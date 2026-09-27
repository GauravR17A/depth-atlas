import { longitudeLabel, latitudeLabel } from '../geography';
import { useEffect, useRef } from 'react';
import { offset, rgb, type Paint, type Point, type ViewMode } from './grid';
import type { ScalarDisplayGrid as Subset } from './grid';
import { mapVector } from './mapVector';

export function BasicView({ data, east, north, mode, depthIndex, sectionIndex, paint, onPick, verticalUnit='m' }: { data: Subset; east?: Subset; north?: Subset; mode: ViewMode; depthIndex: number; sectionIndex: number; paint: Paint; onPick: (p: Point) => void; verticalUnit?:string }) {
  const ref=useRef<HTMLCanvasElement>(null);
  const section=mode==='section'||mode==='volume'||mode==='iso';
  const plotLeft=section&&verticalUnit==='dbar'?86:65;
  useEffect(()=>{
    const canvas=ref.current!,ctx=canvas.getContext('2d')!;
    const render=()=>{
      const width=canvas.clientWidth,height=canvas.clientHeight;
      canvas.width=Math.round(width*Math.min(devicePixelRatio,1.5));canvas.height=Math.round(height*Math.min(devicePixelRatio,1.5));
      const sx=canvas.width/width,sy=canvas.height/height;ctx.setTransform(sx,0,0,sy,0,0);ctx.clearRect(0,0,width,height);
      const left=plotLeft,top=42,w=width-left-30,h=height-94;
      const tile=document.createElement('canvas');tile.width=12;tile.height=12;const pen=tile.getContext('2d')!;
      pen.fillStyle='#152933';pen.fillRect(0,0,12,12);pen.strokeStyle='#526975';pen.lineWidth=1;pen.beginPath();pen.moveTo(0,12);pen.lineTo(12,0);pen.stroke();const missing=ctx.createPattern(tile,'repeat')!;
      const xs=data.longitude,ys=section?data.depth_m:data.latitude;
      const X=(x:number)=>left+(x-xs[0])/(xs.at(-1)!-xs[0])*w;
      const Y=(y:number)=>top+(section?(y-ys[0])/(ys.at(-1)!-ys[0]):1-(y-ys[0])/(ys.at(-1)!-ys[0]))*h;
      ctx.fillStyle='#102936';ctx.fillRect(left,top,w,h);
      let cells=0;
      for(let y=0;y<ys.length-1;y++)for(let x=0;x<xs.length-1;x++){
        const values=[[x,y],[x+1,y],[x+1,y+1],[x,y+1]].map(([i,j])=>data.values[offset(data,i,section?sectionIndex:j,section?j:depthIndex)]);
        if(values.some(v=>v===null)){
          ctx.globalAlpha=1;ctx.fillStyle=missing;ctx.fillRect(X(xs[x]),Math.min(Y(ys[y]),Y(ys[y+1])),X(xs[x+1])-X(xs[x])+.5,Math.abs(Y(ys[y+1])-Y(ys[y]))+.5);continue;
        }
        const color=rgb((values as number[]).reduce((a,b)=>a+b,0)/4,paint);if(!color)continue;
        ctx.globalAlpha=paint.opacity;ctx.fillStyle=`rgb(${color.map(v=>Math.round(v*255)).join(',')})`;
        ctx.fillRect(X(xs[x]),Math.min(Y(ys[y]),Y(ys[y+1])),X(xs[x+1])-X(xs[x])+.5,Math.abs(Y(ys[y+1])-Y(ys[y]))+.5);cells++;
      }
      ctx.globalAlpha=1;
      if(mode==='currents'&&east&&north){
        ctx.strokeStyle='#effaf3';ctx.lineWidth=1.25;
        for(let y=0;y<data.latitude.length;y+=3)for(let x=0;x<xs.length;x+=3){
          const i=offset(data,x,y,depthIndex),u=east.values[i],v=north.values[i];if(u===null||v===null)continue;
          const direction=mapVector(u,v,data.latitude[y],xs.at(-1)!-xs[0],data.latitude.at(-1)!-data.latitude[0],w,h);
          if(!direction)continue;
          const px=X(xs[x]),py=Y(data.latitude[y]),angle=Math.atan2(direction[1],direction[0]);
          const ex=px+direction[0],ey=py+direction[1];
          ctx.beginPath();ctx.moveTo(px,py);ctx.lineTo(ex,ey);ctx.moveTo(ex-4*Math.cos(angle-.5),ey-4*Math.sin(angle-.5));ctx.lineTo(ex,ey);ctx.lineTo(ex-4*Math.cos(angle+.5),ey-4*Math.sin(angle+.5));ctx.stroke();
        }
      }
      ctx.strokeStyle='#51717c';ctx.strokeRect(left,top,w,h);ctx.fillStyle='#b5c9d1';ctx.font='12px sans-serif';ctx.textAlign='center';
      for(let i=0;i<=4;i++){
        const x=xs[0]+i/4*(xs.at(-1)!-xs[0]);ctx.fillText(longitudeLabel(x,1),X(x),top+h+24);
        const y=ys[0]+i/4*(ys.at(-1)!-ys[0]);ctx.textAlign='right';ctx.fillText(section?`${verticalUnit==='dbar'?Number(y.toFixed(1)):Math.round(y)} ${verticalUnit}`:latitudeLabel(y,1),left-9,Y(y)+4);ctx.textAlign='center';
      }
      ctx.textAlign='left';ctx.fillText(section?`East-west section at ${latitudeLabel(data.latitude[sectionIndex])}`:`${verticalUnit==='m'?'Depth':'Pressure'} slice at ${data.depth_m[depthIndex]} ${verticalUnit}`,left,24);
      if(!cells){ctx.textAlign='center';ctx.fillStyle='#e2eaf0';ctx.fillText('No valid cells in this view',left+w/2,top+h/2);}
      canvas.dataset.cells=String(cells);
    };
    const observer=new ResizeObserver(render);observer.observe(canvas);render();return()=>observer.disconnect();
  },[data,east,north,section,mode,depthIndex,sectionIndex,paint,verticalUnit,plotLeft]);
  return <canvas ref={ref} className="basic-ocean" role="img" aria-label={section?'Scientific depth section':'Scientific depth slice'} onClick={event=>{
    const rect=event.currentTarget.getBoundingClientRect(),x=(event.clientX-rect.left-plotLeft)/(rect.width-plotLeft-30),y=(event.clientY-rect.top-42)/(rect.height-94);
    if(x<0||x>1||y<0||y>1)return;
    onPick([data.longitude[0]+x*(data.longitude.at(-1)!-data.longitude[0]),section?data.latitude[sectionIndex]:data.latitude.at(-1)!-y*(data.latitude.at(-1)!-data.latitude[0]),section?data.depth_m[0]+y*(data.depth_m.at(-1)!-data.depth_m[0]):data.depth_m[depthIndex]]);
  }}/>;
}
