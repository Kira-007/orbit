const test=require('node:test'),assert=require('node:assert/strict');
const {createPetRunner}=require('../src/main/pet-runner.cjs');

function harness(options={}){
 let time=0,nextId=1,position={x:0,y:0};
 const timers=new Map(),moves=[],starts=[],ends=[];
 const runner=createPetRunner({
  getPosition:()=>position,
  move:(x,y,motion)=>{position={x,y};moves.push({x,y,...motion,time});},
  onStart:event=>starts.push(event),onEnd:event=>ends.push({...event,time}),
  now:()=>time,
  schedule:(fn,delay)=>{const id=nextId++;timers.set(id,{at:time+delay,fn});return id;},
  cancel:id=>timers.delete(id),...options
 });
 const tick=duration=>{
  const until=time+duration;
  while(true){
   const due=[...timers].filter(([,timer])=>timer.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];
   if(!due)break;
   time=due[1].at;timers.delete(due[0]);due[1].fn();
  }
  time=until;
 };
 // Simulate a blocked main loop, then run each currently due callback once.
 const stall=duration=>{
  time+=duration;
  for(const [id,timer]of [...timers])if(timer.at<=time&&timers.delete(id))timer.fn();
 };
 return{runner,tick,stall,moves,starts,ends,timers,get position(){return position;}};
}

test('runs to the captured destination and ends exactly there at the configured speed',()=>{
 const h=harness(),target={x:700,y:0};
 assert.equal(h.runner.run(target),true);
 target.x=9999;target.y=9999;
 assert.equal(h.runner.running,true);
 assert.deepEqual(h.starts,[{direction:1}]);
 h.tick(500);
 assert(h.position.x>300&&h.position.x<400);
 assert.equal(h.position.y,0);
 assert(h.moves.every(frame=>frame.walking&&frame.direction===1));
 h.tick(500);
 assert.deepEqual(h.position,{x:700,y:0});
 assert.equal(h.runner.running,false);
 assert.deepEqual(h.ends,[{cancelled:false,time:1000}]);
 assert.equal(h.timers.size,0);
});

test('uses elapsed time after dropped frames instead of accumulating motion',()=>{
 const h=harness();h.runner.run({x:700,y:0});
 h.stall(500);
 assert.deepEqual(h.position,{x:350,y:0});
 h.stall(700);
 assert.deepEqual(h.position,{x:700,y:0});
 assert.deepEqual(h.ends,[{cancelled:false,time:1200}]);
});

test('bounds short and long runs while preserving exact final coordinates',()=>{
 const short=harness();short.runner.run({x:2,y:0});
 short.tick(179);assert.equal(short.runner.running,true);
 short.tick(1);assert.deepEqual(short.position,{x:2,y:0});
 assert.equal(short.ends[0].time,180);
 const long=harness();long.runner.run({x:7000,y:1234});
 long.tick(2999);assert.equal(long.runner.running,true);
 long.tick(1);assert.deepEqual(long.position,{x:7000,y:1234});
 assert.equal(long.ends[0].time,3000);
});

test('configured speed changes travel duration',()=>{
 const h=harness({speed:350});h.runner.run({x:700,y:0});
 h.tick(1000);assert(h.position.x>340&&h.position.x<360);
 assert.equal(h.runner.running,true);
 h.tick(1000);assert.deepEqual(h.position,{x:700,y:0});
 assert.equal(h.ends[0].time,2000);
});

test('replacement cancels the first run once and starts at its current position',()=>{
 const h=harness();h.runner.run({x:700,y:0});h.tick(400);
 const previous={...h.position},count=h.moves.length;
 h.runner.run({x:-350,y:200});
 assert.deepEqual(h.position,previous);
 assert.deepEqual(h.starts,[{direction:1},{direction:-1}]);
 assert.deepEqual(h.ends,[{cancelled:true,time:400}]);
 h.tick(3000);
 assert.deepEqual(h.position,{x:-350,y:200});
 assert.equal(h.ends.length,2);assert.equal(h.ends[1].cancelled,false);
 assert(h.moves.slice(count).every(frame=>frame.direction===-1&&frame.x<=previous.x));
 assert.equal(h.timers.size,0);
});

test('stopping freezes movement and emits cancellation only once',()=>{
 const h=harness();h.runner.run({x:700,y:400});h.tick(200);
 const before={...h.position};
 assert.equal(h.runner.stop(),true);assert.equal(h.runner.stop(),false);
 h.tick(5000);
 assert.deepEqual(h.position,before);
 assert.deepEqual(h.ends,[{cancelled:true,time:200}]);
 assert.equal(h.runner.running,false);assert.equal(h.timers.size,0);
});

test('near-vertical travel preserves facing and tiny travel does nothing',()=>{
 const h=harness();assert.equal(h.runner.run({x:.3,y:.4}),false);
 assert.equal(h.moves.length,0);assert.equal(h.starts.length,0);assert.equal(h.ends.length,0);
 h.runner.run({x:5,y:200});
 assert.deepEqual(h.starts,[{direction:0}]);
 h.tick(1000);assert(h.moves.every(frame=>frame.direction===0));
});

test('rejects invalid destinations without interrupting a valid run',()=>{
 const h=harness();h.runner.run({x:700,y:0});
 assert.throws(()=>h.runner.run({x:NaN,y:20}),/destination/);
 assert.equal(h.runner.running,true);assert.equal(h.ends.length,0);
 h.tick(1000);assert.deepEqual(h.position,{x:700,y:0});
 assert.throws(()=>createPetRunner({getPosition:()=>({x:0,y:0}),move:()=>{},speed:0}),/speed/);
});
