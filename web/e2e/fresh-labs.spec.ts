import {test,expect} from '@playwright/test';
import {enterWorkspace,openTool} from './ux-helpers';

for(const [tool,result] of [
 ['Open structure search','Structure search results'],
 ['Open observation blackout','Applied observation blackout'],
])test(`March case uses existing ${tool} calculation`,async({page})=>{
 test.setTimeout(60000);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');
 await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
 await openTool(page,tool);
 await expect(page.getByLabel(result,{exact:true})).toBeVisible({timeout:30000});
 expect(errors).toEqual([]);
});

test('March currents support a bounded historical particle calculation',async({page})=>{
 test.setTimeout(60000);await enterWorkspace(page);
 await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');
 await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
 await openTool(page,'Open Drift Lab');
 await page.getByLabel('Drift particle count',{exact:true}).fill('6');
 await page.getByLabel('Drift duration hours',{exact:true}).fill('6');
 await page.getByRole('button',{name:'Calculate run A',exact:true}).click();
 await expect(page.getByLabel('Applied drift run A',{exact:true})).toBeVisible({timeout:30000});
 await expect(page.locator('.drift-map-top')).toContainText('2024-03-28');
});

for(const [tool,title] of [['Open Virtual Expedition','Virtual Expedition'],['Open feature evolution','Feature evolution']])test(`March ${title} offers a checked case`,async({page})=>{
 await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-03');
 await expect(page.getByLabel('Ocean timestamp').locator('option')).toHaveCount(5);
 await openTool(page,tool);await expect(page.getByRole('heading',{name:`Choose a case for ${title}`,exact:true})).toBeVisible();
 await page.locator('.tool-case-choice .tool-card').first().click();
 await expect(page.getByLabel('Study case',{exact:true})).toHaveValue('bay-bengal-2024-01');
});
