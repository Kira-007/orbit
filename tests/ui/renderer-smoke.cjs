const {app,BrowserWindow}=require('electron'),path=require('node:path'),fs=require('node:fs'),os=require('node:os'),assert=require('node:assert/strict');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'orbit-renderer-profile-'));app.setPath('userData',profile);let win;const errors=[];
app.whenReady().then(async()=>{
 win=new BrowserWindow({show:false,width:500,height:1000,webPreferences:{preload:path.join(__dirname,'renderer-preload.cjs'),contextIsolation:true,sandbox:true,backgroundThrottling:false}});
 win.webContents.on('console-message',(_e,level,message)=>{if(level>=3)errors.push(message)});
 const evaluate=expression=>win.webContents.executeJavaScript(expression);
 try{
  await win.loadFile(path.join(__dirname,'../../src/renderer/index.html'));await new Promise(r=>setTimeout(r,200));
  assert.equal(await evaluate('visibleTasks().length'),3);
  await evaluate("document.querySelector('.card.codex-cli').click()");await new Promise(r=>setTimeout(r,150));
  assert.deepEqual(await evaluate("({chat:chatOpen,harness:$('harness').value,thread:selectedThread,disabled:$('submit-task').disabled})"),{chat:true,harness:'codex-cli',thread:'one',disabled:false});
  assert.equal((await evaluate('testStats.get()')).focusCalls,0);
  // Clicking a done card opens its session, then removes its notification.
  await evaluate("document.querySelector('.card.claude').click()");await new Promise(r=>setTimeout(r,80));
  assert.equal(await evaluate('selectedThread'),'two');assert.equal(await evaluate("visibleTasks().some(s=>s.session==='two')"),false);
  // An unavailable target must never fall back to another conversation.
  await evaluate("document.querySelector('.card.codex-desktop').click()");await new Promise(r=>setTimeout(r,80));
  assert.equal(await evaluate('selectedThread'),'');assert.equal(await evaluate("$('submit-task').disabled"),true);
  // Slow request must not overwrite a newer harness choice.
  await evaluate("openTaskChat(data.sessions[0]);$('harness').value='claude';chooseHarness();loadProjects('two')");await new Promise(r=>setTimeout(r,150));assert.equal(await evaluate('selectedThread'),'two');
  // Double submit is blocked, and typing while sending is not erased.
  await evaluate("$('prompt').value='hello';$('composer').requestSubmit();$('composer').requestSubmit();$('prompt').value='new draft'");await new Promise(r=>setTimeout(r,150));
  assert.deepEqual((await evaluate('testStats.get()')).sends,[{provider:'claude',prompt:'hello',thread:'two'}]);assert.equal(await evaluate("$('prompt').value"),'new draft');
  const motion=await evaluate(`(()=>{settings.petMode='sprite';settings.spriteSheets={walking:{name:'Run'},dragging:{name:'Float'},idle:{name:'Idle'}};petWalking=true;petDragging=true;const drag=currentSpriteConfig().name;petDragging=false;const run=currentSpriteConfig().name;petWalking=false;return {drag,run,idle:currentSpriteConfig().name}})()`);
  assert.deepEqual(motion,{drag:'Float',run:'Run',idle:'Idle'});
  // Toolbar spacing measures visible artwork, in either panel direction.
  const gaps=await evaluate(`(()=>{
   settings.spritePets=[{id:'gap-test',offsetY:18}];settings.activeSpritePet='gap-test';
   spriteBounds={top:50,bottom:200};$('pet-sprite').hidden=false;
   document.body.classList.add('toolbar-expanded');const values=[];
   for(const gap of [18,-8])for(const above of [false,true]){
    settings.spritePets[0].offsetY=gap;
    document.body.classList.toggle('above',above);fitContent();
    const pet=$('pet').getBoundingClientRect(),bar=$('toolbar').getBoundingClientRect(),factor=pet.height/$('pet-sprite').height;
    values.push({expected:gap,actual:above?pet.top+50*factor-bar.bottom:bar.top-(pet.top+200*factor)});
   }
   return values;
  })()`);
  for(const gap of gaps)assert(Math.abs(gap.actual-gap.expected)<1,'Incorrect visible sprite–toolbar gap: '+JSON.stringify(gap));
  assert.equal(errors.filter(x=>!x.includes('Content-Security-Policy')).length,0,errors.join('\n'));
  console.log('PASS renderer: exact session, done dismissal, missing target, async race, duplicate submission, draft retention, no external focus');
 }catch(e){console.error(e);process.exitCode=1;}finally{win.destroy();app.quit();}
});app.on('will-quit',()=>{fs.rmSync(profile,{recursive:true,force:true})});
