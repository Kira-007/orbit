#!/usr/bin/env python3
"""Install Orbit for the current user; no root or system application patches."""
import argparse,ctypes,datetime,json,pathlib,shlex,shutil,subprocess
from integration import ROOT,HOME,CONFIG,DATA,STATE,remove_block,block
parser=argparse.ArgumentParser()
parser.add_argument('--config',type=pathlib.Path,default=CONFIG/'hypr/hyprland.lua',help='Hyprland Lua configuration to integrate')
parser.add_argument('--no-autostart',action='store_true')
parser.add_argument('--hooks',action='store_true',help='Also enable passive Claude Code and AGY hooks')
parser.add_argument('--check',action='store_true',help='Check requirements without modifying files')
args=parser.parse_args()
missing=[x for x in ('node','python3','hyprctl','Xwayland') if not shutil.which(x)]
if not any(shutil.which(x) for x in ('electron44','electron')):missing.append('electron44 or electron')
for name in ('libX11.so.6','libXext.so.6'):
    try:ctypes.CDLL(name)
    except OSError:missing.append(name)
if missing:parser.exit(1,'Missing dependencies: '+', '.join(missing)+'\n')
probe=subprocess.run(['hyprctl','eval','assert(type(hl.window_rule)=="function")'],capture_output=True,text=True)
if probe.returncode or probe.stdout.strip()!='ok':parser.exit(1,'Orbit requires a running Hyprland session with the Lua API (tested on 0.56.2).\n')
config=args.config.expanduser().resolve()
if not config.is_file():parser.exit(1,'Lua configuration not found: '+str(config)+'. Pass --config /path/to/hyprland.lua.\n')
if args.check:print('Dependencies and Hyprland Lua API available.');raise SystemExit
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
STATE.mkdir(parents=True,exist_ok=True)
manifest=STATE/'portable-install.json'
record=json.loads(manifest.read_text()) if manifest.exists() else {}
if record.get('root') and record['root']!=str(ROOT):parser.exit(1,'Another portable Orbit installation exists. Uninstall it first.\n')
text=config.read_text()
shutil.copy2(config,str(config)+'.before-orbit-'+stamp)
config.write_text(remove_block(text).rstrip()+'\n\n'+block(not args.no_autostart))
result=subprocess.run(['hyprctl','reload'],capture_output=True,text=True)
errors=subprocess.run(['hyprctl','configerrors'],capture_output=True,text=True)
if result.returncode or errors.stdout.strip():
    config.write_text(text);subprocess.run(['hyprctl','reload'],capture_output=True)
    parser.exit(1,'Hyprland reported configuration errors; original configuration restored.\n'+errors.stdout)
def edit(file,transform):
    existed=file.exists();d=json.loads(file.read_text()) if existed else {}
    if existed:shutil.copy2(file,str(file)+'.before-orbit-'+stamp)
    transform(d);file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps(d,indent=2)+'\n')
command=lambda provider,status:'python3 '+shlex.quote(str(ROOT/'emit.py'))+' '+provider+' '+status
if args.hooks:
    def claude(d):
        for event,status in {'UserPromptSubmit':'working','PreToolUse':'working','PostToolUse':'working','Notification':'waiting','Stop':'done','SessionEnd':'idle'}.items():
            entries=d.setdefault('hooks',{}).setdefault(event,[])
            for group in entries:group['hooks']=[h for h in group.get('hooks',[]) if str(ROOT/'emit.py') not in h.get('command','')]
            entries[:]=[g for g in entries if g.get('hooks')]
            group={'hooks':[{'type':'command','command':command('claude',status),'timeout':3}]}
            if event in ('PreToolUse','PostToolUse'):group['matcher']='.*'
            if event=='Notification':group['matcher']='permission_prompt|idle_prompt'
            entries.append(group)
    edit(HOME/'.claude/settings.json',claude)
    edit(HOME/'.gemini/config/hooks.json',lambda d:d.update({'orbit-agent-pet':{'enabled':True,'PreInvocation':[{'type':'command','command':command('antigravity','working'),'timeout':3}],'Stop':[{'type':'command','command':command('antigravity','done'),'timeout':3}]}}))
apps=DATA/'applications';apps.mkdir(parents=True,exist_ok=True)
# Desktop Entry quoting differs from shell quoting.
def desktop_quote(value):return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')+'"'
launcher=apps/'orbit.desktop'
launcher.write_text('[Desktop Entry]\nType=Application\nName=Orbit\nComment=Coding agent companion for Hyprland\nExec='+desktop_quote(ROOT/'start.sh')+'\nIcon='+str(ROOT/'tray.png')+'\nTerminal=false\nCategories=Utility;Development;\n')
record.update(root=str(ROOT),config=str(config),launcher=str(launcher),hooks=args.hooks or record.get('hooks',False))
manifest.write_text(json.dumps(record,indent=2)+'\n')
print('Installed Orbit for this user. Run ./start.sh; '+('autostart enabled.' if not args.no_autostart else 'autostart disabled.'))
if args.hooks:print('Restart Claude/AGY to load hooks. Hook support depends on your CLI version.')
