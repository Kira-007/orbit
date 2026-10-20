"""Thread discovery and message dispatch to agent CLIs (port of main.cjs start-task)."""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from .desktop_ipc import desktop_url, send_desktop_message
from .paths import ROOT
from .store import PROVIDERS, now_ms

_INACTIVE = re.compile(r'(?:thread|session|conversation).{0,100}(?:not (?:loaded|running|active|open)|is (?:closed|inactive)|must be (?:loaded|resumed))'
                       r'|(?:not (?:loaded|running|active|open)|closed|inactive).{0,100}(?:thread|session|conversation)', re.I)


def open_threads(provider, store):
    if provider not in PROVIDERS:
        return []
    try:
        out = subprocess.run(['python3', str(ROOT / 'scripts/threads.py'), provider], capture_output=True, text=True, timeout=5).stdout
        threads = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        threads = []
    threads = [t for t in threads if isinstance(t, dict) and isinstance(t.get('id'), str) and isinstance(t.get('name'), str)] \
        if isinstance(threads, list) else []
    for s in store.snapshot()['sessions']:
        if s['provider'] == provider and not any(t['id'] == s['session'] for t in threads):
            threads.append({'id': s['session'], 'name': s['title'], 'path': s['workspace']})
    return threads


def _codex_thread_in_terminal(thread):
    """True when a codex process attached to a tty is already running this thread."""
    for pid in filter(str.isdigit, os.listdir('/proc')):
        try:
            if Path(f'/proc/{pid}/comm').read_text().strip() != 'codex':
                continue
            args = Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace').split('\0')
            tty = re.match(r'^/dev/(pts/|tty)', os.readlink(f'/proc/{pid}/fd/0'))
            if tty and thread['id'] in args:
                return True
        except OSError:
            continue
    return False


def start_task(provider, prompt, thread_id, store, on_finish):
    """Dispatch a prompt. Returns (ok, message); on_finish(code, output) runs from a worker thread for --print runs."""
    if provider not in PROVIDERS or not prompt.strip() or len(prompt) > 12000:
        return False, 'Enter a message and choose a harness'
    selected = next((t for t in open_threads(provider, store) if t['id'] == thread_id), None)
    if not selected:
        return False, 'Choose a conversation before sending'
    if provider == 'codex-desktop':
        desktop = os.environ.get('ORBIT_CODEX_DESKTOP') or shutil.which('codex-desktop') or shutil.which('chatgpt')
        if not desktop:
            return False, 'Codex Desktop launcher is unavailable'
        try:
            subprocess.Popen([desktop, desktop_url(selected['id'])], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            send_desktop_message(selected['id'], prompt)
        except (OSError, ValueError, RuntimeError) as error:
            return False, str(error) or 'Desktop could not accept the message'
        return True, 'Sent to %s in Desktop' % selected['name']
    name = 'codex' if provider.startswith('codex-') else 'claude' if provider == 'claude' else 'agy'
    executable = shutil.which(name)
    if not executable:
        return False, name + ' is not installed or is missing from PATH'
    cwd = selected.get('path') or ''
    if not os.path.isdir(cwd):
        cwd = str(Path.home())
    if provider == 'codex-cli':
        if _codex_thread_in_terminal(selected):
            result = subprocess.run([executable, 'queue', '--thread', selected['id'], '--message', prompt], cwd=cwd,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True, 'Message queued for ' + selected['name']
            text = result.stderr or result.stdout
            if not _INACTIVE.search(text):
                return False, ('Could not queue message: ' + text)[:300]
        terminal = shutil.which('kitty')
        if not terminal:
            return False, 'Install kitty to reopen this conversation'
        try:
            subprocess.Popen([terminal, '--directory', cwd, '--title', selected['name'], executable, 'resume', selected['id'], prompt],
                             cwd=cwd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False, 'Could not reopen ' + selected['name']
        return True, 'Opened %s in a terminal' % selected['name']
    if provider == 'claude':
        args = ['--resume', selected['id'], '--print', prompt]
    else:
        args = ['--conversation', selected['id'], *(['--project', str(selected['project'])] if selected.get('project') else []), '--print', prompt]
    try:
        child = subprocess.Popen([executable, *args], cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError:
        return False, 'Could not resume ' + selected['name']
    base = {'provider': provider, 'session': selected['id'], 'title': selected['name'], 'workspace': cwd}
    store.update({**base, 'status': 'working', 'time': now_ms(), 'activity': 'Continuing conversation'})

    def wait():
        out, err = child.communicate()
        ok = child.returncode == 0
        text = (out[-16000:] if ok else err[-1000:]).strip()[-1000:] or 'Conversation finished'
        on_finish({**base, 'status': 'done' if ok else 'error', 'time': now_ms(), 'activity': text})
    threading.Thread(target=wait, daemon=True).start()
    return True, 'Continuing ' + selected['name']
