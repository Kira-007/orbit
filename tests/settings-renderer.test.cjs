const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {normalizeSettings}=require('../src/main/settings.cjs');

class Element{
 constructor(id=''){this.id=id;this.value='';this.type='text';this.children=[];this.options=[];this.attributes={};this.style={setProperty(){}};this.dataset={};this.listeners={};this.classes=new Set();this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};this.previousElementSibling={style:{}};}
 setAttribute(key,value){this.attributes[key]=value;}removeAttribute(key){delete this.attributes[key];}getAttribute(key){return this.attributes[key];}
 addEventListener(name,fn){this.listeners[name]=fn;}append(...children){this.children.push(...children);if(this.tag==='select')this.options.push(...children);}replaceChildren(){this.children=[];this.options=[];}
 after(){}before(){}focus(){}select(){}click(){return this.onclick?.();}get selectedOptions(){return this.options.filter(option=>option.value===this.value);}
}
async function harness({update=async()=>{},pickSpriteSheet=async()=>null,animations=true}={}){
 const elements=new Map(),events={},updates=[],timers=new Map();let closed=0,nextTimer=0;
 const el=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
 const selectIds=['hoverDelay','completionMinutes','harness','face','petMode','sprite-pet','animation-state','sprite-facing'];
 for(const id of selectIds){el(id).tag='select';el(id).options=[{value:id==='animation-state'?'idle':'right',textContent:'Option'}];}
 el('animation-state').value='idle';for(const id of ['animations','controls'])el(id).type='checkbox';
 const preferences=normalizeSettings({animations,petMode:'sprite',activeSpritePet:'a',spritePets:[{id:'a',name:'A',spriteSheets:{idle:{sheet:'file:///a.png',frames:6,columns:6,fps:9,facing:'left'}}},{id:'b',name:'B',spriteSheets:{idle:{sheet:'file:///b.png',frames:8,columns:8,fps:12}}}]});
 const context=vm.createContext({document:{getElementById:el,querySelectorAll:()=>selectIds.map(el),querySelector:()=>el('mouth'),createElement:tag=>new Element(tag),addEventListener(){},documentElement:new Element(),body:new Element()},window:{preferences:{get:async()=>preferences,update:async value=>{updates.push(structuredClone(value));return update(value);},pickSpriteSheet,close:()=>closed++,resetPosition(){}},addEventListener:(name,fn)=>events[name]=fn},SpritePlayer:class{set(){}},structuredClone,crypto:require('node:crypto').webcrypto,setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timers.delete(id)});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/renderer/settings-renderer.js'),'utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 return{el,events,updates,timers,run:code=>vm.runInContext(code,context),closed:()=>closed,flush:()=>new Promise(resolve=>setImmediate(resolve))};
}

test('custom preview follows the animations setting',async()=>{
 const h=await harness({animations:false});
 assert.equal(h.run("document.body.classes.has('animations-off')"),true);
 h.el('animations').checked=true;h.el('animations').listeners.input();
 assert.equal(h.run("document.body.classes.has('animations-off')"),false);
});

test('movement speed slider displays and saves a numeric value without changing animation speed',async()=>{
 const h=await harness();
 assert.equal(h.el('movementSpeed').value,700);
 assert.equal(h.el('movement-speed-label').textContent,'700 px/s');
 h.el('movementSpeed').value='1150';h.el('movementSpeed').listeners.input();
 assert.equal(h.el('movement-speed-label').textContent,'1150 px/s');
 h.el('movementSpeed').listeners.change();await h.flush();
 assert.equal(h.updates.at(-1).movementSpeed,1150);
 assert.equal(h.updates.at(-1).spriteSheets.idle.fps,9);
 assert.equal(h.updates.at(-1).petScale,1);
 const html=fs.readFileSync(path.join(__dirname,'../src/renderer/settings.html'),'utf8');
 assert.match(html,/<input id="movementSpeed" type="range" min="150" max="1800" step="50"/);
});

test('upload keeps its original pet and animation when selection changes during the dialog',async()=>{
 let finish;const h=await harness({pickSpriteSheet:()=>new Promise(resolve=>finish=resolve)});
 const uploading=h.el('pick-sprite').onclick();
 h.run("choosePet('b')");h.el('animation-state').value='walking';
 finish({sheet:'file:///replacement.png',frames:10,columns:10,fps:10});await uploading;
 const settings=h.run('settings');
 assert.equal(settings.activeSpritePet,'b');
 assert.equal(settings.spriteSheets.idle.sheet,'file:///b.png');
 assert.equal(settings.spritePets[0].spriteSheets.idle.sheet,'file:///replacement.png');
 assert.equal(settings.spritePets[0].spriteSheets.idle.fps,9);
 assert.equal(settings.spritePets[0].spriteSheets.idle.facing,'left');
 assert.equal(settings.spritePets[0].spriteSheets.walking,undefined);
});

test('closing settings waits for a pending debounce and its disk write',async()=>{
 let finish;const h=await harness({update:()=>new Promise(resolve=>finish=resolve)});
 h.el('petName').value='Newest name';h.el('petName').listeners.input();
 let prevented=false;const event={preventDefault:()=>prevented=true};h.events.beforeunload(event);
 await h.flush();assert.equal(prevented,true);assert.equal(event.returnValue,false);assert.equal(h.closed(),0);
 assert.equal(h.updates.at(-1).petName,'Newest name');assert.equal(h.timers.size,0);
 finish();await h.flush();assert.equal(h.closed(),1);
});

test('failed save leaves settings open and retries the unsaved edit on the next close',async()=>{
 let fail=true;const h=await harness({update:async()=>{if(fail)throw Error('disk full');}});
 h.el('petName').value='Keep my edit';h.el('petName').listeners.input();
 const event=()=>({preventDefault(){}});h.events.beforeunload(event());await h.flush();
 assert.equal(h.closed(),0);assert.equal(h.el('saved').textContent,'Could not save');
 fail=false;h.events.beforeunload(event());await h.flush();
 assert.equal(h.closed(),1);assert.equal(h.updates.at(-1).petName,'Keep my edit');
});
