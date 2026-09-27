import {useEffect} from 'react';
import {visibleTarget} from './useTourAnchor';

// Highlight actionable targets, without painting every control inside a chart.
export function useControlGlow(selector:string,enabled:boolean){
  useEffect(()=>{
    if(!enabled||!selector)return;
    let node:HTMLElement|null=null;
    function update(){
      const target=visibleTarget(selector);
      const next=target?.matches('button,select,input,label,summary')?target:null;
      if(next===node)return;
      node?.removeAttribute('data-tutorial-control');node=next;node?.setAttribute('data-tutorial-control','');
    }
    const observer=new MutationObserver(update);observer.observe(document.body,{childList:true,subtree:true});update();
    return()=>{observer.disconnect();node?.removeAttribute('data-tutorial-control');};
  },[selector,enabled]);
}
