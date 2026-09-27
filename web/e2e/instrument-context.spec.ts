import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { locateInstruments,inModel,overlapsModelTime } from '../src/instruments/context';
import type { CaseManifest } from '../src/contracts';
import type { InstrumentProfile,InstrumentSummary } from '../src/instruments/contracts';

const source:InstrumentProfile=JSON.parse(readFileSync(resolve(import.meta.dirname,'../../tests/fixtures/p16a-chlorophyll-profile.json'),'utf8'));
// Synthetic location fixtures only, with known expected coordinates and times.
const manifest={case:{bounds:[85,12,90,15]},coordinates:{times:['2024-01-07T00:00:00Z','2024-01-10T00:00:00Z']}} as CaseManifest;
test('marker positions use eligible sample coordinates and their own time',()=>{
 const p={...source,id:'import-fixture',levels:[
  {...source.levels[0],latitude:20,longitude:87,coordinate_eligible:true,time:'2024-01-07T00:00:00Z'},
  {...source.levels[0],latitude:13,longitude:88,coordinate_eligible:false,time:'2024-01-08T00:00:00Z'},
  {...source.levels[0],latitude:14,longitude:89,coordinate_eligible:true,time:'2024-01-09T00:00:00Z'},
 ]};
 const result=locateInstruments(manifest,[p]);
 expect(result[0].marker).toEqual({latitude:14,longitude:89,time:'2024-01-09T00:00:00Z'});
 expect(result[0].latitude).toBe(source.latitude);
 expect(result[0].imported).toBe(true);
 expect(locateInstruments(manifest,[{...p,levels:p.levels.slice(0,2)}])).toEqual([]);
});
test('track-only markers do not invent per-position times and dateline locations are preserved',()=>{
 const {levels,...summary}=source;void levels;
 const track={...summary,latitude:20,longitude:87,track:[[87,20],[88,14]]} as InstrumentSummary;
 expect(locateInstruments(manifest,[track])[0].marker).toEqual({latitude:14,longitude:88,time:null});
 const crossing={...manifest,case:{...manifest.case,bounds:[170,-5,190,5]}} as CaseManifest;
 expect(inModel(crossing,{latitude:0,longitude:-175})).toBe(true);
 const point={...source,levels:[{...source.levels[0],latitude:0,longitude:-175,coordinate_eligible:true}]};
 expect(locateInstruments(crossing,[point])[0].marker.longitude).toBe(-175);
 expect(inModel(crossing,{latitude:0,longitude:-160})).toBe(false);
 expect(overlapsModelTime(manifest,source)).toBe(false);
 expect(overlapsModelTime(manifest,{...source,time:'2024-01-08T00:00:00Z',time_end:'2024-01-08T00:00:00Z'})).toBe(true);
});
