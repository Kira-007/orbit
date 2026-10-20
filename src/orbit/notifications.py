"""Task notification lifecycle (port of notifications.js)."""
import json
import time

from .paths import STATE_DIR
from .store import PROVIDERS

ACTIVE = ('working', 'waiting')
COMPLETE = ('done', 'error')
STATES = ACTIVE + COMPLETE + ('idle', 'unknown')
FRESH_MS, RETENTION_MS, MAX_VISIBLE, MAX_TRACKED = 15 * 60000, 24 * 3600000, 100, 200
FILE = STATE_DIR / 'notifications.json'


def _stamp(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _title(v):
    return ' '.join(v.split())[:160] if isinstance(v, str) else ''


def task_key(s):
    if isinstance(s, dict) and s.get('provider') in PROVIDERS and isinstance(s.get('session'), str) and s['session'].strip():
        return ('codex' if s['provider'].startswith('codex-') else s['provider']) + ':' + s['session'].strip()[:180]
    return ''


def _identity(s):
    return 'started:%s' % s['taskStartedAt'] if _stamp(s.get('taskStartedAt')) else 'title:' + _title(s.get('title'))


def _normalize(s):
    if not isinstance(s, dict) or not task_key(s) or s.get('status') not in STATES or not _stamp(s.get('time')):
        return None
    out = {'provider': s['provider'], 'session': s['session'].strip()[:180], 'status': s['status'], 'time': s['time'],
           'title': _title(s.get('title')) or 'Agent session',
           'workspace': s['workspace'][:300] if isinstance(s.get('workspace'), str) else '',
           'activity': s['activity'][:120] if isinstance(s.get('activity'), str) else ''}
    if _stamp(s.get('taskStartedAt')) and s['taskStartedAt'] <= s['time'] + 1000:
        out['taskStartedAt'] = s['taskStartedAt']
    return out


def _new_record(s):
    return {'session': s, 'run': _identity(s) if _stamp(s.get('taskStartedAt')) else '%s:%s' % (_identity(s), s['time']),
            'firstTime': s['time'], 'completedAt': s['time'] if s['status'] in COMPLETE else None,
            'reason': None, 'closedAt': None}


def _different_run(record, s):
    before = record['session']
    if _stamp(s.get('taskStartedAt')):
        if _stamp(before.get('taskStartedAt')):
            return s['taskStartedAt'] != before['taskStartedAt']
        return s['taskStartedAt'] > record['firstTime']
    if _stamp(before.get('taskStartedAt')):
        return False
    return s['time'] > before['time'] and (s['title'] != before['title'] or (before['status'] in COMPLETE and s['status'] in ACTIVE))


class NotificationFeed:
    def __init__(self):
        self.records = {}
        self._load()

    def _load(self):
        try:
            data = json.loads(FILE.read_text())
        except (OSError, ValueError):
            return
        for item in (data if isinstance(data, list) else [])[-MAX_TRACKED:]:
            session = _normalize(item.get('session'))
            if session:
                self.records[task_key(session)] = {**_new_record(session), **{
                    k: item[k] for k in ('run', 'firstTime', 'completedAt', 'reason', 'closedAt') if k in item}}

    def save(self):
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            FILE.write_text(json.dumps(list(self.records.values())))
        except OSError:
            pass

    def update(self, sessions, completion_minutes=10, now=None):
        now = now or time.time() * 1000
        lifetime = max(0, min(60, completion_minutes)) * 60000
        incoming = {}
        for value in sessions:
            s = _normalize(value)
            if not s or s['time'] > now + 60000:
                continue
            key = task_key(s)
            old = incoming.get(key)
            if not old or s['time'] > old['time'] or (s['time'] == old['time'] and s['provider'] == 'codex-desktop'):
                incoming[key] = s
        for key, s in sorted(incoming.items(), key=lambda kv: -kv[1]['time'])[:MAX_TRACKED]:
            record = self.records.get(key)
            if record and s['time'] < record['session']['time']:
                continue
            if not record or _different_run(record, s):
                record = _new_record(s)
            else:
                if not _stamp(s.get('taskStartedAt')) and _stamp(record['session'].get('taskStartedAt')):
                    s['taskStartedAt'] = record['session']['taskStartedAt']
                record['session'] = s
                if _stamp(s.get('taskStartedAt')):
                    record['run'] = _identity(s)
                if s['status'] in COMPLETE and record['completedAt'] is None:
                    record['completedAt'] = s['time']
            self.records[key] = record
        visible = []
        for key, record in list(self.records.items()):
            s = record['session']
            if s['time'] > now + 60000 or now - max(s['time'], min(record['closedAt'] or 0, now)) > RETENTION_MS:
                del self.records[key]
                continue
            if s['status'] in ACTIVE:
                if now - s['time'] >= FRESH_MS:
                    if not record['reason']:
                        record['reason'], record['closedAt'] = 'inactive', now
                elif record['reason'] == 'inactive':
                    record['reason'] = record['closedAt'] = None
            elif s['status'] in COMPLETE:
                done = record['completedAt'] if record['completedAt'] is not None else s['time']
                if now - done >= lifetime and not record['reason']:
                    record['reason'], record['closedAt'] = 'expired', now
                elif record['reason'] == 'inactive' and now - done < lifetime:
                    record['reason'] = record['closedAt'] = None
            elif not record['reason']:
                record['reason'], record['closedAt'] = 'inactive', now
            if not record['reason']:
                visible.append(s)
        if len(self.records) > MAX_TRACKED:
            keep = sorted(self.records.items(), key=lambda kv: -kv[1]['session']['time'])[:MAX_TRACKED]
            self.records = dict(keep)
        visible.sort(key=lambda s: (-s['time'], task_key(s)))
        return [s for s in visible if task_key(s) in self.records][:MAX_VISIBLE]

    def dismiss(self, session, now=None):
        s = _normalize(session)
        if not s:
            return
        key = task_key(s)
        record = self.records.get(key)
        if record and s['time'] < record['session']['time'] and _different_run(record, s):
            return
        if not record or _different_run(record, s):
            record = _new_record(s)
        record['reason'], record['closedAt'] = 'dismissed', now or time.time() * 1000
        self.records[key] = record
        self.save()
