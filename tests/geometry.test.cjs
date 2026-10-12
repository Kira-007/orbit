const test=require('node:test'),assert=require('node:assert/strict');const {placePet}=require('../src/main/geometry.cjs');
test('pet reaches every corner while its transparent window stays on screen',()=>{const area={x:0,y:0,width:1920,height:1200};for(const [x,y] of [[0,0],[1770,0],[0,1071],[1770,1071]]){const p=placePet(x,y,area);assert.equal(p.x+p.petX,x);assert.equal(p.y+p.petY,y);assert(p.x>=0&&p.y>=0&&p.x+374<=1920&&p.y+630<=1200);}});
test('near the bottom, controls fit above without moving the pet',()=>{const p=placePet(800,900,{x:0,y:0,width:1920,height:1200});assert.equal(p.above,true);assert.equal(p.petY,330);assert.equal(p.y+p.petY,900);});

test('window position stays continuous when the controls switch sides',()=>{const area={x:0,y:0,width:1920,height:1200};let previous;for(let y=560;y<590;y++){const p=placePet(800,y,area);if(previous){assert(Math.abs(p.y-previous.y)<=1);assert(Math.abs(p.petY-previous.petY)<=1);}previous=p;}});
