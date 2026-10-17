'use strict';
function createPetFollower({getPosition,getTarget,move,onMotion=()=>{},onStop=()=>{},getSpeed=()=>350,getRadius=()=>24,now=()=>performance.now(),schedule=setTimeout,cancel=clearTimeout}){
 let active=null;
 const motion=(run,walking,direction=0)=>{if(run.walking===walking&&(!walking||run.direction===direction))return;run.walking=walking;run.direction=direction;onMotion({walking,direction});};
 const stop=()=>{if(!active)return false;const run=active;active=null;if(run.timer!==null)cancel(run.timer);motion(run,false);onStop();return true;};
 const frame=async run=>{
  if(active!==run)return;run.timer=null;
  try{
   const target=await getTarget();if(active!==run)return;
   const time=now(),dt=Math.max(0,Math.min(.064,(time-run.time)/1000));run.time=time;
   const position=getPosition(),dx=target.x-position.x,dy=target.y-position.y,distance=Math.hypot(dx,dy),radius=Math.max(0,getRadius());
   if(![distance,getSpeed()].every(Number.isFinite))throw Error('Invalid follow position');
   if(distance<=radius+(run.walking?1:5))motion(run,false);
   else{
    // Ease near the cursor, cap travel speed, and never overshoot contact.
    const travel=Math.min(distance-radius,Math.max(1,getSpeed())*dt,(distance-radius)*(1-Math.exp(-3*dt)));
    const direction=Math.abs(dx)>Math.max(5,Math.abs(dy)*.15)?Math.sign(dx):(run.direction||0);
    motion(run,true,direction);move(position.x+dx/distance*travel,position.y+dy/distance*travel);
   }
  }catch{if(active===run){run.time=now();motion(run,false);}}
  if(active===run)run.timer=schedule(()=>frame(run),16);
 };
 const start=()=>{if(active)return false;const run={time:now(),walking:false,direction:0,timer:null};active=run;run.timer=schedule(()=>frame(run),16);return true;};
 return{start,stop,toggle(){if(active){stop();return false;}start();return true;},get following(){return !!active;}};
}
module.exports={createPetFollower};
