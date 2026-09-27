import { dismissIntroduction, displaySettings, enterWorkspace, openTool } from './ux-helpers';
import { expect,test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const root=resolve(import.meta.dirname,'../../casepacks/instruments');
const catalog=JSON.parse(readFileSync(resolve(root,'index.json'),'utf8'));
const getProfile=(type:string,platform?:string)=>catalog.profiles.find((p:{instrument:string;platform:string})=>p.instrument===type&&(!platform||p.platform===platform));
const original=(id:string)=>JSON.parse(readFileSync(resolve(root,id+'.json'),'utf8'));
async function open(page:import('@playwright/test').Page){await enterWorkspace(page);await openTool(page,'Open instruments');await expect(page.getByLabel('Observed sample value')).toBeVisible();}

test('instrument markers select real profiles and link to the nearest native model depth',async({page})=>{
  const p=getProfile('argo','2903891'),raw=original(p.id);
  await enterWorkspace(page);await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('balanced');
  await page.getByLabel('Instrument locations',{exact:true}).check();
  const pin=page.locator('.observation-pin').filter({hasText:'2'});await expect(pin).toBeVisible();await pin.click();
  await expect(page.getByLabel('Instrument profile')).toHaveValue(p.id);
  const i=raw.levels.findIndex((l:{depth_m:number})=>l.depth_m>=99&&l.depth_m<=110);expect(i).toBeGreaterThan(-1);
  await page.getByLabel('Observation sample',{exact:true}).selectOption(String(i));
  await expect(page.getByLabel('Observed sample value')).toContainText(raw.levels[i].readings.temperature.value.toLocaleString('en-US',{maximumFractionDigits:3}));
  await page.getByRole('button',{name:'View nearest model depth',exact:true}).click();
  await expect(page.getByLabel('Explorer depth')).toHaveValue('19');
  await expect(page.locator('.ocean-notice')).toContainText('no comparison has been calculated');
  await expect(page.getByLabel('Ocean timestamp')).toHaveValue('0');
  await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
  await page.getByLabel('Instrument locations',{exact:true}).uncheck();await expect(page.locator('.observation-pin')).toHaveCount(0);
});

test('BGC charts use the oxygen adjustment and preserve distinct parameter modes',async({page})=>{
  const p=getProfile('bgc'),raw=original(p.id),i=raw.levels.findIndex((l:{readings:{oxygen:{accepted:boolean}}})=>l.readings.oxygen.accepted);
  await open(page);await page.getByLabel('Observation collection').selectOption(p.collection);
  await expect(page.getByLabel('Profile variable')).toHaveValue('oxygen');
  const eligible=(i:number)=>Boolean(raw.levels[i]?.readings.oxygen.accepted&&raw.levels[i]?.depth_m!==null);
  const isolated=raw.levels.filter((_:unknown,i:number)=>eligible(i)&&!eligible(i-1)&&!eligible(i+1));
  expect(isolated.length).toBeGreaterThan(0);await expect(page.locator('.profile-chart .accepted-sample')).toHaveCount(isolated.length);
  await page.getByLabel('Observation sample',{exact:true}).selectOption(String(i));
  await expect(page.getByLabel('Observed sample value')).toContainText(raw.levels[i].readings.oxygen.value.toLocaleString('en-US',{maximumFractionDigits:3}));
  await expect(page.getByLabel('Observed sample value')).toContainText('ARGO 1 · A');
  await page.getByText('Raw, adjusted and coordinate details',{exact:true}).click();
  await expect(page.locator('.sample-details')).toContainText(raw.levels[i].readings.oxygen.raw.toLocaleString('en-US',{maximumFractionDigits:3}));
  await page.getByLabel('Profile variable').selectOption('temperature');await expect(page.getByLabel('Observed sample value')).toContainText('· R');
  await expect(page.getByRole('button',{name:'View nearest model depth',exact:true})).toBeDisabled();
  await expect(page.locator('.observation-context')).toContainText('outside the selected model domain');
});

test('glider preserves moving samples and excludes contradictory salinity metadata',async({page})=>{
  const all=catalog.profiles.filter((p:{instrument:string})=>p.instrument==='glider'),p=all[2],raw=original(p.id);
  await open(page);await page.getByLabel('Observation collection').selectOption(p.collection);await page.getByLabel('Instrument profile').selectOption(p.id);
  await expect(page.getByLabel('Observed sample value')).toContainText('QARTOD');
  await page.getByLabel('Observation sample',{exact:true}).selectOption('500');
  await expect(page.locator('.instrument-readings')).toContainText(raw.levels[500].latitude.toFixed(6));
  await expect(page.locator('.instrument-readings')).toContainText(raw.levels[500].time.replace('T',' ').replace('Z',' UTC'));
  await page.getByText('Location, track and source',{exact:true}).click();await page.getByRole('button',{name:'Track detail',exact:true}).click();await expect(page.getByRole('button',{name:'Track detail',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByLabel('Profile variable').selectOption('salinity');
  await expect(page.locator('.curve-key')).toContainText('0 accepted');
  await expect(page.getByLabel('Observed sample value')).toContainText('valid_min exceeds valid_max');
  await page.getByLabel('Show excluded values').check();await expect(page.locator('.profile-chart svg path')).not.toHaveCount(1);
  await expect(page.getByRole('button',{name:'View nearest model depth',exact:true})).toBeDisabled();
});

test('ship CTD shows source values and missing oxygen without fabricated curves',async({page})=>{
  const p=getProfile('ctd');await open(page);await page.getByLabel('Observation collection').selectOption(p.collection);
  await expect(page.getByLabel('Observed sample value')).toContainText('25.155');
  await expect(page.locator('.instrument-readings')).toContainText('1996-02-21 11:16:00 UTC');
  await page.getByLabel('Profile variable').selectOption('oxygen');await expect(page.getByLabel('Observed sample value')).toContainText('Missing');
  await expect(page.locator('.curve-key')).toContainText('0 accepted');
  await expect(page.getByText('No eligible values for this curve.',{exact:true})).toBeVisible();
});

test('genuine CSV and NetCDF imports are session-only and can be cleared',async({page})=>{
  await open(page);await page.getByRole('button',{name:'Import observations',exact:true}).click();
  const input=page.locator('input[type=file]');
  for(const name of ['argo-2903891-example.csv','D2903891_012.nc','ctd-station.csv','SR6903091_100.nc','glider-ru29.nc']){
    await input.setInputFiles(resolve(root,'examples',name));
    await expect(page.getByLabel('Import preview')).toBeVisible();
    await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
    await expect(page.locator('.import-panel')).toContainText('Stored only in this open workspace.',{timeout:25000});
    await expect(page.getByLabel('Observation collection')).toHaveValue(`Imported · ${name}`);
    await expect(page.getByLabel('Observed sample value')).toBeVisible();
  }
  await page.getByRole('button',{name:'Clear imported profiles',exact:true}).click();
  await expect(page.getByLabel('Observation collection').locator('option')).toHaveCount(new Set(catalog.profiles.map((p:{collection:string})=>p.collection)).size);
  await page.reload();await dismissIntroduction(page);await openTool(page,'Open instruments');
  await expect(page.getByLabel('Observation collection').locator('option')).toHaveCount(new Set(catalog.profiles.map((p:{collection:string})=>p.collection)).size);
  expect(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length}))).toEqual({local:0,session:0});
});

test('unsupported uploads and oversized files explain errors without replacing the selected profile',async({page})=>{
  await open(page);const selected=await page.getByLabel('Instrument profile').inputValue();await page.getByRole('button',{name:'Import observations',exact:true}).click();
  await page.locator('input[type=file]').setInputFiles({name:'broken.csv',mimeType:'text/csv',buffer:Buffer.from('a,b\n1,2')});
  await expect(page.locator('.import-panel [role=alert]')).toContainText('documented Depth Atlas CSV columns');
  await expect(page.getByLabel('Instrument profile')).toHaveValue(selected);
  await page.locator('input[type=file]').setInputFiles({name:'large.csv',mimeType:'text/csv',buffer:Buffer.alloc(2_000_001)});
  await expect(page.locator('.import-panel [role=alert]')).toContainText('no larger than 2 MB');
});

test('inconsistent observation quality counts cannot render an accepted curve',async({page})=>{
  await page.route('**/api/instruments/profiles/*',async route=>{const response=await route.fetch();const body=await response.json();body.parameters.temperature.accepted_count=999;await route.fulfill({response,json:body});});
  await enterWorkspace(page);await openTool(page,'Open instruments');
  await expect(page.locator('.instrument-readings [role=alert]')).toContainText('could not be verified');
  await expect(page.getByLabel('Observed sample value')).toHaveCount(0);
  await page.unroute('**/api/instruments/profiles/*');await page.getByRole('button',{name:'Retry profile',exact:true}).click();
  await expect(page.getByLabel('Observed sample value')).toBeVisible();
});

test('observation map is keyboard selectable and keeps the source timestamp',async({page})=>{
  await open(page);await page.getByText('Location, track and source',{exact:true}).click();const p=getProfile('argo','2903891');const marker=page.getByRole('button',{name:`${p.title}, ${p.time}`,exact:true});await marker.focus();await page.keyboard.press('Enter');
  await expect(page.getByLabel('Instrument profile')).toHaveValue(p.id);await expect(page.locator('.instrument-readings')).toContainText(p.time.replace('T',' ').replace('Z',' UTC'));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
