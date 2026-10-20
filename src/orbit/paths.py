import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'agent-pet'
SETTINGS_FILE = STATE_DIR / 'settings.json'
POSITION_FILE = STATE_DIR / 'position.json'
