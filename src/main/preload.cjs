const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('orbit',{
 refreshUsage:()=>ipcRenderer.send('refresh-usage'),viewport:()=>ipcRenderer.send('pet-viewport',{height:window.innerHeight,width:window.innerWidth}),hide:()=>ipcRenderer.send('hide-pet'),
 openSettings:()=>ipcRenderer.send('open-settings'),
 initializeSettings:settings=>ipcRenderer.send('settings-initialize',settings),
 onPreferences:fn=>ipcRenderer.on('settings-changed',(_,settings)=>fn(settings)),
 resetPosition:()=>ipcRenderer.send('reset-position'),
 onSettings:fn=>ipcRenderer.on('show-settings',()=>fn()),
 onLayout:fn=>ipcRenderer.on('layout',(_,layout)=>fn(layout)),
 onState:fn=>{const cb=(_,state)=>fn(state);ipcRenderer.on('state',cb);return()=>ipcRenderer.removeListener('state',cb);},
 hitRegions:regions=>ipcRenderer.send('hit-regions',regions),
 ready:()=>ipcRenderer.send('ready',{height:window.innerHeight,width:window.innerWidth}),expand:(open)=>ipcRenderer.send('expand',!!open),drag:(phase,x,y,grab)=>ipcRenderer.send('drag',{phase,x,y,grab}),
 projects:provider=>ipcRenderer.invoke('projects',provider),
 startTask:(provider,prompt,thread)=>ipcRenderer.invoke('start-task',{provider,prompt,thread}),
 focus:provider=>ipcRenderer.invoke('focus-agent',provider),quit:()=>ipcRenderer.send('quit')
});
