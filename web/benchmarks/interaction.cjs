const {chromium,webkit}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8000';
const prefix=process.env.OCEAN_BENCH_NAME||'motion-interaction';
(async()=>{
  const rows=[];
  for(const [name,engine] of [['chromium',chromium],['webkit',webkit]]){
    const browser=await engine.launch(),page=await browser.newPage({viewport:{width:1536,height:960}});
    await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));
    const requests=[];page.on('request',r=>{if(r.url().includes('/subset?'))requests.push(r.url());});
    await page.goto(base);await page.getByLabel('Native model value').filter({hasText:'22.303'}).waitFor();
    await page.getByLabel('Graphics quality').selectOption('balanced');await page.locator('.ocean-webgl[data-rendered=volume]').waitFor();
    requests.length=0;const actions=[];
    for(const [index,depth] of [['27','500'],['32','1,000'],['19','100']]){
      const start=Date.now();await page.getByLabel('Explorer depth').selectOption(index);
      await page.waitForFunction(d=>{const s=document.querySelector('.probe-value').textContent;return !s.includes('Loading')&&s.includes(`${d} m`);},depth);
      actions.push({depth,readyMs:Date.now()-start,text:await page.getByLabel('Native model value').textContent()});
    }
    const depths={requests:requests.length,actions};
    const scene=page.locator('.ocean-webgl');
    const before=await scene.evaluate(e=>({...e.dataset}));
    let cut=null;
    if(await page.getByRole('button',{name:'Cutaway',exact:true}).count()){
      const intervals=await page.evaluate(async()=>{
        const start=performance.now(),frames=[],progress=[];let previous=0;
        document.querySelector('[aria-label="Cutaway"]').click();
        await new Promise(resolve=>{function frame(t){if(previous)frames.push(t-previous);previous=t;progress.push(Number(document.querySelector('.ocean-webgl').dataset.cutProgress));if(t-start<1200)requestAnimationFrame(frame);else resolve();}requestAnimationFrame(frame);});
        return {frames,progress};
      });
      const measured=intervals.frames.sort((a,b)=>a-b);
      cut={intermediateFrames:intervals.progress.filter(x=>x>0&&x<1).length,medianMs:measured[Math.floor(measured.length/2)],p95Ms:measured[Math.floor(measured.length*.95)],final:await scene.evaluate(e=>({...e.dataset}))};
      await scene.screenshot({path:path.resolve(__dirname,`../../docs/evidence/${prefix}-${name}-cutaway.png`)});
    }
    rows.push({name,depths,before,cut});await browser.close();
  }
  const report={checkedUtc:new Date().toISOString(),base,method:'Windows headless, 1536x960, data-saving flag disables optional prefetch, Balanced 3D. UI latency includes automation overhead. Frame intervals include idle frames after the 460 ms transition, not sustained 3D FPS.',rows};
  fs.writeFileSync(path.resolve(__dirname,`../../docs/evidence/${prefix}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exit(1)});
