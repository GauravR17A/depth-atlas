import { enterWorkspace, openTool } from './ux-helpers';
import { expect, test } from '@playwright/test';

test('real service, region navigation, evidence and truthful unavailable controls', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await enterWorkspace(page);
  await expect(page.getByText('Service connected', { exact: true })).toBeVisible();
  await openTool(page,'Geographic context');
  await expect(page.getByRole('group',{name:'Interactive data locations'})).toBeVisible();
  await expect(page.getByLabel('Globe model case')).toHaveValue('bay-bengal-2024-01');
  await expect(page.getByLabel('Located data details')).toContainText('2024');
  await page.getByLabel('Globe model case').selectOption('pacific-godas-2013-son');
  await page.getByRole('button',{name:'Open this 3D ocean'}).click();
  await expect(page.getByLabel('Study case')).toHaveValue('pacific-godas-2013-son');
  await expect(page.getByLabel('Variable', { exact: true })).toHaveValue('temperature');
  await expect(page.getByLabel('Variable', { exact: true }).locator('option')).toHaveCount(1);
  await openTool(page,'Geographic context');
  await expect(page.getByLabel('Located data details')).toContainText('2013');
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Map', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Zoom data globe in', exact: true }).click();
  await page.getByRole('button', { name: 'Reset data globe' }).click();
  await page.getByRole('button', { name: 'Globe', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Globe', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button',{name:'Open this 3D ocean'}).click();
  const showEvidence = page.getByRole('button', { name: 'Sources', exact: true });
  if (await showEvidence.isVisible()) await showEvidence.click();
  await expect(page.getByRole('heading', { name: 'Natural Earth coastlines' })).toBeVisible();
  await page.getByRole('button', { name: 'Close evidence inspector', exact: true }).click();
  await expect(page.getByRole('complementary', { name: 'Evidence inspector' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Sources', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Natural Earth coastlines' })).toBeVisible();
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('guide supports keyboard focus and Escape', async ({ page }) => {
  await enterWorkspace(page);
  const trigger = page.getByRole('button', { name: 'Quick guide' });
  // The icon-only mobile variant has the same accessible name.
  await trigger.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('heading',{name:'See it happen. Then try it.'})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('failed catalogue has a useful recovery path', async ({ page }) => {
  await page.route('**/api/catalog', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'unavailable', message: 'Temporarily unavailable.', request_id: 'browser-test' } }) }));
  await page.goto('/');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Temporarily unavailable.');
  await expect(page.getByRole('button',{name:'Open 3D ocean',exact:true})).toHaveCount(0);
  await page.unroute('**/api/catalog');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  // The intercepted failure returns immediately; the explicit retry uses the real catalogue.
  await expect(page.getByText('Service connected', { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('button',{name:'Open 3D ocean',exact:true})).toBeEnabled();
  await expect(page.getByLabel('Globe model case')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('malformed responses cannot invent available ocean data', async ({ page }) => {
  await page.route('**/api/catalog', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cases: [{ name: 'unsupported data' }] }) }));
  await page.goto('/');await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('not compatible');
  await expect(page.getByRole('button',{name:'Open 3D ocean',exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Globe model case')).toHaveCount(0);
});
