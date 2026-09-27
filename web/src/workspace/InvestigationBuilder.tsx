import { ArrowRight, Check, X } from 'lucide-react';
import type { ActivityId } from './ToolMenu';

const steps = ['Choose data', 'Explore depth', 'Inspect a reading', 'Compare', 'Save'];
const tools:ActivityId[] = ['ocean','ocean','instruments','comparison','comparison'];
const descriptions = [
  'Choose a study case above. Check its source dates before comparing measurements.',
  'Turn the model, open the cutaway or change depth. Colour shows the selected quantity. The stretched depth helps you see inside.',
  'Choose a profile or import your own file. Select a source sample to link its depth and position to the model. Each keeps its own timestamp.',
  'Read the eligible pair count and residual: model minus observation. If none match, use Find a useful comparison or inspect the exclusions.',
  'Save the applied comparison and any reference. Reopening checks sources and recalculates results. Download a backup for another browser.',
];

export function InvestigationBuilder({step,onStep,activity,ready,canCompare,saved,onSave,onClose,onGuide}:{
  step:number;onStep:(step:number,tool:ActivityId)=>void;activity:ActivityId;ready:boolean;canCompare:boolean;saved:boolean;onSave:()=>void;onClose:()=>void;onGuide:()=>void;
}){
  const inPlace=activity===tools[step];
  return <section className="investigation-builder" aria-label="Investigation builder">
    <div className="builder-title"><strong>Build an investigation</strong><button className="icon-button" aria-label="Close investigation builder" onClick={onClose}><X size={18}/></button></div>
    <nav aria-label="Investigation steps">{steps.map((label,i)=><button key={label} aria-label={`${i+1} ${label}`} aria-current={step===i?'step':undefined} disabled={i>=3&&!canCompare} onClick={()=>onStep(i,tools[i])}><span>{i===4&&saved?<Check size={15}/>:i+1}</span><span className="builder-step-label">{label}</span></button>)}</nav>
    <div className="builder-instruction"><div><h2>{saved&&step===4?'Saved on this browser':steps[step]}</h2><p>{descriptions[step]}</p>{!canCompare&&<p>This case supplies monthly potential temperature. Direct comparisons are unavailable. Choose an Indian Ocean case to follow all five steps, or keep exploring this model.</p>}</div><div className="builder-actions">
      {!inPlace?<button className="primary-button" onClick={()=>onStep(step,tools[step])}>Return to this step</button>:step<4?<button className="primary-button" disabled={!ready||step===2&&!canCompare} onClick={()=>onStep(step+1,tools[step+1])}>Next: {steps[step+1]} <ArrowRight size={15}/></button>:<button className="primary-button" disabled={!ready} onClick={onSave}>{saved?'Save another copy':'Save this investigation'}</button>}
      {!ready&&inPlace&&<small>Waiting for this view to finish. Any error and retry control appear below.</small>}
      <button className="context-button" onClick={onGuide}>Try a prepared example</button>
    </div></div>
    <p className="builder-note">Tools stays available. This guide keeps its place until reload. Save only records the applied analysis.</p>
  </section>;
}
