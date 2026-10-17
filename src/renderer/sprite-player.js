class SpritePlayer{
 constructor(canvas){this.canvas=canvas;this.context=canvas.getContext('2d');this.key='';this.generation=0;}
 set(config,animate=true){
  const key=JSON.stringify([config,animate,this.canvas.width,this.canvas.height]);if(key===this.key)return;
  this.key=key;const generation=++this.generation;cancelAnimationFrame(this.tick);this.context.clearRect(0,0,this.canvas.width,this.canvas.height);if(!config)return;
  // A pending image load must retain the frame geometry it was requested with.
  const source={...config},image=new Image();
  image.onerror=()=>{if(generation===this.generation)this.key='';};
  image.onload=()=>{
   if(generation!==this.generation)return;
   const columns=source.columns,rows=Math.ceil(source.frames/columns),width=image.width/columns,height=image.height/rows;
   if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0){this.key='';return;}
   const ratio=Math.min(this.canvas.width/width,this.canvas.height/height),dw=width*ratio,dh=height*ratio,start=performance.now();
   const draw=now=>{if(generation!==this.generation)return;const frame=animate?Math.floor((now-start)*source.fps/1000)%source.frames:0;this.context.clearRect(0,0,this.canvas.width,this.canvas.height);this.context.imageSmoothingEnabled=false;this.context.drawImage(image,(frame%columns)*width,Math.floor(frame/columns)*height,width,height,(this.canvas.width-dw)/2,(this.canvas.height-dh)/2,dw,dh);if(animate)this.tick=requestAnimationFrame(draw);};draw(start);
  };
  image.src=source.sheet;
 }
}
