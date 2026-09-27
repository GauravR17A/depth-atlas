import {useEffect,useRef} from 'react';
import {ArrowRight,LayoutGrid,X} from 'lucide-react';
import {useTourAnchor} from './useTourAnchor';

export function ToolsHandoff({onOpen,onDismiss}:{onOpen:()=>void;onDismiss:()=>void}){
  const card=useRef<HTMLElement>(null);
  const {placement}=useTourAnchor(card,'#workspace-tools','tools-handoff',true);
  useEffect(()=>{
    const button=document.getElementById('workspace-tools');
    button?.setAttribute('data-tutorial-control','');
    button?.addEventListener('click',onDismiss);
    return()=>{button?.removeAttribute('data-tutorial-control');button?.removeEventListener('click',onDismiss);};
  },[onDismiss]);
  return <aside ref={card} className="tools-handoff" data-side={placement.side} style={{left:placement.left,top:placement.top}} aria-label="Find all tools">
    {placement.found&&placement.side!=='none'&&<span className="learn-pointer" aria-hidden="true" style={placement.side==='left'||placement.side==='right'?{top:placement.arrow}:{left:placement.arrow}}/>}
    <button className="icon-button" aria-label="Dismiss Tools hint" onClick={onDismiss}><X size={16}/></button>
    <strong><LayoutGrid size={18}/> All your tools are here</strong>
    <p>Open Tools for the globe, analyses and labs. Guide can show you each one again.</p>
    <button className="primary-button tutorial-next-glow" onClick={()=>{onDismiss();onOpen();}}>Open Tools <ArrowRight size={16}/></button>
  </aside>;
}
