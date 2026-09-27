import {test,expect,type Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {enterWorkspace,openTool} from './ux-helpers';

async function support(page:Page){
  await enterWorkspace(page);await openTool(page,'Open structure search');
  await page.getByLabel('Structure model snapshot',{exact:true}).selectOption('1');
  await page.getByRole('button',{name:'Find regions',exact:true}).click();
  await expect(page.locator('.feature-result-header')).toContainText('2024-01-07 12:00 UTC');
  await page.getByRole('button',{name:'Show observation support',exact:true}).click();
  await expect(page.getByLabel('Structure support counts')).toContainText('34');
}

test('builder guides a complete investigation without saving automatically',async({page})=>{
  test.setTimeout(90000);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await enterWorkspace(page);await page.getByRole('button',{name:'Build investigation',exact:true}).click();
  const builder=page.getByLabel('Investigation builder',{exact:true});
  await builder.getByRole('button',{name:'Next: Explore depth',exact:true}).click();
  await builder.getByRole('button',{name:'Next: Inspect a reading',exact:true}).click();
  await page.getByLabel('Observation sample',{exact:true}).selectOption('5');
  await expect(page.getByLabel('Linked source selection')).toContainText('Source sample #');
  const observation=await page.getByLabel('Observation sample',{exact:true}).inputValue();
  await builder.getByRole('button',{name:'Next: Compare',exact:true}).click();
  await expect(page.getByLabel('Comparison sample',{exact:true})).toHaveValue(observation);
  await expect(page.getByLabel('Ocean model context',{exact:true})).toBeVisible();
  await builder.getByRole('button',{name:'Next: Save',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await builder.getByRole('button',{name:'Save this investigation',exact:true}).click();
  await page.getByLabel('Investigation name',{exact:true}).fill('Connected workflow check');
  await page.getByRole('button',{name:'Save on this browser',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible({timeout:30000});
  await page.getByRole('button',{name:'Close saved investigations',exact:true}).click();
  await expect(builder.getByRole('heading',{name:'Saved on this browser'})).toBeVisible();
  await page.getByLabel('Comparison model snapshot',{exact:true}).selectOption('1');
  await expect(builder.getByRole('heading',{name:'Saved on this browser',exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('source sample, variable, model time and unmatched states survive view changes',async({page})=>{
  test.setTimeout(90000);await enterWorkspace(page);await openTool(page,'Compare');
  await page.getByRole('button',{name:'Find a useful comparison',exact:true}).click();
  const suggestion=page.locator('.evidence-snapshot-suggestion button');if(await suggestion.count())await suggestion.click();
  await expect(page.getByLabel('Eligible comparison count')).not.toContainText('0 /');
  await page.getByLabel('Compared variable',{exact:true}).selectOption('salinity');
  await page.getByLabel('Comparison sample',{exact:true}).selectOption('10');
  const observationTime=await page.getByLabel('Selected comparison sample').locator('dd').first().innerText();
  const modelTime=await page.getByLabel('Comparison model snapshot',{exact:true}).inputValue();
  await page.getByRole('button',{name:'Inspect source readings',exact:true}).click();
  await expect(page.getByLabel('Profile variable',{exact:true})).toHaveValue('salinity');
  await expect(page.getByLabel('Observation sample',{exact:true})).toHaveValue('10');
  await expect(page.getByLabel('Ocean timestamp',{exact:true})).toHaveValue(modelTime);
  await page.getByRole('button',{name:'Compare with model',exact:true}).click();
  await expect(page.getByLabel('Comparison sample',{exact:true})).toHaveValue('10');
  await page.getByRole('button',{name:'Matching rules',exact:true}).click();
  await page.getByLabel('Matching time window',{exact:true}).fill('0');
  await page.getByRole('button',{name:'Apply matching rules',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('0 /');
  await expect(page.getByLabel('Linked source selection')).toContainText('Not paired');
  await expect(page.getByLabel('Linked model depth',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Selected comparison sample').locator('dd').first()).toHaveText(observationTime);
  await expect(page.getByRole('button',{name:'View matched model column',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Expand comparison',exact:true}).click();
  await expect(page.getByLabel('Ocean model context',{exact:true})).toBeHidden();
  await page.getByRole('button',{name:'Show model beside comparison',exact:true}).click();
  await expect(page.getByLabel('Ocean model context',{exact:true})).toBeVisible();
});

test('structure support shows checked residuals, gaps, sensitivity and a linked pair',async({page})=>{
  test.setTimeout(90000);await support(page);
  const counts=await page.getByLabel('Structure support counts').innerText();
  await page.getByRole('button',{name:'Keep support as reference',exact:true}).click();
  await page.getByText('Support matching rules and sensitivity',{exact:true}).click();
  await page.getByLabel('Support time window',{exact:true}).fill('0');
  await page.getByRole('button',{name:'Apply support rules',exact:true}).click();
  await expect(page.locator('.support-empty')).toContainText('No eligible pairs');
  await expect(page.getByLabel('Support sensitivity')).toContainText('-34');
  await page.getByRole('button',{name:'Restore support reference',exact:true}).click();
  await expect(page.getByLabel('Structure support counts')).toHaveText(counts,{useInnerText:true});
  const downloading=page.waitForEvent('download');await page.getByRole('button',{name:'Export support snapshot',exact:true}).click();
  const file=await downloading,record=JSON.parse(await readFile((await file.path())!,'utf8'));
  expect(record.support.eligible_samples).toBe(34);expect(record.reference.eligible_samples).toBe(34);
  expect(record.support.supported_cells+record.support.unsupported_cells).toBe(record.support.region_cells);
  await page.getByLabel('Structure support sample',{exact:true}).selectOption('3');
  const row=record.support.rows[3];
  await page.getByRole('button',{name:'Open this pair in comparison',exact:true}).click();
  await expect(page.getByLabel('Comparison profile',{exact:true})).toHaveValue(row.profile_id);
  await expect(page.getByLabel('Selected comparison sample')).toContainText(`Source sample #${row.sample_index}`);
  await expect(page.getByLabel('Comparison model snapshot',{exact:true})).toHaveValue('1');
  await openTool(page,'Open structure search');
  await expect(page.getByLabel('Structure support counts')).toHaveText(counts,{useInnerText:true});
  await expect(page.getByLabel('Support sensitivity')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('builder keeps its place after a lab detour and exposes unsupported monthly comparisons',async({page})=>{
  test.setTimeout(90000);await enterWorkspace(page);
  // Opening a model from the globe moves focus to the resulting workspace.
  await expect(page.locator('#ocean-workspace')).toBeFocused();
  const trigger=page.getByRole('button',{name:'Build investigation',exact:true});
  await trigger.focus();await expect(trigger).toBeFocused();await page.keyboard.press('Enter');
  const builder=page.getByLabel('Investigation builder',{exact:true});
  await builder.getByRole('button',{name:'Next: Explore depth',exact:true}).click();
  await openTool(page,'Open structure search');
  await expect(builder.getByRole('button',{name:'Return to this step'})).toBeVisible();
  await builder.getByRole('button',{name:'Return to this step'}).click();
  await expect(page.getByLabel('Ocean timestamp',{exact:true})).toBeVisible();
  await page.getByLabel('Study case',{exact:true}).selectOption('pacific-godas-2015-son');
  await expect(builder).toContainText('Direct comparisons are unavailable');
  await expect(builder.getByRole('button',{name:'4 Compare',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Close investigation builder',exact:true}).click();
  await expect(builder).toHaveCount(0);
});

test('support service failure offers retry and never displays invented counts',async({page})=>{
  test.setTimeout(90000);await page.route('**/features/support',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Support temporarily unavailable'}})}));
  await enterWorkspace(page);await openTool(page,'Open structure search');
  await page.getByRole('button',{name:'Show observation support',exact:true}).click();
  await expect(page.getByRole('button',{name:'Retry support',exact:true})).toBeVisible({timeout:20000});
  await expect(page.getByLabel('Structure support counts')).toHaveCount(0);
  await page.unroute('**/features/support');await page.getByRole('button',{name:'Retry support',exact:true}).click();
  await expect(page.getByLabel('Structure support counts')).toBeVisible();
});

test('a newly imported March profile supports a structure and opens the exact accepted pair',async({page})=>{
  test.setTimeout(120000);await enterWorkspace(page);
  await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');
  await page.getByLabel('Ocean timestamp',{exact:true}).selectOption('2');
  await openTool(page,'Open instruments');await page.getByRole('button',{name:'Import observations',exact:true}).click();
  await page.getByText('Formats and genuine example files',{exact:true}).click();
  await page.getByRole('button',{name:'Preview SR1902594_034.nc',exact:true}).click();
  await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
  await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');
  await openTool(page,'Open structure search');
  await page.getByLabel('Structure threshold',{exact:true}).fill('20');
  await page.getByRole('button',{name:'Find regions',exact:true}).click();
  await expect(page.locator('.feature-result-header')).toContainText('20 \u00b0C');
  await page.getByRole('button',{name:'Show observation support',exact:true}).click();
  await expect(page.locator('.support-empty')).toBeVisible();
  await page.getByLabel('Structure support source',{exact:true}).selectOption({label:'Imported: SR1902594_034.nc'});
  await expect(page.getByLabel('Structure support sample',{exact:true})).toBeVisible({timeout:20000});
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export support snapshot',exact:true}).click();
  const file=await download,data=JSON.parse(await readFile((await file.path())!,'utf8')).support;
  expect(data.import_identity.source_sha256).toBe('1368b43fca3d535e3d4745cfcc0c477706ce5e121137ae18e0bf4ac9a613bc2c');
  expect(data.eligible_samples).toBeGreaterThan(0);expect(data.eligible_samples+data.accepted_outside_region).toBe(245);
  await page.getByRole('button',{name:'Open this pair in comparison',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('245 / 1475');
  await expect(page.getByLabel('Selected comparison sample')).toContainText(`Source sample #${data.rows[0].sample_index}`);
  await expect(page.getByLabel('Linked source selection')).toContainText('2024-03-29T02:30:44Z');
});
