'use strict';
function createFleaQueue({createMarker,removeMarker,getDestination,run,stop,max=32}){
 const pending=[];let current=null;
 const next=()=>{
  if(current||!pending.length)return;
  current=pending.shift();
  if(!run(getDestination(current.point)))complete();
 };
 const complete=()=>{if(!current)return;removeMarker(current.marker);current=null;next();};
 return{
  add(point){if(pending.length+(current?1:0)>=max)return false;const fixed={x:point.x,y:point.y};pending.push({point:fixed,marker:createMarker(fixed)});next();return true;},
  complete,
  clear(){const items=[...(current?[current]:[]),...pending];current=null;pending.length=0;stop();for(const item of items)removeMarker(item.marker);},
  get count(){return pending.length+(current?1:0);}
 };
}
module.exports={createFleaQueue};
