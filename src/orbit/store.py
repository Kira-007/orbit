"""Session store and Codex log event parsing (port of store.cjs)."""
import os
import re
import time
from datetime import datetime

PROVIDERS = ['claude', 'codex-cli', 'codex-desktop', 'antigravity']
STATES = ['working', 'waiting', 'done', 'error', 'idle', 'unknown']
_RANK = {'waiting': 0, 'error': 1, 'working': 2, 'unknown': 3, 'done': 4, 'idle': 5}
_ENV = re.compile(r'<environment_context>[\s\S]*?</environment_context>')
BUSY = ('working', 'waiting')


def now_ms():
    return int(time.time() * 1000)


class Store:
    def __init__(self):
        self.sessions = {}
        self.online = {}
        self.usage = {}
        self.usage_status = {}

    def update(self, e):
        if (not isinstance(e, dict) or e.get('provider') not in PROVIDERS or e.get('status') not in STATES
                or not isinstance(e.get('session'), str) or not isinstance(e.get('time'), (int, float))):
            return False
        key = e['provider'] + ':' + e['session']
        old = self.sessions.get(key)
        if old and old['time'] > e['time']:
            return False
        workspace = str(e.get('workspace') or (old or {}).get('workspace') or '')
        started = e.get('taskStartedAt')
        if not isinstance(started, (int, float)):
            started = e['time'] if old and e['status'] in BUSY and old['status'] not in BUSY else (old or {}).get('taskStartedAt')
        default_activity = (old or {}).get('activity') or 'Working on task' if e['status'] in BUSY else 'Task ' + e['status']
        self.sessions[key] = {
            'provider': e['provider'], 'session': e['session'][:180], 'status': e['status'], 'time': e['time'],
            'workspace': workspace[:300],
            'title': str(e.get('title') or (old or {}).get('title') or os.path.basename(workspace) or 'Agent session')[:160],
            'activity': str(e.get('activity') or default_activity)[:120],
            'source': e.get('source') or 'hook', 'taskStartedAt': started,
        }
        return True

    def snapshot(self, now=None):
        now = now or now_ms()
        sessions = []
        for e in self.sessions.values():
            if now - e['time'] >= 86400000:
                continue
            stale = e['status'] in BUSY and now - e['time'] > 900000
            sessions.append({**e, 'status': 'unknown' if stale else e['status']})
        sessions.sort(key=lambda s: (_RANK[s['status']], -s['time']))
        return {
            'sessions': sessions[:30], 'online': self.online, 'usage': self.usage,
            'usageStatus': self.usage_status, 'time': now,
        }


def _clean(text):
    return _ENV.sub('', text).strip()


def _flat(text, limit):
    return ' '.join(str(text).split())[:limit]


def _parse_time(stamp):
    try:
        return int(datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp() * 1000)
    except (AttributeError, ValueError):
        return None


def codex_event(record, meta, file_time):
    source = meta.get('source') if meta else None
    if (not meta or (isinstance(source, dict) and source.get('subagent')) or meta.get('parent_thread_id')
            or (meta.get('agent_path') and meta['agent_path'] != '/root')):
        return None
    payload = record.get('payload') or {}
    kind, ptype = record.get('type'), payload.get('type')
    statuses = {'task_started': 'working', 'turn_started': 'working', 'task_complete': 'done', 'turn_complete': 'done',
                'turn_aborted': 'idle', 'permission_request': 'waiting', 'user_message': 'working', 'agent_message': 'working'}
    status = statuses.get(ptype) if kind == 'event_msg' else None
    title = activity = None
    if kind == 'event_msg' and ptype == 'user_message':
        title = payload.get('message')
    if kind == 'response_item' and ptype == 'message' and payload.get('role') == 'user':
        content = payload.get('content')
        text = _clean(' '.join(c.get('text') or '' for c in content if c.get('type') in ('input_text', 'text'))) if isinstance(content, list) else ''
        if text and not text.startswith('<'):
            title, status = text, 'working'
    if kind == 'response_item' and ptype in ('function_call', 'custom_tool_call'):
        status = 'working'
        activity = 'Using ' + re.sub(r'^.*__', '', str(payload.get('name') or 'tool')).replace('_', ' ')
    if kind == 'event_msg' and ptype == 'agent_message':
        activity = _flat(payload.get('message') or 'Working on task', 120)
    if kind == 'event_msg' and ptype == 'task_complete' and payload.get('last_agent_message'):
        activity = _flat(payload['last_agent_message'], 120)
    if kind == 'event_msg' and ptype == 'item_completed':
        item = payload.get('item') or {}
        content = item.get('content')
        text = _clean(' '.join(c['text'] for c in content if isinstance(c.get('text'), str))) if isinstance(content, list) else ''
        itype = item.get('type')
        if itype == 'UserMessage' and text and not text.startswith('<'):
            title, status = text, 'working'
        elif itype == 'AgentMessage':
            status = 'done' if item.get('phase') == 'final_answer' else 'working'
            activity = text or None
        elif itype in ('Reasoning', 'CommandExecution', 'McpToolCall', 'DynamicToolCall', 'FileChange', 'WebSearch', 'ImageGeneration'):
            status = 'working'
            activity = 'Thinking' if itype == 'Reasoning' else 'Using ' + re.sub(r'([a-z])([A-Z])', r'\1 \2', itype).lower()
    if not status:
        return None
    if title:
        title = _flat(title, 160)
    stamp = _parse_time(record.get('timestamp')) or file_time
    starts = (kind == 'event_msg' and ptype in ('task_started', 'turn_started', 'user_message')) or \
        (kind == 'event_msg' and ptype == 'item_completed' and (payload.get('item') or {}).get('type') == 'UserMessage')
    event = {
        'provider': 'codex-desktop' if re.search('desktop', meta.get('originator') or '', re.I) else 'codex-cli',
        'session': str(meta.get('id') or meta.get('session_id') or 'unknown'), 'workspace': meta.get('cwd') or '',
        'status': status, 'time': stamp, 'title': title, 'activity': activity, 'source': 'local log',
    }
    if starts:
        event['taskStartedAt'] = stamp
    return event
