import {expect,test} from '@playwright/test';
async function globe(page:import('@playwright/test').Page){await page.goto('/');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(page.getByRole('region',{name:'Ocean data globe'})).toBeVisible();}
test('globe is an explicit persistent view when late model metadata arrives',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(r=>release=r);await page.route('**/api/cases/bay-bengal-2024-01',async route=>{const response=await route.fetch();await gate;try{await route.fulfill({response});}catch{}});
 await globe(page);await expect(page.getByRole('region',{name:'Ocean model context'})).toBeHidden();release();await expect(page.getByRole('region',{name:'Ocean model context',includeHidden:true})).toHaveCount(1);
 await expect(page.getByRole('region',{name:'Ocean data globe'})).toBeVisible();await expect(page.getByRole('region',{name:'Ocean model context'})).toBeHidden();
 await page.getByRole('button',{name:'Open this 3D ocean'}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');await expect(page.locator('#ocean-workspace')).toBeFocused();await expect(page.getByRole('region',{name:'Ocean data globe'})).toHaveCount(0);
 await page.getByRole('button',{name:'Find data on globe'}).click();await expect(page.getByRole('region',{name:'Ocean data globe'})).toBeVisible();
});
test('globe selects a real Pacific source, supports keyboard rotation and opens the chosen model',async({page})=>{
 await globe(page);await page.getByLabel('Globe model case').selectOption('pacific-godas-2022-son');await expect(page.getByLabel('Located data details')).toContainText('2022');
 const before=await page.locator('.data-globe').innerHTML();await page.getByRole('button',{name:'Rotate globe east'}).focus();await page.keyboard.press('Enter');expect(await page.locator('.data-globe').innerHTML()).not.toBe(before);
 await page.getByRole('button',{name:'Map',exact:true}).click();await page.getByRole('button',{name:'Open this 3D ocean'}).click();await expect(page.getByLabel('Study case')).toHaveValue('pacific-godas-2022-son');await expect(page.getByLabel('Native model value')).toBeVisible();
});
test('instrument locations keep source dates and profiles outside model coverage inspectable',async({page})=>{
 await globe(page);await page.getByRole('button',{name:'Instrument locations',exact:true}).click();const choices=page.getByLabel('Globe observation');await expect(choices.locator('option')).not.toHaveCount(0);
 const id=await choices.locator('option').filter({hasText:'Glider'}).first().getAttribute('value');await choices.selectOption(id!);await expect(page.getByLabel('Located data details')).toContainText('No loaded model case covers this marker');
 await page.getByRole('button',{name:'Open measured profile'}).click();await expect(page.getByLabel('Instrument profile')).toHaveValue(id!);await expect(page.getByLabel('Observed sample value')).toBeVisible();
});
test('source-checked chlorophyll location opens its original profile beside the matching March context',async({page})=>{
 test.setTimeout(90000);await globe(page);await page.getByRole('button',{name:'Chlorophyll observations',exact:true}).click();await page.getByRole('button',{name:'Load public chlorophyll profile'}).click();
 await expect(page.getByLabel('Globe observation')).toBeVisible({timeout:50000});await expect(page.getByLabel('Located data details')).toContainText('2024-03-29');await expect(page.getByLabel('Located data details')).toContainText('area and timestamp overlap');
 await expect(page.getByLabel('Located data details')).toContainText('do not map bloom extent');await page.getByRole('button',{name:'Open measured profile'}).click();
 await expect(page.getByLabel('Study case')).toHaveValue('bay-bengal-2024-03');await expect(page.getByLabel('Profile variable')).toHaveValue('chlorophyll');await expect(page.getByLabel('Observed sample value')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('failed chlorophyll loading is explicit, cancelable and leaves original locations available',async({page})=>{
 await globe(page);await page.route('**/api/instruments/examples/SR1902594_034.nc',route=>route.abort('connectionreset'));
 await page.getByRole('button',{name:'Chlorophyll observations',exact:true}).click();await page.getByRole('button',{name:'Load public chlorophyll profile'}).click();await expect(page.locator('.globe-error')).toBeVisible();
 await page.getByRole('button',{name:'Instrument locations',exact:true}).click();await expect(page.getByLabel('Globe observation')).toBeVisible();
});

test('the header opens the selected globe case rather than the previous workspace case',async({page})=>{
 await globe(page);await page.getByLabel('Globe model case').selectOption('arabian-sea-2024-01');await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();
 await expect(page.getByLabel('Study case')).toHaveValue('arabian-sea-2024-01');await expect(page.getByLabel('Native model value')).toBeVisible();await expect(page.locator('#ocean-workspace')).toBeFocused();
});
