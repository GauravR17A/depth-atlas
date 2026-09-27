const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.OCEAN_TEST_URL||'http://127.0.0.1:5174';
const prefix=process.env.OCEAN_BENCH_NAME||'p07-audit-vectors-fixed';
const out=path.resolve(__dirname,'../../docs/evidence');
(async()=>{
 const rows=[];
 for(const viewport of [{width:1536,height:960},{width:390,height:844}]){
  const browser=await chromium.launch(),page=await browser.newPage({viewport});
  await page.addInitScript(()=>{
   const p=CanvasRenderingContext2D.prototype,begin=p.beginPath,move=p.moveTo,line=p.lineTo,stroke=p.stroke,clear=p.clearRect;
   p.beginPath=function(){this.auditPath=[];return begin.call(this);};
   p.moveTo=function(x,y){this.auditPath?.push(['M',x,y]);return move.call(this,x,y);};
   p.lineTo=function(x,y){this.auditPath?.push(['L',x,y]);return line.call(this,x,y);};
   p.clearRect=function(...args){this.canvas.auditArrows=[];return clear.apply(this,args);};
   p.stroke=function(...args){if(this.strokeStyle==='#effaf3')this.canvas.auditArrows?.push(this.auditPath.map(x=>[...x]));return stroke.apply(this,args);};
  });
  await page.goto(base);await page.getByLabel('Native model value').filter({hasText:'22.303'}).waitFor();
  await page.getByLabel('Graphics quality').selectOption('basic');await page.getByRole('button',{name:'Current vectors',exact:true}).click();
  const canvas=page.getByRole('img',{name:'Scientific depth slice'});await canvas.waitFor();
  await page.waitForFunction(()=>document.querySelector('.basic-ocean')?.auditArrows?.length>0);
  const rendering=await canvas.evaluate(c=>({width:c.clientWidth,height:c.clientHeight,arrows:c.auditArrows}));
  const fields={};
  for(const variable of ['eastward_velocity','northward_velocity']){
   const response=await page.request.get(`${base}/api/cases/bay-bengal-2024-01/subset?variable=${variable}&time_index=0&representation=display&operation=volume`);fields[variable]=await response.json();
  }
  const east=fields.eastward_velocity,north=fields.northward_velocity,z=east.depth_m.indexOf(100),lon=east.longitude,lat=east.latitude,expected=[];
  for(let y=0;y<lat.length;y+=3)for(let x=0;x<lon.length;x+=3){
   const i=(z*lat.length+y)*lon.length+x,u=east.values[i],v=north.values[i];if(u===null||v===null||Math.hypot(u,v)<1e-8)continue;
   // Independent physical step on a sphere, then the chart's lon/lat-to-pixel map.
   const dLon=u/(6371008.8*Math.cos(lat[y]*Math.PI/180))*180/Math.PI,dLat=v/6371008.8*180/Math.PI;
   const dx=dLon/(lon.at(-1)-lon[0])*(rendering.width-95),dy=-dLat/(lat.at(-1)-lat[0])*(rendering.height-94),m=Math.hypot(dx,dy);
   expected.push([14*dx/m,14*dy/m]);
  }
  let maximumError=0;
  const actual=rendering.arrows.map(a=>[a[1][1]-a[0][1],a[1][2]-a[0][2]]);
  actual.forEach((a,i)=>{maximumError=Math.max(maximumError,...a.map((v,n)=>Math.abs(v-expected[i][n])));});
  const file=`${prefix}-${viewport.width}.png`;await page.locator('.ocean-viewport').screenshot({path:path.join(out,file)});
  rows.push({viewport,arrows:actual.length,expectedArrows:expected.length,maximumErrorCssPixels:maximumError,tolerance:1e-8,passed:actual.length===expected.length&&maximumError<1e-8,file});
  await browser.close();
 }
 const result={base,checkedUtc:new Date().toISOString(),method:'Intercept actual CanvasRenderingContext2D arrow line segments and compare with independent spherical physical displacement mapped to the rendered axes.',rows,passed:rows.every(r=>r.passed)};
 fs.writeFileSync(path.join(out,prefix+'.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));if(!result.passed)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1);});
