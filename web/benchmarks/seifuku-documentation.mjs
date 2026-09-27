import {chromium,expect as rawExpect} from '@playwright/test';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const base='https://seifuku-ocean-navigator.vercel.app';
const out=resolve('submission/documentation-assets');await mkdir(out,{recursive:true});
const browser=await chromium.launch(),context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage(),expect=rawExpect.configure({timeout:45000}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const library=JSON.parse(await readFile('casepacks/instruments/index.json','utf8'));
const profile=library.profiles.find(p=>p.platform==='1902669').id;
let passed=false;
try{
 await page.goto(base);await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
 const globe=page.getByRole('region',{name:'Ocean data globe'});await expect(globe).toBeVisible();await expect(page.getByLabel('Globe model case')).toBeEnabled();
 await globe.screenshot({path:resolve(out,'globe.png')});
 await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');
 await expect(page.locator('.ocean-render-status')).toHaveText('Interactive 3D');await page.getByRole('button',{name:'Cutaway',exact:true}).click();await page.waitForTimeout(650);
 await page.locator('.ocean-explorer').screenshot({path:resolve(out,'volume.png')});
 await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:'Compare',exact:true}).click();
 await page.getByLabel('Comparison model snapshot').selectOption('1');await page.getByLabel('Comparison profile').selectOption(profile);await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');await expect(page.getByLabel('Selected comparison sample')).toContainText('-0.152');
 await page.getByRole('button',{name:'Expand comparison',exact:true}).click();
 await page.getByLabel('Matched profile and residual charts').screenshot({path:resolve(out,'comparison.png')});
 await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name',{exact:true}).fill('Seifuku documentation verification');await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible();
 await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();await expect(page.locator('.replay-notice')).toContainText('Recalculation matched');
 passed=errors.length===0;
}catch(e){errors.push(String(e));}finally{await browser.close();await writeFile('docs/evidence/seifuku-domain-browser.json',JSON.stringify({at:new Date().toISOString(),base,release:'0.17.0',passed,errors,checks:['globe','native22.303','interactive3D','optionalcutaway','comparison103pairs','residual-0.152','explicitbrowserlocalsave','exactrecalculation'],screenshots:out},null,2));}
console.log(JSON.stringify({passed,errors}));if(!passed)process.exitCode=1;
