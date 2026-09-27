import { enterWorkspace, dismissIntroduction } from './ux-helpers';
import { expect, test } from '@playwright/test';

test('an open workspace offers a reload when the server release changes', async ({ page }) => {
  await page.clock.install();
  await enterWorkspace(page);
  await expect(page.getByText('Service connected', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Case details', exact: true })).toBeVisible();
  // A healthy but incompatible response from a later deployment must be detected
  // before the old browser client attempts to parse it.
  await page.route('**/api/health', route => route.fulfill({
    status: 200, contentType: 'application/json', headers: { 'X-Ocean-App-Version': 'future-release' },
    body: JSON.stringify({ changed_contract: true }),
  }));
  await page.clock.fastForward(31_000);
  await expect(page.getByText('Update available', { exact: true })).toBeVisible();
  await expect(page.locator('.service-alert')).toContainText('This workspace has been updated.');
  await expect(page.getByText('Service unavailable', { exact: true })).toHaveCount(0);
  await page.unroute('**/api/health');
  await page.getByRole('button', { name: 'Reload workspace', exact: true }).click();await dismissIntroduction(page);
  await expect(page.getByText('Service connected', { exact: true })).toBeVisible();
  await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();
  await expect(page.getByRole('button', { name: 'Case details', exact: true })).toBeVisible();
});

test('catalogue recovers automatically after a temporary failure', async ({ page }) => {
  await page.clock.install();
  await page.route('**/api/catalog', route => route.fulfill({
    status: 503, contentType: 'application/json',
    body: JSON.stringify({ error: { message: 'Temporary catalogue failure.' } }),
  }));
  await page.goto('/');await dismissIntroduction(page);
  await expect(page.getByText('Service unavailable', { exact: true })).toBeVisible();
  await page.unroute('**/api/catalog');
  await page.clock.fastForward(31_000);
  await expect(page.getByText('Service connected', { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();
  await expect(page.getByRole('button', { name: 'Case details', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('invalid JSON is described as an unreadable response, not a connection failure', async ({ page }) => {
  await page.route('**/api/catalog', route => route.fulfill({ status: 200, contentType: 'text/html', body: '<html>Unexpected upstream page</html>' }));
  await page.goto('/');await dismissIntroduction(page);
  await expect(page.getByText('Data unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('The service returned an unreadable response.');
  await expect(page.getByRole('button', { name: 'Reload workspace', exact: true })).toBeVisible();
  await expect(page.getByText('Service unavailable', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Case details', exact: true })).toHaveCount(0);
});
