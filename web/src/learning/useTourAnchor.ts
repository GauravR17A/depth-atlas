import { useEffect, useRef, useState, type RefObject } from 'react';

type Box = { left:number; top:number; width:number; height:number };
type Placement = { left:number; top:number; side:'left'|'right'|'top'|'bottom'|'none'; arrow:number; target:Box|null; found:boolean; offscreen:boolean };
const initial:Placement={left:12,top:12,side:'none',arrow:0,target:null,found:false,offscreen:false};
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(n,Math.max(min,max)));

// Kept workspaces remain mounted. Never point at a hidden copy of a control.
export function visibleTarget(selectors:string):HTMLElement|null {
  for(const selector of selectors.split('|')){
    for(const node of document.querySelectorAll<HTMLElement>(selector.trim())){
      const r=node.getBoundingClientRect();
      if(r.width>0&&r.height>0&&!node.closest('[hidden], [inert]')&&getComputedStyle(node).visibility!=='hidden')return node;
    }
  }
  return null;
}

export function useTourAnchor(card:RefObject<HTMLElement|null>,selector:string,key:string,enabled:boolean){
  const [placement,setPlacement]=useState(initial),[locate,setLocate]=useState(0);
  const [modal,setModal]=useState<HTMLElement|null>(null);
  const lastPosition=useRef('');
  useEffect(()=>{
    if(!enabled){setPlacement(initial);setModal(null);return;}
    let frame=0,disposed=false,node:HTMLElement|null=null,arranged=false;
    const margin=12,gap=18;
    const resize=new ResizeObserver(schedule);
    if(card.current)resize.observe(card.current);
    resize.observe(document.documentElement);
    const mutations=new MutationObserver(schedule);
    mutations.observe(document.body,{childList:true,subtree:true});
    function schedule(){if(!frame&&!disposed)frame=requestAnimationFrame(measure);}
    function measure(){
      frame=0;if(disposed||!card.current)return;
      const dialog=document.querySelector<HTMLElement>('[role="dialog"][data-state="open"]');
      setModal(old=>old===dialog?old:dialog);
      if(dialog)return;
      const found=selector?visibleTarget(selector):null;
      if(found!==node){
        if(node){resize.unobserve(node);node.removeAttribute('data-tour-anchor');}
        node=found;
        if(node){node.setAttribute('data-tour-anchor','');resize.observe(node);}
        arranged=false;
      }
      const viewport=window.visualViewport,w=viewport?.width??document.documentElement.clientWidth,h=viewport?.height??innerHeight;
      const ox=viewport?.offsetLeft??0,oy=viewport?.offsetTop??0;
      const c=card.current.getBoundingClientRect(),cw=c.width,ch=c.height;
      document.documentElement.style.setProperty('--tutorial-card-height',`${ch}px`);
      if(!node){
        update({left:ox+(w-cw)/2,top:oy+(h-ch)/2,side:'none',arrow:0,target:null,found:false,offscreen:false});return;
      }
      let r=node.getBoundingClientRect();
      // Scroll once per destination, including a late-mounted chart. A user's later
      // scrolling is never fought; the callout follows and offers "Bring back".
      if(!arranged){
        arranged=true;
        const sideRoom=r.left-ox>=cw+gap+margin||ox+w-r.right>=cw+gap+margin;
        const visibleHeight=Math.min(r.height,sideRoom?h-2*margin:Math.max(80,h-ch-gap-2*margin));
        const desiredTop=oy+(sideRoom?(h-visibleHeight)/2:margin);
        const desiredCenter=r.top+Math.min(r.height,visibleHeight)/2;
        const delta=desiredCenter-(desiredTop+visibleHeight/2);
        if(Math.abs(delta)>4){
          // The document has a temporary tail so lower results can come fully into view.
          window.scrollBy({top:delta,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
        }
      }
      r=node.getBoundingClientRect();
      const left=clamp(r.left,ox+margin,ox+w-margin),right=clamp(r.right,ox+margin,ox+w-margin);
      const top=clamp(r.top,oy+margin,oy+h-margin),bottom=clamp(r.bottom,oy+margin,oy+h-margin);
      const offscreen=r.bottom<=oy+margin||r.top>=oy+h-margin||r.right<=ox||r.left>=ox+w;
      const target={left,top,width:Math.max(0,right-left),height:Math.max(0,bottom-top)};
      const centerX=left+target.width/2,centerY=top+target.height/2;
      let x=ox+margin,y=oy+margin,side:Placement['side']='none';
      if(!offscreen){
        if(ox+w-right>=cw+gap+margin){side='right';x=right+gap;y=clamp(centerY-ch/2,oy+margin,oy+h-ch-margin);}
        else if(left-ox>=cw+gap+margin){side='left';x=left-gap-cw;y=clamp(centerY-ch/2,oy+margin,oy+h-ch-margin);}
        else if(oy+h-bottom>=ch+gap+margin){side='bottom';x=clamp(centerX-cw/2,ox+margin,ox+w-cw-margin);y=bottom+gap;}
        else if(top-oy>=ch+gap+margin){side='top';x=clamp(centerX-cw/2,ox+margin,ox+w-cw-margin);y=top-gap-ch;}
        else {
          // A full-width chart can be taller than the screen. Keep its upper part
          // visible and point to that part, rather than claiming the whole chart fits.
          side='bottom';x=clamp(centerX-cw/2,ox+margin,ox+w-cw-margin);y=oy+h-ch-margin;
          target.height=Math.max(0,y-gap-target.top);
        }
      }else{x=clamp(centerX-cw/2,ox+margin,ox+w-cw-margin);y=r.top>=oy+h?oy+h-ch-margin:oy+margin;}
      const arrow=side==='left'||side==='right'?clamp(centerY-y,20,ch-20):clamp(centerX-x,20,cw-20);
      update({left:x,top:y,side,arrow,target:offscreen?null:target,found:true,offscreen});
    }
    function update(value:Placement){const serial=JSON.stringify(value);if(serial!==lastPosition.current){lastPosition.current=serial;setPlacement(value);}}
    const reflow=()=>{arranged=false;schedule();};
    window.addEventListener('scroll',schedule,true);window.addEventListener('resize',reflow);
    window.visualViewport?.addEventListener('resize',reflow);window.visualViewport?.addEventListener('scroll',schedule);
    schedule();
    return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();mutations.disconnect();node?.removeAttribute('data-tour-anchor');document.documentElement.style.removeProperty('--tutorial-card-height');window.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',reflow);window.visualViewport?.removeEventListener('resize',reflow);window.visualViewport?.removeEventListener('scroll',schedule);lastPosition.current='';};
  },[card,selector,key,enabled,locate]);
  return {placement,modal,relocate:()=>setLocate(n=>n+1)};
}
