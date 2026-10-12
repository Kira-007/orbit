#!/usr/bin/env python3
"""Remove managed integration, retaining user settings and downloaded sprites."""
import json,pathlib,subprocess
from integration import ROOT,HOME,STATE,remove_block
manifest=STATE/'portable-install.json'
if not manifest.exists():raise SystemExit('No portable Orbit integration is installed.')
record=json.loads(manifest.read_text())
if record['root']!=str(ROOT):raise SystemExit('Run uninstall.py from the installed Orbit directory.')
p=pathlib.Path(record['config'])
if p.exists():p.write_text(remove_block(p.read_text()));subprocess.run(['hyprctl','reload'],check=False)
if record.get('hooks'):
 p=HOME/'.claude/settings.json'
 if p.exists():
  d=json.loads(p.read_text())
  for name,entries in d.get('hooks',{}).items():
   for group in entries:group['hooks']=[h for h in group.get('hooks',[]) if not any(str(ROOT/rel) in h.get('command','') for rel in ('emit.py','scripts/emit.py'))]
   entries[:]=[g for g in entries if g.get('hooks')]
  p.write_text(json.dumps(d,indent=2)+'\n')
 p=HOME/'.gemini/config/hooks.json'
 if p.exists():
  d=json.loads(p.read_text());entry=d.get('orbit-agent-pet',{})
  if any(str(ROOT/rel) in json.dumps(entry) for rel in ('emit.py','scripts/emit.py')):d.pop('orbit-agent-pet',None);p.write_text(json.dumps(d,indent=2)+'\n')
pathlib.Path(record['launcher']).unlink(missing_ok=True)
manifest.unlink()
print('Orbit integration removed. Quit Orbit from the tray. Settings and activity data retained.')
