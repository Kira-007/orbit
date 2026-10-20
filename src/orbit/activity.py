"""Collects agent activity from Codex session logs and hook events (port of activity.cjs)."""
import json
import os
import subprocess
from pathlib import Path

from .store import codex_event, now_ms
from .usage import normalize_agy, normalize_codex

ROOT = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'sessions'
TAIL_WINDOW = 262144


def _jsonl_files(root):
    found = []
    for dirpath, _, names in os.walk(root):
        found.extend(os.path.join(dirpath, n) for n in names if n.endswith('.jsonl'))
    return found


class Activity:
    def __init__(self, store, state_dir, root=ROOT):
        self.store, self.state_dir, self.root = store, Path(state_dir), Path(root)
        self.events = self.state_dir / 'events'
        self.events.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.tails, self.event_times, self.files, self.last_scan = {}, {}, [], 0

    def poll(self):
        now = now_ms()
        try:
            file = self.state_dir / 'agy-usage.json'
            if file.stat().st_size < 32768:
                usage = normalize_agy(json.loads(file.read_text()))
                if usage and usage['time'] > (self.store.usage.get('antigravity') or {}).get('time', 0):
                    self.store.usage['antigravity'] = usage
        except (OSError, ValueError):
            pass
        if now - self.last_scan > 10000:
            self.last_scan = now
            recent = []
            for file in _jsonl_files(self.root):
                try:
                    mtime = os.stat(file).st_mtime * 1000
                except OSError:
                    continue
                if now - mtime < 86400000:
                    recent.append((mtime, file))
            self.files = [f for _, f in sorted(recent, reverse=True)[:40]]
            self._processes()
        for file in self.files:
            self._tail(file)
        try:
            names = os.listdir(self.events)
        except OSError:
            return
        for name in names:
            if not name.endswith('.json'):
                continue
            file = self.events / name
            try:
                stat = file.stat()
                if self.event_times.get(file) == stat.st_mtime_ns:
                    continue
                self.event_times[file] = stat.st_mtime_ns
                if stat.st_size < 16384:
                    self.store.update(json.loads(file.read_text()))
            except (OSError, ValueError):
                pass

    def _tail(self, file):
        try:
            size = os.stat(file).st_size
            tail = self.tails.get(file)
            if tail is None or size < tail['offset']:
                tail = {'offset': 0, 'pending': b'', 'meta': None}
                self.tails[file] = tail
                with open(file, 'rb') as handle:
                    for line in handle.read(min(32768, size)).split(b'\n'):
                        try:
                            record = json.loads(line)
                            if record.get('type') == 'session_meta':
                                tail['meta'] = record.get('payload')
                        except ValueError:
                            pass
                if size > TAIL_WINDOW:
                    tail['offset'] = size - TAIL_WINDOW
            if size == tail['offset']:
                return
            with open(file, 'rb') as handle:
                handle.seek(tail['offset'])
                chunk = handle.read(min(size - tail['offset'], 1024 * 1024))
            skip = tail['offset'] > 0 and not tail['pending'] and tail['offset'] == size - TAIL_WINDOW
            tail['offset'] += len(chunk)
            lines = (tail['pending'] + chunk).split(b'\n')
            tail['pending'] = lines.pop()
            if skip and lines:
                lines.pop(0)
            mtime = os.stat(file).st_mtime * 1000
            for line in lines:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get('type') == 'session_meta':
                    tail['meta'] = record.get('payload')
                limits = (record.get('payload') or {}).get('rate_limits')
                if limits:
                    from .store import _parse_time
                    usage = normalize_codex(limits, _parse_time(record.get('timestamp')) or mtime)
                    if usage and usage['time'] > (self.store.usage.get('codex') or {}).get('time', 0):
                        self.store.usage['codex'] = usage
                event = codex_event(record, tail['meta'], mtime)
                if event:
                    self.store.update(event)
        except OSError:
            pass

    def _processes(self):
        try:
            names = set(subprocess.run(['ps', '-eo', 'comm='], capture_output=True, text=True, timeout=2).stdout.lower().split())
        except (OSError, subprocess.SubprocessError):
            return
        self.store.online = {
            'claude': 'claude' in names, 'codex-cli': 'codex' in names,
            'codex-desktop': bool(names & {'chatgpt', 'codex-desktop'}), 'antigravity': bool(names & {'antigravity', 'agy'}),
        }
