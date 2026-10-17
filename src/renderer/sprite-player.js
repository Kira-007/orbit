const spriteTopCache=new Map();
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
   const boundsKey=JSON.stringify([source.sheet,source.frames,columns]);let spriteTop=spriteTopCache.get(boundsKey);
   if(spriteTop===undefined){
    const probe=document.createElement('canvas');probe.width=width;probe.height=height;
    const ctx=probe.getContext('2d',{willReadFrequently:true});spriteTop=height;
    for(let f=0;f<source.frames&&spriteTop>0;f++){
     ctx.clearRect(0,0,width,height);ctx.drawImage(image,(f%columns)*width,Math.floor(f/columns)*height,width,height,0,0,width,height);
     const pixels=ctx.getImageData(0,0,width,height).data;
     scan:for(let y=0;y<spriteTop;y++)for(let x=0;x<width;x++)if(pixels[(y*width+x)*4+3]>8){spriteTop=y;break scan;}
    }
    if(spriteTop===height)spriteTop=0;spriteTopCache.set(boundsKey,spriteTop);
   }
   // Y is the gap to visible artwork, not a translation of transparent padding.
   const drawY=((Number(source.offsetY)||0)-spriteTop)*ratio;
   const draw=now=>{if(generation!==this.generation)return;const frame=animate?Math.floor((now-start)*source.fps/1000)%source.frames:0;this.context.clearRect(0,0,this.canvas.width,this.canvas.height);this.context.imageSmoothingEnabled=false;this.context.drawImage(image,(frame%columns)*width,Math.floor(frame/columns)*height,width,height,(this.canvas.width-dw)/2+(Number(source.offsetX)||0)*ratio,drawY,dw,dh);if(animate)this.tick=requestAnimationFrame(draw);};draw(start);
  };
  image.src=source.sheet;
 }
}
