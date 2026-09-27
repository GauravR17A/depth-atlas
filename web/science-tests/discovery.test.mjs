import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
registerHooks({resolve(specifier,context,next){return specifier==='../geography'?{url:new URL('../geography.ts',context.parentURL).href,shortCircuit:true}:next(specifier,context);}});
const { caseCenter,containsPosition,locateObservations,modelContexts,footprint } = await import('../src/discovery/data.ts');
const model={id:'fixture',bounds:[170,-10,-160,10],time_start:'2024-01-01T00:00:00Z',time_end:'2024-01-02T00:00:00Z'};
test('globe dateline domains preserve native positions and do not cover the other hemisphere',()=>{
 assert.deepEqual(caseCenter(model),[-175,0]);assert.equal(containsPosition(model,-170,0),true);assert.equal(containsPosition(model,190,0),true);assert.equal(containsPosition(model,0,0),false);assert.equal(containsPosition(model,-170,12),false);
 const p=footprint(model.bounds);assert.deepEqual(p.coordinates[0][0],p.coordinates[0].at(-1));assert.equal(Math.max(...p.coordinates[0].map(p=>p[0])),200);
});
test('chlorophyll markers require actual parameter data and keep the first eligible sample time',()=>{
 const summary={id:'test',latitude:1,longitude:80,time:'2024-01-01T00:00:00Z',parameters:{temperature:{}}};
 assert.equal(locateObservations([summary],'chlorophyll').length,0);
 const profile={...summary,parameters:{chlorophyll:{}},levels:[{coordinate_eligible:false,latitude:1,longitude:80,time:summary.time,readings:{chlorophyll:{value:9}}},{coordinate_eligible:true,latitude:2,longitude:181,time:'2024-01-02T00:00:00Z',readings:{chlorophyll:{value:null}}},{coordinate_eligible:true,latitude:3,longitude:182,time:'2024-01-03T00:00:00Z',readings:{chlorophyll:{value:-.01,accepted:false}}}]};
 const [point]=locateObservations([profile],'chlorophyll');assert.deepEqual(point.position,[-178,3]);assert.equal(point.time,'2024-01-03T00:00:00Z');assert.equal(point.profile.levels[2].readings.chlorophyll.value,-.01); // Locator never promotes QC or paints a concentration field.
});
test('model context uses the actual marker time and labels area-only overlap separately',()=>{
 const p={position:[190,0],time:'2024-01-03T00:00:00Z'};
 const contexts=modelContexts([model,{...model,id:'matching',time_end:p.time},{...model,id:'elsewhere',bounds:[50,0,60,10]}],p);
 assert.deepEqual(contexts.map(c=>[c.model.id,c.timeOverlap]),[['matching',true],['fixture',false]]);
 assert.equal('accepted' in contexts[0],false);
});
