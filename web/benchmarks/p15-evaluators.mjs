/** Four isolated browser sessions, one bounded regional workflow per evaluator. */
import {chromium,expect as rawExpect} from '@playwright/test';
import {writeFile} from 'node:fs/promises';
const base=process.argv[2],out=process.argv[3],expect=rawExpect.configure({timeout:45000});
const browser=await chromium.launch({headless:true});const rows=[];
try{
 await Promise.all(Array.from({length:4},async(_,id)=>{
  const context=await browser.newContext({viewport:{width:1280,height:900}});await context.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));const page=await context.newPage();const row={id,errors:[],failedAPI:[],source:id<2?'godas-2022':'gobai-v2.2'};rows.push(row);
  page.on('pageerror',e=>row.errors.push(e.message));page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)row.failedAPI.push({path:new URL(r.url()).pathname,status:r.status()});});
  const start=performance.now();await page.goto(base);await page.getByRole('button',{name:'Open wider ocean coverage',exact:true}).click();await expect(page.getByRole('combobox',{name:'Data source',exact:true})).toBeEnabled();await page.getByRole('combobox',{name:'Data source',exact:true}).selectOption(row.source);await page.getByRole('combobox',{name:'Regional month',exact:true}).selectOption(String(id%2));await page.getByRole('button',{name:id%2?'Across the date line':'Southern Indian Ocean',exact:true}).click();const load=performance.now();await page.getByRole('button',{name:'Load region',exact:true}).click();await expect(page.locator('.wide-status')).toContainText('Region loaded');row.regionalLoadMs=performance.now()-load;
  await page.locator('.wide-data-view canvas').click({position:{x:180,y:140}});await expect(page.getByRole('heading',{name:'Native water column',exact:true})).toBeVisible();await page.getByRole('button',{name:'Save regional pack on device',exact:true}).click();await expect(page.locator('.wide-status')).toContainText('Saved one regional pack');await page.getByRole('button',{name:'Verify replay online',exact:true}).click();await expect(page.locator('.wide-status')).toContainText('Server replay matched');row.fullWorkflowMs=performance.now()-start;
  const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');const metrics=await cdp.send('Performance.getMetrics');row.jsHeapUsedBytes=metrics.metrics.find(m=>m.name==='JSHeapUsedSize')?.value;row.passed=row.errors.length===0&&row.failedAPI.length===0;await context.close();
 }));
 const report={base,at:new Date().toISOString(),scope:'Four isolated Chromium sessions on one test computer. This is a small concurrency sample, not a sustained capacity forecast.',sessions:rows,passed:rows.every(r=>r.passed)};await writeFile(out,JSON.stringify(report,null,2));if(!report.passed)process.exitCode=1;
}catch(e){await writeFile(out,JSON.stringify({base,passed:false,error:String(e),sessions:rows},null,2));throw e;}finally{await browser.close();}
