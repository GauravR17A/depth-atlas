import { chromium } from '@playwright/test';
import { mkdir,writeFile } from 'node:fs/promises';
import path from 'node:path';
const base=process.argv[2]??'http://127.0.0.1:8006',out=path.resolve(process.argv[3]??'../docs/evidence/p09-visual-local'),scope=process.argv[4]??'all';
await mkdir(out,{recursive:true});const browser=await chromium.launch({headless:true});const checks=[],errors=[];
const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
async function shot(name,locator=page){await locator.screenshot({path:path.join(out,name+'.png')});checks.push({name,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),alerts:await page.getByRole('alert').filter({visible:true}).allTextContents()});await writeFile(path.join(out,'checks.json'),JSON.stringify({base,checks,errors,complete:false},null,2));}
try {
for(const [cid,label] of [['bay-bengal-2024-01','bay'],['arabian-sea-2024-01','arabian']]){
  if(scope!=='all'&&label!==scope)continue;
  await page.goto(base);await page.getByLabel('Study case',{exact:true}).selectOption(cid);await page.getByLabel('Graphics quality').selectOption('balanced');
  await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();await shot(label+'-volume',page.locator('.ocean-stage'));
  await page.getByRole('button',{name:'Cutaway',exact:true}).click();await page.waitForTimeout(500);await shot(label+'-cutaway',page.locator('.ocean-stage'));
  for(const [name,mode] of [['Depth slice','slice'],['Section','section'],['Isosurface','iso'],['Current vectors','currents']]){await page.getByRole('button',{name,exact:true}).click();await page.locator(`.ocean-webgl[data-rendered="${mode}"]`).waitFor();await shot(label+'-'+mode,page.locator('.ocean-stage'));}
  await page.getByLabel('Variable',{exact:true}).selectOption('horizontal_kinetic_energy');await page.locator('.ocean-viewport[data-shown-variable="horizontal_kinetic_energy"]').waitFor();await shot(label+'-energy',page.locator('.ocean-stage'));
  await page.getByRole('button',{name:'Start guided investigation',exact:true}).click();await page.getByLabel('Compare at depth',{exact:true}).waitFor();await shot(label+'-guide',page.getByLabel('Guided investigation',{exact:true}));
  await page.getByRole('button',{name:'Next: Compare a measurement',exact:true}).click();await page.getByLabel('Eligible comparison count').waitFor();await shot(label+'-comparison',page.getByLabel('Model and observation comparison',{exact:true}));
  await page.getByRole('button',{name:'Next: Find warm water',exact:true}).click();await page.getByLabel('Structure search results',{exact:true}).waitFor();await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');await shot(label+'-search',page.locator('.feature-overview'));
}
for(const width of [800,390,320]){
  await page.setViewportSize({width,height:900});await page.goto(base);await page.getByRole('button',{name:'Start guided investigation',exact:true}).click();await page.getByLabel('Compare at depth',{exact:true}).waitFor();await shot('guide-'+width,page.getByLabel('Guided investigation',{exact:true}));
}
await writeFile(path.join(out,'checks.json'),JSON.stringify({base,checks,errors,complete:true},null,2));console.log(JSON.stringify({screenshots:checks.length,errors,overflow:checks.filter(c=>c.overflow),alerts:checks.filter(c=>c.alerts.length)},null,2));
if(errors.length||checks.some(c=>c.overflow||c.alerts.length))process.exitCode=1;
}catch(error){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});await writeFile(path.join(out,'failure.json'),JSON.stringify({message:error.message,checks,errors,alerts:await page.getByRole('alert').filter({visible:true}).allTextContents()},null,2));throw error;}finally{await browser.close();}
