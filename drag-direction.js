// Confirm a horizontal turn before mirroring; vertical drags often wobble sideways.
class DragDirection{
 constructor(x,direction=1){this.extreme=x;this.extremeY=0;this.direction=direction;this.turn=null;}
 update(x,time=Date.now(),y=0){
  if(!Number.isFinite(x)||!Number.isFinite(time)||!Number.isFinite(y))return this.direction;
  const advance=(x-this.extreme)*this.direction;
  if(advance>=0){this.extreme=x;this.extremeY=y;this.turn=null;return this.direction;}
  const retreat=-advance;
  const vertical=Math.abs(y-this.extremeY);
  if(vertical>=Math.max(24,retreat*1.5)){this.extreme=x;this.extremeY=y;this.turn=null;return this.direction;}
  if(retreat<4){this.turn=null;return this.direction;}
  if(this.turn&&(x-this.turn.farthest)*this.direction>=4)this.turn=null;
  if(!this.turn)this.turn={since:time,farthest:x};
  if((x-this.turn.farthest)*this.direction<0)this.turn.farthest=x;
  if(retreat>=18&&retreat>=vertical*1.25&&time-this.turn.since>=70){this.direction*=-1;this.extreme=x;this.extremeY=y;this.turn=null;}
  return this.direction;
 }
}
if(typeof module!=='undefined')module.exports={DragDirection};
