import { version as appVersion } from '../../api/release.json';

export { appVersion };

export type Region = {
  id: string;
  name: string;
  description: string;
  center: [number, number];
  viewport_bounds: [number, number, number, number];
  status: 'planned' | 'data_available';
};

export type Health = {
  status: 'ok';
  service: string;
  version: string;
  data_status: 'not_configured' | 'historical_case_ready';
  case_count: number;
};

export type Catalog = {
  schema_version: '2';
  data_status: 'not_configured' | 'historical_case_ready';
  message: string;
  regions: Region[];
  cases: CaseSummary[]; unavailable_tools?: Record<string,string[]>;
};

export type ScientificVariable = 'temperature' | 'salinity' | 'eastward_velocity' | 'northward_velocity';
export type CaseSummary = {
  id: string; title: string; region_id: string; kind: 'model_analysis'; bounds: [number, number, number, number];
  time_start: string; time_end: string; time_count: number; depth_range_m: [number, number]; depth_count: number;
  profile_count: number; variables: ScientificVariable[]; source_label: string;
};
export type ProfileSummary = {
  id: string; platform: string; cycle: number; time: string; latitude: number; longitude: number;
  data_mode: 'R' | 'A' | 'D'; samples: number; eligible_samples: number; depth_range_m: [number, number] | null;
  source_file: string; source_sha256: string; source_url: string;
  overlap: { eligible: boolean; nearest_model_time?: string; time_offset_seconds?: number; meaning: string; model_temporal_support?: string; source_month?: number };
};
export type CaseManifest = {
  schema_version: '1'; case: CaseSummary;
  coordinates: { times: string[]; depth_m: number[]; latitude: number[]; longitude: number[] };
  display_coordinates: { times: string[]; depth_m: number[]; latitude: number[]; longitude: number[] };
  variables: { id: ScientificVariable; label: string; units: string; definition: string }[];
  sources: { source_id: string; title: string; kind: string; provider: string; dataset_version: string; source_url: string; licence_url: string; licence: string; citation: string; retrieved_at: string; limitations: string[] }[];
  profiles: ProfileSummary[]; limitations: string[];
  representations?: { unavailable_tools?: string[]; temporal_support?: { kind: string; intervals: [string,string][]; meaning: string }; science_compatibility?: { temperature: string; direct_observation_residual: boolean }; display?: { variable_ranges?: Partial<Record<'temperature'|'salinity',{min:number;max:number}>> } };
};
export type Subset = {
  schema_version: '1'; kind: 'model_analysis' | 'derived'; case_id: string; variable: ScientificVariable | 'horizontal_kinetic_energy'; units: string; time: string;
  representation: 'analytical' | 'display'; shape: [number, number, number]; depth_m: number[]; latitude: number[]; longitude: number[];
  values: (number | null)[]; processing: string[]; manifest_sha256: string;
};
export type Observation = ProfileSummary & {
  schema_version: '1'; kind: 'observation'; qc_policy: string; depth_method: string;
  levels: { source_level_index: number; pressure_dbar: number | null; depth_m: number | null; temperature_c: number | null; salinity_psu: number | null; eligible: boolean; qc: { PRES: string; TEMP: string; PSAL: string } }[];
};

export class ApiError extends Error {
  constructor(message: string, public readonly requestId?: string, public readonly kind: 'service' | 'update' | 'response' = 'service') {
    super(message);
    this.name = 'ApiError';
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function numbers(value: unknown, length: number): value is number[] {
  return Array.isArray(value) && value.length === length && value.every((item) => typeof item === 'number' && Number.isFinite(item));
}

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const count = (v: unknown): v is number => finite(v) && Number.isInteger(v) && v >= 0;
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === 'string');
const stamp = (v: unknown): v is string => typeof v === 'string' && v.endsWith('Z') && Number.isFinite(Date.parse(v));
const variableIds = ['temperature', 'salinity', 'eastward_velocity', 'northward_velocity'];
const https = (v: unknown): v is string => typeof v === 'string' && v.startsWith('https://');
function caseSummary(v: unknown): v is CaseSummary {
  return record(v) && typeof v.id === 'string' && typeof v.title === 'string' && typeof v.region_id === 'string' && v.kind === 'model_analysis' && numbers(v.bounds, 4) && stamp(v.time_start) && stamp(v.time_end) && count(v.time_count) && v.time_count > 0 && count(v.depth_count) && v.depth_count > 0 && numbers(v.depth_range_m, 2) && count(v.profile_count) && Array.isArray(v.variables) && v.variables.length >= 1 && v.variables.length <= 4 && new Set(v.variables).size === v.variables.length && v.variables.every(x => variableIds.includes(x)) && typeof v.source_label === 'string';
}
function profileSummary(v: unknown): v is ProfileSummary {
  return record(v) && typeof v.id === 'string' && typeof v.platform === 'string' && count(v.cycle) && stamp(v.time) && finite(v.latitude) && finite(v.longitude) && ['R', 'A', 'D'].includes(String(v.data_mode)) && count(v.samples) && count(v.eligible_samples) && v.eligible_samples <= v.samples && (v.depth_range_m === null || numbers(v.depth_range_m, 2)) && typeof v.source_file === 'string' && typeof v.source_sha256 === 'string' && https(v.source_url) && record(v.overlap) && typeof v.overlap.eligible === 'boolean' && (stamp(v.overlap.nearest_model_time) && finite(v.overlap.time_offset_seconds) || v.overlap.model_temporal_support === 'calendar_month_mean' && v.overlap.eligible === false && count(v.overlap.source_month) && v.overlap.source_month >= 1 && v.overlap.source_month <= 12) && typeof v.overlap.meaning === 'string';
}

export function parseHealth(value: unknown): Health {
  if (!record(value) || value.status !== 'ok' || typeof value.service !== 'string' || typeof value.version !== 'string' || !['not_configured', 'historical_case_ready'].includes(String(value.data_status)) || !count(value.case_count) || (value.data_status === 'not_configured' ? value.case_count !== 0 : value.case_count < 1)) {
    throw new ApiError('The service returned an unsupported status response.', undefined, 'response');
  }
  return value as Health;
}

export function parseCatalog(value: unknown): Catalog {
  if (!record(value) || value.schema_version !== '2' || !['not_configured', 'historical_case_ready'].includes(String(value.data_status)) || typeof value.message !== 'string' || !Array.isArray(value.cases) || !value.cases.every(caseSummary) || (value.data_status === 'not_configured' ? value.cases.length !== 0 : value.cases.length === 0) || !Array.isArray(value.regions) || value.regions.length === 0) {
    throw new ApiError('The data catalogue is not compatible with this preview.', undefined, 'response');
  }
  if (value.unavailable_tools !== undefined && (!record(value.unavailable_tools) || !Object.values(value.unavailable_tools).every(strings))) throw new ApiError('The case tools could not be verified.');
  const regions = value.regions;
  if (!regions.every((region) => record(region) && typeof region.id === 'string' && typeof region.name === 'string' && typeof region.description === 'string' && ['planned', 'data_available'].includes(String(region.status)) && numbers(region.center, 2) && numbers(region.viewport_bounds, 4)) || new Set(regions.map((region) => region.id)).size !== regions.length) {
    throw new ApiError('The region catalogue could not be read.', undefined, 'response');
  }
  return value as Catalog;
}

export function parseCase(value: unknown): CaseManifest {
  const fail = () => new ApiError('The scientific case metadata could not be verified.');
  if (!record(value) || value.schema_version !== '1' || !caseSummary(value.case) || !record(value.coordinates)) throw fail();
  const c = value.coordinates;
  if (!Array.isArray(c.times) || !c.times.every(stamp) || c.times.length !== value.case.time_count) throw fail();
  for (const key of ['depth_m', 'latitude', 'longitude']) {
    const axis = c[key];
    if (!Array.isArray(axis) || !axis.length || !axis.every(finite) || axis.some((v, i) => i > 0 && v <= axis[i - 1])) throw fail();
  }
  if (!record(value.display_coordinates)) throw fail();
  const display = value.display_coordinates;
  if (!Array.isArray(display.times) || JSON.stringify(display.times) !== JSON.stringify(c.times)) throw fail();
  for (const key of ['depth_m', 'latitude', 'longitude']) {
    const axis = display[key];
    if (!Array.isArray(axis) || axis.length < 2 || axis.length > 64 || !axis.every(finite) || axis.some((v, i) => i > 0 && v <= axis[i - 1])) throw fail();
  }
  if (!Array.isArray(value.variables) || value.variables.length !== value.case.variables.length || !value.variables.every(v => record(v) && (value.case as CaseSummary).variables.includes(v.id as ScientificVariable) && ['label', 'units', 'definition'].every(k => typeof v[k] === 'string'))) throw fail();
  if (!Array.isArray(value.sources) || value.sources.length === 0 || !value.sources.every(s => record(s) && ['source_id', 'title', 'kind', 'provider', 'dataset_version', 'licence', 'citation', 'retrieved_at'].every(k => typeof s[k] === 'string') && https(s.source_url) && https(s.licence_url) && strings(s.limitations))) throw fail();
  if (!Array.isArray(value.profiles) || !value.profiles.every(profileSummary) || value.profiles.length !== value.case.profile_count || !strings(value.limitations)) throw fail();
  return value as CaseManifest;
}

export function parseSubset(value: unknown): Subset {
  if (!record(value) || value.schema_version !== '1' || !['model_analysis', 'derived'].includes(String(value.kind)) || (value.kind === 'derived') !== (value.variable === 'horizontal_kinetic_energy') || !['analytical', 'display'].includes(String(value.representation)) || typeof value.case_id !== 'string' || ![...variableIds, 'horizontal_kinetic_energy'].includes(String(value.variable)) || typeof value.units !== 'string' || !stamp(value.time) || !numbers(value.shape, 3) || !value.shape.every(count) || !numbers(value.depth_m, value.shape[0]) || !numbers(value.latitude, value.shape[1]) || !numbers(value.longitude, value.shape[2]) || !Array.isArray(value.values) || value.values.length !== value.shape.reduce((a,b) => a*b, 1) || value.values.length > 100000 || !value.values.every(v => v === null || finite(v)) || !strings(value.processing) || typeof value.manifest_sha256 !== 'string') throw new ApiError('The model values could not be verified.');
  return value as Subset;
}

export function parseObservation(value: unknown): Observation {
  if (!record(value) || value.schema_version !== '1' || value.kind !== 'observation' || typeof value.qc_policy !== 'string' || typeof value.depth_method !== 'string' || !Array.isArray(value.levels) || value.levels.length !== value.samples || !value.levels.every(v => record(v) && count(v.source_level_index) && ['pressure_dbar', 'depth_m', 'temperature_c', 'salinity_psu'].every(k => v[k] === null || finite(v[k])) && typeof v.eligible === 'boolean' && record(v.qc) && ['PRES','TEMP','PSAL'].every(k => typeof (v.qc as Record<string,unknown>)[k] === 'string')) || !profileSummary(value)) throw new ApiError('The instrument profile could not be verified.');
  return value as Observation;
}

export async function getApi<T>(path: string, parse: (value: unknown) => T, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', forwardAbort, { once: true });
  // An eight-second deadline also cut off valid reads during short connection
  // stalls. Keep a finite budget while allowing the transport time to recover.
  // User/query cancellation still aborts immediately, including body transfer.
  const timer = window.setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(path, { signal: controller.signal, headers: { Accept: 'application/json' }, cache: 'no-store' });
    const serverVersion = response.headers.get('X-Ocean-App-Version');
    if (serverVersion && serverVersion !== appVersion) {
      throw new ApiError('A new version of Depth Atlas is available. Reload to continue with the updated workspace.', response.headers.get('X-Request-ID') ?? undefined, 'update');
    }
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null);
      const detail = record(payload) && record(payload.error) ? payload.error : null;
      throw new ApiError(detail && typeof detail.message === 'string' ? detail.message : 'The service is temporarily unavailable.', response.headers.get('X-Request-ID') ?? undefined);
    }
    const body = await response.text();
    let payload: unknown;
    try { payload = JSON.parse(body); } catch {
      throw new ApiError('The service returned an unreadable response.', response.headers.get('X-Request-ID') ?? undefined, 'response');
    }
    return parse(payload);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (signal?.aborted) throw error;
    throw new ApiError(controller.signal.aborted ? 'The service took too long to respond. Please try again.' : 'Could not reach the service. Check your connection and try again.');
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', forwardAbort);
  }
}
