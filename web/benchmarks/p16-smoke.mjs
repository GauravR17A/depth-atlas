import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const base=process.env.OCEAN_TEST_URL??'http://127.0.0.1:8019';
const output=process.env.OCEAN_VISUAL_DIR??'docs/evidence/p16-initial';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1536,height:960}});const errors=[],steps=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
try{
 await page.goto(base);await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).waitFor();await page.screenshot({path:`${output}/welcome.png`});
 await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();
 for(let i=0;i<27;i++){
  const coach=page.getByRole('complementary',{name:'Basic tutorial',exact:true});
  if(i===16){await page.getByRole('button',{name:'Close saved investigations',exact:true}).waitFor();await page.getByRole('button',{name:'Close saved investigations',exact:true}).click();}
  await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});
  if(await page.getByRole('button',{name:'Close saved investigations',exact:true}).isVisible())await page.getByRole('button',{name:'Close saved investigations',exact:true}).click();
  const title=await coach.locator('h2').innerText();steps.push({title,result:await coach.getByLabel('Tutorial result').innerText()});
  if([0,1,12,17,19,20,23,25].includes(i))await page.screenshot({path:`${output}/step-${i}.png`});
  await coach.getByRole('button',{name:'Next',exact:true}).click();
  if(await coach.getByRole('button',{name:'Show me the extra labs'}).isVisible())await coach.getByRole('button',{name:'Show me the extra labs'}).click();
 }
 await expect(page.getByText('You’re ready to explore.')).toBeVisible();
}catch(error){errors.push(String(error));await page.screenshot({path:`${output}/failed.png`});}
await fs.writeFile(`${output}/result.json`,JSON.stringify({base,steps,errors},null,2));console.log(JSON.stringify({steps:steps.length,errors},null,2));await browser.close();if(errors.length)process.exitCode=1;
