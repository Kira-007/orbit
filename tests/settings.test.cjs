const test=require('node:test'),assert=require('node:assert/strict');const {normalizeSettings}=require('../src/main/settings.cjs');const {placePet}=require('../src/main/geometry.cjs');
test('customization validates colors, names, expressions, and size bounds',()=>{const p=normalizeSettings({petScale:10,petName:'  Nova  ',bodyColor:'invalid',accentColor:'#12ab34',face:'focused'});assert.equal(p.petScale,2.4);assert.equal(p.petName,'Nova');assert.equal(p.bodyColor,'#90bbb7');assert.equal(p.accentColor,'#12ab34');assert.equal(p.face,'focused');assert.equal(normalizeSettings({petScale:-1}).petScale,.6);});
test('movement speed defaults for existing settings, clamps bounds, and survives saving',()=>{
 assert.equal(normalizeSettings({petScale:1.25}).movementSpeed,700);
 for(const value of [NaN,Infinity,'900',null])assert.equal(normalizeSettings({movementSpeed:value}).movementSpeed,700);
 assert.equal(normalizeSettings({movementSpeed:20}).movementSpeed,150);
 assert.equal(normalizeSettings({movementSpeed:9000}).movementSpeed,1800);
 const saved=normalizeSettings(JSON.parse(JSON.stringify(normalizeSettings({movementSpeed:1150,petScale:1.25}))));
 assert.equal(saved.movementSpeed,1150);assert.equal(saved.petScale,1.25);
});
test('scaled pet can reach corners without moving outside the screen',()=>{const area={x:0,y:0,width:1920,height:1200};for(const scale of [.6,1,1.6,2.4]){const x=1920-150*scale,y=1200-129*scale,p=placePet(x,y,area,374,630,scale);assert(Math.abs(p.x+p.petX-x)<=1);assert(Math.abs(p.y+p.petY-y)<=1);assert(p.petX>=0&&p.petX+150*scale<=375);assert(p.petY>=0&&p.petY+129*scale<=631);}});

test('sprite settings preserve independent animation sheets and bound frame counts',()=>{const settings=normalizeSettings({spriteSheets:{walking:{sheet:'file:///tmp/walk.png',frames:8,columns:8,fps:12},idle:{sheet:'file:///tmp/pet.png',frames:8,columns:4,fps:12},working:{sheet:'file:///tmp/work.png',frames:999,columns:0,fps:90},error:{sheet:'https://example.com/pet.png'}}});assert.equal(settings.spriteSheets.walking.frames,8);assert.equal(settings.spriteSheets.idle.frames,8);assert.equal(settings.spriteSheets.idle.columns,4);assert.equal(settings.spriteSheets.working.frames,256);assert.equal(settings.spriteSheets.working.fps,60);assert.equal(settings.spriteSheets.error,undefined);});

test('switching and round-tripping pets preserves each independent animation set',()=>{
 const a={id:'cat',name:'Cat',facing:'right',spriteSheets:{idle:{sheet:'file:///cat.png',frames:10}}};
 const b={id:'chibi',name:'Chibi',facing:'left',spriteSheets:{walking:{sheet:'file:///chibi.png',frames:2}}};
 const selected=normalizeSettings({spritePets:[a,b],activeSpritePet:'chibi'});
 assert.equal(selected.spriteSheets.walking.sheet,'file:///chibi.png');assert.equal(selected.spritePets[1].facing,'left');
 selected.spriteSheets.walking.frames=4;
 const restored=normalizeSettings(JSON.parse(JSON.stringify(selected)));
 assert.equal(restored.spritePets[1].spriteSheets.walking.frames,4);
 const switched=normalizeSettings({...restored,activeSpritePet:'cat'});
 assert.equal(switched.spriteSheets.idle.frames,10);assert.equal(switched.spritePets[1].spriteSheets.walking.frames,4);
});
test('legacy sprites migrate and empty pets survive while uploading states',()=>{
 const legacy=normalizeSettings({spriteSheets:{idle:{sheet:'file:///old.png',frames:8}}});
 assert.equal(legacy.spritePets.length,1);assert.equal(legacy.spriteSheets.idle.frames,8);
 const fresh=normalizeSettings({spritePets:[{id:'new',name:'My pet',spriteSheets:{}}],activeSpritePet:'new'});
 assert.equal(fresh.spritePets.length,1);assert.deepEqual(fresh.spriteSheets,{});
});
test('different animation facing directions survive saving without changing their speeds',()=>{
 const pet={id:'hornet',name:'Hornet',facing:'right',spriteSheets:{idle:{sheet:'file:///idle.png',frames:6,fps:3,facing:'left'},walking:{sheet:'file:///walk.png',frames:8,fps:15,facing:'right'},working:{sheet:'file:///working.png',frames:6,facing:'invalid'}}};
 const settings=normalizeSettings({spritePets:[pet],activeSpritePet:pet.id});
 const saved=normalizeSettings(JSON.parse(JSON.stringify(settings)));
 assert.equal(saved.spriteSheets.idle.facing,'left');assert.equal(saved.spriteSheets.walking.facing,'right');
 assert.equal(saved.spriteSheets.idle.fps,3);assert.equal(saved.spriteSheets.walking.fps,15);
 assert.equal(saved.spriteSheets.working.facing,undefined);
});
test('animation offsets are bounded and preserved separately per state',()=>{
 const sheet={sheet:'file:///tmp/pet.png',frames:1,columns:1,fps:8};
 const p=normalizeSettings({spriteSheets:{idle:{...sheet,offsetX:24,offsetY:-12},walking:{...sheet,offsetX:999,offsetY:-999}}});
 assert.equal(p.spriteSheets.idle.offsetX,24);assert.equal(p.spriteSheets.idle.offsetY,-12);
 assert.equal(p.spriteSheets.walking.offsetX,100);assert.equal(p.spriteSheets.walking.offsetY,-100);
 assert.equal(normalizeSettings(p).spriteSheets.idle.offsetX,24);
});
test('global pet offsets survive saving and apply independently of animation selection',()=>{
 const p=normalizeSettings({activeSpritePet:'hornet',spritePets:[{id:'hornet',offsetX:25,offsetY:-15,spriteSheets:{}}]});
 const saved=normalizeSettings(JSON.parse(JSON.stringify(p)));
 assert.equal(saved.spritePets[0].offsetX,25);assert.equal(saved.spritePets[0].offsetY,-15);
});
