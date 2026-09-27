import { ApiError, appVersion } from '../contracts';

export type Reading={value:number|null;qc:string;accepted:boolean;reason:string;raw:number|null;raw_qc:string;adjusted:number|null;adjusted_qc:string;adjusted_error:number|null};
export type Measurement={index:number;depth_m:number|null;pressure_dbar:number|null;latitude:number;longitude:number;time:string;coordinate_status:string;coordinate_qc:Record<string,string>;coordinate_eligible:boolean;readings:Record<string,Reading>};
export type Parameter={label:string;units:string;definition:string;source_field:string;mode:string;qc_scheme:string;accepted_count:number};
export type InstrumentSummary={id:string;instrument:'argo'|'bgc'|'ctd'|'glider';platform:string;title:string;time:string;time_end:string;latitude:number;longitude:number;samples:number;depth_range_m:[number,number]|null;parameters:Record<string,Parameter>;collection:string;source_url:string;source_file:string;source_sha256:string;track:[number,number][]};
export type InstrumentProfile=InstrumentSummary & {schema_version:'2';kind:'observation';depth_method:string;qc_policy:string;warnings:string[];metadata:Record<string,unknown>;levels:Measurement[]};
export type Example={name:string;format:string;bytes:number;sha256:string;source_url:string;collection:string};
export type InstrumentCatalog={schema_version:'2';profiles:InstrumentSummary[];examples:Example[];limitations:string[]};
export type ImportResult={schema_version:'2';format:string;profiles:InstrumentProfile[];warnings:string[];persistence:'request_only'};
const object=(x:unknown):x is Record<string,unknown>=>Boolean(x)&&typeof x==='object'&&!Array.isArray(x);
const finite=(x:unknown):x is number=>typeof x==='number'&&Number.isFinite(x);
const nullable=(x:unknown)=>x===null||finite(x);
const date=(x:unknown)=>typeof x==='string'&&Number.isFinite(Date.parse(x))&&x.endsWith('Z');
const stringArray=(x:unknown)=>Array.isArray(x)&&x.every(v=>typeof v==='string');
export function safeSource(url:string){return /^https:\/\//i.test(url)?url:undefined;}
function summary(x:unknown):x is InstrumentSummary & Record<string,unknown> {
  if(!object(x)||!['argo','bgc','ctd','glider'].includes(String(x.instrument))||!['id','platform','title','collection','source_url','source_file','source_sha256'].every(k=>typeof x[k]==='string')||!date(x.time)||!date(x.time_end)||!finite(x.latitude)||Math.abs(x.latitude)>90||!finite(x.longitude)||Math.abs(x.longitude)>180||!Number.isInteger(x.samples)||Number(x.samples)<1||Number(x.samples)>5000||!object(x.parameters))return false;
  if(!Object.keys(x.parameters).length||!Object.values(x.parameters).every(p=>object(p)&&['label','units','definition','source_field','mode','qc_scheme'].every(k=>typeof p[k]==='string')&&Number.isInteger(p.accepted_count)&&Number(p.accepted_count)>=0&&Number(p.accepted_count)<=Number(x.samples)))return false;
  return Array.isArray(x.track)&&x.track.length<=5000&&x.track.every(p=>Array.isArray(p)&&p.length===2&&p.every(finite)&&Math.abs(p[0])<=180&&Math.abs(p[1])<=90)&&(x.depth_range_m===null||Array.isArray(x.depth_range_m)&&x.depth_range_m.length===2&&x.depth_range_m.every(finite));
}
export function parseInstrumentCatalog(x:unknown):InstrumentCatalog{
  if(!object(x)||x.schema_version!=='2'||!Array.isArray(x.profiles)||!x.profiles.every(summary)||new Set(x.profiles.map(p=>p.id)).size!==x.profiles.length||!Array.isArray(x.examples)||!x.examples.every(e=>object(e)&&['name','format','sha256','source_url','collection'].every(k=>typeof e[k]==='string')&&finite(e.bytes))||!stringArray(x.limitations))throw new ApiError('The observation catalogue could not be verified.',undefined,'response');
  return x as InstrumentCatalog;
}
export function parseInstrument(x:unknown):InstrumentProfile{
  if(!summary(x)||!object(x)||x.schema_version!=='2'||x.kind!=='observation'||!stringArray(x.warnings)||typeof x.depth_method!=='string'||typeof x.qc_policy!=='string'||!object(x.metadata)||!Array.isArray(x.levels)||x.levels.length!==x.samples)throw new ApiError('The observation profile could not be verified.',undefined,'response');
  const keys=Object.keys(x.parameters);
  for(const l of x.levels){
    if(!object(l)||typeof l.coordinate_eligible!=='boolean'||!object(l.coordinate_qc)||!Object.values(l.coordinate_qc).every(q=>typeof q==='string'))throw new ApiError('Observation coordinate quality is missing.',undefined,'response');
    if(!object(l)||!Number.isInteger(l.index)||!nullable(l.depth_m)||!nullable(l.pressure_dbar)||!finite(l.latitude)||!finite(l.longitude)||Math.abs(l.latitude)>90||Math.abs(l.longitude)>180||!date(l.time)||typeof l.coordinate_status!=='string'||!object(l.readings)||!keys.every(k=>{const r=(l.readings as Record<string,unknown>)[k];return object(r)&&['value','raw','adjusted','adjusted_error'].every(f=>nullable(r[f]))&&['qc','reason','raw_qc','adjusted_qc'].every(f=>typeof r[f]==='string')&&typeof r.accepted==='boolean'&&(!r.accepted||finite(r.value)&&finite(l.depth_m));}))throw new ApiError('Observation coordinates, samples or QC are inconsistent.',undefined,'response');
  }
  for(const k of keys)if(x.levels.filter(l=>l.readings[k].accepted).length!==x.parameters[k].accepted_count)throw new ApiError('The profile quality counts do not match its samples.',undefined,'response');
  return x as InstrumentProfile;
}
export async function importInstruments(file:File,signal?:AbortSignal):Promise<ImportResult>{
  if(file.size>2_000_000||!file.size)throw new Error('Choose a non-empty file no larger than 2 MB.');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
  try{
    const response=await fetch(`/api/instruments/import?filename=${encodeURIComponent(file.name)}`,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'},signal:signal?AbortSignal.any([signal,controller.signal]):controller.signal});
    if(response.headers.get('X-Ocean-App-Version')!==appVersion)throw new Error('Reload the workspace to use the latest import reader.');
    const data:unknown=await response.json();
    if(!response.ok)throw new Error(object(data)&&object(data.error)&&typeof data.error.message==='string'?data.error.message:'The file could not be read.');
    if(!object(data)||data.schema_version!=='2'||data.persistence!=='request_only'||typeof data.format!=='string'||!Array.isArray(data.profiles)||data.profiles.length>24||!stringArray(data.warnings))throw new Error('The import response could not be verified.');
    return {...data,profiles:data.profiles.map(parseInstrument)} as ImportResult;
  }catch(error){if(controller.signal.aborted)throw new Error('Import took too long. Try a smaller file or retry.');throw error;}
  finally{clearTimeout(timer);}
}
