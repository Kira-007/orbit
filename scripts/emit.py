#!/usr/bin/env python3
"""A passive status hook. Stores a short task label; never changes agent decisions."""
import argparse, hashlib, json, os, pathlib, sys, time
parser=argparse.ArgumentParser()
parser.add_argument('provider',choices=['claude','codex-cli','codex-desktop','antigravity'])
parser.add_argument('status',choices=['working','waiting','done','error','idle','unknown'])
parser.add_argument('--session');parser.add_argument('--title');args=parser.parse_args()
try:
    payload=json.load(sys.stdin) if not sys.stdin.isatty() else {}
except Exception:payload={}
try:
    session=args.session or str(payload.get('session_id') or payload.get('conversationId') or os.getppid())
    workspace=payload.get('cwd') or next(iter(payload.get('workspacePaths') or []),os.getcwd())
    event={'provider':args.provider,'status':args.status,'session':session,'workspace':workspace,'title':args.title or pathlib.Path(workspace).name,'time':int(time.time()*1000),'source':'hook'}
    root=pathlib.Path(os.environ.get('XDG_STATE_HOME',str(pathlib.Path.home()/'.local/state')))/'agent-pet/events';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    name=hashlib.sha256((args.provider+session).encode()).hexdigest()+'.json'
    previous={}
    try:previous=json.loads((root/name).read_text())
    except Exception:pass
    prompt=payload.get('prompt') or payload.get('userPrompt') or ''
    event['title']=args.title or (' '.join(str(prompt).split())[:160] if prompt else previous.get('title')) or pathlib.Path(workspace).name
    tool=payload.get('tool_name') or (payload.get('toolCall') or {}).get('name')
    event['activity']=('Using '+str(tool))[:120] if tool else ('Working on task' if args.status=='working' else 'Task '+args.status)
    tmp=root/(name+'.'+str(os.getpid())+'.tmp');tmp.write_text(json.dumps(event));tmp.chmod(0o600);tmp.replace(root/name)
except Exception:pass
print('{}')
