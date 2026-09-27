import { queryOptions } from '@tanstack/react-query';
import { ApiError, appVersion, getApi, parseSubset, type CaseManifest, type ScientificVariable, type Subset } from '../contracts';
import type { Variable } from '../store';
import { speed } from './grid';

export type FieldData = { data: Subset; east?: Subset; north?: Subset };

async function read(manifest: CaseManifest, field: ScientificVariable | 'horizontal_kinetic_energy', time: number, signal: AbortSignal, point?: number[]) {
  const params = new URLSearchParams({ variable: field, time_index: String(time), representation: point ? 'analytical' : 'display', operation: 'volume' });
  const longitude = point ? [manifest.coordinates.longitude[point[0]]] : manifest.display_coordinates.longitude;
  const latitude = point ? [manifest.coordinates.latitude[point[1]]] : manifest.display_coordinates.latitude;
  if (point) {
    params.set('west', String(longitude[0])); params.set('east', String(longitude[0]));
    params.set('south', String(latitude[0])); params.set('north', String(latitude[0]));
  }
  return getApi(`/api/cases/${encodeURIComponent(manifest.case.id)}/subset?${params}`, value => {
    const g = parseSubset(value);
    const expected = [manifest.coordinates.depth_m, latitude, longitude];
    if (g.case_id !== manifest.case.id || g.variable !== field || g.time !== manifest.coordinates.times[time] || g.units !== (field === 'horizontal_kinetic_energy' ? 'm²/s²' : manifest.variables.find(v => v.id === field)!.units) || g.representation !== params.get('representation') || JSON.stringify([g.depth_m, g.latitude, g.longitude]) !== JSON.stringify(expected)) {
      throw new ApiError('The requested field and returned data do not match.', undefined, 'response');
    }
    return g;
  }, signal);
}

async function readData(manifest: CaseManifest, variable: Variable, time: number, signal: AbortSignal, point?: number[]): Promise<FieldData> {
  if (variable !== 'currents') return { data: await read(manifest, variable, time, signal, point) };
  const [east, north] = await Promise.all([read(manifest, 'eastward_velocity', time, signal, point), read(manifest, 'northward_velocity', time, signal, point)]);
  try { return { data: speed(east, north), east, north }; }
  catch { throw new ApiError('Current components do not share the same source and timestamp.', undefined, 'response'); }
}

// This release pins an immutable case pack. Cache its verified data in memory,
// bounded to ten minutes of inactivity, and separate entries by application version.
export function fieldOptions(manifest: CaseManifest, variable: Variable, time: number) {
  return queryOptions({ queryKey: ['ocean-frame', appVersion, manifest.case.id, variable, time], queryFn: ({ signal }) => readData(manifest, variable, time, signal), staleTime: Infinity, gcTime: 600_000 });
}

// Read all forty native levels at one location once. Depth selection then uses
// the original array index, with no interpolation or extra network round trip.
export function profileOptions(manifest: CaseManifest, variable: Variable, time: number, point: number[], expectedHash?: string) {
  const xy = point.slice(0, 2);
  return queryOptions({ queryKey: ['native-column', appVersion, manifest.case.id, expectedHash, variable, time, ...xy], queryFn: async ({ signal }) => {
    const result = await readData(manifest, variable, time, signal, xy);
    if (expectedHash && result.data.manifest_sha256 !== expectedHash) throw new ApiError('The source point and displayed field come from different dataset versions.', undefined, 'response');
    return result;
  }, staleTime: Infinity, gcTime: 600_000 });
}
