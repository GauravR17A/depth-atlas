import { test, expect } from '@playwright/test';
import { enterWorkspace, openTool, displaySettings, extraView } from './ux-helpers';

test('tutorial welcome is skippable, keyboard accessible and reopens from Guide',async({page})=>{
  await page.goto('/');const intro=page.getByRole('dialog');await expect(intro).toBeVisible();
  await expect(page.getByRole('button',{name:'Start Basic tutorial',exact:true})).toBeFocused();
  await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(intro).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Quick guide',exact:true})).toBeFocused();
  await page.getByRole('button',{name:'Quick guide',exact:true}).click();await expect(page.getByRole('heading',{name:'See it happen. Then try it.'})).toBeVisible();
  for(let i=0;i<8;i++){await page.keyboard.press('Tab');expect(await page.evaluate(()=>Boolean(document.activeElement?.closest('.learning-welcome')))).toBe(true);}
  await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Quick guide',exact:true})).toBeFocused();
});

test('tutorial choice fits narrow and short screens without scrolling',async({page})=>{
  for(const size of [{width:320,height:568},{width:844,height:390}]){
    await page.setViewportSize(size);await page.goto('/');const dialog=page.locator('.learning-welcome');await expect(dialog).toBeVisible();
    expect(await dialog.evaluate(el=>{const r=el.getBoundingClientRect();return el.scrollHeight<=el.clientHeight+1&&el.scrollWidth<=el.clientWidth+1&&r.top>=0&&r.bottom<=innerHeight+1;})).toBe(true);
    await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await expect(dialog).toHaveCount(0);
  }
});

test('opening prioritizes a real scene and only essential navigation',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await expect(page.locator('.navigation-rail')).toHaveCount(0);await expect(page.locator('.controls-panel')).toHaveCount(0);await expect(page.locator('.ocean-context-toggle')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Tools',exact:true})).toHaveCount(1);
  await expect(page.locator('.ocean-settings')).not.toHaveAttribute('open');await expect(page.getByLabel('Graphics quality')).not.toBeVisible();
  await expect(page.getByRole('button',{name:'Cutaway',exact:true})).toHaveAttribute('aria-pressed','false');
  const viewport=await page.locator('.ocean-viewport').boundingBox();expect(viewport!.width).toBeGreaterThan(250);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await expect(page.locator('.ocean-legend')).toContainText('Temperature');await expect(page.locator('.ocean-heading')).toContainText('2024');
});

test('every tool remains reachable and a return preserves the current ocean selection',async({page})=>{
  test.setTimeout(90000);await enterWorkspace(page);await page.getByLabel('Explorer depth').selectOption('27');await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
  const value=await page.getByLabel('Native model value').innerText();
  const tools=[['Open instruments','Instruments'],['Compare','Model comparison'],['Open structure search','Find structures'],['Open Drift Lab','Drift Lab'],['Open Heat and Depth Lab','Heat & Depth'],['Open Virtual Expedition','Virtual Expedition'],['Open feature evolution','Feature evolution'],['Open observation blackout','Observation blackout'],['Open wider ocean coverage','More regions'],['Geographic context','Data globe']];
  for(const [button,title] of tools){await openTool(page,button);await expect(page.locator('.current-activity')).toHaveText(title);await expect(page.locator('.tool-menu')).toHaveCount(0);}
  await openTool(page,'Ocean explorer');await expect(page.getByLabel('Explorer depth')).toHaveValue('27');await expect(page.getByLabel('Native model value')).toHaveText(value,{useInnerText:true});
  await openTool(page,'Open Climate Event Lab');await expect(page.locator('.current-activity')).toHaveText('Climate Event Lab');
});

test('changing a compatible case keeps the chosen lab and Pacific offers an explicit source choice',async({page})=>{
  await enterWorkspace(page);await openTool(page,'Open Drift Lab');
  await page.getByLabel('Study case',{exact:true}).selectOption('arabian-sea-2024-01');await expect(page.getByRole('region',{name:'Drift Lab',exact:true})).toBeVisible();
  await openTool(page,'Open Climate Event Lab');await expect(page.locator('.climate-workspace')).toBeVisible();await expect(page.getByRole('button',{name:'Save climate investigation',exact:true})).toBeEnabled({timeout:20000});
  await openTool(page,'Open Drift Lab');await expect(page.getByRole('heading',{name:'Choose a case for Drift Lab'})).toBeVisible();
  await page.getByRole('button',{name:/Bay of Bengal/}).click();await expect(page.getByRole('region',{name:'Drift Lab',exact:true})).toBeVisible();await expect(page.getByLabel('Study case',{exact:true})).toHaveValue('bay-bengal-2024-01');
});

test('advanced display, extra views and instrument overlays retain real values',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await extraView(page,'Isosurface');await expect(page.getByLabel('Isosurface value')).toBeVisible();await page.getByRole('button',{name:'More views',exact:true}).click();await page.keyboard.press('Escape');await expect(page.locator('.extra-views')).toHaveCount(0);await expect(page.getByRole('button',{name:'More views',exact:true})).toBeFocused();
  await displaySettings(page);await expect(page.getByLabel('Instrument locations',{exact:true})).not.toBeChecked();await page.getByLabel('Instrument locations',{exact:true}).check();
  await page.getByLabel('Colour palette').selectOption('mono');await page.getByLabel('Layer opacity').fill('0.5');await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByLabel('Graphics quality').selectOption('basic');await expect(page.getByRole('img',{name:'Scientific depth section'})).toBeVisible();
});

test('sources open on demand and dataset details return focus without stacked dialogs',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByRole('button',{name:'Sources',exact:true}).click();await expect(page.getByRole('dialog',{name:'Sources and observations'})).toBeVisible();
  await expect(page.locator('.source-drawer')).toContainText('HYCOM');await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Sources',exact:true})).toBeFocused();
  await page.getByRole('button',{name:'Case details',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(1);await expect(page.getByRole('dialog')).toContainText('not live 2026 data');await page.getByRole('button',{name:'Close dataset inspector',exact:true}).click();await expect(page.getByRole('button',{name:'Case details',exact:true})).toBeFocused();
});

test('guided case is optional and still applies the verified teaching pair',async({page})=>{
  await enterWorkspace(page);await expect(page.getByRole('region',{name:'Guided investigation',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Guided case',exact:true}).click();await expect(page.getByLabel('Similar surface, different depths')).toContainText('Difference at 100 m: 4.24');
  await page.getByRole('button',{name:'Open this column',exact:true}).click();await expect(page.getByRole('button',{name:'Cutaway',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'Exit guide',exact:true}).click();await expect(page.getByRole('region',{name:'Guided investigation',exact:true})).toHaveCount(0);
});

test('save and exact replay survive the new navigation and introduction',async({page})=>{
  test.setTimeout(60000);await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();await page.getByLabel('Explorer depth').selectOption('27');await expect(page.getByLabel('Native model value')).not.toContainText('Loading');const value=await page.getByLabel('Native model value').innerText();
  await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name',{exact:true}).fill('UX depth check');await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByLabel('Selected saved investigation')).toContainText('UX depth check',{timeout:25000});
  await page.reload();await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();await openTool(page,'Open wider ocean coverage');await page.getByRole('button',{name:'Open saved investigations'}).click();await page.getByRole('button',{name:/UX depth check Ocean view/}).click();await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();
  await expect(page.locator('.replay-notice')).toContainText('Recalculation matched',{timeout:25000});await expect(page.locator('.current-activity')).toHaveText('Ocean Explorer');await expect(page.getByLabel('Native model value')).toHaveText(value,{useInnerText:true});await expect(page.getByLabel('Explorer depth')).toHaveValue('27');
});

test('reduced motion and enlarged text retain functional introduction and controls',async({page})=>{
  await page.setViewportSize({width:768,height:900});await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');await page.addStyleTag({content:'html{font-size:200% !important}'});
  expect(await page.locator('.learning-welcome').evaluate(e=>e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth+1)).toBe(true);await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
  await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play ocean playback',exact:true})).toBeDisabled();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('simplified drift setup still calculates real trajectories and keeps exact coordinates available',async({page})=>{
  test.setTimeout(60000);await enterWorkspace(page);await openTool(page,'Open Drift Lab');
  await expect(page.getByLabel('Drift release west',{exact:true})).not.toBeVisible();await page.getByText('Release coordinates',{exact:true}).click();await expect(page.getByLabel('Drift release west',{exact:true})).toBeVisible();
  await page.getByText('Release coordinates',{exact:true}).click();await page.getByLabel('Drift particle count',{exact:true}).fill('4');await page.getByLabel('Drift duration hours',{exact:true}).fill('1');
  const response=page.waitForResponse(r=>r.url().endsWith('/drift/stream')&&r.request().method()==='POST');await page.getByRole('button',{name:'Calculate run A',exact:true}).click();const result=await response;expect(result.ok()).toBe(true);
  await expect(page.getByLabel('Applied drift run A',{exact:true})).toContainText('4 simulated particles',{timeout:30000});await expect(page.getByLabel('Applied drift run A',{exact:true})).toContainText('2024-01-07');await expect(page.getByRole('button',{name:'Play paths',exact:true})).toBeVisible();
});

test('shared investigations open directly without two competing introductions',async({page})=>{
  await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name',{exact:true}).fill('Shared UX check');await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByLabel('Selected saved investigation')).toContainText('Shared UX check',{timeout:25000});
  await page.getByRole('button',{name:'Copy replay link',exact:true}).click();const link=await page.getByLabel('Replay link',{exact:true}).inputValue();await page.goto(link);await expect(page.getByLabel('Selected saved investigation')).toContainText('Shared UX check');await expect(page.locator('.learning-welcome')).toHaveCount(0);await expect(page.getByRole('dialog')).toHaveCount(1);
});

test('a late climate calculation cannot replace the case in another tool',async({page})=>{
  let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
  await page.route('**/api/climate/analyse',async route=>{await gate;await route.continue();});
  await enterWorkspace(page);await openTool(page,'Open Climate Event Lab');await expect(page.getByRole('button',{name:'Cancel comparison',exact:true})).toBeVisible();
  await openTool(page,'Open Drift Lab');await expect(page.getByLabel('Study case',{exact:true})).toHaveValue('bay-bengal-2024-01');
  const response=page.waitForResponse(r=>r.url().endsWith('/api/climate/analyse'));release();await response;
  await expect(page.getByLabel('Study case',{exact:true})).toHaveValue('bay-bengal-2024-01');await expect(page.getByRole('region',{name:'Drift Lab',exact:true})).toBeVisible();
  await openTool(page,'Open Climate Event Lab');await expect(page.getByRole('button',{name:'Save climate investigation',exact:true})).toBeEnabled();await openTool(page,'Open Drift Lab');await expect(page.getByRole('heading',{name:'Choose a case for Drift Lab'})).toBeVisible();
});
