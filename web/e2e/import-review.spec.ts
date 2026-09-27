import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { enterWorkspace,openTool,displaySettings } from './ux-helpers';
const root=resolve(import.meta.dirname,'../../casepacks/instruments');
const native=JSON.parse(readFileSync(resolve(root,'../../tests/fixtures/p16a-chlorophyll-profile.json'),'utf8'));
async function openImport(page:import('@playwright/test').Page){await enterWorkspace(page);await openTool(page,'Open instruments');await expect(page.getByLabel('Observed sample value')).toBeVisible();await page.getByRole('button',{name:'Import observations',exact:true}).click();}

test('review precedes adding, imported pin opens beside model, and clearing removes only imports',async({page})=>{
 await openImport(page);const previous=await page.getByLabel('Instrument profile').inputValue();
 await page.locator('input[type=file]').setInputFiles(resolve(root,'examples','D2903891_012.nc'));
 await expect(page.getByLabel('Import preview')).toContainText('Detected variables and quality');
 await expect(page.getByLabel('Instrument profile')).toHaveValue(previous);
 await expect(page.locator('.observation-pin[aria-label^="Inspect Imported:"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
 const imported=await page.getByLabel('Instrument profile').inputValue();expect(imported).toMatch(/^import-/);
 await expect(page.getByRole('region',{name:'Ocean model context',exact:true})).toBeVisible();
 await expect(page.getByLabel('Observed sample value')).toBeVisible();
 await page.getByRole('button',{name:'Close profile',exact:true}).click();
 const pin=page.locator('.observation-pin[aria-label^="Inspect Imported:"]');await expect(pin).toHaveCount(1);await pin.click();
 await expect(page.getByLabel('Instrument profile')).toHaveValue(imported);
 await expect(page.getByLabel('Observation and model dates')).toContainText('Observation');
 await page.getByRole('button',{name:'Clear imported profiles',exact:true}).click();
 await expect(page.locator('.observation-pin[aria-label^="Inspect Imported:"]')).toHaveCount(0);
 await expect(page.locator('.observation-pin')).not.toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('CSV mapping converts only supported units and previews QC before committing',async({page})=>{
 await openImport(page);
 const body='profile_id,instrument,platform,time,latitude,longitude,pressure_dbar,pressure_qc,position_qc,time_qc,water_temperature,quality,ignored\nfixture,ctd,analytical-test,2024-01-08T00:00:00Z,13,87,10,1,1,1,300,1,note\nfixture,ctd,analytical-test,2024-01-08T00:00:00Z,13,87,20,1,1,1,,9,note\n';
 await page.locator('input[type=file]').setInputFiles({name:'analytical-test.csv',mimeType:'text/csv',buffer:Buffer.from(body)});
 await expect(page.getByLabel('Import preview')).toContainText('QC column');
 await page.getByLabel('Source column for temperature_c',{exact:true}).selectOption('water_temperature');
 await page.getByLabel('Source units for temperature_c',{exact:true}).selectOption('K');
 await page.getByLabel('Source column for temperature_qc',{exact:true}).selectOption('quality');
 await page.getByRole('button',{name:'Review mapped file',exact:true}).click();
 await expect(page.getByRole('button',{name:'Add profiles to workspace',exact:true})).toBeEnabled();
 await page.getByText('Map supported CSV columns',{exact:true}).click();
 await page.getByLabel('Source column for latitude',{exact:true}).selectOption('');
 await expect(page.getByLabel('Source column for latitude',{exact:true})).toHaveValue('');
 await expect(page.getByRole('button',{name:'Add profiles to workspace',exact:true})).toBeDisabled();
 await page.getByLabel('Source column for latitude',{exact:true}).selectOption('latitude');
 await page.getByRole('button',{name:'Review mapped file',exact:true}).click();
 await expect(page.getByRole('button',{name:'Add profiles to workspace',exact:true})).toBeEnabled();
 const row=page.getByRole('row').filter({hasText:'Temperature'});await expect(row).toContainText('1');
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
 await expect(page.getByLabel('Observed sample value')).toContainText('26.85');
 await page.getByLabel('Observation sample',{exact:true}).selectOption('1');
 await expect(page.getByLabel('Observed sample value')).toContainText('Missing');
 await expect(page.getByLabel('Observed sample value')).toContainText('Excluded');
});

test('chlorophyll source values retain QC, separate dates and the model context',async({page})=>{
 await openImport(page);
 await page.getByText('Formats and genuine example files',{exact:true}).click();
 await page.getByRole('button',{name:'Preview SR1902594_034.nc',exact:true}).click();
 await expect(page.getByLabel('Import preview')).toContainText('Chlorophyll');
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
 await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');
 await expect(page.locator('.observation-context')).toContainText('outside its time range');
 await expect(page.getByLabel('Observation and model dates')).toContainText('29 Mar 2024');
 await expect(page.getByLabel('Observation and model dates')).toContainText('07 Jan 2024');
 await expect(page.locator('.curve-key')).toContainText('1171 accepted');
 const index=native.levels.findIndex((l:{readings:{chlorophyll:{accepted:boolean}}})=>l.readings.chlorophyll.accepted);
 await page.getByLabel('Observation sample',{exact:true}).selectOption(String(index));
 await expect(page.getByLabel('Observed sample value')).toContainText(native.levels[index].readings.chlorophyll.value.toLocaleString('en-US',{maximumFractionDigits:3}));
 await expect(page.locator('.instrument-readings')).toContainText('no chlorophyll field');
 await page.getByRole('button',{name:'View nearest model depth',exact:true}).click();
 await expect(page.getByLabel('Observed sample value')).toBeVisible();
 await expect(page.getByLabel('Ocean timestamp')).toHaveValue('0');
 await expect(page.locator('.ocean-notice')).toContainText('no comparison has been calculated');
});

test('cancelled delayed review cannot replace an existing profile',async({page})=>{
 await openImport(page);const previous=await page.getByLabel('Instrument profile').inputValue();
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
 await page.route('**/api/instruments/inspect?**',async route=>{await gate;try{await route.continue();}catch{}});
 await page.locator('input[type=file]').setInputFiles(resolve(root,'examples','D2903891_012.nc'));
 await page.getByRole('button',{name:'Cancel review',exact:true}).click();release();
 await expect(page.locator('.import-panel')).toContainText('cancelled');
 await expect(page.getByLabel('Instrument profile')).toHaveValue(previous);
 await expect(page.getByLabel('Import preview')).toHaveCount(0);
 await page.unroute('**/api/instruments/inspect?**');
 await page.locator('input[type=file]').setInputFiles(resolve(root,'examples','D2903891_012.nc'));
 await expect(page.getByLabel('Import preview')).toBeVisible();
 await page.getByRole('button',{name:'Discard preview',exact:true}).click();
 await expect(page.getByLabel('Instrument profile')).toHaveValue(previous);
});

test('Basic graphics keeps imported locations accessible and shows out-of-area imports honestly',async({page})=>{
 await openImport(page);await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
 await page.locator('input[type=file]').setInputFiles(resolve(root,'examples','D2903891_012.nc'));
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
 const list=page.getByLabel('Instrument locations in Basic view');await expect(list).toBeVisible();
 await list.getByRole('button',{name:/Imported:/}).click();
 await expect(page.getByLabel('Instrument profile')).toHaveValue(/^import-/);
 await page.locator('input[type=file]').setInputFiles(resolve(root,'examples','ctd-station.csv'));
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
 await expect(page.locator('.observation-context')).toContainText('outside the selected model domain');
 await expect(page.getByRole('button',{name:'View nearest model depth',exact:true})).toBeDisabled();
 await expect(list.getByRole('button',{name:/Imported:/})).toHaveCount(1);
});
