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
const {mergeImported,checkBatch}=await import('../src/instruments/batch.ts');
const {offlineSeries}=await import('../src/investigations/offline.ts');
const source={source_sha256:'a'.repeat(64),filename:'input.csv',parser_version:'observation-preview-v1',content_base64:'YQ==',mapping:null};
const profile=(id,samples)=>({id,samples,levels:[]});
test('batch count and source budgets reject before requests',()=>{assert.throws(()=>checkBatch(Array.from({length:9},()=>({size:1}))),/8 files/);assert.throws(()=>checkBatch([{size:16000001}]),/16 MB/);checkBatch([{size:2000000}]);});
test('workspace aggregates samples and deduplicates replaced profiles',()=>{const first=mergeImported([], [profile('a',10000)],{},source);const replaced=mergeImported(first.profiles,[profile('a',10000),profile('b',10000)],first.sources,source);assert.equal(replaced.profiles.length,2);assert.throws(()=>mergeImported(replaced.profiles,[profile('c',1)],replaced.sources,source),/20,000/);assert.equal(replaced.profiles.length,2);});
test('workspace bounds decoded bytes and profile count independently',()=>{assert.throws(()=>mergeImported([],Array.from({length:33},(_,i)=>profile(String(i),1)),{},source),/32 profiles/);assert.throws(()=>mergeImported([],[{...profile('a',1),oversize:'x'.repeat(24000000)}],{},source),/decoded data/);});
test('offline comparison retains exact residual, excluded rows and source sample identity',()=>{const rows=[{sample_index:4,depth_m:12.25,observed:25,model:26,residual:1,accepted:true},{sample_index:7,depth_m:23.75,observed:27,model:null,residual:null,accepted:false}];const series=offlineSeries({results:[{module:'comparison',output:{profile:{title:'test'},settings:{variable:'temperature'},units:'C',rows}}]});assert.equal(series.length,2);assert.deepEqual(series[0].rows.map(r=>r.depth),[12.25,23.75]);assert.deepEqual(series[1].rows.map(r=>r.values),[[1],[null]]);assert.equal(series[0].rows[1].accepted,false);assert.equal(series[0].rows[1].details.sample_index,7);});
test('offline profile keeps missing values, excluded QC and each variable units',()=>{const r={value:null,accepted:false,qc:'9'},p={parameters:{chlorophyll:{label:'Chlorophyll',units:'mg/m3'}},levels:[{index:12,depth_m:null,readings:{chlorophyll:r}}]};const [s]=offlineSeries({results:[{module:'observation_profile',output:p}]});assert.equal(s.units,'mg/m3');assert.equal(s.rows[0].depth,null);assert.deepEqual(s.rows[0].values,[null]);assert.equal(s.rows[0].details.reading.qc,'9');});
test('native column preserves irregular depths, masks and exact component values',()=>{const [s]=offlineSeries({results:[{module:'native_profile',method_version:'native',output:{columns:[{variable:'u',units:'m/s',depth_m:[0,2,50],latitude:[12],longitude:[85],values:[.1,null,-.2]}]}}]});assert.deepEqual(s.rows.map(r=>r.depth),[0,2,50]);assert.deepEqual(s.rows.map(r=>r.values),[[.1],[null],[-.2]]);assert.equal(s.rows[1].accepted,false);});
