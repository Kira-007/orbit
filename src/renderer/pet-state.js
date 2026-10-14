// Historical task cards must not hold the pet in a stale/error pose indefinitely.
function petState(sessions,now=Date.now()){
 if(sessions.some(s=>s.status==='waiting'))return 'waiting';
 if(sessions.some(s=>s.status==='working'))return 'working';
 const recent=sessions.filter(s=>Number.isFinite(s.time)&&now-s.time>=0&&now-s.time<30000);
 if(recent.some(s=>s.status==='error'))return 'error';
 if(recent.some(s=>s.status==='done'))return 'done';
 if(recent.some(s=>s.status==='unknown'))return 'unknown';
 return 'idle';
}
if(typeof module!=='undefined')module.exports={petState};
