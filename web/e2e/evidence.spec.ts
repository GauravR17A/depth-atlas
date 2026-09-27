import { enterWorkspace, openTool } from './ux-helpers';
import {expect,test,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const library=JSON.parse(readFileSync(resolve(import.meta.dirname,'../../casepacks/instruments/index.json'),'utf8'));
const id=(platform:string)=>library.profiles.find((p:{platform:string})=>p.platform===platform).id;
async function open(page:Page,time='1'){
  await enterWorkspace(page);await openTool(page,'Compare');
  await page.getByLabel('Comparison model snapshot').selectOption(time);
  await page.getByLabel('Comparison profile').selectOption(id('1902669'));
  await expect(page.getByLabel('Eligible comparison count')).toBeVisible();
}

test('empty initial snapshot offers an explicit useful comparison without silently changing time',async({page})=>{
  await open(page,'0');await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 103');
  await expect(page.getByRole('heading',{name:'No eligible pairs for this selection'})).toBeVisible();
  await page.getByRole('button',{name:'Find a useful comparison',exact:true}).click();
  await expect(page.getByLabel('Comparison model snapshot')).toHaveValue('0');
  const offer=page.getByRole('button',{name:/Use .*snapshot/});await expect(offer).toBeVisible();await offer.click();
  await expect(page.getByLabel('Eligible comparison count')).not.toContainText('0 /');
  await expect(page.getByLabel('Comparison model snapshot')).not.toHaveValue('0');
  await expect(page.locator('.evidence-notice')).toContainText('Opened the suggested');
});

test('source-derived comparison values, synchronized cursor and matched model navigation',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await open(page);
  await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
  const sample=page.getByLabel('Selected comparison sample');
  await expect(sample).toContainText('28.153');await expect(sample).toContainText('28.001');await expect(sample).toContainText('-0.152');
  await expect(page.getByLabel('Selected sample metrics')).toContainText('0.251');
  await page.getByLabel('Comparison sample',{exact:true}).focus();await page.getByLabel('Comparison sample',{exact:true}).press('ArrowDown');
  await expect(sample).toContainText('Source sample #1');
  const cursors=page.locator('.evidence-chart svg line[stroke="#f2e4bb"]');await expect(cursors).toHaveCount(2);
  expect(await cursors.nth(0).getAttribute('y1')).toBe(await cursors.nth(1).getAttribute('y1'));
  await page.getByLabel('Comparison sample',{exact:true}).selectOption('0');
  await page.getByRole('button',{name:'View matched model column',exact:true}).click();
  await expect(page.getByLabel('Ocean timestamp')).toHaveValue('1');await expect(page.getByLabel('Explorer depth')).toHaveValue('0');
  await expect(page.getByLabel('Linked model depth',{exact:true})).toContainText('interpolated between 0 and 2 m');
  await expect(page.getByLabel('Native model value')).toContainText('27.999');
  await openTool(page,'Compare');
  await page.getByLabel('Compared variable').selectOption('salinity');
  await expect(sample).toContainText('33.767');await expect(sample).toContainText('32.832');await expect(sample).toContainText('+0.935');
  expect(errors).toEqual([]);
});

test('coverage and sensitivity use the same accepted counts and restore an in-memory reference',async({page})=>{
  await open(page);await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
  await page.getByRole('button',{name:'Keep this result as reference',exact:true}).click();
  await page.getByRole('button',{name:'Matching rules',exact:true}).click();await page.getByLabel('Matching time window').fill('2');
  await page.getByRole('button',{name:'Apply matching rules',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 103');
  await expect(page.getByLabel('Sensitivity count change')).toContainText('-103 eligible pairs');
  await page.getByRole('button',{name:'Evidence coverage',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Where eligible observations exist'}).locator('..')).toContainText('0 of 13');
  await expect(page.locator('.evidence-depth-coverage svg g[aria-label]')).toHaveCount(0);
  await page.getByRole('button',{name:'Profile comparison',exact:true}).click();await page.getByRole('button',{name:'Restore reference settings',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
  await page.getByRole('button',{name:'Evidence coverage',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Where eligible observations exist'}).locator('..')).toContainText('2 of 13 library profiles contribute 206 pairs');
  await expect(page.locator('.evidence-depth-coverage svg line[stroke="#a1e1cf"], .evidence-depth-coverage svg line[stroke="#ffe3ae"]')).toHaveCount(206);
  const pin=page.getByRole('button',{name:/Argo 4903775.*103 eligible pairs/});await pin.focus();await pin.press('Enter');
  await expect(page.getByLabel('Comparison profile')).toHaveValue(id('4903775'));
  await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
});

test('source-review hold and out-of-domain observations cannot produce a residual',async({page})=>{
  await open(page);await page.getByLabel('Comparison profile').selectOption(id('5907083'));
  await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 102');
  await expect(page.getByLabel('Selected comparison sample')).toContainText('Source held for review');
  await expect(page.getByRole('button',{name:'View matched model column',exact:true})).toBeDisabled();
  await page.getByLabel('Compared variable').selectOption('salinity');await page.getByLabel('Comparison profile').selectOption(id('35MF103_1'));
  await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 48');
  await expect(page.getByLabel('Selected comparison sample')).toContainText('Outside this model domain');
  await expect(page.getByLabel('Selected comparison sample')).toContainText('Not calculated');
});

test('large-residual discovery is explicit and restricted to the current eligible profiles',async({page})=>{
  await open(page);await page.getByLabel('Comparison discovery order').selectOption('residual');
  await page.getByRole('button',{name:'Find a useful comparison',exact:true}).click();
  await expect(page.getByLabel('Comparison profile')).toHaveValue(id('4903775'));
  await expect(page.getByLabel('Comparison model snapshot')).toHaveValue('1');
  await expect(page.locator('.evidence-notice')).toContainText('largest absolute residual');
  await page.getByRole('button',{name:'Matching rules',exact:true}).click();await page.getByLabel('Matching depth gap').fill('25');
  await page.getByLabel('Comparison QC policy').selectOption('good');await page.getByRole('button',{name:'Apply matching rules',exact:true}).click();
  await expect(page.getByLabel('Eligible comparison count')).toContainText('25 / 103');
  await page.getByRole('button',{name:'Evidence coverage',exact:true}).click();
  await expect(page.locator('.evidence-section-heading')).toContainText('50 pairs');
});

test('inconsistent comparison payload is rejected and a verified retry recovers',async({page})=>{
  let corrupt=true;
  await page.route('**/evidence/profiles/**',async route=>{const response=await route.fetch();const json=await response.json();if(corrupt)json.matched_count+=1;await route.fulfill({response,json});});
  await enterWorkspace(page);await openTool(page,'Compare');
  await expect(page.getByRole('alert').filter({hasText:'could not be verified'})).toBeVisible();
  await expect(page.getByLabel('Eligible comparison count')).toHaveCount(0);
  corrupt=false;await page.getByRole('button',{name:/Retry comparison/}).click();
  await expect(page.getByLabel('Eligible comparison count')).toBeVisible();
});
