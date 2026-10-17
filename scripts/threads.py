#!/usr/bin/env python3
"""Read conversation names and identifiers from local agent history."""
import contextlib,datetime,json,os,pathlib,re,sqlite3,sys,urllib.parse

LIMIT=300

def label(value):
    """Use human-readable labels, never tool output or injected context blocks."""
    if not isinstance(value,str):return ''
    value=' '.join(value.split())
    return value[:160] if value and not value.startswith('<') else ''

def timestamp(value):
    try:
        if isinstance(value,(int,float)):return value/1000 if value>100000000000 else value
        return datetime.datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,OverflowError):return 0

def log_records(file):
    """Bound work per session while retaining both its first prompt and latest rename."""
    try:
        with file.open('rb') as stream:
            size=stream.seek(0,2);stream.seek(0)
            head=stream.read(65536)
            parts=[head]
            if size>len(head):
                offset=max(len(head),size-65536)
                stream.seek(offset-1);boundary=stream.read(1)==b'\n'
                tail=stream.read(65536)
                parts.append(tail if boundary else tail.split(b'\n',1)[-1])
        for part in parts:
            for line in part.splitlines():
                try:
                    record=json.loads(line)
                    if isinstance(record,dict):yield record
                except (ValueError,UnicodeDecodeError):pass
    except OSError:return

def claude_threads(home):
    root=pathlib.Path(os.environ.get('CLAUDE_CONFIG_DIR',str(home/'.claude'))).expanduser()/'projects'
    sessions={}
    def add(identifier,entry,mtime=0):
        if not isinstance(identifier,str) or not identifier or entry.get('isSidechain'):return
        old=sessions.setdefault(identifier,{'id':identifier,'name':'Untitled conversation','path':str(home),'_rank':0,'_time':0})
        for key,rank in [('firstPrompt',1),('title',2),('summary',3),('customTitle',4)]:
            name=label(entry.get(key))
            if name and rank>=old['_rank']:old['name']=name;old['_rank']=rank
        cwd=entry.get('projectPath') or entry.get('cwd')
        if isinstance(cwd,str) and cwd:old['path']=cwd
        old['_time']=max(old['_time'],mtime,timestamp(entry.get('modified') or entry.get('timestamp') or entry.get('fileMtime')))
    for index in root.glob('*/sessions-index.json'):
        try:
            if index.stat().st_size>4*1024*1024:continue
            data=json.loads(index.read_text());entries=data.get('entries',[]) if isinstance(data,dict) else []
            for entry in entries:
                if isinstance(entry,dict):add(entry.get('sessionId') or entry.get('id'),entry)
        except (OSError,ValueError,TypeError):pass
    files=[]
    for file in root.glob('*/*.jsonl'):
        if file.name.startswith('agent-'):continue
        try:files.append((file.stat().st_mtime,file))
        except OSError:pass
    for mtime,file in sorted(files,key=lambda item:item[0],reverse=True)[:LIMIT]:
        records=list(log_records(file))
        if any(record.get('isSidechain') for record in records):continue
        identifier=next((r['sessionId'] for r in records if isinstance(r.get('sessionId'),str)),file.stem)
        add(identifier,{},mtime)
        first_prompt=False
        for record in records:
            entry={k:record[k] for k in ('cwd','timestamp','customTitle','summary','title') if k in record}
            if not first_prompt and record.get('type')=='user' and not record.get('isMeta'):
                message=record.get('message',{})
                content=message.get('content') if isinstance(message,dict) else None
                if isinstance(content,list):content=' '.join(c.get('text','') for c in content if isinstance(c,dict) and c.get('type')=='text' and isinstance(c.get('text'),str))
                if label(content):entry['firstPrompt']=content;first_prompt=True
            add(identifier,entry,mtime)
    return [{k:value for k,value in session.items() if not k.startswith('_')} for session in sorted(sessions.values(),key=lambda s:s['_time'],reverse=True)[:LIMIT]]

def threads(provider,home=None):
    home=pathlib.Path(home or pathlib.Path.home());result=[]
    if provider in ('codex-cli','codex-desktop'):
        root=pathlib.Path(os.environ.get('CODEX_HOME',str(home/'.codex'))).expanduser()
        versions=lambda file:int(re.search(r'state_(\d+)\.sqlite$',file.name)[1]) if re.search(r'state_(\d+)\.sqlite$',file.name) else -1
        for database in sorted(root.glob('state_*.sqlite'),key=versions,reverse=True):
            try:
                with contextlib.closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)) as c:
                    columns={r[1] for r in c.execute('pragma table_info(threads)')}
                    if not {'id','cwd'}.issubset(columns):continue
                    origin='originator' if 'originator' in columns else "''"
                    names=[f"NULLIF({column},'')" for column in ('name','title') if column in columns]
                    display='COALESCE('+','.join(names+["'Untitled conversation'"])+')' if names else "'Untitled conversation'"
                    source='source' if 'source' in columns else "''"
                    agent_path='agent_path' if 'agent_path' in columns else "''"
                    where='WHERE archived=0' if 'archived' in columns else ''
                    order=next((column for column in ('updated_at_ms','updated_at','created_at','id') if column in columns),'id')
                    rows=c.execute(f'SELECT id,{display},cwd,{source},{origin},{agent_path} FROM threads {where} ORDER BY {order} DESC LIMIT 1000')
                    for identifier,title,cwd,source,client,agent in rows:
                        try:
                            source_data=json.loads(source) if isinstance(source,str) else None
                            subagent=isinstance(source_data,dict) and 'subagent' in source_data
                        except ValueError:subagent=False
                        if subagent or agent and agent!='/root':continue
                        desktop='desktop' in (client or '').lower()
                        cli=source=='cli' or client in ('codex-tui','codex_cli_rs','codex-cli')
                        if (provider=='codex-desktop' and desktop) or (provider=='codex-cli' and cli and not desktop):
                            result.append({'id':identifier,'name':title or 'Untitled conversation','path':cwd})
                            if len(result)>=LIMIT:break
                break
            except sqlite3.Error:pass
    if provider=='claude':return claude_threads(home)
    if provider=='antigravity':
        try:
            data=json.loads((home/'.gemini/antigravity-cli/cache/conversation_metadata.json').read_text())
            for identifier,entry in sorted(data['conversations'].items(),key=lambda p:p[1].get('last_modified_time',''),reverse=True):
                s=entry.get('summary',{})
                if entry.get('is_internal') or s.get('Internal'):continue
                uris=s.get('WorkspaceURIs') or []
                cwd=urllib.parse.unquote(urllib.parse.urlparse(uris[0]).path) if uris else str(home)
                result.append({'id':identifier,'name':s.get('Title') or 'Untitled conversation','path':cwd,'project':s.get('ProjectID')})
        except (OSError,ValueError,KeyError):pass
    return result
if __name__=='__main__':print(json.dumps(threads(sys.argv[1])))
