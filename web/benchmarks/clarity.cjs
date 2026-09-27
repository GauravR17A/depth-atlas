const {chromium,webkit}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8000';
const prefix=process.env.OCEAN_BENCH_NAME||'clarity-local';
const directory=path.resolve(__dirname,'../../docs/evidence');
const rows=[];
(async()=>{
  for(const [name,engine,viewport,zoom] of [
    ['desktop',chromium,{width:1536,height:960},1],
    ['webkit',webkit,{width:1440,height:900},1],
    ['mobile',chromium,{width:390,height:844},1],
    ['narrow',chromium,{width:320,height:740},1],
    ['large-text',chromium,{width:768,height:1024},2],
  ]){
    const browser=await engine.launch(),page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const started=Date.now();await page.goto(base);await page.locator('.ocean-webgl[data-rendered=volume]').waitFor();
    const readyMs=Date.now()-started;
    if(zoom===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
    await page.waitForTimeout(250);await page.screenshot({path:path.join(directory,`${prefix}-${name}.png`),fullPage:true});
    const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,canvas:document.querySelector('.ocean-viewport').getBoundingClientRect().toJSON(),legend:document.querySelector('.ocean-legend').getBoundingClientRect().toJSON(),value:document.querySelector('.probe-value').getBoundingClientRect().toJSON()}));
    const frames=[];
    if(name==='desktop'||name==='webkit'){
      await page.getByLabel('Graphics quality').selectOption('balanced');
      for(const [mode,label] of [['slice','Depth slice'],['section','Section'],['iso','Isosurface'],['currents','Current vectors']]){
        await page.getByRole('button',{name:label,exact:true}).click();await page.locator(`.ocean-webgl[data-rendered=${mode}]`).waitFor();await page.waitForTimeout(150);
        await page.locator('.ocean-stage').screenshot({path:path.join(directory,`${prefix}-${name}-${mode}.png`)});
      }
      await page.getByLabel('Variable',{exact:true}).selectOption('temperature');await page.getByRole('button',{name:'Volume',exact:true}).click();
      await page.getByLabel('Depth window').selectOption('5000');await page.waitForTimeout(250);await page.locator('.ocean-stage').screenshot({path:path.join(directory,`${prefix}-${name}-full.png`)});
      await page.getByLabel('Volume style').selectOption('whole');await page.waitForTimeout(200);await page.locator('.ocean-stage').screenshot({path:path.join(directory,`${prefix}-${name}-whole.png`)});
      await page.getByLabel('Graphics quality').selectOption('basic');await page.getByRole('img',{name:'Scientific depth section'}).waitFor();await page.locator('.ocean-stage').screenshot({path:path.join(directory,`${prefix}-${name}-basic.png`)});
      await page.getByRole('button',{name:'Reset exploration',exact:true}).click();await page.getByLabel('Graphics quality').selectOption('auto');await page.locator('.ocean-webgl[data-rendered=volume]').waitFor();
      const observation=await page.evaluate(async()=>{
        let previous=0;const intervals=[],began=performance.now();
        const timer=setInterval(()=>document.querySelector('[aria-label="Rotate ocean right"]').click(),50);
        await new Promise(resolve=>{function frame(t){if(previous)intervals.push(t-previous);previous=t;if(t-began<8000)requestAnimationFrame(frame);else resolve();}requestAnimationFrame(frame);});clearInterval(timer);
        intervals.sort((a,b)=>a-b);return {samples:intervals.length,medianMs:intervals[Math.floor(intervals.length/2)],p95Ms:intervals[Math.floor(intervals.length*.95)],finalMode:document.querySelector('.ocean-render-status').textContent,diagnostics:{...document.querySelector('.ocean-webgl').dataset}};
      });frames.push(observation);
    }
    rows.push({name,viewport,textZoom:zoom,readyMs,layout,frames,errors});await browser.close();
  }
  const result={checkedUtc:new Date().toISOString(),base,method:'Windows headless browser visual review and RAF intervals during repeated rotation. Auto may transition to Basic during timing; the median is not a claim of sustained 3D FPS. Mobile sizes are emulation, not physical-device coverage.',rows};
  fs.writeFileSync(path.join(directory,`${prefix}-review.json`),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1);});
