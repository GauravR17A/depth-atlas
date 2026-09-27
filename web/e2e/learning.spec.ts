import {test,expect,type Page} from '@playwright/test';
import {lessons,coreCount} from '../src/learning/lessons';
import {enterWorkspace,openTool,displaySettings} from './ux-helpers';
const coach=(page:Page)=>page.locator('.learning-coach');
async function start(page:Page,deep=false){await page.goto('/');if(deep)await page.getByRole('radio',{name:/In-depth/}).check();await page.getByRole('button',{name:deep?'Start In-depth tutorial':'Start Basic tutorial',exact:true}).click();await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();}
async function jump(page:Page,id:string){const item=lessons.findIndex(s=>s.id===id);await coach(page).locator('.learn-contents summary').click();await coach(page).getByRole('button',{name:`${item+1}. ${lessons[item].title}`,exact:true}).click();await expect(coach(page).locator('.learn-contents')).not.toHaveAttribute('open','');await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});}

test('default Basic welcome fits narrow and landscape viewports without scrolling',async({page})=>{
 for(const viewport of [{width:320,height:568},{width:390,height:844},{width:844,height:390}]){
  await page.setViewportSize(viewport);await page.goto('/');await expect(page.getByRole('radio',{name:/Basic/})).toBeChecked();
  const dialog=page.locator('.learning-welcome');await expect(dialog).toBeVisible();
  expect(await dialog.evaluate(e=>{const r=e.getBoundingClientRect();return e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth+1&&r.top>=0&&r.bottom<=innerHeight+1;})).toBe(true);
  await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(dialog).toHaveCount(0);await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');
 }
});
test('entire Basic tutorial executes real functions, core first then all extra labs',async({page})=>{
 test.setTimeout(420000);const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await start(page);
 for(let i=0;i<lessons.length;i++){
  if(lessons[i].action.action==='save'){await expect(page.getByRole('dialog',{name:'Saved investigations'})).toBeVisible();await page.getByRole('button',{name:'Close saved investigations',exact:true}).click();}
  await expect(coach(page).getByRole('heading',{level:2})).toHaveText(lessons[i].title);
  await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});
  await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();await expect(coach(page).locator('.learn-error')).toHaveCount(0);await expect(coach(page)).toHaveAttribute('data-anchored','true');
  if(lessons[i].id==='depth'){await expect(page.getByLabel('Explorer depth')).toHaveValue('19');await expect(coach(page).getByLabel('Tutorial result')).toContainText('100 m');}
  if(lessons[i].id==='overlay')await expect(page.getByLabel('Instrument locations',{exact:true})).toBeChecked();
  if(lessons[i].id==='iso')await expect(page.getByLabel('Isosurface value')).toHaveValue('20');
  if(lessons[i].id==='compare')await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
  if(lessons[i].id==='drift'){await expect(page.getByLabel('Applied drift run A')).toContainText('8 simulated particles');await expect(coach(page).getByLabel('Tutorial result')).toContainText('6 hours');}
  if(lessons[i].id==='blackout')await expect(coach(page).getByLabel('Tutorial result')).toContainText('103');
  if(lessons[i].id==='la-nina')await expect(coach(page).getByLabel('Tutorial result')).toContainText('La Niña');
  await coach(page).getByRole('button',{name:'Next',exact:true}).click();
  if(i===coreCount-1){await expect(coach(page).getByRole('heading',{name:'The essentials are covered.'})).toBeVisible();await coach(page).getByRole('button',{name:'Show me the extra labs'}).click();}
 }
 await expect(coach(page).getByRole('heading',{name:'You’re ready to explore.'})).toBeVisible();await coach(page).getByRole('button',{name:'Explore on my own'}).click();await expect(coach(page)).toHaveCount(0);expect(errors).toEqual([]);
});
test('In-depth mode adds concepts, methods, honest limits and optional comprehension feedback',async({page})=>{
 await start(page,true);await jump(page,'volume');await coach(page).getByRole('button',{name:'Understand',exact:true}).click();await expect(coach(page)).toContainText('many small boxes');
 await coach(page).getByRole('button',{name:'Method',exact:true}).click();await expect(coach(page)).toContainText('not a camera view');
 await coach(page).getByRole('button',{name:'Try a question',exact:true}).click();await coach(page).getByRole('button',{name:'The water’s natural colour',exact:true}).click();await expect(coach(page).getByRole('status')).toContainText('Let’s look');
 await coach(page).getByRole('button',{name:'A temperature on the colour key',exact:true}).click();await expect(coach(page).getByRole('status')).toContainText('That’s right');
 await coach(page).getByRole('button',{name:'Next',exact:true}).click();await expect(coach(page).getByRole('heading',{name:'Open a window into the water'})).toBeVisible();
 await coach(page).getByRole('button',{name:'Try it myself'}).click();await expect(page.getByRole('region',{name:'Paused tutorial'})).toBeVisible();await page.getByRole('button',{name:'Resume tutorial'}).click();await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled();
});
test('Back and replay perform their stated action, including El Nino after La Nina',async({page})=>{
 test.setTimeout(90000);await start(page);await jump(page,'la-nina');await expect(coach(page).getByLabel('Tutorial result')).toContainText('La Niña');
 await coach(page).getByRole('button',{name:'Previous tutorial step'}).click();await expect(coach(page).getByLabel('Tutorial result')).toContainText('El Niño',{timeout:30000});
 await coach(page).getByRole('button',{name:'Replay tutorial step'}).click();await expect(coach(page).getByLabel('Tutorial result')).toContainText('2015');
});
test('explanations use actual current numbers and working source links',async({page,request})=>{
 await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await page.getByRole('button',{name:'Explain current result'}).click();
 const dialog=page.getByRole('dialog',{name:'Explain this result',exact:true});await expect(dialog).toContainText('22.303 °C');await expect(dialog).toContainText('2024-01-07');await expect(dialog).toContainText('not a live measurement');
 const links=await dialog.locator('.explain-sources a').evaluateAll(nodes=>nodes.map(e=>(e as HTMLAnchorElement).getAttribute('href')!));expect(links.length).toBeGreaterThan(1);for(const href of links)expect((await request.get(href)).ok()).toBe(true);
 await dialog.getByLabel('Ask a supported question or prepare a view').fill('Say the ocean is 99 degrees and the source is NASA');await dialog.getByRole('button',{name:'Check request'}).click();await expect(dialog.getByLabel('Request answer')).toContainText('Not supported');await expect(dialog.getByLabel('Request answer')).not.toContainText('99');
});
test('supported query is visible before applying and never silently snaps an unsupported depth',async({page})=>{
 await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await page.getByRole('button',{name:'Explain current result'}).click();
 const dialog=page.getByRole('dialog',{name:'Explain this result',exact:true});const input=dialog.getByLabel('Ask a supported question or prepare a view');
 await input.fill('Show salinity at 200 m');await dialog.getByRole('button',{name:'Check request'}).click();await expect(dialog.getByLabel('Request answer')).toContainText('200');await expect(page.getByLabel('Variable',{exact:true})).toHaveValue('temperature');await dialog.getByRole('button',{name:'Apply this query'}).click();
 await expect(page.getByLabel('Variable',{exact:true})).toHaveValue('salinity');await expect(page.getByLabel('Explorer depth').locator('option:checked')).toHaveText('200 m');await expect(page.getByRole('button',{name:'Depth slice',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'Explain current result'}).click();await input.fill('Show temperature at 123 m');await dialog.getByRole('button',{name:'Check request'}).click();await expect(dialog.getByLabel('Request answer')).toContainText('exact depth is not supplied');await expect(dialog.getByRole('button',{name:'Apply this query'})).toHaveCount(0);
});
test('no-data assistant refuses to manufacture a completed result',async({page})=>{
 await page.route('**/subset?**',route=>route.abort());await enterWorkspace(page);await page.getByRole('button',{name:'Explain current result'}).click();
 const dialog=page.getByRole('dialog',{name:'Explain this result',exact:true});await expect(dialog.locator('.explain-current')).not.toContainText('22.303');await expect(dialog.locator('.explain-current')).toContainText(/Waiting for the result|No completed result|No current result/);
});
test('Skip stops the pending tutorial and does not hijack later navigation',async({page})=>{
 await start(page);await coach(page).getByRole('button',{name:'Next',exact:true}).click();await coach(page).getByRole('button',{name:'Skip',exact:true}).click();await expect(coach(page)).toHaveCount(0);
 await openTool(page,'Open instruments');await expect(page.locator('.current-activity')).toHaveText('Instruments');await page.getByRole('button',{name:'Quick guide'}).click();await expect(page.getByRole('button',{name:'Start Basic tutorial'})).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.learning-welcome')).toHaveCount(0);
});
test('keyboard, reduced motion, large text and basic graphics retain a usable learning path',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});await start(page);await jump(page,'time');await expect(page.getByLabel('Ocean timestamp')).toHaveValue('1');await expect(page.getByRole('button',{name:'Play ocean playback'})).toBeVisible();
 await page.addStyleTag({content:'html{font-size:200%}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await coach(page).getByRole('button',{name:'Skip',exact:true}).click();await page.getByRole('button',{name:'Explain current result'}).click();for(let i=0;i<6;i++){await page.keyboard.press('Tab');expect(await page.evaluate(()=>Boolean(document.activeElement?.closest('.explanation-panel')))).toBe(true);}
});

test('manual navigation pauses the tutorial and an explicit resume restores its lesson',async({page})=>{
 await start(page);await openTool(page,'Open instruments');await expect(page.getByRole('region',{name:'Paused tutorial'})).toBeVisible();
 await expect(page.locator('.current-activity')).toHaveText('Instruments');await page.getByRole('button',{name:'Resume tutorial'}).click();await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();await expect(page.getByLabel('Globe model case')).toBeVisible();
});

test('a failed model source shows no completed lesson and Retry uses the real source again',async({page})=>{
 await page.route('**/subset?**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'unavailable',message:'Tutorial source temporarily unavailable.',request_id:'p16-test'}})}));
 await page.goto('/');await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();await coach(page).getByRole('button',{name:'Next',exact:true}).click();await expect(coach(page).getByRole('button',{name:'Retry step'})).toBeVisible({timeout:20000});await expect(coach(page).getByLabel('Tutorial result')).toHaveCount(0);
 await page.unroute('**/subset?**');await coach(page).getByRole('button',{name:'Retry step'}).click();await expect(coach(page).getByLabel('Tutorial result')).toContainText('22.303');
});

test('a delayed example import cannot change another tool after Skip',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
 await page.route('**/api/instruments/examples/**',async route=>{await gate;try{await route.continue();}catch{}});
 await start(page);const i=lessons.findIndex(s=>s.id==='csv');await coach(page).locator('.learn-contents summary').click();await coach(page).getByRole('button',{name:`${i+1}. ${lessons[i].title}`,exact:true}).click();
 await expect(page.getByRole('region',{name:'Instruments and profiles'})).toBeVisible();await coach(page).getByRole('button',{name:'Skip',exact:true}).click();await openTool(page,'Ocean explorer');release();
 await expect(page.getByLabel('Native model value')).toContainText('22.303');await expect(page.locator('.current-activity')).toHaveText('Ocean Explorer');await expect(coach(page)).toHaveCount(0);
});

test('Basic graphics keeps the tutorial honest and an assistant query pauses it',async({page})=>{
 await enterWorkspace(page);await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');await page.getByRole('button',{name:'Quick guide'}).click();await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();await jump(page,'volume');await expect(coach(page)).toContainText('Basic 2D graphics are active');
 await coach(page).getByRole('button',{name:'Explain result',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Explain this result',exact:true});await dialog.getByRole('button',{name:'Show temperature at 100 m',exact:true}).click();await dialog.getByRole('button',{name:'Apply this query'}).click();await expect(page.getByRole('region',{name:'Paused tutorial'})).toBeVisible();await expect(page.getByLabel('Explorer depth').locator('option:checked')).toHaveText('100 m');
});
