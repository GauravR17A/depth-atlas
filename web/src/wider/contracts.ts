import { ApiError, appVersion } from '../contracts';

export type WideQuery={dataset:'godas-2022'|'gobai-v2.2';variable:'potential_temperature'|'source_salinity'|'oxygen'|'oxygen_uncertainty';time_index:number;west:number;east:number;south:number;north:number;level_min:number;level_max:number;resolution:'preview'|'display'|'native'};
export type WideDataset={id:WideQuery['dataset'];title:string;kind:'model_analysis'|'ml_derived';version:string;provider:string;vertical_name:string;vertical_units:'m'|'dbar';reference:string;citation:string;licence:string;source_sha256:string;latitude_range:[number,number];level_range:[number,number];levels:number[];times:string[];intervals:[string,string][];shape:number[];instrument_availability:string;retrieved_at:string;limitations:string[];variables:Partial<Record<WideQuery['variable'],{label:string;units:string;definition:string;paint:[number,number]}>>;uncertainty_definition?:string;model_version?:string;training_reference?:string;validation_reference?:string};
export type WideCatalog={schema_version:'p15-1';method:'p15-native-subset-v1';datasets:WideDataset[];limits:Record<string,number>;presets:{id:string;label:string;bounds:[number,number,number,number]}[]};
export type WideField={schema_version:'p15-1';method:'p15-native-subset-v1';query:WideQuery;dataset:WideDataset;source_sha256:string;file_sha256:string;shape:[number,number,number];native_shape:[number,number,number];levels:number[];latitude:number[];longitude:number[];values:(number|null)[];units:string;kind:WideDataset['kind'];time:string;valid_count:number;source_indices:{level:number[];latitude:number[];longitude:number[]};processing:string[]};
export type WideProfile={levels:number[];values:(number|null)[];longitude:number;latitude:number;units:string;vertical_units:string;source_sha256:string;source_indices:{level:number[];latitude:number;longitude:number}};
export type WidePack={schema_version:'p15-pack-1';method:'p15-native-subset-v1';payload_text:string;sha256:string};
export const METHOD='p15-native-subset-v1';
export const DEFAULT_QUERY:WideQuery={dataset:'godas-2022',variable:'potential_temperature',time_index:0,west:-65,east:-45,south:25,north:40,level_min:5,level_max:459,resolution:'display'};
const object=(x:unknown):x is Record<string,any>=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const number=(x:unknown):x is number=>typeof x==='number'&&Number.isFinite(x);
const hash=(x:unknown):x is string=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const axis=(x:unknown):x is number[]=>Array.isArray(x)&&x.length>0&&x.length<=500&&x.every((v,i)=>number(v)&&(i===0||v>x[i-1]));
const textList=(x:unknown):x is string[]=>Array.isArray(x)&&x.every(v=>typeof v==='string');
const fail=()=>{throw new ApiError('The regional data response could not be verified.',undefined,'response');};
const shape=(x:unknown):x is number[]=>Array.isArray(x)&&x.length===3&&x.every(v=>number(v)&&Number.isInteger(v)&&v>0)&&x.reduce((a,b)=>a*b,1)<=120000;
function query(x:unknown):x is WideQuery{
 if(!object(x)||!['west','east','south','north','level_min','level_max'].every(k=>number(x[k]))||![0,1].includes(x.time_index))return false;
 const width=((x.east-x.west)%360+360)%360;
 return Math.abs(x.west)<=180&&Math.abs(x.east)<=180&&width>0&&width<=90&&x.south>=-90&&x.north<=90&&x.north>x.south&&x.north-x.south<=40&&x.level_min>=0&&x.level_max>=x.level_min&&x.level_max<=5000;
}
function dataset(x:unknown):x is WideDataset{
 return object(x)&&['godas-2022','gobai-v2.2'].includes(x.id)&&(x.id==='godas-2022'?x.vertical_units==='m'&&x.kind==='model_analysis':x.vertical_units==='dbar'&&x.kind==='ml_derived')&&hash(x.source_sha256)&&axis(x.levels)&&textList(x.times)&&x.times.length===2&&x.times.every(t=>Number.isFinite(Date.parse(t)))&&Array.isArray(x.intervals)&&x.intervals.length===2&&x.intervals.every((a:unknown)=>Array.isArray(a)&&a.length===2&&a.every(t=>typeof t==='string'&&Number.isFinite(Date.parse(t)))&&Date.parse(a[0])<Date.parse(a[1]))&&object(x.variables)&&Object.values(x.variables).every((v:unknown)=>object(v)&&typeof v.label==='string'&&typeof v.units==='string'&&typeof v.definition==='string'&&Array.isArray(v.paint)&&v.paint.length===2&&v.paint.every(number)&&v.paint[0]<v.paint[1])&&textList(x.limitations)&&['title','version','provider','vertical_name','reference','citation','licence','instrument_availability','retrieved_at'].every(k=>typeof x[k]==='string')&&x.reference.startsWith('https://')&&[x.latitude_range,x.level_range].every(a=>Array.isArray(a)&&a.length===2&&a.every(number)&&a[0]<a[1]);
}
export function parseWideCatalog(x:unknown):WideCatalog{
 if(!object(x)||x.schema_version!=='p15-1'||x.method!==METHOD||!Array.isArray(x.datasets)||!x.datasets.length||!x.datasets.every(dataset)||!object(x.limits)||!Array.isArray(x.presets)||!x.presets.every((p:unknown)=>object(p)&&typeof p.id==='string'&&typeof p.label==='string'&&Array.isArray(p.bounds)&&p.bounds.length===4&&p.bounds.every(number)))return fail();return x as WideCatalog;
}
export function parseWideField(x:unknown):WideField{
 if(!object(x)||!query(x.query)||!shape(x.shape)||!shape(x.native_shape)||x.shape.some((v:number,i:number)=>v>x.native_shape[i])||!Array.isArray(x.latitude)||!Array.isArray(x.longitude)||x.latitude.length<2||x.longitude.length<2)return fail();
 if(!object(x)||x.schema_version!=='p15-1'||x.method!==METHOD||!dataset(x.dataset)||!object(x.query)||!['preview','display','native'].includes(x.query.resolution)||x.query.dataset!==x.dataset.id||!x.dataset.variables[x.query.variable as WideQuery['variable']]||!hash(x.source_sha256)||x.source_sha256!==x.dataset.source_sha256||!hash(x.file_sha256)||!Array.isArray(x.shape)||x.shape.length!==3||!x.shape.every((v:unknown)=>number(v)&&Number.isInteger(v)&&v>0)||x.shape.reduce((a:number,b:number)=>a*b,1)>120000||!axis(x.levels)||!axis(x.latitude)||!axis(x.longitude)||[x.levels.length,x.latitude.length,x.longitude.length].some((v,i)=>v!==x.shape[i])||!Array.isArray(x.values)||x.values.length!==x.shape.reduce((a:number,b:number)=>a*b,1)||!x.values.every((v:unknown)=>v===null||number(v))||x.values.filter((v:unknown)=>v!==null).length!==x.valid_count||!object(x.source_indices)||!['level','latitude','longitude'].every((key,i)=>Array.isArray(x.source_indices[key])&&x.source_indices[key].length===x.shape[i]&&new Set(x.source_indices[key]).size===x.shape[i]&&x.source_indices[key].every((v:unknown)=>number(v)&&Number.isInteger(v)&&v>=0))||!textList(x.processing)||x.kind!==x.dataset.kind||x.time!==x.dataset.times[x.query.time_index]||x.units!==x.dataset.variables[x.query.variable as WideQuery['variable']]?.units)return fail();
 return x as WideField;
}
export function parseWideProfile(x:unknown):WideProfile{
 if(!object(x)||!axis(x.levels)||!Array.isArray(x.values)||x.values.length!==x.levels.length||!x.values.every((v:unknown)=>v===null||number(v))||!number(x.longitude)||!number(x.latitude)||!hash(x.source_sha256)||!object(x.source_indices)||!Array.isArray(x.source_indices.level)||x.source_indices.level.length!==x.levels.length||!['m','dbar'].includes(x.vertical_units)||typeof x.units!=='string')return fail();return x as WideProfile;
}
export async function verifyPack(x:unknown):Promise<{pack:WidePack;field:WideField;uncertainty:WideField|null}>{
 if(!object(x)||x.schema_version!=='p15-pack-1'||x.method!==METHOD||typeof x.payload_text!=='string'||!hash(x.sha256))return fail();
 const bytes=new TextEncoder().encode(x.payload_text);if(bytes.length>4_000_000)return fail();
 const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');if(digest!==x.sha256)throw new Error('The regional pack checksum does not match.');
 const data:unknown=JSON.parse(x.payload_text);if(!object(data))return fail();const field=parseWideField(data.field),uncertainty=data.uncertainty===null?null:parseWideField(data.uncertainty);
 if(field.query.resolution!=='native'||(field.query.variable==='oxygen'&&!uncertainty)||uncertainty&&(uncertainty.query.variable!=='oxygen_uncertainty'||uncertainty.source_sha256!==field.source_sha256||JSON.stringify([uncertainty.levels,uncertainty.latitude,uncertainty.longitude,uncertainty.time])!==JSON.stringify([field.levels,field.latitude,field.longitude,field.time])))return fail();
 return {pack:x as WidePack,field,uncertainty};
}
export async function wideRequest<T>(path:string,body:unknown,parse:(x:unknown)=>T,signal?:AbortSignal):Promise<T>{
 const controller=new AbortController(),abort=()=>controller.abort();if(signal?.aborted)controller.abort();signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(abort,30000);
 try{
  const r=await fetch(`/api/wider/${path}`,{method:body===undefined?'GET':'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,cache:'no-store'});
  const version=r.headers.get('X-Ocean-App-Version');if(version&&version!==appVersion)throw new ApiError('A new release is available. Reload the workspace.',undefined,'update');
  if(Number(r.headers.get('Content-Length'))>5_000_000)throw new Error('Regional response exceeds the allowed size.');
  const text=await r.text();if(new TextEncoder().encode(text).length>5_000_000)throw new Error('Regional response exceeds the allowed size.');const data:unknown=JSON.parse(text);
  if(!r.ok)throw new Error(object(data)&&object(data.error)?String(data.error.message):`Regional request failed (${r.status}).`);
  if(controller.signal.aborted)throw new DOMException('Cancelled','AbortError');return parse(data);
 }catch(e){if(signal?.aborted)throw new DOMException('Cancelled','AbortError');if(controller.signal.aborted)throw new Error('The regional request timed out. Reduce the area or try again.');throw e;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}

const entries=new Map<string,{value:WideField;bytes:number}>();let cacheBytes=0;
export const CACHE_LIMIT=8*1024*1024;
export function cacheKey(q:WideQuery,source:string){return JSON.stringify([appVersion,METHOD,source,q]);}
export function cachedField(key:string){const entry=entries.get(key);if(entry){entries.delete(key);entries.set(key,entry);}return entry?.value;}
export function cacheField(key:string,value:WideField){const bytes=new TextEncoder().encode(JSON.stringify(value)).length;const old=entries.get(key);if(old){cacheBytes-=old.bytes;entries.delete(key);}if(bytes>CACHE_LIMIT)return;while(entries.size&&(entries.size>=6||cacheBytes+bytes>CACHE_LIMIT)){const first=entries.keys().next().value!;cacheBytes-=entries.get(first)!.bytes;entries.delete(first);}entries.set(key,{value,bytes});cacheBytes+=bytes;}
export function cacheStats(){return {bytes:cacheBytes,items:entries.size,limit:CACHE_LIMIT};}
