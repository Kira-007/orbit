const path = require('node:path');
const PROVIDERS = ['claude','codex-cli','codex-desktop','antigravity'];
const STATES = ['working','waiting','done','error','idle','unknown'];
class Store {
  constructor(){this.sessions=new Map();this.online={};this.usage={};}
  update(e){
    if(!e||typeof e!=='object'||!PROVIDERS.includes(e.provider)||!STATES.includes(e.status)||typeof e.session!=='string'||!Number.isFinite(e.time))return false;
    const key=e.provider+':'+e.session,old=this.sessions.get(key);
    if(old&&old.time>e.time)return false;
    this.sessions.set(key,{provider:e.provider,session:e.session.slice(0,180),status:e.status,time:e.time,workspace:String(e.workspace||old?.workspace||'').slice(0,300),title:String(e.title||old?.title||path.basename(e.workspace||'')||'Agent session').slice(0,160),activity:String(e.activity||(['working','waiting'].includes(e.status)?old?.activity||'Working on task':'Task '+e.status)).slice(0,120),source:e.source||'hook'});return true;
  }
  snapshot(now=Date.now()){
    const sessions=[...this.sessions.values()].filter(e=>now-e.time<86400000).map(e=>({...e,status:['working','waiting'].includes(e.status)&&now-e.time>900000?'unknown':e.status})).sort((a,b)=>{const rank={waiting:0,error:1,working:2,unknown:3,done:4,idle:5};return rank[a.status]-rank[b.status]||b.time-a.time;}).slice(0,30);
    return {sessions,online:this.online,usage:this.usage,usageStatus:this.usageStatus||{},counts:Object.fromEntries(PROVIDERS.map(p=>[p,sessions.filter(s=>s.provider===p&&s.status==='working').length])),time:now};
  }
}
function codexEvent(record,meta,fileTime){
  if(!meta)return null;
  const payload=record.payload||{};
  const statuses={task_started:'working',turn_started:'working',task_complete:'done',turn_complete:'done',turn_aborted:'idle',permission_request:'waiting',user_message:'working',agent_message:'working'};
  let status=record.type==='event_msg'?statuses[payload.type]:null,title,activity;
  if(record.type==='event_msg'&&payload.type==='user_message')title=payload.message;
  if(record.type==='response_item'&&payload.type==='message'&&payload.role==='user'){
    const text=(Array.isArray(payload.content)?payload.content:[]).filter(c=>c.type==='input_text'||c.type==='text').map(c=>c.text||'').join(' ').replace(/<environment_context>[\s\S]*?<\/environment_context>/g,'').trim();
    if(text&&!text.startsWith('<')){title=text;status='working';}
  }
  if(record.type==='response_item'&&['function_call','custom_tool_call'].includes(payload.type)){status='working';activity='Using '+String(payload.name||'tool').replace(/^.*__/,'').replace(/_/g,' ');}
  if(record.type==='event_msg'&&payload.type==='agent_message')activity=String(payload.message||'Working on task').replace(/\s+/g,' ').slice(0,120);
  if(record.type==='event_msg'&&payload.type==='task_complete'&&payload.last_agent_message)activity=String(payload.last_agent_message).replace(/\s+/g,' ').slice(0,120);
  if(record.type==='event_msg'&&payload.type==='item_completed'){
    const item=payload.item||{};
    const text=(Array.isArray(item.content)?item.content:[]).filter(c=>typeof c.text==='string').map(c=>c.text).join(' ').replace(/<environment_context>[\s\S]*?<\/environment_context>/g,'').trim();
    if(item.type==='UserMessage'&&text&&!text.startsWith('<')){title=text;status='working';}
    else if(item.type==='AgentMessage'){status=item.phase==='final_answer'?'done':'working';activity=text||undefined;}
    else if(['Reasoning','CommandExecution','McpToolCall','DynamicToolCall','FileChange','WebSearch','ImageGeneration'].includes(item.type)){status='working';activity=item.type==='Reasoning'?'Thinking':'Using '+item.type.replace(/([a-z])([A-Z])/g,'$1 $2').toLowerCase();}
  }
  if(!status)return null;
  if(title)title=String(title).replace(/\s+/g,' ').trim().slice(0,160);
  const time=Date.parse(record.timestamp)||fileTime;
  return {provider:/desktop/i.test(meta.originator||'')?'codex-desktop':'codex-cli',session:String(meta.id||meta.session_id||'unknown'),workspace:meta.cwd||'',status,time,title,activity,source:'local log'};
}
module.exports={Store,PROVIDERS,codexEvent};
