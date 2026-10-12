function placePet(x,y,area,width=374,height=630,scale=1){
 const petWidth=150*scale,petHeight=129*scale;
 const px=Math.max(area.x,Math.min(x,area.x+area.width-petWidth));
 const py=Math.max(area.y,Math.min(y,area.y+area.height-petHeight));
 const left=Math.max(area.x,Math.min(px-(width-petWidth)/2,area.x+Math.max(0,area.width-width)));
 const above=py-area.y>area.y+area.height-py-petHeight;
 const desiredTop=py-(height-petHeight)/2;
 const top=Math.max(area.y,Math.min(desiredTop,area.y+Math.max(0,area.height-height)));
 return {x:Math.round(left),y:Math.round(top),petX:Math.round(px-left),petY:Math.round(py-top),above};
}
module.exports={placePet};
