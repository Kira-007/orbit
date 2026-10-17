const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const {parseSummon,listenForSummon}=require('../src/main/summon-control.cjs');
test('summon accepts one fixed finite cursor snapshot and rejects old or malformed requests',()=>{assert.deepEqual(parseSummon(JSON.stringify({type:'summon',x:-5,y:200,time:1000}),1001),{x:-5,y:200});for(const value of [{type:'other',x:1,y:1,time:1000},{type:'summon',x:null,y:1,time:1000},{type:'summon',x:1,y:1,time:0}])assert.throws(()=>parseSummon(JSON.stringify(value),10000));});
test('local control socket acknowledges capture once and rejects oversized input',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'orbit-control-')),endpoint=path.join(dir,'control.sock'),points=[];
 const server=listenForSummon(point=>points.push(point),endpoint);
 try{
  const send=message=>new Promise((resolve,reject)=>{let text='';const client=net.createConnection(endpoint);client.on('error',reject);client.on('connect',()=>client.write(message));client.on('data',chunk=>text+=chunk);client.on('end',()=>resolve(text));});
  assert.equal(await send(JSON.stringify({type:'summon',x:10,y:20,time:Date.now()})+'\n'),'ok\n');
  assert.deepEqual(points,[{x:10,y:20}]);assert.match(await send('x'.repeat(1025)),/error/);assert.equal(points.length,1);
 }finally{server.close();fs.rmSync(dir,{recursive:true,force:true});}
});
