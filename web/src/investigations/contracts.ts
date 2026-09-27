import { parseClimate, validClimateRecipe, validClimateQuery, sameClimateQuery, supportedClimateMethod, type ClimateRecipe } from '../climate/contracts';
import { parseEvolution, validEvolutionRecipe, sameEvolutionQuery, supportedEvolutionMethod, type EvolutionRecipe } from '../evolution/contracts';
import { parseBlackout, validBlackoutRecipe, sameBlackoutQuery, supportedBlackoutMethod, type BlackoutRecipe } from '../blackout/contracts';
import { appVersion,ApiError } from '../contracts';
import type { Variable } from '../store';
import type { Paint,ViewMode } from '../ocean/grid';
import { parseComparison,parseCoverage,type MatchSettings } from '../evidence/contracts';
import { parseSearch,parseRegion,parseSection,type FeatureQuery,type SectionRequest } from '../features/contracts';
import { parseInstrument } from '../instruments/contracts';
import type { InstrumentProfile } from '../instruments/contracts';
import type { ImportedSource } from '../instruments/imported';
import { parsePlan,parseSurvey,parseExperiment,validExpeditionRecipe,supportedExpeditionMethod,equalQuery,type ExpeditionRecipe } from '../expedition/contracts';
import { parseDrift,validDriftRecipe,same,supportedDriftMethod,type DriftRecipe } from '../drift/contracts';
import { parseHeat,validHeatRecipe,validHeatQuery,sameHeatQuery,supportedHeatMethod,type HeatRecipe } from '../heat/contracts';

export type OceanRecipe={mode:'ocean';case_id:string;variable:Variable;time_index:number;view:ViewMode;depth_index:number;section_index:number;point:[number,number,number];paint:Paint;iso:number;exaggeration:number;window_depth:1000|5000;cutaway:boolean;quality:'auto'|'balanced'|'basic';show_instruments:boolean};
export type ComparisonSelection={profile_id:string;settings:MatchSettings};
export type ComparisonRecipe=ComparisonSelection&{mode:'comparison';case_id:string;sample_index:number;view:'comparison'|'coverage';rank:'nearest'|'residual';baseline:ComparisonSelection|null};
export type FeatureRecipe={mode:'features';case_id:string;query:FeatureQuery;selected_region:string|null;section:SectionRequest|null;section_pick:number;show_observations:boolean;graphics:'3d'|'basic';exaggeration:1|100|500|1000|2000};
export type InstrumentRecipe={mode:'instrument';case_id:string;profile_id:string;variable:string;sample_index:number;show_excluded:boolean;model_time_index?:number};
export type Recipe=OceanRecipe|ComparisonRecipe|FeatureRecipe|InstrumentRecipe|ExpeditionRecipe|DriftRecipe|HeatRecipe|ClimateRecipe|EvolutionRecipe|BlackoutRecipe;
export type SaveDraft={recipe:Recipe;import_source?:ImportedSource;expected_model_sha256?:string;expected_profile_sha256?:string;expected_heat_manifest_sha256?:string;expected_climate_manifest_sha256?:string;expected_observation_library_sha256?:string};
export type SourceIdentity={model_manifest_sha256:string;observation_library_sha256:string;heat_manifest_sha256?:string;climate_manifest_sha256?:string;import_context_sha256?:string;import_profiles_sha256?:string;methods:Record<string,string>};
export type Replay={schema_version:'1';title:string;recipe:Recipe;sources:SourceIdentity;import_source?:ImportedSource;expected_result_sha256:string;expected_recipe_sha256:string};
export type ResultModule={module:string;method_version:string;parameters:Record<string,unknown>;random_seed:number|null;output:unknown;output_sha256:string};
export type Investigation={schema_version:'1';kind:'ocean_investigation';created_at:string;case:{id:string;region_id:string;title:string};software:{app:string;python:string;numpy:string};replay:Replay;imported_profiles?:InstrumentProfile[];results:ResultModule[];result_sha256:string;references:unknown[];limitations:string[];document_sha256:string};
export const modeLabel={ocean:'Ocean view',comparison:'Model comparison',features:'Structure search',instrument:'Observation profile',expedition:'Virtual Expedition',drift:'Drift Lab',heat:'Heat & Depth Lab',climate:'Climate Event Lab',evolution:'Feature evolution',blackout:'Observation blackout'};
export const MAX_FILE_BYTES=8_000_000;
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const obj=(v:unknown):v is Record<string,unknown>=>typeof v==='object'&&v!==null&&!Array.isArray(v);
const bad=()=>new Error('This investigation file is incomplete, altered or uses an unsupported format. The current workspace has been kept.');

export async function fingerprint(value:unknown):Promise<string>{
  const buffer=new ArrayBuffer(8),view=new DataView(buffer);
  const compare=(a:string,b:string)=>{const aa=Array.from(a,x=>x.codePointAt(0)!),bb=Array.from(b,x=>x.codePointAt(0)!);for(let i=0;i<Math.min(aa.length,bb.length);i++)if(aa[i]!==bb[i])return aa[i]-bb[i];return aa.length-bb.length;};
  function tag(v:unknown,depth=0):unknown{
    if(depth>60)throw bad();
    if(v===null)return ['null'];
    if(typeof v==='boolean')return ['boolean',v];
    if(typeof v==='number'){if(!Number.isFinite(v)||Number.isInteger(v)&&Math.abs(v)>Number.MAX_SAFE_INTEGER)throw bad();view.setFloat64(0,v===0?0:v,false);return ['number',Array.from(new Uint8Array(buffer),b=>b.toString(16).padStart(2,'0')).join('')];}
    if(typeof v==='string')return ['string',v];
    if(Array.isArray(v))return ['array',v.map(x=>tag(x,depth+1))];
    if(obj(v))return ['object',Object.keys(v).sort(compare).map(k=>[k,tag(v[k],depth+1)])];
    throw bad();
  }
  const text=JSON.stringify(tag(value)).replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
}

export async function verifyReplay(raw:unknown):Promise<Replay>{
  if(!obj(raw)||raw.schema_version!=='1'||typeof raw.title!=='string'||raw.title.length<1||raw.title.length>100||!obj(raw.recipe)||!['ocean','comparison','features','instrument','expedition','drift','heat','climate','evolution','blackout'].includes(String(raw.recipe.mode))||typeof raw.recipe.case_id!=='string'||!obj(raw.sources)||!hash(raw.sources.model_manifest_sha256)||!hash(raw.sources.observation_library_sha256)||!obj(raw.sources.methods)||!hash(raw.expected_result_sha256)||!hash(raw.expected_recipe_sha256))throw bad();
  if(await fingerprint({recipe:raw.recipe,sources:raw.sources})!==raw.expected_recipe_sha256)throw bad();
  if(raw.import_source!==undefined){
    const s=raw.import_source;
    if(!['instrument','comparison'].includes(String(raw.recipe.mode))||!obj(s)||s.schema_version!=='1'||typeof s.filename!=='string'||!s.filename||s.filename.length>160||/[\\/\x00-\x1f]/.test(s.filename)||typeof s.content_base64!=='string'||s.content_base64.length>2666668||!hash(s.source_sha256)||s.parser_version!=='observation-preview-v1'||raw.sources.methods.import_parser!==s.parser_version||raw.sources.methods.imported!=='p16c-original-input-v1'||!(s.mapping===null||obj(s.mapping))||!hash(raw.sources.import_context_sha256)||!hash(raw.sources.import_profiles_sha256))throw bad();
    const {content_base64,...context}=s;
    if(await fingerprint(context)!==raw.sources.import_context_sha256)throw bad();
    let bytes:Uint8Array;try{bytes=Uint8Array.from(atob(content_base64 as string),c=>c.charCodeAt(0));}catch{throw bad();}
    if(!bytes.length||bytes.length>2000000)throw bad();
    const digest=await crypto.subtle.digest('SHA-256',bytes as Uint8Array<ArrayBuffer>);
    if(Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')!==s.source_sha256)throw bad();
  }else if(raw.sources.import_context_sha256||raw.sources.import_profiles_sha256||raw.sources.methods.imported)throw bad();
  if(raw.recipe.mode==='expedition'&&(!validExpeditionRecipe(raw.recipe)||!supportedExpeditionMethod(raw.sources.methods.expedition)))throw bad();
  if(raw.recipe.mode==='drift'&&(!validDriftRecipe(raw.recipe)||!supportedDriftMethod(raw.sources.methods.drift)))throw bad();
  if(raw.recipe.mode==='heat'&&(!validHeatRecipe(raw.recipe)||!supportedHeatMethod(raw.sources.methods.heat)||!hash(raw.sources.heat_manifest_sha256)))throw bad();
  if(raw.recipe.mode==='climate'&&(!validClimateRecipe(raw.recipe)||!supportedClimateMethod(raw.sources.methods.climate)||!hash(raw.sources.climate_manifest_sha256)))throw bad();
  if(raw.recipe.mode==='evolution'&&(!validEvolutionRecipe(raw.recipe)||!supportedEvolutionMethod(raw.sources.methods.evolution)))throw bad();
  if(raw.recipe.mode==='blackout'&&(!validBlackoutRecipe(raw.recipe)||!supportedBlackoutMethod(raw.sources.methods.blackout)))throw bad();
  return raw as Replay;
}

export async function verifyInvestigation(raw:unknown):Promise<Investigation>{
  if(!obj(raw)||raw.schema_version!=='1'||raw.kind!=='ocean_investigation'||!hash(raw.document_sha256)||!Array.isArray(raw.results)||raw.results.length<1||raw.results.length>4||typeof raw.created_at!=='string'||!Number.isFinite(Date.parse(raw.created_at))||!obj(raw.software)||!Array.isArray(raw.references)||!Array.isArray(raw.limitations)||!raw.limitations.every(x=>typeof x==='string'))throw bad();
  const {document_sha256,...body}=raw;
  if(await fingerprint(body)!==document_sha256)throw bad();
  const descriptor=await verifyReplay(raw.replay);
  if(descriptor.import_source){
    if(!Array.isArray(raw.imported_profiles)||!raw.imported_profiles.length||raw.imported_profiles.length>24||await fingerprint(raw.imported_profiles)!==descriptor.sources.import_profiles_sha256)throw bad();
    const profiles=raw.imported_profiles.map(parseInstrument);
    if(profiles.reduce((n,p)=>n+p.samples,0)>5000||profiles.some(p=>!p.id.startsWith('import-')||p.source_sha256!==descriptor.import_source!.source_sha256))throw bad();
    if(!('profile_id' in descriptor.recipe)||!profiles.some(p=>p.id===(descriptor.recipe as InstrumentRecipe).profile_id))throw bad();
  }else if(raw.imported_profiles!==undefined)throw bad();
  if(!obj(raw.case)||raw.case.id!==descriptor.recipe.case_id||typeof raw.case.region_id!=='string')throw bad();
  if(await fingerprint(raw.results)!==raw.result_sha256||raw.result_sha256!==descriptor.expected_result_sha256)throw bad();
  if(descriptor.recipe.mode==='expedition'){
    const recipe=descriptor.recipe,expected=['station_plan',...(recipe.survey?['virtual_survey']:[]),...(recipe.experiment?['sampling_experiment']:[])];
    if(raw.results.length!==expected.length||raw.results.some((m,i)=>!obj(m)||m.module!==expected[i]||m.method_version!==descriptor.sources.methods.expedition||m.random_seed!==(m.module==='sampling_experiment'?recipe.query.seed:null)||!equalQuery(m.parameters,m.module==='virtual_survey'?recipe.survey:recipe.query)||!obj(m.output)||m.output.method_version!==m.method_version||m.output.case_id!==recipe.case_id||m.output.manifest_sha256!==descriptor.sources.model_manifest_sha256||!equalQuery(m.output.query,m.module==='virtual_survey'?recipe.survey:recipe.query)))throw bad();
  }
  if(descriptor.recipe.mode==='drift'){
    const recipe=descriptor.recipe,expected=['drift_run',...(recipe.comparison?['reference_drift_run']:[])];
    if(raw.results.length!==expected.length||raw.results.some((m,i)=>{const q=i===0?recipe.query:recipe.comparison;return !q||!obj(m)||m.module!==expected[i]||m.method_version!==descriptor.sources.methods.drift||m.random_seed!==q.seed||!same(m.parameters,q)||!obj(m.output)||m.output.method_version!==m.method_version||m.output.case_id!==recipe.case_id||m.output.manifest_sha256!==descriptor.sources.model_manifest_sha256||!same(m.output.query,q);}))throw bad();
  }
  if(descriptor.recipe.mode==='heat'){
    const recipe=descriptor.recipe,m=raw.results[0];
    if(raw.results.length!==1||!obj(m)||m.module!=='heat_analysis'||m.method_version!==descriptor.sources.methods.heat||m.random_seed!==null||!validHeatQuery(m.parameters)||!sameHeatQuery(m.parameters,recipe.query)||!obj(m.output)||m.output.method_version!==m.method_version||m.output.case_id!==recipe.case_id||m.output.model_manifest_sha256!==descriptor.sources.model_manifest_sha256||m.output.heat_manifest_sha256!==descriptor.sources.heat_manifest_sha256||!validHeatQuery(m.output.query)||!sameHeatQuery(m.output.query,recipe.query))throw bad();
  }
  if(descriptor.recipe.mode==='climate'){
    const recipe=descriptor.recipe,m=raw.results[0];
    if(raw.results.length!==1||!obj(m)||m.module!=='climate_analysis'||m.method_version!==descriptor.sources.methods.climate||m.random_seed!==null||!validClimateQuery(m.parameters)||!sameClimateQuery(m.parameters,recipe.query)||!obj(m.output)||m.output.method_version!==m.method_version||m.output.case_id!==recipe.case_id||m.output.model_manifest_sha256!==descriptor.sources.model_manifest_sha256||m.output.climate_manifest_sha256!==descriptor.sources.climate_manifest_sha256||!validClimateQuery(m.output.query)||!sameClimateQuery(m.output.query,recipe.query))throw bad();
  }
  if(descriptor.recipe.mode==='evolution'||descriptor.recipe.mode==='blackout'){
    const recipe=descriptor.recipe,m=raw.results[0],sameQuery=recipe.mode==='evolution'?sameEvolutionQuery:sameBlackoutQuery;
    if(raw.results.length!==1||!obj(m)||m.module!==`${recipe.mode}_analysis`||m.method_version!==descriptor.sources.methods[recipe.mode]||m.random_seed!==null||!sameQuery(m.parameters,recipe.query)||!obj(m.output)||m.output.method_version!==m.method_version||m.output.case_id!==recipe.case_id||m.output.manifest_sha256!==descriptor.sources.model_manifest_sha256||m.output.observation_library_sha256!==descriptor.sources.observation_library_sha256||!sameQuery(m.output.query,recipe.query))throw bad();
    if(recipe.mode==='evolution'){
      const output=parseEvolution(m.output);
      if(recipe.selected_node&&!output.frames.some(frame=>frame.regions.some(node=>node.node_id===recipe.selected_node)))throw bad();
    }else parseBlackout(m.output);
  }
  for(const m of raw.results){
    if(!obj(m)||typeof m.module!=='string'||!hash(m.output_sha256)||await fingerprint(m.output)!==m.output_sha256)throw bad();
    if(m.module==='comparison'||m.module==='reference_comparison')parseComparison(m.output);
    else if(m.module==='coverage')parseCoverage(m.output);
    else if(m.module==='regions')parseSearch(m.output);
    else if(m.module==='region_boundary')parseRegion(m.output);
    else if(m.module==='section')parseSection(m.output);
    else if(m.module==='observation_profile')parseInstrument(m.output);
    else if(m.module==='station_plan')parsePlan(m.output);
    else if(m.module==='virtual_survey')parseSurvey(m.output);
    else if(m.module==='sampling_experiment')parseExperiment(m.output);
    else if(m.module==='drift_run'||m.module==='reference_drift_run')parseDrift(m.output);
    else if(m.module==='heat_analysis')parseHeat(m.output);
    else if(m.module==='climate_analysis')parseClimate(m.output);
    else if(m.module==='evolution_analysis')parseEvolution(m.output);
    else if(m.module==='blackout_analysis')parseBlackout(m.output);
    else if(m.module!=='native_profile')throw bad();
  }
  return raw as Investigation;
}

export async function investigationRequest(path:string,payload:unknown,binary=false,signal?:AbortSignal){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),45000);
  try{
    const response=await fetch(`/api/investigations/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:signal?AbortSignal.any([signal,controller.signal]):controller.signal,cache:'no-store'});
    if(response.headers.get('X-Ocean-App-Version')!==appVersion)throw new ApiError('The workspace was updated. Reload before saving or reopening an investigation.',undefined,'update');
    if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.error?.message??'The investigation service could not finish. Your current workspace has been kept.');}
    return binary?response.blob():response.json();
  }catch(error){if(signal?.aborted)throw new Error('Investigation request cancelled. Previous results are kept.');if(error instanceof Error&&error.name==='AbortError')throw new Error('The investigation request timed out. Your current workspace has been kept. Try again.');throw error;}finally{clearTimeout(timer);}
}

export function downloadBlob(blob:Blob,name:string){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function downloadRecord(record:Investigation){downloadBlob(new Blob([JSON.stringify(record,null,record.replay.import_source?undefined:2)],{type:'application/json'}),'ocean-investigation.json');}
export function shareLink(replay:Replay){if(replay.import_source)throw new Error('Imported source bytes are shared through the investigation file, never a URL. Download JSON or the evidence ZIP.');const bytes=new TextEncoder().encode(JSON.stringify(replay));let raw='';for(const b of bytes)raw+=String.fromCharCode(b);const encoded=btoa(raw).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');if(encoded.length>16000)throw new Error('This recipe is too long for a share link. Use the investigation file instead.');return `${location.origin}/#investigation=${encoded}`;}
export async function readShare(hashValue:string){
  const prefix='#investigation=';if(!hashValue.startsWith(prefix))return null;
  const encoded=hashValue.slice(prefix.length);if(encoded.length>16000||!/^[A-Za-z0-9_-]+$/.test(encoded))throw bad();
  try{const raw=atob(encoded.replaceAll('-','+').replaceAll('_','/')),bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));return await verifyReplay(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)));}catch{throw bad();}
}
