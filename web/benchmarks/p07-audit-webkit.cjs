const {webkit}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await webkit.launch(),page=await browser.newPage({viewport:{width:1440,height:900}}),events=[];
 page.on('console',m=>events.push({kind:m.type(),text:m.text()}));page.on('pageerror',e=>events.push({kind:'pageerror',text:e.message}));
 await page.goto(process.env.OCEAN_TEST_URL||'http://127.0.0.1:8003');
 await page.getByLabel('Native model value').filter({hasText:'22.303'}).waitFor();
 await page.locator('.ocean-webgl[data-rendered="volume"]').waitFor();
 const rows=[];
 for(const mode of ['initial','rotate','slice','cutaway','basic']){
  if(mode==='rotate')await page.getByLabel('Rotate ocean right',{exact:true}).click();
  if(mode==='slice')await page.getByRole('button',{name:'Depth slice',exact:true}).click();
  if(mode==='cutaway'){await page.getByRole('button',{name:'Volume',exact:true}).click();await page.getByRole('button',{name:'Cutaway',exact:true}).click();}
  if(mode==='basic')await page.getByLabel('Graphics quality').selectOption('basic');
  await page.waitForTimeout(1500);
  const file=`p07-audit-webkit-${mode}.png`;
  await page.locator('.ocean-viewport').screenshot({path:path.resolve(__dirname,'../../docs/evidence',file)});
  const info=await page.locator('.ocean-webgl').evaluate(e=>({attributes:{...e.dataset},children:[...e.children].map(c=>({tag:c.tagName,width:c.width,height:c.height,style:getComputedStyle(c).cssText}))}));rows.push({mode,file,info});
 }
 fs.writeFileSync(path.resolve(__dirname,'../../docs/evidence/p07-audit-webkit.json'),JSON.stringify({rows,events},null,2));
 await browser.close();console.log(JSON.stringify({rows:rows.map(r=>({mode:r.mode,attributes:r.info.attributes})),events}));
})().catch(e=>{console.error(e);process.exit(1);});
