function terminalHasThread(thread,windows,processes){
 const byPid=new Map(processes.map(p=>[p.pid,p]));
 const descends=(process,pid)=>{let p=process;const visited=new Set();while(p&&!visited.has(p.pid)){if(p.pid===pid)return true;visited.add(p.pid);p=byPid.get(p.ppid);}return false;};
 const codex=processes.filter(p=>p.name==='codex');
 if(codex.some(p=>p.tty&&p.args.includes(thread.id)))return true;
 const title=(thread.name||'').toLowerCase();
 return windows.some(w=>/kitty|alacritty|foot|wezterm|konsole|gnome-terminal/i.test(w.class||'')&&title.length>2&&title!=='untitled conversation'&&(w.title||'').toLowerCase().includes(title)&&codex.some(p=>descends(p,w.pid)));
}
module.exports={terminalHasThread};
