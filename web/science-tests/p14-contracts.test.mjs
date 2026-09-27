import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks, stripTypeScriptTypes } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Test-only loading of the actual browser contracts, without a new bundler or
// runtime dependency. The generated fixture below is never a deployed dataset.
const sourceRoot = new URL('../src/', import.meta.url).href;
const releaseUrl = new URL('../../api/release.json', import.meta.url).href;
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.') && context.parentURL?.startsWith(sourceRoot)) {
      const url = new URL(specifier, context.parentURL);
      if (url.href === releaseUrl) return { url: url.href, format: 'module', shortCircuit: true };
      if (existsSync(fileURLToPath(url) + '.ts')) return { url: url.href + '.ts', format: 'module', shortCircuit: true };
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url === releaseUrl) return { format: 'module', source: `export const version=${JSON.stringify(JSON.parse(readFileSync(new URL(url), 'utf8')).version)};`, shortCircuit: true };
    if (url.startsWith(sourceRoot) && url.endsWith('.ts')) return { format: 'module', source: stripTypeScriptTypes(readFileSync(new URL(url), 'utf8'), { mode: 'transform' }), shortCircuit: true };
    return next(url, context);
  },
});
const { parseBlackout } = await import('../src/blackout/contracts.ts');
const time = '2024-01-07T12:00:00Z';
const settings = { variable: 'temperature', time_index: 1, time_window_hours: 6, distance_km: 5, max_vertical_gap_m: 500, qc: 'good_probably_good' };
const emptyMetrics = { count: 0, bias: null, rmse: null, mae: null, maximum_abs_residual: null };
const metricsA = { count: 2, bias: 1, rmse: Math.sqrt(5), mae: 2, maximum_abs_residual: 3 };
const metricsB = { count: 1, bias: -2, rmse: 2, mae: 2, maximum_abs_residual: 2 };

function profile(id, instrument, samples, eligible, metrics) {
  return {
    profile: {
      id, instrument, platform: id, title: 'Synthetic parser fixture, never deployed',
      time, time_end: time, latitude: 15, longitude: 85, samples, depth_range_m: [10, 30],
      parameters: { temperature: { label: 'Fixture temperature', units: '°C', definition: 'Test-only numeric input', source_field: 'TEMP', mode: 'D', qc_scheme: 'Argo', accepted_count: eligible } },
      collection: 'Synthetic test collection', source_url: 'https://example.invalid/fixture',
      source_file: 'parser-fixture', source_sha256: 'c'.repeat(64), track: [],
    },
    total_samples: samples, matched_count: eligible, excluded_count: samples - eligible,
    exclusion_counts: { observation_qc: samples - eligible }, eligible_depths_m: Array(eligible).fill(10),
    time_offset_hours_min: 0, time_offset_hours_max: 0, minimum_abs_time_offset_hours: eligible ? 0 : null,
    distance_km_min: eligible ? 0 : null, distance_km_max: eligible ? 0 : null, metrics,
    suggested_time_index: null, suggested_matched_count: 0, suggested_time_offset_hours: null, suggested_distance_km: null,
  };
}

function fixture() {
  const profiles = [profile('test-a', 'argo', 3, 2, metricsA), profile('test-b', 'argo', 2, 1, metricsB), profile('test-c', 'ctd', 2, 0, emptyMetrics)];
  const baseline = {
    schema_version: '1', kind: 'observation_coverage', method_version: 'p05-native-column-v1',
    case_id: 'synthetic-test-only', manifest_sha256: 'a'.repeat(64), observation_library_sha256: 'b'.repeat(64),
    model_time: time, settings, total_profiles: 3, matched_profiles: 2, total_samples: 7,
    matched_samples: 3, excluded_samples: 4, exclusion_counts: { observation_qc: 4 }, profiles, methods: [], caveats: [],
  };
  const modified = { ...baseline, total_profiles: 2, matched_profiles: 1, total_samples: 4, matched_samples: 1, excluded_samples: 3, exclusion_counts: { observation_qc: 3 }, profiles: profiles.slice(1) };
  return {
    schema_version: '1', kind: 'observation_blackout', method_version: 'p14-blackout-v1',
    case_id: baseline.case_id, manifest_sha256: baseline.manifest_sha256, observation_library_sha256: baseline.observation_library_sha256,
    query: { settings, excluded_profile_ids: ['test-a'], excluded_instruments: [], excluded_platforms: [], excluded_collections: [] }, units: '°C',
    baseline, modified, baseline_metrics: { count: 3, bias: 0, rmse: Math.sqrt(14 / 3), mae: 2, maximum_abs_residual: 3 }, modified_metrics: metricsB,
    profile_effects: profiles.map((entry, index) => ({ profile_id: entry.profile.id, excluded_by_user: index === 0, selected_by: index === 0 ? ['profile:test-a'] : [], baseline_matched_samples: entry.matched_count, remaining_matched_samples: index === 0 ? 0 : entry.matched_count, removed_eligible_samples: index === 0 ? 2 : 0, removed_sample_indices: index === 0 ? [11, 37] : [], original_metrics: entry.metrics })),
    excluded_profile_ids: ['test-a'], removed_profiles: 1, removed_eligible_profiles: 1, removed_samples: 3, removed_eligible_samples: 2,
    statements: [{ id: 'residual_statistics', baseline: 'Original residuals', modified: 'Retained residuals', changed: true }],
    model_unchanged: true, source_qc_unchanged: true, methods: [], caveats: [],
  };
}

test('blackout accepts original sparse source identifiers above the profile row count', () => {
  const result = parseBlackout(fixture());
  assert.equal(result.baseline.profiles[0].total_samples, 3);
  assert.deepEqual(result.profile_effects[0].removed_sample_indices, [11, 37]);
});

test('blackout still rejects duplicate negative and fractional source identifiers', () => {
  for (const indices of [[11, 11], [-1, 37], [11.5, 37]]) {
    const data = fixture(); data.profile_effects[0].removed_sample_indices = indices;
    assert.throws(() => parseBlackout(data), /could not be verified/);
  }
});

test('blackout keeps exact metric changes when rounded statement text is identical', () => {
  const data = fixture();
  // Same display at six significant digits; the metrics remain different.
  data.baseline_metrics.bias = -2.00000000001;
  data.modified_metrics = { ...data.modified_metrics, bias: -2.00000000002 };
  data.statements[0].baseline = data.statements[0].modified = 'Rounded displayed bias: -2 °C';
  data.statements[0].changed = true;
  assert.equal(parseBlackout(data).statements[0].changed, true);
  data.statements[0].changed = false;
  assert.throws(() => parseBlackout(data), /could not be verified/);
});
