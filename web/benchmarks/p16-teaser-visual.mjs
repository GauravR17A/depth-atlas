import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const out=process.env.OCEAN_VISUAL_DIR??'docs/evidence/p16-teaser-visual';
const base=process.env.OCEAN_TEST_URL??'http://127.0.0.1:8020';
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch();const page=await browser.newPage();const checks=[],errors=[];
page.on('pageerror',error=>errors.push(error.message));
async function capture(name,selector){
  // Only anchored callouts scroll; static dialogs need a layout frame.
  await page.waitForTimeout(selector==='.learning-coach'?1100:50);
  const state=await page.locator(selector).evaluate(e=>{const r=e.getBoundingClientRect();const controls=[...e.querySelectorAll('.learn-navigation .primary-button,.learn-complete button')];return {fits:r.top>=0&&r.bottom<=innerHeight+1&&r.left>=0&&r.right<=innerWidth+1,scrolls:e.scrollHeight>e.clientHeight+1,overflow:document.documentElement.scrollWidth>innerWidth+1,nextVisible:controls.every(button=>{const b=button.getBoundingClientRect();return b.top>=r.top&&b.bottom<=Math.min(r.bottom,innerHeight)+1;})};});
  checks.push({name,...state});await page.screenshot({path:`${out}/${name}.png`});
}
for(const [name,width,height] of [['desktop',1536,960],['mobile',390,844],['narrow',320,568],['landscape',844,390]]){
  await page.setViewportSize({width,height});await page.goto(base);await expect(page.locator('.learning-welcome')).toBeVisible();await capture(`${name}-welcome`,'.learning-welcome');
  await page.getByRole('button',{name:/Explore extra feature tutorials/}).click();
  for(let i=0;i<4;i++){await capture(`${name}-features-${i+1}`,'.feature-tour-picker');if(i<3)await page.getByRole('button',{name:'More features',exact:true}).click();}
  for(let i=0;i<3;i++)await page.getByRole('button',{name:'Back',exact:true}).click();
  await page.getByRole('button',{name:'Start Drift tutorial',exact:true}).click();
  const coach=page.locator('.learning-coach');await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await capture(`${name}-drift`,'.learning-coach');
  await coach.getByRole('button',{name:'Next',exact:true}).click();await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await coach.getByRole('button',{name:'Next',exact:true}).click();await expect(coach.getByRole('heading',{name:'End of the Drift tour'})).toBeVisible();await capture(`${name}-next-feature`,'.learning-coach');
}
await page.setViewportSize({width:768,height:900});await page.emulateMedia({reducedMotion:'reduce'});await page.locator('.learning-coach').getByRole('button',{name:'Try another feature'}).click();await page.addStyleTag({content:'html{font-size:200% !important}'});await capture('enlarged-picker','.feature-tour-picker');
await browser.close();await fs.writeFile(`${out}/checks.json`,JSON.stringify({checks,errors},null,2));const failures=checks.filter(c=>!c.fits||c.overflow||!c.nextVisible||c.scrolls&&!c.name.includes('enlarged'));console.log(JSON.stringify({captures:checks.length,failures,errors},null,2));if(failures.length||errors.length)process.exitCode=1;
