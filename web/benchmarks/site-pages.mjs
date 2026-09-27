import { chromium, webkit, expect } from '../node_modules/@playwright/test/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = process.env.OCEAN_TEST_URL || 'http://127.0.0.1:8022';
const output = resolve(process.env.OCEAN_PAGE_EVIDENCE || 'docs/evidence/site-pages-local');
await mkdir(output, { recursive: true });
const checks = [], errors = [];
const pages = [['about', 'About Us'], ['privacy', 'Privacy Policy'], ['terms', 'Terms & Conditions']];
for (const [engineName, engine, viewport] of [
  ['chromium-desktop', chromium, { width: 1440, height: 900 }],
  ['chromium-small', chromium, { width: 320, height: 568 }],
  ['webkit-mobile', webkit, { width: 390, height: 844 }],
]) {
  const browser = await engine.launch();
  try {
    const context = await browser.newContext({ viewport, javaScriptEnabled: false });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', error => errors.push({ engineName, message: error.message }));
    page.on('console', msg => { if (msg.type() === 'error') errors.push({ engineName, message: msg.text() }); });
    for (const [path, title] of pages) {
      console.log(`${engineName} /${path}`);
      const response = await page.goto(`${base}/${path}`);
      expect(response.status()).toBe(200);
      await expect(page.getByRole('heading', { name: title, level: 1, exact: true })).toBeVisible();
      // This Windows WebKit build does not tab to links. Check native activation
      // from explicit focus there; Chromium checks sequential keyboard entry.
      if (engineName.startsWith('webkit')) await page.getByRole('link', { name: 'Skip to content' }).focus();
      else await page.keyboard.press('Tab');
      await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page.locator('#document')).toBeFocused();
      const email = page.getByRole('link', { name: 'ranadegaurav30@gmail.com', exact: true });
      expect(await email.count()).toBeGreaterThan(0);
      for (const link of await email.all()) await expect(link).toHaveAttribute('href', 'mailto:ranadegaurav30@gmail.com');
      const main = await page.locator('main').innerText();
      expect(main).not.toContain('\u2014');
      expect(main).not.toContain('\u00c2\u00b7');
      expect(main).toContain('Gaurav Ranade');
      if (path === 'about') {
        await expect(page.locator('.team-list li')).toHaveCount(6);
        expect(main).toContain('Tanisha Natrajan');
        expect(main).toContain('150123');
      }
      const fit = await page.evaluate(() => ({
        width: innerWidth, content: document.documentElement.scrollWidth,
        background: getComputedStyle(document.body).backgroundColor,
      }));
      expect(fit.content).toBeLessThanOrEqual(fit.width + 1);
      expect(fit.background).toBe('rgb(11, 22, 33)');
      await page.screenshot({ path: `${output}/${engineName}-${path}-top.png` });
      if (path === 'about') {
        await page.locator('#people').scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${output}/${engineName}-team.png` });
      }
      if (path !== 'about') {
        await page.getByRole('navigation', { name: 'On this page' }).getByRole('link').last().click();
        await expect(page.getByRole('heading', { name: path === 'privacy' ? 'Your choices and contact' : 'Questions and issue reports' })).toBeInViewport();
      }
      const footer = page.getByRole('navigation', { name: 'Site information' });
      await footer.scrollIntoViewIfNeeded();
      await expect(footer.getByRole('link', { name: title, exact: true })).toHaveAttribute('aria-current', 'page');
      for (const [slug, label] of [...pages, ['data-access', 'Use the data'], ['third-party-notices.txt', 'Source & software credits']]) {
        await expect(footer.getByRole('link', { name: label, exact: true })).toHaveAttribute('href', `/${slug}`);
      }
      await page.screenshot({ path: `${output}/${engineName}-${path}-footer.png` });
      if (engineName === 'chromium-small') {
        await page.evaluate(() => document.documentElement.style.setProperty('font-size', '200%', 'important'));
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
        await page.locator('h1').scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${output}/enlarged-${path}.png` });
      }
      await page.emulateMedia({ media: 'print' });
      expect(await page.locator('.legal-header').isVisible()).toBe(false);
      expect(await page.locator('main p').first().evaluate(el => getComputedStyle(el).color)).toBe('rgb(0, 0, 0)');
      await page.emulateMedia({ media: 'screen' });
      checks.push({ engineName, path, noJavaScript: true, keyboardEntry: engineName.startsWith('webkit') ? 'Explicit link focus, Enter activates skip target; default link tabbing unavailable in this engine' : 'Tab then Enter', fit, passed: true });
    }
    await context.close();
    if (engineName !== 'chromium-small') {
      const appContext = await browser.newContext({ viewport });
      const app = await appContext.newPage();
      app.on('pageerror', error => errors.push({ engineName, message: error.message }));
      await app.goto(`${base}/about`);
      await app.getByRole('link', { name: 'Back to workspace', exact: true }).click();
      await app.getByRole('button', { name: 'Skip tutorial', exact: true }).click();
      await expect(app.getByLabel('Native model value')).toContainText('22.303', { timeout: 30000 });
      await app.getByRole('navigation', { name: 'Site information' }).getByRole('link', { name: 'About Us', exact: true }).click();
      await expect(app.getByRole('heading', { name: 'About Us', exact: true, level: 1 })).toBeVisible();
      await app.getByRole('navigation', { name: 'Site information' }).getByRole('link', { name: 'Privacy Policy', exact: true }).click();
      await expect(app.getByRole('heading', { name: 'Privacy Policy', exact: true, level: 1 })).toBeVisible();
      await app.getByRole('navigation', { name: 'Site information' }).getByRole('link', { name: 'Terms & Conditions', exact: true }).click();
      await expect(app.getByRole('heading', { name: 'Terms & Conditions', exact: true, level: 1 })).toBeVisible();
      checks.push({ engineName, navigation: 'About > workspace > About > Privacy > Terms', passed: true });
      await appContext.close();
    }
  } catch (error) {
    checks.push({ engineName, passed: false, error: String(error) });
  } finally { await browser.close(); }
}
await writeFile(`${output}/checks.json`, JSON.stringify({ base, checkedAt: new Date().toISOString(), checks, errors }, null, 2));
console.log(JSON.stringify({ checks: checks.length, failures: checks.filter(c => !c.passed).length, errors: errors.length, output }));
if (checks.some(c => !c.passed) || errors.length) process.exitCode = 1;
