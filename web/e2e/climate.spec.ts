import { displaySettings, enterWorkspace, openTool } from './ux-helpers';
import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import type { ClimateAnalysis } from '../src/climate/contracts';
const version = JSON.parse(readFileSync(new URL('../../api/release.json', import.meta.url), 'utf8')).version;
test.beforeEach(async ({ page }) => { await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true })); });
async function open(page: Page): Promise<ClimateAnalysis> {
  await enterWorkspace(page); const response = page.waitForResponse(response => response.url().endsWith('/api/climate/analyse') && response.status() === 200);
  await openTool(page,'Open Climate Event Lab'); const result = await (await response).json();
  await expect(page.getByLabel('Applied climate comparison', { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('button', { name: 'Cancel comparison', exact: true })).toHaveCount(0);
  return result;
}
async function resultAfter(page: Page, action: () => Promise<unknown>): Promise<ClimateAnalysis> {
  const response = page.waitForResponse(response => response.url().endsWith('/api/climate/analyse') && response.status() === 200);
  await action(); const result = await (await response).json();
  await expect(page.getByRole('button', { name: 'Cancel comparison', exact: true })).toHaveCount(0, { timeout: 30000 }); return result;
}
async function save(page: Page) {
  await page.getByRole('button', { name: 'Save climate investigation', exact: true }).click();
  await page.getByRole('button', { name: 'Save on this browser', exact: true }).click();
  await expect(page.getByLabel('Selected saved investigation', { exact: true })).toBeVisible({ timeout: 30000 });
  const download = page.waitForEvent('download'); await page.getByRole('button', { name: 'Investigation JSON', exact: true }).click();
  return JSON.parse(await readFile((await (await download).path())!, 'utf8'));
}

test('actual El Nino neutral and La Nina cases use same-season data and separate index versions', async ({ page }) => {
  test.setTimeout(120000); let result = await open(page);
  expect(result.query.event_id).toBe('son-2015'); expect(result.events[0].enso.value_c).toBe(2);
  await openTool(page,'Ocean explorer');await expect(page.getByLabel('Study case', { exact: true })).toHaveValue('pacific-godas-2015-son');await openTool(page,'Open Climate Event Lab');
  await expect(page.getByLabel('Pacific climate sections', { exact: true })).toContainText('1991–2020');
  for (const [event, classification] of [['son-2013', 'neutral'], ['son-2022', 'la_nina'], ['son-2015', 'el_nino']]) {
    await page.getByLabel('Selected climate event', { exact: true }).selectOption(event);
    result = await resultAfter(page, () => page.getByRole('button', { name: 'Compare historical fields', exact: true }).click());
    expect(result.events[0].enso.classification).toBe(classification);
    expect(result.panels[0].pacific.depth_m[0]).toBe(5); expect(result.panels[0].pacific.depth_m.at(-1)).toBe(459);
    expect(result.panels[0].pacific.longitude).toEqual(result.panels[1].pacific.longitude);
    await expect(page.locator('.climate-event-card.selected')).toContainText(result.events[0].year.toString());
  }
  await expect(page.getByLabel('Separate Indian Ocean context', { exact: true })).toContainText('+0.39');
  await expect(page.getByLabel('Separate Indian Ocean context', { exact: true })).toContainText('below +0.4');
  await page.getByText('Methods, index versions and source records', { exact: true }).click();
  await expect(page.locator('.climate-methods')).toContainText('ERSSTv5');
  await expect(page.locator('.climate-methods')).toContainText('p13-climate-v1');
});

test('all calendar windows align fields while SON event labels remain explicitly separate', async ({ page }) => {
  test.setTimeout(120000); await open(page);
  for (const [period, start, end] of [['09', '-09-01', '-10-01'], ['10', '-10-01', '-11-01'], ['11', '-11-01', '-12-01'], ['SON', '-09-01', '-12-01']]) {
    await page.getByLabel('Climate calendar window', { exact: true }).selectOption(period);
    const result = await resultAfter(page, () => page.getByRole('button', { name: 'Compare historical fields', exact: true }).click());
    for (const panel of result.panels) { expect(panel.period_start.slice(4, 10)).toBe(start); expect(panel.period_end_exclusive.slice(4, 10)).toBe(end); }
    expect(result.events[0].enso.value_c).toBe(2);
    await expect(page.locator('.climate-settings')).toContainText('ENSO labels always describe the pinned September–November window');
    await expect(page.getByLabel('Pacific climate sections', { exact: true })).toContainText(result.period.label);
  }
});

test('longitude depth and chart selection keep exact synchronized native values across the dateline', async ({ page }) => {
  test.setTimeout(120000); await open(page);
  for (const x of [0, 39, 40, 139]) {
    const result = await resultAfter(page, () => page.getByLabel('Climate profile longitude', { exact: true }).selectOption(String(x)));
    expect(result.selected_point.longitude).toBe(140.5 + x);
    await expect(page.getByLabel('Selected climate source values', { exact: true })).toContainText(result.selected_point.selected.potential_temperature_c!.toLocaleString('en-US', { maximumFractionDigits: 3 }));
  }
  const deep = await resultAfter(page, () => page.getByLabel('Climate profile depth', { exact: true }).selectOption('27'));
  expect(deep.selected_point.depth_m).toBe(459);
  await expect(page.getByLabel('Selected climate source values', { exact: true })).toContainText('459 m');
  await expect(page.getByLabel('Climate profile longitude', { exact: true }).locator('option').last()).toHaveText('80.5° W');
  for (const type of ['temperature', 'difference', 'anomaly']) { await page.getByLabel('Climate section quantity', { exact: true }).selectOption(type); await expect(page.getByLabel('Pacific climate sections', { exact: true })).toBeVisible(); }
});

test('comparing an event with itself produces a visibly constant zero difference', async ({ page }) => {
  test.setTimeout(90000); await open(page); await page.getByLabel('Reference climate event', { exact: true }).selectOption('son-2015');
  const result = await resultAfter(page, () => page.getByRole('button', { name: 'Compare historical fields', exact: true }).click());
  expect(result.difference.pacific.values_c.every(value => value === null || value === 0)).toBe(true);
  await page.getByLabel('Climate section quantity', { exact: true }).selectOption('difference');
  await expect(page.getByLabel('Pacific climate sections', { exact: true })).toContainText('constant finite value');
  await expect(page.locator('.climate-difference-value')).toContainText('0 °C');
});

test('unapplied event controls do not relabel or change the saved result', async ({ page }) => {
  test.setTimeout(90000); const original = await open(page);
  await page.getByLabel('Selected climate event', { exact: true }).selectOption('son-2022');
  await page.getByLabel('Climate calendar window', { exact: true }).selectOption('09');
  await expect(page.locator('.climate-applied-note')).toContainText('unapplied changes');
  const record = await save(page);
  expect(record.replay.recipe.query).toEqual(original.query);
  expect(record.replay.sources.climate_manifest_sha256).toBe(original.climate_manifest_sha256);
  expect(record.results[0].output.selected_point).toEqual(original.selected_point);
});

test('save download export and replay restore climate settings in a fresh context', async ({ page, browser }) => {
  test.setTimeout(120000); const original = await open(page), record = await save(page);
  expect(record.results.map((module: { module: string }) => module.module)).toEqual(['climate_analysis']);
  const downloaded = page.waitForEvent('download'); await page.getByRole('button', { name: 'Complete evidence ZIP', exact: true }).click();
  expect((await downloaded).suggestedFilename()).toBe('ocean-investigation.zip');
  const context = await browser.newContext(), other = await context.newPage(); await enterWorkspace(other,page.url());
  await other.getByRole('button', { name: 'Open saved investigations', exact: true }).click();
  await other.getByLabel('Open investigation file', { exact: true }).setInputFiles({ name: 'climate.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(record)) });
  await expect(other.getByLabel('Selected saved investigation', { exact: true })).toContainText('Climate Event Lab');
  await other.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click();
  await expect(other.getByRole('dialog')).toHaveCount(0, { timeout: 30000 });
  await expect(other.getByLabel('Climate Event Lab', { exact: true })).toBeVisible();
  await openTool(other,'Ocean explorer');await expect(other.getByLabel('Study case', { exact: true })).toHaveValue(original.case_id);await openTool(other,'Open Climate Event Lab');
  await expect(other.getByLabel('Selected climate event', { exact: true })).toHaveValue(original.query.event_id);
  await context.close();
});

test('cancellation service failures and corrupt arithmetic retain the checked comparison', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  let release!: () => void; const gate = new Promise<void>(resolve => release = resolve);
  await page.route('**/api/climate/analyse', async route => { await gate; await route.abort().catch(() => undefined); });
  await page.getByLabel('Selected climate event', { exact: true }).selectOption('son-2022');
  await page.getByRole('button', { name: 'Compare historical fields', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel comparison', exact: true }).click();
  await expect(page.getByLabel('Climate Event Lab', { exact: true })).toContainText('Calculation cancelled');
  release(); await page.unroute('**/api/climate/analyse');
  await page.route('**/api/climate/analyse', route => route.fulfill({ status: 503, headers: { 'X-Ocean-App-Version': version }, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Climate source temporarily unavailable.' } }) }));
  await page.getByRole('button', { name: 'Compare historical fields', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Climate source temporarily unavailable');
  await page.unroute('**/api/climate/analyse');
  await page.route('**/api/climate/analyse', async route => { const response = await route.fetch(), result = await response.json(); result.panels[0].pacific.anomaly_c[0] += 1; await route.fulfill({ response, json: result }); });
  await page.getByRole('button', { name: 'Compare historical fields', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('could not be verified');
  await expect(page.locator('.climate-event-card.selected')).toContainText(String(original.events[0].year));
});

test('shared Pacific cases show only supplied fields correct depths and original observations', async ({ page }) => {
  test.setTimeout(150000); await open(page);
  await page.getByRole('button', { name: 'Explore this Pacific case', exact: true }).first().click();
  await expect(page.getByLabel('Scientific ocean explorer', { exact: true })).toBeVisible();
  await displaySettings(page);await page.getByLabel('Graphics quality', { exact: true }).selectOption('basic');
  await expect(page.getByLabel('Native model value', { exact: true })).not.toContainText('Loading', { timeout: 30000 });
  await expect(page.getByLabel('Scientific ocean explorer', { exact: true })).toContainText('Potential temperature');
  await expect(page.getByLabel('Scientific ocean explorer', { exact: true })).toContainText('5 m to 459 m');
  await expect(page.locator('.case-source-strip')).toContainText('NOAA GODAS');
  await expect(page.locator('.case-source-strip')).not.toContainText('HYCOM');
  await expect(page.getByLabel('Ocean timestamp',{exact:true}).locator('option')).toHaveCount(3);
  await expect(page.getByRole('button',{name:'Play ocean playback',exact:true})).toHaveAttribute('title','Play available times');
  await openTool(page,'Open Drift Lab');await expect(page.getByRole('heading',{name:'Choose a case for Drift Lab'})).toBeVisible();await page.getByRole('button',{name:'Close tools',exact:true}).click();
  await openTool(page,'Open Heat and Depth Lab');await expect(page.getByRole('heading',{name:'Choose a case for Heat & Depth'})).toBeVisible();await page.getByRole('button',{name:'Close tools',exact:true}).click();
  for (const caseId of ['pacific-godas-2013-son', 'pacific-godas-2022-son', 'pacific-godas-2015-son']) {
    await page.getByLabel('Study case', { exact: true }).selectOption(caseId);
    await expect(page.getByLabel('Study case', { exact: true })).toHaveValue(caseId);
    await expect(page.getByLabel('Scientific ocean explorer', { exact: true })).toContainText(caseId.slice(14, 18));
  }
  const searchResponse=page.waitForResponse(response=>response.url().includes('/features/search')&&response.status()===200);
  await openTool(page,'Open structure search');
  const search=await (await searchResponse).json();expect(search.query.depth_min_m).toBe(5);
  await expect(page.getByLabel('Minimum search depth',{exact:true})).toHaveValue('5');
  await expect(page.getByLabel('Structure variable',{exact:true})).toHaveText('Potential temperature');
  await expect(page.getByLabel('Underwater structure search',{exact:true})).toContainText('monthly mean');
  await page.getByRole('button',{name:'Section through selected region',exact:true}).click();
  await expect(page.getByRole('img',{name:'Vertical section along the drawn line',exact:true})).toBeVisible({timeout:30000});
  await expect(page.getByLabel('Section source value',{exact:true})).toContainText('Native model value');
  await openTool(page,'Open Climate Event Lab');
  await expect(page.getByLabel('Applied climate comparison', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Inspect source profile', exact: true }).first().click();
  await expect(page.getByLabel('Climate Event Lab', { exact: true })).toBeHidden();
  await expect(page.getByText('This monthly potential-temperature field is not directly compared with instantaneous in-situ observations.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Compare with model', exact: true })).toHaveCount(0);
  await page.locator('.instrument-location > summary').click();
  const markers=page.getByRole('group',{name:'Observed instrument locations',exact:true}).getByRole('button');
  await expect(markers).toHaveCount(3);
  const positions=await markers.evaluateAll(elements=>elements.map(element=>Number(element.getAttribute('transform')!.match(/translate\(([^,]+)/)![1])));
  expect(positions.every(x=>Math.abs(x-360)<25)).toBe(true);
});

test('narrow enlarged and reduced-motion layouts preserve controls and exact values', async ({ page }) => {
  test.setTimeout(90000); await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 900 }); await open(page);
  await expect(page.getByLabel('Climate calendar window', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(await page.locator('.climate-pacific').evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  await page.getByText('Compare Indian Ocean depth sections for the same dates', { exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 900, height: 1000 }); await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test('Pacific depth exaggeration is explicit preserves native values and survives ocean replay', async ({ page }) => {
  test.setTimeout(120000); await open(page);
  await page.getByRole('button', { name: 'Explore this Pacific case', exact: true }).first().click();
  await displaySettings(page);await page.getByLabel('Graphics quality', { exact: true }).selectOption('balanced');
  await expect(page.getByText('Interactive 3D', { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.ocean-display-bar')).toContainText('6,000'.replace(',', ''));
  await expect(page.getByLabel('Native model value', { exact: true })).toContainText('°C', { timeout: 30000 });
  const before = await page.getByLabel('Native model value', { exact: true }).textContent();
  await displaySettings(page);
  const slider = page.getByRole('slider', { name: 'Vertical exaggeration', exact: true });
  await slider.fill('10000');
  await expect(page.getByLabel('Native model value', { exact: true })).toHaveText(before!);
  await slider.fill('6000');
  await page.getByRole('button', { name: 'Save investigation', exact: true }).click();
  await page.getByRole('button', { name: 'Save on this browser', exact: true }).click();
  await expect(page.getByLabel('Selected saved investigation', { exact: true })).toBeVisible({ timeout: 30000 });
  const download = page.waitForEvent('download'); await page.getByRole('button', { name: 'Investigation JSON', exact: true }).click();
  const record = JSON.parse(await readFile((await (await download).path())!, 'utf8'));
  expect(record.replay.recipe.exaggeration).toBe(6000);
  expect(record.replay.recipe.case_id).toBe('pacific-godas-2015-son');
  await page.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator('.ocean-display-bar')).toContainText('6000');
  await expect(page.getByLabel('Native model value', { exact: true })).toHaveText(before!, { timeout: 30000 });
});
