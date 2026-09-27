import { displaySettings, enterWorkspace, openTool } from './ux-helpers';
import { expect,test,type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

async function open(page:Page){
  await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));
  await enterWorkspace(page);await openTool(page,'Open structure search');
  await expect(page.getByLabel('Structure search results',{exact:true})).toBeVisible({timeout:20000});
}
async function noon(page:Page){await page.getByLabel('Structure model snapshot',{exact:true}).selectOption('1');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.locator('.feature-result-header')).toContainText('2024-01-07 12:00 UTC');}

test('native query, eligible evidence, exact source section and exported values stay connected',async({page,browserName})=>{
  test.setTimeout(60000);await open(page);await noon(page);
  const inspector=page.getByLabel('Selected structure inspector',{exact:true});
  await expect(inspector).toContainText('12,966.152 km³');await expect(inspector).toContainText('34 eligible samples in 2 profiles');
  if(browserName==='chromium')await expect(page.locator('.feature-mesh-canvas')).toHaveAttribute('data-rendered','region');
  await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');
  await page.getByLabel('Section start longitude').fill('86');await page.getByLabel('Section start latitude').fill('13');await page.getByLabel('Section end longitude').fill('89');await page.getByLabel('Section end latitude').fill('14');
  await page.getByRole('button',{name:'Build section',exact:true}).click();await expect(page.getByRole('img',{name:'Vertical section along the drawn line'})).toBeVisible({timeout:20000});
  await page.getByLabel('Section station',{exact:true}).selectOption('23');await page.getByLabel('Section native depth',{exact:true}).selectOption('7');
  const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'Export query results',exact:true}).click();const item=await downloaded,path=await item.path();expect(path).not.toBeNull();const exported=JSON.parse(await readFile(path!,'utf8'));
  expect(exported.result.qualified_cells).toBe(80203);expect(exported.result.query.threshold).toBe(26);expect(exported.result.model_time).toBe('2024-01-07T12:00:00Z');expect(exported.selected_region.region.eligible_samples).toBe(34);expect(exported.section.start).toEqual([86,13]);expect(exported.section.end).toEqual([89,14]);
  const value=exported.section.values[7*81+23],station=exported.section.stations[23];await expect(page.getByLabel('Section source value')).toContainText(value.toLocaleString('en-US',{maximumFractionDigits:6}));
  const source=await page.request.get(`/api/cases/bay-bengal-2024-01/subset?variable=temperature&time_index=1&representation=analytical&operation=depth_slice&depth_index=${exported.result.coordinates.depth_m.indexOf(exported.section.depth_m[7])}`);expect(source.ok()).toBeTruthy();const subset=await source.json(),i=subset.longitude.indexOf(station.model_longitude),j=subset.latitude.indexOf(station.model_latitude);expect(i).toBeGreaterThanOrEqual(0);expect(j).toBeGreaterThanOrEqual(0);expect(value).toBe(subset.values[j*subset.longitude.length+i]);
  await inspector.getByRole('button',{name:/1902669/}).click();await expect(page.getByLabel('Instrument profile',{exact:true})).toBeVisible();
});

test('pending query keeps its verified condition and section, then updates honestly',async({page})=>{
  test.setTimeout(60000);await open(page);await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');
  await page.getByRole('button',{name:'Section through selected region',exact:true}).click();await expect(page.getByLabel('Section source value')).toBeVisible();
  let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
  await page.route('**/features/search',async route=>{if(route.request().postDataJSON().threshold===27)await gate;await route.continue();});
  await page.getByLabel('Structure threshold').fill('27');await page.getByRole('button',{name:'Find regions',exact:true}).click();
  await expect(page.locator('.feature-result-header')).toContainText('PREVIOUS VERIFIED RESULT');await expect(page.locator('.feature-result-header')).toContainText('Temperature ≥ 26 °C');await expect(page.getByLabel('Section source value')).toBeVisible();
  release();await expect(page.locator('.feature-result-header')).toContainText('Temperature ≥ 27 °C');await expect(page.getByLabel('Section source value')).toHaveCount(0);await expect(page.getByLabel('Draw a question',{exact:true})).toContainText('earlier section belongs to a different query');
});

test('empty, inclusive equality, order and derived variable queries explain their results',async({page})=>{
  test.setTimeout(60000);await open(page);
  await page.getByLabel('Structure threshold').fill('100');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.getByRole('heading',{name:'No regions meet this condition',exact:true})).toBeVisible();
  await page.getByLabel('Threshold condition', { exact: true }).selectOption('between');await page.getByLabel('Structure threshold',{exact:true}).fill('28.199000389431603');await page.getByLabel('Structure upper threshold').fill('28.199000389431603');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.locator('.feature-result-header')).toContainText('28.199000389431603 to 28.199000389431603');
  await page.getByLabel('Structure variable').selectOption('horizontal_kinetic_energy');await page.getByLabel('Threshold condition', { exact: true }).selectOption('at_least');await page.getByLabel('Order regions by').selectOption('observations');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.locator('.feature-result-header')).toContainText('Horizontal kinetic energy ≥ 0.05 m²/s²');await expect(page.getByLabel('Selected structure inspector')).toContainText('no comparable velocity or kinetic-energy observations');
});

test('malformed component totals are rejected before unverified results are shown',async({page})=>{
  await page.route('**/features/search',async route=>{const response=await route.fetch(),body=await response.json();body.qualified_cells+=1;await route.fulfill({response,json:body});});
  await enterWorkspace(page);await openTool(page,'Open structure search');await expect(page.getByLabel('Underwater structure search')).toContainText('The structure result could not be verified.');await expect(page.getByLabel('Structure search results')).toHaveCount(0);
});

test('map drawing uses real SVG coordinates and query mode preserves the explorer',async({page})=>{
  test.setTimeout(60000);await open(page);await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');await page.getByRole('button',{name:'Draw a section',exact:true}).click();
  const map=page.getByRole('img',{name:'Plan view of qualifying regions and section line'});await map.scrollIntoViewIfNeeded();
  await map.evaluate(svg=>svg.addEventListener('click',event=>{const mouse=event as MouseEvent,m=(svg as SVGSVGElement).getScreenCTM()!,p=new DOMPoint(mouse.clientX,mouse.clientY).matrixTransform(m.inverse());svg.setAttribute('data-test-first-click',JSON.stringify([p.x,p.y]));},{once:true}));
  for(const point of [[200,120],[450,230]]){const p=await map.evaluate((svg,[x,y])=>{const chart=svg.parentElement!,bounds=chart.getBoundingClientRect(),initial=new DOMPoint(x,y).matrixTransform((svg as SVGSVGElement).getScreenCTM()!);if(initial.x>bounds.right-20)chart.scrollLeft+=initial.x-bounds.right+20;if(initial.x<bounds.left+20)chart.scrollLeft+=initial.x-bounds.left-20;const p=new DOMPoint(x,y).matrixTransform((svg as SVGSVGElement).getScreenCTM()!);return {x:p.x,y:p.y};},point);await page.mouse.click(p.x,p.y);}
  await expect(page.getByRole('img',{name:'Vertical section along the drawn line'})).toBeVisible({timeout:20000});
  const actualClick=JSON.parse((await map.getAttribute('data-test-first-click'))!),aLon=Number(await page.getByLabel('Section start longitude').inputValue()),aLat=Number(await page.getByLabel('Section start latitude').inputValue());expect(aLon).toBeCloseTo(85.0400390625+(actualClick[0]-64)/554*(90-85.0400390625),8);expect(aLat).toBeCloseTo(15-(actualClick[1]-22)/310*3,8);
  await openTool(page,'Ocean explorer');await displaySettings(page);await expect(page.getByLabel('Graphics quality')).toBeVisible();await openTool(page,'Open structure search');await expect(page.getByLabel('Section source value')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  const chartMetrics=await page.locator('.feature-chart-scroll').evaluateAll(charts=>charts.map(chart=>{const svg=chart.querySelector('svg')!,label=svg.querySelector('text')!,matrix=svg.getScreenCTM()!;return {labelPixels:parseFloat(getComputedStyle(label).fontSize)*Math.hypot(matrix.a,matrix.b),minimum:innerWidth<680?11.5:8,focusable:(chart as HTMLElement).tabIndex===0,inside:chart.getBoundingClientRect().right<=innerWidth+1};}));expect(chartMetrics.length).toBe(2);expect(chartMetrics.every(chart=>chart.labelPixels>=chart.minimum&&chart.focusable&&chart.inside)).toBe(true);
});

test('service failure retains the last verified region and can recover',async({page})=>{
  test.setTimeout(60000);await open(page);await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');
  await page.route('**/features/search',route=>route.request().postDataJSON().threshold===27?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Structure service temporarily unavailable.'}})}):route.continue());
  await page.getByLabel('Structure threshold').fill('27');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.getByLabel('Underwater structure search')).toContainText('Structure service temporarily unavailable.');await expect(page.locator('.feature-result-header')).toContainText('Temperature ≥ 26 °C');
  await page.unroute('**/features/search');await page.getByLabel('Underwater structure search').getByRole('button',{name:'Try again',exact:true}).click();await expect(page.locator('.feature-result-header')).toContainText('Temperature ≥ 27 °C');
});
