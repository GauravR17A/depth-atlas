import { enterWorkspace, openTool } from './ux-helpers';
import { expect,test } from '@playwright/test';
test.beforeEach(async({page})=>{await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));});
for(const [caseId,label,count] of [['bay-bengal-2024-01','Bay of Bengal','103 / 103'],['arabian-sea-2024-01','Arabian Sea','101 / 101']]){
  test(`guided investigation runs and saves in ${label}`,async({page})=>{
    test.setTimeout(90000);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption(caseId);
    await page.getByRole('button',{name:'Guided case',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Similar at the surface. Different below.'})).toBeVisible();
    await expect(page.getByLabel('Similar surface, different depths')).toContainText('Difference at 100 m: 4.24');
    await page.getByLabel('Compare at depth',{exact:true}).selectOption('0');await expect(page.getByLabel('Similar surface, different depths')).toContainText('Difference at 0 m: 0.01');
    const g=(await(await page.request.get('/api/guided-cases')).json()).columns.find((c:{case_id:string})=>c.case_id===caseId);
    await page.getByRole('button',{name:'Open this column',exact:true}).click();
    await expect(page.getByLabel('Native model value')).toContainText(g.temperature_c[19].toFixed(3));
    await page.getByRole('button',{name:'Next: Compare a measurement',exact:true}).click();
    await expect(page.getByLabel('Eligible comparison count')).toContainText(count,{timeout:25000});
    await expect(page.getByLabel('Study case',{exact:true})).toHaveValue(caseId);
    await page.getByRole('button',{name:'Next: Find warm water',exact:true}).click();
    await expect(page.getByLabel('Structure search results',{exact:true})).toBeVisible({timeout:25000});
    await expect(page.getByLabel('Structure threshold',{exact:true})).toHaveValue('26');
    await expect(page.getByLabel('Maximum search depth',{exact:true})).toHaveValue('300');
    await page.getByRole('button',{name:'Next: Save the evidence',exact:true}).click();
    await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();
    await page.getByLabel('Investigation name',{exact:true}).fill(`${label} guided result`);
    await page.getByRole('button',{name:'Save on this browser',exact:true}).click();
    await expect(page.getByLabel('Selected saved investigation')).toContainText(`${label} guided result`,{timeout:25000});
    await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();
    await expect(page.getByRole('dialog')).not.toBeVisible({timeout:25000});
    await expect(page.locator('.replay-notice')).toContainText('Recalculation matched');
    expect(errors).toEqual([]);
  });
}
test('compatible case changes retain tools and salinity range follows the source case',async({page})=>{
  await enterWorkspace(page);await page.getByLabel('Study case',{exact:true}).selectOption('arabian-sea-2024-01');
  await page.getByLabel('Variable',{exact:true}).selectOption('salinity');
  await page.locator('.ocean-settings summary').click();await expect(page.getByLabel('Colour maximum',{exact:true})).toHaveValue('38');
  await openTool(page,'Compare');await page.getByLabel('Study case',{exact:true}).selectOption('bay-bengal-2024-01');await expect(page.getByLabel('Eligible comparison count')).toBeVisible();await openTool(page,'Ocean explorer');
  await expect(page.getByLabel('Scientific ocean explorer')).toBeVisible();
  await page.locator('.ocean-settings summary').click();await expect(page.getByLabel('Colour maximum',{exact:true})).toHaveValue('36');
  await page.getByLabel('Study case',{exact:true}).selectOption('pacific-godas-2013-son');
  await expect(page.getByLabel('Scientific ocean explorer')).toBeVisible();
  await expect(page.getByLabel('Variable',{exact:true})).toHaveValue('temperature');
  await expect(page.getByRole('button',{name:'Guided case',exact:true})).toHaveCount(0);
  await openTool(page,'Compare');await expect(page.getByRole('heading',{name:'Choose a case for Model comparison'})).toBeVisible();
});
test('guide fits narrow layouts, uses keyboard controls and respects reduced motion',async({page})=>{
  test.setTimeout(60000);await page.setViewportSize({width:320,height:800});await page.emulateMedia({reducedMotion:'reduce'});await enterWorkspace(page);
  const start=page.getByRole('button',{name:'Guided case',exact:true});await start.focus();await page.keyboard.press('Enter');
  await expect(page.getByLabel('Compare at depth',{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.getByRole('button',{name:'Open this column',exact:true}).click();await expect(page.getByRole('button',{name:'Play ocean playback',exact:true})).toBeDisabled();
  await page.setViewportSize({width:768,height:1000});await page.addStyleTag({content:'html{font-size:200% !important}'});
  await page.getByRole('button',{name:'Restart guide',exact:true}).click();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.getByRole('button',{name:'Exit guide',exact:true}).click();await expect(start).toBeVisible();await expect(start).toBeFocused();
});
test('unavailable guide can retry while the scientific explorer stays available',async({page})=>{
  await page.route('**/api/guided-cases',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'The guided example is temporarily unavailable.'}})}));
  await enterWorkspace(page);await page.getByRole('button',{name:'Guided case',exact:true}).click();await expect(page.getByRole('alert')).toContainText('temporarily unavailable');
  await expect(page.getByLabel('Native model value')).toContainText('22.303');await page.unroute('**/api/guided-cases');await page.getByRole('button',{name:'Retry guided example'}).click();await expect(page.getByLabel('Compare at depth',{exact:true})).toBeVisible();
});
test('pending structure calculation can be cancelled and then rerun',async({page})=>{
  test.setTimeout(60000);await page.route('**/features/search',async route=>{await new Promise(resolve=>setTimeout(resolve,4000));await route.continue().catch(()=>{});});
  await enterWorkspace(page);await openTool(page,'Open structure search');await page.getByRole('button',{name:'Cancel calculation',exact:true}).click();
  await expect(page.getByText('Calculation cancelled.',{exact:false})).toBeVisible();await expect(page.getByRole('button',{name:'Find regions',exact:true})).toBeEnabled();
  await page.unroute('**/features/search');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.getByLabel('Structure search results',{exact:true})).toBeVisible({timeout:25000});
});
