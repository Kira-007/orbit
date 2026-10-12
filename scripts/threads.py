#!/usr/bin/env python3
"""Read conversation names and identifiers from local agent history."""
import json,os,pathlib,sqlite3,sys,urllib.parse

def threads(provider,home=None):
    home=pathlib.Path(home or pathlib.Path.home());result=[]
    if provider in ('codex-cli','codex-desktop'):
        root=pathlib.Path(os.environ.get('CODEX_HOME',str(home/'.codex')))
        for database in sorted(root.glob('state_*.sqlite'),reverse=True)[:1]:
            try:
                with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5) as c:
                    columns={r[1] for r in c.execute('pragma table_info(threads)')}
                    origin='originator' if 'originator' in columns else "''"
                    display="COALESCE(NULLIF(name,''),NULLIF(title,''),'Untitled conversation')" if 'name' in columns else 'title'
                    rows=c.execute(f'SELECT id,{display},cwd,source,{origin} FROM threads WHERE archived=0 ORDER BY updated_at DESC LIMIT 300')
                    for identifier,title,cwd,source,client in rows:
                        desktop='desktop' in (client or '').lower()
                        cli=source=='cli' or client in ('codex-tui','codex_cli_rs','codex-cli')
                        if (provider=='codex-desktop' and desktop) or (provider=='codex-cli' and cli and not desktop):
                            result.append({'id':identifier,'name':title or 'Untitled conversation','path':cwd})
            except sqlite3.Error:pass
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
