import { chromium, expect as rawExpect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = process.env.OCEAN_TEST_URL ?? 'http://127.0.0.1:8039';
const label = process.env.OCEAN_BENCH_NAME ?? 'local';
const out = resolve(`docs/evidence/depth-atlas-${label}`);
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const expect = rawExpect.configure({ timeout: 45000 });
const errors = [], checks = [];
const library = JSON.parse(await readFile('casepacks/instruments/index.json', 'utf8'));
const profile = library.profiles.find(p => p.platform === '1902669').id;
try {
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844], ['narrow', 320, 568]]) {
    const context = await browser.newContext({ viewport: { width, height } });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(`${name}: ${e.message}`));
    await page.goto(base);
    await expect(page).toHaveTitle(/Depth Atlas/);
    await expect(page.locator('body')).toContainText('DEPTH ATLAS');
    await page.getByRole('button', { name: 'Skip tutorial', exact: true }).click();
    const globe = page.getByRole('region', { name: 'Ocean data globe' });
    await expect(globe).toBeVisible();
    await expect(page.getByLabel('Globe model case')).toBeEnabled();
    await expect(page.getByRole('link', { name: 'Depth Atlas home', exact: true })).toBeVisible();
    await expect(page.locator('.brand-light')).toBeVisible();
    await expect(page.locator('body')).not.toContainText(/Ocean Navigator/i);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    if (overflow) throw new Error(`${name}: document overflow`);
    await page.screenshot({ path: resolve(out, `${name}-globe.png`), fullPage: true });
    checks.push(`${name}: title, tutorial branding, full header name, globe, no horizontal overflow`);
    if (name === 'desktop') {
      await globe.screenshot({ path: resolve(out, 'globe.png') });
      await page.getByRole('button', { name: 'Open 3D ocean', exact: true }).click();
      await expect(page.getByLabel('Native model value')).toContainText('22.303');
      await expect(page.locator('.ocean-render-status')).toHaveText('Interactive 3D');
      await page.getByRole('button', { name: 'Cutaway', exact: true }).click();
      await page.waitForTimeout(650);
      await page.locator('.ocean-explorer').screenshot({ path: resolve(out, 'volume.png') });
      await page.getByRole('button', { name: 'Tools', exact: true }).click();
      await page.getByRole('button', { name: 'Compare', exact: true }).click();
      await page.getByLabel('Comparison model snapshot').selectOption('1');
      await page.getByLabel('Comparison profile').selectOption(profile);
      await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');
      await expect(page.getByLabel('Selected comparison sample')).toContainText('-0.152');
      await page.getByRole('button', { name: 'Expand comparison', exact: true }).click();
      await page.getByLabel('Matched profile and residual charts').screenshot({ path: resolve(out, 'comparison.png') });
      await page.getByRole('button', { name: 'Save investigation', exact: true }).filter({ visible: true }).click();
      await page.getByLabel('Investigation name', { exact: true }).fill('Depth Atlas release check');
      await page.getByRole('button', { name: 'Save on this browser', exact: true }).click();
      await expect(page.getByRole('status').filter({ hasText: 'Saved on this browser.' })).toBeVisible();
      await page.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click();
      await expect(page.locator('.replay-notice')).toContainText('Recalculation matched');
      checks.push('desktop: 3D, cutaway, 22.303 native value, 103 pairs, -0.152 residual, explicit save, exact replay');
      for (const path of ['/about', '/privacy', '/terms', '/data-access']) {
        const response = await page.goto(base + path);
        if (response.status() !== 200) throw new Error(`${path}: ${response.status()}`);
        await expect(page).toHaveTitle(/Depth Atlas/);
        await expect(page.locator('body')).not.toContainText(/Ocean Navigator/i);
        if (path === '/about') {
          await expect(page.locator('body')).toContainText('Website creator & operator');
          await expect(page.locator('body')).toContainText('Adwita Kurle');
        }
      }
      checks.push('static about, privacy, terms and data access pages');
    }
    await context.close();
  }
} catch (error) { errors.push(String(error)); }
finally {
  await browser.close();
  const result = { at: new Date().toISOString(), base, release: '0.17.1', passed: errors.length === 0, checks, errors };
  await writeFile(resolve(out, 'browser.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  if (!result.passed) process.exitCode = 1;
}
