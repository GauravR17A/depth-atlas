import type { ImportedSource } from '../instruments/imported';
import { ApiError } from '../contracts';
import { row as validRow,type MatchRow,type MatchSettings,querySettings } from '../evidence/contracts';
import { sameQuery,type FeatureSearch } from './contracts';

export type SupportRow=MatchRow&{profile_id:string;platform:string;source_sha256:string;cell:[number,number,number]};
export type Support={import_identity?:{source_sha256:string;parser_version:string;context_sha256:string;profiles_sha256:string};schema_version:'1';kind:'structure_observation_support';method_version:'p16d-native-support-v1';case_id:string;manifest_sha256:string;observation_library_sha256:string;source_scope:string;model_time:string;query:FeatureSearch['query'];region_id:string;settings:MatchSettings;units:string;rows:SupportRow[];eligible_samples:number;eligible_profiles:number;region_cells:number;supported_cells:number;unsupported_cells:number;footprint_indices:number[];supported_columns:number[];unsupported_columns:number;accepted_outside_region:number;excluded_samples:number;exclusion_counts:Record<string,number>;limitations:string[]};
export function parseSupport(value:unknown,result:FeatureSearch,regionId:string,settings:MatchSettings,source?:ImportedSource):Support{
  const s=value as Support,fail=()=>{throw new ApiError('The observation support result could not be verified.',undefined,'response');};
  const count=(n:unknown)=>Number.isInteger(n)&&Number(n)>=0,hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
  const region=result.regions.find(r=>r.id===regionId);
  if(!s||!region||s.schema_version!=='1'||s.kind!=='structure_observation_support'||s.method_version!=='p16d-native-support-v1'||s.case_id!==result.case_id||s.manifest_sha256!==result.manifest_sha256||!hash(s.observation_library_sha256)||s.model_time!==result.model_time||!s.query||!sameQuery(s.query,result.query)||s.region_id!==regionId||!s.settings||querySettings(s.settings)!==querySettings(settings)||s.units!==result.units||typeof s.source_scope!=='string')fail();
  if(!['eligible_samples','eligible_profiles','region_cells','supported_cells','unsupported_cells','unsupported_columns','accepted_outside_region','excluded_samples'].every(k=>count(s[k as keyof Support]))||s.region_cells!==region!.cell_count||s.supported_cells+s.unsupported_cells!==s.region_cells||!Array.isArray(s.rows)||s.rows.length!==s.eligible_samples||!Array.isArray(s.limitations)||!s.limitations.every(v=>typeof v==='string'))fail();
  if(source?(s.source_scope!==source.filename||s.import_identity?.source_sha256!==source.source_sha256||s.import_identity?.parser_version!==source.parser_version||!hash(s.import_identity?.context_sha256)||!hash(s.import_identity?.profiles_sha256)):(s.source_scope!=='Bundled observation library'||s.import_identity!==undefined))fail();
  const nx=result.shape[2],ny=result.shape[1],indices=(a:unknown):a is number[]=>Array.isArray(a)&&a.every(n=>count(n)&&n<nx*ny)&&new Set(a).size===a.length;
  if(!indices(s.footprint_indices)||!indices(s.supported_columns)||s.unsupported_columns+s.supported_columns.length!==s.footprint_indices.length||s.supported_columns.some(n=>!s.footprint_indices.includes(n)))fail();
  if(!s.exclusion_counts||typeof s.exclusion_counts!=='object'||!Object.values(s.exclusion_counts).every(count)||Object.values(s.exclusion_counts).reduce((a,b)=>a+b,0)!==s.excluded_samples)fail();
  for(const r of s.rows){
    if(!validRow(r)||!r.accepted||!hash(r.source_sha256)||typeof r.profile_id!=='string'||typeof r.platform!=='string'||!Array.isArray(r.cell)||r.cell.length!==3||r.cell.some((n,i)=>!count(n)||n>=result.shape[i]))fail();
    const [z,y,x]=r.cell;
    if(result.coordinates.latitude[y]!==r.model_latitude||result.coordinates.longitude[x]!==r.model_longitude||!s.supported_columns.includes(y*nx+x)||r.depth_m!<result.query.depth_min_m||r.depth_m!>result.query.depth_max_m||result.coordinates.depth_m[z]<result.query.depth_min_m||result.coordinates.depth_m[z]>result.query.depth_max_m||Math.abs(r.time_offset_hours)>settings.time_window_hours||r.distance_km!>settings.distance_km||r.upper_depth_m!-r.lower_depth_m!>settings.max_vertical_gap_m||Math.abs(r.time_offset_hours-(Date.parse(r.observation_time)-Date.parse(s.model_time))/3600000)>1e-8)fail();
  }
  if(new Set(s.rows.map(r=>r.profile_id)).size!==s.eligible_profiles||new Set(s.rows.map(r=>r.cell.join(','))).size!==s.supported_cells||new Set(s.rows.map(r=>r.profile_id+':'+r.sample_index)).size!==s.eligible_samples)fail();
  return s;
}
