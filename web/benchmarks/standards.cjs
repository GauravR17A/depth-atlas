const {chromium,webkit}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8003',prefix=process.env.OCEAN_BENCH_NAME||'p06-local';
const directory=path.resolve(__dirname,'../../docs/evidence');
(async()=>{
 const rows=[];
 for(const [name,engine,viewport,zoom] of [['desktop',chromium,{width:1536,height:1000},1],['webkit',webkit,{width:1440,height:900},1],['mobile',chromium,{width:390,height:844},1],['narrow',chromium,{width:320,height:740},1],['large-text',chromium,{width:768,height:1024},2]]){
  const browser=await engine.launch(),page=await browser.newPage({viewport}),errors=[],layouts=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByLabel('Variable',{exact:true}).selectOption('horizontal_kinetic_energy');
  await page.getByRole('heading',{name:'Horizontal kinetic energy beneath the surface'}).waitFor();
  await page.getByLabel('Native model value').filter({hasText:'m²/s²'}).waitFor();
  if(zoom===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
  async function capture(view){
   await page.screenshot({path:path.join(directory,`${prefix}-${name}-${view}.png`),fullPage:true});
   const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
   assert.ok(layout.scrollWidth<=layout.width,`${name} ${view} page overflow: ${layout.scrollWidth}/${layout.width}`);layouts.push({view,...layout});
  }
  await capture('derived-volume');
  await page.getByLabel('Graphics quality').selectOption('basic');await page.getByRole('button',{name:'Depth slice',exact:true}).click();
  await page.getByRole('img',{name:'Scientific depth slice'}).waitFor();await capture('derived-slice');
  await page.goto(base+'/data-access');
  if(zoom===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
  await capture('data-access');
  assert.equal(errors.length,0);rows.push({name,viewport,textZoom:zoom,layouts,errors});await browser.close();
 }
 const result={checkedUtc:new Date().toISOString(),base,method:'Sequential Windows headless Chromium/WebKit. Emulated mobile widths and 200% text, not physical-device certification.',rows};
 fs.writeFileSync(path.join(directory,`${prefix}-visual-review.json`),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1);});
