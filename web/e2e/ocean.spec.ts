import { enterWorkspace, displaySettings, extraView } from './ux-helpers';
import { expect, test } from '@playwright/test';
import source from './fixtures/phase-03-source.json' with { type: 'json' };

// Independent perspective calculation from the declared physical domain and camera.
// This does not import the application's projection, picking or interpolation helpers.
function screenPoint(coordinates:number[],width:number,height:number,camera:number[],target:number[],exaggeration=200){
  const [west,south,east,north]=source.bounds,midLat=(south+north)/2;
  const metresPerDegree=6371008.8*Math.PI/180;
  const scale=10/((east-west)*metresPerDegree*Math.cos(midLat*Math.PI/180));
  const world=[(coordinates[0]-(west+east)/2)*metresPerDegree*Math.cos(midLat*Math.PI/180)*scale,-coordinates[2]*exaggeration*scale,-(coordinates[1]-midLat)*metresPerDegree*scale];
  const unit=(v:number[])=>{const n=Math.hypot(...v);return v.map(x=>x/n);};
  const cross=(a:number[],b:number[])=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const dot=(a:number[],b:number[])=>a.reduce((s,x,i)=>s+x*b[i],0);
  const forward=unit(target.map((x,i)=>x-camera[i])),right=unit(cross(forward,[0,1,0])),up=cross(right,forward),relative=world.map((x,i)=>x-camera[i]);
  const distance=dot(relative,forward),tangent=Math.tan(37*Math.PI/360);
  return {x:width*(1+dot(relative,right)/(distance*tangent*width/height))/2,y:height*(1-dot(relative,up)/(distance*tangent))/2};
}

test('3D and Basic clicks resolve to independently read source coordinates and values',async({page,browserName},testInfo)=>{
  await enterWorkspace(page);await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('balanced');
  // Test the field layer explicitly, without observation marker hit targets above it.
  await displaySettings(page);await page.getByLabel('Instrument locations',{exact:true}).uncheck();
  await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','volume');
  // Native latitude spacing can project to less than one pointer pixel at overview scale.
  // Zoom before checking an exact native row, just as a user would for precise picking.
  await page.getByRole('button',{name:'Zoom ocean in',exact:true}).click();
  await page.getByRole('button',{name:'Zoom ocean in',exact:true}).click();
  await page.getByRole('button',{name:'Zoom ocean in',exact:true}).click();
  for(const [i,point] of source.points.entries()){
    await page.getByRole('button',{name:i===0?'Depth slice':'Section',exact:true}).click();
    await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered',i===0?'slice':'section');
    const canvas=page.locator('.ocean-webgl canvas');const rect=await canvas.boundingBox();expect(rect).not.toBeNull();
    const view=await page.locator('.ocean-webgl').evaluate(e=>({camera:JSON.parse(e.dataset.camera!),target:JSON.parse(e.dataset.target!)}));
    // Aim inside the section near its bottom native level. A click exactly on the
    // 1,000 m outer edge can round below the domain, correctly producing no pick.
    const aim=i===1?[point.coordinates[0],point.coordinates[1],975]:point.coordinates;
    const requested=screenPoint(aim,rect!.width,rect!.height,view.camera,view.target);
    await canvas.evaluate(element=>element.addEventListener('pointerup',event=>{
      const pointer=event as PointerEvent,box=element.getBoundingClientRect(),host=element.parentElement!;
      element.setAttribute('data-audit-pointer',JSON.stringify({clientX:pointer.clientX,clientY:pointer.clientY,
        rect:{x:box.x,y:box.y,width:box.width,height:box.height},camera:host.dataset.camera,target:host.dataset.target}));
    },{once:true,capture:true}));
    // Firefox's delivered pointer was quantized more than one CSS pixel above
    // the subpixel target on this Windows display. Its correct native pick was
    // then the next latitude row. Aim at the pixel centre, retaining the exact
    // independently read native indices/value assertions and actual event trace.
    const pixelCenter=browserName==='firefox'?.5:0;
    await canvas.click({position:{x:requested.x+pixelCenter,y:requested.y+pixelCenter}});
    await testInfo.attach(`native-pick-${i}`,{body:JSON.stringify({point,aim,requested,pixelCenter,rect,view,
      delivered:JSON.parse((await canvas.getAttribute('data-audit-pointer'))!),
      longitude:await page.getByLabel('Probe longitude').inputValue(),latitude:await page.getByLabel('Probe latitude').inputValue()},null,2),contentType:'application/json'});
    await expect(page.getByLabel('Probe longitude')).toHaveValue(String(point.indices[0]));
    await expect(page.getByLabel('Probe latitude')).toHaveValue(String(point.indices[1]));
    await expect(page.getByLabel('Native model value')).toContainText(point.expected!.toFixed(3));
    await expect(page.getByLabel('Native model value')).toContainText(`${point.coordinates[2].toLocaleString()} m`);
  }
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
  await page.getByLabel('Explorer depth').selectOption('19');
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();
  const canvas=page.getByRole('img',{name:'Scientific depth slice'}),rect=(await canvas.boundingBox())!;
  const [west,south,east,north]=source.bounds,point=source.points[0];
  await canvas.click({position:{x:65+(rect.width-95)*(point.coordinates[0]-west)/(east-west),y:42+(rect.height-94)*(north-point.coordinates[1])/(north-south)}});
  await expect(page.getByLabel('Probe longitude')).toHaveValue(String(point.indices[0]));await expect(page.getByLabel('Probe latitude')).toHaveValue(String(point.indices[1]));
  await expect(page.getByLabel('Native model value')).toContainText(point.expected!.toFixed(3));
});

test('real scientific views, missing depths, isosurface and native numerical inspection',async({page,browserName})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&/THREE|shader/i.test(m.text()))errors.push(m.text());});
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  if(browserName==='chromium')await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','volume');
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();
  await page.getByLabel('Explorer depth').selectOption('39');await expect(page.getByLabel('Native model value')).toContainText('No value at this depth');
  await page.getByLabel('Explorer depth').selectOption('19');await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByRole('button',{name:'Section',exact:true}).click();await expect(page.getByLabel('Section latitude')).toBeVisible();
  await extraView(page,'Isosurface');
  if(browserName==='chromium')await expect.poll(()=>page.locator('.ocean-webgl').getAttribute('data-vertices')).not.toBe('0');
  await page.getByLabel('Isosurface value').fill('99');
  if(browserName==='chromium')await expect(page.locator('.ocean-empty-label')).toContainText('No isosurface at this value');
  await page.getByLabel('Isosurface value').fill('20');
  await page.getByLabel('Variable',{exact:true}).selectOption('salinity');await expect(page.getByLabel('Native model value')).toContainText('psu');
  await extraView(page,'Current vectors');await expect(page.getByLabel('Native model value')).toContainText('East 0.036 / North 0.070 m/s');
  expect(errors).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('colour and exaggeration controls cannot change analytical values',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByText('Colour, depth and display settings',{exact:true}).click();
  await page.getByLabel('Colour palette').selectOption('mono');await page.getByLabel('Colour minimum').fill('0');await page.getByLabel('Colour scale').selectOption('log');
  await expect(page.getByRole('alert')).toContainText('Log scale needs');
  await page.getByLabel('Colour minimum').fill('1');await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByLabel('Colour maximum').fill('0');await expect(page.getByRole('alert')).toContainText('Minimum must');await page.getByLabel('Colour maximum').fill('30');
  const stretch=page.getByLabel('Vertical exaggeration');if(await stretch.isEnabled())await stretch.fill('80');
  await page.getByLabel('Layer opacity').fill('0.25');await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');await expect(page.getByRole('img',{name:'Scientific depth section'})).toBeVisible();
});

test('timestamp selection and playback use the supplied snapshots',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
  await page.getByLabel('Ocean timestamp').selectOption('6');await expect(page.locator('.ocean-heading')).toContainText('10 Jan 2024, 00:00');
  await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
  await page.getByRole('button',{name:'Play ocean playback',exact:true}).click();await expect(page.getByLabel('Ocean timestamp')).not.toHaveValue('6');
  await page.getByRole('button',{name:'Pause ocean playback',exact:true}).click();
  await page.emulateMedia({reducedMotion:'reduce'});await expect(page.getByRole('button',{name:'Play ocean playback',exact:true})).toBeDisabled();
});

test('unavailable WebGL has a real selectable 2D fallback',async({page})=>{
  await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(this:HTMLCanvasElement,type:string,...args:unknown[]){if(type==='webgl2')return null;return Reflect.apply(original,this,[type,...args]);} as typeof original;});
  await enterWorkspace(page);await expect(page.locator('.ocean-render-status')).toHaveText('Basic 2D');
  await expect(page.getByRole('img',{name:'Scientific depth section'})).toBeVisible();
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();
  const canvas=page.getByRole('img',{name:'Scientific depth slice'});await expect(canvas).toBeVisible();await expect.poll(()=>canvas.getAttribute('data-cells')).not.toBe('0');
  await page.getByLabel('Explorer depth').selectOption('39');await expect(canvas).toHaveAttribute('data-cells','0');await expect(page.getByLabel('Native model value')).toContainText('No value at this depth');
  await page.getByRole('button',{name:'Section',exact:true}).click();await expect(page.getByRole('img',{name:'Scientific depth section'})).toBeVisible();
});

test('graphics context loss preserves data inspection',async({page,browserName})=>{
  test.skip(browserName!=='chromium','Chromium provides the WebGL2 context-loss test.');
  await enterWorkspace(page);await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','volume');
  await page.locator('.ocean-webgl canvas').evaluate((canvas:HTMLCanvasElement)=>canvas.getContext('webgl2')!.getExtension('WEBGL_lose_context')!.loseContext());
  await expect(page.locator('.ocean-render-status')).toHaveText('Basic 2D');await expect(page.getByLabel('Native model value')).toContainText('22.303');await expect(page.getByRole('img',{name:'Scientific depth section'})).toBeVisible();
});

test('failed field requests recover without substituting made-up data',async({page})=>{
  await page.route('**/subset?*',route=>{if(route.request().url().includes('representation=display'))return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Field temporarily unavailable.'}})});return route.continue();});
  await enterWorkspace(page);await expect(page.getByRole('alert')).toContainText('Field temporarily unavailable.');
  await expect(page.locator('.ocean-webgl canvas')).toHaveCount(0);await page.unroute('**/subset?*');await page.getByRole('button',{name:'Retry ocean field'}).click();
  await expect(page.getByLabel('Native model value')).toContainText('22.303',{timeout:20_000});
});

test('Auto reduces rendering cost under a slow frame clock and preserves native inspection',async({page})=>{
  // Inject long presented-frame intervals, without stalling the browser or altering data.
  await page.addInitScript(()=>{const raf=window.requestAnimationFrame.bind(window);window.requestAnimationFrame=callback=>raf(t=>callback(t*30));});
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.evaluate(()=>{const timer=setInterval(()=>{
    if(document.querySelector('.ocean-render-status')?.textContent==='Basic 2D'){clearInterval(timer);return;}
    (document.querySelector('[aria-label="Rotate ocean right"]') as HTMLButtonElement).click();
  },16);});
  await expect(page.locator('.ocean-render-status')).toHaveText('Basic 2D',{timeout:20_000});
  await expect(page.getByText('This device is drawing 3D slowly.',{exact:false})).toBeVisible();
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
});

test('cutaway exposes a real deep source value and distinguishes absent levels',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Depth window')).toHaveValue('1000');
  await displaySettings(page);await page.getByLabel('Instrument locations',{exact:true}).uncheck();
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('balanced');
  await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','volume');
  await page.getByRole('button',{name:'Cutaway',exact:true}).click();
  await expect(page.getByText('The opening reveals depth layers',{exact:false})).toBeVisible();
  await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-cut-progress','1.0000');
  const point=source.cut_face,canvas=page.locator('.ocean-webgl canvas');
  let rect=(await canvas.boundingBox())!,view=await page.locator('.ocean-webgl').evaluate(e=>({camera:JSON.parse(e.dataset.camera!),target:JSON.parse(e.dataset.target!)}));
  await canvas.click({position:screenPoint(point.coordinates,rect.width,rect.height,view.camera,view.target)});
  await expect(page.getByLabel('Native model value')).toContainText(point.expected.toFixed(3));
  await expect(page.getByLabel('Explorer depth')).toHaveValue('27');
  await page.getByLabel('Depth window').selectOption('5000');
  await expect(page.locator('.ocean-coverage')).toContainText('4,000 or 5,000 m');
  await expect.poll(()=>page.locator('.ocean-webgl').getAttribute('data-target')).not.toBe(JSON.stringify(view.target));
  rect=(await canvas.boundingBox())!;view=await page.locator('.ocean-webgl').evaluate(e=>({camera:JSON.parse(e.dataset.camera!),target:JSON.parse(e.dataset.target!)}));
  await canvas.click({position:screenPoint([point.coordinates[0],point.coordinates[1],4000],rect.width,rect.height,view.camera,view.target,50)});
  await expect(page.getByLabel('Native model value')).toContainText('No value at this depth');
  await expect(page.getByLabel('Explorer depth')).toHaveValue('38');
  await page.getByRole('button',{name:'Reset exploration',exact:true}).click();
  await expect(page.getByLabel('Depth window')).toHaveValue('1000');
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();await page.getByLabel('Explorer depth').selectOption('32');
  await expect(page.getByRole('button',{name:'Depth slice',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByLabel('Explorer depth')).toHaveValue('32');
});
