const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8004';
const prefix=process.env.OCEAN_BENCH_NAME||'p07-local';
const out=path.resolve(__dirname,'../../docs/evidence');
const configurations=[['desktop',chromium,1536,1000,1],['webkit',webkit,1440,900,1],['mobile',chromium,390,844,1],['narrow',chromium,320,740,1],['large-text',chromium,768,1024,2]].filter(c=>!process.env.OCEAN_AUDIT_CONFIG||c[0]===process.env.OCEAN_AUDIT_CONFIG);
const result={base,checkedUtc:new Date().toISOString(),method:'Sequential headless Windows Chromium and WebKit with pointer and keyboard interactions, downloaded result inspection, source API cross-checks and actual screenshot review. Narrow widths are emulated, not physical-device or unfamiliar-user certification.',rows:[]};
const save=()=>fs.writeFileSync(path.join(out,`${prefix}-features-visual.json`),JSON.stringify(result,null,2)+'\n');
(async()=>{
 for(const [name,engine,width,height,textScale]of configurations){
  const browser=await engine.launch(),page=await browser.newPage({viewport:{width,height},acceptDownloads:true}),errors=[],row={name,width,height,textScale,checks:[],screenshots:[],errors};result.rows.push(row);
  page.on('pageerror',e=>errors.push(e.message));
  const check=async(label,work)=>{try{const details=await work();row.checks.push({label,passed:true,details});}catch(e){row.checks.push({label,passed:false,error:e.message});}save();};
  const shot=async(view)=>{await page.waitForTimeout(300);const file=`${prefix}-features-${name}-${view}.png`;await page.screenshot({path:path.join(out,file),fullPage:true});row.screenshots.push(file);const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));assert.ok(layout.scrollWidth<=layout.width,`Horizontal overflow: ${layout.scrollWidth}/${layout.width}`);return layout;};
  try{
   await check('initial structured result and actual 3D boundary',async()=>{
    await page.goto(base);await page.getByRole('button',{name:'Find structures',exact:true}).click();
    await page.getByLabel('Structure search results',{exact:true}).waitFor({timeout:40000});
    await page.getByRole('button',{name:'Select region 1',exact:false}).waitFor();
    const canvas=page.locator('.feature-mesh-canvas[data-rendered="region"] canvas');await canvas.waitFor();
    if(textScale===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
    await page.waitForTimeout(1500); // allow GPU composition and the introductory transition to settle
    assert.ok((await page.locator('.feature-method-strip').innerText()).includes('not automatically identified eddies'));
    assert.ok((await page.getByLabel('Selected structure inspector').innerText()).includes('Estimated volume'));
    return shot('initial');
   });
   await check('changed query is explicit and updates source time',async()=>{
    const previous=await page.locator('.feature-result-header').innerText();
    await page.getByLabel('Structure threshold',{exact:true}).fill('27');
    await page.getByLabel('Structure model snapshot',{exact:true}).selectOption('1');
    assert.equal(await page.locator('.feature-result-header').innerText(),previous);
    assert.ok((await page.locator('.feature-notice').innerText()).includes('controls have changed'));
    const response=page.waitForResponse(r=>r.url().endsWith('/features/search')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Find regions',exact:true}).click();const body=await(await response).json();
    await page.getByRole('button',{name:'Find regions',exact:true}).waitFor();
    await page.waitForFunction(()=>document.querySelector('.feature-result-header')?.textContent.includes('12:00'));
    assert.equal(body.query.threshold,27);assert.equal(body.query.time_index,1);
    row.query=body.query;row.regionCount=body.total_regions;
    return {modelTime:body.model_time,regions:body.total_regions};
   });
   await check('draw two map positions using true SVG screen coordinates',async()=>{
    await page.getByRole('button',{name:'Draw a section',exact:true}).click();
    const map=page.getByRole('img',{name:'Plan view of qualifying regions and section line',exact:true});await map.scrollIntoViewIfNeeded();
    async function point(x,y){
     // A narrow viewport keeps chart labels readable through a bounded scroller.
     // Bring the requested scientific position into that viewport before clicking.
     await map.evaluate((el,p)=>{const value=new DOMPoint(p[0],p[1]).matrixTransform(el.getScreenCTM());let scroller=el.parentElement;while(scroller&&!(scroller.scrollWidth>scroller.clientWidth&&['auto','scroll'].includes(getComputedStyle(scroller).overflowX)))scroller=scroller.parentElement;if(scroller){const box=scroller.getBoundingClientRect(),margin=24;if(value.x<box.left+margin)scroller.scrollLeft+=value.x-box.left-margin;else if(value.x>box.right-margin)scroller.scrollLeft+=value.x-box.right+margin;}},[x,y]);
     const screen=await map.evaluate((el,p)=>{const value=new DOMPoint(p[0],p[1]).matrixTransform(el.getScreenCTM());return{x:value.x,y:value.y};},[x,y]);await page.mouse.click(screen.x,screen.y);
    }
    await point(64+554*.2,22+310*.25);
    const request=page.waitForRequest(r=>r.url().endsWith('/features/section')&&r.method()==='POST');await point(64+554*.8,22+310*.75);
    const payload=(await request).postDataJSON();await page.getByLabel('Section source value',{exact:true}).waitFor({timeout:40000});
    assert.ok(payload.start[0]<payload.end[0]);assert.ok(payload.start[1]>payload.end[1]);assert.equal(payload.stations,81);
    row.drawnLine=payload;await shot('drawn-section');return payload;
   });
   await check('keyboard coordinate entry and source-value picking',async()=>{
    await page.getByLabel('Section start longitude',{exact:true}).fill('86');await page.getByLabel('Section start latitude',{exact:true}).fill('13.2');
    await page.getByLabel('Section end longitude',{exact:true}).fill('89');await page.getByLabel('Section end latitude',{exact:true}).fill('14.2');
    const response=page.waitForResponse(r=>r.url().endsWith('/features/section')&&r.request().method()==='POST');
    const build=page.getByRole('button',{name:'Build section',exact:true});await build.focus();await build.press('Enter');
    const section=await(await response).json();assert.deepEqual(section.start,[86,13.2]);assert.deepEqual(section.end,[89,14.2]);
    // A response event precedes React's commit. Verify the new line's first
    // source column is displayed before operating its remounted sample controls.
    const first=section.stations[0];await page.getByLabel('Section source value',{exact:true}).filter({hasText:first.model_latitude.toLocaleString('en-US',{maximumFractionDigits:6})}).waitFor();
    await page.getByLabel('Section station',{exact:true}).selectOption('40');await page.getByLabel('Section native depth',{exact:true}).selectOption(String(section.depth_m.indexOf(100)));
    await page.getByLabel('Section source value',{exact:true}).filter({hasText:'100 m'}).waitFor();
    const cell=section.stations[40],manifest=await(await page.request.get(base+'/api/cases/bay-bengal-2024-01')).json();
    const params=new URLSearchParams({variable:section.query.variable,time_index:String(section.query.time_index),operation:'depth_slice',depth_index:String(manifest.coordinates.depth_m.indexOf(100)),representation:'analytical',west:String(cell.model_longitude),east:String(cell.model_longitude),south:String(cell.model_latitude),north:String(cell.model_latitude)});
    const native=await(await page.request.get(base+'/api/cases/bay-bengal-2024-01/subset?'+params)).json();
    const value=section.values[section.depth_m.indexOf(100)*section.shape[1]+40];assert.equal(value,native.values[0]);
    if(value!==null)await page.getByLabel('Section source value',{exact:true}).filter({hasText:value.toLocaleString('en-US',{maximumFractionDigits:6})}).waitFor({timeout:10000});
    await page.getByLabel('Show eligible observations',{exact:true}).uncheck();await page.getByLabel('Show eligible observations',{exact:true}).check();
    row.keyboardSection={start:section.start,end:section.end,nativeValue:value,sourceLongitude:cell.model_longitude,sourceLatitude:cell.model_latitude};
    return shot('keyboard-section');
   });
   await check('download agrees with the visible selection and source identity',async()=>{
    const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export query results',exact:true}).click();const artifact=await download;
    const file=`${prefix}-features-${name}-export.json`;await artifact.saveAs(path.join(out,file));const data=JSON.parse(fs.readFileSync(path.join(out,file),'utf8'));
    assert.equal(data.result.query.threshold,27);assert.equal(data.result.query.time_index,1);assert.deepEqual(data.section.start,[86,13.2]);assert.match(data.result.manifest_sha256,/^[a-f0-9]{64}$/);
    assert.equal(data.section.values[data.section.depth_m.indexOf(100)*81+40],row.keyboardSection.nativeValue);
    return {file,version:data.app_version,modelTime:data.result.model_time,manifestSha256:data.result.manifest_sha256};
   });
   await check('keyboard region selection and graphics alternative',async()=>{
    const choose=page.getByRole('button',{name:'Select region 1',exact:false});await choose.focus();await choose.press('Enter');assert.equal(await choose.getAttribute('aria-pressed'),'true');
    await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');assert.equal(await page.locator('.feature-mesh-canvas canvas').count(),0);
    await page.getByText('Methods, source identity and limitations',{exact:true}).click();assert.ok((await page.locator('.feature-methods').innerText()).includes('Manifest SHA-256'));
    return shot('methods-basic');
   });
   await check('empty result explains the supported inference',async()=>{
    await page.getByLabel('Structure threshold',{exact:true}).fill('99');await page.getByRole('button',{name:'Find regions',exact:true}).click();
    await page.getByRole('heading',{name:'No regions meet this condition',exact:true}).waitFor({timeout:40000});
    assert.ok((await page.locator('.feature-empty').innerText()).includes('does not prove'));
    return shot('empty');
   });
  }finally{await browser.close();row.passed=row.checks.every(c=>c.passed)&&errors.length===0;save();}
 }
 result.passed=result.rows.every(r=>r.passed);save();console.log(JSON.stringify({base,passed:result.passed,configurations:result.rows.length,checks:result.rows.reduce((n,r)=>n+r.checks.length,0),failures:result.rows.flatMap(r=>r.checks.filter(c=>!c.passed).map(c=>({configuration:r.name,...c}))),errors:result.rows.flatMap(r=>r.errors)}));if(!result.passed)process.exitCode=1;
})().catch(e=>{console.error(e);save();process.exit(1);});
