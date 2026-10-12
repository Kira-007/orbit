const {execFile}=require('node:child_process');
// Hyprland 0.56 hit-tests pinned X11 windows by their rectangular bounds.
// Keep its focus eligibility in sync with the visible controls, inside its event loop.
function createHyprInputPolicy(pid){
 let state=null,last='',busy=false,pending=false,closed=false;
 const timer=setInterval(()=>flush(true),2500);
 function flush(force=false){
  if(closed||!state||!process.env.HYPRLAND_INSTANCE_SIGNATURE)return;
  const signature=JSON.stringify(state);if(!force&&signature===last)return;
  if(busy){pending=true;return;}busy=true;
  const regions=state.regions.map(r=>`{x=${r.x},y=${r.y},width=${r.width},height=${r.height}}`).join(',');
  const code=`local p=_G.orbit_input_policy
if not p or p.pid ~= ${pid} then
 if p and p.timer then p.timer:set_enabled(false) end
 p={pid=${pid}};_G.orbit_input_policy=p
 p.timer=hl.timer(function()
  local w=nil;for _,candidate in ipairs(hl.get_windows()) do if candidate.title == "Orbit Agent Pet" and candidate.pid == p.pid then w=candidate;break end end
  if not w or w.pid ~= p.pid or not p.regions then return end
  local c=hl.get_cursor_pos();if not c then return end
  local x=(c.x-w.at.x)*p.width/math.max(1,w.size.x)
  local y=(c.y-w.at.y)*p.height/math.max(1,w.size.y)
  local interactive=p.drag
  for _,r in ipairs(p.regions) do
   if x>=r.x and y>=r.y and x<r.x+r.width and y<r.y+r.height then interactive=true;break end
  end
  local nofocus=not interactive
  if p.nofocus ~= nofocus then
   hl.dispatch(hl.dsp.window.set_prop({window=w,prop="no_focus",value=nofocus and "1" or "0"}))
   p.nofocus=nofocus
  end
 end,{timeout=8,type="repeat"})
end
p.regions={${regions}};p.width=${state.width};p.height=${state.height};p.drag=${state.drag?'true':'false'}`;
  execFile('hyprctl',['eval',code],{timeout:1500},(err,out)=>{busy=false;if(!err&&out.trim()==='ok')last=signature;else if(!err)console.error('Orbit input policy:',out.trim());if(pending){pending=false;flush();}});
 }
 return{update(value){state=value;flush();},close(){closed=true;clearInterval(timer);execFile('hyprctl',['eval',`local p=_G.orbit_input_policy;if p and p.pid == ${pid} then p.timer:set_enabled(false);_G.orbit_input_policy=nil end`],{timeout:1000},()=>{});}};
}
module.exports={createHyprInputPolicy};
