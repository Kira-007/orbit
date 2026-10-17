const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function harness(){
 const images=[],draws=[],frames=new Map();let next=0;
 const canvas={width:300,height:200,getContext:()=>({clearRect(){},drawImage:(...args)=>draws.push(args)})};
 const context=vm.createContext({Image:class{constructor(){this.width=600;this.height=100;images.push(this);}},performance:{now:()=>0},requestAnimationFrame:fn=>{frames.set(++next,fn);return next;},cancelAnimationFrame:id=>frames.delete(id)});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/renderer/sprite-player.js'),'utf8')+';globalThis.Player=SpritePlayer;',context);
 return{player:new context.Player(canvas),canvas,images,draws,frames};
}
const sheet=()=>({sheet:'file:///pet.png',frames:6,columns:6,fps:10});
test('a failed image load can be retried with the same sheet',()=>{
 const h=harness(),config=sheet();h.player.set(config);h.images[0].onerror();
 h.player.set(config);assert.equal(h.images.length,2);h.images[1].onload();assert.equal(h.draws.length,1);
});
test('late image loads cannot overwrite a newer animation or keep running after closing',()=>{
 const h=harness();h.player.set(sheet());h.player.set({...sheet(),sheet:'file:///walk.png'});
 h.images[0].onload();assert.equal(h.draws.length,0);h.images[1].onload();assert.equal(h.draws.length,1);assert.equal(h.frames.size,1);
 h.player.set(null);assert.equal(h.frames.size,0);h.images[0].onerror();h.player.set(null);assert.equal(h.images.length,2);
});
test('asynchronous image loading uses the frame geometry originally requested',()=>{
 const h=harness(),config=sheet();h.player.set(config,false);config.columns=2;config.frames=2;
 h.images[0].onload();assert.equal(h.draws[0][3],100);assert.equal(h.draws[0][4],100);
 h.canvas.width=400;h.player.set(sheet(),false);assert.equal(h.images.length,2);
});
