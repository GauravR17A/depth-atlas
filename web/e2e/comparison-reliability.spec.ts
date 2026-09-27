import {test,expect} from '@playwright/test';
import {lessons} from '../src/learning/lessons';
import {enterWorkspace,openTool} from './ux-helpers';

test('a slow valid comparison finishes without a false timeout or manual Retry',async({page})=>{
 test.setTimeout(60000);
 await page.route('**/evidence/**',async route=>{
  const response=await route.fetch();
  await new Promise(resolve=>setTimeout(resolve,9500));
  await route.fulfill({response}).catch(()=>{});
 });
 await page.goto('/');await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();
 const coach=page.locator('.learning-coach'),index=lessons.findIndex(l=>l.id==='compare');
 await coach.locator('.learn-contents summary').click();await coach.getByRole('button',{name:`${index+1}. ${lessons[index].title}`,exact:true}).click();
 await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:40000});
 await expect(coach.locator('.learn-error')).toHaveCount(0);await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
});

test('leaving the model cancels unused speculative reads while comparison stays usable',async({page})=>{
 await page.addInitScript(()=>{
  Object.defineProperty(navigator,'connection',{value:{saveData:false,effectiveType:'4g'},configurable:true});
  const fetchOriginal=window.fetch;
  Object.assign(window,{speculativeReadCancelled:false});
  window.fetch=(input,init)=>{
   if(String(input).includes('/subset?')&&String(input).includes('time_index=1')&&String(input).includes('representation=display'))init?.signal?.addEventListener('abort',()=>Object.assign(window,{speculativeReadCancelled:true}),{once:true});
   return fetchOriginal(input,init);
  };
 });
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
 await page.route('**/subset?*',async route=>{if(route.request().url().includes('time_index=1'))await gate;await route.continue().catch(()=>{});});
 const started=page.waitForRequest(r=>r.url().includes('/subset?')&&r.url().includes('time_index=1'));
 await enterWorkspace(page);await started;
 try{
  await openTool(page,'Compare');
  await expect.poll(()=>page.evaluate(()=>(window as unknown as {speculativeReadCancelled:boolean}).speculativeReadCancelled),{timeout:4000}).toBe(true);
  await expect(page.getByLabel('Eligible comparison count')).toBeVisible();
 }finally{release();}
});

test('selecting a prefetched snapshot keeps that request and its exact source timestamp',async({page})=>{
 await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:false,effectiveType:'4g'},configurable:true}));
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
 const reads:string[]=[];
 await page.route('**/subset?*',async route=>{
  if(route.request().url().includes('time_index=1')&&route.request().url().includes('representation=display')){reads.push(route.request().url());await gate;}
  await route.continue().catch(()=>{});
 });
 const started=page.waitForRequest(r=>r.url().includes('/subset?')&&r.url().includes('time_index=1'));
 await enterWorkspace(page);await started;
 await page.getByLabel('Ocean timestamp').selectOption('1');release();
 await expect(page.locator('.ocean-viewport')).toHaveAttribute('data-shown-time','2024-01-07T12:00:00Z');
 await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
 expect(reads).toHaveLength(1);
});

test('core walkthrough reaches an exact comparison on normal browser transport',async({page,browserName},testInfo)=>{
 test.setTimeout(180000);
 const network:unknown[]=[];
 if(browserName==='chromium'){
  const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');
  cdp.on('Network.requestWillBeSent',e=>{if(e.request.url.includes('/api/'))network.push({event:'request',at:Date.now(),id:e.requestId,url:e.request.url,time:e.timestamp});});
  cdp.on('Network.responseReceived',e=>{if(e.response.url.includes('/api/'))network.push({event:'response',at:Date.now(),id:e.requestId,status:e.response.status,protocol:e.response.protocol,timing:e.response.timing,time:e.timestamp});});
  cdp.on('Network.loadingFailed',e=>network.push({event:'failed',at:Date.now(),...e}));
 }
 await page.addInitScript(()=>{
  const records:{start:number;duration:number}[]=[];
  Object.assign(window,{oceanLongTasks:records});
  if(PerformanceObserver.supportedEntryTypes.includes('longtask'))new PerformanceObserver(list=>{for(const e of list.getEntries())records.push({start:e.startTime,duration:e.duration});}).observe({type:'longtask',buffered:true});
 });
 try{
  await page.goto('/');await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();
  const coach=page.locator('.learning-coach');
  for(const lesson of lessons.slice(0,lessons.findIndex(l=>l.id==='compare')+1)){
   network.push({event:'lesson',id:lesson.id,at:Date.now()});
   await expect(coach.getByRole('heading',{level:2})).toHaveText(lesson.title);
   await expect(coach.getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});
   await expect(coach.getByLabel('Tutorial result')).toBeVisible();
   if(lesson.id==='compare')await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
   else await coach.getByRole('button',{name:'Next',exact:true}).click();
  }
  await page.screenshot({path:testInfo.outputPath('comparison-ready.png'),fullPage:true});
 }finally{
  const performanceData=await page.evaluate(()=>({origin:performance.timeOrigin,longTasks:(window as unknown as {oceanLongTasks:unknown[]}).oceanLongTasks})).catch(()=>null);
  await testInfo.attach('comparison-network-and-long-tasks',{body:JSON.stringify({network,performance:performanceData},null,2),contentType:'application/json'});
 }
});
