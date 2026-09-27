import { test, expect } from '@playwright/test';
import { enterWorkspace, openTool } from './ux-helpers';

test('a missing entry shows recovery and an explicit reload opens the actual app', async ({ page }) => {
  await page.route('**/assets/workspace-*.js', route => route.fulfill({ status: 404, body: 'Missing entry' }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'The workspace could not load' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const retry = page.getByRole('link', { name: 'Reload workspace', exact: true }).filter({ visible: true });
  await expect(retry).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('missing-entry.png') });
  await page.unroute('**/assets/workspace-*.js');
  await retry.click();
  await page.getByRole('button', { name: 'Skip tutorial', exact: true }).click();
  await page.getByRole('button', { name: 'Open 3D ocean', exact: true }).click();
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await expect(page.locator('#startup-screen')).toHaveCount(0);
  await expect(page.locator('#startup-update')).toBeHidden();
  expect(new URL(page.url()).searchParams.has('_startup_recovered')).toBe(false);
});

test('the retired entry URL recovers stale HTML once and preserves shared URL context', async ({ page }) => {
  let documents = 0;
  await page.route('**/*', async route => {
    if (route.request().isNavigationRequest()) {
      documents++;
      if (documents === 1) {
        await route.fulfill({ contentType: 'text/html', body: '<!doctype html><div id="root"></div><script type="module" src="/assets/workspace-fwVeVJXC.js"></script>' });
        return;
      }
    }
    await route.continue();
  });
  await page.goto('/?release=0.14.1&context=keep#keep-fragment');
  await expect(page.getByRole('heading', { name: 'See it happen. Then try it.' })).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.has('_startup_recovered')).toBe(false);
  expect(documents).toBe(2);
  const url = new URL(page.url());
  expect(url.searchParams.get('context')).toBe('keep');
  expect(url.hash).toBe('#keep-fragment');
  expect(url.searchParams.has('release')).toBe(false);
});

test('persistent stale HTML stops with a usable link instead of an automatic reload loop', async ({ page }) => {
  let documents = 0;
  await page.route('**/*', async route => {
    if (route.request().isNavigationRequest()) {
      documents++;
      await route.fulfill({ contentType: 'text/html', body: '<!doctype html><div id="root"></div><script type="module" src="/assets/workspace-fwVeVJXC.js"></script>' });
    } else await route.continue();
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'The workspace needs a fresh page' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Reload workspace' })).toBeVisible();
  expect(documents).toBe(2);
});

test('a failed lazy tool retains the workspace and asks before losing unsaved work', async ({ page }) => {
  await enterWorkspace(page);
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByLabel('Explorer depth').selectOption('27');
  await page.route('**/assets/WiderWorkspace-*.js', route => route.fulfill({ status: 404, body: 'Missing tool' }));
  await openTool(page, 'Open wider ocean coverage');
  await expect(page.getByRole('heading', { name: 'Regional tools could not load' })).toBeVisible();
  await expect(page.locator('#startup-update')).toBeVisible();
  await expect(page.locator('#startup-update')).toContainText('Unsaved work in this tab will be lost.');
  await openTool(page, 'Ocean explorer');
  await expect(page.getByLabel('Explorer depth')).toHaveValue('27');
});

test('the independent team credits are consistent across public pages', async ({ page }) => {
  for (const path of ['/about', '/privacy', '/terms']) {
    await page.goto(path);
    await expect(page.locator('main')).toContainText('Website creator & operator');
    await expect(page.locator('main')).toContainText('Gaurav Ranade');
    await expect(page.locator('main')).not.toContainText(/university|affiliation|Vishwanath|MIT World/i);
    if (path === '/about') {
      await expect(page.locator('.team-list li').filter({ hasText: 'Adwita Kurle' })).toContainText('Team leader');
    }
  }
});
