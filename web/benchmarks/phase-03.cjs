/* Run against a built, running API. These are observations, not device guarantees. */
const { chromium, webkit } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.OCEAN_TEST_URL || 'http://127.0.0.1:8000';
const prefix = process.env.OCEAN_BENCH_NAME || 'phase-03-local';
const evidence = path.resolve(__dirname, '../../docs/evidence');
const rows = [];
async function motion(page,duration=4000) {
  return page.evaluate(async duration => {
    const intervals = [], begin = performance.now(); let previous = 0;
    const timer = setInterval(() => document.querySelector('[aria-label="Rotate ocean right"]').click(), 50);
    await new Promise(resolve => {
      function frame(now) {
        if (previous) intervals.push(now - previous); previous = now;
        if (now - begin < duration) requestAnimationFrame(frame); else resolve();
      }
      requestAnimationFrame(frame);
    });
    clearInterval(timer);
    intervals.sort((a,b) => a-b);
    return { samples: intervals.length, medianFrameMs: intervals[Math.floor(intervals.length/2)], p95FrameMs: intervals[Math.floor(intervals.length*.95)], quality: document.querySelector('.ocean-render-status').textContent, diagnostics: {...document.querySelector('.ocean-webgl').dataset} };
  },duration);
}
(async () => {
  for (const [name,engine,viewport] of [['chromium',chromium,{width:1536,height:960}],['webkit',webkit,{width:1440,height:900}]]) {
    const browser=await engine.launch(),page=await browser.newPage({viewport});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const start=Date.now();await page.goto(base);
    await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();
    const firstVolumeMs=Date.now()-start;
    const gpu=await page.locator('.ocean-webgl canvas').evaluate(c=>{
      const gl=c.getContext('webgl2'),info=gl.getExtension('WEBGL_debug_renderer_info');
      return {vendor:info?gl.getParameter(info.UNMASKED_VENDOR_WEBGL):'unavailable',renderer:info?gl.getParameter(info.UNMASKED_RENDERER_WEBGL):'unavailable',max3DTextureSize:gl.getParameter(gl.MAX_3D_TEXTURE_SIZE)};
    });
    await page.getByLabel('Graphics quality').selectOption('balanced');await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();
    const balanced=await motion(page);
    await page.getByLabel('Graphics quality').selectOption('auto');await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();
    const auto=await motion(page,8000);
    await page.getByLabel('Graphics quality').selectOption('balanced');await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();
    await page.getByRole('button',{name:'Reset ocean camera',exact:true}).click();
    await page.waitForTimeout(300);
    await page.screenshot({path:path.join(evidence,`${prefix}-${name}-volume.png`)});
    for(const [mode,label] of [['section','Section'],['iso','Isosurface'],['currents','Current vectors']]){
      await page.getByRole('button',{name:label,exact:true}).click();
      await page.waitForFunction(m=>document.querySelector('.ocean-webgl').dataset.rendered===m||document.querySelector('.ocean-render-status').textContent==='Basic 2D',mode);
      await page.screenshot({path:path.join(evidence,`${prefix}-${name}-${mode}.png`)});
    }
    const resources=await page.evaluate(()=>performance.getEntriesByType('resource').filter(r=>/representation=display|scene-/.test(r.name)).map(r=>({url:r.name,durationMs:r.duration,encodedBytes:r.encodedBodySize,decodedBytes:r.decodedBodySize})));
    const overflow=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
    rows.push({name,viewport,firstVolumeMs,gpu,balanced,auto,resources,overflow,errors});await browser.close();
  }
  const browser=await chromium.launch();
  for(const [name,viewport,textZoom] of [['mobile',{width:390,height:844},1],['enlarged-text',{width:768,height:1024},2]]){
    const page=await browser.newPage({viewport,isMobile:name==='mobile',deviceScaleFactor:name==='mobile'?2:1,hasTouch:name==='mobile'});
    await page.goto(base);await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();
    if(textZoom===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
    await page.getByText('Colour, depth and display settings',{exact:true}).click();
    await page.screenshot({path:path.join(evidence,`${prefix}-${name}.png`),fullPage:true});
    const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
    rows.push({name,viewport,textZoom,layout});await page.close();
  }
  await browser.close();
  const result={checkedUtc:new Date().toISOString(),base,method:'Headless Playwright on Windows. Browser RAF intervals during repeated camera rotation, measured without concurrent browser suites. Includes browser scheduling, rendering and host load. Not a hardware-device or network guarantee.',rows};
  fs.writeFileSync(path.join(evidence,`${prefix}-performance.json`),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1);});
