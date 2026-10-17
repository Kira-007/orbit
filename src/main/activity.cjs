const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {execFile}=require('node:child_process');
const {normalizeUsage,normalizeAgyUsage}=require('./usage.cjs');
const {codexEvent}=require('./store.cjs');
const ROOT=path.join(process.env.CODEX_HOME||path.join(os.homedir(),'.codex'),'sessions');
function filesUnder(dir,out=[]){try{for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())filesUnder(p,out);else if(e.name.endsWith('.jsonl'))out.push(p);}}catch{}return out;}
class Activity {
 constructor(store,stateDir,root=ROOT){this.stateDir=stateDir;this.root=root;this.store=store;this.dir=path.join(stateDir,'events');this.tails=new Map();this.eventTimes=new Map();this.lastScan=0;this.files=[];fs.mkdirSync(this.dir,{recursive:true,mode:0o700});}
 poll(){
  const now=Date.now();
  try{const file=path.join(this.stateDir,'agy-usage.json');if(fs.statSync(file).size<32768){const usage=normalizeAgyUsage(JSON.parse(fs.readFileSync(file,'utf8')));if(usage&&usage.time>(this.store.usage.antigravity?.time||0))this.store.usage.antigravity=usage;}}catch{}
  if(now-this.lastScan>10000){this.lastScan=now;this.files=filesUnder(this.root).map(file=>{try{return{file,time:fs.statSync(file).mtimeMs};}catch{return null;}}).filter(e=>e&&now-e.time<86400000).sort((a,b)=>b.time-a.time).slice(0,40).map(e=>e.file);this.processes();}
  for(const file of this.files)this.tail(file);
  try{for(const name of fs.readdirSync(this.dir)){if(!name.endsWith('.json'))continue;const file=path.join(this.dir,name);try{const stat=fs.statSync(file);if(this.eventTimes.get(file)===stat.mtimeMs)continue;this.eventTimes.set(file,stat.mtimeMs);if(stat.size<16384)this.store.update(JSON.parse(fs.readFileSync(file,'utf8')));}catch{}}}catch{}
 }
 tail(file){try{
  const stat=fs.statSync(file);let t=this.tails.get(file);
  if(!t||stat.size<t.offset){t={offset:0,pending:'',meta:null};this.tails.set(file,t);const fd=fs.openSync(file,'r');try{const b=Buffer.alloc(Math.min(32768,stat.size));fs.readSync(fd,b,0,b.length,0);for(const l of b.toString().split('\n')){try{const r=JSON.parse(l);if(r.type==='session_meta')t.meta=r.payload;}catch{}}}finally{fs.closeSync(fd);}if(stat.size>262144)t.offset=stat.size-262144;}
  if(stat.size===t.offset)return;
  const fd=fs.openSync(file,'r');try{const b=Buffer.alloc(Math.min(stat.size-t.offset,1024*1024));fs.readSync(fd,b,0,b.length,t.offset);const skip=t.offset>0&&!t.pending&&t.offset===stat.size-262144;t.offset+=b.length;const lines=(t.pending+b.toString()).split('\n');t.pending=lines.pop();if(skip)lines.shift();for(const line of lines){try{const record=JSON.parse(line);if(record.type==='session_meta')t.meta=record.payload;if(record.payload?.rate_limits){const usage=normalizeUsage(record.payload.rate_limits,Date.parse(record.timestamp)||stat.mtimeMs);if(usage&&usage.time>(this.store.usage.codex?.time||0))this.store.usage.codex=usage;}const e=codexEvent(record,t.meta,stat.mtimeMs);if(e)this.store.update(e);}catch{}}}finally{fs.closeSync(fd);}
 }catch{}}
 processes(){execFile('ps',['-eo','comm='],{timeout:2000},(err,text)=>{if(err)return;const names=new Set(text.trim().split(/\s+/).map(x=>x.toLowerCase()));this.store.online={'claude':names.has('claude'),'codex-cli':names.has('codex'),'codex-desktop':names.has('chatgpt')||names.has('codex-desktop'),'antigravity':names.has('antigravity')||names.has('agy')};});}
}
module.exports={Activity};
