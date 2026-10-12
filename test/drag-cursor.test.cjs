const test=require('node:test'),assert=require('node:assert/strict');
const net=require('node:net'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createCursorReader,toScreenPoint}=require('../drag-cursor.cjs');

test('compositor coordinates map to the physical pixels used by XWayland',()=>{
 const monitor={name:'eDP-1',x:0,y:0,width:1920,height:1200,scale:1.2};
 assert.deepEqual(toScreenPoint({x:1200,y:700},[monitor],[{label:'Built-in display',bounds:{x:0,y:0,width:1920,height:1200}}]),{x:1440,y:840});
 const other={name:'DP-1',x:1600,y:0,width:2560,height:1440,scale:1.6};
 assert.deepEqual(toScreenPoint({x:1700,y:100},[monitor,other],[{label:'DP-1',bounds:{x:1920,y:0,width:2560,height:1440}}]),{x:2080,y:160});
 assert.throws(()=>toScreenPoint({x:NaN,y:0}),/Invalid/);
});

test('fast jumps are read as absolute points, without integrating missing events',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'orbit-cursor-')),folder=path.join(root,'hypr','session');fs.mkdirSync(folder,{recursive:true});
 const points=[{x:10,y:30},{x:1400,y:600},{x:250,y:80},{x:900,y:400}];let index=0;
 const server=net.createServer(socket=>socket.once('data',data=>{assert.equal(data.toString(),'j/cursorpos');const text=JSON.stringify(points[index++]);socket.write(text.slice(0,6));socket.end(text.slice(6));}));
 await new Promise(resolve=>server.listen(path.join(folder,'.socket.sock'),resolve));
 try{const read=createCursorReader({instance:'session',runtimeDir:root});for(const point of points)assert.deepEqual(await read(),point);}finally{await new Promise(resolve=>server.close(resolve));fs.rmSync(root,{recursive:true,force:true});}
});

test('a failed compositor query does not fall back to a stale XWayland cursor',async()=>{
 const read=createCursorReader({instance:'missing',runtimeDir:'/tmp/orbit-no-such-runtime',fallback:()=>({x:0,y:0})});
 await assert.rejects(read(),/ENOENT/);
 const native=createCursorReader({instance:'',runtimeDir:'',fallback:()=>({x:20,y:30})});assert.deepEqual(await native(),{x:20,y:30});
});
