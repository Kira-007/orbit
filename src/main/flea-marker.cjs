const {BrowserWindow}=require('electron'),fs=require('node:fs'),path=require('node:path');
function createFleaMarker(point,stateDir){
 const marker=new BrowserWindow({title:'Orbit Flea',width:52,height:72,x:Math.round(point.x-26),y:Math.round(point.y-36),frame:false,transparent:true,backgroundColor:'#00000000',hasShadow:false,resizable:false,movable:false,focusable:false,skipTaskbar:true,show:false,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true}});
 marker.setIgnoreMouseEvents(true);marker.setAlwaysOnTop(true,'floating');marker.setVisibleOnAllWorkspaces(true,{visibleOnFullScreen:true});
 const animated=path.join(stateDir,'sprites/flea/flea-animated.webp'),file=fs.existsSync(animated)?animated:path.join(stateDir,'sprites/flea/Flea.png');
 const fallback='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 130"><path fill="#c5afa2" stroke="#302b30" stroke-width="4" d="M40 40Q10 3 24 4Q39 6 46 34Q58 2 71 5Q81 13 60 40Q96 52 85 81L97 95L81 95L85 111L69 106Q50 127 30 107L13 113L17 96L3 95L16 81Q4 56 40 40Z"/><path d="M37 65Q49 83 63 64Q61 96 49 91Q37 87 37 65Z" fill="#554653" stroke="#302b30" stroke-width="3"/></svg>';
 const data=fs.existsSync(file)?'data:image/'+(file.endsWith('.webp')?'webp':'png')+';base64,'+fs.readFileSync(file).toString('base64'):'data:image/svg+xml;base64,'+Buffer.from(fallback).toString('base64');
 marker.loadURL('data:text/html;charset=utf-8,'+encodeURIComponent('<!doctype html><title>Orbit Flea</title><style>html,body{margin:0;background:transparent;overflow:hidden;width:100%;height:100%;display:grid;place-items:center}img{width:44px;height:64px;object-fit:contain}</style><img alt="Flea" src="'+data+'">')).catch(()=>{});
 marker.once('ready-to-show',()=>{if(!marker.isDestroyed())marker.showInactive();});return marker;
}
module.exports={createFleaMarker};
