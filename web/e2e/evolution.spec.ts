import { enterWorkspace, openTool } from './ux-helpers';
import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import type { EvolutionAnalysis } from '../src/evolution/contracts';
const version = JSON.parse(readFileSync(new URL('../../api/release.json', import.meta.url), 'utf8')).version;
test.beforeEach(async ({ page }) => { await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true })); });
const workspace = (page: Page) => page.getByLabel('Feature evolution workspace', { exact: true });
async function after(page: Page, action: () => Promise<unknown>): Promise<EvolutionAnalysis> {
  const response = page.waitForResponse(response => /\/evolution\/run$/.test(response.url()) && response.status() === 200);
  await action(); const result = await (await response).json();
  await expect(workspace(page).getByRole('button', { name: 'Cancel calculation', exact: true })).toHaveCount(0, { timeout: 60000 });
  await expect(page.getByLabel('Applied feature evolution', { exact: true })).toBeVisible(); return result;
}
async function open(page: Page) { await enterWorkspace(page); return after(page, () => openTool(page,'Open feature evolution')); }
async function save(page: Page) {
  await workspace(page).getByRole('button', { name: 'Save investigation', exact: true }).click();
  await page.getByRole('button', { name: 'Save on this browser', exact: true }).click();
  await expect(page.getByLabel('Selected saved investigation', { exact: true })).toBeVisible({ timeout: 60000 });
  const downloaded = page.waitForEvent('download'); await page.getByRole('button', { name: 'Investigation JSON', exact: true }).click();
  return JSON.parse(await readFile((await (await downloaded).path())!, 'utf8'));
}

test('native timestamps regions and selected footprint agree with source-backed results', async ({ page }) => {
  test.setTimeout(120000); const result = await open(page);
  expect(result.case_id).toBe('bay-bengal-2024-01'); expect(result.frames).toHaveLength(7);
  expect(result.transitions.every(transition => transition.elapsed_hours === 12 && transition.status === 'compared')).toBe(true);
  const frame = result.frames[2], node = frame.regions[0];
  await page.getByLabel('Inspect evolution frame', { exact: true }).selectOption(String(frame.time_index));
  await expect(page.getByLabel('Inspect evolution region', { exact: true })).toHaveValue(node.node_id);
  await expect(page.getByLabel('Evolution region extent', { exact: true })).toContainText(node.estimated_volume_km3.toLocaleString('en-US', { maximumFractionDigits: 3 }));
  await expect(workspace(page)).toContainText('not proof that the same water moved');
  await expect(page.getByLabel('Evolution region extent', { exact: true })).toContainText('Selected depth limits are separate');
});

test('Arabian Sea real source regions expose branching and native overlap evidence', async ({ page }) => {
  test.setTimeout(120000); await open(page);
  const result = await after(page, () => page.getByRole('button', { name: 'Open Arabian Sea branching case', exact: true }).click());
  expect(result.case_id).toBe('arabian-sea-2024-01'); expect(result.summary.split_count).toBeGreaterThan(0); expect(result.summary.merge_count).toBeGreaterThan(0);
  await expect(page.getByLabel('Study case', { exact: true })).toHaveValue(result.case_id);
  const link = result.transitions.flatMap(transition => transition.links).find(link => link.classification === 'split')!;
  await page.getByLabel('Inspect evolution frame', { exact: true }).selectOption(link.source_node_id.split(':')[0].slice(1));
  await page.getByLabel('Inspect evolution region', { exact: true }).selectOption(link.source_node_id);
  await expect(page.getByLabel('Evolution link inspector', { exact: true })).toContainText(link.target_node_id);
  await expect(page.getByLabel('Evolution link inspector', { exact: true })).toContainText(`${link.shared_cells.toLocaleString('en-US')} shared native cells`);
  await page.getByLabel('Evolution link inspector', { exact: true }).getByRole('button', { name: 'Inspect connected region', exact: true }).first().click();
  await expect(page.getByLabel('Inspect evolution region', { exact: true })).not.toHaveValue(link.source_node_id);
});

test('sensitivity recomputes nearby thresholds and applied controls retain old result until submission', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  await page.getByLabel('Evolution threshold sensitivity', { exact: true }).fill('0.5');
  await expect(workspace(page).getByRole('button', { name: 'Save investigation', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Applied feature evolution', { exact: true })).toContainText('at least 26');
  const result = await after(page, () => page.getByRole('button', { name: 'Compare source frames', exact: true }).click());
  expect(result.sensitivity.map(trial => trial.offset)).toEqual([-.5, 0, .5]);
  expect(result.frames).toEqual(original.frames);
  await expect(page.getByLabel('Threshold sensitivity results', { exact: true })).toContainText('26.5');
});

test('skipped source frames make explicit unbridged gaps instead of trajectories', async ({ page }) => {
  test.setTimeout(120000); await open(page); await page.getByText('Depth limits, overlap rule and time gaps', { exact: true }).click();
  await page.getByLabel('Evolution frame spacing', { exact: true }).selectOption('2');
  const result = await after(page, () => page.getByRole('button', { name: 'Compare source frames', exact: true }).click());
  expect(result.frames.map(frame => frame.time_index)).toEqual([0, 2, 4, 6]); expect(result.summary.gap_count).toBe(3); expect(result.summary.link_count).toBe(0);
  await expect(page.getByLabel('Evolution link inspector', { exact: true })).toContainText('No correspondence is inferred across this gap');
  expect(result.transitions.every(transition => transition.appeared_node_ids.length === 0 && transition.disappeared_node_ids.length === 0)).toBe(true);
});

test('empty regions and a zero sensitivity delta have no invented graph nodes', async ({ page }) => {
  test.setTimeout(120000); await open(page); await page.getByLabel('Evolution threshold', { exact: true }).fill('100'); await page.getByLabel('Evolution threshold sensitivity', { exact: true }).fill('0');
  const result = await after(page, () => page.getByRole('button', { name: 'Compare source frames', exact: true }).click());
  expect(result.summary.node_count).toBe(0); expect(result.sensitivity).toHaveLength(1);
  await expect(page.getByLabel('Inspect evolution region', { exact: true })).toBeDisabled();
  await expect(workspace(page)).toContainText('Showing 0 of 0 nodes');
  await expect(page.getByLabel('Evolution region extent', { exact: true })).toHaveCount(0);
});

test('cancel service error and malformed region totals preserve the verified graph', async ({ page }) => {
  test.setTimeout(150000); const original = await open(page);
  let release!: () => void; const gate = new Promise<void>(resolve => release = resolve);
  await page.route('**/evolution/run', async route => { await gate; await route.abort().catch(() => undefined); });
  await page.getByLabel('Evolution threshold', { exact: true }).fill('27'); await page.getByRole('button', { name: 'Compare source frames', exact: true }).click(); await workspace(page).getByRole('button', { name: 'Cancel calculation', exact: true }).click();
  await expect(workspace(page)).toContainText('Calculation cancelled'); release(); await page.unroute('**/evolution/run');
  await page.route('**/evolution/run', route => route.fulfill({ status: 503, headers: { 'X-Ocean-App-Version': version }, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Evolution source temporarily unavailable.' } }) }));
  await page.getByRole('button', { name: 'Compare source frames', exact: true }).click(); await expect(workspace(page).getByRole('alert')).toContainText('Evolution source temporarily unavailable'); await page.unroute('**/evolution/run');
  await page.route('**/evolution/run', async route => { const response = await route.fetch(), body = await response.json(); body.frames[0].qualified_cells += 1; await route.fulfill({ response, json: body }); });
  const corrupted = page.waitForResponse(response => /\/evolution\/run$/.test(response.url()) && response.status() === 200, { timeout: 60000 });
  await page.getByRole('button', { name: 'Compare source frames', exact: true }).click(); await corrupted; await expect(workspace(page).getByRole('alert')).toContainText('could not be verified');
  await expect(page.getByLabel('Applied feature evolution', { exact: true })).toContainText(`at least ${original.query.threshold}`);
});

test('saved evolution restores selected node and exact scientific output in a fresh browser context', async ({ page, browser }) => {
  test.setTimeout(180000); const original = await open(page), frame = original.frames[2];
  await page.getByLabel('Inspect evolution frame', { exact: true }).selectOption(String(frame.time_index));
  const record = await save(page); expect(record.replay.recipe.selected_node).toBe(frame.regions[0].node_id); expect(record.results[0].module).toBe('evolution_analysis'); expect(record.results[0].output).toEqual(original);
  const zip = page.waitForEvent('download'); await page.getByRole('button', { name: 'Complete evidence ZIP', exact: true }).click(); expect((await zip).suggestedFilename()).toBe('ocean-investigation.zip');
  const context = await browser.newContext(), other = await context.newPage(); await enterWorkspace(other,page.url()); await other.getByRole('button', { name: 'Open saved investigations', exact: true }).click();
  await other.getByLabel('Open investigation file', { exact: true }).setInputFiles({ name: 'evolution.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(record)) });
  await other.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click(); await expect(other.getByRole('dialog')).toHaveCount(0, { timeout: 60000 });
  await expect(other.getByLabel('Feature evolution workspace', { exact: true })).toBeVisible(); await expect(other.getByLabel('Inspect evolution region', { exact: true })).toHaveValue(frame.regions[0].node_id); await context.close();
});

test('narrow reduced-motion and enlarged text views stay usable without page overflow', async ({ page }) => {
  test.setTimeout(120000); await page.setViewportSize({ width: 320, height: 820 }); await page.emulateMedia({ reducedMotion: 'reduce' }); await open(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.getByLabel('Inspect evolution frame', { exact: true }).selectOption('1'); await expect(page.getByLabel('Evolution region extent', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 768, height: 1000 }); await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const node = page.getByRole('button', { name: /Inspect t1:r/ }).first(); await node.focus(); await page.keyboard.press('Enter'); await expect(node).toHaveAttribute('aria-pressed', 'true');
});

test('evolution preserves newer draft edits while an earlier calculation finishes', async ({ page }) => {
  test.setTimeout(120000); await open(page);
  let release!: () => void; const gate = new Promise<void>(resolve => release = resolve);
  await page.route('**/evolution/run', async route => { await gate; await route.continue(); });
  await page.getByLabel('Evolution threshold', { exact: true }).fill('27');
  const completed = page.waitForResponse(response => /\/evolution\/run$/.test(response.url()) && response.status() === 200, { timeout: 60000 });
  await page.getByRole('button', { name: 'Compare source frames', exact: true }).click();
  await page.getByLabel('Evolution threshold', { exact: true }).fill('28'); release();
  const result: EvolutionAnalysis = await (await completed).json(); expect(result.query.threshold).toBe(27);
  await expect(workspace(page).getByRole('button', { name: 'Cancel calculation', exact: true })).toHaveCount(0, { timeout: 60000 });
  await expect(page.getByLabel('Evolution threshold', { exact: true })).toHaveValue('28');
  await expect(page.getByLabel('Applied feature evolution', { exact: true })).toContainText('at least 27');
  await expect(workspace(page).getByRole('button', { name: 'Save investigation', exact: true })).toBeDisabled();
});
