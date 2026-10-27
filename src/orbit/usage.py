"""Quota normalization and fresh readers for Codex, AGY and Claude (port of usage.cjs and friends)."""
import json
import math
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


def _ms(stamp):
    try:
        return int(datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp() * 1000)
    except (AttributeError, ValueError):
        return None


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _window_label(minutes, fallback):
    """Name a quota window by its length; keeps 'Session'/'Weekly' so saved bar selections still match."""
    if not _finite(minutes) or minutes <= 0:
        return fallback
    if minutes <= 24 * 60:
        return 'Session' if minutes == 300 else f'{round(minutes / 60)}h'
    days = minutes / 1440
    if 6 <= days <= 8:
        return 'Weekly'
    if 27 <= days <= 32:
        return 'Monthly'
    return f'{round(days)}d'


def normalize_codex(limits, stamp):
    if not isinstance(limits, dict) or not _finite(stamp):
        return None
    windows = []
    for key, label in (('primary', 'Session'), ('secondary', 'Weekly')):
        w = limits.get(key)
        if not isinstance(w, dict) or not _finite(w.get('used_percent')):
            continue
        # Slots don't fix the period (a plan may put a monthly window in secondary); the duration does.
        label = _window_label(w.get('window_minutes'), label)
        windows.append({'label': label, 'remaining': round(max(0, min(100, 100 - w['used_percent']))),
                        'reset': w['resets_at'] * 1000 if _finite(w.get('resets_at')) else None,
                        'minutes': w.get('window_minutes')})
    return {'time': stamp, 'windows': windows} if windows else None


def normalize_agy(payload):
    if not isinstance(payload, dict) or not _finite(payload.get('time')) or not isinstance(payload.get('quota'), dict):
        return None
    windows = []
    for label, value in list(payload['quota'].items())[:64]:
        if not isinstance(value, dict) or not _finite(value.get('remaining_fraction')) or not 0 <= value['remaining_fraction'] <= 1:
            continue
        reset = _ms(value['reset_time']) if isinstance(value.get('reset_time'), str) else None
        if reset is None and _finite(value.get('reset_in_seconds')):
            reset = payload['time'] + value['reset_in_seconds'] * 1000
        windows.append({'label': label[:120], 'remaining': round(value['remaining_fraction'] * 100), 'reset': reset})
    return {'time': payload['time'], 'windows': windows} if windows else None


def normalize_claude(payload, stamp=None):
    stamp = stamp or int(time.time() * 1000)
    if not isinstance(payload, dict):
        return None
    windows = []
    for key, label in (('five_hour', 'Session'), ('seven_day', 'Weekly'), ('seven_day_sonnet', 'Sonnet · Week'), ('seven_day_opus', 'Opus · Week')):
        bucket = payload.get(key)
        if not isinstance(bucket, dict) or not _finite(bucket.get('utilization')):
            continue
        reset = _ms(bucket['resets_at']) if isinstance(bucket.get('resets_at'), str) else None
        windows.append({'label': label, 'remaining': round(max(0, min(100, 100 - bucket['utilization']))), 'reset': reset})
    return {'time': stamp, 'windows': windows} if windows else None


def agy_usage():
    try:
        out = subprocess.run(['agy', '-p', '/usage', '--output-format', 'json'], capture_output=True, text=True, timeout=30).stdout
        result = json.loads(out)
        groups = result['command']['data']['groups']
        if result.get('status') != 'SUCCESS':
            raise ValueError
        quota = {f"{g['name']} · {b['name']}": b for g in groups for b in g.get('buckets') or []}
        usage = normalize_agy({'time': int(time.time() * 1000), 'quota': quota})
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise RuntimeError('AGY quota refresh failed')
    if not usage:
        raise RuntimeError('AGY did not return quota data')
    return usage


def codex_usage():
    try:
        child = subprocess.Popen(['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
    except OSError:
        raise RuntimeError('Codex could not start')
    timer = threading.Timer(20, child.kill)
    timer.start()

    def send(value):
        child.stdin.write(json.dumps(value) + '\n')
        child.stdin.flush()
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'orbit_usage', 'version': '1.0.0'}}})
        for line in child.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('id') == 1:
                if message.get('error'):
                    raise RuntimeError('Codex initialization failed')
                send({'method': 'initialized'})
                send({'id': 2, 'method': 'account/rateLimits/read'})
            elif message.get('id') == 2:
                if message.get('error'):
                    raise RuntimeError('Codex account quota unavailable')
                result = message.get('result') or {}
                limit = (result.get('rateLimitsByLimitId') or {}).get('codex') or result.get('rateLimits') or {}
                limits = {k: {'used_percent': limit[k].get('usedPercent'), 'resets_at': limit[k].get('resetsAt'),
                              'window_minutes': limit[k].get('windowDurationMins')} for k in ('primary', 'secondary') if limit.get(k)}
                usage = normalize_codex(limits, int(time.time() * 1000))
                if not usage:
                    raise RuntimeError('Codex did not return quota data')
                return usage
        raise RuntimeError('Codex quota refresh failed')
    except (OSError, ValueError):
        raise RuntimeError('Codex quota refresh failed')
    finally:
        timer.cancel()
        child.kill()


class ClaudeUsage:
    """Reads Claude Code quota via the OAuth usage endpoint, cached and rate-limit aware."""

    def __init__(self, state_file=None):
        config = os.environ.get('CLAUDE_CONFIG_DIR') or str(Path.home() / '.claude')
        self.credentials = Path(config) / '.credentials.json'
        # Cache and cooldown survive restarts, so relaunching never re-triggers a 429.
        self.state_file = state_file
        self.cached, self.retry_after = None, 0
        try:
            saved = json.loads(state_file.read_text())
            self.cached, self.retry_after = saved.get('cached'), float(saved.get('retryAfter') or 0)
        except (AttributeError, OSError, ValueError, TypeError):
            pass

    def _save(self):
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({'cached': self.cached, 'retryAfter': self.retry_after}))
        except OSError:
            pass

    def __call__(self):
        now = time.time() * 1000
        if self.cached and now - self.cached['time'] < 60000:
            return self.cached
        if now < self.retry_after:
            raise RuntimeError('Claude rate-limited the quota check; retrying in %d min' % max(1, round((self.retry_after - now) / 60000)))
        try:
            token = json.loads(self.credentials.read_text())['claudeAiOauth']['accessToken']
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError('Claude Code sign-in not found')
        if not isinstance(token, str) or not token:
            raise RuntimeError('Sign in to Claude Code to read quota')
        request = urllib.request.Request('https://api.anthropic.com/api/oauth/usage', headers={
            'Authorization': 'Bearer ' + token, 'anthropic-beta': 'oauth-2025-04-20', 'User-Agent': 'Orbit/0.2.0'})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                body = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                try:
                    seconds = float(error.headers.get('retry-after'))
                except (TypeError, ValueError):
                    seconds = 300
                self.retry_after = now + max(60, min(900, seconds)) * 1000
                self._save()
                raise RuntimeError('Claude rate-limited the quota check; retrying in %d min' % max(1, round(seconds / 60)))
            raise RuntimeError('Claude Code sign-in needs refreshing' if error.code in (401, 403) else 'Claude quota refresh failed')
        except (OSError, ValueError):
            raise RuntimeError('Claude quota refresh failed')
        usage = normalize_claude(body, int(now))
        if not usage:
            raise RuntimeError('Claude did not return quota data')
        self.cached = usage
        self._save()
        return usage


claude_usage = ClaudeUsage(Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'agent-pet/claude-usage.json')
