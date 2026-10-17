const {test}=require('node:test'),assert=require('node:assert/strict');
const {createPetFollower}=require('../src/main/pet-follower.cjs');
function harness(){let time=0,position={x:0,y:0},target={x:300,y:0},next=0;const jobs=new Map(),states=[],moves=[];const follower=createPetFollower({getPosition:()=>position,getTarget:async()=>({...target}),move:(x,y)=>{position={x,y};moves.push(position)},onMotion:s=>states.push(s),getSpeed:()=>150,getRadius:()=>20,now:()=>time,schedule:fn=>{jobs.set(++next,fn);return next},cancel:id=>jobs.delete(id)});return{follower,states,moves,target,get position(){return position},async tick(frames=1){for(let i=0;i<frames;i++){time+=16;const current=[...jobs];jobs.clear();for(const [,fn]of current)await fn();}},get jobs(){return jobs.size}};}
test('follows a moving target, pauses on contact, then resumes without another toggle',async()=>{
 const h=harness();h.follower.toggle();await h.tick(300);assert(h.position.x>279&&h.position.x<281);assert.equal(h.states.at(-1).walking,false);assert.equal(h.follower.following,true);
 const paused={...h.position};await h.tick(20);assert.deepEqual(h.position,paused);
 h.target.x=-200;await h.tick(20);assert(h.position.x<paused.x);assert.deepEqual(h.states.at(-1),{walking:true,direction:-1});
 h.follower.toggle();const stopped={...h.position};await h.tick(100);assert.deepEqual(h.position,stopped);assert.equal(h.jobs,0);assert.equal(h.follower.following,false);
});
test('movement is speed-limited, never overshoots, and stops cleanly during cursor reads',async()=>{
 const h=harness();h.follower.start();await h.tick(100);let previous={x:0,y:0};for(const p of h.moves){assert(Math.hypot(p.x-previous.x,p.y-previous.y)<=2.401);assert(p.x<=280);previous=p;}
 let resolve,moved=false;const f=createPetFollower({getPosition:()=>({x:0,y:0}),getTarget:()=>new Promise(r=>resolve=r),move:()=>moved=true,schedule:fn=>{global.nextFollowTest=fn;return 1},cancel:()=>{}});f.start();const pending=global.nextFollowTest();f.stop();resolve({x:500,y:0});await pending;assert.equal(moved,false);delete global.nextFollowTest;
});
