#!/usr/bin/env python3
"""Capture only AGY quota metadata from its documented status-line payload."""
import json, os, pathlib, sys, tempfile, time

def capture(payload, directory):
    quota = payload.get('quota')
    if not isinstance(quota, dict):
        return
    cleaned = {}
    for key, value in list(quota.items())[:64]:
        if not isinstance(value, dict):
            continue
        fraction = value.get('remaining_fraction')
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 <= fraction <= 1:
            continue
        cleaned[str(key)[:120]] = {k: value[k] for k in ('remaining_fraction', 'reset_time', 'reset_in_seconds') if k in value and isinstance(value[k], (str, int, float))}
    if not cleaned:
        return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.agy-usage-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'time': int(time.time()*1000), 'quota': cleaned}, stream)
        os.replace(temporary, directory / 'agy-usage.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

if __name__ == '__main__':
    try:
        payload = json.loads(sys.stdin.read(1024*1024))
        root = pathlib.Path(os.environ.get('XDG_STATE_HOME', pathlib.Path.home()/'.local/state')) / 'agent-pet'
        capture(payload, root)
    except Exception:
        pass
