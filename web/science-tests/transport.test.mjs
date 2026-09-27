import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
const source=readFileSync(new URL('../src/contracts.ts',import.meta.url),'utf8').replace(/import \{ version as appVersion \} from '[^']+';/,"const appVersion='test';");
const {getApi}=await import('data:text/javascript;base64,'+Buffer.from(stripTypeScriptTypes(source,{mode:"transform"})).toString('base64'));
globalThis.window={setTimeout,clearTimeout};
test('invalid JSON is a response error, interrupted transfers stay retryable service errors',async()=>{
  const original=globalThis.fetch;
  try{
    for(const [error,kind] of [[new SyntaxError('Bad JSON'),'response'],[new TypeError('Transfer interrupted'),'service'],[new DOMException('Body aborted','AbortError'),'service']]){
      globalThis.fetch=async()=>({ok:true,headers:new Headers(),text:async()=>{if(error instanceof SyntaxError)return '<html>Bad response</html>';throw error;}});
      await assert.rejects(getApi('/sample',v=>v),e=>e.kind===kind);
    }
  }finally{globalThis.fetch=original;}
});
test('caller cancellation preserves cancellation and never displays a service fault',async()=>{
  const original=globalThis.fetch;const signal=new AbortController();signal.abort();
  try{globalThis.fetch=async()=>{throw new DOMException('Cancelled','AbortError');};await assert.rejects(getApi('/sample',v=>v,signal.signal),e=>e.name==='AbortError'&&!e.kind);}finally{globalThis.fetch=original;}
});
