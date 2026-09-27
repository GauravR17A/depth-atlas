import { longitudeOnAxis } from '../geography';
import type { CaseManifest } from '../contracts';
import type { InstrumentProfile, InstrumentSummary } from './contracts';

export function inModel(manifest:CaseManifest|undefined,point:{latitude:number;longitude:number}){
  if(!manifest)return false;
  const [w,s,e,n]=manifest.case.bounds,longitude=longitudeOnAxis(point.longitude,[w,e]);
  return longitude>=w&&longitude<=e&&point.latitude>=s&&point.latitude<=n;
}
export type LocatedInstrument=InstrumentSummary & {marker:{longitude:number;latitude:number;time:string|null};imported:boolean};
export function locateInstruments(manifest:CaseManifest|undefined,profiles:(InstrumentSummary|InstrumentProfile)[]):LocatedInstrument[]{
  if(!manifest)return [];
  return profiles.flatMap<LocatedInstrument>(p=>{
    const imported=p.id.startsWith('import-');
    if('levels' in p){
      const l=p.levels.find(l=>l.coordinate_eligible&&inModel(manifest,l));
      return l?[{...p,imported,marker:{longitude:l.longitude,latitude:l.latitude,time:l.time}}]:[];
    }
    if(inModel(manifest,p))return [{...p,imported,marker:{longitude:p.longitude,latitude:p.latitude,time:p.time}}];
    // The summary track has positions, not sample timestamps. Never assign its
    // first timestamp to a later location; the profile provides the exact time.
    const point=p.track.find(([longitude,latitude])=>inModel(manifest,{longitude,latitude}));
    return point?[{...p,imported,marker:{longitude:point[0],latitude:point[1],time:null}}]:[];
  });
}
export function overlapsModelTime(manifest:CaseManifest|undefined,p:InstrumentSummary){
  if(!manifest)return false;
  const times=manifest.coordinates.times.map(Date.parse);
  return Date.parse(p.time)<=Math.max(...times)&&Date.parse(p.time_end)>=Math.min(...times);
}
