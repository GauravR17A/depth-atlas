import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpen, X } from 'lucide-react';
import { ApiError, getApi, appVersion } from '../contracts';
import type { Recipe } from '../investigations/contracts';
import './guides.css';

type Column={case_id:string;region_id:string;label:string;manifest_sha256:string;time_index:number;time:string;point:[number,number,number];latitude:number;longitude:number;depth_m:number[];temperature_c:(number|null)[];comparison:{profile_id:string;platform:string;matched_count:number}};
type Guide={schema_version:'1';method:string;surface_tolerance_c:number;comparison_depth_m:number;selection:string;columns:Column[]};
function parseGuide(v:unknown):Guide {
  const g=v as Guide;
  if(!g||g.schema_version!=='1'||g.method!=='p09-native-teaching-pair-v1'||g.surface_tolerance_c!==.05||g.comparison_depth_m!==100||typeof g.selection!=='string'||!Array.isArray(g.columns)||g.columns.length!==2)throw new ApiError('The guided example could not be verified.',undefined,'response');
  for(const c of g.columns){if(typeof c.case_id!=='string'||typeof c.label!=='string'||typeof c.region_id!=='string'||!Array.isArray(c.depth_m)||!Array.isArray(c.temperature_c)||c.depth_m.length!==c.temperature_c.length||!c.depth_m.every((z,i)=>Number.isFinite(z)&&z>=0&&(!i||z>c.depth_m[i-1]))||!c.temperature_c.every(v=>v===null||Number.isFinite(v))||!Number.isFinite(c.latitude)||!Number.isFinite(c.longitude)||!Array.isArray(c.point)||c.point.length!==3||!c.point.every(n=>Number.isInteger(n)&&n>=0)||c.time!=='2024-01-07T12:00:00Z'||c.time_index!==1||!c.comparison||typeof c.comparison.profile_id!=='string'||!(c.comparison.matched_count>0)||!/^[a-f0-9]{64}$/.test(c.manifest_sha256))throw new ApiError('The guided profiles could not be verified.',undefined,'response');}
  if(g.columns.some(c=>c.depth_m[0]!==0||c.depth_m[c.point[2]]!==100||c.temperature_c[0]===null||c.temperature_c[c.point[2]]===null)||Math.abs(g.columns[0].temperature_c[0]!-g.columns[1].temperature_c[0]!)>.05)throw new ApiError('The teaching pair does not meet its declared selection rule.',undefined,'response');
  return g;
}

function preset(c:Column,step:number):Recipe {
  if(step===1)return {mode:'comparison',case_id:c.case_id,profile_id:c.comparison.profile_id,settings:{variable:'temperature',time_index:c.time_index,time_window_hours:6,distance_km:5,max_vertical_gap_m:500,qc:'good_probably_good'},sample_index:0,view:'comparison',rank:'nearest',baseline:null};
  if(step>=2)return {mode:'features',case_id:c.case_id,query:{variable:'temperature',units:'°C',time_index:c.time_index,operator:'at_least',threshold:26,upper_threshold:null,depth_min_m:0,depth_max_m:300,order:'volume'},selected_region:null,section:null,section_pick:0,show_observations:true,graphics:'3d',exaggeration:1000};
  return {mode:'ocean',case_id:c.case_id,variable:'temperature',time_index:c.time_index,view:'volume',depth_index:c.point[2],section_index:Math.round(c.point[1]/2),point:c.point,paint:{min:0,max:30,log:false,palette:'thermal',opacity:1},iso:20,exaggeration:200,window_depth:1000,cutaway:true,quality:'auto',show_instruments:true};
}
const steps=['Look below the surface','Compare a measurement','Find warm water','Save the evidence'];
const descriptions=[
  'The cutaway reveals depth layers. Colour represents temperature; depth increases downwards. The opening and stretched height help you see inside. Neither changes the measured coordinates or model values.',
  'This real Argo float measured a separate location in the selected case. Compare it with the nearby model column. Model minus observation is the residual. Only samples passing the displayed source, quality, time, distance and depth rules count. HYCOM may assimilate Argo, so agreement is not independent validation.',
  'Find connected model cells at or above 26 °C between 0 and 300 m. The prepared search runs when you open this step. Change the query and choose Find regions to apply a different condition. A connected warm region is a threshold result, not proof of an eddy or a tracked parcel of water.',
  'Use Save investigation in the analysis below after the search finishes. Give it a title, then choose Save on this browser. Open Saved to replay it or download the investigation file and report. Browser storage is local to this device; export a file to keep a separate copy.',
];

function Contrast({guide}:{guide:Guide}){
  const [depth,setDepth]=useState(100);const colors=['#91e5d1','#f3ba7e'];
  const depths=guide.columns[0].depth_m.filter(z=>z<=1000&&guide.columns.every(c=>c.depth_m.includes(z)));
  const value=(c:Column,z:number)=>c.temperature_c[c.depth_m.indexOf(z)];
  const difference=Math.abs(value(guide.columns[0],depth)!-value(guide.columns[1],depth)!);
  return <section className="contrast-example" aria-label="Similar surface, different depths">
    <div><span className="eyebrow">TWO REAL MODEL COLUMNS</span><h3>Similar at the surface. Different below.</h3><p>7 January 2024, 12:00 UTC · HYCOM model analysis</p><p>Their surface temperatures differ by {Math.abs(value(guide.columns[0],0)!-value(guide.columns[1],0)!).toFixed(3)} °C. Inspect the same depth in both columns.</p>
      <label className="guide-depth">Compare at depth<select aria-label="Compare at depth" value={depth} onChange={e=>setDepth(Number(e.target.value))}>{depths.map(z=><option key={z} value={z}>{z} m</option>)}</select></label>
      <table><caption>Native model temperatures in °C</caption><thead><tr><th>Location</th><th>Surface</th><th>{depth} m</th></tr></thead><tbody>{guide.columns.map((c,i)=><tr key={c.case_id}><th><span className={`column-key column-${i}`}/>{c.label}<small>{c.latitude.toFixed(3)}°N, {c.longitude.toFixed(3)}°E</small></th><td>{value(c,0)?.toFixed(2)??'Missing'}</td><td>{value(c,depth)?.toFixed(2)??'Missing'}</td></tr>)}</tbody></table>
      <p aria-live="polite">{guide.columns.every(c=>value(c,depth)!==null)?`Difference at ${depth} m: ${difference.toFixed(2)} °C.`:'A source value is missing at this depth; no difference is calculated.'}</p>
    </div>
    <svg viewBox="0 0 420 290" role="img" aria-label="Temperature profiles from 0 to 1000 metres. Bay of Bengal is a solid mint line; Arabian Sea is a dashed amber line. Exact values are in the adjacent depth selector and table.">
      {[0,250,500,750,1000].map(z=><g key={z}><line x1="55" x2="392" y1={25+z*.23} y2={25+z*.23} stroke="#304956"/><text x="47" y={29+z*.23} textAnchor="end">{z}</text></g>)}
      {[0,10,20,30].map(t=><g key={t}><text x={55+t*11} y="278" textAnchor="middle">{t} °C</text></g>)}
      <text x="55" y="15">Depth (m)</text><line x1="55" x2="392" y1={25+depth*.23} y2={25+depth*.23} stroke="#d9e8ec" strokeDasharray="3 5"/>
      {guide.columns.map((c,i)=>{let pen=false;let d='';c.depth_m.forEach((z,k)=>{const v=c.temperature_c[k];if(z>1000||v===null){pen=false;return;}d+=`${pen?'L':'M'}${55+v*11},${25+z*.23} `;pen=true;});return <g key={c.case_id}><path d={d} fill="none" stroke={colors[i]} strokeWidth="2.5" strokeDasharray={i?'7 4':undefined}/>{value(c,depth)!==null&&<circle cx={55+value(c,depth)!*11} cy={25+depth*.23} r="4" fill={colors[i]}/>}</g>;})}
    </svg>
    <details className="guide-method"><summary>How this example was selected</summary><p>{guide.selection}</p><p>Lines join available native samples for readability. No gaps are filled. This compares model columns, not two float measurements. Similar surface temperature does not establish equal density, salinity or future behaviour.</p><a href="/api/guided-cases" target="_blank" rel="noreferrer">Coordinates, native values and source fingerprints</a></details>
  </section>;
}

export function GuidedJourney({caseId,onApply,onExit,initialOpen=false}:{initialOpen?:boolean;caseId?:string;onApply:(recipe:Recipe,region:string)=>void;onExit:()=>void}){
  const [open,setOpen]=useState(initialOpen),[step,setStep]=useState(0),[contrast,setContrast]=useState(true);
  const entry=useRef<HTMLButtonElement>(null),wasOpen=useRef(false);
  useEffect(()=>{if(!open&&wasOpen.current)entry.current?.focus();wasOpen.current=open;},[open]);
  const query=useQuery({queryKey:['guided-cases',appVersion],queryFn:({signal})=>getApi('/api/guided-cases',parseGuide,signal),enabled:open,staleTime:Infinity});
  const column=query.data?.columns.find(c=>c.case_id===caseId)??query.data?.columns[0];
  function go(next:number){if(!column)return;setStep(next);if(next<3||(step!==2&&step!==3))onApply(preset(column,next),column.region_id);}
  if(!open)return <section className="guide-entry"><div><BookOpen size={18}/><span><strong>New to the ocean workspace?</strong> Follow a real investigation from depth to evidence.</span></div><button ref={entry} className="secondary-button" onClick={()=>setOpen(true)}>Start guided investigation <ArrowRight size={15}/></button></section>;
  return <section className="guided-journey" aria-label="Guided investigation">
    <div className="journey-heading"><div><span className="eyebrow">GUIDED INVESTIGATION</span><h2>What can a surface view miss?</h2></div><button className="secondary-button" onClick={()=>{setOpen(false);onExit();}}>Exit guide <X size={15}/></button></div>
    {query.isPending?<p role="status">Loading the source-checked example. You can continue using the workspace below.</p>:query.isError?<div role="alert"><p>{query.error.message}</p><button className="secondary-button" onClick={()=>void query.refetch()}>Retry guided example</button></div>:<>
      <div className="journey-options"><button className="secondary-button" aria-expanded={contrast} onClick={()=>setContrast(!contrast)}>{contrast?'Hide':'Show'} two-column comparison</button><button className="secondary-button" onClick={()=>{setContrast(true);go(0);}}>Restart guide</button></div>
      {contrast&&<Contrast guide={query.data}/>}
      <nav className="journey-steps" aria-label="Guided steps">{steps.map((label,i)=><button key={label} aria-current={step===i?'step':undefined} onClick={()=>go(i)}><span>{i+1}</span>{label}</button>)}</nav>
      <div className="journey-instruction"><div><h3>Step {step+1}: {steps[step]}</h3><p>{descriptions[step]}</p>{step===1&&<p>Prepared example: Argo {column?.comparison.platform}. Applied model snapshot: 7 January 2024, 12:00 UTC. The selected float is separate from the teaching pair above.</p>}</div><div className="journey-actions">{step>0&&<button className="secondary-button" onClick={()=>go(step-1)}>Previous step</button>}{step===0&&<button className="secondary-button" onClick={()=>{go(0);setContrast(false);}}>Open this column</button>}{step<3&&<button className="primary-button" onClick={()=>{go(step+1);setContrast(false);}}>Next: {steps[step+1]} <ArrowRight size={15}/></button>}</div></div>
      <details className="guide-glossary"><summary>Reading the ocean data</summary><p><strong>Model:</strong> a numerical estimate on a grid. <strong>Observation:</strong> a sensor measurement with its own time, location and quality flags. <strong>Temperature:</strong> how warm the water is, in °C. <strong>Practical salinity:</strong> a conductivity-based measure of salt content, displayed as psu. <strong>Depth:</strong> metres below the surface, increasing downwards. <strong>Missing:</strong> unavailable, never zero.</p><p>Switch Study case to repeat these steps in the other region. Each case covers only its shown rectangle. Advanced colour and matching controls remain available below. Reset exploration returns the explorer to its starting view.</p></details>
    </>}
  </section>;
}
