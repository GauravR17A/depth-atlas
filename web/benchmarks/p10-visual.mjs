import { chromium } from '@playwright/test';
import { mkdir,writeFile } from 'node:fs/promises';
import path from 'node:path';
const base=process.argv[2]??'http://127.0.0.1:8008',out=path.resolve(process.argv[3]??'../docs/evidence/p10-visual-local');
await mkdir(out,{recursive:true});const browser=await chromium.launch({headless:true}),checks=[],errors=[];
const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));
async function shot(name,locator=page){await locator.screenshot({path:path.join(out,name+'.png')});checks.push({name,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),alerts:await page.getByRole('alert').filter({visible:true}).allTextContents()});await writeFile(path.join(out,'checks.json'),JSON.stringify({base,checks,errors,complete:false},null,2));}
try{
for(const [cid,label] of [['bay-bengal-2024-01','bay'],['arabian-sea-2024-01','arabian']]){
 await page.goto(base);await page.getByLabel('Study case',{exact:true}).selectOption(cid);await page.getByRole('button',{name:'Expedition',exact:true}).click();
 await page.getByLabel('Applied expedition plan',{exact:true}).waitFor();await shot(label+'-workspace',page.getByLabel('Virtual Expedition',{exact:true}));
 await page.getByRole('button',{name:'Select suggested station 3',exact:true}).click();await shot(label+'-map',page.locator('.expedition-plan-layout'));
 await page.getByRole('button',{name:'Sample a route',exact:true}).click();await page.getByLabel('Virtual survey snapshot',{exact:true}).selectOption('4');await page.getByRole('button',{name:'Sample virtual route',exact:true}).click();await page.getByLabel('Simulated survey results',{exact:true}).waitFor();await shot(label+'-survey',page.getByLabel('Simulated survey results',{exact:true}));
 await page.getByRole('button',{name:'Compare strategies',exact:true}).click();await page.getByRole('button',{name:'Run reconstruction test',exact:true}).click();await page.getByLabel('Sampling strategy results',{exact:true}).waitFor();await shot(label+'-benchmark',page.getByLabel('Sampling strategy results',{exact:true}));
 await page.getByText('Inspect every snapshot and failure',{exact:true}).click();await shot(label+'-trials',page.getByLabel('Sampling strategy results',{exact:true}));
}
await page.getByLabel('Station budget',{exact:true}).fill('16');await page.getByLabel('Station minimum spacing',{exact:true}).fill('150');await page.getByRole('button',{name:'Update station plan',exact:true}).click();await page.getByText(/Only \d+ stations could be selected/).waitFor();await page.getByRole('button',{name:'Run reconstruction test',exact:true}).click();await page.getByText('Some selected or uniform runs failed.',{exact:false}).waitFor();await shot('constraint-failure',page.getByLabel('Sampling strategy results',{exact:true}));
for(const width of [800,390,320]){
 await page.setViewportSize({width,height:900});await page.goto(base);await page.getByRole('button',{name:'Expedition',exact:true}).click();await page.getByLabel('Applied expedition plan',{exact:true}).waitFor();await shot('plan-'+width,page.getByLabel('Virtual Expedition',{exact:true}));
 await page.getByRole('button',{name:'Compare strategies',exact:true}).click();await page.getByRole('button',{name:'Run reconstruction test',exact:true}).click();await page.getByLabel('Sampling strategy results',{exact:true}).waitFor();await shot('benchmark-'+width,page.getByLabel('Sampling strategy results',{exact:true}));
}
await page.setViewportSize({width:900,height:1000});await page.addStyleTag({content:'html{font-size:200% !important}'});await page.getByRole('button',{name:'Plan stations',exact:true}).click();await shot('enlarged-text',page.getByLabel('Virtual Expedition',{exact:true}));
await writeFile(path.join(out,'checks.json'),JSON.stringify({base,checks,errors,complete:true},null,2));console.log(JSON.stringify({screenshots:checks.length,errors,overflow:checks.filter(c=>c.overflow),alerts:checks.filter(c=>c.alerts.length)},null,2));if(errors.length||checks.some(c=>c.overflow||c.alerts.length))process.exitCode=1;
}catch(error){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});await writeFile(path.join(out,'failure.json'),JSON.stringify({message:error.message,checks,errors,alerts:await page.getByRole('alert').filter({visible:true}).allTextContents()},null,2));throw error;}finally{await browser.close();}
