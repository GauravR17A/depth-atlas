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
const { selectedOffset } = await import('../src/workspace/selection.ts');
const { parseSupport } = await import('../src/features/support.ts');
const units='\u00b0C',time='2024-01-07T12:00:00Z';
const settings={variable:'temperature',time_index:1,time_window_hours:6,distance_km:5,max_vertical_gap_m:500,qc:'good_probably_good'};
const query={variable:'temperature',units,time_index:1,operator:'at_least',threshold:25,upper_threshold:null,depth_min_m:0,depth_max_m:100,order:'volume'};
const search={case_id:'test-only',manifest_sha256:'a'.repeat(64),model_time:time,units,query,shape:[3,2,2],coordinates:{depth_m:[0,10,100],latitude:[10,11],longitude:[80,81]},regions:[{id:'r4',cell_count:1}]};
function fixture(){return {schema_version:'1',kind:'structure_observation_support',method_version:'p16d-native-support-v1',case_id:search.case_id,manifest_sha256:search.manifest_sha256,observation_library_sha256:'b'.repeat(64),source_scope:'Bundled observation library',model_time:time,query:{...query},region_id:'r4',settings:{...settings},units,eligible_samples:1,eligible_profiles:1,region_cells:1,supported_cells:1,unsupported_cells:0,footprint_indices:[0],supported_columns:[0],unsupported_columns:0,accepted_outside_region:0,excluded_samples:0,exclusion_counts:{},limitations:[],rows:[{profile_id:'profile',platform:'fixture',source_sha256:'c'.repeat(64),cell:[1,0,0],sample_index:37,observation_time:time,latitude:10,longitude:80,depth_m:10,observed:25,model:26,residual:1,accepted:true,reason:'accepted',qc:'1',mode:'R',model_latitude:10,model_longitude:80,distance_km:0,time_offset_hours:0,lower_depth_m:10,upper_depth_m:10,upper_weight:0,model_lower_value:26,model_upper_value:26}]};}
test('noncontiguous source sample IDs synchronize by identity, never by depth or list offset',()=>{
 assert.equal(selectedOffset({profileId:'a',sampleIndex:37},'a',[2,11,37],0),2);
 assert.equal(selectedOffset({profileId:'b',sampleIndex:37},'a',[2,11,37],0),0);
 assert.equal(selectedOffset({profileId:'a',sampleIndex:100},'a',[2,11,37],9),2);
 assert.equal(selectedOffset(undefined,'a',[],0),0);
});
test('support parser accepts checked native coordinates and exact residual arithmetic',()=>assert.deepEqual(parseSupport(fixture(),search,'r4',settings),fixture()));
for(const [label,mutate] of [
 ['fabricated residual',s=>s.rows[0].residual=12],
 ['wrong model time',s=>s.model_time='2024-01-08T12:00:00Z'],
 ['wrong source model',s=>s.manifest_sha256='d'.repeat(64)],
 ['duplicated source pair',s=>{s.rows.push({...s.rows[0]});s.eligible_samples=2;}],
 ['invented coverage',s=>s.supported_cells=2],
 ['wrong native column',s=>s.rows[0].model_latitude=11],
 ['out of bounds cell',s=>s.rows[0].cell=[3,0,0]],
 ['nonmatching settings',s=>s.settings.distance_km=10],
 ['substituted observation date',s=>s.rows[0].observation_time='2026-01-07T12:00:00Z'],
 ['unsupported footprint',s=>s.supported_columns=[1]],
])test(`support rejects ${label}`,()=>{const s=fixture();mutate(s);assert.throws(()=>parseSupport(s,search,'r4',settings));});
test('an imported file must retain its own original and parser identity',()=>{
 const source={filename:'fixture.csv',source_sha256:'c'.repeat(64),parser_version:'observation-preview-v1'};
 const s=fixture();assert.throws(()=>parseSupport(s,search,'r4',settings,source));
 s.source_scope=source.filename;s.import_identity={source_sha256:source.source_sha256,parser_version:source.parser_version,context_sha256:'e'.repeat(64),profiles_sha256:'f'.repeat(64)};
 assert.equal(parseSupport(s,search,'r4',settings,source).source_scope,source.filename);
 s.import_identity.parser_version='other';assert.throws(()=>parseSupport(s,search,'r4',settings,source));
});
