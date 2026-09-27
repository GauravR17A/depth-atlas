const {chromium,webkit}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8002',prefix=process.env.OCEAN_BENCH_NAME||'p05-local';
const directory=path.resolve(__dirname,'../../docs/evidence');
(async()=>{
 const rows=[];
 for(const [name,engine,viewport,zoom] of [['desktop',chromium,{width:1536,height:1000},1],['webkit',webkit,{width:1440,height:900},1],['mobile',chromium,{width:390,height:844},1],['narrow',chromium,{width:320,height:740},1],['large-text',chromium,{width:768,height:1024},2]]){
  const browser=await engine.launch(),page=await browser.newPage({viewport}),errors=[],layouts=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByRole('button',{name:'Compare',exact:true}).click();
  await page.getByLabel('Comparison model snapshot').selectOption('1');
  await page.getByLabel('Eligible comparison count').filter({hasText:'103 / 103'}).waitFor();
  if(zoom===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
  const footnote=await page.locator('.comparison-footnote').boundingBox();
  const workspace=await page.locator('.evidence-workspace').boundingBox();
  assert.ok(footnote.width>=workspace.width-2,`${name} footnote must use workspace width`);
  await page.getByRole('link',{name:'Go to results',exact:true}).click();
  assert.ok(await page.locator('#comparison-results').evaluate(e=>e.getBoundingClientRect().top<150),'Results link should bring results into view');
  await page.evaluate(()=>scrollTo(0,0));
  async function capture(view){
   await page.screenshot({path:path.join(directory,`${prefix}-${name}-${view}.png`),fullPage:true});
   const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,chart:[...document.querySelectorAll('.evidence-chart svg')].map(e=>e.getBoundingClientRect().toJSON())}));
   assert.ok(layout.scrollWidth<=layout.width,`${name} ${view} page overflow`);layouts.push({view,...layout});
  }
  await capture('comparison');
  await page.getByRole('button',{name:'Evidence coverage',exact:true}).click();await page.locator('.evidence-section-heading').filter({hasText:'206 pairs'}).waitFor();await capture('coverage');
  await page.getByRole('button',{name:'Matching rules',exact:true}).click();await capture('rules');
  assert.equal(errors.length,0);rows.push({name,viewport,textZoom:zoom,layouts,errors});await browser.close();
 }
 const result={checkedUtc:new Date().toISOString(),base,method:'Sequential Windows headless Chromium/WebKit screenshot and page-overflow checks. Mobile widths and 200% root text are emulated, not physical-device certification.',rows};
 fs.writeFileSync(path.join(directory,`${prefix}-visual-review.json`),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1);});
