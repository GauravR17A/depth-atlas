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
const {parseWideField,parseWideCatalog,verifyPack,cacheField,cachedField,cacheStats,cacheKey,DEFAULT_QUERY}=await import('../src/wider/contracts.ts');
const fixture=JSON.parse(readFileSync(new URL('../../docs/evidence/p15-parser-fixture.json',import.meta.url),'utf8'));
test('real native fields keep original coordinates units and pressure',async()=>{for(const pack of fixture.packs){const r=await verifyPack(pack);assert.equal(r.field.query.resolution,'native');assert.ok(r.field.values.some(v=>v!==null));}assert.equal(parseWideCatalog(fixture.catalog).datasets.length,2);});
test('regional parser rejects malformed native shapes and numeric queries',()=>{for(const mutate of [x=>x.native_shape=[1],x=>x.native_shape=[1000,1000,1000],x=>x.query.north=null,x=>x.query.time_index=3,x=>x.longitude.reverse(),x=>x.source_indices.longitude[1]=x.source_indices.longitude[0],x=>x.units='fake']){const data=JSON.parse(fixture.packs[0].payload_text).field;mutate(data);assert.throws(()=>parseWideField(data));}});
test('ML pressure cannot be relabelled metres or observations',()=>{for(const mutate of [x=>x.dataset.vertical_units='m',x=>x.dataset.kind='observation']){const data=JSON.parse(fixture.packs[1].payload_text).field;mutate(data);assert.throws(()=>parseWideField(data));}});
test('offline checksum rejects altered values before display',async()=>{const p=structuredClone(fixture.packs[0]);p.payload_text+=' ';await assert.rejects(()=>verifyPack(p),/checksum/);});
test('regional field cache is bounded and source-keyed',()=>{const field=JSON.parse(fixture.packs[0].payload_text).field;for(let i=0;i<9;i++)cacheField('fixture-'+i,field);assert.equal(cacheStats().items,6);assert.ok(cacheStats().bytes<=cacheStats().limit);assert.equal(cachedField('fixture-0'),undefined);assert.notEqual(cacheKey(DEFAULT_QUERY,'a'),cacheKey(DEFAULT_QUERY,'b'));});
