import { appVersion } from '../contracts';
export type Mapping=Record<string,{source:string;units?:string|null}|null>;
export type ImportedSource={schema_version:'1';filename:string;content_base64:string;source_sha256:string;parser_version:string;mapping:Mapping|null};
export type ImportSources=Record<string,ImportedSource>;
export async function retainSource(file:File,source_sha256:string,parser_version:string,mapping?:Mapping):Promise<ImportedSource>{
  const bytes=new Uint8Array(await file.arrayBuffer());let raw='';
  for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));
  return {schema_version:'1',filename:file.name,content_base64:btoa(raw),source_sha256,parser_version,mapping:mapping??null};
}
export const sourceKey=(s?:ImportedSource)=>s?JSON.stringify([s.source_sha256,s.filename,s.parser_version,s.mapping]):'library';
export async function importedEvidence<T>(caseId:string,kind:'comparison'|'coverage',payload:unknown,parse:(raw:unknown)=>T,signal:AbortSignal):Promise<T>{
  const response=await fetch(`/api/cases/${encodeURIComponent(caseId)}/evidence/imported/${kind}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal,cache:'no-store'});
  if(response.headers.get('X-Ocean-App-Version')!==appVersion)throw new Error('Reload the workspace before comparing imported observations.');
  const raw=await response.json();if(!response.ok)throw new Error(raw?.error?.message??'The imported comparison could not be completed.');
  return parse(raw);
}
