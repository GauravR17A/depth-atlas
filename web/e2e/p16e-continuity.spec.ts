import release from '../../api/release.json' with {type:'json'};
import {expect,test,type Page} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {enterWorkspace,openTool,dismissIntroduction} from './ux-helpers';

const examples=resolve(import.meta.dirname,'../../casepacks/instruments/examples');
async function openImport(page:Page){await enterWorkspace(page);await openTool(page,'Open instruments');await expect(page.getByLabel('Observed sample value')).toBeVisible();await page.getByRole('button',{name:'Import observations',exact:true}).click();}
async function save(page:Page,title:string){await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name',{exact:true}).fill(title);await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible({timeout:55000});}
async function download(page:Page,name:string){const pending=page.waitForEvent('download');await page.getByRole('button',{name,exact:true}).click();const file=await pending;return (await file.path())!;}
const fixture=(i:number,n=2500)=>({name:`load-${i}.csv`,mimeType:'text/csv',buffer:Buffer.from('profile_id,instrument,platform,time,latitude,longitude,pressure_dbar,pressure_qc,position_qc,time_qc,temperature_c,temperature_qc,salinity_psu,salinity_qc\n'+Array.from({length:n},(_,z)=>`load-${i},argo,TEST-FIXTURE-${i},2024-03-29T00:00:00Z,12.5,85.5,${z/2},1,1,1,${28-z/500},1,35,1\n`).join(''))});

test('batch keeps genuine valid files around one rejected file and permits individual review',async({page})=>{
 test.setTimeout(65000);await openImport(page);await page.locator('.import-panel input[type=file]').setInputFiles([
 {name:'D2903891_012.nc',mimeType:'application/octet-stream',buffer:await readFile(resolve(examples,'D2903891_012.nc'))},
 {name:'broken.nc',mimeType:'application/octet-stream',buffer:Buffer.from('not,a,profile\n1,2,3')},
 {name:'SR1902594_034.nc',mimeType:'application/octet-stream',buffer:await readFile(resolve(examples,'SR1902594_034.nc'))}]);
 const queue=page.getByLabel('File review queue');await expect(queue).toContainText('failed',{timeout:35000});await expect(queue.getByText('ready',{exact:true})).toHaveCount(2,{timeout:35000});await expect(page.getByRole('button',{name:'Add all reviewed files'})).toBeEnabled();
 await queue.getByRole('button',{name:'SR1902594_034.nc',exact:true}).click();await expect(page.getByLabel('Import preview')).toContainText('Chlorophyll');
 await page.getByRole('button',{name:'Add all reviewed files'}).click();await expect(queue.getByText('added',{exact:true})).toHaveCount(2);await expect(page.getByLabel('Instrument profile')).toHaveValue(/^import-bgc/);
 await queue.getByRole('button',{name:'broken.nc',exact:true}).click();await expect(page.getByRole('button',{name:'Retry selected file'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('cancelling a batch preserves a completed preview and never adds a late response',async({page})=>{
 await openImport(page);let release!:()=>void;const gate=new Promise<void>(r=>release=r);let requests=0;
 await page.route('**/api/instruments/inspect?**',async route=>{requests++;if(requests===2)await gate;try{await route.continue();}catch{}});
 await page.locator('.import-panel input[type=file]').setInputFiles([fixture(1,2),fixture(2,2),fixture(3,2)]);
 await expect(page.getByLabel('File review queue')).toContainText('ready');await expect.poll(()=>requests).toBe(2);
 await page.getByRole('button',{name:'Cancel review',exact:true}).click();release();
 await expect(page.getByLabel('File review queue').getByText('cancelled',{exact:true})).toHaveCount(2);
 await page.getByRole('button',{name:'Add all reviewed files'}).click();await expect(page.getByLabel('File review queue').getByText('added',{exact:true})).toHaveCount(1);expect(requests).toBe(2);
 await expect(page.getByLabel('Instrument profile')).toHaveValue(/^import-argo-load-1/);
});

test('late model metadata preserves the running observation review',async({page})=>{
 let releaseModel!:()=>void,releaseImport!:()=>void;
 const modelGate=new Promise<void>(r=>releaseModel=r),importGate=new Promise<void>(r=>releaseImport=r);
 await page.route('**/api/cases/bay-bengal-2024-01',async route=>{const response=await route.fetch();await modelGate;try{await route.fulfill({response});}catch{}});
 await page.route('**/api/instruments/inspect?**',async route=>{await importGate;try{await route.continue();}catch{}});
 await openImport(page);await page.locator('.import-panel input[type=file]').setInputFiles(fixture(7,2));await expect(page.getByRole('button',{name:'Cancel review',exact:true})).toBeVisible();
 releaseModel();await expect(page.getByLabel('Native model value')).toContainText('22.303');
 await expect(page.getByRole('button',{name:'Cancel review',exact:true})).toBeVisible();releaseImport();
 await expect(page.getByLabel('Import preview')).toBeVisible();await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();await expect(page.getByLabel('Instrument profile')).toHaveValue(/^import-argo-load-7/);
});

test('a failed large-file connection can be explicitly retried without replacing earlier evidence',async({page})=>{
 test.setTimeout(120000);await openImport(page);const previous=await page.getByLabel('Instrument profile').inputValue();
 await page.route('**/api/instruments/inspect?**',route=>route.abort('connectionreset'),{times:1});
 await page.locator('.import-panel input[type=file]').setInputFiles(resolve(examples,'SR1902594_034.nc'));
 await expect(page.getByRole('button',{name:'Retry selected file',exact:true})).toBeVisible();await expect(page.getByLabel('Instrument profile')).toHaveValue(previous);
 await page.getByRole('button',{name:'Retry selected file',exact:true}).click();await expect(page.getByLabel('Import preview')).toContainText('Chlorophyll',{timeout:35000});
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();await expect(page.getByLabel('Instrument profile')).toHaveValue(/^import-bgc/);
 await save(page,'Recovered BGC evidence');const path=await download(page,'Offline viewer');expect(await readFile(path,'utf8')).toContain('Observation: Chlorophyll a');
});

test('measured 20000-sample batch is bounded and a later quota failure retains it',async({page},info)=>{
 test.setTimeout(120000);await openImport(page);
 const client=info.project.name.startsWith('chromium')?await page.context().newCDPSession(page):null;if(client){await client.send('Performance.enable');await client.send('HeapProfiler.collectGarbage');}
 const before=client?await client.send('Performance.getMetrics'):null,start=Date.now();
 await page.locator('.import-panel input[type=file]').setInputFiles(Array.from({length:8},(_,i)=>fixture(i)));
 const queue=page.getByLabel('File review queue');await expect(queue.getByText('ready',{exact:true})).toHaveCount(8,{timeout:60000});
 await page.getByRole('button',{name:'Add all reviewed files'}).click();await expect(queue.getByText('added',{exact:true})).toHaveCount(8);
 if(client)await client.send('HeapProfiler.collectGarbage');const after=client?await client.send('Performance.getMetrics'):null;
 await info.attach('bounded-browser-workload',{body:JSON.stringify({kind:'generated resource fixture, not scientific observations',files:8,samples:20000,elapsed_ms:Date.now()-start,metrics_before:before?.metrics,metrics_after:after?.metrics,limits:'one context, Chromium, heap is not full browser RSS'}),contentType:'application/json'});
 await page.locator('.import-panel input[type=file]').setInputFiles(fixture(9,1));await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();await expect(page.locator('.import-panel')).toContainText('Workspace limit reached');
 await expect(page.getByLabel('Observation collection').locator('option').filter({hasText:/^Imported/})).toHaveCount(8);
 await page.locator('.import-panel input[type=file]').setInputFiles(Array.from({length:9},(_,i)=>fixture(i,1)));await expect(page.locator('.import-panel')).toContainText('Choose up to 8 files');
});

test('timed-out review keeps the current profile and can be retried',async({page})=>{
 await openImport(page);const original=await page.getByLabel('Instrument profile').inputValue();let release!:()=>void;const gate=new Promise<void>(r=>release=r);
 await page.route('**/api/instruments/inspect?**',async route=>{await gate;try{await route.continue();}catch{}});await page.clock.install();
 await page.locator('.import-panel input[type=file]').setInputFiles(fixture(4,2));await expect(page.getByRole('button',{name:'Cancel review',exact:true})).toBeVisible();await page.clock.fastForward(31000);
 await expect(page.locator('.import-panel')).toContainText('took too long');await expect(page.getByLabel('Instrument profile')).toHaveValue(original);release();await page.unroute('**/api/instruments/inspect?**');
 await page.getByRole('button',{name:'Retry selected file'}).click();await expect(page.getByLabel('Import preview')).toBeVisible();
});

for(const mode of ['ocean','instrument','comparison','imported'])test(`offline ${mode} viewer retains exact values, works after reload and rejects tampering`,async({page,browser},info)=>{
 test.setTimeout(100000);await enterWorkspace(page);
 if(mode==='ocean')await expect(page.getByLabel('Native model value')).toContainText('22.303');
 if(mode==='imported'){await openTool(page,'Open instruments');await expect(page.getByLabel('Observed sample value')).toBeVisible();await page.getByRole('button',{name:'Import observations',exact:true}).click();await page.locator('.import-panel input[type=file]').setInputFiles(resolve(examples,'SR1902594_034.nc'));await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');}
 if(mode==='instrument'){await openTool(page,'Open instruments');await expect(page.getByLabel('Observed sample value')).toBeVisible();}
 if(mode==='comparison'){await openTool(page,'Compare');await page.getByLabel('Comparison model snapshot').selectOption('1');await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103',{timeout:35000});}
 await save(page,`Offline ${mode}`);const original=JSON.parse(await readFile(await download(page,'Investigation JSON'),'utf8'));
 const html=await readFile(await download(page,'Offline viewer'),'utf8'),path=info.outputPath(`offline-${mode}.html`);await writeFile(path,html);
 const envelope=JSON.parse(html.match(/<script type="application\/json" id="payload">(.*?)<\/script>/s)![1]),payload=JSON.parse(envelope.text);
 expect(payload.record).toEqual(original);expect(payload.series.length).toBeGreaterThan(0);
 const context=await browser.newContext({offline:!info.project.name.startsWith('webkit'),viewport:info.project.use.viewport}),offline=await context.newPage();const requests:string[]=[];await context.route(/^https?:/,route=>route.abort('internetdisconnected'));offline.on('request',r=>{if(r.url().startsWith('http'))requests.push(r.url());});
 await offline.goto(pathToFileURL(path).href);await expect(offline.getByRole('status')).toContainText('Offline saved results');
 if(mode==='imported')await expect(offline.locator('#source-date')).toContainText('2024-03-29');
 const row=payload.series[0].rows[1];await offline.locator('#sample').selectOption({index:1});await offline.getByText('Selected sample and quality flags',{exact:true}).click();await expect(offline.locator('#details')).toHaveText(JSON.stringify(row.details,null,2),{useInnerText:true});
 await offline.getByRole('button',{name:'Next sample',exact:true}).click();await expect(offline.locator('#readout')).toContainText('Sample 2');await offline.reload();await expect(offline.getByRole('status')).toContainText('Offline saved results');expect(requests).toEqual([]);
 expect(await offline.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await offline.screenshot({path:info.outputPath(`offline-${mode}.png`),fullPage:true});
 const bad=info.outputPath('tampered.html');await writeFile(bad,html.replace(`"sha256":"${envelope.sha256}"`,'"sha256":"'+'0'.repeat(64)+'"'));await offline.goto(pathToFileURL(bad).href);await expect(offline.getByRole('status')).toContainText('Checksum mismatch');await expect(offline.locator('#controls')).not.toBeVisible();await context.close();
});

test('cancelled replay leaves saved record usable offline and local removal survives restart',async({page})=>{
 test.setTimeout(90000);await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await save(page,'Retained evidence');
 let release!:()=>void;const gate=new Promise<void>(r=>release=r);await page.route('**/api/investigations/replay',async route=>{await gate;try{await route.continue();}catch{}});
 await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();await page.getByRole('button',{name:'Cancel operation',exact:true}).click();release();await expect(page.getByLabel('Selected saved investigation')).toContainText('Retained evidence');
 await page.context().setOffline(true);const html=await download(page,'Offline viewer');expect((await readFile(html,'utf8')).length).toBeGreaterThan(1000);await page.context().setOffline(false);
 await page.getByRole('button',{name:'Remove local copy of Retained evidence',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Local copy removed.'})).toBeVisible();await page.reload();await dismissIntroduction(page);await page.getByRole('button',{name:'Open saved investigations'}).click();await expect(page.locator('.investigation-library')).toContainText('No local investigations yet.');
});

test('publication status retains last checked data on an offline failure',async({page},info)=>{
 await enterWorkspace(page);await page.locator('.context-actions').getByRole('button',{name:'Sources',exact:true}).click();await page.getByText('Data publication and updates',{exact:true}).click();const panel=page.locator('.publication-status');
 await expect(panel).toContainText('Publication checked:');await expect(panel).toContainText(release.version);
 await page.context().setOffline(true);await panel.getByRole('button',{name:'Check publication',exact:true}).click();await expect(panel.getByRole('alert')).toBeVisible();await expect(panel).toContainText('Publication checked:');await page.context().setOffline(false);
 await page.screenshot({path:info.outputPath('publication-status.png'),fullPage:true});
});
