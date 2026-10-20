"""Settings normalization, compatible with the settings.json written by the Electron build."""
import json
import os
from urllib.parse import unquote, urlparse

from .paths import ROOT, SETTINGS_FILE, STATE_DIR

STATES = ['idle', 'walking', 'dragging', 'working', 'waiting', 'done', 'error', 'unknown']
HARNESSES = ['codex-cli', 'codex-desktop', 'claude', 'antigravity']
DEFAULTS = {
    'animations': True, 'controls': False, 'hoverDelay': 750, 'completionMinutes': 10,
    'harness': 'codex-cli', 'usageBar': None, 'petScale': 1, 'movementSpeed': 700,
    'petName': 'Orbit', 'activeSpritePet': '', 'spritePets': [],
}


def _num(value, low, high, default=0):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _sheets(value):
    sheets = {}
    for state in STATES:
        entry = (value or {}).get(state)
        if not isinstance(entry, dict) or not isinstance(entry.get('sheet'), str):
            continue
        frames = int(_num(entry.get('frames'), 1, 256, 1))
        sheet = {
            'sheet': entry['sheet'], 'name': str(entry.get('name') or 'Sprite sheet')[:180],
            'frames': frames, 'columns': int(_num(entry.get('columns') or frames, 1, 256, frames)),
            'fps': _num(entry.get('fps'), 1, 60, 10),
            'offsetX': _num(entry.get('offsetX'), -100, 100), 'offsetY': _num(entry.get('offsetY'), -100, 100),
        }
        if entry.get('facing') in ('left', 'right'):
            sheet['facing'] = entry['facing']
        sheets[state] = sheet
    return sheets


def sheet_path(sheet):
    """Resolve a sheet reference (file:// URL or repository-relative path) to a file path."""
    if sheet.startswith('file:'):
        return unquote(urlparse(sheet).path)
    return str(ROOT / sheet)


def bundled_pets():
    with open(ROOT / 'assets/library/pets.json') as handle:
        return json.load(handle)


def normalize(value=None):
    value = value or {}
    pets, seen = [], set()
    for entry in (value.get('spritePets') or [])[:64]:
        pid = entry.get('id') if isinstance(entry, dict) else None
        if not isinstance(pid, str) or not pid or len(pid) > 80 or pid in seen:
            continue
        seen.add(pid)
        pets.append({
            'id': pid, 'name': str(entry.get('name') or 'My pet').strip()[:60] or 'My pet',
            'facing': 'left' if entry.get('facing') == 'left' else 'right',
            'offsetX': _num(entry.get('offsetX'), -100, 100), 'offsetY': _num(entry.get('offsetY'), -100, 100),
            'spriteSheets': _sheets(entry.get('spriteSheets')),
        })
    active = next((p for p in pets if p['id'] == value.get('activeSpritePet')), pets[0] if pets else None)
    bar = value.get('usageBar')
    if not (isinstance(bar, dict) and bar.get('provider') in ('codex', 'claude', 'antigravity')
            and isinstance(bar.get('label'), str) and len(bar['label']) <= 120):
        bar = None
    else:
        bar = {'provider': bar['provider'], 'label': bar['label']}
    return {
        'usageBar': bar, 'spritePets': pets, 'activeSpritePet': active['id'] if active else '',
        'petScale': _num(value.get('petScale'), .6, 2.4, 1) if 'petScale' in value else 1,
        'movementSpeed': _num(value.get('movementSpeed'), 150, 1800, 700) if 'movementSpeed' in value else 700,
        'petName': str(value.get('petName') or '').strip()[:30] or DEFAULTS['petName'],
        'animations': value['animations'] if isinstance(value.get('animations'), bool) else True,
        'controls': value['controls'] if isinstance(value.get('controls'), bool) else False,
        'hoverDelay': value['hoverDelay'] if value.get('hoverDelay') in (400, 750, 1200) else 750,
        'completionMinutes': value['completionMinutes'] if value.get('completionMinutes') in (5, 10, 30, 60) else 10,
        'harness': value['harness'] if value.get('harness') in HARNESSES else 'codex-cli',
    }


def load():
    try:
        with open(SETTINGS_FILE) as handle:
            loaded = normalize(json.load(handle))
    except (OSError, ValueError):
        loaded = None
    if loaded is None or not loaded['spritePets']:
        base = loaded or {}
        loaded = normalize({**base, 'spritePets': bundled_pets()})
    return loaded


def save(value):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, indent=2)
    tmp.replace(SETTINGS_FILE)
