const {chromium,webkit}=require('playwright');
const path=require('node:path'),fs=require('node:fs');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8004';
const prefix=process.env.OCEAN_BENCH_NAME||'p07-local-detail';
const out=path.resolve(__dirname,'../../docs/evidence');
(async()=>{
 const rows=[];
 for(const[name,engine,width,height,scale]of[['webkit',webkit,1440,900,1],['mobile',chromium,390,844,1],['narrow',chromium,320,740,1],['large-text',chromium,768,1024,2]]){
  const browser=await engine.launch(),page=await browser.newPage({viewport:{width,height}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByRole('button',{name:'Find structures',exact:true}).click();
  await page.locator('.feature-mesh-canvas[data-rendered="region"] canvas').waitFor({timeout:40000});
  if(scale===2)await page.addStyleTag({content:'html{font-size:200% !important}'});
  const files=[];
  for(const[part,selector]of[['query','.feature-query'],['map','.feature-map-panel'],['inspector','.feature-inspector']]){
   const element=page.locator(selector);await element.scrollIntoViewIfNeeded();await page.waitForTimeout(500);
   const file=`${prefix}-${name}-${part}.png`;await element.screenshot({path:path.join(out,file)});files.push(file);
  }
  await page.getByRole('button',{name:'Build section',exact:true}).click();
  await page.getByLabel('Section source value',{exact:true}).waitFor({timeout:40000});
  await page.getByLabel('Section native depth',{exact:true}).selectOption('13');
  const section=page.locator('.feature-section-view');await section.scrollIntoViewIfNeeded();await page.waitForTimeout(300);
  const file=`${prefix}-${name}-section.png`;await section.screenshot({path:path.join(out,file)});files.push(file);
  const scroller=section.locator('svg').locator('..');
  const overflow=await scroller.evaluate(el=>el.scrollWidth>el.clientWidth);
  if(overflow){await scroller.evaluate(el=>{el.scrollLeft=el.scrollWidth});const endFile=`${prefix}-${name}-section-end.png`;await section.screenshot({path:path.join(out,endFile)});files.push(endFile);}
  const dimensions=await page.evaluate(()=>({width:innerWidth,pageWidth:document.documentElement.scrollWidth}));
  rows.push({name,width,height,textScale:scale,files,errors,...dimensions});await browser.close();
 }
 fs.writeFileSync(path.join(out,`${prefix}.json`),JSON.stringify({base,checkedUtc:new Date().toISOString(),rows},null,2)+'\n');
 console.log(JSON.stringify(rows.map(r=>({name:r.name,width:r.width,pageWidth:r.pageWidth,errors:r.errors}))));
})().catch(e=>{console.error(e);process.exit(1)});
