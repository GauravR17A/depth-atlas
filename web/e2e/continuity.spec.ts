import { enterWorkspace, displaySettings, openTool, extraView } from './ux-helpers';
import { expect, test } from '@playwright/test';

async function noPreload(page: import('@playwright/test').Page) {
  await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true }));
}

test('depth and cutaway changes reuse source data and GPU resources', async ({ page }) => {
  await noPreload(page);
  const requests: string[] = []; page.on('request', r => { if (r.url().includes('/subset?')) requests.push(r.url()); });
  await enterWorkspace(page); await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('balanced');
  const scene = page.locator('.ocean-webgl');
  await expect(scene).toHaveAttribute('data-rendered', 'volume');
  const before = await scene.evaluate(e => ({ rebuilds: e.dataset.rebuilds, textures: e.dataset.textures, camera: e.dataset.camera }));
  const count = requests.length;
  for (const z of ['27', '32', '19']) {
    await page.getByLabel('Explorer depth').selectOption(z);
    await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
  }
  expect(requests.length).toBe(count);
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await expect(page.getByRole('button', { name: 'Cutaway', exact: true })).toHaveAttribute('aria-pressed', 'false');
  const progress = await page.evaluate(async () => {
    (document.querySelector('[aria-label="Cutaway"]') as HTMLButtonElement).click();
    const samples: number[] = []; const start = performance.now();
    await new Promise<void>(resolve => { function frame() {
      samples.push(Number((document.querySelector('.ocean-webgl') as HTMLElement).dataset.cutProgress));
      if (performance.now() - start < 1100) requestAnimationFrame(frame); else resolve();
    } requestAnimationFrame(frame); });
    return samples;
  });
  expect(progress.some(p => p > 0 && p < 1)).toBe(true);
  await expect(scene).toHaveAttribute('data-cut-progress', '1.0000');
  await expect(scene).toHaveAttribute('data-transitioning', 'false');
  await expect(scene).toHaveAttribute('data-rebuilds', before.rebuilds!);
  await expect(scene).toHaveAttribute('data-textures', before.textures!);
  await expect(scene).toHaveAttribute('data-camera', before.camera!);
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
  expect(requests.length).toBe(count);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Cutaway', exact: true }).click();
  await expect(scene).toHaveAttribute('data-cut-progress', '0.0000');
  await expect(scene).toHaveAttribute('data-transitioning', 'false');
});

test('slow field updates retain a correctly labelled scene and cached revisits need no loading', async ({ page }) => {
  await noPreload(page);
  await enterWorkspace(page); await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
  let release!: () => void; const gate = new Promise<void>(r => release = r);
  await page.route('**/subset?*', async route => {
    if (route.request().url().includes('variable=salinity')) await gate;
    await route.continue();
  });
  await page.getByLabel('Variable', { exact: true }).selectOption('salinity');
  await expect(page.locator('.ocean-update')).toContainText('Showing temperature');
  await expect(page.getByRole('img', { name: 'Scientific depth section' })).toBeVisible();
  await expect(page.locator('.ocean-legend h3')).toContainText('Temperature');
  await expect(page.locator('.ocean-state')).toHaveCount(0);
  release();
  await expect(page.getByLabel('Native model value')).toContainText('psu');
  await expect(page.locator('.ocean-legend h3')).toContainText('Salinity');
  const later: string[] = []; page.on('request', r => { if (r.url().includes('/subset?')) later.push(r.url()); });
  await page.getByLabel('Variable', { exact: true }).selectOption('temperature');
  await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await page.getByLabel('Variable', { exact: true }).selectOption('salinity');
  await expect(page.getByLabel('Native model value')).toContainText('psu');
  expect(later).toEqual([]);
});

test('failed next snapshot keeps the previous timestamp and can recover', async ({ page }) => {
  await noPreload(page);
  await enterWorkspace(page); await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
  await page.route('**/subset?*', route => route.request().url().includes('time_index=6') ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Snapshot unavailable.' } }) }) : route.continue());
  await page.getByLabel('Ocean timestamp').selectOption('6');
  await expect(page.locator('.ocean-update')).toContainText('Snapshot unavailable.');
  await expect(page.locator('.ocean-heading')).toContainText('07 Jan 2024, 00:00');
  await expect(page.locator('.ocean-viewport')).toHaveAttribute('data-shown-time', '2024-01-07T00:00:00Z');
  await expect(page.getByRole('img', { name: 'Scientific depth section' })).toBeVisible();
  await expect(page.getByLabel('Native model value')).toContainText('Waiting for field');
  await page.unroute('**/subset?*'); await page.getByRole('button', { name: 'Retry ocean field' }).click();
  await expect(page.locator('.ocean-heading')).toContainText('10 Jan 2024, 00:00');
  await expect(page.locator('.ocean-update')).toHaveCount(0);
});

test('geographic context preserves the explorer and camera instead of recreating it', async ({ page }) => {
  await noPreload(page);
  await enterWorkspace(page); await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('balanced');
  await page.getByLabel('Explorer depth').selectOption('27');
  await page.getByRole('button', { name: 'Rotate ocean right', exact: true }).click();
  const scene = page.locator('.ocean-webgl');
  await scene.evaluate(e => { (e as HTMLElement & { retained?: boolean }).retained = true; });
  const camera = await scene.getAttribute('data-camera');
  await openTool(page,'Geographic context');
  await expect(scene).not.toBeVisible();
  await openTool(page,'Ocean explorer');
  await expect(scene).toBeVisible();
  expect(await scene.evaluate(e => (e as HTMLElement & { retained?: boolean }).retained)).toBe(true);
  await expect(page.getByLabel('Explorer depth')).toHaveValue('27');
  await expect(scene).toHaveAttribute('data-camera', camera!);
});

test('native profile coordinate mismatch is rejected rather than used for a reading', async ({ page }) => {
  await noPreload(page);
  await page.route('**/subset?*', async route => {
    if (!route.request().url().includes('representation=analytical')) return route.continue();
    const response = await route.fetch(), body = await response.json();
    body.longitude[0] += 1;
    await route.fulfill({ response, json: body });
  });
  await enterWorkspace(page);
  await expect(page.getByLabel('Native model value')).toContainText('Value unavailable');
  await expect(page.getByLabel('Native model value')).not.toContainText('22.303');
  await expect(page.locator('.ocean-webgl')).toHaveAttribute('data-rendered', 'volume');
});

test('a late abandoned snapshot cannot overwrite the latest selection', async ({ page }) => {
  await noPreload(page);
  await enterWorkspace(page); await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('basic');
  let release!: () => void; const gate = new Promise<void>(r => release = r);
  await page.route('**/subset?*', async route => {
    if (route.request().url().includes('time_index=5')) await gate;
    await route.continue();
  });
  await page.getByLabel('Ocean timestamp').selectOption('5');
  await expect(page.locator('.ocean-update')).toBeVisible();
  await page.getByLabel('Ocean timestamp').selectOption('6');
  await expect(page.locator('.ocean-heading')).toContainText('10 Jan 2024, 00:00');
  release();
  await expect(page.getByLabel('Native model value')).not.toContainText('Loading');
  await expect(page.locator('.ocean-viewport')).toHaveAttribute('data-shown-time', '2024-01-10T00:00:00Z');
  await expect(page.getByLabel('Ocean timestamp')).toHaveValue('6');
});

test('a retained isosurface keeps its own threshold and colour key while another variable loads', async ({ page }) => {
  await noPreload(page);
  await enterWorkspace(page); await expect(page.getByLabel('Native model value')).toContainText('22.303');
  await displaySettings(page);await page.getByLabel('Graphics quality').selectOption('balanced');
  await extraView(page,'Isosurface');
  const scene=page.locator('.ocean-webgl');
  await expect(scene).toHaveAttribute('data-rendered','iso');
  const vertices=await scene.getAttribute('data-vertices');
  let release!: () => void; const gate=new Promise<void>(r=>release=r);
  await page.route('**/subset?*',async route=>{if(route.request().url().includes('variable=salinity'))await gate;await route.continue();});
  await page.getByLabel('Variable',{exact:true}).selectOption('salinity');
  await expect(page.locator('.ocean-update')).toContainText('Showing temperature');
  await expect(page.locator('.ocean-instruction')).toContainText('20 °C');
  await expect(page.locator('.ocean-legend h3')).toContainText('Temperature');
  await expect(scene).toHaveAttribute('data-vertices',vertices!);
  release();await expect(page.getByLabel('Native model value')).toContainText('psu');
});
