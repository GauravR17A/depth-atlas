import { dismissIntroduction, enterWorkspace, openTool } from './ux-helpers';
import { expect,test,type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
const version=JSON.parse(readFileSync(new URL('../../api/release.json',import.meta.url),'utf8')).version;

test.beforeEach(async({page})=>{await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));});
async function save(page:Page,title:string){await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByLabel('Investigation name',{exact:true}).fill(title);await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByLabel('Selected saved investigation')).toContainText(title,{timeout:25000});await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toBeVisible();}
async function file(page:Page){const p=page.waitForEvent('download');await page.getByRole('button',{name:'Investigation JSON',exact:true}).click();const d=await p;return JSON.parse(await readFile((await d.path())!,'utf8'));}
async function reopen(page:Page){await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();await expect(page.getByRole('dialog')).not.toBeVisible({timeout:30000});await expect(page.locator('.replay-notice')).toContainText('Recalculation matched');}

test('ocean save survives reload and restores exact native point and display settings',async({page})=>{
  test.setTimeout(60000);await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByRole('button',{name:'Depth slice',exact:true}).click();await page.getByLabel('Explorer depth',{exact:true}).selectOption('27');await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
  await save(page,'Deep source point');const record=await file(page);expect(record.replay.recipe.depth_index).toBe(27);expect(record.replay.recipe.point[2]).toBe(27);
  await page.reload();await dismissIntroduction(page);await page.getByRole('button',{name:'Open saved investigations'}).click();await page.getByRole('button',{name:/Deep source point Ocean view/}).click();await reopen(page);
  await expect(page.getByLabel('Explorer depth',{exact:true})).toHaveValue('27');await expect(page.getByRole('button',{name:'Depth slice',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByLabel('Native model value')).toContainText(record.results[0].output.selected_values[0].toFixed(3));
});

test('comparison saves both matching policies and replays sensitivity in a fresh context',async({page,browser})=>{
  test.setTimeout(90000);await enterWorkspace(page);await openTool(page,'Compare');await page.getByLabel('Comparison model snapshot').selectOption('1');await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
  await page.getByRole('button',{name:'Keep this result as reference'}).click();await page.getByRole('button',{name:'Matching rules',exact:true}).click();await page.getByLabel('Matching time window').fill('1');await page.getByRole('button',{name:'Apply matching rules'}).click();await expect(page.getByLabel('Eligible comparison count')).toContainText('0 / 103');
  await save(page,'Time-window sensitivity');const record=await file(page);expect(record.replay.recipe.settings.time_window_hours).toBe(1);expect(record.replay.recipe.baseline.settings.time_window_hours).toBe(6);
  const ctx=await browser.newContext(),other=await ctx.newPage();await enterWorkspace(other,page.url());await other.getByRole('button',{name:'Open saved investigations'}).click();await other.getByLabel('Open investigation file',{exact:true}).setInputFiles({name:'investigation.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(record))});await expect(other.getByLabel('Selected saved investigation')).toContainText('Time-window sensitivity');await reopen(other);
  await expect(other.getByLabel('Eligible comparison count')).toContainText('0 / 103');await expect(other.locator('.evidence-baseline')).toContainText('103 eligible pairs');await other.getByRole('button',{name:'Restore reference settings'}).click();await expect(other.getByLabel('Eligible comparison count')).toContainText('103 / 103');await ctx.close();
});

test('structure section and exact selected sample replay through a stateless share link',async({page,browser})=>{
  test.setTimeout(90000);await enterWorkspace(page);await openTool(page,'Open structure search');await expect(page.getByLabel('Structure search results',{exact:true})).toBeVisible({timeout:20000});
  await page.getByLabel('Structure model snapshot').selectOption('1');await page.getByRole('button',{name:'Find regions',exact:true}).click();await expect(page.locator('.feature-result-header')).toContainText('12:00');await page.getByRole('button',{name:'Section through selected region'}).click();await expect(page.getByLabel('Section source value')).toBeVisible();await page.getByLabel('Section station',{exact:true}).selectOption('23');await page.getByLabel('Section native depth',{exact:true}).selectOption('7');await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');
  const value=await page.getByLabel('Section source value').innerText();await save(page,'Warm-water section');const record=await file(page);expect(record.replay.recipe.section_pick).toBe(7*81+23);
  await page.getByRole('button',{name:'Copy replay link',exact:true}).click();const link=await page.getByLabel('Replay link',{exact:true}).inputValue();expect(link.length).toBeLessThan(16000);
  const ctx=await browser.newContext(),other=await ctx.newPage();await other.goto(link);await expect(other.getByLabel('Selected saved investigation')).toContainText('Warm-water section');await reopen(other);
  await expect(other.getByLabel('Structure graphics',{exact:true})).toHaveValue('basic');await expect(other.getByLabel('Section station',{exact:true})).toHaveValue('23');await expect(other.getByLabel('Section native depth',{exact:true})).toHaveValue('7');await expect(other.getByLabel('Section source value')).toHaveText(value,{useInnerText:true});await ctx.close();
});

test('source observation selection and excluded-values preference survive reopening',async({page})=>{
  test.setTimeout(60000);await enterWorkspace(page);await openTool(page,'Open instruments');await expect(page.getByLabel('Observed sample value')).toBeVisible();await page.getByLabel('Observation sample',{exact:true}).selectOption('6');await page.getByLabel('Show excluded values').check();const before=await page.getByLabel('Observed sample value').innerText();await save(page,'Observed profile');await reopen(page);await expect(page.getByLabel('Observation sample',{exact:true})).toHaveValue('6');await expect(page.getByLabel('Show excluded values')).toBeChecked();await expect(page.getByLabel('Observed sample value')).toHaveText(before,{useInnerText:true});
});

test('altered file and unavailable replay keep the current workspace intact',async({page})=>{
  test.setTimeout(60000);await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await save(page,'Integrity example');const record=await file(page);record.results[0].output.selected_values[0]=999;
  await page.getByLabel('Open investigation file',{exact:true}).setInputFiles({name:'changed.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(record))});await expect(page.getByRole('alert')).toContainText('altered');
  await page.route('**/api/investigations/replay',async route=>route.fulfill({status:422,headers:{'X-Ocean-App-Version':version},contentType:'application/json',body:JSON.stringify({error:{code:'source_mismatch',message:'The required source version is unavailable. No replacement source or cached result has been substituted.'}})}));await page.getByRole('button',{name:'Recalculate and reopen',exact:true}).click();await expect(page.getByRole('alert')).toContainText('source version is unavailable');await page.getByRole('button',{name:'Close saved investigations'}).click();await expect(page.getByLabel('Native model value')).toContainText('22.303');
});

test('storage denial keeps the portable file available and does not claim a save',async({page})=>{
  test.setTimeout(60000);await page.addInitScript(()=>{IDBFactory.prototype.open=function(){throw new DOMException('Denied','SecurityError');};});await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await page.getByRole('button',{name:'Save investigation',exact:true}).filter({visible:true}).click();await page.getByRole('button',{name:'Save on this browser',exact:true}).click();await expect(page.getByLabel('Selected saved investigation')).toBeVisible({timeout:25000});await expect(page.getByRole('alert')).toBeVisible();const record=await file(page);expect(record.kind).toBe('ocean_investigation');await expect(page.getByRole('status').filter({hasText:'Saved on this browser.'})).toHaveCount(0);
});

test('report, numerical CSV and evidence ZIP export after recalculation',async({page})=>{
  test.setTimeout(90000);await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await save(page,'Export evidence');
  for(const [name,pattern] of [['Readable report','<!doctype html>'],['Numerical CSV','temperature ['],['Complete evidence ZIP','PK']] as const){const promise=page.waitForEvent('download');await page.getByRole('button',{name,exact:true}).click();const d=await promise,bytes=await readFile((await d.path())!);expect(bytes.toString('utf8')).toContain(pattern);await expect(page.getByRole('status').filter({hasText:'Export verified and downloaded'})).toBeVisible();}
});

test('saved panel fits narrow and enlarged text layouts and preserves keyboard return',async({page})=>{
  test.setTimeout(60000);await page.setViewportSize({width:320,height:800});await enterWorkspace(page);await page.getByRole('button',{name:'Open saved investigations'}).click();const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Open saved investigations'})).toBeFocused();await page.setViewportSize({width:768,height:1000});await page.addStyleTag({content:'html{font-size:200% !important}'});await page.getByRole('button',{name:'Open saved investigations'}).click();expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
});

test('removing a local copy persists across reload while its portable backup still replays',async({page})=>{
  test.setTimeout(60000);await enterWorkspace(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');await save(page,'Portable backup');const record=await file(page);
  await page.getByRole('button',{name:'Remove local copy of Portable backup',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Local copy removed'})).toBeVisible();await page.reload();await dismissIntroduction(page);await page.getByRole('button',{name:'Open saved investigations'}).click();await expect(page.locator('.investigation-library')).toContainText('No local investigations yet.');
  await page.getByLabel('Open investigation file',{exact:true}).setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(record))});await expect(page.getByLabel('Selected saved investigation')).toContainText('Portable backup');await reopen(page);await expect(page.getByLabel('Native model value')).toContainText('22.303');
});
