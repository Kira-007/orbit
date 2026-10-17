const {test}=require('node:test'),assert=require('node:assert/strict');
const {NotificationFeed,taskKey,taskIdentity}=require('../src/renderer/notifications.js');
const minute=60000,now=100*minute;
const task=(overrides={})=>({provider:'codex-cli',session:'thread-1',title:'Fix tests',status:'working',time:now,taskStartedAt:now-1000,workspace:'/tmp/project',activity:'Thinking',...overrides});
const roundTrip=feed=>new NotificationFeed(JSON.parse(JSON.stringify({notifications:feed.notifications,dismissed:feed.dismissed})));

test('active tasks expire at fifteen minutes; idle and stale snapshots remove old cards',()=>{
 const feed=new NotificationFeed();assert.equal(feed.update([task()],{now}).length,1);
 assert.equal(feed.update([],{now:now+15*minute-1}).length,1);
 assert.equal(feed.update([],{now:now+15*minute}).length,0);
 assert.equal(feed.update([task({time:now+16*minute})],{now:now+16*minute}).length,1);
 assert.equal(feed.update([task({status:'unknown',time:now+17*minute})],{now:now+17*minute}).length,0);
 assert.equal(feed.update([task({status:'idle',time:now+18*minute})],{now:now+18*minute}).length,0);
});

test('done and error expire at completion lifetime without progress extending it',()=>{
 for(const status of ['done','error']){
  const feed=new NotificationFeed();assert.equal(feed.update([task({status})],{now}).length,1);
  assert.equal(feed.update([task({status,time:now+5*minute})],{now:now+5*minute}).length,1);
  assert.equal(feed.update([task({status,time:now+10*minute})],{now:now+10*minute}).length,0);
  assert.equal(roundTrip(feed).update([task({status,time:now+11*minute})],{now:now+11*minute}).length,0);
 }
 const feed=new NotificationFeed();assert.equal(feed.update([task({status:'done'})],{now,completionMinutes:1}).length,1);
 assert.equal(feed.update([],{now:now+minute,completionMinutes:1}).length,0);
});

test('dismissals apply to one marked run and survive progress, completion, and reload',()=>{
 let feed=new NotificationFeed();const session=task();feed.update([session],{now});feed.dismiss(session);
 feed=roundTrip(feed);
 assert.equal(feed.update([task({time:now+1000})],{now:now+1000}).length,0);
 assert.equal(feed.update([task({status:'done',time:now+2000})],{now:now+2000}).length,0);
 assert.equal(feed.update([task({taskStartedAt:now+3000,time:now+3000})],{now:now+3000}).length,1);
 assert.notEqual(taskIdentity(session),taskIdentity(task({taskStartedAt:now+3000})));
});

test('legacy same-title completed runs can start again without progress resurrecting dismissals',()=>{
 const feed=new NotificationFeed(),first=task({taskStartedAt:undefined});feed.update([first],{now});feed.dismiss(first);
 assert.equal(feed.update([task({taskStartedAt:undefined,time:now+1})],{now:now+1}).length,0);
 assert.equal(feed.update([task({taskStartedAt:undefined,status:'done',time:now+2})],{now:now+2}).length,0);
 assert.equal(roundTrip(feed).update([task({taskStartedAt:undefined,time:now+3})],{now:now+3}).length,1);
});

test('a marker upgrade keeps a legacy dismissal while a later marker starts a new run',()=>{
 const feed=new NotificationFeed(),session=task({taskStartedAt:undefined});feed.update([session],{now});feed.dismiss(session);
 assert.equal(feed.update([task({taskStartedAt:now-1000,time:now+1000})],{now:now+1000}).length,0);
 assert.equal(feed.update([task({taskStartedAt:now+2000,time:now+2000})],{now:now+2000}).length,1);
});

test('shared Codex sessions deduplicate providers and ignore older snapshots',()=>{
 const feed=new NotificationFeed(),desktop=task({provider:'codex-desktop',time:now+100});
 assert.equal(taskKey(desktop),taskKey(task()));
 assert.deepEqual(feed.update([task(),desktop],{now:now+100}).map(s=>s.provider),['codex-desktop']);
 assert.equal(feed.update([task({status:'done'})],{now:now+200})[0].status,'working');
 feed.dismiss(desktop);assert.equal(feed.update([task({time:now+300})],{now:now+300}).length,0);
 assert.equal(taskKey(task({provider:'claude'})),'claude:thread-1');
});

test('malformed persisted state and legacy title-only dismissals migrate without permanent hidden tasks',()=>{
 for(const bad of [null,[],0,'bad',{'codex:x':null},{'codex:x':{provider:'codex-cli',session:'x',status:'working',time:'wrong'}}]){
  const feed=new NotificationFeed({notifications:bad,dismissed:bad});assert.equal(feed.update([null,task()],{now}).length,1);
 }
 const legacy=task({taskStartedAt:undefined,status:'done',time:now-20*minute});
 const feed=new NotificationFeed({notifications:{old:legacy},dismissed:{'codex:thread-1':'Fix tests'}});
 assert.equal(feed.update([],{now}).length,0);
 assert.equal(feed.update([task()],{now}).length,1);
 const untrusted=task({session:'bad',time:now+minute+1});assert.equal(feed.update([untrusted],{now}).some(s=>s.session==='bad'),false);
 const future=new NotificationFeed({notifications:{old:untrusted}});assert.equal(future.update([],{now}).length,0);
});

test('storage is bounded and stale task history is pruned',()=>{
 const feed=new NotificationFeed(),sessions=Array.from({length:500},(_,i)=>task({session:String(i),title:'x'.repeat(5000),activity:'y'.repeat(5000),workspace:'z'.repeat(5000),time:now-i}));
 assert.equal(feed.update(sessions,{now}).length,100);
 for(const session of sessions)feed.dismiss(session,{now});
 assert.ok(Object.keys(feed.notifications).length<=100);assert.ok(Object.keys(feed.dismissed).length<=200);
 for(const session of Object.values(feed.dismissed)){assert.equal(session.title.length,160);assert.equal(session.activity.length,120);assert.equal(session.workspace.length,300);}
 assert.equal(feed.update([],{now:now+25*60*minute}).length,0);
 assert.equal(Object.keys(feed.dismissed).length,0);
});
