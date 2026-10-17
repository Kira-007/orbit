const net=require('node:net'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
function controlPath(){return path.join(process.env.XDG_RUNTIME_DIR||process.env.XDG_STATE_HOME||path.join(os.homedir(),'.local/state'),'orbit-agent-pet-control.sock');}
function parseSummon(text,now=Date.now()){
 const value=JSON.parse(text);
 if(value?.type!=='summon'||![value.x,value.y,value.time].every(Number.isFinite)||Math.abs(now-value.time)>5000)throw Error('Invalid or expired summon request');
 return {x:value.x,y:value.y};
}
function listenForSummon(onSummon,endpoint=controlPath()){
 fs.mkdirSync(path.dirname(endpoint),{recursive:true});
 try{if(fs.lstatSync(endpoint).isSocket())fs.unlinkSync(endpoint);else throw Error('Orbit control path is not a socket');}catch(error){if(error.code!=='ENOENT')throw error;}
 const server=net.createServer(socket=>{
  let text='',handled=false;socket.setTimeout(1000,()=>socket.destroy());socket.on('error',()=>{});
  socket.on('data',chunk=>{if(handled)return;text+=chunk;if(text.length>1024){handled=true;socket.end('error: request too large\n');return;}if(!text.includes('\n'))return;handled=true;
   try{onSummon(parseSummon(text.split('\n')[0]));socket.end('ok\n');}catch{socket.end('error: could not summon pet\n');}
  });
 });
 server.on('error',error=>console.error('Orbit shortcut:',error.message));
 server.listen(endpoint,()=>fs.chmodSync(endpoint,0o600));server.unref();
 return {close(){server.close();try{fs.unlinkSync(endpoint);}catch{}}};
}
module.exports={controlPath,parseSummon,listenForSummon};
