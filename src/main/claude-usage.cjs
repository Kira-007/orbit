const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {normalizeClaudeUsage}=require('./usage.cjs');
function createClaudeUsage({credentialsPath=path.join(process.env.CLAUDE_CONFIG_DIR||path.join(os.homedir(),'.claude'),'.credentials.json'),readFile=(file)=>fs.promises.readFile(file,'utf8'),fetch=globalThis.fetch,now=Date.now}={}){
 let cached=null,inflight=null,retryAfter=0;
 return function claudeUsage(){
  if(cached&&now()-cached.time<60000)return Promise.resolve(cached);
  if(inflight)return inflight;
  if(now()<retryAfter)return Promise.reject(Error('Claude quota refresh is cooling down'));
  inflight=(async()=>{
   let auth;try{auth=JSON.parse(await readFile(credentialsPath)).claudeAiOauth;}catch{throw Error('Claude Code sign-in not found');}
   if(typeof auth?.accessToken!=='string'||!auth.accessToken)throw Error('Sign in to Claude Code to read quota');
   const response=await fetch('https://api.anthropic.com/api/oauth/usage',{headers:{Authorization:'Bearer '+auth.accessToken,'anthropic-beta':'oauth-2025-04-20','User-Agent':'Orbit/0.2.0'},signal:AbortSignal.timeout(12000)});
   if(response.status===429){const seconds=Number(response.headers.get('retry-after'));retryAfter=now()+Math.max(60000,Math.min(900000,Number.isFinite(seconds)&&seconds>0?seconds*1000:300000));throw Error('Claude quota refresh rate limited');}
   if(!response.ok)throw Error(response.status===401||response.status===403?'Claude Code sign-in needs refreshing':'Claude quota refresh failed');
   const body=await response.json(),usage=normalizeClaudeUsage(body,now());if(!usage)throw Error('Claude did not return quota data');
   cached=usage;return usage;
  })().finally(()=>inflight=null);
  return inflight;
 };
}
const claudeUsage=createClaudeUsage();
module.exports={createClaudeUsage,claudeUsage};
