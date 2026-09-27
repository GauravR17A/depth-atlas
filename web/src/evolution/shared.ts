import { ApiError, appVersion } from '../contracts';

export const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
export const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
export const count = (value: unknown): value is number => finite(value) && Number.isInteger(value) && value >= 0;
export const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');
export const numbers = (value: unknown): value is number[] => Array.isArray(value) && value.every(finite);
export const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const stamp = (value: unknown): value is string => typeof value === 'string' && value.endsWith('Z') && Number.isFinite(Date.parse(value));
export const equal = (a: unknown, b: unknown): boolean => object(a) && object(b) && Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([key, value]) => Array.isArray(value) ? JSON.stringify(value) === JSON.stringify(b[key]) : object(value) ? equal(value, b[key]) : value === b[key]);
export const number = (value: number | null, digits = 3) => value === null ? 'Not available' : value !== 0 && Math.abs(value) < 10 ** -digits ? value.toPrecision(3) : value.toLocaleString('en-US', { maximumFractionDigits: digits });
export const utc = (value: string) => value.replace('T', ' ').replace(/:00Z$/, ' UTC').replace('Z', ' UTC');
export const invalid = (lab: string) => new ApiError(`The ${lab} response could not be verified. Your previous verified result is kept.`, undefined, 'response');

export async function postAnalysis<T>(path: string, body: unknown, parse: (raw: unknown) => T, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController(), abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 60000);
  try {
    const response = await fetch(path, { method: 'POST', signal: controller.signal, cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) });
    if (response.headers.get('X-Ocean-App-Version') !== appVersion) throw new ApiError('The workspace has been updated. Reload before continuing.', undefined, 'update');
    const raw: unknown = await response.json();
    if (!response.ok) throw new ApiError(object(raw) && object(raw.error) && typeof raw.error.message === 'string' ? raw.error.message : 'The calculation could not finish. Try again.');
    return parse(raw);
  } catch (error) {
    if (error instanceof ApiError || signal?.aborted) throw error;
    throw new ApiError(controller.signal.aborted ? 'The calculation timed out. Your completed result is kept. Try a shorter time window.' : 'Could not reach the ocean service. Your completed result is kept.');
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
