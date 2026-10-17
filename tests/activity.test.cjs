const test=require('node:test'),assert=require('node:assert/strict');const {Store,codexEvent}=require('../src/main/store.cjs');
test('parallel providers and out-of-order events do not overwrite newer session state',()=>{const s=new Store(),time=Date.now();s.update({provider:'claude',session:'a',status:'working',time});s.update({provider:'codex-cli',session:'b',status:'working',time});s.update({provider:'claude',session:'a',status:'done',time:time+10});assert.equal(s.update({provider:'claude',session:'a',status:'working',time:time-10}),false);const snap=s.snapshot(time+20);assert.equal(snap.counts.claude,0);assert.equal(snap.counts['codex-cli'],1);assert.equal(snap.sessions.length,2);});
test('stale working sessions stop claiming the agent is busy',()=>{const s=new Store();s.update({provider:'antigravity',session:'x',status:'working',time:1000});assert.equal(s.snapshot(1000000).sessions[0].status,'unknown');assert.equal(s.snapshot(1000000).counts.antigravity,0);});
test('Codex desktop vs terminal classification uses originator, not shared source vscode',()=>{const record={type:'event_msg',payload:{type:'task_started'},timestamp:'2026-10-06T01:00:00Z'};assert.equal(codexEvent(record,{source:'vscode',originator:'Codex Desktop',id:'d'},1).provider,'codex-desktop');assert.equal(codexEvent(record,{source:'vscode',originator:'codex-tui',id:'c'},1).provider,'codex-cli');assert.equal(codexEvent({...record,payload:{type:'task_complete'}},{id:'c'},1).status,'done');assert.equal(codexEvent({...record,type:'response_item',payload:{type:'message',content:'private'}},{id:'c'},1),null);});
test('invalid or untrusted event values are rejected',()=>{const s=new Store();assert.equal(s.update({provider:'unknown',session:'x',status:'working',time:1}),false);assert.equal(s.update({provider:'claude',session:'x',status:'running',time:1}),false);});
test('incremental Codex reader handles a partially written JSON line and later completion',()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');const {Activity}=require('../src/main/activity.cjs');const temp=fs.mkdtempSync(path.join(os.tmpdir(),'orbit-test-'));try{const logs=path.join(temp,'logs');fs.mkdirSync(logs);const file=path.join(logs,'session.jsonl');const now=new Date().toISOString();fs.writeFileSync(file,JSON.stringify({type:'session_meta',payload:{id:'partial',originator:'Codex Desktop',cwd:'/project'}})+'\n'+JSON.stringify({type:'event_msg',timestamp:now,payload:{type:'task_started'}})+'\n');const store=new Store(),activity=new Activity(store,path.join(temp,'state'),logs);activity.processes=()=>{};activity.poll();assert.equal(store.snapshot().sessions[0].status,'working');const done=JSON.stringify({type:'event_msg',timestamp:now,payload:{type:'task_complete'}});fs.appendFileSync(file,done.slice(0,20));activity.poll();assert.equal(store.snapshot().sessions[0].status,'working');fs.appendFileSync(file,done.slice(20)+'\n');activity.poll();assert.equal(store.snapshot().sessions[0].status,'done');assert.equal(store.snapshot().sessions.length,1);}finally{fs.rmSync(temp,{recursive:true,force:true});}
});
test('passive hook writes only normalized metadata and returns neutral output',()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');const temp=fs.mkdtempSync(path.join(os.tmpdir(),'orbit-hook-'));try{const result=spawnSync('python3',[path.join(__dirname,'../scripts/emit.py'),'antigravity','working'],{input:JSON.stringify({conversationId:'conversation',workspacePaths:['/project'],prompt:'must not persist'}),encoding:'utf8',env:{...process.env,XDG_STATE_HOME:temp}});assert.equal(result.status,0);assert.deepEqual(JSON.parse(result.stdout),{});const dir=path.join(temp,'agent-pet/events');const event=JSON.parse(fs.readFileSync(path.join(dir,fs.readdirSync(dir)[0]),'utf8'));assert.equal(event.session,'conversation');assert.equal(event.workspace,'/project');assert.equal(event.status,'working');assert.equal(event.title,'must not persist');assert.equal(event.prompt,undefined);}finally{fs.rmSync(temp,{recursive:true,force:true});}
});

test('task names survive progress and completion events',()=>{const s=new Store();s.update({provider:'claude',session:'task',status:'working',title:'Fix login',time:1});s.update({provider:'claude',session:'task',status:'working',activity:'Using Bash',time:2});assert.equal(s.snapshot(3).sessions[0].title,'Fix login');assert.equal(s.snapshot(3).sessions[0].activity,'Using Bash');s.update({provider:'claude',session:'task',status:'done',time:4});assert.equal(s.snapshot(5).sessions[0].title,'Fix login');});
test('Codex user messages supply task labels and tool calls supply activity',()=>{const meta={id:'task',originator:'codex-tui'};const task=codexEvent({type:'response_item',payload:{type:'message',role:'user',content:[{type:'input_text',text:'Build a task panel'}]}},meta,1);assert.equal(task.title,'Build a task panel');const tool=codexEvent({type:'response_item',payload:{type:'function_call',name:'exec_command'}},meta,2);assert.equal(tool.activity,'Using exec command');});

test('current Codex item events refresh progress and recognize final answers',()=>{
 const meta={id:'new-format',originator:'codex-tui'},store=new Store();
 const event=(item,time)=>codexEvent({type:'event_msg',timestamp:new Date(time).toISOString(),payload:{type:'item_completed',item}},meta,time);
 store.update(event({type:'UserMessage',content:[{type:'text',text:'Fix the pet'}]},1000));
 store.update(event({type:'Reasoning'},901000));
 assert.equal(store.snapshot(902000).sessions[0].status,'working');
 assert.equal(store.snapshot(902000).sessions[0].title,'Fix the pet');
 store.update(event({type:'AgentMessage',phase:'final_answer',content:[{type:'text',text:'Fixed'}]},903000));
 assert.equal(store.snapshot(904000).sessions[0].status,'done');
 assert.equal(store.snapshot(904000).sessions[0].activity,'Fixed');
});

test('task start markers survive progress and distinguish repeated same-title turns',()=>{
 const store=new Store(),meta={id:'repeat',originator:'codex-tui'};
 const event=(type,time)=>codexEvent({type:'event_msg',timestamp:new Date(time).toISOString(),payload:{type}},meta,time);
 store.update(event('task_started',1000));store.update(event('agent_message',2000));
 assert.equal(store.snapshot(3000).sessions[0].taskStartedAt,1000);
 store.update(event('task_complete',4000));store.update(event('task_started',5000));
 assert.equal(store.snapshot(6000).sessions[0].taskStartedAt,5000);
 const tailOnly=new Store();tailOnly.update(event('agent_message',7000));
 assert.equal(tailOnly.snapshot(8000).sessions[0].taskStartedAt,undefined,'partial log tails must not fabricate a different run on restart');
});
test('internal worker sessions do not create resumable task notifications',()=>{
 const record={type:'event_msg',payload:{type:'task_started'}};
 assert.equal(codexEvent(record,{id:'worker',source:{subagent:{}}},1),null);
 assert.equal(codexEvent(record,{id:'worker',agent_path:'/root/child'},1),null);
 assert.equal(codexEvent(record,{id:'parent',agent_path:'/root'},1).session,'parent');
});
