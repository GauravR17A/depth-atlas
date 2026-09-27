import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve(process.env.OCEAN_VISUAL_DIR??'docs/evidence/p16c-visual-local');await mkdir(out,{recursive:true});
const browser=await chromium.launch(),results=[];
for(const [name,width,height] of [['desktop',1536,960],['tablet',768,1024],['mobile',393,851]]){
 const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.OCEAN_TEST_URL??'http://127.0.0.1:8030');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
 await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');await page.getByLabel('Ocean timestamp').locator('option').nth(4).waitFor({state:'attached'});
 await page.getByLabel('Ocean timestamp').selectOption('2');await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:'Open instruments',exact:true}).click();
 await page.getByRole('button',{name:'Import observations',exact:true}).click();await page.getByText('Formats and genuine example files',{exact:true}).click();await page.getByRole('button',{name:'Preview SR1902594_034.nc',exact:true}).click();
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();await page.getByRole('button',{name:'Compare with model',exact:true}).click();
 await page.getByLabel('Eligible comparison count').waitFor();await page.locator('.evidence-heading').scrollIntoViewIfNeeded();
 await page.screenshot({path:resolve(out,`comparison-controls-${name}.png`)});
 await page.getByLabel('Matched profile and residual charts').scrollIntoViewIfNeeded();await page.screenshot({path:resolve(out,`comparison-result-${name}.png`)});
 const count=await page.getByLabel('Eligible comparison count').innerText();const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.screenshot({path:resolve(out,`save-disclosure-${name}.png`)});
 await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await page.getByRole('status').filter({hasText:'Saved on this browser.'}).waitFor({timeout:30000});
 await page.screenshot({path:resolve(out,`saved-import-${name}.png`)});
 results.push({name,count,overflow,dialogOverflow:await page.getByRole('dialog').evaluate(el=>el.scrollWidth>el.clientWidth+1),errors});await page.close();
}
await browser.close();await writeFile(resolve(out,'checks.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
if(results.some(r=>r.overflow||r.dialogOverflow||r.errors.length))process.exitCode=1;
