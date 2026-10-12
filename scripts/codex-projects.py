#!/usr/bin/env python3
"""Read CLI project folders without changing Codex configuration or history."""
import json, os, pathlib, sqlite3, tomllib

def projects(root):
    result=[]; names={}
    try:
        config=tomllib.loads((root/'config.toml').read_text())
        result.extend(config.get('projects',{}).keys())
        for folder,settings in config.get('projects',{}).items():
            if isinstance(settings,dict) and settings.get('name'):names[folder]=settings['name']
    except (OSError,ValueError):pass
    for database in sorted(root.glob('state_*.sqlite'),reverse=True)[:1]:
        try:
            with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=.5) as connection:
                try:
                    names.update({folder:name for name,folder in connection.execute('SELECT projects.name, project_roots.path FROM projects JOIN project_roots ON project_roots.project_id=projects.id') if name})
                except sqlite3.Error:pass
                columns={row[1] for row in connection.execute('pragma table_info(threads)')}
                if not {'cwd','source'}.issubset(columns):continue
                where="source='cli'"
                if 'originator' in columns:where+=" OR originator IN ('codex-tui','codex_cli_rs','codex-cli')"
                result.extend(row[0] for row in connection.execute('SELECT DISTINCT cwd FROM threads WHERE '+where))
        except sqlite3.Error:pass
    return [{'path':p,'name':names.get(p) or 'Unnamed project'} for p in dict.fromkeys(result) if isinstance(p,str) and pathlib.Path(p).is_absolute() and pathlib.Path(p).is_dir()]

if __name__=='__main__':
    root=pathlib.Path(os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex'))).resolve()
    print(json.dumps(projects(root)))
