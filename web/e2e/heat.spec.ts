import { enterWorkspace, openTool } from './ux-helpers';
import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import type { HeatAnalysis } from '../src/heat/contracts';
const version = JSON.parse(readFileSync(new URL('../../api/release.json', import.meta.url), 'utf8')).version;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true }));
});
async function open(page: Page, caseId = 'bay-bengal-2024-01'): Promise<HeatAnalysis> {
  await enterWorkspace(page);
  await page.getByLabel('Study case', { exact: true }).selectOption(caseId);
  const response = page.waitForResponse(response => response.url().includes(`/api/cases/${caseId}/heat/analyse`) && response.request().method() === 'POST' && response.status() === 200);
  await openTool(page,'Open Heat and Depth Lab');
  const result = await (await response).json() as HeatAnalysis;
  await expect(page.getByLabel('Applied heat analysis', { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('button', { name: 'Cancel analysis', exact: true })).toHaveCount(0);
  return result;
}
async function resultAfter(page: Page, action: () => Promise<unknown>): Promise<HeatAnalysis> {
  const response = page.waitForResponse(response => response.url().endsWith('/heat/analyse') && response.request().method() === 'POST' && response.status() === 200);
  await action(); const result = await (await response).json() as HeatAnalysis;
  await expect(page.getByRole('button', { name: 'Cancel analysis', exact: true })).toHaveCount(0, { timeout: 30000 });
  return result;
}
async function save(page: Page) {
  await page.getByRole('button', { name: 'Save heat investigation', exact: true }).click();
  await page.getByRole('button', { name: 'Save on this browser', exact: true }).click();
  await expect(page.getByLabel('Selected saved investigation', { exact: true })).toBeVisible({ timeout: 30000 });
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Investigation JSON', exact: true }).click();
  return JSON.parse(await readFile((await (await download).path())!, 'utf8'));
}

test('both real cases show checked daily surface evidence and actual event/depth support', async ({ page }) => {
  test.setTimeout(120000);
  for (const caseId of ['bay-bengal-2024-01', 'arabian-sea-2024-01']) {
    const result = await open(page, caseId);
    expect(result.case_id).toBe(caseId); expect(result.series).toHaveLength(366); expect(result.baseline.baseline_period).toEqual([1982, 2011]);
    await expect(page.getByLabel('Surface heatwave evidence', { exact: true })).toContainText('NOAA OISST analysed SST');
    if (result.selected_event) await expect(page.getByLabel('Selected heatwave event', { exact: true })).toContainText(`${result.selected_event.duration_days} days`);
    if (result.depth_profile) await expect(page.getByLabel('Heat model depth profile', { exact: true })).toContainText(result.depth_profile.model_time.slice(0, 10));
    else await expect(page.getByLabel('Linked depth evidence', { exact: true })).toContainText(result.depth_link.message);
    await expect(page.getByLabel('Heat and Depth Lab', { exact: true })).toContainText('A surface event does not prove a heatwave at depth.');
  }
});

test('daily slider and event selection retain complete numerical event definitions', async ({ page }) => {
  test.setTimeout(90000); const original = await open(page);
  await page.getByRole('button', { name: 'Whole year', exact: true }).click();
  await page.getByRole('slider', { name: 'Heat daily sample', exact: true }).fill('60');
  const sample = original.series[60];
  await expect(page.getByLabel('Selected surface sample', { exact: true })).toContainText(sample.sst_c!.toLocaleString('en-US', { maximumFractionDigits: 3 }));
  const event = original.events.at(-1)!;
  const result = await resultAfter(page, () => page.getByLabel('Detected surface event', { exact: true }).selectOption(event.id));
  expect(result.selected_event?.id).toBe(event.id);
  await expect(page.getByLabel('Selected heatwave event', { exact: true })).toContainText('above seasonal mean');
  await expect(page.getByLabel('Selected heatwave event', { exact: true })).toContainText(`${event.duration_days} days`);
  await page.getByRole('button', { name: 'Around selected event', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Around selected event', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const firstEventDay = result.series.find(sample => sample.date >= event.start && sample.date <= event.end)!;
  await expect(page.getByLabel('Selected surface date', { exact: true })).toHaveText(new Date(firstEventDay.date + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }));
  await page.getByText('Inspect daily source values and event membership', { exact: true }).click();
  await expect(page.getByRole('region', { name: 'Heat daily values, scrollable', exact: true }).locator('tbody tr')).toHaveCount(366);
});

test('events outside the model period cannot imply a depth profile and preserve historical years', async ({ page }) => {
  test.setTimeout(90000); await open(page);
  await page.getByLabel('Heat event year', { exact: true }).selectOption('2023');
  const year = await resultAfter(page, () => page.getByRole('button', { name: 'Analyse surface record', exact: true }).click());
  expect(year.query.year).toBe(2023); expect(year.series).toHaveLength(365);
  const outside = year.events.find(event => !event.depth_overlap);
  expect(outside).toBeDefined();
  const result = await resultAfter(page, () => page.getByLabel('Detected surface event', { exact: true }).selectOption(outside!.id));
  expect(['outside_model_period', 'no_event']).toContain(result.depth_link.status); expect(result.depth_profile).toBeNull();
  await expect(page.getByLabel('Heat model depth profile', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Linked depth evidence', { exact: true })).toContainText('An unrelated snapshot will not be substituted.');
  await expect(page.getByLabel('Surface heatwave evidence', { exact: true })).toContainText('2023');
});

test('native depth variables, integration limits and linked observation quality remain explicit', async ({ page }) => {
  test.setTimeout(90000); const original = await open(page);
  expect(original.depth_link.available_time_indices.length).toBeGreaterThan(0);
  if (!original.depth_profile) await resultAfter(page, () => page.getByRole('button', { name: 'Use first snapshot within this event', exact: true }).click());
  const deep = await resultAfter(page, () => page.getByLabel('Heat depth limit', { exact: true }).selectOption('1000'));
  expect(deep.depth_profile?.points.at(-1)?.depth_m).toBe(1000);
  for (const [value, text] of [['salinity', 'Practical salinity'], ['density', 'Potential-density anomaly'], ['gradient', 'Temperature gradient'], ['stratification', 'N-squared']]) {
    await page.getByLabel('Heat depth variable', { exact: true }).selectOption(value);
    await expect(page.getByRole('img', { name: new RegExp(`${text} versus depth`) })).toBeVisible();
    await page.getByLabel('Heat depth sample', { exact: true }).selectOption({ index: 3 });
    await expect(page.getByLabel('Selected depth value', { exact: true })).toBeVisible();
  }
  await expect(page.getByLabel('Derived column diagnostics', { exact: true })).toContainText('Conservative Temperature = 0 °C');
  await expect(page.getByLabel('Derived column diagnostics', { exact: true })).toContainText('not heatwave excess');
  if (deep.observations.length) {
    await page.getByRole('button', { name: 'Inspect source profile', exact: true }).first().click();
    await expect(page.getByLabel('Heat and Depth Lab', { exact: true })).toBeHidden();
    await openTool(page,'Open Heat and Depth Lab');
    await expect(page.getByLabel('Heat depth limit', { exact: true })).toHaveValue('1000');
  }
});

test('unapplied source changes never relabel or overwrite the saved analysis', async ({ page }) => {
  test.setTimeout(90000); const original = await open(page);
  await page.getByLabel('Heat event year', { exact: true }).selectOption('2023');
  await page.getByRole('button', { name: 'Select West', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Heat surface location', { exact: true })).toHaveValue('bay-west');
  await expect(page.locator('.heat-applied-note')).toContainText('unapplied changes');
  await expect(page.getByLabel('Surface heatwave evidence', { exact: true })).toContainText('2024');
  const captured = page.waitForRequest(request => request.url().endsWith('/api/investigations/capture'));
  const record = await save(page), request = (await captured).postDataJSON();
  expect(request.expected_heat_manifest_sha256).toBe(original.heat_manifest_sha256);
  expect(record.replay.recipe.query).toEqual(original.query); expect(record.results[0].output.series).toEqual(original.series);
});

test('save export and replay restore the complete analysis in a fresh browser context', async ({ page, browser }) => {
  test.setTimeout(120000); const original = await open(page), record = await save(page);
  expect(record.results.map((module: { module: string }) => module.module)).toEqual(['heat_analysis']);
  expect(record.results[0].output.depth_profile).toEqual(original.depth_profile);
  expect(record.replay.sources.heat_manifest_sha256).toBe(original.heat_manifest_sha256);
  const exported = page.waitForEvent('download'); await page.getByRole('button', { name: 'Complete evidence ZIP', exact: true }).click();
  expect((await exported).suggestedFilename()).toBe('ocean-investigation.zip');
  const context = await browser.newContext(), other = await context.newPage();
  await enterWorkspace(other,page.url()); await other.getByRole('button', { name: 'Open saved investigations', exact: true }).click();
  await other.getByLabel('Open investigation file', { exact: true }).setInputFiles({ name: 'heat-investigation.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(record)) });
  await expect(other.getByLabel('Selected saved investigation', { exact: true })).toContainText('Heat & Depth');
  await other.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click();
  await expect(other.getByRole('dialog')).toHaveCount(0, { timeout: 30000 });
  await expect(other.getByLabel('Heat and Depth Lab', { exact: true })).toBeVisible();
  await expect(other.getByLabel('Detected surface event', { exact: true })).toHaveValue(original.query.event_id!);
  await context.close();
});

test('cancel failure and corrupt results keep the previously verified analysis', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  let unblock!: () => void; const gate = new Promise<void>(resolve => unblock = resolve);
  await page.route('**/heat/analyse', async route => { await gate; await route.abort().catch(() => undefined); });
  await page.getByLabel('Heat event year', { exact: true }).selectOption('2023');
  await page.getByRole('button', { name: 'Analyse surface record', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel analysis', exact: true }).click();
  await expect(page.getByLabel('Heat and Depth Lab', { exact: true })).toContainText('Calculation cancelled');
  unblock(); await page.unroute('**/heat/analyse');
  await page.route('**/heat/analyse', route => route.fulfill({ status: 503, headers: { 'X-Ocean-App-Version': version }, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Surface analysis temporarily unavailable.' } }) }));
  await page.getByRole('button', { name: 'Analyse surface record', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Surface analysis temporarily unavailable');
  await expect(page.getByLabel('Surface heatwave evidence', { exact: true })).toContainText(original.query.year.toString());
  await page.unroute('**/heat/analyse');
  await page.route('**/heat/analyse', async route => { const response = await route.fetch(), result = await response.json(); result.series[0].anomaly_c += 1; await route.fulfill({ response, json: result }); });
  await page.getByRole('button', { name: 'Analyse surface record', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('could not be verified');
  await expect(page.getByLabel('Surface heatwave evidence', { exact: true })).toContainText(original.query.year.toString());
});

test('case changes discard the prior case analysis and hidden navigation preserves current work', async ({ page }) => {
  test.setTimeout(90000); await open(page);
  await openTool(page,'Ocean explorer');
  await expect(page.getByLabel('Heat and Depth Lab', { exact: true })).toBeHidden();
  await openTool(page,'Open Heat and Depth Lab');
  await expect(page.getByLabel('Heat surface location', { exact: true })).toHaveValue('bay-center');
  await page.getByLabel('Study case', { exact: true }).selectOption('arabian-sea-2024-01');
  const response = page.waitForResponse(response => response.url().includes('/arabian-sea-2024-01/heat/analyse') && response.status() === 200);
  await openTool(page,'Open Heat and Depth Lab');
  await response;
  await expect(page.getByLabel('Heat surface location', { exact: true })).toHaveValue('arabian-center');
  await expect(page.getByLabel('Surface heatwave evidence', { exact: true })).not.toContainText('Bay');
});

test('narrow layouts enlarged text and reduced motion keep controls and source values usable', async ({ page }) => {
  test.setTimeout(90000); await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 900 });
  await open(page); await page.getByRole('button', { name: 'Whole year', exact: true }).click();
  await page.getByRole('slider', { name: 'Heat daily sample', exact: true }).focus(); await page.keyboard.press('Home'); await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('slider', { name: 'Heat daily sample', exact: true })).toHaveValue('1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(await page.locator('.heat-surface').evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  await page.setViewportSize({ width: 900, height: 1000 }); await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  await expect(page.getByLabel('Heat event year', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});
