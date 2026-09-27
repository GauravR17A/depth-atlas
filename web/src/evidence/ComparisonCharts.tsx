import type { Comparison,MatchRow } from './contracts';
import { number } from './contracts';

export function ComparisonCharts({comparison,index,onSample}:{comparison:Comparison;index:number;onSample:(i:number)=>void}){
  const rows=comparison.rows,valid=rows.filter(r=>r.accepted),depths=rows.flatMap(r=>r.depth_m===null?[]:[r.depth_m]);
  const bottom=Math.max(10,...depths),values=valid.flatMap(r=>[r.observed!,r.model!]);
  const min=values.length?Math.min(...values):0,max=values.length?Math.max(...values):1,pad=Math.max((max-min)*.07,.01);
  const residualLimit=Math.max(.01,...valid.map(r=>Math.abs(r.residual!)))*1.12;
  const y=(d:number)=>35+d/bottom*330,profileX=(v:number)=>69+(v-min+pad)/(max-min+2*pad)*313,residualX=(v:number)=>69+(v+residualLimit)/(2*residualLimit)*313;
  const selected=rows[index],label=comparison.settings.variable==='temperature'?'In-situ temperature':'Practical salinity';
  function line(key:'observed'|'model'|'residual',x:(v:number)=>number){let path='',previous:MatchRow|undefined;for(const r of rows){if(!r.accepted||r[key]===null||r.depth_m===null){previous=undefined;continue;}const connect=previous&&r.sample_index===previous.sample_index+1&&Math.abs(r.depth_m-previous.depth_m!)<=comparison.settings.max_vertical_gap_m;path+=`${connect?'L':'M'}${x(r[key]!).toFixed(2)},${y(r.depth_m).toFixed(2)} `;previous=r;}return path;}
  function isolated(i:number){const r=rows[i];return ![rows[i-1],rows[i+1]].some(p=>p?.accepted&&p.depth_m!==null&&r.depth_m!==null&&Math.abs(p.sample_index-r.sample_index)===1&&Math.abs(p.depth_m-r.depth_m)<=comparison.settings.max_vertical_gap_m);}
  function pick(clientY:number,target:SVGSVGElement){const rect=target.getBoundingClientRect(),depth=(clientY-rect.top)*425/rect.height;let nearest=-1,distance=Infinity;rows.forEach((r,i)=>{if(r.accepted&&r.depth_m!==null&&Math.abs(y(r.depth_m)-depth)<distance){nearest=i;distance=Math.abs(y(r.depth_m)-depth);}});if(nearest>=0)onSample(nearest);}
  const charts=[{key:'profile',title:'Observation and model',x:profileX,low:min-pad,high:max+pad,axis:`${label} (${comparison.units})`},{key:'residual',title:'Difference at the same depth',x:residualX,low:-residualLimit,high:residualLimit,axis:`Model minus observation (${comparison.units})`}];
  return <div className="evidence-charts" aria-label="Matched profile and residual charts">{charts.map(c=><figure key={c.key} className="evidence-chart"><figcaption>{c.title}</figcaption><svg viewBox="0 0 425 425" role="img" aria-label={`${c.title}, ${comparison.matched_count} eligible pairs. Depth in metres, positive down.`} onClick={e=>pick(e.clientY,e.currentTarget)}>
    {[0,.25,.5,.75,1].map(f=><g key={f}><line x1="69" x2="382" y1={y(f*bottom)} y2={y(f*bottom)} stroke="#2d4753"/><text x="59" y={y(f*bottom)+4} textAnchor="end">{number(f*bottom,0)}</text><text x={69+f*313} y="386" textAnchor="middle">{number(c.low+f*(c.high-c.low),2)}</text></g>)}
    <text x="225" y="414" textAnchor="middle">{c.axis}</text><text transform="translate(17,203) rotate(-90)" textAnchor="middle">Depth (m), positive down</text>
    {c.key==='residual'&&<line x1={residualX(0)} x2={residualX(0)} y1="35" y2="365" stroke="#a3bcc7" strokeDasharray="3 4"/>}
    {(c.key==='profile'?(['observed','model'] as const):(['residual'] as const)).map(k=><g key={k}><path d={line(k,c.x)} fill="none" stroke={k==='model'?'#e5b789':k==='observed'?'#a1e1cf':'#c6dce9'} strokeWidth="2" strokeDasharray={k==='model'?'6 3':undefined}/>{rows.map((r,i)=>r.accepted&&isolated(i)?<circle key={r.sample_index} cx={c.x(r[k]!)} cy={y(r.depth_m!)} r="2.5" fill={k==='model'?'#e5b789':k==='observed'?'#a1e1cf':'#c6dce9'}/>:null)}</g>)}
    {selected?.depth_m!==null&&selected&&<line x1="69" x2="382" y1={y(selected.depth_m)} y2={y(selected.depth_m)} stroke="#f2e4bb" strokeDasharray="4 4"/>}
    {selected?.accepted&&(c.key==='profile'?(['observed','model'] as const):(['residual'] as const)).map(k=><circle key={k} cx={c.x(selected[k]!)} cy={y(selected.depth_m!)} r="4.5" fill={k==='model'?'#e5b789':k==='observed'?'#a1e1cf':'#e5edf2'} stroke="#102733"/>)}
    {!valid.length&&<text x="225" y="180" textAnchor="middle">No eligible pairs to plot.</text>}
    </svg></figure>)}<p className="evidence-chart-note">Both panels use the same {comparison.matched_count} eligible pairs. Click a depth or use the sample selector. Lines follow source order and stop at exclusions or depth gaps; no extrapolation.</p></div>;
}
