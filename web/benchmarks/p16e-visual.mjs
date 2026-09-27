import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const out=resolve(process.env.OCEAN_VISUAL_DIR??'docs/evidence/p16e-visual-local');await mkdir(out,{recursive:true});
const browser=await chromium.launch(),results=[];
try{
 for(const [name,width,height] of [['desktop',1536,960],['tablet',768,1024],['mobile',393,851]]){
  const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.OCEAN_TEST_URL??'http://127.0.0.1:8035');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.locator('.context-actions').getByRole('button',{name:'Sources',exact:true}).click();await page.getByText('Data publication and updates',{exact:true}).click();await expect(page.locator('.publication-status')).toContainText('Publication checked:');await page.screenshot({path:resolve(out,`publication-${name}.png`)});
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:'Open instruments',exact:true}).click();await expect(page.getByLabel('Observed sample value')).toBeVisible();await page.getByRole('button',{name:'Import observations',exact:true}).click();
  await page.locator('.import-panel input[type=file]').setInputFiles([resolve('casepacks/instruments/examples/D2903891_012.nc'),resolve('casepacks/instruments/examples/SR1902594_034.nc')]);await expect(page.getByLabel('File review queue').getByText('ready',{exact:true})).toHaveCount(2,{timeout:65000});
  await page.getByLabel('File review queue').scrollIntoViewIfNeeded();await page.screenshot({path:resolve(out,`batch-${name}.png`)});
  await page.getByRole('button',{name:'Add all reviewed files'}).click();await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name').fill('Offline BGC profile');await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible({timeout:55000});
  await page.screenshot({path:resolve(out,`saved-${name}.png`)});const promise=page.waitForEvent('download');await page.getByRole('button',{name:'Offline viewer',exact:true}).click();const d=await promise,file=resolve(out,`offline-${name}.html`);await writeFile(file,await readFile(await d.path()));
  const offline=await browser.newPage({viewport:{width,height},offline:true});offline.on('pageerror',e=>errors.push(e.message));await offline.goto(pathToFileURL(file).href);await expect(offline.getByRole('status')).toContainText('Offline saved results');await offline.locator('#view').selectOption({label:'Observation: Chlorophyll a'});await offline.screenshot({path:resolve(out,`offline-${name}.png`)});
  results.push({name,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),dialogOverflow:await page.getByRole('dialog').evaluate(el=>el.scrollWidth>el.clientWidth+1),offlineOverflow:await offline.evaluate(()=>document.documentElement.scrollWidth>innerWidth),errors});await offline.close();await page.close();
 }
}finally{await browser.close();await writeFile(resolve(out,'checks.json'),JSON.stringify(results,null,2));}
console.log(JSON.stringify(results));if(results.some(r=>r.overflow||r.dialogOverflow||r.offlineOverflow||r.errors.length))process.exitCode=1;
