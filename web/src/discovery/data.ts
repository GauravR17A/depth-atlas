import type { CaseSummary } from '../contracts';
import type { InstrumentProfile, InstrumentSummary } from '../instruments/contracts';
import { longitudeOnAxis, normalizedLongitude } from '../geography';

export type LocatedObservation = { profile: InstrumentSummary; position: [number, number]; time: string; positionMeaning: string };
export function caseCenter(c: CaseSummary): [number, number] {
  const [w,s,e,n]=c.bounds;
  return [normalizedLongitude((w+(e<w?e+360:e))/2),(s+n)/2];
}
export function containsPosition(c: CaseSummary, longitude: number, latitude: number) {
  const [w,s,rawEast,n]=c.bounds,e=rawEast<w?rawEast+360:rawEast,lon=longitudeOnAxis(longitude,[w,e]);
  return lon>=w&&lon<=e&&latitude>=s&&latitude<=n;
}
// These are positions, not an interpolated surface, concentration or coverage estimate.
// Imported moving profiles use the first eligible source coordinate for this variable.
export function locateObservations(profiles:(InstrumentSummary|InstrumentProfile)[],variable?:string):LocatedObservation[] {
  return profiles.flatMap(p=>{
    if(variable&&!p.parameters[variable])return [];
    if('levels' in p){
      const l=p.levels.find(l=>l.coordinate_eligible&&(!variable||l.readings[variable]?.value!==null&&l.readings[variable]!==undefined));
      return l?[{profile:p,position:[normalizedLongitude(l.longitude),l.latitude] as [number,number],time:l.time,positionMeaning:'First eligible source position for this view. Open the profile for its full track and sample QC.'}]:[];
    }
    if(!Number.isFinite(p.longitude)||!Number.isFinite(p.latitude)||Math.abs(p.latitude)>90)return [];
    return [{profile:p,position:[normalizedLongitude(p.longitude),p.latitude] as [number,number],time:p.time,positionMeaning:'Recorded first profile position. Open the profile to inspect its track, sample positions and QC.'}];
  });
}
export function modelContexts(cases:CaseSummary[],observation:LocatedObservation){
  return cases.filter(c=>containsPosition(c,...observation.position)).map(c=>({
    model:c,
    timeOverlap:Date.parse(observation.time)>=Date.parse(c.time_start)&&Date.parse(observation.time)<=Date.parse(c.time_end),
  })).sort((a,b)=>Number(b.timeOverlap)-Number(a.timeOverlap)||a.model.id.localeCompare(b.model.id));
}
export function footprint(bounds:CaseSummary['bounds']):GeoJSON.Polygon{
  const [w,s,rawE,n]=bounds,e=rawE<w?rawE+360:rawE;
  const points:number[][]=[[w,s],[w,n]];
  for(let x=w+1;x<e;x++)points.push([x,n]);
  points.push([e,n],[e,s]);for(let x=e-1;x>w;x--)points.push([x,s]);points.push([w,s]);
  return {type:'Polygon',coordinates:[points]};
}
