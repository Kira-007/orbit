'use strict';
function createRandomFleas({spawn,getArea,canSpawn=()=>true,getMargin=()=>({x:80,y:80}),random=Math.random,schedule=setTimeout,cancel=clearTimeout,minDelay=8*60000,maxDelay=15*60000}){
 let timer=null,active=false;
 const arm=()=>{if(active)timer=schedule(tick,minDelay+random()*(maxDelay-minDelay));};
 const tick=()=>{
  timer=null;if(!active)return;
  try{
   if(canSpawn()){
    const area=getArea(),margin=getMargin(),mx=Math.min(margin.x,area.width/2),my=Math.min(margin.y,area.height/2);
    spawn({x:Math.round(area.x+mx+random()*Math.max(0,area.width-2*mx)),y:Math.round(area.y+my+random()*Math.max(0,area.height-2*my))});
   }
  }finally{arm();}
 };
 return{start(){if(active)return;active=true;arm();},stop(){active=false;if(timer!==null)cancel(timer);timer=null;}};
}
module.exports={createRandomFleas};
