import { MAX_FILE_BYTES,type Investigation } from './contracts';
const DB='ocean-navigator-investigations',STORE='records';
export type SavedRecord={id:string;bytes:number;record:Investigation};
function database():Promise<IDBDatabase>{return new Promise((resolve,reject)=>{
  if(!('indexedDB' in window)){reject(new Error('Browser storage is unavailable. Download the investigation file to keep it.'));return;}
  let request:IDBOpenDBRequest;
  try{request=indexedDB.open(DB,1);}catch{reject(new Error('Browser storage access was denied. Download the investigation file to keep it.'));return;}
  request.onupgradeneeded=()=>{request.result.createObjectStore(STORE,{keyPath:'id'});};
  request.onsuccess=()=>{request.result.onversionchange=()=>request.result.close();resolve(request.result);};
  request.onerror=()=>reject(new Error('Browser storage could not be opened. Download a file to keep your investigation.'));
  request.onblocked=()=>reject(new Error('Another tab is holding an older saved-record database. Close it and try again.'));
});}
export async function listRecords():Promise<SavedRecord[]>{const db=await database();return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readonly'),request=tx.objectStore(STORE).getAll();request.onsuccess=()=>resolve((request.result as SavedRecord[]).sort((a,b)=>b.record.created_at.localeCompare(a.record.created_at)));request.onerror=()=>reject(new Error('Saved investigations could not be read.'));tx.oncomplete=()=>db.close();tx.onabort=()=>db.close();});}
export async function storeRecord(record:Investigation){
  const bytes=new TextEncoder().encode(JSON.stringify(record)).length;
  if(bytes>MAX_FILE_BYTES)throw new Error('This investigation exceeds the 8 MB local record limit. Download it as a file.');
  const db=await database();return new Promise<void>((resolve,reject)=>{
    const tx=db.transaction(STORE,'readwrite'),store=tx.objectStore(STORE),request=store.getAll();let problem='The browser could not save this record. Download the investigation file to keep it.';
    request.onsuccess=()=>{const previous=(request.result as SavedRecord[]).filter(r=>r.id!==record.document_sha256);if(previous.length>=25||previous.reduce((s,r)=>s+r.bytes,bytes)>32_000_000){problem='This browser holds at most 25 investigations or 32 MB. Download older records and remove their local copies, then save again.';tx.abort();return;}store.put({id:record.document_sha256,bytes,record});};
    tx.oncomplete=()=>{db.close();resolve();};tx.onabort=()=>{db.close();reject(new Error(problem));};tx.onerror=()=>{problem='The browser storage quota was exceeded or access was denied. Download the investigation file to keep it.';};
  });
}
export async function removeRecord(id:string){const db=await database();return new Promise<void>((resolve,reject)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).delete(id);tx.oncomplete=()=>{db.close();resolve();};tx.onabort=()=>{db.close();reject(new Error('The local copy could not be removed.'));};});}
