import { useEffect, useRef, useState } from 'react';
import { Download } from 'lucide-react';
import { appVersion } from '../contracts';
import { parseInstrument, safeSource, type InstrumentCatalog, type InstrumentProfile, type ImportResult } from './contracts';
import { retainSource, type ImportedSource, type ImportSources, type Mapping } from './imported';

import { checkBatch, mergeImported, importLimits } from './batch';

type Review = {schema_version:'1';parser_version:string;source_sha256:string;columns:string[];mapping_supported:boolean;ignored_fields:string[];result:ImportResult|null;issue:string|null};
const required = ['profile_id','instrument','platform','time','latitude','longitude','pressure_dbar','pressure_qc','position_qc','time_qc'];
const measurements = [
  {field:'temperature_c',label:'In-situ temperature',qc:'temperature_qc',units:['degC','K']},
  {field:'salinity_psu',label:'Practical salinity',qc:'salinity_qc',units:['psu','PSS-78']},
  {field:'oxygen_umol_kg',label:'Dissolved oxygen',qc:'oxygen_qc',units:['umol/kg']},
  {field:'chlorophyll_mg_m3',label:'Chlorophyll a',qc:'chlorophyll_qc',units:['mg/m3','ug/L','mg/L']},
  {field:'nitrate_umol_kg',label:'Nitrate',qc:'nitrate_qc',units:['umol/kg']},
];
const date = (s:string) => s.replace('T',' ').replace('Z',' UTC');
const number = (n:number) => n.toLocaleString('en-US',{maximumFractionDigits:2});

export async function inspectFile(file:File,mapping:Mapping|undefined,signal:AbortSignal):Promise<Review>{
  if(!file.size||file.size>2_000_000)throw new Error('Choose a non-empty file no larger than 2 MB.');
  const headers:Record<string,string>={'Content-Type':'application/octet-stream'};
  if(mapping)headers['X-Ocean-Column-Mapping']=encodeURIComponent(JSON.stringify(mapping));
  const response=await fetch(`/api/instruments/inspect?filename=${encodeURIComponent(file.name)}`,{method:'POST',body:file,headers,signal});
  if(response.headers.get('X-Ocean-App-Version')!==appVersion)throw new Error('Reload the workspace to use the latest import reader.');
  const data=await response.json();
  if(!response.ok)throw new Error(data?.error?.message??'The file could not be inspected.');
  if(data?.schema_version!=='1'||typeof data.parser_version!=='string'||typeof data.source_sha256!=='string'||typeof data.mapping_supported!=='boolean'||![data.columns,data.ignored_fields].every(x=>Array.isArray(x)&&x.every(v=>typeof v==='string'))||(data.issue!==null&&typeof data.issue!=='string'))throw new Error('The import review response could not be verified.');
  if(data.result){
    const r=data.result;
    if(r.schema_version!=='2'||r.persistence!=='request_only'||typeof r.format!=='string'||!Array.isArray(r.profiles)||!r.profiles.length||r.profiles.length>24||!Array.isArray(r.warnings))throw new Error('The parsed import could not be verified.');
    r.profiles=r.profiles.map(parseInstrument);
  }
  return data;
}

type QueueEntry={id:number;file:File;status:'queued'|'reading'|'ready'|'needs mapping'|'failed'|'added'|'cancelled';review?:Review;source?:ImportedSource;error?:string};
export function useImportReview(imports:InstrumentProfile[],onImport:(p:InstrumentProfile[],source:ImportedSource)=>void,onSelect:(id:string)=>void,sources:ImportSources={}){
  const [queue,setQueue]=useState<QueueEntry[]>([]),[selected,setSelected]=useState(0),[uploading,setUploading]=useState(false),[uploadError,setUploadError]=useState(''),[uploadMessage,setUploadMessage]=useState('');
  const running=useRef<AbortController|null>(null),sequence=useRef(0),entries=useRef<QueueEntry[]>([]),workspace=useRef({profiles:imports,sources});
  workspace.current={profiles:imports,sources};
  const current=queue.find(e=>e.id===selected),file=current?.file,review=current?.status==='added'?undefined:current?.review;
  function update(id:number,patch:Partial<QueueEntry>){entries.current=entries.current.map(e=>e.id===id?{...e,...patch}:e);setQueue(entries.current);}
  function replace(items:QueueEntry[]){entries.current=items;setQueue(items);setSelected(items[0]?.id??0);}
  useEffect(()=>()=>{sequence.current++;running.current?.abort();},[]);
  function accept(entry:QueueEntry){
    if(!entry.review?.result||!entry.source||entry.status==='added')return;
    const result=entry.review.result,incoming=result.profiles.map(p=>({...p,id:`import-${p.id}`,collection:`Imported \u00b7 ${entry.file.name}`,metadata:{...p.metadata,original_profile_id:p.id}}));
    workspace.current=mergeImported(workspace.current.profiles,incoming,workspace.current.sources,entry.source);
    onImport(incoming,entry.source);onSelect(incoming[0].id);update(entry.id,{status:'added',review:undefined,source:undefined,error:undefined});
    setUploadMessage(`${result.format}: ${incoming.length} profile${incoming.length===1?'':'s'} added. Stored only in this open workspace.`);
  }
  async function process(items:QueueEntry[],signal?:AbortSignal,autoAccept=false,mapping?:Mapping){
    running.current?.abort();const controller=new AbortController();running.current=controller;const version=++sequence.current;
    setUploading(true);setUploadError('');setUploadMessage('');
    const combined=signal?AbortSignal.any([signal,controller.signal]):controller.signal;
    try{for(const entry of items){
      if(combined.aborted||version!==sequence.current)break;
      update(entry.id,{status:'reading',error:undefined});let timedOut=false;
      const perFile=new AbortController(),timer=setTimeout(()=>{timedOut=true;perFile.abort();},30000);
      try{
        const result=await inspectFile(entry.file,mapping,AbortSignal.any([combined,perFile.signal]));
        const retained=await retainSource(entry.file,result.source_sha256,result.parser_version,mapping);
        if(version!==sequence.current||combined.aborted)break;
        const otherBytes=entries.current.filter(e=>e.id!==entry.id&&e.review).reduce((n,e)=>n+new TextEncoder().encode(JSON.stringify(e.review)).length,0);
        if(otherBytes+new TextEncoder().encode(JSON.stringify(result)).length>importLimits.decodedBytes)throw new Error('The review queue reached its 24 MB decoded-data limit. Earlier previews are kept. Add or discard them before retrying.');
        const patch={status:result.result?'ready' as const:'needs mapping' as const,review:result,source:retained,error:undefined};
        update(entry.id,patch);if(autoAccept&&result.result)accept({...entry,...patch});
      }catch(error){if(version!==sequence.current||combined.aborted)break;const message=timedOut?'Import review took too long. Existing profiles are unchanged. Retry this file.':error instanceof Error?error.message:'Import could not be completed.';update(entry.id,{status:'failed',error:message,review:undefined,source:undefined});setUploadError(message);}
      finally{clearTimeout(timer);}
    }}finally{if(version===sequence.current){setUploading(false);if(combined.aborted){entries.current=entries.current.map(e=>['queued','reading'].includes(e.status)?{...e,status:'cancelled'}:e);setQueue(entries.current);}}}
  }
  async function uploadBatch(files:File[],signal?:AbortSignal){
    if(!files.length)return;
    try{checkBatch(files);}catch(e){setUploadError(e instanceof Error?e.message:'Batch limit exceeded.');return;}
    const items=files.map((file,id)=>({id,file,status:'queued' as const}));replace(items);await process(items,signal);
  }
  async function upload(next?:File,signal?:AbortSignal,autoAccept=false,mapping?:Mapping){
    if(!next)return;
    if(mapping&&current){update(current.id,{review:current.review?{...current.review,result:null,issue:'Review the selected mappings.'}:undefined});await process([{...current,file:next}],signal,autoAccept,mapping);}
    else{const item:QueueEntry={id:0,file:next,status:'queued'};replace([item]);await process([item],signal,autoAccept);}
  }
  async function previewExample(name:string){
    running.current?.abort();const controller=new AbortController();running.current=controller;const version=++sequence.current;
    setUploading(true);setUploadError('');setUploadMessage('');const timer=setTimeout(()=>controller.abort(),30000);
    try{const response=await fetch(`/api/instruments/examples/${encodeURIComponent(name)}`,{signal:controller.signal});if(!response.ok)throw new Error('The example could not be loaded. Existing profiles are unchanged.');const blob=await response.blob();if(version!==sequence.current||controller.signal.aborted)return;clearTimeout(timer);await upload(new File([blob],name));}
    catch(e){if(version===sequence.current)setUploadError(controller.signal.aborted?'The example download timed out. Try again.':e instanceof Error?e.message:'The example could not be loaded.');}
    finally{clearTimeout(timer);if(version===sequence.current)setUploading(false);}
  }
  function confirm(all=false){setUploadError('');for(const entry of all?entries.current:current?[current]:[]){if(entry.status!=='ready')continue;try{accept(entry);}catch(e){const error=e instanceof Error?e.message:'The profiles could not be added.';update(entry.id,{error});setUploadError(error);break;}}}
  return {file,review,queue,selected,select:(id:number)=>{setSelected(id);setUploadError(entries.current.find(e=>e.id===id)?.error??'');},uploading,uploadError,uploadMessage,setUploadMessage,setUploadError,upload,uploadBatch,previewExample,
    retry:()=>{if(current)void process([current]);},
    cancel:()=>{sequence.current++;running.current?.abort();setUploading(false);entries.current=entries.current.map(e=>['reading','queued'].includes(e.status)?{...e,status:'cancelled'}:e);setQueue(entries.current);setUploadMessage('Import review cancelled. Completed previews and existing profiles are kept.');},
    discard:()=>{if(current)update(current.id,{status:'cancelled',review:undefined,source:undefined,error:undefined});setUploadMessage('Preview discarded. Existing profiles are unchanged.');},
    confirm:()=>confirm(),confirmAll:()=>confirm(true),
  };
}

export function ImportReviewPanel({state,catalog,imports,onClear}:{state:ReturnType<typeof useImportReview>;catalog?:InstrumentCatalog;imports:InstrumentProfile[];onClear:()=>void}){
  const {file,review,uploading,uploadError,uploadMessage}=state;
  const [mapping,setMapping]=useState<Mapping>({}),[mappingChanged,setMappingChanged]=useState(false);
  const examples=useRef<HTMLDetailsElement>(null);
  useEffect(()=>{setMappingChanged(false);if(review&&examples.current)examples.current.open=false;},[review]);
  useEffect(()=>{setMapping({});setMappingChanged(false);},[state.selected,file]);
  function source(target:string,units?:string){return <select aria-label={`Source column for ${target}`} value={target in mapping?(mapping[target]?.source??''):(review?.columns.includes(target)?target:'')} onChange={e=>{setMappingChanged(true);setMapping(old=>({...old,[target]:e.target.value?{source:e.target.value,...(units?{units:e.target.value===target?units:''}:{})}:null}));}}><option value="">Not selected</option>{review?.columns.map(c=><option key={c}>{c}</option>)}</select>;}
  const profiles=review?.result?.profiles??[];
  const keys=[...new Set(profiles.flatMap(p=>Object.keys(p.parameters)))];
  return <section className="import-panel" aria-label="Import observations">
    <h3>Review a file, then add it</h3><p>Your file is sent to this app's Vercel service for parsing. Added profiles stay in this tab until cleared or reloaded. Save investigation keeps the original file on this browser only when you choose it.</p>
    <label className="file-label">Choose NetCDF or CSV <input type="file" multiple accept=".nc,.csv,.txt" disabled={uploading} onChange={e=>{setMapping({});void state.uploadBatch(Array.from(e.target.files??[]));e.target.value='';}}/></label>
    <p className="muted">Up to 8 files at once, 2 MB per file. Review each result before adding.</p><details><summary>File formats and workspace limits</summary><p>Each file supports up to 24 profiles and 5,000 samples. Workspace: 32 profiles or 20,000 samples, 16 MB originals and 24 MB decoded data. The review queue has separate 16 MB original and 24 MB decoded limits. Native Argo/BGC, IOOS glider subsets, CTD Exchange and supported CSV tables.</p></details>
    {state.queue.length>1&&<div className="import-batch" aria-label="File review queue"><h4>Files in this batch</h4><ol>{state.queue.map(e=><li key={e.id}><button className="secondary-button" aria-pressed={state.selected===e.id} onClick={()=>state.select(e.id)}>{e.file.name}</button><span>{e.status}</span>{e.error&&<small>{e.error}</small>}</li>)}</ol><button className="primary-button" disabled={uploading||mappingChanged||!state.queue.some(e=>e.status==='ready')} onClick={state.confirmAll}>Add all reviewed files</button><p>Only ready files are added. Failed files do not remove earlier results.</p></div>}
    {state.queue.find(e=>e.id===state.selected)?.status.match(/failed|cancelled/)&&<button className="secondary-button" disabled={uploading} onClick={state.retry}>Retry selected file</button>}
    {uploading&&<div role="status" className="import-pending"><p>Reading file {state.queue.find(e=>e.status==='reading')?`${state.queue.findIndex(e=>e.status==='reading')+1} of ${state.queue.length}: ${state.queue.find(e=>e.status==='reading')?.file.name}`:'example'}. Checking coordinates, variables and quality flags...</p><button className="secondary-button" onClick={state.cancel}>Cancel review</button></div>}
    {uploadError&&<p role="alert" className="instrument-error">{uploadError}</p>}{uploadMessage&&<p role="status">{uploadMessage}</p>}
    {review&&<div className="import-review" aria-label="Import preview">
      <h4>{file?.name}</h4>{review.issue&&<p role="alert" className="instrument-warning">{review.issue}</p>}
      {profiles.length>0&&<><p>{profiles.length} profiles · {profiles.reduce((n,p)=>n+p.samples,0).toLocaleString()} source samples. Review below before adding.</p>
        <div className="import-table-scroll"><table><caption>Detected variables and quality</caption><thead><tr><th>Variable / units</th><th>Accepted</th><th>Excluded</th><th>Missing</th></tr></thead><tbody>{keys.map(k=>{const ps=profiles.filter(p=>p.parameters[k]),readings=ps.flatMap(p=>p.levels.map(l=>l.readings[k]));return <tr key={k}><th>{ps[0].parameters[k].label}<small>{ps[0].parameters[k].units}</small></th><td>{readings.filter(r=>r.accepted).length}</td><td>{readings.filter(r=>!r.accepted&&r.value!==null).length}</td><td>{readings.filter(r=>r.value===null).length}</td></tr>;})}</tbody></table></div>
        <details><summary>Locations, dates, depth and exclusions</summary>{profiles.map(p=><div className="import-profile-summary" key={p.id}><strong>{p.title}</strong><p>{date(p.time)} to {date(p.time_end)}<br/>{number(p.latitude)}° latitude, {number(p.longitude)}° longitude at first sample<br/>Latitude span {number(Math.min(...p.levels.map(l=>l.latitude)))} to {number(Math.max(...p.levels.map(l=>l.latitude)))} degrees; longitude span {number(Math.min(...p.levels.map(l=>l.longitude)))} to {number(Math.max(...p.levels.map(l=>l.longitude)))} degrees<br/>{p.depth_range_m?`${number(p.depth_range_m[0])} to ${number(p.depth_range_m[1])} m depth`:'No eligible depth'} · pressure in dbar</p>{safeSource(p.source_url)&&<a href={safeSource(p.source_url)} target="_blank" rel="noreferrer">Original source</a>}<p>{p.qc_policy}</p><ul>{[...new Set(p.levels.flatMap(l=>Object.values(l.readings).filter(r=>!r.accepted).map(r=>r.reason)))].map(reason=><li key={reason}>{reason}</li>)}</ul>{p.warnings.map(w=><p key={w}>{w}</p>)}</div>)}</details>
        {mappingChanged&&<p role="status">Review the mapped file before adding these profiles.</p>}<div className="import-actions"><button className="primary-button" disabled={mappingChanged||uploading} onClick={state.confirm}>Add profiles to workspace</button><button className="secondary-button" onClick={state.discard}>Discard preview</button></div>
      </>}
      {review.ignored_fields.length>0&&<details><summary>Fields not visualized ({review.ignored_fields.length})</summary><p>{review.ignored_fields.join(', ')}</p><p>These fields are not interpreted or substituted for supported quantities.</p></details>}
      {review.mapping_supported&&<details className="import-mapping" open={review.result?undefined:true}><summary>Map supported CSV columns</summary><p>Choose the source column for each required field and at least one measurement with QC. Coordinates must be WGS84 degrees, time must include a timezone, and pressure must already be sea pressure in dbar. QC uses declared CSV flags 1/2, not QARTOD or WOCE flags.</p>
        <div className="mapping-grid">{required.map(f=><label key={f}>{f}{source(f)}</label>)}</div>
        {measurements.map(m=><fieldset key={m.field}><legend>{m.label}</legend><div className="mapping-grid"><label>Value column{source(m.field,m.units[0])}</label><label>Source units<select aria-label={`Source units for ${m.field}`} value={m.field in mapping?(mapping[m.field]?.units??''):(review.columns.includes(m.field)?m.units[0]:'')} onChange={e=>{setMappingChanged(true);setMapping(old=>({...old,[m.field]:{source:old[m.field]?.source??(review.columns.includes(m.field)?m.field:''),units:e.target.value}}));}}><option value="">Choose units</option>{m.units.map(u=><option key={u}>{u}</option>)}</select></label><label>Quality flag column{source(m.qc)}</label></div></fieldset>)}
        <p>Kelvin converts to Celsius by subtracting 273.15. Chlorophyll mg/L converts to mg/m³ by multiplying by 1,000; µg/L and mg/m³ have equal numerical values. No mass/volume oxygen conversion or salinity redefinition is offered. Blank values stay missing; replace source-specific missing sentinels with blanks before importing.</p>
        <button className="secondary-button" disabled={uploading} onClick={()=>void state.upload(file,undefined,false,mapping)}>Review mapped file</button>
      </details>}
      {!review.mapping_supported&&<p>Native variable names, units and QC are read from the source metadata. A different NetCDF layout needs an adapter.</p>}
    </div>}
    <details ref={examples}><summary>Formats and genuine example files</summary><a href="/observation-import-guide.txt" target="_blank" rel="noreferrer">Column and metadata guide</a><div className="example-files">{catalog?.examples.map(e=><div className="example-file" key={e.name}><span>{e.name}<small>{e.format} · {e.collection}</small></span><div><button className="secondary-button" disabled={uploading} onClick={()=>{setMapping({});void state.previewExample(e.name);}} aria-label={`Preview ${e.name}`}>Preview example</button><a href={`/api/instruments/examples/${encodeURIComponent(e.name)}`} download aria-label={`Download ${e.name}`}><Download size={14}/>Download</a></div></div>)}</div></details>
    {imports.length>0&&<button className="secondary-button" disabled={uploading} onClick={()=>{onClear();state.setUploadMessage('Imported profiles cleared from this workspace.');state.setUploadError('');}}>Clear imported profiles</button>}
  </section>;
}
