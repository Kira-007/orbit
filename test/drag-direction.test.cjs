const test=require('node:test'),assert=require('node:assert/strict');
const {DragDirection}=require('../drag-direction.js');
test('deliberate turns require distance and sustained motion',()=>{
 const right=new DragDirection(100,-1);
 assert.equal(right.update(108,0),-1);
 assert.equal(right.update(120,40),-1);
 assert.equal(right.update(128,75),1);
 const left=new DragDirection(100,1);
 assert.equal(left.update(92,0),1);
 assert.equal(left.update(80,40),1);
 assert.equal(left.update(72,75),-1);
});
test('sideways wobble during vertical dragging does not flip repeatedly',()=>{
 const drag=new DragDirection(100,1);
 for(let i=0;i<60;i++)assert.equal(drag.update(100+(Math.floor(i/4)%2?10:0),i*17),1);
});
test('a brief large sideways twitch does not turn the pet',()=>{
 const drag=new DragDirection(100,1);
 for(let i=0;i<60;i++)assert.equal(drag.update(100-(Math.floor(i/3)%2?25:0),i*17),1);
});
test('predominantly vertical movement keeps its facing despite a wider lateral twitch',()=>{
 const drag=new DragDirection(0,1);
 const samples=[[0,0,0],[9,50,15],[20,80,23],[10,97,27],[0,115,30],[1,150,38],[0,175,42]];
 for(const [x,time,y] of samples)assert.equal(drag.update(x,time,y),1);
 for(let i=0;i<60;i++)assert.equal(drag.update(Math.floor(i/4)%2?12:0,200+i*17,45+i*4),1);
});
test('deliberate reversal works in both directions with small pointer noise',()=>{
 const drag=new DragDirection(100,1);
 assert.equal(drag.update(125,0),1);
 assert.equal(drag.update(120,20),1);
 assert.equal(drag.update(110,45),1);
 assert.equal(drag.update(112,60),1);
 assert.equal(drag.update(100,95),-1);
 assert.equal(drag.update(90,110),-1);
 assert.equal(drag.update(96,130),-1);
 assert.equal(drag.update(105,165),-1);
 assert.equal(drag.update(103,180),-1);
 assert.equal(drag.update(118,205),1);
});
test('invalid samples cannot alter direction',()=>{
 const drag=new DragDirection(100,-1);
 assert.equal(drag.update(NaN,0),-1);
 assert.equal(drag.update(130,Infinity),-1);
});
