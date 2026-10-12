const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('preferences',{pickSpriteSheet:()=>ipcRenderer.invoke('pick-sprite-sheet'),get:()=>ipcRenderer.invoke('settings-get'),update:settings=>ipcRenderer.invoke('settings-update',settings),resetPosition:()=>ipcRenderer.send('reset-position'),close:()=>ipcRenderer.send('settings-close')});
