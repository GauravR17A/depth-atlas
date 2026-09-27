import { enterWorkspace } from './ux-helpers';
import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('initial evolution archives remain readable and explain the changed method on replay', async ({ page }) => {
  test.setTimeout(60000);
  const fixture = JSON.parse(await readFile(new URL('../../docs/evidence/p14-local-records-final.json', import.meta.url), 'utf8'));
  const record = fixture.records.find((entry: { replay: { recipe: { mode: string } } }) => entry.replay.recipe.mode === 'evolution');
  expect(record.replay.sources.methods.evolution).toBe('p14-native-overlap-v1');
  await enterWorkspace(page);
  await page.getByRole('button', { name: 'Open saved investigations', exact: true }).click();
  await page.getByLabel('Open investigation file', { exact: true }).setInputFiles({ name: 'initial-evolution.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(record)) });
  await expect(page.getByLabel('Selected saved investigation', { exact: true })).toContainText(record.replay.title);
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Investigation JSON', exact: true }).click();
  const retained = JSON.parse(await readFile((await (await downloaded).path())!, 'utf8'));
  expect(retained.document_sha256).toBe(record.document_sha256);
  expect(retained.result_sha256).toBe(record.result_sha256);
  await page.getByRole('button', { name: 'Recalculate and reopen', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('different scientific method version');
  await expect(page.getByRole('dialog')).toBeVisible();
});
