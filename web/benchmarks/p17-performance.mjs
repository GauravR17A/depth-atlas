/** Measured browser workflow, not a capacity forecast or participant study. */
import {chromium, expect as rawExpect} from '@playwright/test';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import os from 'node:os';
const base=process.env.OCEAN_TEST_URL??'http://127.0.0.1:8038';
const out=resolve(process.env.OCEAN_PERF_DIR??'docs/evidence/p17-performance-local');
await mkdir(out,{recursive:true});
const library=JSON.parse(await readFile(new URL('../../casepacks/instruments/index.json',import.meta.url),'utf8'));
const profile=library.profiles.find(p=>p.platform==='1902669').id;
const expect=rawExpect.configure({timeout:45000}), browser=await chromium.launch();
const report={at:new Date().toISOString(),base,host:{platform:os.platform(),release:os.release(),cpu:os.cpus()[0]?.model,logicalCpus:os.cpus().length,memoryBytes:os.totalmem()},browser:browser.version(),limitations:['Same Windows host and headless Chromium; mobile is emulation, not a physical device.','Fresh browser contexts; server/case caches can be warm.','Three samples per condition, not a sustained load or universal performance guarantee.','Throttling is synthetic. Scientific values must remain unchanged.'],runs:[]};
try{
 for(const condition of ['desktop','mobile-throttled'])for(let sample=1;sample<=3;sample++){
  const mobile=condition==='mobile-throttled';
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:900},isMobile:mobile,hasTouch:mobile,deviceScaleFactor:1});
  const page=await context.newPage(),cdp=await context.newCDPSession(page);
  await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
  if(mobile){await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:200000,uploadThroughput:93750});}
  await cdp.send('Performance.enable');
  const row={condition,sample,cpuRate:mobile?4:1,latencyMs:mobile?150:0,downloadBytesPerSecond:mobile?200000:null,errors:[],failedApi:[],timingsMs:{}};report.runs.push(row);
  page.on('pageerror',e=>row.errors.push(e.message));page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)row.failedApi.push({url:new URL(r.url()).pathname,status:r.status()});});
  const start=performance.now();await page.goto(base);await expect(page.getByRole('button',{name:'Skip tutorial',exact:true})).toBeVisible();row.timingsMs.welcome=performance.now()-start;
  await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(page.getByLabel('Globe model case')).toBeEnabled();row.timingsMs.globe=performance.now()-start;
  let t=performance.now();await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');row.timingsMs.openModel=performance.now()-t;
  await expect(page.locator('.ocean-render-status')).toHaveText(/Interactive 3D|Basic 2D/);row.renderMode=await page.locator('.ocean-render-status').innerText();
  t=performance.now();await page.getByRole('button',{name:'Depth slice',exact:true}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');row.timingsMs.slice=performance.now()-t;
  t=performance.now();await page.getByRole('button',{name:'Tools',exact:true}).click();await page.getByRole('button',{name:'Compare',exact:true}).click();await page.getByLabel('Comparison model snapshot').selectOption('1');await page.getByLabel('Comparison profile').selectOption(profile);await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');row.timingsMs.comparison=performance.now()-t;
  await expect(page.getByLabel('Selected comparison sample')).toContainText('-0.152');
  row.timingsMs.workflow=performance.now()-start;
  row.overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  const metrics=await cdp.send('Performance.getMetrics');row.heapBytes=metrics.metrics.find(m=>m.name==='JSHeapUsedSize')?.value;
  row.resources=await page.evaluate(()=>performance.getEntriesByType('resource').map(e=>({path:new URL(e.name).pathname,durationMs:e.duration,transferBytes:e.transferSize,decodedBytes:e.decodedBodySize})));
  row.passed=!row.errors.length&&!row.failedApi.length&&!row.overflow;
  if(sample===1)await page.screenshot({path:resolve(out,`${condition}-comparison.png`),fullPage:true});
  await context.close();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2));
 }
 report.passed=report.runs.every(r=>r.passed);if(!report.passed)process.exitCode=1;
}catch(error){report.passed=false;report.error=String(error);process.exitCode=1;}finally{await browser.close();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({passed:report.passed,runs:report.runs.map(({condition,sample,timingsMs,passed})=>({condition,sample,timingsMs,passed})),error:report.error}));
