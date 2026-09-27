/** Phase 14 visual evidence. Real API responses, no route mocks or fabricated fields. */
import { chromium, expect as baseExpect } from '@playwright/test';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';

const base = process.argv[2] ?? 'http://127.0.0.1:8014';
const out = path.resolve(process.argv[3] ?? '../docs/evidence/p14-visual-local');
const expect = baseExpect.configure({ timeout: 60000 });
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1536, height: 1000 } });
page.setDefaultTimeout(60000);
const checks = [], errors = [], consoleErrors = [], exports = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => { if (message.type() === 'error') consoleErrors.push({ message: message.text(), location: message.location() }); });
await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true }));
const labs = {
  evolution: { button: 'Evolution', workspace: 'Feature evolution workspace', applied: 'Applied feature evolution', apply: 'Compare source frames' },
  blackout: { button: 'Blackout', workspace: 'Observation blackout workspace', applied: 'Applied observation blackout', apply: 'Apply observation blackout' },
};
let currentLab = 'evolution';
const label = name => page.getByLabel(name, { exact: true }).filter({ visible: true });
const button = name => page.getByRole('button', { name, exact: true }).filter({ visible: true });

async function checkpoint(complete = false) {
  await writeFile(path.join(out, 'checks.json'), JSON.stringify({ base, checkedAtUtc: new Date().toISOString(), complete, checks, errors, consoleErrors, exports }, null, 2));
}

async function shot(name, target = page) {
  if (target !== page) await target.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  await target.screenshot({ path: path.join(out, `${name}.png`), animations: 'disabled' });
  const layout = await page.evaluate(() => ({
    viewport: { width: innerWidth, height: innerHeight },
    documentWidth: document.documentElement.scrollWidth,
    overflow: document.documentElement.scrollWidth > innerWidth + 1,
    rootFontSize: getComputedStyle(document.documentElement).fontSize,
  }));
  checks.push({ name, ...layout, alerts: await page.getByRole('alert').filter({ visible: true }).allTextContents() });
  await checkpoint();
}

async function completed(lab) {
  await expect(label(labs[lab].applied)).toBeVisible();
  await expect(button(labs[lab].apply)).toBeEnabled();
  await expect(button('Cancel calculation')).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
}

function responseFor(lab, caseId) {
  return page.waitForResponse(response => response.request().method() === 'POST'
    && response.url().endsWith(`/api/cases/${caseId}/${lab}/run`));
}

async function open(lab, caseId = 'bay-bengal-2024-01') {
  currentLab = lab;
  await page.goto(base);
  await expect(label('Study case')).toBeEnabled();
  if (await label('Study case').inputValue() !== caseId) await label('Study case').selectOption(caseId);
  await expect(button(labs[lab].button)).toBeEnabled();
  const pending = responseFor(lab, caseId);
  await button(labs[lab].button).click();
  const response = await pending;
  expect(response.status(), `${lab} API load`).toBe(200);
  const result = await response.json();
  await completed(lab);
  return result;
}

async function apply(lab = currentLab) {
  const caseId = await label('Study case').inputValue();
  const pending = responseFor(lab, caseId);
  await button(labs[lab].apply).click();
  const response = await pending;
  expect(response.status(), `${lab} API apply`).toBe(200);
  const result = await response.json();
  await completed(lab);
  return result;
}

async function advancedEvolution() {
  const details = label('Feature evolution settings').locator('details').filter({ hasText: 'Depth limits, overlap rule and time gaps' });
  if (await details.getAttribute('open') === null) await details.locator('summary').click();
}

async function saveBlackout(original, expectedRemovedProfiles) {
  await button(original ? 'Save original evidence' : 'Save modified evidence').click();
  const dialog = page.getByRole('dialog', { name: 'Saved investigations', exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Investigation name', { exact: true }).fill(original ? 'P14 visual original evidence' : 'P14 visual modified evidence');
  const pending = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/investigations/capture'));
  await dialog.getByRole('button', { name: 'Save on this browser', exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const saved = await response.json();
  expect(saved.replay.recipe.mode).toBe('blackout');
  expect(saved.results[0].output.removed_profiles).toBe(expectedRemovedProfiles);
  await expect(dialog.getByLabel('Selected saved investigation', { exact: true })).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Complete evidence ZIP', exact: true })).toBeEnabled();
  await shot(original ? 'blackout-saved-original' : 'blackout-saved-modified', dialog);
  if (!original) {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      dialog.getByRole('button', { name: 'Complete evidence ZIP', exact: true }).click(),
    ]);
    const filename = path.join(out, 'blackout-visual-modified-evidence.zip');
    await download.saveAs(filename);
    const size = (await stat(filename)).size;
    expect(size).toBeGreaterThan(0);
    exports.push({ file: path.basename(filename), bytes: size, mode: 'blackout', removedProfiles: expectedRemovedProfiles });
    await expect(dialog.getByRole('button', { name: 'Complete evidence ZIP', exact: true })).toBeEnabled();
  }
  await dialog.getByRole('button', { name: 'Close saved investigations', exact: true }).click();
  await expect(dialog).toBeHidden();
}

try {
  await open('evolution');
  await shot('evolution-bay-introduction', label(labs.evolution.workspace).locator('.p14-heading'));
  await shot('evolution-bay-graph', label('Applied feature evolution'));
  await shot('evolution-bay-selected-extent', label('Evolution region extent'));

  const branching = responseFor('evolution', 'arabian-sea-2024-01');
  await button('Open Arabian Sea branching case').click();
  expect((await branching).status()).toBe(200);
  await completed('evolution');
  await shot('evolution-arabian-branching', label('Applied feature evolution'));
  await shot('evolution-selected-extent', label('Evolution region extent'));
  await shot('evolution-link-inspector', label('Evolution link inspector'));
  await shot('evolution-threshold-sensitivity', page.getByRole('region', { name: 'Evolution sensitivity comparison', exact: true }));
  if (await button('Inspect connected region').count()) {
    await button('Inspect connected region').first().click();
    await shot('evolution-connected-selection', label('Evolution link inspector'));
  }
  await page.getByText('Inspect every transition, sources and scientific method', { exact: true }).click();
  await shot('evolution-source-transition-table', label('All source transitions'));

  await advancedEvolution();
  await label('Evolution frame spacing').selectOption('2');
  await apply('evolution');
  await shot('evolution-explicit-time-gap', label('Applied feature evolution'));
  await shot('evolution-gap-explanation', label('Evolution link inspector'));
  await label('Evolution frame spacing').selectOption('1');
  await label('Evolution last frame').selectOption('1');
  await label('Evolution threshold').fill('0');
  await label('Feature evolution settings').getByLabel('Evolution threshold sensitivity', { exact: true }).fill('0');
  await label('Evolution minimum depth').fill('100');
  await label('Evolution maximum depth').fill('300');
  const depthSelection = await apply('evolution');
  expect(depthSelection.frames[0].regions[0].selection_depth_contacts).toEqual(['shallow', 'deep']);
  await shot('evolution-requested-depth-boundaries', label('Evolution region extent'));

  await open('blackout');
  await expect(label('Original eligible pairs')).toHaveText('206');
  await expect(label('Remaining eligible pairs')).toHaveText('206');
  await shot('blackout-original-coverage', label('Applied observation blackout'));
  await shot('blackout-original-depth-evidence', label('Blackout eligible depths'));
  await button('Select one contributing profile').click();
  const single = await apply('blackout');
  expect(single.removed_profiles).toBe(1);
  await expect(label('Remaining eligible pairs')).toHaveText('103');
  await shot('blackout-single-profile-coverage', label('Applied observation blackout'));
  await shot('blackout-single-profile-depths', label('Blackout eligible depths'));
  const indices = label('Removed eligible comparisons').locator('details').first();
  await indices.locator('summary').click();
  await shot('blackout-exact-lost-source-indices', label('Removed eligible comparisons'));
  await shot('blackout-affected-statements', label('Blackout affected statements'));
  await shot('blackout-residual-statistics', label('Blackout residual summaries'));
  await saveBlackout(true, 0);
  await saveBlackout(false, 1);

  await button('Clear exclusions').click();
  for (const group of ['Argo floats', 'BGC Argo floats', 'Ship CTD profiles', 'Glider profiles']) await label(`Exclude ${group}`).check();
  const all = await apply('blackout');
  expect(all.modified.total_profiles).toBe(0);
  await expect(label('Remaining eligible pairs')).toHaveText('0');
  await shot('blackout-all-observations-excluded', label('Applied observation blackout'));
  await shot('blackout-no-pairs-residuals', label('Blackout residual summaries'));
  await button('Clear exclusions').click();
  await label('Exclude Glider profiles').check();
  const ineligible = await apply('blackout');
  expect(ineligible.removed_profiles).toBe(4);
  expect(ineligible.removed_eligible_samples).toBe(0);
  await expect(label('Remaining eligible pairs')).toHaveText('206');
  await shot('blackout-already-ineligible-group', label('Applied observation blackout'));
  await shot('blackout-ineligible-group-explanation', label('Removed eligible comparisons'));

  const monthly = await open('blackout', 'pacific-godas-2015-son');
  expect(monthly.baseline.matched_samples).toBe(0);
  expect(monthly.baseline.exclusion_counts.incompatible_variable).toBeGreaterThan(0);
  await shot('blackout-pacific-monthly-period-controls', label('Observation blackout settings'));
  await shot('blackout-pacific-incompatible-quantity', label('Applied observation blackout'));

  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await open('evolution', 'arabian-sea-2024-01');
    await shot(`evolution-controls-${width}`, label('Feature evolution settings'));
    await shot(`evolution-graph-${width}`, label('Applied feature evolution'));
    await shot(`evolution-extent-${width}`, label('Evolution region extent'));
    await open('blackout');
    await button('Select one contributing profile').click();
    await apply('blackout');
    await shot(`blackout-controls-${width}`, label('Observation blackout settings'));
    await shot(`blackout-evidence-${width}`, label('Applied observation blackout'));
    await shot(`blackout-depths-${width}`, label('Blackout eligible depths'));
  }

  await page.setViewportSize({ width: 900, height: 1000 });
  await open('evolution', 'arabian-sea-2024-01');
  await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  await shot('evolution-controls-enlarged-root-text', label('Feature evolution settings'));
  await shot('evolution-graph-enlarged-root-text', label('Applied feature evolution'));
  await open('blackout');
  await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  await shot('blackout-controls-enlarged-root-text', label('Observation blackout settings'));
  await shot('blackout-evidence-enlarged-root-text', label('Applied observation blackout'));

  await checkpoint(true);
  const failures = checks.filter(check => check.overflow || check.alerts.length);
  console.log(JSON.stringify({ screenshots: checks.length, errors, consoleErrors, failures, exports }, null, 2));
  if (errors.length || consoleErrors.length || failures.length) process.exitCode = 1;
} catch (error) {
  await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true });
  await writeFile(path.join(out, 'failure.json'), JSON.stringify({ message: error.message, checks, errors, consoleErrors,
    alerts: await page.getByRole('alert').filter({ visible: true }).allTextContents() }, null, 2));
  await checkpoint(false);
  throw error;
} finally {
  await browser.close();
}
