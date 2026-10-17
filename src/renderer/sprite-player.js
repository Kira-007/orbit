const spriteBoundsCache=new Map(),spriteImageCache=new Map();
class SpritePlayer{
 constructor(canvas){this.canvas=canvas;this.context=canvas.getContext('2d');this.key='';this.generation=0;}
 set(config,animate=true){
  const key=JSON.stringify([config,animate,this.canvas.width,this.canvas.height]);if(key===this.key)return;
  this.key=key;const generation=++this.generation;cancelAnimationFrame(this.tick);if(!config){this.context.clearRect(0,0,this.canvas.width,this.canvas.height);return;}
  // A pending image load must retain the frame geometry it was requested with.
  const source={...config},image=spriteImageCache.get(config.sheet)||new Image();
  image.onerror=()=>{if(generation===this.generation)this.key='';};
  const ready=()=>{
   spriteImageCache.set(source.sheet,image);
   if(generation!==this.generation)return;
   const columns=source.columns,rows=Math.ceil(source.frames/columns),width=image.width/columns,height=image.height/rows;
   if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0){this.key='';return;}
   const ratio=Math.min(this.canvas.width/width,this.canvas.height/height),dw=width*ratio,dh=height*ratio,start=performance.now();
   const boundsKey=JSON.stringify([source.sheet,source.frames,columns]);let bounds=spriteBoundsCache.get(boundsKey);
   if(!bounds){
    const probe=document.createElement('canvas');probe.width=width;probe.height=height;const ctx=probe.getContext('2d',{willReadFrequently:true});let top=height,bottom=0;
    for(let f=0;f<source.frames;f++){
     ctx.clearRect(0,0,width,height);ctx.drawImage(image,(f%columns)*width,Math.floor(f/columns)*height,width,height,0,0,width,height);
     const pixels=ctx.getImageData(0,0,width,height).data;
     for(let y=0;y<height;y++)for(let x=0;x<width;x++)if(pixels[(y*width+x)*4+3]>8){top=Math.min(top,y);bottom=Math.max(bottom,y+1);break;}
    }
    bounds={top:top===height?0:top,bottom:bottom||height};spriteBoundsCache.set(boundsKey,bounds);
   }
   this.onBounds?.({top:(this.canvas.height-dh)/2+bounds.top*ratio,bottom:(this.canvas.height-dh)/2+bounds.bottom*ratio});
   const draw=now=>{if(generation!==this.generation)return;const frame=animate?Math.floor((now-start)*source.fps/1000)%source.frames:0;this.context.clearRect(0,0,this.canvas.width,this.canvas.height);this.context.imageSmoothingEnabled=true;this.context.imageSmoothingQuality='high';this.context.drawImage(image,(frame%columns)*width,Math.floor(frame/columns)*height,width,height,(this.canvas.width-dw)/2+(Number(source.offsetX)||0)*ratio,(this.canvas.height-dh)/2,dw,dh);if(animate)this.tick=requestAnimationFrame(draw);};draw(start);this.onReady?.(source);
  };
  if(image.complete&&image.naturalWidth)ready();else{image.onload=ready;image.src=source.sheet;}
 }
}
