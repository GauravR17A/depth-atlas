import type { InstrumentProfile } from './contracts';

export function ProfileChart({profile,variable,index,onSample,excluded}:{profile:InstrumentProfile;variable:string;index:number;onSample:(index:number)=>void;excluded:boolean}){
  const parameter=profile.parameters[variable],levels=profile.levels;
  const points=levels.map((l,i)=>({l,i,r:l.readings[variable]})).filter(p=>p.l.depth_m!==null&&p.r.value!==null&&(p.r.accepted||excluded));
  const values=points.map(p=>p.r.value!),depths=levels.flatMap(l=>l.depth_m===null?[]:[l.depth_m]);
  const low=Math.min(...values),high=Math.max(...values),pad=values.length?Math.max((high-low)*.08,.01):1;
  const min=values.length?low-pad:0,max=values.length?high+pad:1,bottom=Math.max(10,...depths);
  const x=(v:number)=>66+(v-min)/(max-min)*330,y=(d:number)=>38+d/bottom*340;
  let line='',wasValid=false;
  for(const l of levels){const r=l.readings[variable];if(!r.accepted||r.value===null||l.depth_m===null){wasValid=false;continue;}line+=`${wasValid?'L':'M'}${x(r.value).toFixed(2)},${y(l.depth_m).toFixed(2)} `;wasValid=true;}
  const eligible=(i:number)=>Boolean(levels[i]?.readings[variable].accepted&&levels[i]?.readings[variable].value!==null&&levels[i]?.depth_m!==null);
  const isolated=points.filter(p=>p.r.accepted&&!eligible(p.i-1)&&!eligible(p.i+1));
  const selected=levels[index],r=selected?.readings[variable];
  function click(clientX:number,clientY:number,target:SVGSVGElement){const bounds=target.getBoundingClientRect();const sx=(clientX-bounds.left)*440/bounds.width,sy=(clientY-bounds.top)*440/bounds.height;let best=Infinity,chosen=-1;for(const p of points){const d=Math.hypot(x(p.r.value!)-sx,y(p.l.depth_m!)-sy);if(d<best){best=d;chosen=p.i;}}if(chosen>=0)onSample(chosen);}
  return <div className="profile-chart"><svg viewBox="0 0 440 440" role="img" aria-label={`${parameter.label} versus depth, ${parameter.units}. ${parameter.accepted_count} accepted of ${profile.samples} source samples.`} onClick={e=>click(e.clientX,e.clientY,e.currentTarget)}>
    {[0,.25,.5,.75,1].map(f=><g key={f}><line x1="66" x2="396" y1={y(f*bottom)} y2={y(f*bottom)} stroke="#294650"/><text x="56" y={y(f*bottom)+4} textAnchor="end">{Math.round(f*bottom).toLocaleString()}</text><text x={66+f*330} y="400" textAnchor="middle">{(min+f*(max-min)).toFixed(variable==='temperature'?1:2)}</text></g>)}
    <text x="231" y="427" textAnchor="middle">{parameter.label} ({parameter.units})</text><text transform="translate(17,205) rotate(-90)" textAnchor="middle">Depth (m), positive down</text>
    <path d={line} fill="none" stroke="#a1e1cf" strokeWidth="2"/>
    {isolated.map(p=><circle className="accepted-sample" key={p.i} cx={x(p.r.value!)} cy={y(p.l.depth_m!)} r="2" fill="#a1e1cf"/>)}
    {excluded&&points.filter(p=>!p.r.accepted).map(p=><path key={p.i} d={`M${x(p.r.value!)-2},${y(p.l.depth_m!)-2}l4,4m0,-4l-4,4`} stroke="#dca679" strokeWidth="1"/>)}
    {selected?.depth_m!==null&&selected&&<line x1="66" x2="396" y1={y(selected.depth_m)} y2={y(selected.depth_m)} stroke="#c5dfe3" strokeDasharray="4 4"/>}
    {r&&r.value!==null&&selected.depth_m!==null&&(r.accepted||excluded)&&<circle cx={x(r.value)} cy={y(selected.depth_m)} r="5" fill="#fff2ce" stroke="#162e37"/>}
    {!points.length&&<text x="231" y="190" textAnchor="middle">No eligible values for this curve.</text>}
  </svg><p>Click a plotted sample or use the sample control. Lines stop at excluded or missing readings. No smoothing or invented values.</p></div>;
}
