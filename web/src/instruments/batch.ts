import type { InstrumentProfile } from './contracts';
import { sourceKey, type ImportSources, type ImportedSource } from './imported';

export const importLimits = {files:8, sourceBytes:16_000_000, profiles:32, samples:20_000, decodedBytes:24_000_000};
const bytes = (value:unknown) => new TextEncoder().encode(JSON.stringify(value)).length;

export function mergeImported(existing:InstrumentProfile[], incoming:InstrumentProfile[], sources:ImportSources, source:ImportedSource){
  const profiles=[...existing.filter(p=>!incoming.some(n=>n.id===p.id)),...incoming];
  const allSources={...sources,...Object.fromEntries(incoming.map(p=>[p.id,source]))};
  const originals=new Map(profiles.map(p=>[sourceKey(allSources[p.id]),allSources[p.id]]));
  const originalBytes=[...originals.values()].reduce((n,s)=>n+(s?Math.floor(s.content_base64.length*3/4):0),0);
  if(profiles.length>importLimits.profiles||profiles.reduce((n,p)=>n+p.samples,0)>importLimits.samples||bytes(profiles)>importLimits.decodedBytes||originalBytes>importLimits.sourceBytes)
    throw new Error('Workspace limit reached: 32 profiles, 20,000 samples, 16 MB of originals or 24 MB of decoded data. Earlier additions are kept. Clear imported profiles before adding more.');
  return {profiles,sources:allSources};
}

export function checkBatch(files:File[]){
  if(files.length>importLimits.files||files.reduce((n,f)=>n+f.size,0)>importLimits.sourceBytes)
    throw new Error('Choose up to 8 files and 16 MB in total. Each file still has a 2 MB limit.');
}
