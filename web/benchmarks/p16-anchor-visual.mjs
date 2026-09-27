import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
const out=process.env.OCEAN_VISUAL_DIR??'docs/evidence/p16-anchor-visual-settled';
const base=process.env.OCEAN_TEST_URL??'http://127.0.0.1:8019';
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch();const page=await browser.newPage();const checks=[];const errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
async function capture(name){
 await page.waitForTimeout(1200);
 const state=await page.evaluate(()=>{
  const c=document.querySelector('.learning-coach'),t=document.querySelector('.tour-spotlight'),n=document.querySelector('.learn-navigation .primary-button');
  const box=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,b:r.bottom,r:r.right};};
  const card=box(c),target=box(t),next=box(n),v={w:document.documentElement.clientWidth,h:innerHeight};
  const save=document.querySelector('.learn-save-hint');
  return {saveVisible:!!save&&save.getBoundingClientRect().height>0,card,target,next,v,side:c?.dataset.side,id:c?.dataset.target,anchored:c?.dataset.anchored,scroll:scrollY,overlap:card&&target?Math.max(0,Math.min(card.r,target.r)-Math.max(card.x,target.x))*Math.max(0,Math.min(card.b,target.b)-Math.max(card.y,target.y)):0,overflow:document.documentElement.scrollWidth>v.w+1};
 });
 await page.screenshot({path:`${out}/${name}.png`});checks.push({name,...state});
}
const coach=page.locator('.learning-coach');
async function jump(name){await coach.locator('.learn-contents summary').click();await coach.getByRole('button',{name,exact:true}).click();}
for(const [name,width,height] of [['desktop',1536,960],['mobile',390,844],['narrow',320,568],['landscape',844,390]]){
 await page.setViewportSize({width,height});await page.goto(base);await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();await expect(coach.getByLabel('Tutorial result')).toBeVisible();await capture(`${name}-volume`);
 for(const id of ['cutaway','depth','slice','overlay','profile','compare']){
  await coach.getByRole('button',{name:'Next',exact:true}).click();await expect(coach).toHaveAttribute('data-target',id);await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await capture(`${name}-${id}`);
 }
 await jump('17. Keep a finding you can reopen');await expect(page.locator('.learn-save-hint')).toBeVisible();await page.locator('.learn-save-hint').scrollIntoViewIfNeeded();await capture(`${name}-save`);await page.getByRole('button',{name:'Close form and continue tutorial'}).click();
 await coach.getByRole('button',{name:'Skip',exact:true}).click();await page.getByRole('button',{name:'Quick guide'}).click();await page.getByRole('radio',{name:/In-depth/}).check();await page.getByRole('button',{name:'Start In-depth tutorial'}).click();await expect(coach.getByLabel('Tutorial result')).toBeVisible();await coach.getByRole('button',{name:'Understand',exact:true}).click();await capture(`${name}-concept`);await coach.getByRole('button',{name:'Method',exact:true}).click();await capture(`${name}-method`);
}
await page.setViewportSize({width:768,height:900});await page.emulateMedia({reducedMotion:'reduce'});await page.addStyleTag({content:'html{font-size:200% !important}'});await capture('enlarged-text-method');
await browser.close();await fs.writeFile(`${out}/checks.json`,JSON.stringify({checks,errors},null,2));const failures=checks.filter(x=>!x.saveVisible&&(x.overlap>2||x.overflow||x.anchored!=='true'||!x.target||x.target.h<18||x.next.b>x.v.h+1||x.next.b>x.card.b+1));console.log(JSON.stringify({captures:checks.length,failures,errors},null,2));if(failures.length||errors.length)process.exitCode=1;
