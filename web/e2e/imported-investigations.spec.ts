import {test,expect,type Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {enterWorkspace,dismissIntroduction,openTool} from './ux-helpers';

async function imported(page:Page){
  await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');
  await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
  await page.getByLabel('Ocean timestamp').selectOption('2');await openTool(page,'Open instruments');
  await page.getByRole('button',{name:'Import observations',exact:true}).click();
  await page.getByText('Formats and genuine example files',{exact:true}).click();
  await page.getByRole('button',{name:'Preview SR1902594_034.nc',exact:true}).click();
  await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
  await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');
  await page.getByRole('button',{name:'Import observations',exact:true}).click();
}
async function save(page:Page,title:string){
  await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();
  await expect(page.locator('.investigation-capture')).toContainText('original uploaded file');
  await page.getByLabel('Investigation name',{exact:true}).fill(title);
  await page.getByRole('button',{name:'Save on this browser',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible({timeout:30000});
  await expect(page.getByRole('button',{name:'Copy replay link',exact:true})).toBeDisabled();
}
async function download(page:Page){
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Investigation JSON',exact:true}).click();
  const file=await pending;return await readFile((await file.path())!);
}
async function reopen(page:Page){
  await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible({timeout:30000});
  await expect(page.locator('.replay-notice')).toContainText('Recalculation matched');
}

test('imported comparison saves, exports and replays exact results in a new browser context',async({page,browser})=>{
  test.setTimeout(120000);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await imported(page);await page.getByRole('button',{name:'Compare with model',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('/ 1475');
  await expect(page.locator('.evidence-notice').first()).toContainText('this file only');
  const count=await page.getByLabel('Eligible comparison count').innerText();expect(count).not.toMatch(/^0 \/ /);
  await save(page,'Imported March comparison');const bytes=await download(page),record=JSON.parse(bytes.toString());
  expect(record.replay.import_source.filename).toBe('SR1902594_034.nc');expect(record.imported_profiles).toHaveLength(1);
  expect(record.results[0].output.matched_count).toBeGreaterThan(0);expect(bytes.length).toBeLessThan(8000000);
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Complete evidence ZIP',exact:true}).click();
  const zipped=await pending;expect((await readFile((await zipped.path())!)).subarray(0,2).toString()).toBe('PK');
  const ctx=await browser.newContext({viewport:page.viewportSize()??undefined}),other=await ctx.newPage();
  await enterWorkspace(other,page.url());await other.getByRole('button',{name:'Open saved investigations'}).click();
  await other.getByLabel('Open investigation file',{exact:true}).setInputFiles({name:'imported.json',mimeType:'application/json',buffer:bytes});
  await expect(other.getByLabel('Selected saved investigation')).toContainText('Imported March comparison');await reopen(other);
  await expect(other.getByLabel('Eligible comparison count')).toHaveText(count,{useInnerText:true});
  await expect(other.getByLabel('Comparison profile')).toHaveValue(record.replay.recipe.profile_id);
  await other.getByRole('button',{name:'Inspect source readings',exact:true}).click();
  await expect(other.getByLabel('Profile variable')).toHaveValue('temperature');
  await expect(other.getByLabel('Observed sample value')).toBeVisible();
  expect(await other.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);await ctx.close();
});

test('chlorophyll profile persists through reload and deletion leaves its portable backup usable',async({page})=>{
  test.setTimeout(120000);await imported(page);await page.getByLabel('Observation sample',{exact:true}).selectOption('100');
  await page.getByLabel('Show excluded values').check();const value=await page.getByLabel('Observed sample value').innerText();
  await save(page,'Imported chlorophyll');const bytes=await download(page);
  await page.reload();await dismissIntroduction(page);await page.getByRole('button',{name:'Open saved investigations'}).click();
  await page.getByRole('button',{name:/Imported chlorophyll Observation profile/}).click();await reopen(page);
  await expect(page.getByLabel('Observation sample',{exact:true})).toHaveValue('100');
  await expect(page.getByLabel('Ocean timestamp')).toHaveValue('2');
  await expect(page.getByLabel('Show excluded values')).toBeChecked();
  await expect(page.getByLabel('Observed sample value')).toHaveText(value,{useInnerText:true});
  await page.getByRole('button',{name:'Open saved investigations'}).click();
  await page.getByRole('button',{name:'Remove local copy of Imported chlorophyll',exact:true}).click();
  await expect(page.locator('.investigation-library')).toContainText('No local investigations yet.');
  await page.getByLabel('Open investigation file',{exact:true}).setInputFiles({name:'backup.json',mimeType:'application/json',buffer:bytes});await reopen(page);
  await expect(page.getByLabel('Observed sample value')).toHaveText(value,{useInnerText:true});
});

test('tampered embedded input is rejected without replacing the open workspace',async({page})=>{
  test.setTimeout(90000);await imported(page);await save(page,'Tamper check');const raw=JSON.parse((await download(page)).toString());
  raw.replay.import_source.content_base64='Y2hhbmdlZA==';
  await page.getByLabel('Open investigation file',{exact:true}).setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(raw))});
  await expect(page.getByRole('alert')).toContainText('altered');
  await page.getByRole('button',{name:'Close saved investigations'}).click();
  await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');
});

test('changing imported and library sources clears the comparison reference',async({page})=>{
  test.setTimeout(90000);await imported(page);await page.getByRole('button',{name:'Compare with model',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('/ 1475');
  await page.getByRole('button',{name:'Keep this result as reference'}).click();await expect(page.locator('.evidence-baseline')).toBeVisible();
  const ids=await page.getByLabel('Comparison profile').locator('option').evaluateAll(options=>options.map(o=>(o as HTMLOptionElement).value));
  await page.getByLabel('Comparison profile').selectOption(ids.find(id=>!id.startsWith('import-'))!);
  await expect(page.locator('.evidence-baseline')).toHaveCount(0);
  await expect(page.getByLabel('Eligible comparison count')).toBeVisible();
});

test('imported time-window sensitivity preserves both policies and exclusions on replay',async({page})=>{
  test.setTimeout(120000);await imported(page);await page.getByRole('button',{name:'Compare with model',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('245 / 1475');
  await page.getByRole('button',{name:'Keep this result as reference'}).click();
  await page.getByRole('button',{name:'Matching rules',exact:true}).click();await page.getByLabel('Matching time window').fill('1');
  await page.getByRole('button',{name:'Apply matching rules'}).click();await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 1475');
  await save(page,'Imported sensitivity');const record=JSON.parse((await download(page)).toString());
  expect(record.replay.recipe.baseline.settings.time_window_hours).toBe(6);expect(record.replay.recipe.settings.time_window_hours).toBe(1);
  await reopen(page);await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 1475');
  await expect(page.locator('.evidence-baseline')).toContainText('245 eligible pairs');
  await page.getByRole('button',{name:'Restore reference settings'}).click();await expect(page.getByLabel('Eligible comparison count')).toContainText('245 / 1475');
});

test('mapped CSV keeps Kelvin conversion and quality exclusions after a reload',async({page})=>{
  test.setTimeout(90000);await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');
  await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);await page.getByLabel('Ocean timestamp').selectOption('2');
  await openTool(page,'Open instruments');await page.getByRole('button',{name:'Import observations',exact:true}).click();
  const text='profile_id,instrument,platform,time,latitude,longitude,pressure_dbar,pressure_qc,position_qc,time_qc,kelvin,flag\nunit,argo,fixture,2024-03-29T00:00:00Z,12.5,85.5,10,1,1,1,300,1\nunit,argo,fixture,2024-03-29T00:00:00Z,12.5,85.5,20,1,1,1,290,4\n';
  await page.locator('input[type=file]').setInputFiles({name:'mapped.csv',mimeType:'text/csv',buffer:Buffer.from(text)});
  await page.getByLabel('Source column for temperature_c',{exact:true}).selectOption('kelvin');
  await page.getByLabel('Source units for temperature_c',{exact:true}).selectOption('K');
  await page.getByLabel('Source column for temperature_qc',{exact:true}).selectOption('flag');
  await page.getByRole('button',{name:'Review mapped file',exact:true}).click();
  await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
  await expect(page.getByLabel('Observed sample value')).toContainText('26.85');
  await page.getByRole('button',{name:'Compare with model',exact:true}).click();await expect(page.getByLabel('Eligible comparison count')).toContainText('1 / 2');
  await save(page,'Mapped temperature');const record=JSON.parse((await download(page)).toString());
  expect(record.replay.import_source.mapping.temperature_c.units).toBe('K');expect(record.results[0].output.rows[1].reason).toBe('observation_qc');
  await page.reload();await dismissIntroduction(page);await page.getByRole('button',{name:'Open saved investigations'}).click();
  await page.getByRole('button',{name:/Mapped temperature Model comparison/}).click();await reopen(page);
  await expect(page.getByLabel('Eligible comparison count')).toContainText('1 / 2');
});
