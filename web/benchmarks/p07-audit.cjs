const { chromium, webkit } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.OCEAN_TEST_URL || 'http://127.0.0.1:8003';
const prefix = process.env.OCEAN_BENCH_NAME || 'p07-audit-initial';
const out = path.resolve(__dirname, '../../docs/evidence');
const library = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../casepacks/instruments/index.json'), 'utf8'));
const result = { base, checkedUtc: new Date().toISOString(), method: 'Independent existing-component visual and interaction audit in Windows headless browsers. Mobile widths are emulated; no unfamiliar-person usability study.', checks: [], screenshots: [], errors: [] };
async function check(name, work) { try { const detail = await work(); result.checks.push({ name, passed: true, detail }); } catch (e) { result.checks.push({ name, passed: false, error: e.message }); } fs.writeFileSync(path.join(out, `${prefix}.json`), JSON.stringify(result, null, 2) + '\n'); }
async function capture(page, name) {
  const file = `${prefix}-${name}.png`;
  await page.screenshot({ path: path.join(out, file), fullPage: true });
  result.screenshots.push(file);
  const layout = await page.evaluate(() => ({ viewport: innerWidth, width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, text: document.body.innerText }));
  assert.ok(layout.width <= layout.viewport, `Horizontal page overflow: ${layout.width}/${layout.viewport}`);
  assert.ok(!layout.text.includes('\u2014'), 'Authored rendered copy contains an em dash.');
  return { viewport: layout.viewport, width: layout.width, height: layout.height };
}
async function waitNative(page) { await page.getByLabel('Native model value').filter({ hasText: /22\.303|28\.001/ }).waitFor({ timeout: 30000 }); }
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1536, height: 960 } });
  page.on('pageerror', error => result.errors.push({ browser: 'chromium', error: error.message }));
  await check('desktop initial scientific view', async () => { await page.goto(base); await waitNative(page); return capture(page, 'desktop-volume'); });
  await check('quick guide keyboard return', async () => { const trigger = page.getByRole('button', { name: 'Quick guide', exact: true }); await trigger.click(); await page.getByRole('dialog').waitFor(); await capture(page, 'desktop-guide'); await page.keyboard.press('Escape'); assert.equal(await trigger.evaluate(e => e === document.activeElement), true); });
  await check('optional 3D cutaway', async () => { await page.getByLabel('Graphics quality').selectOption('balanced'); await page.getByRole('button', { name: 'Cutaway', exact: true }).click(); await page.locator('.ocean-webgl[data-cut-progress="1.0000"]').waitFor(); return capture(page, 'desktop-cutaway'); });
  for (const mode of ['Depth slice', 'Section', 'Isosurface', 'Current vectors']) await check(`desktop ${mode}`, async () => { await page.getByRole('button', { name: mode, exact: true }).click(); await page.getByLabel('Native model value').filter({ hasText: /\d/ }).waitFor(); return capture(page, 'desktop-' + mode.toLowerCase().replaceAll(' ', '-')); });
  await check('derived field and 2D fallback', async () => { await page.getByLabel('Variable', { exact: true }).selectOption('horizontal_kinetic_energy'); await page.getByLabel('Native model value').filter({ hasText: 'm\u00b2/s\u00b2' }).waitFor(); await page.getByLabel('Graphics quality').selectOption('basic'); return capture(page, 'desktop-derived-basic'); });
  await check('missing-depth explanation', async () => { await page.getByRole('button', { name: 'Depth slice', exact: true }).click(); await page.getByLabel('Explorer depth').selectOption('39'); await page.getByLabel('Native model value').filter({ hasText: 'No value at this depth' }).waitFor(); return capture(page, 'desktop-missing'); });
  await check('colour validation and controls', async () => { await page.getByText('Colour, depth and display settings', { exact: true }).click(); await page.getByLabel('Colour scale').selectOption('log'); await page.getByRole('alert').filter({ hasText: 'Log scale needs' }).waitFor(); await capture(page, 'desktop-controls'); await page.getByLabel('Colour minimum').fill('0.001'); await page.getByLabel('Layer opacity').fill('0.25'); await page.getByLabel('Colour scale').selectOption('linear'); });
  await check('Argo profile', async () => { await page.getByRole('button', { name: 'Open instruments', exact: true }).click(); await page.getByLabel('Observed sample value').waitFor(); return capture(page, 'desktop-argo'); });
  for (const instrument of ['glider', 'ctd', 'bgc']) await check(`${instrument} profile and provenance`, async () => { const item = library.profiles.find(p => p.instrument === instrument); await page.getByLabel('Observation collection').selectOption(item.collection); await page.getByLabel('Instrument profile').selectOption(item.id); await page.getByLabel('Observed sample value').waitFor(); if (instrument === 'bgc') await page.getByLabel('Profile variable').selectOption('oxygen'); return capture(page, `desktop-${instrument}`); });
  await check('import explainability', async () => { await page.getByRole('button', { name: 'Import observations', exact: true }).click(); return capture(page, 'desktop-import'); });
  await check('useful comparison path', async () => { await page.getByRole('button', { name: 'Compare', exact: true }).click(); await page.getByLabel('Comparison model snapshot').selectOption('1'); await page.getByLabel('Comparison profile').selectOption(library.profiles.find(p => p.platform === '1902669').id); await page.getByLabel('Eligible comparison count').filter({ hasText: '103 / 103' }).waitFor(); return capture(page, 'desktop-comparison'); });
  await check('coverage view', async () => { await page.getByRole('button', { name: 'Evidence coverage', exact: true }).click(); await page.getByRole('heading', { name: 'Where eligible observations exist' }).waitFor(); return capture(page, 'desktop-coverage'); });
  await check('geographic context and planned coverage', async () => { await page.getByRole('button', { name: 'Ocean explorer', exact: true }).click(); await page.getByLabel('Region', { exact: true }).selectOption('arabian-sea'); await page.getByRole('heading', { name: 'Arabian Sea', exact: true }).waitFor(); return capture(page, 'desktop-planned-region'); });
  for (const route of ['data-access', 'privacy', 'terms']) await check(route + ' page', async () => { const response = await page.goto(base + '/' + route); assert.equal(response.status(), 200); return capture(page, 'desktop-' + route); });
  await check('favicon', async () => { await page.goto(base); const href = await page.locator('link[rel="icon"]').getAttribute('href'); const response = await page.request.get(new URL(href, base).href); assert.equal(response.status(), 200); return { href, type: response.headers()['content-type'] }; });
  await browser.close();
  for (const config of [{ name: 'mobile', width: 390, height: 844, scale: 1 }, { name: 'narrow', width: 320, height: 740, scale: 1 }, { name: 'large-text', width: 768, height: 1024, scale: 2 }, { name: 'webkit', width: 1440, height: 900, scale: 1 }]) {
    const engine = config.name === 'webkit' ? webkit : chromium, b = await engine.launch(), p = await b.newPage({ viewport: { width: config.width, height: config.height } });
    p.on('pageerror', error => result.errors.push({ browser: config.name, error: error.message }));
    await check(config.name + ' explorer', async () => { await p.goto(base); await waitNative(p); if (config.scale === 2) await p.addStyleTag({ content: 'html { font-size: 200% !important; }' }); return capture(p, config.name + '-explorer'); });
    await check(config.name + ' instruments', async () => { await p.getByRole('button', { name: 'Open instruments', exact: true }).click(); await p.getByLabel('Observed sample value').waitFor(); return capture(p, config.name + '-instruments'); });
    await check(config.name + ' comparison', async () => { await p.getByRole('button', { name: 'Compare', exact: true }).click(); await p.getByLabel('Comparison model snapshot').selectOption('1'); await p.getByLabel('Comparison profile').selectOption(library.profiles.find(x => x.platform === '1902669').id); await p.getByLabel('Eligible comparison count').filter({ hasText: '103 / 103' }).waitFor(); return capture(p, config.name + '-comparison'); });
    await b.close();
  }
  fs.writeFileSync(path.join(out, `${prefix}.json`), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ checks: result.checks.length, failures: result.checks.filter(c => !c.passed), errors: result.errors, screenshots: result.screenshots.length }));
})().catch(e => { console.error(e); process.exitCode = 1; });
