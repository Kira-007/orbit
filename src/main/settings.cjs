const animationStates=['idle','walking','dragging','working','waiting','done','error','unknown'];
const defaults={animations:true,controls:false,hoverDelay:750,completionMinutes:10,harness:'codex-cli',petScale:1,movementSpeed:700,petName:'Orbit',bodyColor:'#90bbb7',accentColor:'#8ce8cf',face:'friendly',spriteSheets:{},spritePets:[],activeSpritePet:'',petMode:'custom'};
function normalizeSheets(value){
 const sheets={};for(const state of animationStates){const entry=value?.[state];if(entry&&typeof entry.sheet==='string'&&entry.sheet.startsWith('file:'))sheets[state]={sheet:entry.sheet,name:String(entry.name||'Sprite sheet').slice(0,180),frames:Math.max(1,Math.min(256,Math.round(Number(entry.frames)||1))),columns:Math.max(1,Math.min(256,Math.round(Number(entry.columns)||Number(entry.frames)||1))),fps:Math.max(1,Math.min(60,Number(entry.fps)||10)),offsetX:Math.max(-100,Math.min(100,Number(entry.offsetX)||0)),offsetY:Math.max(-100,Math.min(100,Number(entry.offsetY)||0)),...(['left','right'].includes(entry.facing)?{facing:entry.facing}:{})};}return sheets;
}
function normalizeSettings(value={}){
 const color=(v,f)=>typeof v==='string'&&/^#[0-9a-f]{6}$/i.test(v)?v:f;
 const legacy=normalizeSheets(value.spriteSheets),spritePets=[];const ids=new Set();
 for(const entry of (Array.isArray(value.spritePets)?value.spritePets:[]).slice(0,64)){
  if(!entry||typeof entry.id!=='string'||!/^[a-zA-Z0-9_-]{1,80}$/.test(entry.id)||ids.has(entry.id))continue;
  ids.add(entry.id);spritePets.push({id:entry.id,name:String(entry.name||'My pet').trim().slice(0,60)||'My pet',facing:entry.facing==='left'?'left':'right',offsetX:Math.max(-100,Math.min(100,Number(entry.offsetX)||0)),offsetY:Math.max(-100,Math.min(100,Number(entry.offsetY)||0)),spriteSheets:normalizeSheets(entry.spriteSheets)});
 }
 if(!spritePets.length&&Object.keys(legacy).length)spritePets.push({id:'legacy',name:'My pet',facing:'right',spriteSheets:legacy});
 const active=spritePets.find(p=>p.id===value.activeSpritePet)||spritePets[0];const spriteSheets=active?.spriteSheets||{};
 return{spritePets,activeSpritePet:active?.id||'',spriteSheets,petMode:value.petMode==='sprite'||(!value.petMode&&Object.keys(spriteSheets).length)?'sprite':'custom',petScale:Number.isFinite(value.petScale)?Math.max(.6,Math.min(2.4,value.petScale)):defaults.petScale,movementSpeed:Number.isFinite(value.movementSpeed)?Math.max(150,Math.min(1800,value.movementSpeed)):defaults.movementSpeed,petName:typeof value.petName==='string'&&value.petName.trim()?value.petName.trim().slice(0,30):defaults.petName,bodyColor:color(value.bodyColor,defaults.bodyColor),accentColor:color(value.accentColor,defaults.accentColor),face:['friendly','focused','sleepy'].includes(value.face)?value.face:defaults.face,animations:typeof value.animations==='boolean'?value.animations:defaults.animations,controls:typeof value.controls==='boolean'?value.controls:defaults.controls,hoverDelay:[400,750,1200].includes(value.hoverDelay)?value.hoverDelay:defaults.hoverDelay,completionMinutes:[5,10,30,60].includes(value.completionMinutes)?value.completionMinutes:defaults.completionMinutes,harness:['codex-cli','codex-desktop','claude','antigravity'].includes(value.harness)?value.harness:defaults.harness};
}
module.exports={defaults,normalizeSettings,normalizeSheets,animationStates};
