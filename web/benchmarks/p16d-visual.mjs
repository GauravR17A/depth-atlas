import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve(process.env.OCEAN_VISUAL_DIR??'docs/evidence/p16d-visual-local');await mkdir(out,{recursive:true});
const browser=await chromium.launch(),results=[];
try{
for(const [name,width,height] of [['desktop',1536,960],['tablet',768,1024],['mobile',393,851]]){
 const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.OCEAN_TEST_URL??'http://127.0.0.1:8033');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
 await page.getByLabel('Ocean timestamp').locator('option').nth(6).waitFor({state:'attached'});
 await expect(page.getByLabel('Native model value')).toContainText('22.303');
 await page.getByRole('button',{name:'Build investigation',exact:true}).click();
 await page.screenshot({path:resolve(out,`builder-${name}.png`)});
 await page.getByRole('button',{name:'Close investigation builder',exact:true}).click();
 await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:'Compare',exact:true}).click();
 await page.getByLabel('Comparison model snapshot').selectOption('1');
 await page.getByRole('button',{name:'Find a useful comparison',exact:true}).click();
 await page.getByLabel('Eligible comparison count').waitFor();
 await page.getByLabel('Matched profile and residual charts').scrollIntoViewIfNeeded();
 await page.screenshot({path:resolve(out,`linked-comparison-${name}.png`)});
 await page.getByRole('button',{name:'Keep this result as reference',exact:true}).click();
 await page.locator('#matching-sensitivity').scrollIntoViewIfNeeded();
 await page.screenshot({path:resolve(out,`matching-sensitivity-${name}.png`)});
 await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:'Open structure search',exact:true}).click();
 await page.getByRole('button',{name:'Show observation support',exact:true}).click();await page.getByLabel('Structure support counts').waitFor();
 await page.locator('.support-map').scrollIntoViewIfNeeded();await page.screenshot({path:resolve(out,`support-map-${name}.png`)});
 const count=await page.getByLabel('Structure support counts').innerText();const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 results.push({name,count,overflow,errors});await page.close();
}
}finally{await browser.close();await writeFile(resolve(out,'checks.json'),JSON.stringify(results,null,2));}
console.log(JSON.stringify(results));
if(results.some(r=>r.overflow||r.errors.length))process.exitCode=1;
