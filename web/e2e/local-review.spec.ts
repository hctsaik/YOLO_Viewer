import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

const root = fileURLToPath(new URL('../..', import.meta.url));
const firstPng = readFileSync(resolve(root, 'sample_images/lot42_frame_000.png')).toString('base64');
const secondPng = readFileSync(resolve(root, 'sample_images/lot42_frame_001.png')).toString('base64');

test('folder review reads a real image, queries a pixel, and saves a sidecar', async ({ page }) => {
  await page.addInitScript(({ first, second }) => {
    const key = 'cv-viewer-test-sidecars';
    const sidecars = new Map<string, string>(Object.entries(JSON.parse(localStorage.getItem(key) || '{}')));
    const fromBase64 = (value: string) => Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
    const source = new Map<string, { bytes: Uint8Array; type: string }>([
      ['lot42_frame_000.png', { bytes: fromBase64(first), type: 'image/png' }],
      ['lot42_frame_001.png', { bytes: fromBase64(second), type: 'image/png' }],
    ]);

    const fileHandle = (name: string, initial = '') => ({
      kind: 'file',
      name,
      async getFile() {
        const saved = sidecars.get(name);
        const entry = source.get(name);
        const content = saved ?? (entry ? entry.bytes : initial);
        return new File([content as BlobPart], name, { type: entry?.type ?? 'application/json' });
      },
      async createWritable() {
        let pending = '';
        return {
          async write(value: string) { pending = value; },
          async close() {
            sidecars.set(name, pending);
            localStorage.setItem(key, JSON.stringify(Object.fromEntries(sidecars)));
          },
        };
      },
    });

    const handles = new Map<string, ReturnType<typeof fileHandle>>(
      [...source.keys()].map((name) => [name, fileHandle(name)]),
    );
    const directory = {
      kind: 'directory',
      name: 'lot42',
      async *entries() { for (const pair of handles.entries()) yield pair; },
      async getFileHandle(name: string, options?: { create?: boolean }) {
        if (!handles.has(name)) {
          if (!options?.create && !sidecars.has(name)) throw new DOMException('Not found', 'NotFoundError');
          handles.set(name, fileHandle(name));
        }
        return handles.get(name)!;
      },
    };
    Object.defineProperty(window, 'showDirectoryPicker', { configurable: true, value: async () => directory });
  }, { first: firstPng, second: secondPng });

  await page.goto('/');
  await page.getByLabel('本機配對碼').fill('cv-viewer-playwright-test');
  await page.getByRole('button', { name: '連線到本機服務' }).click();
  await expect(page.getByText('本機服務已連線')).toBeVisible();

  await page.getByRole('button', { name: '選擇資料夾' }).click();
  await expect(page.getByText('lot42_frame_000.png')).toBeVisible();
  await expect(page.getByText('1 / 2')).toBeVisible();
  await expect(page.getByText('1200 × 900 · 8-bit · 3 channels')).toBeVisible();

  const canvas = page.getByLabel('影像畫布');
  await expect(canvas).toBeVisible();
  const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error('OpenSeadragon canvas is not positioned');
  await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await expect(page.getByText(/像素 \(/)).toBeVisible();

  await page.getByLabel('判讀備註').fill('React review round-trip');
  await page.getByLabel('判讀結果').selectOption('true_defect');
  await page.getByLabel('標籤').fill('scratch, edge');
  await page.getByRole('button', { name: '切換書籤' }).click();
  await page.getByRole('button', { name: '保存判讀' }).click();
  await expect(page.getByRole('status').filter({ hasText: '已保存 lot42_frame_000.cvr.json' })).toBeVisible();

  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('cv-viewer-test-sidecars') || '{}'));
  const sidecar = JSON.parse(saved['lot42_frame_000.cvr.json']);
  expect(sidecar.comment).toBe('React review round-trip');
  expect(sidecar.verdict).toBe('true_defect');
  expect(sidecar.tags).toEqual(['scratch', 'edge']);
  expect(sidecar.bookmarked).toBe(true);

  await page.evaluate(() => {
    const key = 'cv-viewer-test-sidecars';
    const saved = JSON.parse(localStorage.getItem(key) || '{}');
    saved['lot42_frame_001.cvr.json'] = '{ malformed sidecar';
    localStorage.setItem(key, JSON.stringify(saved));
  });
  await page.getByRole('button', { name: '下一張' }).click();
  await expect(page.getByText('2 / 2')).toBeVisible();
  await expect(page.getByRole('button', { name: /lot42_frame_001\.png/ })).toHaveAttribute('aria-current', 'true');
  await expect(page.getByLabel('判讀備註')).toHaveValue('');
  await expect(page.getByLabel('判讀結果')).toHaveValue('unset');
  await expect(page.getByLabel('標籤')).toHaveValue('');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('☆');
  await page.getByRole('button', { name: '上一張' }).click();
  await expect(page.getByLabel('判讀備註')).toHaveValue('React review round-trip');

  await page.reload();
  await page.getByLabel('本機配對碼').fill('cv-viewer-playwright-test');
  await page.getByRole('button', { name: '連線到本機服務' }).click();
  await expect(page.getByText('本機服務已連線')).toBeVisible();
  await page.getByRole('button', { name: '選擇資料夾' }).click();
  await expect(page.getByText('1200 × 900 · 8-bit · 3 channels')).toBeVisible();
  await expect(page.getByLabel('判讀備註')).toHaveValue('React review round-trip');
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.getByLabel('標籤')).toHaveValue('scratch, edge');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('★');
  await page.screenshot({ path: resolve(root, '.artifacts/cv-viewer-react-e2e.png') });
});
