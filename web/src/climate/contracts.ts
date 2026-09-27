import { ApiError, appVersion } from '../contracts';

export type ClimateQuery = { event_id: 'son-2013' | 'son-2015' | 'son-2022'; reference_event_id: 'son-2013' | 'son-2015' | 'son-2022'; period: 'SON' | '09' | '10' | '11'; longitude_index: number; depth_index: number };
export type ClimateRecipe = { mode: 'climate'; case_id: string; query: ClimateQuery };
export type ClimateEvent = { event_id: ClimateQuery['event_id']; year: number; season: 'SON'; case_id?: string; enso: { classification: 'el_nino' | 'la_nina' | 'neutral'; index_id: string; value_c: number }; iod: { classification: string; classification_basis: string; seasonal_dmi_c: number; index_id: string; episode_timing_note: string; event_label_source_id: string | null }; legacy_enso_context: { index_id: string; value_c: number; classification: string }[]; monthly_context: { month: number; centered_season: string; season_months: string[]; roni_v6_c: number; oni_v5_c: number; oni_v6_c: number; cpc_dmi_v6_c: number; interpretation: string }[] };
export type ClimateSource = { source_id?: string; title?: string; name?: string; url?: string; source_url?: string; provider?: string; dataset_version?: string; sha256?: string; retrieved_at?: string; [key: string]: unknown };
export type ClimateSectionData = { latitude: number; latitude_index: number; longitude: number[]; depth_m: number[]; shape: [number, number]; potential_temperature_c: (number | null)[]; baseline_c: (number | null)[]; anomaly_c: (number | null)[]; note: string };
export type ClimateProfile = Pick<ClimateSectionData, 'depth_m' | 'potential_temperature_c' | 'baseline_c' | 'anomaly_c'> & { latitude: number; longitude: number; longitude_index: number };
export type ClimateDifference = Pick<ClimateSectionData, 'latitude' | 'longitude' | 'depth_m' | 'shape'> & { values_c: (number | null)[] };
export type ClimateScale = { min: number | null; max: number | null; units: string; symmetric: boolean };
export type ClimatePanel = { event: ClimateEvent; case_id: string; model_manifest_sha256: string; period_start: string; period_end_exclusive: string; pacific: ClimateSectionData; indian: ClimateSectionData; profile: ClimateProfile };
export type ClimateAnalysis = { schema_version: string; kind: string; method_version: string; case_id: string; query: ClimateQuery; climate_manifest_sha256: string; model_manifest_sha256: string; baseline: Record<string, unknown>; field_source: ClimateSource; index_definitions: Record<string, Record<string, unknown>>; events: [ClimateEvent, ClimateEvent]; period: { id: string; label: string; [key: string]: unknown }; panels: [ClimatePanel, ClimatePanel]; difference: { pacific: ClimateDifference; indian: ClimateDifference; profile_c: (number | null)[] }; scales: Record<'pacific' | 'indian', Record<'temperature' | 'anomaly' | 'difference', ClimateScale>>; selected_point: { longitude: number; latitude: number; depth_m: number; longitude_index: number; depth_index: number; selected: { potential_temperature_c: number | null; baseline_c: number | null; anomaly_c: number | null }; reference: { potential_temperature_c: number | null; baseline_c: number | null; anomaly_c: number | null }; difference_c: number | null }; observations: { event_id: string; case_id: string; profiles: { id: string; platform?: string; title?: string; time: string; latitude: number; longitude: number; source_url?: string; eligible_samples?: number; samples?: number; data_mode?: string }[] }[]; methods: string[]; caveats: string[] };
export type ClimateCatalog = Pick<ClimateAnalysis, 'schema_version' | 'method_version' | 'climate_manifest_sha256' | 'baseline' | 'field_source' | 'index_definitions' | 'methods' | 'caveats'> & { events: ClimateEvent[]; index_sources: ClimateSource[]; coordinates: { depth_m: number[]; latitude: number[]; longitude: number[] }; periods: { id: ClimateQuery['period']; label: string }[]; default_query: ClimateQuery };
const obj = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const integer = (value: unknown): value is number => finite(value) && Number.isInteger(value) && value >= 0;
const hash = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const strings = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string');
const axis = (value: unknown): value is number[] => Array.isArray(value) && value.length >= 2 && value.every(finite) && value.every((item, index) => index === 0 || item > value[index - 1]);
const values = (value: unknown, length: number): value is (number | null)[] => Array.isArray(value) && value.length === length && value.every(item => item === null || finite(item));
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const fail = () => new ApiError('The climate analysis could not be verified. Your completed analysis has been kept.', undefined, 'response');
export const supportedClimateMethod = (value: unknown) => value === 'p13-climate-v1';
export const climateCaseId = (event: ClimateQuery['event_id']) => `pacific-godas-${event.slice(4)}-son`;
export const ensoLabel = (event: ClimateEvent) => ({ el_nino: 'El Niño', la_nina: 'La Niña', neutral: 'ENSO neutral' })[event.enso.classification];
export const eventLabel = (event: ClimateEvent) => `${event.year} · ${ensoLabel(event)}`;
export function validClimateQuery(value: unknown): value is ClimateQuery { return obj(value) && ['son-2013', 'son-2015', 'son-2022'].includes(String(value.event_id)) && ['son-2013', 'son-2015', 'son-2022'].includes(String(value.reference_event_id)) && ['SON', '09', '10', '11'].includes(String(value.period)) && integer(value.longitude_index) && value.longitude_index < 140 && integer(value.depth_index) && value.depth_index < 28; }
export const sameClimateQuery = (a: ClimateQuery, b: ClimateQuery) => a.event_id === b.event_id && a.reference_event_id === b.reference_event_id && a.period === b.period && a.longitude_index === b.longitude_index && a.depth_index === b.depth_index;
export function validClimateRecipe(value: unknown): value is ClimateRecipe { return obj(value) && value.mode === 'climate' && validClimateQuery(value.query) && value.case_id === climateCaseId(value.query.event_id); }
function event(value: unknown): value is ClimateEvent { return obj(value) && ['son-2013', 'son-2015', 'son-2022'].includes(String(value.event_id)) && integer(value.year) && value.season === 'SON' && obj(value.enso) && ['el_nino', 'la_nina', 'neutral'].includes(String(value.enso.classification)) && finite(value.enso.value_c) && value.enso.index_id === 'roni_v6' && obj(value.iod) && finite(value.iod.seasonal_dmi_c) && typeof value.iod.classification_basis === 'string' && typeof value.iod.episode_timing_note === 'string' && Array.isArray(value.legacy_enso_context) && Array.isArray(value.monthly_context); }
export function parseClimateCatalog(raw: unknown): ClimateCatalog {
  if (!obj(raw) || !supportedClimateMethod(raw.method_version) || !hash(raw.climate_manifest_sha256) || !obj(raw.coordinates) || !axis(raw.coordinates.depth_m) || !axis(raw.coordinates.latitude) || !axis(raw.coordinates.longitude) || !Array.isArray(raw.events) || raw.events.length !== 3 || !raw.events.every(event) || !Array.isArray(raw.periods) || !validClimateQuery(raw.default_query) || !Array.isArray(raw.index_sources) || !obj(raw.field_source) || !obj(raw.baseline) || !obj(raw.index_definitions) || !strings(raw.methods) || !strings(raw.caveats)) throw fail();
  return raw as ClimateCatalog;
}
function section(raw: unknown): raw is ClimateSectionData {
  if (!obj(raw) || !axis(raw.longitude) || !axis(raw.depth_m) || !finite(raw.latitude) || !same(raw.shape, [raw.depth_m.length, raw.longitude.length])) return false;
  const count = raw.depth_m.length * raw.longitude.length;
  if (count > 20000 || !values(raw.potential_temperature_c, count) || !values(raw.baseline_c, count) || !values(raw.anomaly_c, count)) return false;
  const a=raw.potential_temperature_c,b=raw.baseline_c;
  return raw.anomaly_c.every((value, index) => value === (a[index] === null || b[index] === null ? null : a[index]! - b[index]!));
}
export function parseClimate(raw: unknown): ClimateAnalysis {
  if (!obj(raw) || !supportedClimateMethod(raw.method_version) || !validClimateQuery(raw.query) || raw.case_id !== climateCaseId(raw.query.event_id) || !hash(raw.climate_manifest_sha256) || !hash(raw.model_manifest_sha256) || !Array.isArray(raw.panels) || raw.panels.length !== 2 || !Array.isArray(raw.events) || raw.events.length !== 2 || !raw.events.every(event) || !obj(raw.baseline) || !obj(raw.field_source) || !obj(raw.index_definitions) || !obj(raw.period) || raw.period.id !== raw.query.period || !obj(raw.difference) || !obj(raw.scales) || !obj(raw.selected_point) || !Array.isArray(raw.observations) || !strings(raw.methods) || !strings(raw.caveats)) throw fail();
  for (let index = 0; index < 2; index++) {
    const panel = raw.panels[index], expected = index === 0 ? raw.query.event_id : raw.query.reference_event_id;
    if (!obj(panel) || !event(panel.event) || panel.event.event_id !== expected || panel.case_id !== climateCaseId(expected) || !hash(panel.model_manifest_sha256) || !section(panel.pacific) || !section(panel.indian) || !obj(panel.profile) || !same(panel.profile.depth_m, panel.pacific.depth_m) || !finite(panel.profile.longitude) || typeof panel.period_start !== 'string' || typeof panel.period_end_exclusive !== 'string') throw fail();
    const pacific=panel.pacific,x=raw.query.longitude_index;
    for (const key of ['potential_temperature_c', 'baseline_c', 'anomaly_c'] as const) if (!same(panel.profile[key], pacific.depth_m.map((_, z) => pacific[key][z * pacific.longitude.length + x]))) throw fail();
  }
  const result = raw as ClimateAnalysis;
  for (const basin of ['pacific', 'indian'] as const) {
    const a = result.panels[0][basin], b = result.panels[1][basin], d = result.difference[basin];
    if (!obj(d) || !same(a.longitude, b.longitude) || !same(a.depth_m, b.depth_m) || !same(d.longitude, a.longitude) || !same(d.depth_m, a.depth_m) || !values(d.values_c, a.potential_temperature_c.length) || !d.values_c.every((value, index) => value === (a.potential_temperature_c[index] === null || b.potential_temperature_c[index] === null ? null : a.potential_temperature_c[index]! - b.potential_temperature_c[index]!))) throw fail();
    for (const type of ['temperature', 'anomaly', 'difference'] as const) { const scale = result.scales[basin]?.[type]; if (!scale || !(scale.min === null && scale.max === null || finite(scale.min) && finite(scale.max) && scale.min <= scale.max) || scale.symmetric !== (type !== 'temperature')) throw fail(); }
  }
  const point = result.selected_point, { longitude_index: x, depth_index: z } = result.query;
  if (point.longitude_index !== x || point.depth_index !== z || point.longitude !== result.panels[0].pacific.longitude[x] || point.depth_m !== result.panels[0].pacific.depth_m[z]) throw fail();
  for (const [index, key] of ['selected', 'reference'].entries()) for (const value of ['potential_temperature_c', 'baseline_c', 'anomaly_c'] as const) if (point[key as 'selected' | 'reference'][value] !== result.panels[index].profile[value][z]) throw fail();
  if (point.difference_c !== result.difference.pacific.values_c[z * result.panels[0].pacific.longitude.length + x]) throw fail();
  return result;
}
export async function postClimate(query: ClimateQuery, signal: AbortSignal): Promise<ClimateAnalysis> {
  const controller = new AbortController(), abort = () => controller.abort(), timer = setTimeout(abort, 45000);
  signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort();
  try {
    const response = await fetch('/api/climate/analyse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(query), cache: 'no-store', signal: controller.signal });
    if (response.headers.get('X-Ocean-App-Version') !== appVersion) throw new ApiError('The workspace has been updated. Reload to inspect this climate analysis.', undefined, 'update');
    const body = await response.json();
    if (!response.ok) throw new ApiError(body?.error?.message ?? 'The climate service could not finish this request.');
    const result = parseClimate(body); if (!sameClimateQuery(query, result.query)) throw fail(); return result;
  } catch (error) { if (controller.signal.aborted && !signal.aborted) throw new ApiError('The climate calculation took too long. Your completed analysis is kept. Try again.'); throw error; }
  finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}
