"""Conversation discovery uses local fixtures without invoking an agent."""
import contextlib,importlib.util,json,os,pathlib,sqlite3,tempfile,unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('orbit_threads',ROOT/'scripts/threads.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ThreadsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='orbit-threads-')
        self.home=pathlib.Path(self.temp.name)
        self.env=patch.dict(os.environ,{'CODEX_HOME':str(self.home/'.codex'),'CLAUDE_CONFIG_DIR':str(self.home/'.claude')})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.temp.cleanup()
    def log(self,identifier,records):
        file=self.home/'.claude/projects/-work-project'/f'{identifier}.jsonl'
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(''.join(json.dumps(r)+'\n' for r in records))
        return file
    def database(self,version,rows):
        file=self.home/'.codex'/f'state_{version}.sqlite'
        file.parent.mkdir(parents=True,exist_ok=True)
        with contextlib.closing(sqlite3.connect(file)) as connection:
            connection.execute('CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, source TEXT, originator TEXT, archived INTEGER, updated_at INTEGER, agent_path TEXT)')
            connection.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?)',rows)
            connection.commit()
        return file
    def test_claude_index_uses_session_titles_and_project_paths(self):
        index=self.home/'.claude/projects/-work-project/sessions-index.json'
        index.parent.mkdir(parents=True)
        index.write_text(json.dumps({'entries':[
            {'sessionId':'older','summary':'Fix login','firstPrompt':'initial request','projectPath':'/work/project','modified':'2026-10-15T10:00:00Z'},
            {'sessionId':'newer','customTitle':'Release checklist','summary':'generated summary','projectPath':'/work/release','modified':'2026-10-18T10:00:00Z'},
            {'sessionId':'child','summary':'Do not list','isSidechain':True}
        ]}))
        result=module.threads('claude',self.home)
        self.assertEqual([r['id'] for r in result],['newer','older'])
        self.assertEqual(result[0],{'id':'newer','name':'Release checklist','path':'/work/release'})
        self.assertEqual(result[1]['name'],'Fix login')
    def test_claude_logs_use_first_real_user_message_and_latest_rename(self):
        self.log('one',[
            {'type':'user','sessionId':'one','cwd':'/work/project','isMeta':True,'message':{'content':'Ignore metadata'}},
            {'type':'user','sessionId':'one','message':{'content':[{'type':'text','text':'<environment_context>private</environment_context>'}]}},
            {'type':'user','sessionId':'one','message':{'content':[{'type':'tool_result','content':'Tool output'},{'type':'text','text':'  Fix\n the login  '}]}},
            {'type':'user','sessionId':'one','message':{'content':'Later followup'}},
        ])
        self.assertEqual(module.threads('claude',self.home),[{'id':'one','name':'Fix the login','path':'/work/project'}])
        with (self.home/'.claude/projects/-work-project/one.jsonl').open('a') as stream:
            stream.write(json.dumps({'type':'custom-title','sessionId':'one','customTitle':'Login repair'})+'\n')
        self.assertEqual(module.threads('claude',self.home)[0]['name'],'Login repair')
    def test_claude_reads_tail_metadata_and_omits_sidechains(self):
        file=self.log('large',[{'type':'user','sessionId':'large','cwd':'/work/project','message':{'content':'Initial task'}}])
        with file.open('a') as stream:
            for _ in range(2000):stream.write(json.dumps({'type':'assistant','message':{'content':'x'*80}})+'\n')
            stream.write(json.dumps({'type':'custom-title','sessionId':'large','customTitle':'Renamed task'})+'\n')
            stream.write('{partial')
        self.log('child',[{'type':'user','sessionId':'child','isSidechain':True,'message':{'content':'Child task'}}])
        result=module.threads('claude',self.home)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['name'],'Renamed task')
    def test_codex_uses_numeric_database_versions_and_skips_subagents(self):
        self.database(9,[('old','','Old database','/work','cli','codex-tui',0,1,None)])
        self.database(10,[
            ('main','Named task','Prompt fallback','/work','vscode','codex-tui',0,2,None),
            ('desktop','','Desktop task','/work','vscode','Codex Desktop',0,3,None),
            ('child','','Child task','/work',json.dumps({'subagent':{'thread_spawn':{}}}),'codex-tui',0,4,None),
            ('child2','','Child task 2','/work','vscode','Codex Desktop',0,5,'/root/child'),
        ])
        self.assertEqual(module.threads('codex-cli',self.home),[{'id':'main','name':'Named task','path':'/work'}])
        self.assertEqual(module.threads('codex-desktop',self.home),[{'id':'desktop','name':'Desktop task','path':'/work'}])
    def test_codex_falls_back_when_new_database_is_incomplete(self):
        self.database(5,[('main','','Main task','/work','cli','codex-tui',0,1,None)])
        with contextlib.closing(sqlite3.connect(self.home/'.codex/state_6.sqlite')) as connection:
            connection.execute('CREATE TABLE other (id TEXT)')
        self.assertEqual(module.threads('codex-cli',self.home)[0]['id'],'main')
    def test_codex_supports_older_schema_without_optional_columns(self):
        folder=self.home/'.codex';folder.mkdir()
        with contextlib.closing(sqlite3.connect(folder/'state_1.sqlite')) as connection:
            connection.execute('CREATE TABLE threads (id TEXT, title TEXT, cwd TEXT, source TEXT)')
            connection.execute("INSERT INTO threads VALUES ('old','Legacy thread','/work','cli')")
            connection.commit()
        self.assertEqual(module.threads('codex-cli',self.home),[{'id':'old','name':'Legacy thread','path':'/work'}])
    def test_missing_or_malformed_history_is_nonfatal(self):
        self.assertEqual(module.threads('claude',self.home),[])
        file=self.home/'.claude/projects/-work/sessions-index.json';file.parent.mkdir(parents=True);file.write_text('{broken')
        self.log('partial',[{'type':'system','cwd':'/work'}])
        self.assertEqual(module.threads('claude',self.home),[{'id':'partial','name':'Untitled conversation','path':'/work'}])

if __name__=='__main__':unittest.main()
