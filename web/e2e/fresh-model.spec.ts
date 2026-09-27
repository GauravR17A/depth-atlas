import {test,expect} from '@playwright/test';
import {enterWorkspace,openTool,displaySettings} from './ux-helpers';
import reference from '../../tests/fixtures/p16b-source-reference.json' with {type:'json'};
const caseId='bay-bengal-2024-03';

test('fresh historical input renders with native dates, depths and source value',async({page,browserName})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption(caseId);
 await expect(page.getByLabel('Ocean timestamp')).toHaveCount(1);
 await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
 await page.getByLabel('Ocean timestamp').selectOption('2');
 await page.getByText('Choose coordinates',{exact:true}).click();
 await page.getByLabel('Probe longitude').selectOption('3');
 await page.getByLabel('Probe latitude').selectOption('17');
 await page.getByLabel('Explorer depth').selectOption('19');
 const value=reference.rows.find(r=>r.time_index===2&&r.variable==='temperature')!.samples[1].value!;
 await expect(page.getByLabel('Native model value')).toContainText(value.toFixed(3));
 if(browserName==='chromium')await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','volume');
 await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
 await page.getByRole('button',{name:'Depth slice',exact:true}).click();
 await expect(page.getByRole('img',{name:'Scientific depth slice'})).toBeVisible();
 await page.getByLabel('Explorer depth').selectOption('39');
 await expect(page.getByLabel('Native model value')).toContainText('No value at this depth');
 expect(errors).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('March chlorophyll import remains alongside the correctly dated model',async({page})=>{
 await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption(caseId);
 await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
 await page.getByLabel('Ocean timestamp').selectOption('2');
 await openTool(page,'Open instruments');
 await page.getByRole('button',{name:'Import observations',exact:true}).click();
 await page.getByText('Formats and genuine example files',{exact:true}).click();
 await page.getByRole('button',{name:'Preview SR1902594_034.nc',exact:true}).click();
 await page.getByRole('button',{name:'Add profiles to workspace',exact:true}).click();
 await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');
 await expect(page.getByLabel('Observation and model dates')).toContainText('29 Mar 2024');
 await expect(page.getByLabel('Ocean timestamp')).toHaveValue('2');
 await expect(page.locator('.observation-context')).not.toContainText('outside its time range');
 await expect(page.locator('.instrument-readings')).toContainText('no chlorophyll field');
 await expect(page.getByRole('region',{name:'Ocean model context',exact:true})).toBeVisible();
});

test('heat lab offers a supported case instead of opening missing March data',async({page})=>{
 await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption(caseId);
 await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
 await openTool(page,'Open Heat and Depth Lab');
 await expect(page.getByRole('heading',{name:'Choose a case for Heat & Depth'})).toBeVisible();
 await page.locator('.tool-case-choice .tool-card').first().click();
 await expect(page.getByLabel('Study case',{exact:true})).toHaveValue('bay-bengal-2024-01');
});
