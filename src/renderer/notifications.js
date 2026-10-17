(function(root){
 'use strict';
 const PROVIDERS=new Set(['claude','codex-cli','codex-desktop','antigravity']);
 const ACTIVE=new Set(['working','waiting']),COMPLETE=new Set(['done','error']);
 const STATES=new Set([...ACTIVE,...COMPLETE,'idle','unknown']);
 const FRESH_MS=15*60*1000,RETENTION_MS=24*60*60*1000,MAX_VISIBLE=100,MAX_TRACKED=200;
 const isObject=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
 const stamp=value=>Number.isFinite(value)&&value>=0;
 const title=value=>typeof value==='string'?value.trim().replace(/\s+/g,' ').slice(0,160):'';
 function taskKey(session){return session&&PROVIDERS.has(session.provider)&&typeof session.session==='string'&&session.session.trim()?(session.provider.startsWith('codex-')?'codex':session.provider)+':'+session.session.trim().slice(0,180):'';}
 function taskIdentity(session){return stamp(session?.taskStartedAt)?'started:'+session.taskStartedAt:'title:'+title(session?.title);}
 function normalize(session){
  if(!isObject(session)||!taskKey(session)||!STATES.has(session.status)||!stamp(session.time))return null;
  const result={provider:session.provider,session:session.session.trim().slice(0,180),status:session.status,time:session.time,title:title(session.title)||'Agent session',workspace:typeof session.workspace==='string'?session.workspace.slice(0,300):'',activity:typeof session.activity==='string'?session.activity.slice(0,120):''};
  if(stamp(session.taskStartedAt)&&session.taskStartedAt<=session.time+1000)result.taskStartedAt=session.taskStartedAt;
  if(typeof session.source==='string')result.source=session.source.slice(0,80);
  return result;
 }
 function newRecord(session){return{session,run:stamp(session.taskStartedAt)?taskIdentity(session):taskIdentity(session)+':'+session.time,firstTime:session.time,completedAt:COMPLETE.has(session.status)?session.time:null,reason:null,closedAt:null};}
 function readRecord(value,dismissed){
  const session=normalize(value);if(!session)return null;
  const record=newRecord(session),meta=value._notification;
  if(!isObject(meta)||meta.version!==1)return dismissed?null:record;
  if(typeof meta.run==='string'&&meta.run.length<=512&&meta.run)record.run=meta.run;
  if(stamp(meta.firstTime)&&meta.firstTime<=session.time)record.firstTime=meta.firstTime;
  if(stamp(meta.completedAt)&&meta.completedAt<=session.time)record.completedAt=meta.completedAt;
  if(['dismissed','expired','inactive'].includes(meta.reason))record.reason=meta.reason;
  if(stamp(meta.closedAt))record.closedAt=meta.closedAt;
  return dismissed&&!record.reason?null:record;
 }
 function persisted(record){return{...record.session,_notification:{version:1,run:record.run,firstTime:record.firstTime,completedAt:record.completedAt,reason:record.reason,closedAt:record.closedAt}};}
 function differentRun(record,session){
  const before=record.session;
  if(stamp(session.taskStartedAt)){
   if(stamp(before.taskStartedAt))return session.taskStartedAt!==before.taskStartedAt;
   // A first start marker can upgrade an already observed legacy run.
   return session.taskStartedAt>record.firstTime;
  }
  if(stamp(before.taskStartedAt))return false;
  return session.time>before.time&&(session.title!==before.title||COMPLETE.has(before.status)&&ACTIVE.has(session.status));
 }
 class NotificationFeed{
  constructor({notifications,dismissed}={}){
   this.records=new Map();this.notifications=Object.create(null);this.dismissed=Object.create(null);this.now=Date.now();
   for(const [source,isDismissed] of [[notifications,false],[dismissed,true]]){
    if(!isObject(source))continue;
    // Bare-title legacy dismissals cannot distinguish a new run and are dropped.
    for(const value of Object.values(source).slice(-MAX_TRACKED)){
     const record=readRecord(value,isDismissed);if(!record)continue;
     const key=taskKey(record.session),previous=this.records.get(key);
     if(!previous||record.session.time>=previous.session.time)this.records.set(key,record);
    }
   }
   this.limit();this.serialize();
  }
  update(sessions,{now=Date.now(),completionMinutes=10}={}){
   this.now=stamp(now)?now:Date.now();
   const lifetime=(Number.isFinite(completionMinutes)?Math.max(0,Math.min(60,completionMinutes)):10)*60000;
   const incoming=new Map();
   for(const value of Array.isArray(sessions)?sessions:[]){
    const session=normalize(value);if(!session||session.time>this.now+60000)continue;
    const key=taskKey(session),old=incoming.get(key);
    if(!old||session.time>old.time||session.time===old.time&&session.provider==='codex-desktop')incoming.set(key,session);
   }
   for(const [key,session] of [...incoming].sort((a,b)=>b[1].time-a[1].time).slice(0,MAX_TRACKED)){
    let record=this.records.get(key);
    if(record&&session.time<record.session.time)continue;
    if(!record||differentRun(record,session))record=newRecord(session);
    else{
     if(!stamp(session.taskStartedAt)&&stamp(record.session.taskStartedAt))session.taskStartedAt=record.session.taskStartedAt;
     record.session=session;
     if(stamp(session.taskStartedAt))record.run=taskIdentity(session);
     if(COMPLETE.has(session.status)&&record.completedAt===null)record.completedAt=session.time;
    }
    this.records.set(key,record);
   }
   const visible=[];
   for(const [key,record] of this.records){
    const session=record.session;
    if(session.time>this.now+60000||this.now-Math.max(session.time,Math.min(record.closedAt||0,this.now))>RETENTION_MS){this.records.delete(key);continue;}
    if(ACTIVE.has(session.status)){
     if(this.now-session.time>=FRESH_MS){if(!record.reason){record.reason='inactive';record.closedAt=this.now;}}
     else if(record.reason==='inactive'){record.reason=null;record.closedAt=null;}
    }else if(COMPLETE.has(session.status)){
     if(this.now-(record.completedAt??session.time)>=lifetime&&!record.reason){record.reason='expired';record.closedAt=this.now;}
     else if(record.reason==='inactive'&&this.now-(record.completedAt??session.time)<lifetime){record.reason=null;record.closedAt=null;}
    }else if(!record.reason){record.reason='inactive';record.closedAt=this.now;}
    if(!record.reason)visible.push(session);
   }
   this.limit();this.serialize();
   return visible.sort((a,b)=>b.time-a.time||taskKey(a).localeCompare(taskKey(b))).filter(session=>this.records.has(taskKey(session))).slice(0,MAX_VISIBLE);
  }
  dismiss(session,{now=this.now}={}){
   const normalized=normalize(session);if(!normalized)return;
   const key=taskKey(normalized);let record=this.records.get(key);
   if(record&&normalized.time<record.session.time&&differentRun(record,normalized))return;
   if(!record||differentRun(record,normalized))record=newRecord(normalized);
   record.reason='dismissed';record.closedAt=stamp(now)?now:Date.now();this.records.set(key,record);this.limit();this.serialize();
  }
  limit(){
   if(this.records.size<=MAX_TRACKED)return;
   const keep=[...this.records].sort((a,b)=>b[1].session.time-a[1].session.time).slice(0,MAX_TRACKED);
   this.records=new Map(keep);
  }
  serialize(){
   this.notifications=Object.create(null);this.dismissed=Object.create(null);
   const records=[...this.records].sort((a,b)=>b[1].session.time-a[1].session.time);let count=0;
   for(const [key,record] of records){if(record.reason)this.dismissed[key]=persisted(record);else if(count++<MAX_VISIBLE)this.notifications[key]=persisted(record);}
  }
 }
 const api={NotificationFeed,taskKey,taskIdentity};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.OrbitNotifications=api;
})(typeof globalThis!=='undefined'?globalThis:this);
