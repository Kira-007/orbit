'use strict';

// Coordinates are pet top-left positions in the same space as getPosition().
// A cancelled run reports onEnd({cancelled:true}); a replacement starts there.
function createPetRunner({getPosition,move,onStart=()=>{},onEnd=()=>{},now=()=>performance.now(),schedule=setTimeout,cancel=clearTimeout,speed=700,getSpeed=()=>speed}){
 if(typeof getPosition!=='function'||typeof move!=='function')throw new TypeError('Pet movement callbacks are required');
 if(!Number.isFinite(speed)||speed<=0)throw new TypeError('Pet speed must be positive');
 let active=null;
 const finish=(run,cancelled)=>{
  if(active!==run)return;
  active=null;
  if(run.timer!==null)cancel(run.timer);
  onEnd({cancelled});
 };
 const stop=()=>{
  if(!active)return false;
  finish(active,true);
  return true;
 };
 const frame=run=>{
  if(active!==run)return;
  run.timer=null;
  const elapsed=Math.max(0,now()-run.started),progress=Math.min(1,elapsed/run.duration);
  // Smoothstep eases into and out of travel without depending on frame rate.
  const eased=progress*progress*(3-2*progress);
  move(progress===1?run.target.x:run.start.x+run.dx*eased,
   progress===1?run.target.y:run.start.y+run.dy*eased,
   {direction:run.direction,walking:true});
  if(active!==run)return;
  if(progress===1)finish(run,false);
  else run.timer=schedule(()=>frame(run),Math.min(16,run.duration-elapsed));
 };
 const run=target=>{
  const destination={x:target?.x,y:target?.y};
  if(!Number.isFinite(destination.x)||!Number.isFinite(destination.y))throw new TypeError('Invalid pet destination');
  const movementSpeed=getSpeed();
  if(!Number.isFinite(movementSpeed)||movementSpeed<=0)throw new TypeError('Pet speed must be positive');
  stop();
  const position=getPosition(),start={x:position?.x,y:position?.y};
  if(!Number.isFinite(start.x)||!Number.isFinite(start.y))throw new TypeError('Invalid pet position');
  const dx=destination.x-start.x,dy=destination.y-start.y,distance=Math.hypot(dx,dy);
  if(distance<1)return false;
  // Near-vertical travel leaves the sprite's current facing unchanged.
  const direction=Math.abs(dx)<=Math.max(1,Math.abs(dy)*.1)?0:Math.sign(dx);
  const current={start,target:destination,dx,dy,direction,started:now(),duration:Math.max(180,Math.min(15000,distance/movementSpeed*1000)),timer:null};
  active=current;
  onStart({direction});
  if(active===current)current.timer=schedule(()=>frame(current),Math.min(16,current.duration));
  return true;
 };
 return{run,stop,get running(){return active!==null;}};
}

module.exports={createPetRunner};
