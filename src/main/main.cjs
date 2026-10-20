const {app,BrowserWindow,ipcMain,screen,Menu,Tray,nativeImage,clipboard,dialog}=require('electron');
const fs=require('node:fs'),path=require('node:path');const {execFile,execFileSync,spawn}=require('node:child_process');
const {normalizeSettings}=require('./settings.cjs');
const {bundledPets}=require('./bundled-pets.cjs');
const {createHyprInputPolicy}=require('./hypr-input.cjs');
const {desktopMessageUrl}=require('./desktop-route.cjs');
const {sendDesktopMessage}=require('./desktop-ipc.cjs');
const {terminalHasThread}=require('./terminal-thread.cjs');
const {inactiveQueueError}=require('./resume-policy.cjs');
const {placePet}=require('./geometry.cjs');
const {createCursorReader,toScreenPoint}=require('./drag-cursor.cjs');
const {createPetRunner}=require('./pet-runner.cjs');
const {createFleaQueue}=require('./flea-queue.cjs');
const {createFleaMarker}=require('./flea-marker.cjs');
const {createRandomFleas}=require('./random-fleas.cjs');
const {listenForSummon}=require('./summon-control.cjs');
const {Store,PROVIDERS}=require('./store.cjs');const {Activity}=require('./activity.cjs');
const {agyUsage,codexUsage}=require('./fresh-usage.cjs');
const {claudeUsage}=require('./claude-usage.cjs');
app.setName('Orbit Agent Pet');app.commandLine.appendSwitch('class','agent-pet');
if(!app.requestSingleInstanceLock())app.quit();
let canvasHeight=null,startupAnchor=null;let win,settingsWin,tray,timer,usageTimer,pointerTimer,drag=null,expanded=false,hitRegions=[],ignoring=false;const store=new Store();let activity,layout={petX:112,petY:0,above:false};
const sizes={closed:{width:160,height:158},open:{width:374,height:630}};
const stateDir=path.join(process.env.XDG_STATE_HOME||path.join(app.getPath('home'),'.local','state'),'agent-pet');
const settingsFile=path.join(stateDir,'settings.json');let preferences=null;
try{preferences=normalizeSettings(JSON.parse(fs.readFileSync(settingsFile,'utf8')));}catch{}
if(!preferences)preferences=normalizeSettings({spritePets:bundledPets()});
function persistPreferences(value){
 const old=preferences;const oldScale=old?.petScale||1;const before=win&&!win.isDestroyed()?win.getBounds():null;
 preferences=normalizeSettings(value);fs.mkdirSync(stateDir,{recursive:true});fs.writeFileSync(settingsFile,JSON.stringify(preferences,null,2),{mode:0o600});win?.webContents.send('settings-changed',preferences);tray?.setToolTip(preferences.petName+' · your agent companion');
 if(before&&oldScale!==preferences.petScale){movePet(before.x+layout.petX+75*(oldScale-preferences.petScale),before.y+layout.petY+64.5*(oldScale-preferences.petScale));save();}
 return preferences;
}
function showSettingsWindow(){
 if(settingsWin&&!settingsWin.isDestroyed()){settingsWin.show();settingsWin.focus();return;}
 settingsWin=new BrowserWindow({title:'Orbit Settings',width:500,height:610,minWidth:420,minHeight:480,parent:win,show:false,backgroundColor:'#1e1c21',webPreferences:{preload:path.join(__dirname,'settings-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 settingsWin.setAlwaysOnTop(true,'floating');settingsWin.loadFile(path.join(__dirname,'../renderer/settings.html'));settingsWin.once('ready-to-show',()=>{settingsWin.show();settingsWin.focus();});settingsWin.on('closed',()=>settingsWin=null);settingsWin.webContents.setWindowOpenHandler(()=>({action:'deny'}));
}
function save(){if(!win||win.isDestroyed())return;try{fs.mkdirSync(stateDir,{recursive:true});const b=win.getBounds();fs.writeFileSync(path.join(stateDir,'position.json'),JSON.stringify({x:b.x+layout.petX,y:b.y+layout.petY}));}catch{}}
function movePet(x,y,dragMotion){
 const area=screen.getDisplayNearestPoint({x,y}).workArea;
 const bounds=win.getBounds();const height=Math.min(bounds.height,canvasHeight||bounds.height);const placed=placePet(x,y,area,bounds.width,height,preferences?.petScale||1);
 layout=placed;if(bounds.x!==placed.x||bounds.y!==placed.y)win.setPosition(placed.x,placed.y,false);win.webContents.send('layout',{...layout,...(dragMotion?{dragMotion}:{})});
}
let summonControl=null;
const petRunner=createPetRunner({
 getSpeed:()=>preferences?.movementSpeed||700,
 getPosition(){const b=win.getBounds();return {x:b.x+layout.petX,y:b.y+layout.petY};},
 move(x,y){if(win&&!win.isDestroyed())movePet(x,y);},
 onStart({direction}){win.webContents.send('run-state',{walking:true,direction});},
 onEnd({cancelled}){if(win&&!win.isDestroyed()){win.webContents.send('run-state',{walking:false});if(!cancelled){save();fleaQueue.complete();}}}
});
const fleaQueue=createFleaQueue({
 createMarker:point=>createFleaMarker(point,stateDir),
 removeMarker:marker=>{if(!marker.isDestroyed())marker.destroy();},
 getDestination(cursor){
  const scale=preferences?.petScale||1,bounds=win.getBounds(),area=screen.getDisplayNearestPoint(cursor).workArea;
  const destination=placePet(cursor.x-75*scale,cursor.y-64.5*scale,area,bounds.width,Math.min(bounds.height,canvasHeight||bounds.height),scale);
  return{x:destination.x+destination.petX,y:destination.y+destination.petY};
 },
 run:point=>petRunner.run(point),stop:()=>petRunner.stop()
});
const randomFleas=createRandomFleas({
 spawn:point=>fleaQueue.add(point),
 canSpawn:()=>win&&!win.isDestroyed()&&win.isVisible()&&!drag&&!expanded&&fleaQueue.count===0,
 getArea(){const b=win.getBounds();return screen.getDisplayNearestPoint({x:b.x+layout.petX,y:b.y+layout.petY}).workArea;},
 getMargin:()=>({x:Math.max(40,75*(preferences?.petScale||1)),y:Math.max(40,64.5*(preferences?.petScale||1))})
});
function summonPet(point){
 if(!win||win.isDestroyed()||drag)return;
 const cursor=toScreenPoint(point,hyprMonitors,screen.getAllDisplays());
 win.showInactive();if(!fleaQueue.add(cursor))throw Error('Flea queue full');
}
let quotaRefresh=null;
function refreshUsage(){
 if(quotaRefresh)return quotaRefresh;
 store.usageStatus={codex:'refreshing',antigravity:'refreshing',claude:'refreshing'};send();
 quotaRefresh=Promise.allSettled([['codex',codexUsage],['antigravity',agyUsage],['claude',claudeUsage]].map(async([provider,read])=>{try{store.usage[provider]=await read();store.usageStatus[provider]='live';}catch{store.usageStatus[provider]='failed';}send();})).finally(()=>quotaRefresh=null);return quotaRefresh;
}
function send(){if(win&&!win.isDestroyed())win.webContents.send('state',store.snapshot());}
let inputShape=null,inputShapeReady=false,hyprInput=null;
function shape(){if(inputShapeReady&&inputShape?.stdin.writable)inputShape.stdin.write(JSON.stringify(hitRegions)+'\n');if(win&&!win.isDestroyed())hyprInput?.update({regions:hitRegions,width:win.getBounds().width,height:canvasHeight||win.getBounds().height,drag:!!drag});}
function startInputShape(){
 if(!process.env.DISPLAY)return;
 const handle=win.getNativeWindowHandle();const id=handle.readUInt32LE(0);
 inputShape=spawn('python3',[path.join(__dirname,'../../scripts/input-shape.py'),String(id)],{stdio:['pipe','pipe','pipe']});
 inputShape.stdin.on('error',()=>{});
 inputShape.stdout.once('data',()=>{if(!win||win.isDestroyed())return;win.setIgnoreMouseEvents(false);ignoring=false;inputShapeReady=true;shape();});
 inputShape.on('error',()=>{inputShapeReady=false;});inputShape.on('exit',()=>{inputShapeReady=false;});
}
let pointerQuery=false,hyprMonitors=[];
const readDragCursor=createCursorReader({getMonitors:()=>hyprMonitors,getDisplays:()=>screen.getAllDisplays(),fallback:()=>screen.getCursorScreenPoint()});
let dragTimer=null,dragRead=null;
function sampleDrag(){
 if(!drag)return Promise.resolve();if(dragRead)return dragRead;const active=drag;
 dragRead=readDragCursor().then(cursor=>{
  if(drag!==active||!win||win.isDestroyed())return;
  const x=cursor.x-active.x,y=cursor.y-active.y;
  if(Math.hypot(x,y)>4)active.moved=true;
  if(!active.moved||active.lastX===cursor.x&&active.lastY===cursor.y)return;
  active.lastX=cursor.x;active.lastY=cursor.y;
  movePet(cursor.x-active.grabX,cursor.y-active.grabY,{x,y,time:Date.now(),moved:true});
 }).catch(()=>{}).finally(()=>{dragRead=null;});return dragRead;
}
function applyPointerPolicy(cursor){
 if(!win||win.isDestroyed())return;
 const bounds=win.getBounds(),x=cursor.x-bounds.x,y=cursor.y-bounds.y;
 const interactive=!!drag||hitRegions.some(r=>x>=r.x&&y>=r.y&&x<r.x+r.width&&y<r.y+r.height);
 if(ignoring===interactive){ignoring=!interactive;win.setIgnoreMouseEvents(ignoring,{forward:true});}
}
function pointerPolicy(){
 if(!win||win.isDestroyed()||inputShapeReady||pointerQuery||drag)return;
 if(!process.env.HYPRLAND_INSTANCE_SIGNATURE)return applyPointerPolicy(screen.getCursorScreenPoint());
 pointerQuery=true;
 execFile('hyprctl',['cursorpos'],{timeout:500},(err,out)=>{
  pointerQuery=false;if(err||inputShapeReady)return;
  const match=out.match(/(-?[\d.]+),\s*(-?[\d.]+)/);if(!match)return;
  const x=Number(match[1]),y=Number(match[2]);
  const monitor=hyprMonitors.find(m=>x>=m.x&&y>=m.y&&x<m.x+m.width/m.scale&&y<m.y+m.height/m.scale);
  const scale=monitor?.scale||1;
  applyPointerPolicy({x:x*scale,y:y*scale});
 });
}
app.whenReady().then(()=>{
 let position={x:screen.getPrimaryDisplay().workArea.width-200,y:screen.getPrimaryDisplay().workArea.height-200};try{position=JSON.parse(fs.readFileSync(path.join(stateDir,'position.json'),'utf8'));}catch{}
 if(!Number.isFinite(position.x)||!Number.isFinite(position.y))position={x:100,y:100};
 startupAnchor={...position};const workArea=screen.getDisplayNearestPoint(position).workArea;const placed=placePet(position.x,position.y,workArea,374,workArea.height,preferences?.petScale||1);layout=placed;
 win=new BrowserWindow({title:'Orbit Agent Pet',...sizes.open,height:workArea.height,x:placed.x,y:placed.y,frame:false,transparent:true,backgroundColor:'#00000000',hasShadow:false,resizable:true,maximizable:false,minimizable:false,skipTaskbar:true,alwaysOnTop:true,show:false,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 win.setVisibleOnAllWorkspaces(true,{visibleOnFullScreen:true});win.setAlwaysOnTop(true,'floating');win.on('page-title-updated',e=>e.preventDefault());win.webContents.setWindowOpenHandler(()=>({action:'deny'}));win.webContents.on('will-navigate',e=>e.preventDefault());
 hyprInput=createHyprInputPolicy(process.pid);
 summonControl=listenForSummon(summonPet);
 win.loadFile(path.join(__dirname,'../renderer/index.html'));win.once('ready-to-show',()=>{startInputShape();win.showInactive();randomFleas.start();});
 win.setIgnoreMouseEvents(true,{forward:true});ignoring=true;execFile('hyprctl',['monitors','-j'],{timeout:1000},(err,out)=>{if(!err)try{hyprMonitors=JSON.parse(out);}catch{}});pointerTimer=setInterval(pointerPolicy,60);
 activity=new Activity(store,stateDir);activity.poll();refreshUsage();usageTimer=setInterval(refreshUsage,5*60000);timer=setInterval(()=>{activity.poll();send();},1000);
 const icon=nativeImage.createFromPath(path.join(__dirname,'../../assets/icons/tray.png'));if(!icon.isEmpty()){tray=new Tray(icon);tray.setToolTip('Orbit · your agent companion');tray.setContextMenu(Menu.buildFromTemplate([{label:'Show companion',click:()=>win.show()},{label:'Hide companion',click:()=>{fleaQueue.clear();win.hide();}},{type:'separator'},{label:'Quit Orbit',click:()=>app.quit()}]));tray.on('click',()=>{if(win.isVisible()){fleaQueue.clear();win.hide();}else win.show();});}
});
ipcMain.on('ready',(_,viewport)=>{if(Number.isFinite(viewport?.height)&&viewport.height>0)canvasHeight=viewport.height;if(startupAnchor){const bounds=win.getBounds();layout.petY=startupAnchor.y-bounds.y;startupAnchor=null;}layout.petY=Math.max(0,Math.min(layout.petY,(canvasHeight||win.getBounds().height)-129*(preferences?.petScale||1)));send();win.webContents.send('layout',layout);});
ipcMain.on('pet-viewport',(_,viewport)=>{if(!Number.isFinite(viewport?.height)||viewport.height<=0)return;canvasHeight=viewport.height;if(startupAnchor){const bounds=win.getBounds();layout.petY=startupAnchor.y-bounds.y;startupAnchor=null;}layout.petY=Math.max(0,Math.min(layout.petY,canvasHeight-129*(preferences?.petScale||1)));win.webContents.send('layout',layout);save();});
ipcMain.on('hit-regions',(_,regions)=>{if(!Array.isArray(regions))return;hitRegions=regions.filter(r=>[r.x,r.y,r.width,r.height].every(Number.isFinite)&&r.width>0&&r.height>0).slice(0,16);shape();pointerPolicy();});
ipcMain.on('expand',(_,open)=>{if(drag||!win)return;expanded=open;pointerPolicy();shape();win.webContents.invalidate();if(open)win.focus();});
ipcMain.on('drag',(_,e)=>{
 if(!win||!['start','move','end'].includes(e.phase))return;
 if(e.phase==='start'){
  fleaQueue.clear();
  if(!Number.isFinite(e.x)||!Number.isFinite(e.y))return;
  if(!inputShapeReady)win.setIgnoreMouseEvents(false);ignoring=false;const b=win.getBounds();
  const grabX=Number.isFinite(e.grab?.x)?e.grab.x:e.x-b.x-layout.petX,grabY=Number.isFinite(e.grab?.y)?e.grab.y:e.y-b.y-layout.petY;
  drag={x:b.x+layout.petX+grabX,y:b.y+layout.petY+grabY,grabX,grabY,moved:false};clearInterval(dragTimer);dragTimer=setInterval(sampleDrag,8);shape();sampleDrag();
 }else if(e.phase==='move'&&drag){sampleDrag();}
 else if(e.phase==='end'&&drag){
  clearInterval(dragTimer);dragTimer=null;const active=drag;
  Promise.resolve(dragRead).then(()=>drag===active?sampleDrag():null).finally(()=>{if(drag!==active)return;drag=null;shape();save();});
 }
});
ipcMain.handle('focus-agent',(_,provider)=>new Promise(resolve=>{
 if(!PROVIDERS.includes(provider))return resolve(false);
 execFile('hyprctl',['clients','-j'],{timeout:2000},(err,out)=>{if(err)return resolve(false);let clients;try{clients=JSON.parse(out);}catch{return resolve(false);}const target=clients.find(c=>provider==='codex-desktop'?/^(Chatgpt|codex-desktop)$/i.test(c.class)&&!c.floating:provider==='antigravity'?/antigravity/i.test(c.class):/kitty|alacritty|foot|wezterm/i.test(c.class)&&new RegExp(provider==='claude'?'claude':'codex','i').test(c.title));if(!target)return resolve(false);const address=JSON.stringify(target.address);execFile('hyprctl',['eval',`for _,w in ipairs(hl.get_windows()) do if w.address == ${address} then hl.dispatch(hl.dsp.focus({window=w})) end end`],{timeout:2000},err=>resolve(!err));});
}));
async function openThreads(provider){
 if(!PROVIDERS.includes(provider))return [];
 let threads=await new Promise(resolve=>execFile('python3',[path.join(__dirname,'../../scripts/threads.py'),provider],{timeout:5000,maxBuffer:1024*1024},(error,out)=>{try{const result=JSON.parse(out);resolve(!error&&Array.isArray(result)?result:[]);}catch{resolve([]);}}));
 threads=threads.filter(t=>t&&typeof t.id==='string'&&typeof t.name==='string');
 for(const session of store.snapshot().sessions)if(session.provider===provider&&!threads.some(t=>t.id===session.session))threads.push({id:session.session,name:session.title,path:session.workspace});
 return threads;
}
ipcMain.handle('projects',(_,provider)=>openThreads(provider));
function threadIsInTerminal(thread){
 let windows=[];try{windows=JSON.parse(execFileSync('hyprctl',['clients','-j'],{timeout:2000,encoding:'utf8'}));}catch{}
 const processes=[];try{for(const pid of fs.readdirSync('/proc'))if(/^\d+$/.test(pid)){try{const dir='/proc/'+pid;const status=fs.readFileSync(dir+'/status','utf8');let tty=false;try{tty=/^\/dev\/(pts\/|tty)/.test(fs.readlinkSync(dir+'/fd/0'));}catch{}processes.push({pid:Number(pid),ppid:Number(status.match(/^PPid:\s*(\d+)/m)?.[1]),name:fs.readFileSync(dir+'/comm','utf8').trim(),args:fs.readFileSync(dir+'/cmdline','utf8').split('\0'),tty});}catch{}}}catch{}
 return terminalHasThread(thread,windows,processes);
}
ipcMain.handle('start-task',async(_,{provider,prompt,thread}={})=>{
 if(!PROVIDERS.includes(provider)||typeof prompt!=='string'||!prompt.trim()||prompt.length>12000)return{ok:false,message:'Enter a message and choose a harness'};
 const selected=(await openThreads(provider)).find(t=>t.id===thread);if(!selected)return{ok:false,message:'Choose a conversation before sending'};
 if(provider==='codex-desktop'){
  const desktop=process.env.ORBIT_CODEX_DESKTOP||['codex-desktop','chatgpt'].flatMap(name=>(process.env.PATH||'').split(path.delimiter).map(dir=>path.join(dir,name))).find(file=>{try{fs.accessSync(file,fs.constants.X_OK);return true;}catch{return false;}});
  if(!desktop)return{ok:false,message:'Codex Desktop launcher is unavailable'};
  const url=new URL(desktopMessageUrl(selected.id,''));url.searchParams.delete('prompt');
  try{await new Promise((resolve,reject)=>{const child=spawn(desktop,[url.href],{detached:true,stdio:'ignore'});child.once('error',reject);child.once('spawn',()=>{child.unref();resolve();});});await sendDesktopMessage(selected.id,prompt);return{ok:true,message:'Sent to '+selected.name+' in Desktop'};}catch(error){return{ok:false,message:error.message||'Desktop could not accept the message'};}

 }
 const name=provider.startsWith('codex-')?'codex':provider==='claude'?'claude':'agy';
 const executable=process.env.PATH.split(path.delimiter).map(dir=>path.join(dir,name)).find(file=>{try{fs.accessSync(file,fs.constants.X_OK);return true;}catch{return false;}});
 if(!executable)return{ok:false,message:name+' is not installed or is missing from PATH'};
 let cwd=selected.path;try{if(!fs.statSync(cwd).isDirectory())cwd=app.getPath('home');}catch{cwd=app.getPath('home');}
 let args;
 if(provider==='codex-cli'){
  if(threadIsInTerminal(selected)){
  const queued=await new Promise(resolve=>execFile(executable,['queue','--thread',selected.id,'--message',prompt],{cwd,timeout:30000,maxBuffer:1024*1024},(error,out,stderr)=>resolve({error,text:stderr||out||error?.message||''})));
  if(!queued.error)return{ok:true,message:'Message queued for '+selected.name};
  if(!inactiveQueueError(queued.error,queued.text))return{ok:false,message:('Could not queue message: '+queued.text).slice(0,300)};
  }
  const terminal=process.env.PATH.split(path.delimiter).map(dir=>path.join(dir,'kitty')).find(file=>{try{fs.accessSync(file,fs.constants.X_OK);return true;}catch{return false;}});
  if(!terminal)return{ok:false,message:'Install kitty to reopen this conversation'};
  return new Promise(resolve=>{const child=spawn(terminal,['--directory',cwd,'--title',selected.name,executable,'resume',selected.id,prompt],{cwd,detached:true,stdio:'ignore'});child.once('error',()=>resolve({ok:false,message:'Could not reopen '+selected.name}));child.once('spawn',()=>{child.unref();resolve({ok:true,message:'Opened '+selected.name+' in a terminal'});});});
 }else args=provider==='claude'?['--resume',selected.id,'--print',prompt]:['--conversation',selected.id,...(selected.project?['--project',String(selected.project)]:[]),'--print',prompt];
 return new Promise(resolve=>{
  const child=spawn(executable,args,{cwd,stdio:['ignore','pipe','pipe']});let output='',errorText='';
  child.stdout.on('data',chunk=>{output=(output+chunk.toString()).slice(-16000);});child.stderr.on('data',chunk=>{errorText=(errorText+chunk.toString()).slice(-1000);});
  child.once('error',()=>resolve({ok:false,message:'Could not resume '+selected.name}));
  child.once('spawn',()=>{store.update({provider,session:selected.id,title:selected.name,workspace:cwd,status:'working',time:Date.now(),activity:'Continuing conversation'});send();resolve({ok:true,message:'Continuing '+selected.name});});
  child.once('close',code=>{store.update({provider,session:selected.id,title:selected.name,workspace:cwd,status:code===0?'done':'error',time:Date.now(),activity:(code===0?output:errorText).trim().slice(-1000)||'Conversation finished'});send();});
 });
});
ipcMain.on('hide-pet',()=>{fleaQueue.clear();win.hide();});
ipcMain.on('refresh-usage',refreshUsage);
ipcMain.on('open-settings',showSettingsWindow);
ipcMain.on('settings-initialize',(_,value)=>{if(!preferences)persistPreferences(value);else win.webContents.send('settings-changed',preferences);});
ipcMain.handle('usage-bar-select',(event,selection)=>{if(event.sender!==win?.webContents)throw Error('Pet window required');return persistPreferences({...preferences,usageBar:selection});});
ipcMain.handle('settings-get',()=>preferences||normalizeSettings());
ipcMain.handle('settings-update',(event,value)=>{if(event.sender!==settingsWin?.webContents)throw Error('Settings window required');return persistPreferences(value);});
ipcMain.handle('pick-sprite-sheet',async event=>{
 if(event.sender!==settingsWin?.webContents)throw Error('Settings window required');
 const result=await dialog.showOpenDialog(settingsWin,{title:'Choose a sprite sheet',properties:['openFile'],filters:[{name:'Images',extensions:['png','webp','jpg','jpeg']}]});
 if(result.canceled)return null;const source=result.filePaths[0];if(fs.statSync(source).size>20*1024*1024)throw Error('Choose an image smaller than 20 MB');
 const picture=nativeImage.createFromPath(source);if(picture.isEmpty())throw Error('Could not read this image');
 const folder=path.join(stateDir,'sprites');fs.mkdirSync(folder,{recursive:true});const destination=path.join(folder,require('node:crypto').randomUUID()+path.extname(source));fs.copyFileSync(source,destination);
 return {sheet:require('node:url').pathToFileURL(destination).href,name:path.basename(source),frames:1,columns:1,fps:10};
});
ipcMain.on('settings-close' ,()=>settingsWin?.close());
ipcMain.on('reset-position',()=>{fleaQueue.clear();const area=screen.getPrimaryDisplay().workArea;movePet(area.x+area.width-210,area.y+area.height-250);save();});
ipcMain.on('quit' ,()=>app.quit());app.on('before-quit',()=>{randomFleas.stop();fleaQueue.clear();summonControl?.close();save();clearInterval(timer);clearInterval(usageTimer);clearInterval(pointerTimer);clearInterval(dragTimer);inputShape?.stdin.end();hyprInput?.close();});app.on('window-all-closed',()=>app.quit());
