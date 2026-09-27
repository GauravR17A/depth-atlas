import type { Example } from '../instruments/contracts';
import { inspectFile } from '../instruments/ImportReview';
import { retainSource } from '../instruments/imported';

export async function readPublicExample(example:Example,signal:AbortSignal){
  if(example.bytes>2_000_000)throw new Error('This example exceeds the supported file limit.');
  const response=await fetch(`/api/instruments/examples/${encodeURIComponent(example.name)}`,{signal});
  if(!response.ok)throw new Error('The public observation file could not load. Try again.');
  const bytes=await response.arrayBuffer();
  if(bytes.byteLength!==example.bytes)throw new Error('The source file size changed. Reload before opening it.');
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');
  if(hash!==example.sha256)throw new Error('The example no longer matches its source checksum.');
  const file=new File([bytes],example.name),review=await inspectFile(file,undefined,signal);
  if(!review.result||review.source_sha256!==hash)throw new Error(review.issue??'The original profile could not be verified.');
  const source=await retainSource(file,hash,review.parser_version);
  const profiles=review.result.profiles.map(p=>({...p,id:`import-${p.id}`,collection:`Imported \u00b7 ${example.name}`,metadata:{...p.metadata,original_profile_id:p.id}}));
  return {profiles,source};
}
