import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve(process.env.OCEAN_VISUAL_DIR??'docs/evidence/globe-visual-local');await mkdir(out,{recursive:true});
const browser=await chromium.launch(),results=[];
try{for(const [name,width,height] of [['desktop',1536,960],['tablet',768,1024],['mobile',393,851]]){
 const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.OCEAN_TEST_URL??'http://127.0.0.1:8035');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(page.getByLabel('Globe model case')).toBeVisible();
 await page.screenshot({path:resolve(out,`globe-${name}.png`),fullPage:true});
 await page.getByRole('button',{name:'Chlorophyll observations',exact:true}).click();await page.getByRole('button',{name:'Load public chlorophyll profile'}).click();await expect(page.getByLabel('Globe observation')).toBeVisible({timeout:50000});
 await page.screenshot({path:resolve(out,`chlorophyll-${name}.png`),fullPage:true});
 results.push({name,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),errors});
 if(process.env.OCEAN_TUTORIAL_VISUAL==='1'){
  await page.getByRole('button',{name:'Quick guide',exact:true}).click();await page.getByRole('button',{name:'Explore extra feature tutorials'}).click();await page.screenshot({path:resolve(out,`features-${name}.png`)});
  const dialog=page.locator('.feature-tour-picker');results.at(-1).pickerFits=await dialog.evaluate(e=>e.scrollHeight<=e.clientHeight+1&&e.getBoundingClientRect().bottom<=innerHeight+1);
  await dialog.getByRole('button',{name:'Start Import and review tutorial',exact:true}).click();
  const coach=page.locator('.learning-coach');
  for(let i=0;i<2;i++){await expect(coach.getByLabel('Tutorial result')).toBeVisible({timeout:45000});await coach.getByRole('button',{name:'Next',exact:true}).click();}
  await coach.getByRole('button',{name:'Explore on my own'}).click();
  const hint=page.getByRole('complementary',{name:'Find all tools'});await expect(hint).toBeVisible();await page.waitForTimeout(700);
  await page.screenshot({path:resolve(out,`tools-arrow-${name}.png`)});
  results.at(-1).toolsHintFits=await hint.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+1&&r.left>=0&&r.right<=innerWidth+1;});
  await hint.getByRole('button',{name:'Dismiss Tools hint'}).click();await page.getByRole('button',{name:'Quick guide',exact:true}).click();await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();
  for(let i=0;i<2;i++){await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await coach.getByRole('button',{name:'Next',exact:true}).click();}
  await expect(page.getByLabel('Cutaway',{exact:true})).toHaveAttribute('data-tutorial-control','');await expect(coach.getByLabel('Tutorial result')).toBeVisible();await page.waitForTimeout(700);
  await page.screenshot({path:resolve(out,`control-glow-${name}.png`)});
 }
 await page.close();
}}finally{await browser.close();await writeFile(resolve(out,'checks.json'),JSON.stringify(results,null,2));}
console.log(JSON.stringify(results));if(results.some(r=>r.overflow||r.errors.length||r.pickerFits===false||r.toolsHintFits===false))process.exitCode=1;
