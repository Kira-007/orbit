let usageSignature='';
const names={'claude':'Claude Code','codex-cli':'Codex CLI','codex-desktop':'Codex Desktop','antigravity':'AGY CLI'};
let data={sessions:[],online:{}},open=false,chatOpen=false,usageOpen=false,settingsOpen=false,stackExpanded=false,frontTaskKey=null,lastStackScroll=0,stackAnimating=false;
const defaults={animations:true,controls:false,hoverDelay:750,completionMinutes:10,harness:'codex-cli'};let settings={...defaults};try{settings={...defaults,...JSON.parse(localStorage.getItem('orbit-settings')||'{}')};}catch{}
let viewedThisOpen=new Set(),notifications={},dismissed={};
try{notifications=JSON.parse(localStorage.getItem('orbit-notifications')||'{}');dismissed=JSON.parse(localStorage.getItem('orbit-dismissed')||'{}');}catch{}
const taskKey=s=>(s.provider.startsWith('codex-')?'codex':s.provider)+':'+s.session;
const taskIdentity=s=>String(s.title||'').trim();
function saveNotifications(){try{localStorage.setItem('orbit-notifications',JSON.stringify(notifications));localStorage.setItem('orbit-dismissed',JSON.stringify(dismissed));}catch{}}
function visibleTasks(){
 for(const s of data.sessions){const key=taskKey(s),old=notifications[key];if(old&&old.time>s.time)continue;
 if(dismissed[key]===taskIdentity(s))continue;
 if(['working','waiting'].includes(s.status)||(s.status==='done'&&(old||s.time>=Date.now()-settings.completionMinutes*60000)))notifications[key]=s;
 }
 saveNotifications();return Object.values(notifications).sort((a,b)=>b.time-a.time);
}
function acknowledge(){}
function dismissTask(session){const key=taskKey(session);dismissed[key]=taskIdentity(session);delete notifications[key];saveNotifications();paint();requestAnimationFrame(reportRegions);}
const $=id=>document.getElementById(id);
const petSprite=new SpritePlayer($('pet-sprite'));let petAnimationState='idle',petWalking=false,petDirection=1;
function currentSpriteConfig(){return settings.petMode==='sprite'?((petWalking?settings.spriteSheets?.walking:null)||settings.spriteSheets?.[petAnimationState]||settings.spriteSheets?.idle):null;}
function applySpriteDirection(config=currentSpriteConfig()){const pet=settings.spritePets?.find(p=>p.id===settings.activeSpritePet),original=(config?.facing||pet?.facing)==='left'?-1:1;const transform='scaleX('+(petDirection*original)+')';if($('pet-sprite').style.transform!==transform)$('pet-sprite').style.transform=transform;}
function updatePetSprite(){const config=currentSpriteConfig();applySpriteDirection(config);$('pet').classList.toggle('custom-sprite',!!config);$('pet-sprite').hidden=!config;petSprite.set(config,settings.animations&&!matchMedia('(prefers-reduced-motion: reduce)').matches);}

let panelClosing=false,lastPanelView='';
$('overlay-layer').append($('harness-menu'),$('projects'));
$('harness-menu')._anchor=$('harness-toggle');$('projects')._anchor=$('thread-toggle');
function closeMenus(except){for(const [id,toggle] of [['harness-menu','harness-toggle'],['projects','thread-toggle'],['settings-menu',null],['pet-menu',null]]){if(id===except)continue;const menu=$(id);menu._wantedVisible=false;menu._motion?.cancel();menu._motion=null;menu.hidden=true;menu.style.pointerEvents='';if(toggle)$(toggle).setAttribute('aria-expanded','false');}}
function wantedVisible(element){return element._wantedVisible??!element.hidden;}
function animateVisible(element,visible){
 element._wantedVisible=visible;element._motion?.cancel();element.style.pointerEvents=visible?'':'none';if(element.id==='harness-menu'||element.id==='projects'||element.id==='settings-menu')element.style.zIndex=visible?'100':'90';
 if(visible)element.hidden=false;
 if(matchMedia('(prefers-reduced-motion: reduce)').matches||document.body.classList.contains('paused')){element.hidden=!visible;return Promise.resolve();}
 const above=element.id==='panel'&&document.body.classList.contains('above');
 const offset=above?-10:10;element.style.transformOrigin=above?'center bottom':'center top';
 const frames=visible?[{opacity:0,transform:`translateY(${offset}px) scale(.96)`},{opacity:1,transform:'translateY(0) scale(1)'}]:[{opacity:1,transform:'translateY(0) scale(1)'},{opacity:0,transform:`translateY(${offset*.65}px) scale(.97)`}];
 const motion=element.animate(frames,{duration:visible?230:160,easing:'cubic-bezier(.22,.75,.25,1)',fill:'both'});element._motion=motion;
 return motion.finished.catch(()=>{}).then(()=>{if(element._motion!==motion)return;if(!element._wantedVisible)element.hidden=true;motion.cancel();element._motion=null;requestAnimationFrame(reportRegions);});
}
function expand(value){
 const view=settingsOpen?'settings':chatOpen?'chat':usageOpen?'usage':'notifications';if(!value||view!==lastPanelView)closeMenus();lastPanelView=view;
 open=value;window.orbit.expand(open);$('pet').setAttribute('aria-expanded',String(open));
 if(!open){viewedThisOpen.clear();chatOpen=false;usageOpen=false;settingsOpen=false;panelClosing=true;animateVisible($('panel'),false).then(()=>{if(open)return;panelClosing=false;document.body.classList.remove('open','chat-open');requestAnimationFrame(reportRegions);});return;}
 panelClosing=false;if(!chatOpen&&!usageOpen&&!settingsOpen)acknowledge();paint();document.body.classList.add('open');$('composer').hidden=!chatOpen;$('cards').hidden=chatOpen||usageOpen||settingsOpen;$('settings-panel').hidden=!settingsOpen;$('usage-panel').hidden=!usageOpen;$('usage-toggle').setAttribute('aria-expanded',String(usageOpen));document.body.classList.toggle('chat-open',chatOpen);document.body.classList.toggle('stacked',!stackExpanded);animateVisible($('panel'),true);requestAnimationFrame(reportRegions);
}
$('notifications').onclick=()=>{const close=open&&!chatOpen&&!usageOpen&&!settingsOpen;chatOpen=false;usageOpen=false;settingsOpen=false;stackExpanded=false;expand(!close);};
$('chat-toggle').onclick=()=>{const close=open&&chatOpen;settingsOpen=false;usageOpen=false;chatOpen=!close;stackExpanded=true;expand(!close);if(chatOpen){loadProjects();$('prompt').focus();}};
$('usage-toggle').onclick=()=>{const close=open&&usageOpen;settingsOpen=false;chatOpen=false;usageOpen=!close;stackExpanded=true;expand(!close);if(!close)window.orbit.refreshUsage();};
$('harness').value=localStorage.getItem('orbit-harness')||settings.harness;
function chooseHarness(){ $('harness-toggle').textContent=names[$('harness').value]+' ▾';localStorage.setItem('orbit-harness',$('harness').value);$('submit-task').title=$('harness').value==='codex-desktop'?'Send to Desktop conversation':'Send message';}
chooseHarness();
$('thread-toggle').onclick=()=>{closeMenus('projects');$('harness-toggle').setAttribute('aria-expanded','false');animateVisible($('projects'),!wantedVisible($('projects')));$('thread-toggle').setAttribute('aria-expanded',String(wantedVisible($('projects'))));requestAnimationFrame(reportRegions);};
$('harness-toggle').onclick=()=>{closeMenus('harness-menu');$('thread-toggle').setAttribute('aria-expanded','false');const menu=$('harness-menu');animateVisible(menu,!wantedVisible(menu));$('harness-toggle').setAttribute('aria-expanded',String(wantedVisible(menu)));requestAnimationFrame(reportRegions);};
for(const button of document.querySelectorAll('[data-harness]'))button.onclick=()=>{$('harness').value=button.dataset.harness;chooseHarness();if(chatOpen)loadProjects();animateVisible($('harness-menu'),false);$('harness-toggle').setAttribute('aria-expanded','false');requestAnimationFrame(reportRegions);};
let selectedThread='',projectRequest=0;const threadSelections={};
async function loadProjects(){const request=++projectRequest,provider=$('harness').value;selectedThread=threadSelections[provider]||'';animateVisible($('projects'),false);$('thread-toggle').textContent='Loading…';$('projects').textContent='Loading conversations…';$('submit-task').disabled=true;const projects=await window.orbit.projects(provider);if(request!==projectRequest||provider!==$('harness').value)return;$('projects').replaceChildren();if(!projects.some(p=>p.id===selectedThread))selectedThread=projects[0]?.id||'';for(const project of projects){const button=document.createElement('button');button.type='button';button.className='project'+(project.id===selectedThread?' selected':'');button.setAttribute('aria-pressed',String(project.id===selectedThread));button.textContent=project.name;button.title=project.path;button.onclick=()=>{selectedThread=project.id;$('thread-toggle').textContent=project.name+' ▾';$('thread-toggle').title=project.name;animateVisible($('projects'),false);$('thread-toggle').setAttribute('aria-expanded','false');requestAnimationFrame(reportRegions);threadSelections[provider]=selectedThread;for(const item of $('projects').children){const selected=item===button;item.classList.toggle('selected',selected);item.setAttribute('aria-pressed',String(selected));}};$('projects').append(button);}threadSelections[provider]=selectedThread;const selected=projects.find(p=>p.id===selectedThread);$('thread-toggle').textContent=(selected?.name||'Choose thread')+' ▾';$('thread-toggle').title=selected?.name||'Choose thread';$('thread-toggle').disabled=!projects.length;$('submit-task').disabled=!projects.length;if(!projects.length)$('projects').textContent='No conversations detected for '+names[provider];requestAnimationFrame(reportRegions);}
$('composer').onsubmit=async e=>{e.preventDefault();const prompt=$('prompt').value.trim();if(!prompt)return;const button=$('submit-task');button.disabled=true;try{const result=await window.orbit.startTask($('harness').value,prompt,selectedThread);if(result.ok){$('prompt').value='';toast(result.message||'Task started');}else toast(result.message);}catch{toast('Could not start task');}finally{button.disabled=false;}};
function toast(message){$('toast').textContent=message;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',3500);}
function age(time){let sec=Math.max(0,Math.floor((Date.now()-time)/1000));return sec<60?'just now':sec<3600?`${Math.floor(sec/60)}m ago`:`${Math.floor(sec/3600)}h ago`;}
function paint(){
 if(stackAnimating||panelClosing||document.body.classList.contains('dragging'))return;
 const waiting=data.sessions.filter(s=>s.status==='waiting').length,busy=data.sessions.filter(s=>s.status==='working').length;
 const state=waiting?'waiting':busy?'working':data.sessions.some(s=>s.status==='error')?'error':data.sessions.some(s=>s.status==='done'&&Date.now()-s.time<30000)?'done':data.sessions.some(s=>s.status==='unknown')?'unknown':'idle';
 document.body.classList.remove('working','waiting','error','done','idle','unknown');document.body.classList.add(state);petAnimationState=state;updatePetSprite();
 paintUsage();
 const scrollTop=$('cards').scrollTop;
 let sessions=visibleTasks();const frontIndex=sessions.findIndex(s=>taskKey(s)===frontTaskKey);if(frontIndex>0)sessions=[...sessions.slice(frontIndex),...sessions.slice(0,frontIndex)];$('badge').textContent=sessions.length;$('badge').hidden=!sessions.length;document.body.classList.toggle('has-tasks',sessions.length>0);$('cards').replaceChildren();
 if(!sessions.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No tasks yet';const small=document.createElement('small');small.textContent='Run an agent task to see it here. Hooks connect Claude and Antigravity.';empty.append(small);$('cards').append(empty);}
 for(const session of sessions){const card=document.createElement('div');card.tabIndex=0;card.setAttribute('role','button');card.className='card '+(session.provider==='claude'?'claude':session.provider==='antigravity'?'agy':session.provider==='codex-cli'?'codex-cli':'codex-desktop');const top=document.createElement('div');top.className='card-top';const brand=document.createElement('span');brand.className='brand';brand.textContent=names[session.provider];const status=document.createElement('span');status.className='state '+session.status;status.textContent=session.status==='unknown'?'status stale':session.status;top.append(brand,status);const title=document.createElement('div');title.className='card-title';title.textContent=session.title;const meta=document.createElement('div');meta.className='meta';meta.textContent=`${age(session.time)} · ${session.workspace||'Local session'}`;card.title=session.workspace;const activity=document.createElement('div');activity.className='task-activity';activity.textContent=session.activity||'Working on task';const dismiss=document.createElement('button');dismiss.className='dismiss-task';dismiss.type='button';dismiss.textContent='×';dismiss.setAttribute('aria-label','Dismiss '+session.title);dismiss.onclick=e=>{e.stopPropagation();dismissTask(session);};card.append(top,title,activity,meta,dismiss);card.onkeydown=e=>{if(e.target===card&&(e.key==='Enter'||e.key===' ')){e.preventDefault();card.click();}};card.onclick=async()=>{if(!stackExpanded){stackExpanded=true;expand(true);return;}if(!await window.orbit.focus(session.provider))toast('Open the agent’s app or terminal to jump to it.');};$('cards').append(card);}
 $('cards').scrollTop=scrollTop;
}
window.orbit.onState(state=>{data=state;if(open&&!chatOpen&&!usageOpen&&!settingsOpen)acknowledge();paint();requestAnimationFrame(reportRegions);});window.orbit.ready();paint();
let pointer=null,raf=null;
$('pet').addEventListener('pointerdown',e=>{if(e.button!==0)return;const rect=$('pet').getBoundingClientRect();pointer={id:e.pointerId,x:e.screenX,y:e.screenY,travelX:0,travelY:0,direction:new DragDirection(0,petDirection),moved:false};$('pet').setPointerCapture(e.pointerId);document.body.classList.add('dragging');window.orbit.drag('start',e.screenX,e.screenY,{x:e.clientX-rect.left,y:e.clientY-rect.top});});
$('pet').addEventListener('pointermove',e=>{
 if(!pointer)return;
 // Browser motion only requests a sample; native absolute coordinates drive the drag.
 if(Math.hypot(e.screenX-pointer.x,e.screenY-pointer.y)>4)pointer.moved=true;
 if(!raf)raf=requestAnimationFrame(()=>{raf=null;if(pointer)window.orbit.drag('move',0,0);});
});
function end(e){if(!pointer)return;const click=!pointer.moved&&e.type!=='pointercancel';if(raf){cancelAnimationFrame(raf);raf=null;}window.orbit.drag('end',e.screenX,e.screenY);pointer=null;petWalking=false;document.body.classList.remove('dragging');paint();if(click)toggleToolbar();}
$('pet').addEventListener('pointerup',end);$('pet').addEventListener('pointercancel',end);$('pet').addEventListener('lostpointercapture',e=>{if(pointer)end({...e,type:'pointercancel'});});$('pet').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleToolbar();}});document.addEventListener('keydown',e=>{if(e.key==='Escape')expand(false);});

function fitContent(){
 const pet=$('pet').getBoundingClientRect();const available=Math.max(90,document.body.classList.contains('above')?pet.top-64:innerHeight-pet.bottom-64);document.body.style.setProperty('--panel-room',available+'px');
 const cards=$('cards');if(open&&!chatOpen&&!usageOpen&&!settingsOpen&&!stackExpanded){const first=cards.querySelector('.card');cards.style.setProperty('--stack-card-height',(first?.offsetHeight||58)+'px');cards.style.height=first?Math.min(first.offsetHeight+24,Math.max(100,innerHeight-cards.getBoundingClientRect().top-18))+'px':'82px';}else cards.style.height='';
 $('composer').style.minHeight='';
 for(const menu of [$('harness-menu'),$('projects'),$('settings-menu')])if(!menu.hidden&&menu._anchor){
  const anchor=menu._anchor.getBoundingClientRect();const width=menu.id==='settings-menu'?190:Math.min(310,innerWidth-16);
  menu.style.width=width+'px';menu.style.left=Math.max(8,Math.min(anchor.right-width,innerWidth-width-8))+'px';menu.style.right='auto';
  const availableBelow=innerHeight-anchor.bottom-12;const height=Math.min(menu.scrollHeight,menu.id==='harness-menu'?190:170);
  menu.style.maxHeight=Math.min(170,Math.max(80,Math.max(availableBelow,anchor.top-12)))+'px';
  menu.style.top=(availableBelow>=height?anchor.bottom+5:Math.max(8,anchor.top-height-5))+'px';
 }
}
function reportRegions(){
 fitContent();
 const ids=['pet'];if(toolbarPinned)ids.push('toolbar');if(open)ids.push(chatOpen?'composer':usageOpen?'usage-panel':settingsOpen?'settings-panel':'cards');if(open&&chatOpen&&!$('harness-menu').hidden)ids.push('harness-menu');if(open&&chatOpen&&!$('projects').hidden)ids.push('projects');if(open&&settingsOpen&&!$('settings-menu').hidden)ids.push('settings-menu');if(!$('pet-menu').hidden)ids.push('pet-menu');
 window.orbit.hitRegions(ids.map(id=>{const r=$(id).getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};}));
}
new ResizeObserver(reportRegions).observe($('shell'));requestAnimationFrame(reportRegions);

window.orbit.onLayout(layout=>{
 if(pointer&&layout.dragMotion){const motion=layout.dragMotion;pointer.travelX=motion.x;pointer.travelY=motion.y;const direction=pointer.direction.update(motion.x,motion.time,motion.y);if(direction!==petDirection){petDirection=direction;if(petWalking)applySpriteDirection();}if(!petWalking&&motion.moved){pointer.moved=true;petWalking=true;updatePetSprite();}}
 document.body.style.setProperty('--pet-x',layout.petX+'px');document.body.style.setProperty('--pet-y',layout.petY+'px');document.body.classList.toggle('above',layout.above);requestAnimationFrame(reportRegions);
});
let toolbarPinned=false;
function toggleToolbar(){toolbarPinned=!toolbarPinned;document.body.classList.toggle('toolbar-expanded',toolbarPinned);if(!toolbarPinned&&open)expand(false);requestAnimationFrame(reportRegions);}
let hoverTimer;for(const id of ['pet','toolbar']){$(id).addEventListener('pointerenter',()=>{clearTimeout(hoverTimer);document.body.classList.add('controls-visible');});$(id).addEventListener('pointerleave',()=>{clearTimeout(hoverTimer);hoverTimer=setTimeout(()=>document.body.classList.remove('controls-visible'),settings.hoverDelay);});}

$('prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('submit-task').disabled)$('composer').requestSubmit();}});
$('cards').tabIndex=0;
async function cycleNotification(direction){
 if(stackAnimating)return;
 const tasks=visibleTasks();if(tasks.length<2)return;
 const index=Math.max(0,tasks.findIndex(s=>taskKey(s)===frontTaskKey));
 const old=$('cards').querySelector('.card');const oldHeight=old?.offsetHeight||58;
 const ghost=old?.cloneNode(true);if(ghost){ghost.classList.add('stack-ghost');ghost.tabIndex=-1;ghost.setAttribute('aria-hidden','true');}
 frontTaskKey=taskKey(tasks[(index+direction+tasks.length)%tasks.length]);paint();fitContent();
 if(matchMedia('(prefers-reduced-motion: reduce)').matches||!settings.animations){reportRegions();return;}
 const cards=$('cards'),front=cards.querySelector('.card');if(!front)return;
 cards.style.height=Math.min(Math.max(oldHeight,front.offsetHeight)+24,innerHeight-cards.getBoundingClientRect().top-18)+'px';
 stackAnimating=true;
 const animations=[];const easing='cubic-bezier(.22,.75,.25,1)';
 if(ghost){cards.append(ghost);animations.push(ghost.animate([{transform:'translateY(0) scale(1)',opacity:1},{transform:`translateY(${-direction*22}px) scale(.94)`,opacity:0}],{duration:240,easing,fill:'forwards'}).finished);}
 animations.push(front.animate([{transform:`translateY(${direction*16}px) scale(.95)`,opacity:.3},{transform:'translateY(0) scale(1)',opacity:1}],{duration:360,easing,fill:'both'}).finished);
 for(const card of [...cards.querySelectorAll('.card:not(.stack-ghost)')].slice(1,3))animations.push(card.animate([{transform:'translateY(7px) scale(.97)'},{transform:'translateY(0) scale(1)'}],{duration:360,easing}).finished);
 try{await Promise.allSettled(animations);}finally{ghost?.remove();stackAnimating=false;paint();reportRegions();}
}
$('cards').addEventListener('wheel',e=>{if(stackExpanded||!open||chatOpen||usageOpen)return;e.preventDefault();if(!e.deltaY||stackAnimating||Date.now()-lastStackScroll<180)return;lastStackScroll=Date.now();cycleNotification(e.deltaY>0?1:-1);},{passive:false});

function paintUsage(){
 const signature=JSON.stringify([data.usage,data.usageStatus]);if(signature===usageSignature)return;usageSignature=signature;
 const panel=$('usage-panel'),scroll=panel.scrollTop;panel.replaceChildren();
 for(const [key,name,color] of [['claude','Claude','claude'],['codex','Codex','codex-desktop'],['antigravity','AGY','agy']]){
  const snapshot=data.usage?.[key],status=data.usageStatus?.[key];
  const card=document.createElement('div');card.className='usage-card '+color;
  const heading=document.createElement('div');heading.className='usage-name';heading.textContent=name;
  if(status==='refreshing'||status==='failed'){const indicator=document.createElement('span');indicator.className='usage-indicator';indicator.textContent=status==='refreshing'?'↻':'!';indicator.title=status==='refreshing'?'Refreshing quota':'Refresh failed; showing previous values';heading.append(indicator);}card.append(heading);
  if(!snapshot){const note=document.createElement('span');note.className='usage-note';note.textContent=status==='refreshing'?'Loading…':'Unavailable';card.append(note);}
  else for(const window of snapshot.windows){
   const row=document.createElement('div');row.className='usage-row';const label=document.createElement('span');
   label.textContent=window.label.replace(/^(gemini|3p)-(5h|weekly)$/,(match,group,period)=>(group==='gemini'?'Gemini':'Claude / GPT')+' · '+(period==='weekly'?'Week':'5h')).replace(/Gemini Models/g,'Gemini').replace(/Claude and GPT models/g,'Claude / GPT').replace(/Five Hour Limit Remaining/g,'5h').replace(/Weekly Limit Remaining/g,'Week').replace(/^Session$/,'5h').replace(/^Weekly$/,'Week');
   const amount=document.createElement('strong');const expired=window.reset&&window.reset<=Date.now();amount.textContent=expired?'—':window.remaining+'%';row.append(label,amount);
   if(window.reset)row.title='Resets '+new Date(window.reset).toLocaleString();
   const meter=document.createElement('progress');meter.max=100;meter.value=expired?0:window.remaining;meter.setAttribute('aria-label',label.textContent+' quota remaining');card.append(row,meter);
  }
  panel.append(card);
 }
 panel.scrollTop=scroll;
}

function applySettings(){const scale=settings.petScale||1;document.body.style.setProperty('--pet-scale',scale);document.body.style.setProperty('--pet-body',settings.bodyColor||'#90bbb7');document.body.style.setProperty('--pet-body-light','color-mix(in srgb, '+(settings.bodyColor||'#90bbb7')+' 40%, white)');document.body.style.setProperty('--pet-accent',settings.accentColor||'#8ce8cf');document.body.classList.remove('face-friendly','face-focused','face-sleepy');document.body.classList.add('face-'+(settings.face||'friendly'));$('pet').setAttribute('aria-label','Drag '+(settings.petName||'Orbit')+' or click to toggle controls');document.querySelector('.mouth').setAttribute('d',settings.face==='focused'?'M68 79H82':settings.face==='sleepy'?'M71 79H79':'M67 77Q75 83 83 77');document.body.classList.toggle('paused',!settings.animations);if(settings.controls!==document.body.classList.contains('always-controls')){toolbarPinned=!!settings.controls;document.body.classList.toggle('toolbar-expanded',toolbarPinned);}document.body.classList.toggle('always-controls',settings.controls);updatePetSprite();}
function saveSettings(){localStorage.setItem('orbit-settings',JSON.stringify(settings));applySettings();paint();requestAnimationFrame(reportRegions);}
function showSettings(){settingsOpen=true;chatOpen=false;usageOpen=false;stackExpanded=true;$('setting-animations').checked=settings.animations;$('setting-controls').checked=settings.controls;$('setting-hover').value=String(settings.hoverDelay);$('setting-completions').value=String(settings.completionMinutes);$('setting-harness').value=settings.harness;syncSettingDropdowns();expand(true);}
$('pet').addEventListener('contextmenu',e=>{e.preventDefault();closeMenus();const menu=$('pet-menu');menu.style.left=Math.max(8,Math.min(e.clientX,innerWidth-168))+'px';menu.style.top=Math.max(8,Math.min(e.clientY,innerHeight-90))+'px';animateVisible(menu,true);requestAnimationFrame(reportRegions);});
$('pet-hide').onclick=()=>{closeMenus();window.orbit.hide();};$('pet-settings').onclick=()=>{closeMenus();window.orbit.openSettings();};

$('setting-animations').onchange=e=>{settings.animations=e.target.checked;saveSettings();};
$('setting-controls').onchange=e=>{settings.controls=e.target.checked;saveSettings();};
$('setting-hover').onchange=e=>{settings.hoverDelay=Number(e.target.value);saveSettings();};
$('setting-completions').onchange=e=>{settings.completionMinutes=Number(e.target.value);saveSettings();};
$('setting-harness').onchange=e=>{settings.harness=e.target.value;localStorage.setItem('orbit-harness',settings.harness);$('harness').value=settings.harness;chooseHarness();saveSettings();};
$('setting-position').onclick=()=>window.orbit.resetPosition();$('settings-done').onclick=()=>expand(false);
applySettings();

document.addEventListener('pointerdown',e=>{if(!e.target.closest('#harness-menu,#projects,#settings-menu,#pet-menu,#harness-toggle,#thread-toggle,.setting-dropdown')){for(const id of ['harness-menu','projects','settings-menu','pet-menu'])if(wantedVisible($(id)))animateVisible($(id),false);$('harness-toggle').setAttribute('aria-expanded','false');$('thread-toggle').setAttribute('aria-expanded','false');}});

const settingDropdowns=[];
for(const select of document.querySelectorAll('.setting-row select')){
 const button=document.createElement('button');button.type='button';button.className='setting-dropdown';select.hidden=true;select.after(button);settingDropdowns.push({select,button});
 button.onclick=()=>{const menu=$('settings-menu');const close=wantedVisible(menu)&&menu._anchor===button;closeMenus();if(close)return;menu._anchor=button;menu.replaceChildren();for(const option of select.options){const choice=document.createElement('button');choice.type='button';choice.textContent=option.textContent;choice.className=option.value===select.value?'selected':'';choice.onclick=()=>{select.value=option.value;select.dispatchEvent(new Event('change'));syncSettingDropdowns();animateVisible(menu,false);};menu.append(choice);}animateVisible(menu,true);requestAnimationFrame(reportRegions);};
}
function syncSettingDropdowns(){for(const {select,button} of settingDropdowns)button.textContent=(select.selectedOptions[0]?.textContent||'Choose')+' ▾';}
syncSettingDropdowns();

window.orbit.onPreferences(value=>{const harnessChanged=settings.harness!==value.harness;settings=value;localStorage.setItem('orbit-settings',JSON.stringify(settings));if(harnessChanged){$('harness').value=settings.harness;chooseHarness();if(chatOpen)loadProjects();}applySettings();paint();requestAnimationFrame(reportRegions);});
window.orbit.initializeSettings(settings);

window.addEventListener('resize',()=>window.orbit.viewport());setTimeout(()=>window.orbit.viewport(),500);
