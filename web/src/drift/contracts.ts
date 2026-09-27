import { ApiError,appVersion,type CaseManifest } from '../contracts';

export type Bounds=[number,number,number,number];
export type Release={kind:'point';longitude:number;latitude:number}|{kind:'box';bounds:Bounds};
export type DriftQuery={release:Release;depth_index:number;start_time_index:number;duration_hours:number;particle_count:number;seed:number;dt_seconds:300|600|1200;target_bounds:Bounds|null};
export type DriftRecipe={mode:'drift';case_id:string;query:DriftQuery;comparison:DriftQuery|null};
export type DriftContext={case_id:string;manifest_sha256:string;depth_m:number;model_time:string;bounds:Bounds;longitude:number[];latitude:number[];u:(number|null)[];v:(number|null)[];shape:[number,number]};
export type ParticleStatus='completed'|'left_domain'|'missing_velocity'|'invalid_release';
export type DriftPoint={elapsed_seconds:number;longitude:number;latitude:number};
export type Particle={id:number;release_longitude:number;release_latitude:number;status:ParticleStatus;stop_elapsed_seconds:number;stop_reason:string|null;distance_km:number;arrival_elapsed_seconds:number|null;points:DriftPoint[]};
export type DriftMethod='p11-drift-v1'|'p11-drift-v2';
export type DriftResult={schema_version:'1';kind:'drift_run';method_version:DriftMethod;case_id:string;manifest_sha256:string;simulated:true;query:DriftQuery;depth_m:number;start_time:string;end_time:string;forcing_times:string[];bounds:Bounds;background:DriftContext;output_interval_seconds:1800|3600;completed_steps:number;total_steps:number;particles:Particle[];summary:{released:number;valid_releases:number;completed:number;left_domain:number;missing_velocity:number;invalid_release:number;arrived:number;arrival_fraction:number|null;earliest_arrival_seconds:number|null;latest_arrival_seconds:number|null;mean_distance_km:number|null};methods:string[];limitations:string[]};
export type DriftProgress={completed_steps:number;total_steps:number};
export const driftMethod:DriftMethod='p11-drift-v2';
export const supportedDriftMethod=(v:unknown):v is DriftMethod=>v==='p11-drift-v1'||v==='p11-drift-v2';
export const statusLabels:Record<ParticleStatus,string>={completed:'Completed duration',left_domain:'Left study area',missing_velocity:'Missing current data',invalid_release:'Invalid release'};
const obj=(v:unknown):v is Record<string,unknown>=>typeof v==='object'&&v!==null&&!Array.isArray(v);
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
const count=(v:unknown):v is number=>finite(v)&&Number.isInteger(v)&&v>=0;
const numberList=(v:unknown):v is number[]=>Array.isArray(v)&&v.every(finite);
const axis=(v:unknown):v is number[]=>numberList(v)&&v.length>=2&&v.every((n,i)=>i===0||n>v[i-1]);
const stamp=(v:unknown):v is string=>typeof v==='string'&&v.endsWith('Z')&&Number.isFinite(Date.parse(v));
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(x=>typeof x==='string');
const hash=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const nullable=(v:unknown)=>v===null||finite(v);
export const validBounds=(v:unknown):v is Bounds=>numberList(v)&&v.length===4&&v[0]>=-180&&v[2]<=180&&v[0]<v[2]&&v[1]>-90&&v[3]<90&&v[1]<v[3];
export function same(a:unknown,b:unknown):boolean {if(a===b)return true;if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((v,i)=>same(v,b[i]));return obj(a)&&obj(b)&&Object.keys(a).length===Object.keys(b).length&&Object.entries(a).every(([k,v])=>same(v,b[k]));}
export function validDriftQuery(v:unknown):v is DriftQuery {return obj(v)&&obj(v.release)&&(v.release.kind==='point'?finite(v.release.longitude)&&Math.abs(v.release.longitude)<=180&&finite(v.release.latitude)&&Math.abs(v.release.latitude)<90:v.release.kind==='box'&&validBounds(v.release.bounds))&&count(v.depth_index)&&v.depth_index<=32&&count(v.start_time_index)&&v.start_time_index<=6&&count(v.duration_hours)&&v.duration_hours>=1&&v.duration_hours<=72&&count(v.particle_count)&&v.particle_count>=1&&v.particle_count<=64&&count(v.seed)&&v.seed<=2147483647&&finite(v.dt_seconds)&&[300,600,1200].includes(v.dt_seconds)&&(v.target_bounds===null||validBounds(v.target_bounds));}
export function validDriftRecipe(v:unknown):v is DriftRecipe {return obj(v)&&v.mode==='drift'&&typeof v.case_id==='string'&&validDriftQuery(v.query)&&(v.comparison===null||validDriftQuery(v.comparison)&&!same(v.query,v.comparison));}
const invalid=()=>new ApiError('The drift result could not be verified. Your previous completed runs are kept.',undefined,'response');
export function parseDriftContext(raw:unknown):DriftContext {
  if(!obj(raw)||typeof raw.case_id!=='string'||!hash(raw.manifest_sha256)||!finite(raw.depth_m)||raw.depth_m<0||raw.depth_m>1000||!stamp(raw.model_time)||!validBounds(raw.bounds)||!axis(raw.longitude)||!axis(raw.latitude)||!numberList(raw.shape)||raw.shape.length!==2||raw.shape[0]!==raw.latitude.length||raw.shape[1]!==raw.longitude.length||!Array.isArray(raw.u)||!Array.isArray(raw.v)||raw.u.length!==raw.shape[0]*raw.shape[1]||raw.u.length>10000||raw.v.length!==raw.u.length||!raw.u.every(nullable)||!raw.v.every(nullable))throw invalid();
  return raw as DriftContext;
}
export function verifyContext(raw:unknown,manifest:CaseManifest,depth:number,time:number):DriftContext {const r=parseDriftContext(raw);if(r.case_id!==manifest.case.id||r.depth_m!==manifest.coordinates.depth_m[depth]||r.model_time!==manifest.coordinates.times[time]||!same(r.bounds,manifest.case.bounds))throw invalid();return r;}
export function parseDrift(raw:unknown):DriftResult {
  if(!obj(raw)||raw.schema_version!=='1'||raw.kind!=='drift_run'||!supportedDriftMethod(raw.method_version)||raw.simulated!==true||!validDriftQuery(raw.query)||typeof raw.case_id!=='string'||!hash(raw.manifest_sha256)||!finite(raw.depth_m)||!stamp(raw.start_time)||!stamp(raw.end_time)||!Array.isArray(raw.forcing_times)||!raw.forcing_times.every(stamp)||!validBounds(raw.bounds)||raw.output_interval_seconds!==(raw.query.dt_seconds===1200?3600:1800)||!count(raw.completed_steps)||!count(raw.total_steps)||raw.completed_steps!==raw.total_steps||!Array.isArray(raw.particles)||raw.particles.length!==raw.query.particle_count||!obj(raw.summary)||!strings(raw.methods)||!strings(raw.limitations))throw invalid();
  const r=raw as DriftResult,seconds=r.query.duration_hours*3600,bg=parseDriftContext(r.background),s=r.summary;
  if(Date.parse(r.end_time)-Date.parse(r.start_time)!==seconds*1000||bg.case_id!==r.case_id||bg.manifest_sha256!==r.manifest_sha256||bg.depth_m!==r.depth_m||bg.model_time!==r.start_time||!same(bg.bounds,r.bounds))throw invalid();
  for(const [i,p] of r.particles.entries()){
    if(!obj(p)||p.id!==i+1||!finite(p.release_longitude)||!finite(p.release_latitude)||(typeof p.status!=='string'||!Object.hasOwn(statusLabels,p.status))||!finite(p.stop_elapsed_seconds)||p.stop_elapsed_seconds<0||p.stop_elapsed_seconds>seconds||!finite(p.distance_km)||p.distance_km<0||!(p.stop_reason===null||typeof p.stop_reason==='string')||!nullable(p.arrival_elapsed_seconds)||p.arrival_elapsed_seconds!==null&&(p.arrival_elapsed_seconds<0||p.arrival_elapsed_seconds>p.stop_elapsed_seconds)||!Array.isArray(p.points)||!p.points.length||p.points.length>150||!p.points.every((v,j)=>obj(v)&&finite(v.longitude)&&Math.abs(v.longitude)<=180&&finite(v.latitude)&&Math.abs(v.latitude)<90&&finite(v.elapsed_seconds)&&v.elapsed_seconds>=0&&v.elapsed_seconds<=p.stop_elapsed_seconds&&(j===0?v.elapsed_seconds===0:v.elapsed_seconds>p.points[j-1].elapsed_seconds)))throw invalid();
    if(p.points[0].longitude!==p.release_longitude||p.points[0].latitude!==p.release_latitude||p.points.at(-1)!.elapsed_seconds!==p.stop_elapsed_seconds||p.status==='completed'&&p.stop_elapsed_seconds!==seconds||p.status==='invalid_release'&&(p.stop_elapsed_seconds!==0||p.distance_km!==0||p.arrival_elapsed_seconds!==null)||p.status!=='completed'&&!p.stop_reason)throw invalid();
  }
  if(!['released','valid_releases','completed','left_domain','missing_velocity','invalid_release','arrived'].every(k=>count(s[k as keyof typeof s]))||s.released!==r.particles.length||s.valid_releases!==s.released-s.invalid_release)throw invalid();
  for(const status of Object.keys(statusLabels) as ParticleStatus[])if(s[status]!==r.particles.filter(p=>p.status===status).length)throw invalid();
  const arrivals=r.particles.flatMap(p=>p.arrival_elapsed_seconds===null?[]:[p.arrival_elapsed_seconds]),distances=r.particles.filter(p=>p.status!=='invalid_release').map(p=>p.distance_km);
  if(s.arrived!==arrivals.length||!nullable(s.arrival_fraction)||!nullable(s.mean_distance_km)||!nullable(s.earliest_arrival_seconds)||!nullable(s.latest_arrival_seconds)||(r.query.target_bounds===null?(s.arrived!==0||s.arrival_fraction!==null||arrivals.length!==0):s.arrival_fraction!==s.arrived/s.released))throw invalid();
  if(s.earliest_arrival_seconds!==(arrivals.length?Math.min(...arrivals):null)||s.latest_arrival_seconds!==(arrivals.length?Math.max(...arrivals):null)||(distances.length?(!finite(s.mean_distance_km)||Math.abs(s.mean_distance_km-distances.reduce((a,b)=>a+b,0)/distances.length)>1e-8):s.mean_distance_km!==null))throw invalid();
  return r;
}
export function verifyDrift(raw:unknown,query:DriftQuery,manifest:CaseManifest):DriftResult {const r=parseDrift(raw);if(r.method_version!==driftMethod||r.case_id!==manifest.case.id||!same(r.query,query)||r.depth_m!==manifest.coordinates.depth_m[query.depth_index]||r.start_time!==manifest.coordinates.times[query.start_time_index]||!same(r.forcing_times,manifest.coordinates.times)||!same(r.bounds,manifest.case.bounds))throw invalid();return r;}
export async function streamDrift(path:string,query:DriftQuery,manifest:CaseManifest,signal:AbortSignal,onProgress:(p:DriftProgress)=>void):Promise<DriftResult>{
  const controller=new AbortController(),abort=()=>controller.abort();if(signal.aborted)abort();signal.addEventListener('abort',abort,{once:true});const timeout=setTimeout(abort,55000);
  try{
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/x-ndjson'},body:JSON.stringify(query),signal:controller.signal,cache:'no-store'});
    if(response.headers.get('X-Ocean-App-Version')!==appVersion)throw new ApiError('The workspace was updated. Reload before running another drift experiment.',undefined,'update');
    if(!response.ok){const body=await response.json().catch(()=>null);throw new ApiError(body?.error?.message??'The drift service could not start this run. Your completed runs are kept.');}
    if(!response.body)throw invalid();const reader=response.body.getReader(),decoder=new TextDecoder(),maxBytes=4_000_000;let buffer='',bytes=0,last=0,result:DriftResult|undefined;
    const event=(line:string)=>{if(!line.trim())return;const e:unknown=JSON.parse(line);if(!obj(e))throw invalid();if(e.type==='error')throw new ApiError(typeof e.message==='string'?e.message:'The drift calculation stopped.');if(e.type==='progress'){if(!count(e.completed_steps)||!count(e.total_steps)||e.total_steps<1||e.completed_steps>e.total_steps||e.completed_steps<last)throw invalid();last=e.completed_steps;onProgress({completed_steps:e.completed_steps,total_steps:e.total_steps});}else if(e.type==='result'){if(result)throw invalid();result=verifyDrift(e.result,query,manifest);}else throw invalid();};
    while(true){const chunk=await reader.read();if(chunk.done)break;bytes+=chunk.value.byteLength;if(bytes>maxBytes)throw invalid();buffer+=decoder.decode(chunk.value,{stream:true});let newline;while((newline=buffer.indexOf('\n'))>=0){event(buffer.slice(0,newline));buffer=buffer.slice(newline+1);}}buffer+=decoder.decode();if(buffer.trim())event(buffer);if(!result)throw invalid();return result;
  }catch(error){if(signal.aborted)throw new DOMException('Calculation cancelled.','AbortError');if(error instanceof ApiError)throw error;throw new ApiError(controller.signal.aborted?'The drift calculation timed out. Your completed runs are kept.':'Could not finish the drift calculation. Your completed runs are kept. Try again.');}finally{clearTimeout(timeout);signal.removeEventListener('abort',abort);}
}
export function defaultDrift(bounds:Bounds):DriftQuery {const [w,s,e,n]=bounds,dx=e-w,dy=n-s;return {release:{kind:'box',bounds:[w+.43*dx,s+.43*dy,w+.57*dx,s+.57*dy]},depth_index:0,start_time_index:0,duration_hours:24,particle_count:24,seed:26067,dt_seconds:600,target_bounds:null};}
export function atTime(particle:Particle,seconds:number):DriftPoint {let previous=particle.points[0];for(const next of particle.points.slice(1)){if(next.elapsed_seconds>seconds){const f=Math.max(0,(seconds-previous.elapsed_seconds)/(next.elapsed_seconds-previous.elapsed_seconds));return {elapsed_seconds:seconds,longitude:previous.longitude+f*(next.longitude-previous.longitude),latitude:previous.latitude+f*(next.latitude-previous.latitude)};}previous=next;}return previous;}
export const number=(v:number|null,digits=3)=>v===null?'Not available':v.toLocaleString('en-US',{maximumFractionDigits:digits});
export const hours=(seconds:number|null)=>seconds===null?'Not reached':`${number(seconds/3600,2)} h`;
export const utc=(v:string)=>v.replace('T',' ').replace(/:00Z$/,' UTC');
