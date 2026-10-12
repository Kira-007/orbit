const net=require('node:net'),path=require('node:path');

function toScreenPoint(cursor,monitors=[],displays=[]){
 if(!Number.isFinite(cursor?.x)||!Number.isFinite(cursor?.y))throw Error('Invalid pointer position');
 const monitor=monitors.find(m=>cursor.x>=m.x&&cursor.y>=m.y&&cursor.x<m.x+m.width/m.scale&&cursor.y<m.y+m.height/m.scale);
 if(!monitor)return cursor;
 const display=displays.find(d=>d.label===monitor.name)||displays.find(d=>d.bounds.width===monitor.width&&d.bounds.height===monitor.height);
 const origin=display?.bounds||{x:monitor.x*monitor.scale,y:monitor.y*monitor.scale};
 return{x:origin.x+(cursor.x-monitor.x)*monitor.scale,y:origin.y+(cursor.y-monitor.y)*monitor.scale};
}

function createCursorReader({instance=process.env.HYPRLAND_INSTANCE_SIGNATURE,runtimeDir=process.env.XDG_RUNTIME_DIR,getMonitors=()=>[],getDisplays=()=>[],fallback}){
 if(!instance||!runtimeDir)return async()=>fallback();
 const endpoint=path.join(runtimeDir,'hypr',instance,'.socket.sock');
 return()=>new Promise((resolve,reject)=>{
  const socket=net.createConnection(endpoint);let text='',settled=false;
  const finish=(error,point)=>{if(settled)return;settled=true;socket.destroy();error?reject(error):resolve(point);};
  socket.setTimeout(120,()=>finish(Error('Pointer query timed out')));
  socket.once('error',error=>finish(error));
  socket.once('connect',()=>socket.write('j/cursorpos'));
  socket.on('data',chunk=>{text+=chunk;if(text.length>4096)finish(Error('Invalid pointer response'));});
  socket.once('end',()=>{try{finish(null,toScreenPoint(JSON.parse(text),getMonitors(),getDisplays()));}catch(error){finish(error);}});
 });
}
module.exports={createCursorReader,toScreenPoint};
