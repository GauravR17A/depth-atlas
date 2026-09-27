import { displaySettings, enterWorkspace, openTool, extraView } from './ux-helpers';
import {expect,test} from '@playwright/test';
import reference from '../../tests/fixtures/p06-source-samples.json' with {type:'json'};

test('registered derived field uses existing scientific views and original source values',async({page,browserName})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await enterWorkspace(page);await page.getByLabel('Variable',{exact:true}).selectOption('horizontal_kinetic_energy');
  await expect(page.getByRole('heading',{name:'Horizontal kinetic energy beneath the surface'})).toBeVisible();
  await expect(page.locator('.ocean-notice')).toContainText('not eddy kinetic energy');
  await page.getByLabel('Ocean timestamp').selectOption('1');
  await page.getByText('Choose coordinates',{exact:true}).click();
  await page.getByLabel('Probe longitude').selectOption('30');
  await page.getByLabel('Probe latitude').selectOption('38');
  const expected=reference.rows.find(r=>r.time_index===1&&r.depth_index===19&&r.x===30&&r.y===38)!.expected!;
  await expect(page.getByLabel('Native model value')).toContainText(expected.toFixed(3));
  await expect(page.getByLabel('Native model value')).toContainText('m²/s²');
  if(browserName==='chromium'){
    await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','volume');
    await page.getByRole('button',{name:'Cutaway',exact:true}).click();
    await expect(page.getByRole('button',{name:'Cutaway',exact:true})).toHaveAttribute('aria-pressed','true');
    await extraView(page,'Isosurface');
    await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered','iso');
  }
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();
  await expect(page.getByRole('img',{name:'Scientific depth slice'})).toBeVisible();
  await page.getByLabel('Explorer depth').selectOption('39');
  await expect(page.getByLabel('Native model value')).toContainText('No value at this depth');
  await openTool(page,'Compare');
  await expect(page.getByLabel('Compared variable',{exact:true})).toHaveValue('temperature');
  await openTool(page,'Ocean explorer');
  await expect(page.getByLabel('Variable',{exact:true})).toHaveValue('temperature');
  expect(errors).toEqual([]);
});

test('data access exposes usable contracts and honest service availability',async({page,request})=>{
  await enterWorkspace(page);await page.getByRole('link',{name:'Use the data',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Use the data',exact:true})).toBeVisible();
  await expect(page.locator('main')).toContainText('no public address');
  await expect(page.getByRole('link',{name:'Bay of Bengal CF NetCDF · 27.6 MB'})).toHaveAttribute('href','/data/bay-bengal-2024-01.nc');
  const metadata=await request.get('/api/data-access');expect(metadata.status()).toBe(200);
  const m=await metadata.json();expect(m.file.shape).toEqual([7,40,76,63]);expect(m.standards.public_url).toBeNull();
  await page.getByRole('link',{name:'Back to workspace',exact:true}).click();
  await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
  await expect(page.getByLabel('Globe model case')).toBeVisible();
  await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();
  await expect(page.getByLabel('Variable',{exact:true})).toBeVisible();
});

test('data access can be read without JavaScript',async({browser,baseURL})=>{
  const context=await browser.newContext({javaScriptEnabled:false,baseURL});const page=await context.newPage();
  await page.goto('/data-access');await expect(page.getByRole('heading',{name:'Download the native grid'})).toBeVisible();
  await expect(page.getByRole('link',{name:'API reference'})).toHaveAttribute('href','/api/docs');
  await context.close();
});
