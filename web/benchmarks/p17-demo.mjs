/** Record real browser actions and verified results; no mocked API responses. */
import {chromium,expect as rawExpect} from '@playwright/test';
import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const base=process.env.OCEAN_TEST_URL??'http://127.0.0.1:8038';
const out=resolve(process.env.OCEAN_DEMO_DIR??'docs/evidence/p17-demo');await mkdir(out,{recursive:true});
const browser=await chromium.launch(),context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:resolve(out,'raw'),size:{width:1440,height:900}}});
const page=await context.newPage(),expect=rawExpect.configure({timeout:45000}),events=[],errors=[],start=performance.now();
const library=JSON.parse(await readFile(new URL('../../casepacks/instruments/index.json',import.meta.url),'utf8'));
const profile=library.profiles.find(p=>p.platform==='1902669').id;
page.on('pageerror',e=>errors.push(e.message));
const mark=async(text)=>{events.push({seconds:Number(((performance.now()-start)/1000).toFixed(2)),text});await page.waitForTimeout(3500);};
const tool=async(name)=>{await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name,exact:true}).click();};
let passed=false;
try{
 await page.goto(base);await expect(page.getByRole('button',{name:'Start Basic tutorial',exact:true})).toBeVisible();await mark('Basic guidance is the default. We will use the same controls directly for this short demonstration.');
 await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(page.getByLabel('Globe model case')).toBeEnabled();await mark('The globe locates genuine bounded datasets. These are historical cases with source dates, not live global coverage.');
 await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');await mark('Open the selected Bay of Bengal case. Colour represents the selected variable, with units and depth.');
 await page.getByRole('button',{name:'Cutaway',exact:true}).click();await page.getByRole('button',{name:'Rotate ocean right',exact:true}).click();await mark('The optional cutaway reveals the water column. Vertical exaggeration changes the display, not the data.');
 await page.getByRole('button',{name:'Depth slice',exact:true}).click();await page.getByLabel('Explorer depth').selectOption('19');await expect(page.getByLabel('Native model value')).toContainText('22.303');await mark('At 100 metres the native source value remains inspectable. Missing depths stay missing.');
 await tool('Compare');await page.getByLabel('Comparison model snapshot').selectOption('1');await page.getByLabel('Comparison profile').selectOption(profile);await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');await page.getByLabel('Matched profile and residual charts').scrollIntoViewIfNeeded();await expect(page.getByLabel('Selected comparison sample')).toContainText('-0.152');await mark('Compare an Argo observation with a compatible model snapshot. Dates, matching rules and the model-minus-observation residual are explicit. Agreement is not independent validation.');
 await page.screenshot({path:resolve(out,'comparison.png')});
 await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name',{exact:true}).fill('Bay of Bengal: source comparison');await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible();await mark('Save source identities, settings and results on this browser. A portable file can be exported.');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Investigation JSON',exact:true}).click();await(await download).saveAs(resolve(out,'demo-investigation.json'));
 await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();await expect(page.locator('.replay-notice')).toContainText('Recalculation matched');await mark('Reopening recalculates the investigation and checks the saved result against its original sources and method.');
 await page.getByRole('button',{name:'Tools',exact:true}).click();await expect(page.getByRole('dialog',{name:'What would you like to find out?'})).toBeVisible();await mark('Tools contains the other investigations: particle drift, climate, heat, structures, observations and wider data. Each keeps its scientific limits visible.');
 passed=errors.length===0;
}catch(error){errors.push(String(error));}finally{
 await context.close();const recording=await page.video().path();await copyFile(recording,resolve(out,'ocean-navigator-demonstration.webm'));await browser.close();
 await writeFile(resolve(out,'recording.json'),JSON.stringify({at:new Date().toISOString(),base,passed,events,errors,description:'Unedited real-browser recording. Narration cues are separate. Browser-local test save only; no external submission.'},null,2));
}
console.log(JSON.stringify({passed,events:events.length,errors}));if(!passed)process.exitCode=1;
