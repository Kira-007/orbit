const {contextBridge,ipcRenderer}=require('electron');let stateCallback;let sends=[],focusCalls=0;
const sessions=[{provider:'codex-cli',session:'one',title:'Same title',status:'working',time:Date.now(),taskStartedAt:Date.now()-1000},{provider:'claude',session:'two',title:'Claude task',status:'done',time:Date.now(),taskStartedAt:Date.now()-2000},{provider:'codex-desktop',session:'missing',title:'Missing',status:'working',time:Date.now(),taskStartedAt:Date.now()-3000}];
contextBridge.exposeInMainWorld('orbit',{
 onState:fn=>{stateCallback=fn},ready:()=>setTimeout(()=>stateCallback({sessions,online:{}}),20),onPreferences:()=>{},onLayout:()=>{},initializeSettings:()=>{},hitRegions:()=>{},expand:()=>{},viewport:()=>{},drag:()=>{},hide:()=>{},openSettings:()=>{},refreshUsage:()=>{},resetPosition:()=>{},
 projects:async provider=>{await new Promise(r=>setTimeout(r,provider==='codex-cli'?90:10));return provider==='codex-cli'?[{id:'other',name:'Other thread',path:'/tmp'},{id:'one',name:'Exact thread',path:'/tmp'}]:provider==='claude'?[{id:'two',name:'Claude task',path:'/tmp'}]:[{id:'not-missing',name:'Wrong thread',path:'/tmp'}]},
 startTask:async(provider,prompt,thread)=>{sends.push({provider,prompt,thread});await new Promise(r=>setTimeout(r,100));return {ok:true,message:'Sent'}},focus:()=>{focusCalls++;return true}
});
contextBridge.exposeInMainWorld('testStats',{get:()=>({sends,focusCalls}),state:value=>stateCallback(value)});
