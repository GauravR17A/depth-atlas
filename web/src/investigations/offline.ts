import { verifyInvestigation, MAX_FILE_BYTES, type Investigation } from './contracts';
import type { InstrumentProfile } from '../instruments/contracts';
import type { Comparison } from '../evidence/contracts';

type Row={depth:number|null;values:(number|null)[];accepted:boolean;details:unknown};
export type OfflineSeries={label:string;units:string;keys:string[];rows:Row[];context:unknown};
export function offlineSeries(record:Investigation):OfflineSeries[]{
  const series:OfflineSeries[]=[];
  for(const module of record.results){
    if(module.module==='observation_profile'){
      const p=module.output as InstrumentProfile;
      for(const [key,parameter] of Object.entries(p.parameters))series.push({label:`Observation: ${parameter.label}`,units:parameter.units,keys:['Observation'],context:{observation_start:p.time,observation_end:p.time_end,title:p.title,source:p.source_url,source_sha256:p.source_sha256,definition:parameter.definition,qc:p.qc_policy,depth_method:p.depth_method,warnings:p.warnings},rows:p.levels.map(l=>({depth:l.depth_m,values:[l.readings[key].value],accepted:l.readings[key].accepted,details:{sample_index:l.index,time:l.time,latitude:l.latitude,longitude:l.longitude,pressure_dbar:l.pressure_dbar,depth_m:l.depth_m,coordinate_qc:l.coordinate_qc,reading:l.readings[key]}}))});
    }else if(module.module==='comparison'||module.module==='reference_comparison'){
      const c=module.output as Comparison,prefix=module.module==='comparison'?'Comparison':'Reference comparison';
      const context={profile:c.profile.title,observation_start:c.profile.time,observation_end:c.profile.time_end,model_time:c.model_time,settings:c.settings,metrics:c.metrics,methods:c.methods,caveats:c.caveats};
      series.push({label:`${prefix}: ${c.settings.variable}`,units:c.units,keys:['Observation','Model'],context,rows:c.rows.map(r=>({depth:r.depth_m,values:[r.observed,r.model],accepted:r.accepted,details:r}))});
      series.push({label:`${prefix}: residual`,units:c.units,keys:['Model minus observation'],context,rows:c.rows.map(r=>({depth:r.depth_m,values:[r.residual],accepted:r.accepted,details:r}))});
    }else if(module.module==='native_profile'){
      const output=module.output as {columns:{variable:string;units:string;time:string;depth_m:number[];latitude:number[];longitude:number[];values:(number|null)[]}[]};
      for(const c of output.columns)series.push({label:`Model column: ${c.variable}`,units:c.units,keys:['Model'],context:{model_time:c.time,latitude:c.latitude,longitude:c.longitude,method:module.method_version},rows:c.depth_m.map((depth,i)=>({depth,values:[c.values[i]],accepted:c.values[i]!==null,details:{source_depth_index:i,depth_m:depth,value:c.values[i],time:c.time,latitude:c.latitude[0],longitude:c.longitude[0]}}))});
    }
  }
  return series;
}

// Self-contained script. All source-derived text uses textContent, never HTML.
const script = `
(async()=>{'use strict';const el=id=>document.getElementById(id),text=(id,value)=>el(id).textContent=value;
try{const envelope=JSON.parse(el('payload').textContent);if(!crypto.subtle)throw Error('This browser cannot verify the file. Use a browser with local-file SHA-256 support.');
const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(envelope.text))),b=>b.toString(16).padStart(2,'0')).join('');if(sha!==envelope.sha256)throw Error('Checksum mismatch. Saved values were not displayed.');
const data=JSON.parse(envelope.text),record=data.record,series=data.series;
text('title',record.replay.title);text('status','Offline saved results. File integrity checked, not source authenticity or independent scientific validation.');
text('date','Saved '+new Date(record.created_at).toLocaleString()+' | App '+record.software.app+' | Model context: '+record.case.title);
text('age','Snapshot age: '+Math.max(0,Math.floor((Date.now()-Date.parse(record.created_at))/86400000))+' days. Historical source dates remain below. No new data is fetched.');
text('sources',JSON.stringify({references:record.references,limitations:record.limitations,source_identity:record.replay.sources,document_sha256:record.document_sha256,inventory:['Saved result arrays and QC','Replay settings and source references',...(record.replay.import_source?['Original imported file and explicit mappings']:[]),'Viewer script and styles'],omitted:'Full model grids and server computation are not included.'},null,2));
const view=el('view'),sample=el('sample'),canvas=el('chart'),ctx=canvas.getContext('2d'),excluded=el('excluded');let s;
for(const item of series){const o=document.createElement('option');o.textContent=item.label;view.append(o);}
function detail(){const row=s.rows[sample.selectedIndex];text('readout','Sample '+sample.selectedIndex+' | Depth '+(row.depth===null?'Missing':row.depth+' m')+' | '+s.keys.map((key,i)=>key+': '+(row.values[i]===null?'Missing':row.values[i]+' '+s.units)).join(' | ')+' | '+(row.accepted?'Accepted':'Excluded'));text('details',JSON.stringify(row.details,null,2));draw();}
function draw(){const w=Math.max(300,Math.min(1000,Math.round(canvas.getBoundingClientRect().width))),h=w<550?340:420,dpr=Math.min(2,window.devicePixelRatio||1);canvas.width=w*dpr;canvas.height=h*dpr;canvas.style.height=h+'px';ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#112b37';ctx.fillRect(0,0,w,h);
const eligible=s.rows.filter(r=>r.depth!==null&&(r.accepted||excluded.checked)),values=eligible.flatMap(r=>r.values.filter(v=>v!==null));
if(!values.length){ctx.fillStyle='#e1eeee';ctx.font='18px system-ui';ctx.fillText('No eligible saved values in this view.',65,60);return;}
let lo=Math.min(...values),hi=Math.max(...values);if(lo===hi){lo-=.5;hi+=.5;}const max=Math.max(1,...eligible.map(r=>r.depth)),x=v=>80+(v-lo)/(hi-lo)*(w-100),y=z=>30+z/max*(h-100);
ctx.strokeStyle='#6a8592';ctx.beginPath();ctx.moveTo(80,30);ctx.lineTo(80,h-70);ctx.lineTo(w-20,h-70);ctx.stroke();ctx.fillStyle='#dce8ec';ctx.font='14px system-ui';ctx.fillText(lo.toPrecision(5),80,h-45);ctx.textAlign='right';ctx.fillText(hi.toPrecision(5),w-20,h-45);ctx.textAlign='left';ctx.fillText(s.units+' (horizontal)',80,h-18);ctx.fillText('Depth (m), positive down',6,17);for(let i=0;i<=4;i++){const z=max*i/4;ctx.fillText(z.toFixed(1),6,y(z)+4);ctx.strokeStyle='#37515e';ctx.beginPath();ctx.moveTo(80,y(z));ctx.lineTo(w-20,y(z));ctx.stroke();}
const colors=['#94e1cc','#f7b38a'];eligible.forEach(r=>r.values.forEach((v,k)=>{if(v===null)return;ctx.strokeStyle=r.accepted?colors[k%2]:'#eaa76f';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.arc(x(v),y(r.depth),3,0,Math.PI*2);if(r.accepted)ctx.fill();else ctx.stroke();}));
const pick=s.rows[sample.selectedIndex];if(pick.depth!==null){ctx.strokeStyle='#fff';ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(80,y(pick.depth));ctx.lineTo(w-20,y(pick.depth));ctx.stroke();ctx.setLineDash([]);}
}
function fill(){s=series[view.selectedIndex];sample.replaceChildren();s.rows.forEach((r,i)=>{const o=document.createElement('option');o.textContent=i+' | '+(r.depth===null?'Missing depth':r.depth+' m')+(r.accepted?'':' | Excluded');sample.append(o);});text('source-date',(s.context.observation_start?'Observed: '+s.context.observation_start+' to '+s.context.observation_end+'. ':'')+(s.context.model_time?'Model snapshot: '+s.context.model_time+'.':''));text('context',JSON.stringify(s.context,null,2));text('key',s.keys.map((k,i)=>k+': '+(i===0?'mint':'peach')).join(' | ')+'. Dots are saved samples at their actual depths. Missing values are not drawn. No interpolation or new calculation.');detail();}
view.onchange=fill;sample.onchange=detail;excluded.onchange=draw;
el('previous').onclick=()=>{sample.selectedIndex=Math.max(0,sample.selectedIndex-1);detail();};el('next').onclick=()=>{sample.selectedIndex=Math.min(s.rows.length-1,sample.selectedIndex+1);detail();};
el('json').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(record)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='ocean-investigation.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};el('controls').hidden=false;fill();new ResizeObserver(()=>draw()).observe(canvas);
}catch(e){text('status',e.message||'The file could not be verified.');}})();`;

export async function offlineInvestigation(raw:Investigation){
  const record=await verifyInvestigation(raw),recordText=JSON.stringify(record);
  if(new TextEncoder().encode(recordText).length>MAX_FILE_BYTES)throw new Error('Offline export supports investigation records up to 8 MB.');
  const series=offlineSeries(record);
  if(!series.length)throw new Error('Offline charts support saved observation profiles, comparisons and native model columns. Keep JSON or a readable report for this laboratory.');
  const text=JSON.stringify({record,series});
  if(new TextEncoder().encode(text).length>16_000_000)throw new Error('The offline file exceeds its 16 MB data budget. Keep an investigation JSON instead.');
  const sha=async(value:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('');
  const envelope=JSON.stringify({text,sha256:await sha(text)}).replace(/</g,'\\u003c');
  const scriptHash=btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(script)))));
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; img-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-${scriptHash}'; base-uri 'none'; form-action 'none'"><title>Depth Atlas | Offline investigation</title><style>body{font:16px system-ui;background:#0c1b26;color:#dce8ec;max-width:1000px;margin:auto;padding:24px}h1{font-size:26px}button,select{font:inherit;padding:9px;background:#17323f;color:inherit;border:1px solid #607c89;border-radius:4px;max-width:100%;margin:4px 0}label{display:block;margin:12px 0}canvas{width:100%;height:auto;background:#112b37}p{line-height:1.5}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}details{margin:16px 0}#readout{padding:14px;background:#17323f}h1,p{overflow-wrap:anywhere}[hidden]{display:none}@media(max-width:500px){body{padding:12px}}</style></head><body><h1 id="title">Offline investigation</h1><p id="status" role="status">Checking file integrity...</p><p id="date"></p><p id="age"></p><p>This file opens on its own. Recalculation, new data and 3D navigation require Depth Atlas online. Keep source credits when sharing. Delete this HTML file to remove this downloaded copy; browser records are separate.</p><div id="controls" hidden><label>Saved view <select id="view"></select></label><p id="source-date"></p><canvas id="chart" role="img" aria-label="Saved values against actual depth"></canvas><p id="key"></p><label><input type="checkbox" id="excluded"> Show excluded values as hollow points</label><label>Source sample <select id="sample"></select></label><button id="previous">Previous sample</button> <button id="next">Next sample</button><p id="readout" aria-live="polite"></p><details><summary>Selected sample and quality flags</summary><pre id="details"></pre></details><details><summary>Variable, dates and method</summary><pre id="context"></pre></details><button id="json">Download original investigation JSON</button></div><details><summary>Sources, file inventory and limitations</summary><pre id="sources"></pre></details><script type="application/json" id="payload">${envelope}</script><script>${script}</script></body></html>`;
}
