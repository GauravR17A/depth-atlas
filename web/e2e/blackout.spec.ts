import { enterWorkspace, openTool } from './ux-helpers';
import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import type { BlackoutAnalysis } from '../src/blackout/contracts';
const version = JSON.parse(readFileSync(new URL('../../api/release.json', import.meta.url), 'utf8')).version;
test.beforeEach(async ({ page }) => { await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true })); });
const workspace = (page: Page) => page.getByLabel('Observation blackout workspace', { exact: true });
async function after(page: Page, action: () => Promise<unknown>): Promise<BlackoutAnalysis> {
  const response = page.waitForResponse(response => /\/blackout\/run$/.test(response.url()) && response.status() === 200);
  await action(); const result = await (await response).json();
  await expect(workspace(page).getByRole('button', { name: 'Cancel calculation', exact: true })).toHaveCount(0, { timeout: 60000 });
  await expect(page.getByLabel('Applied observation blackout', { exact: true })).toBeVisible(); return result;
}
async function open(page: Page) { await enterWorkspace(page); return after(page, () => openTool(page,'Open observation blackout')); }
async function save(page: Page, label: string) {
  await workspace(page).getByRole('button', { name: label, exact: true }).click(); await page.getByRole('button', { name: 'Save on this browser', exact: true }).click();
  await expect(page.getByLabel('Selected saved investigation', { exact: true })).toBeVisible({ timeout: 60000 });
  const downloaded = page.waitForEvent('download'); await page.getByRole('button', { name: 'Investigation JSON', exact: true }).click();
  return JSON.parse(await readFile((await (await downloaded).path())!, 'utf8'));
}

test('original and modified coverage share exact model identity and actual source timestamps', async ({ page }) => {
  test.setTimeout(120000); const result = await open(page);
  expect(result.model_unchanged).toBe(true); expect(result.source_qc_unchanged).toBe(true); expect(result.baseline.matched_samples).toBeGreaterThan(0); expect(result.modified).toEqual(result.baseline);
  await expect(page.getByLabel('Original eligible pairs', { exact: true })).toHaveText(String(result.baseline.matched_samples));
  await expect(page.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText(String(result.modified.matched_samples));
  await expect(page.getByLabel('Applied observation blackout', { exact: true })).toContainText('2024-01-07 12:00 UTC');
  await expect(workspace(page)).toContainText('does not rerun the ocean model');
});

test('removing one real contributing profile reveals exact lost comparisons without changing the model', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  await page.getByRole('button', { name: 'Select one contributing profile', exact: true }).click();
  await expect(page.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText(String(original.baseline.matched_samples));
  await expect(workspace(page).getByRole('button', { name: 'Save investigation', exact: true })).toBeDisabled();
  const result = await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  expect(result.manifest_sha256).toBe(original.manifest_sha256); expect(result.baseline).toEqual(original.baseline); expect(result.removed_eligible_samples).toBeGreaterThan(0);
  expect(result.profile_effects.reduce((count, effect) => count + effect.removed_sample_indices.length, 0)).toBe(result.removed_eligible_samples);
  await expect(page.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText(String(result.modified.matched_samples));
  await expect(page.getByLabel('Removed eligible comparisons', { exact: true })).toContainText(`${result.removed_eligible_samples} eligible comparisons lost`);
  const profile = original.baseline.profiles.find(profile => result.excluded_profile_ids.includes(profile.profile.id))!;
  await expect(page.getByLabel('Removed eligible comparisons', { exact: true })).toContainText(profile.profile.time.slice(0, 10));
});

test('overlapping profile and instrument-group choices never double-count removals', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  const profile = original.baseline.profiles.find(profile => profile.matched_count > 0)!;
  const labels = { argo: 'Argo floats', bgc: 'BGC Argo floats', glider: 'Glider profiles', ctd: 'Ship CTD profiles' };
  await page.getByRole('button', { name: 'Select one contributing profile', exact: true }).click();
  await page.getByLabel(`Exclude ${labels[profile.profile.instrument]}`, { exact: true }).check();
  const result = await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  const expected = original.baseline.profiles.filter(item => item.profile.instrument === profile.profile.instrument);
  expect(result.removed_profiles).toBe(expected.length); expect(result.removed_eligible_samples).toBe(expected.reduce((count, item) => count + item.matched_count, 0));
  expect(new Set(result.excluded_profile_ids).size).toBe(result.excluded_profile_ids.length);
});

test('excluding all instrument groups produces empty coverage and unavailable residuals', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  for (const box of await workspace(page).getByRole('checkbox', { name: /^Exclude (Argo floats|BGC Argo floats|Glider profiles|Ship CTD profiles)$/ }).all()) await box.check();
  const result = await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  expect(result.modified.total_profiles).toBe(0); expect(result.modified.matched_samples).toBe(0); expect(result.modified_metrics.rmse).toBeNull(); expect(result.removed_eligible_samples).toBe(original.baseline.matched_samples);
  await expect(page.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText('0');
  await expect(page.getByLabel('Original and modified residual metrics', { exact: true })).toContainText('Not available');
  await page.getByRole('button', { name: 'Clear exclusions', exact: true }).click();
  const restored = await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  expect(restored.modified).toEqual(original.baseline);
});

test('removing an already ineligible profile keeps eligible evidence unchanged', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page), profile = original.baseline.profiles.find(profile => profile.matched_count === 0)!;
  await page.getByText('Choose individual profiles, platforms or collections', { exact: true }).click();
  await page.getByLabel(`Exclude profile ${profile.profile.id}`, { exact: true }).check();
  const result = await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  expect(result.removed_profiles).toBe(1); expect(result.removed_eligible_samples).toBe(0); expect(result.modified.matched_samples).toBe(original.baseline.matched_samples); expect(result.modified_metrics).toEqual(original.baseline_metrics);
  await expect(page.getByLabel('Removed eligible comparisons', { exact: true })).toContainText('0 eligible comparisons lost');
});

test('original and excluded investigations both save and modified output replays in a fresh context', async ({ page, browser }) => {
  test.setTimeout(180000); await open(page); await page.getByRole('button', { name: 'Select one contributing profile', exact: true }).click();
  const analysis = await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  const original = await save(page, 'Save original evidence'); expect(original.replay.recipe.query.excluded_profile_ids).toEqual([]); expect(original.results[0].output.removed_profiles).toBe(0);
  await page.getByRole('button', { name: 'Close saved investigations', exact: true }).click();
  const record = await save(page, 'Save modified evidence'); expect(record.results[0].module).toBe('blackout_analysis'); expect(record.results[0].output).toEqual(analysis);
  const context = await browser.newContext(), other = await context.newPage(); await enterWorkspace(other,page.url()); await other.getByRole('button', { name: 'Open saved investigations', exact: true }).click();
  await other.getByLabel('Open investigation file', { exact: true }).setInputFiles({ name: 'blackout.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(record)) });
  await other.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click(); await expect(other.getByRole('dialog')).toHaveCount(0, { timeout: 60000 });
  await expect(other.getByLabel('Observation blackout workspace', { exact: true })).toBeVisible(); await expect(other.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText(String(analysis.modified.matched_samples)); await context.close();
});

test('cancellation service failure and inconsistent effect totals preserve the last result', async ({ page }) => {
  test.setTimeout(120000); const original = await open(page);
  await page.getByRole('button', { name: 'Select one contributing profile', exact: true }).click();
  let release!: () => void; const gate = new Promise<void>(resolve => release = resolve);
  await page.route('**/blackout/run', async route => { await gate; await route.abort().catch(() => undefined); });
  await page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click(); await workspace(page).getByRole('button', { name: 'Cancel calculation', exact: true }).click(); await expect(workspace(page)).toContainText('Calculation cancelled'); release(); await page.unroute('**/blackout/run');
  await page.route('**/blackout/run', route => route.fulfill({ status: 503, headers: { 'X-Ocean-App-Version': version }, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Observation library temporarily unavailable.' } }) }));
  await page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click(); await expect(workspace(page).getByRole('alert')).toContainText('Observation library temporarily unavailable'); await page.unroute('**/blackout/run');
  await page.route('**/blackout/run', async route => { const response = await route.fetch(), result = await response.json(); result.removed_eligible_samples += 1; await route.fulfill({ response, json: result }); });
  await page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click(); await expect(workspace(page).getByRole('alert')).toContainText('could not be verified');
  await expect(page.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText(String(original.modified.matched_samples));
});

test('blackout controls and evidence remain usable at 320 pixels and enlarged text', async ({ page }) => {
  test.setTimeout(120000); await page.setViewportSize({ width: 320, height: 820 }); await page.emulateMedia({ reducedMotion: 'reduce' }); await open(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.getByRole('button', { name: 'Select one contributing profile', exact: true }).click(); await after(page, () => page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click());
  await expect(page.getByLabel('Removed eligible comparisons', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 768, height: 1000 }); await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test('blackout preserves newer exclusion edits while an earlier calculation finishes', async ({ page }) => {
  test.setTimeout(120000); await open(page);
  await page.getByRole('button', { name: 'Select one contributing profile', exact: true }).click();
  let release!: () => void; const gate = new Promise<void>(resolve => release = resolve);
  await page.route('**/blackout/run', async route => { await gate; await route.continue(); });
  const completed = page.waitForResponse(response => /\/blackout\/run$/.test(response.url()) && response.status() === 200, { timeout: 60000 });
  await page.getByRole('button', { name: 'Apply observation blackout', exact: true }).click();
  await page.getByLabel('Exclude Ship CTD profiles', { exact: true }).check(); release();
  const result: BlackoutAnalysis = await (await completed).json(); expect(result.query.excluded_instruments).toEqual([]);
  await expect(workspace(page).getByRole('button', { name: 'Cancel calculation', exact: true })).toHaveCount(0, { timeout: 60000 });
  await expect(page.getByLabel('Exclude Ship CTD profiles', { exact: true })).toBeChecked();
  await expect(page.getByLabel('Remaining eligible pairs', { exact: true })).toHaveText(String(result.modified.matched_samples));
  await expect(workspace(page).getByRole('button', { name: 'Save investigation', exact: true })).toBeDisabled();
});

test('Pacific blackout labels monthly potential temperature and excludes incompatible residuals', async ({ page }) => {
  test.setTimeout(120000); await enterWorkspace(page); await page.getByLabel('Study case', { exact: true }).selectOption('pacific-godas-2015-son');
  await openTool(page,'Open feature evolution');await expect(page.getByRole('heading',{name:'Choose a case for Feature evolution'})).toBeVisible();await page.getByRole('button',{name:'Close tools',exact:true}).click();
  const result = await after(page, () => openTool(page,'Open observation blackout'));
  expect(result.case_id).toBe('pacific-godas-2015-son'); expect(result.baseline.matched_samples).toBe(0); expect(result.baseline.exclusion_counts.incompatible_variable).toBeGreaterThan(0);
  await expect(page.getByLabel('Blackout model period', { exact: true })).toBeVisible();
  const applied = page.getByLabel('Applied observation blackout', { exact: true });
  await expect(applied).toContainText('Monthly potential-temperature model field'); await expect(applied).toContainText('2015-10-01'); await expect(applied).toContainText('2015-11-01'); await expect(applied).toContainText('end exclusive');
  await expect(page.getByLabel('Blackout variable', { exact: true }).locator('option[value="salinity"]')).toHaveJSProperty('disabled', true);
  await expect(page.getByLabel('Monthly blackout quantity limits', { exact: true })).toContainText('not directly comparable');
});
