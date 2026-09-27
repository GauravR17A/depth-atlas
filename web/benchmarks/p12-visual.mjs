import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const base = process.argv[2] ?? 'http://127.0.0.1:8010';
const out = path.resolve(process.argv[3] ?? '../docs/evidence/p12-visual-local');
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
async function open(caseId = 'bay-bengal-2024-01') {
  await page.goto(base);
  await page.getByLabel('Study case', { exact: true }).selectOption(caseId);
  await page.getByRole('button', { name: 'Heat & Depth', exact: true }).click();
  await page.getByLabel('Applied heat analysis', { exact: true }).waitFor({ timeout: 60000 });
  await page.getByRole('button', { name: 'Cancel analysis', exact: true }).waitFor({ state: 'hidden' });
}

try {
  for (const [caseId, label] of [['bay-bengal-2024-01', 'bay'], ['arabian-sea-2024-01', 'arabian']]) {
    await open(caseId);
    await shot(label + '-source-locations', page.locator('.heat-location-map'));
    await shot(label + '-surface-event', page.locator('.heat-surface'));
    await shot(label + '-event-definition', page.locator('.heat-events-grid'));
    await shot(label + '-depth-evidence', page.getByLabel('Linked depth evidence', { exact: true }));
  }
  await open();
  for (const variable of ['salinity', 'density', 'gradient', 'stratification']) {
    await page.getByLabel('Heat depth variable', { exact: true }).selectOption(variable);
    await shot('bay-' + variable, page.locator('.heat-depth-body'));
  }
  await page.getByText('Inspect native profile and layer diagnostics', { exact: true }).click();
  await shot('native-layer-tables', page.getByLabel('Heat model depth profile', { exact: true }).locator('.heat-table-details'));
  await page.getByLabel('Heat event year', { exact: true }).selectOption('2023');
  const yearResponse = page.waitForResponse(response => response.url().endsWith('/heat/analyse') && response.status() === 200);
  await page.getByRole('button', { name: 'Analyse surface record', exact: true }).click();
  const yearResult = await (await yearResponse).json();
  await page.getByRole('button', { name: 'Cancel analysis', exact: true }).waitFor({ state: 'hidden' });
  const outside = yearResult.events.find(event => !event.depth_overlap);
  if (!outside) throw new Error('No real event without depth overlap is available for this intended visual check.');
  await page.getByLabel('Detected surface event', { exact: true }).selectOption(outside.id);
  await page.getByRole('button', { name: 'Cancel analysis', exact: true }).waitFor({ state: 'hidden' });
  await page.getByText('Depth evidence is unavailable for this selection', { exact: true }).waitFor();
  await shot('2023-unavailable-depth', page.getByLabel('Linked depth evidence', { exact: true }));
  for (const width of [320, 390, 800]) {
    await page.setViewportSize({ width, height: 900 }); await open();
    await shot('workspace-' + width, page.getByLabel('Heat and Depth Lab', { exact: true }));
    if (width === 320) await shot('surface-320', page.locator('.heat-surface'));
    if (width === 390) await shot('depth-390', page.locator('.heat-depth-body'));
  }
  await page.setViewportSize({ width: 900, height: 1000 });
  await page.addStyleTag({ content: 'html{font-size:200% !important}' });
  await shot('enlarged-text', page.getByLabel('Heat and Depth Lab', { exact: true }));
  await writeFile(path.join(out, 'checks.json'), JSON.stringify({ base, checks, errors, complete: true }, null, 2));
  console.log(JSON.stringify({ screenshots: checks.length, errors, overflow: checks.filter(check => check.overflow), alerts: checks.filter(check => check.alerts.length) }, null, 2));
  if (errors.length || checks.some(check => check.overflow || check.alerts.length)) process.exitCode = 1;
} catch (error) {
  await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true });
  await writeFile(path.join(out, 'failure.json'), JSON.stringify({ message: error.message, checks, errors, alerts: await page.getByRole('alert').filter({ visible: true }).allTextContents() }, null, 2));
  throw error;
} finally { await browser.close(); }
