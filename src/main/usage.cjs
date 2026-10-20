function normalizeUsage(limits,time){
 if(!limits||!Number.isFinite(time))return null;
 const windows=[];for(const [key,label] of [['primary','Session'],['secondary','Weekly']]){const window=limits[key];if(!window||!Number.isFinite(window.used_percent))continue;windows.push({label,remaining:Math.round(Math.max(0,Math.min(100,100-window.used_percent))),reset:Number.isFinite(window.resets_at)?window.resets_at*1000:null,minutes:window.window_minutes||null});}
 return windows.length?{time,windows}:null;
}
function normalizeAgyUsage(payload){
 if(!payload||!Number.isFinite(payload.time)||!payload.quota||typeof payload.quota!=='object')return null;
 const windows=[];for(const [label,value] of Object.entries(payload.quota).slice(0,64)){
  if(!value||!Number.isFinite(value.remaining_fraction)||value.remaining_fraction<0||value.remaining_fraction>1)continue;
  const date=typeof value.reset_time==='string'?Date.parse(value.reset_time):NaN;
  const reset=Number.isFinite(date)?date:Number.isFinite(value.reset_in_seconds)?payload.time+value.reset_in_seconds*1000:null;
  windows.push({label:label.slice(0,120),remaining:Math.round(value.remaining_fraction*100),reset});
 }
 return windows.length?{time:payload.time,windows}:null;
}
function normalizeClaudeUsage(payload,time=Date.now()){
 if(!payload||!Number.isFinite(time))return null;
 const windows=[];
 for(const [key,label] of [['five_hour','Session'],['seven_day','Weekly'],['seven_day_sonnet','Sonnet · Week'],['seven_day_opus','Opus · Week']]){
  const bucket=payload[key];if(!bucket||!Number.isFinite(bucket.utilization))continue;
  const reset=typeof bucket.resets_at==='string'?Date.parse(bucket.resets_at):NaN;
  windows.push({label,remaining:Math.round(Math.max(0,Math.min(100,100-bucket.utilization))),reset:Number.isFinite(reset)?reset:null});
 }
 return windows.length?{time,windows}:null;
}
module.exports={normalizeUsage,normalizeAgyUsage,normalizeClaudeUsage};
