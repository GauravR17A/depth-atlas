import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const base = process.argv[2] ?? 'http://127.0.0.1:8012', out = path.resolve(process.argv[3] ?? '../docs/evidence/p13-visual-local');
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true }), checks = [], errors = [];
const page = await browser.newPage({ viewport: { width: 1536, height: 1000 } });
page.on('pageerror', error => errors.push(error.message));
await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true }));
async function shot(name, locator = page) {
  await locator.screenshot({ path: path.join(out, name + '.png') });
  checks.push({ name, overflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), alerts: await page.getByRole('alert').filter({ visible: true }).allTextContents() });
  await writeFile(path.join(out, 'checks.json'), JSON.stringify({ base, checks, errors, complete: false }, null, 2));
}
async function open() {
  await page.goto(base); await page.getByRole('button', { name: 'Climate', exact: true }).click();
  await page.getByLabel('Applied climate comparison', { exact: true }).waitFor({ timeout: 60000 });
  await page.getByRole('button', { name: 'Cancel comparison', exact: true }).waitFor({ state: 'hidden' });
  await expect(page.getByRole('button', { name: 'Ocean data', exact: true })).toBeEnabled();
  await page.evaluate(() => document.fonts.ready);
}
async function apply(event, reference = 'son-2013', period = 'SON') {
  await page.getByLabel('Selected climate event', { exact: true }).selectOption(event);
  await page.getByLabel('Reference climate event', { exact: true }).selectOption(reference);
  await page.getByLabel('Climate calendar window', { exact: true }).selectOption(period);
  await page.getByRole('button', { name: 'Compare historical fields', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel comparison', exact: true }).waitFor({ state: 'hidden' });
}
try {
  await open();
  await shot('historical-event-cards', page.locator('.climate-event-cards'));
  await shot('el-nino-neutral-anomaly', page.getByLabel('Pacific climate sections', { exact: true }));
  await shot('synchronized-native-profiles', page.getByLabel('Synchronized climate profiles', { exact: true }));
  await shot('iod-episode-and-index', page.getByLabel('Separate Indian Ocean context', { exact: true }));
  await page.getByText('Compare Indian Ocean depth sections for the same dates', { exact: true }).click();
  await shot('indian-anomaly-context', page.locator('.climate-indian-sections'));
  await page.getByLabel('Climate section quantity', { exact: true }).selectOption('temperature');
  await shot('potential-temperature', page.getByLabel('Pacific climate sections', { exact: true }));
  await page.getByLabel('Climate section quantity', { exact: true }).selectOption('difference');
  await shot('selected-minus-reference', page.getByLabel('Pacific climate sections', { exact: true }));
  await apply('son-2015', 'son-2015');
  await shot('same-event-zero-difference', page.getByLabel('Pacific climate sections', { exact: true }));
  await apply('son-2022'); await page.getByLabel('Climate section quantity', { exact: true }).selectOption('anomaly');
  await shot('la-nina-neutral-anomaly', page.getByLabel('Pacific climate sections', { exact: true }));
  await shot('negative-iod-context', page.locator('.climate-iod-cards'));
  await apply('son-2013', 'son-2022', '09');
  await shot('september-aligned-comparison', page.getByLabel('Pacific climate sections', { exact: true }));
  await shot('original-profile-context', page.getByLabel('Climate observation context', { exact: true }));
  await page.getByText('Methods, index versions and source records', { exact: true }).click();
  await shot('source-definitions', page.locator('.climate-methods'));
  await open(); await page.getByRole('button', { name: 'Explore this Pacific case', exact: true }).first().click();
  await page.getByLabel('Graphics quality', { exact: true }).selectOption('balanced');
  await page.getByText('Interactive 3D', { exact: true }).waitFor({ timeout: 60000 });
  await page.waitForFunction(() => document.querySelector('.ocean-webgl')?.getAttribute('data-rendered') === 'volume');
  await shot('pacific-shared-3d', page.getByLabel('Scientific ocean explorer', { exact: true }));
  await shot('pacific-case-sidebar', page.getByRole('complementary', { name: 'Investigation controls', exact: true }));
  await page.getByRole('button', { name: 'Cutaway', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.ocean-webgl')?.getAttribute('data-cut-progress') === '1.0000' && document.querySelector('.ocean-webgl')?.getAttribute('data-transitioning') === 'false');
  await shot('pacific-shared-cutaway', page.getByLabel('Scientific ocean explorer', { exact: true }));
  await page.getByRole('button', { name: 'Instruments', exact: true }).click();
  await page.getByLabel('Observed sample value', { exact: true }).waitFor({ timeout: 30000 });
  await shot('pacific-original-instrument', page.getByLabel('Instruments and profiles', { exact: true }));
  await page.getByRole('button', { name: 'Find structures', exact: true }).click();
  await page.getByRole('button', { name: 'Section through selected region', exact: true }).click();
  await page.getByRole('img', { name: 'Vertical section along the drawn line', exact: true }).waitFor({ timeout: 30000 });
  await shot('pacific-feature-section', page.locator('.feature-section-view'));
  for (const width of [320, 390, 800]) {
    await page.setViewportSize({ width, height: 900 }); await open();
    await shot('workspace-' + width, page.getByLabel('Climate Event Lab', { exact: true }));
    if (width === 320) await shot('pacific-320', page.getByLabel('Pacific climate sections', { exact: true }));
    if (width === 390) await shot('profiles-390', page.getByLabel('Synchronized climate profiles', { exact: true }));
  }
  await page.setViewportSize({ width: 900, height: 1000 }); await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  await shot('enlarged-text', page.getByLabel('Climate Event Lab', { exact: true }));
  await writeFile(path.join(out, 'checks.json'), JSON.stringify({ base, checks, errors, complete: true }, null, 2));
  console.log(JSON.stringify({ screenshots: checks.length, errors, overflow: checks.filter(check => check.overflow), alerts: checks.filter(check => check.alerts.length) }, null, 2));
  if (errors.length || checks.some(check => check.overflow || check.alerts.length)) process.exitCode = 1;
} catch (error) {
  await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true });
  await writeFile(path.join(out, 'failure.json'), JSON.stringify({ message: error.message, checks, errors, alerts: await page.getByRole('alert').filter({ visible: true }).allTextContents() }, null, 2)); throw error;
} finally { await browser.close(); }
