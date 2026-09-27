import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const base=process.env.OCEAN_TEST_URL??'http://127.0.0.1:8018';
const out=path.resolve(process.env.OCEAN_VISUAL_DIR??'docs/evidence/ux-visual-local');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch();const errors=[],checks=[];
const page=await browser.newPage({viewport:{width:1536,height:960}});
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
async function capture(name){await page.waitForTimeout(220);await page.screenshot({path:path.join(out,`${name}.png`)});const result=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,alerts:[...document.querySelectorAll('[role=alert]')].filter(e=>e.getBoundingClientRect().height).map(e=>e.textContent)}));checks.push({name,...result});}
async function readyScene(){await expect(page.getByLabel('Native model value')).toContainText('22.303',{timeout:30000});await expect(page.getByText('Loading the ocean field',{exact:true})).toHaveCount(0);}
async function intro(size,name){await page.setViewportSize(size);await page.goto(base);await page.getByRole('button',{name:'Next',exact:true}).waitFor();for(let i=0;i<3;i++){await capture(`${name}-step-${i+1}`);const fits=await page.locator('.intro-dialog').evaluate(e=>{const r=e.getBoundingClientRect();return {width:r.width,height:r.height,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,bottom:r.bottom,inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight+1,contentFits:e.scrollHeight<=e.clientHeight+1};});checks.push({name:`${name}-intro-fit-${i+1}`,...fits});await page.getByRole('button',{name:i===2?'Start exploring':'Next',exact:true}).click();}}
await intro({width:1536,height:960},'desktop');await page.getByLabel('Native model value').filter({hasText:'22.303'}).waitFor();await capture('desktop-explorer');
await page.getByRole('button',{name:'Cutaway',exact:true}).click();await page.waitForTimeout(500);await capture('desktop-cutaway');
await page.getByRole('button',{name:'Tools',exact:true}).click();await capture('desktop-tools');await page.getByRole('button',{name:'Close tools',exact:true}).click();
const tools=[['Open instruments','instruments'],['Compare','comparison'],['Open structure search','features'],['Open Drift Lab','drift'],['Open Heat and Depth Lab','heat'],['Open Climate Event Lab','climate'],['Open Virtual Expedition','expedition'],['Open feature evolution','evolution'],['Open observation blackout','blackout'],['Open wider ocean coverage','wider'],['Geographic context','geography']];
for(const [label,name] of tools){await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:label,exact:true}).click();if(await page.getByRole('heading',{name:/Choose a case for/}).isVisible())await page.getByRole('button',{name:/Bay of Bengal/}).click();await page.waitForTimeout(1000);await page.evaluate(()=>scrollTo(0,0));await capture(`desktop-${name}`);}
await intro({width:390,height:844},'mobile');await readyScene();await capture('mobile-explorer');await page.getByRole('button',{name:'Tools',exact:true}).click();await capture('mobile-tools');await page.getByRole('button',{name:'Open Drift Lab',exact:true}).click();await capture('mobile-drift');
await intro({width:320,height:568},'narrow');await readyScene();await capture('narrow-explorer');
await intro({width:844,height:390},'landscape');
await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:640,height:720});await page.goto(base);await page.getByRole('button',{name:'Skip introduction',exact:true}).waitFor();await capture('zoom-equivalent-intro');await page.getByRole('button',{name:'Skip introduction',exact:true}).click();await readyScene();await capture('zoom-equivalent-explorer');
await fs.writeFile(path.join(out,'checks.json'),JSON.stringify({base,checkedAt:new Date().toISOString(),checks,errors},null,2));await browser.close();console.log(JSON.stringify({captures:checks.filter(x=>'overflow'in x).length,checks:checks.length,failures:checks.filter(x=>x.overflow||x.contentFits===false||x.inside===false),errors},null,2));
