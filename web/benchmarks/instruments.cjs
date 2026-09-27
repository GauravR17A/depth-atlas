const {chromium,webkit}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:8001';
const prefix=process.env.OCEAN_BENCH_NAME||'p04-local';
const directory=path.resolve(__dirname,'../../docs/evidence');
const catalog=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../casepacks/instruments/index.json'),'utf8'));
(async()=>{
  const rows=[];
  for(const [name,engine,viewport,zoom] of [
    ['desktop',chromium,{width:1536,height:1000},1],
    ['webkit',webkit,{width:1440,height:900},1],
    ['mobile',chromium,{width:390,height:844},1],
    ['narrow',chromium,{width:320,height:740},1],
    ['large-text',chromium,{width:768,height:1024},2],
  ]){
    const browser=await engine.launch(),page=await browser.newPage({viewport});const errors=[],layouts=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&/THREE|shader|React/i.test(m.text()))errors.push(m.text());});
    await page.goto(base);await page.getByLabel('Native model value').filter({hasText:'22.303'}).waitFor();
    if(zoom===2)await page.addStyleTag({content:'html {font-size:200% !important;}'});
    async function capture(view){
      await page.screenshot({path:path.join(directory,`${prefix}-${name}-${view}.png`),fullPage:true});
      const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,chart:document.querySelector('.profile-chart')?.getBoundingClientRect().toJSON()}));
      assert.ok(layout.scrollWidth<=layout.width,`${name} ${view} overflow`);layouts.push({view,...layout});
    }
    if(name==='desktop')await capture('ocean');
    await page.getByRole('button',{name:'Open instruments',exact:true}).click();await page.getByLabel('Observed sample value').waitFor();await capture('argo');
    if(name==='desktop'||name==='webkit'){
      const bgc=catalog.profiles.find(p=>p.instrument==='bgc');
      await page.getByLabel('Observation collection').selectOption(bgc.collection);await page.getByLabel('Profile variable').filter({has:page.locator('option[value=oxygen]')}).waitFor();
      const raw=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../casepacks/instruments',bgc.id+'.json'),'utf8'));
      await page.getByLabel('Observation sample',{exact:true}).selectOption(String(raw.levels.findIndex(l=>l.readings.oxygen.accepted)));await capture('bgc');
      const glider=catalog.profiles.filter(p=>p.instrument==='glider')[2];
      await page.getByLabel('Observation collection').selectOption(glider.collection);await page.getByLabel('Instrument profile').selectOption(glider.id);
      await page.getByLabel('Observed sample value').filter({hasText:'QARTOD'}).waitFor();await page.getByRole('button',{name:'Track detail',exact:true}).click();await capture('glider');
      await page.getByLabel('Profile variable').selectOption('salinity');await page.getByLabel('Show excluded values').check();await capture('excluded');
      await page.getByLabel('Observation collection').selectOption(catalog.profiles.find(p=>p.instrument==='ctd').collection);await page.getByLabel('Observed sample value').filter({hasText:'WOCE'}).waitFor();
      await page.getByLabel('Profile variable').selectOption('oxygen');await capture('ctd-missing');
    }
    await page.getByRole('button',{name:'Import observations',exact:true}).click();await page.getByText('Formats and genuine example files',{exact:true}).click();await capture('import');
    assert.equal(errors.length,0);rows.push({name,viewport,textZoom:zoom,layouts,errors});await browser.close();
  }
  const result={checkedUtc:new Date().toISOString(),base,method:'Windows headless Chromium and WebKit screenshots and layout checks. Mobile widths and 200% root text are emulation, not physical-device certification.',rows};
  fs.writeFileSync(path.join(directory,`${prefix}-visual-review.json`),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1);});
