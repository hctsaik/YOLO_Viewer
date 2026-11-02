import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

const root = fileURLToPath(new URL('../..', import.meta.url));
const firstPng = readFileSync(resolve(root, 'sample_images/lot42_frame_000.png')).toString('base64');
const secondPng = readFileSync(resolve(root, 'sample_images/lot42_frame_001.png')).toString('base64');
const sixteenBitTiff = readFileSync(resolve(root, 'sample_images/wafer16_000.tif')).toString('base64');

test('folder review reads a real image, queries a pixel, and saves a sidecar', async ({ page }) => {
  await page.addInitScript(({ first, second, tiff }) => {
    const key = 'cv-viewer-test-sidecars';
    const sidecars = new Map<string, string>(Object.entries(JSON.parse(localStorage.getItem(key) || '{}')));
    const fromBase64 = (value: string) => Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
    const source = new Map<string, { bytes: Uint8Array; type: string }>([
      ['lot42_frame_10.png', { bytes: fromBase64(second), type: 'image/png' }],
      ['lot42_frame_2.png', { bytes: fromBase64(first), type: 'image/png' }],
      ['wafer16_000.tif', { bytes: fromBase64(tiff), type: 'image/tiff' }],
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
        if (source.has(name)) throw new Error('Source images are read-only');
        const writeKey = 'cv-viewer-test-write-targets';
        const writeTargets = JSON.parse(localStorage.getItem(writeKey) || '[]') as string[];
        writeTargets.push(name);
        localStorage.setItem(writeKey, JSON.stringify(writeTargets));
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
  }, { first: firstPng, second: secondPng, tiff: sixteenBitTiff });

  await page.goto('/');
  await page.getByLabel('本機配對碼').fill('cv-viewer-playwright-test');
  await page.getByRole('button', { name: '連線到本機服務' }).click();
  await expect(page.getByText('本機服務已連線')).toBeVisible();

  await page.getByRole('button', { name: '選擇資料夾' }).click();
  // AC1: enumeration intentionally yields frame_10 before frame_2.
  const imageRows = page.getByRole('complementary', { name: '影像清單' }).getByRole('button');
  await expect(imageRows).toHaveCount(3);
  await expect(imageRows.nth(0)).toHaveAccessibleName(/lot42_frame_2\.png/);
  await expect(imageRows.nth(1)).toHaveAccessibleName(/lot42_frame_10\.png/);
  await expect(imageRows.nth(2)).toHaveAccessibleName(/wafer16_000\.tif/);
  await expect(imageRows.nth(0)).toHaveAttribute('aria-current', 'true');
  await expect(page.getByText('1 / 3')).toBeVisible();
  await expect(page.getByText('1200 × 900 · 8-bit · 3 channels')).toBeVisible();

  const canvas = page.getByLabel('影像畫布');
  await expect(canvas).toBeVisible();
  const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error('OpenSeadragon canvas is not positioned');
  const centerX = bounds.x + bounds.width / 2;
  const centerY = bounds.y + bounds.height / 2;
  const pixelReadout = page.locator('.pixel-readout');
  await page.mouse.click(centerX, centerY);
  await expect(pixelReadout).toHaveText('像素 (600, 450) · 40, 44, 60');
  const initialPixel = await pixelReadout.textContent();

  // AC2: zoom, pan, then click the same viewport location and require a new source coordinate.
  await page.getByRole('button', { name: '放大' }).click();
  await page.mouse.move(centerX - 45, centerY - 15);
  await page.mouse.down();
  await page.mouse.move(centerX + 55, centerY + 35, { steps: 5 });
  await page.mouse.up();
  await page.mouse.click(centerX, centerY);
  await expect(pixelReadout).not.toHaveText(initialPixel!);

  // AC4: Shift+drag creates one source-coordinate ROI and an image-space overlay.
  const drawRoi = async (reverse = false) => {
    await page.keyboard.down('Shift');
    await page.mouse.move(centerX + (reverse ? 45 : -35), centerY + (reverse ? 35 : -25));
    await page.mouse.down();
    await page.mouse.move(centerX + (reverse ? -35 : 45), centerY + (reverse ? -25 : 35), { steps: 5 });
    await page.mouse.up();
    await page.keyboard.up('Shift');
  };
  const roiPanel = page.getByRole('region', { name: 'ROI 標記' });
  await drawRoi(true);
  await expect(roiPanel.getByText('ROI 1')).toBeVisible();
  await expect(page.getByRole('img', { name: 'ROI 1' })).toBeVisible();
  await page.getByRole('button', { name: '移除 ROI 1' }).click();
  await expect(roiPanel.getByText('尚無 ROI')).toBeVisible();
  await expect(page.getByRole('img', { name: 'ROI 1' })).toHaveCount(0);
  await drawRoi();
  await expect(page.getByRole('img', { name: 'ROI 1' })).toBeVisible();

  await page.getByLabel('判讀備註').fill('React review round-trip');
  await page.getByLabel('判讀結果').selectOption('true_defect');
  await page.getByLabel('標籤').fill('scratch, edge');
  await page.getByRole('button', { name: '切換書籤' }).click();
  await page.getByRole('button', { name: '保存判讀' }).click();
  await expect(page.getByRole('status').filter({ hasText: '已保存 lot42_frame_2.cvr.json' })).toBeVisible();

  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('cv-viewer-test-sidecars') || '{}'));
  const sidecar = JSON.parse(saved['lot42_frame_2.cvr.json']);
  expect(sidecar.comment).toBe('React review round-trip');
  expect(sidecar.verdict).toBe('true_defect');
  expect(sidecar.tags).toEqual(['scratch', 'edge']);
  expect(sidecar.bookmarked).toBe(true);
  expect(sidecar.rois).toHaveLength(1);
  expect(sidecar.rois[0]).toMatchObject({ label: '', verdict: 'unset', comment: '' });
  const [roiX, roiY, roiWidth, roiHeight] = sidecar.rois[0].bbox;
  expect([roiX, roiY, roiWidth, roiHeight].every(Number.isInteger)).toBe(true);
  expect(roiX).toBeGreaterThanOrEqual(0);
  expect(roiY).toBeGreaterThanOrEqual(0);
  expect(roiWidth).toBeGreaterThan(2);
  expect(roiHeight).toBeGreaterThan(2);
  expect(roiX + roiWidth).toBeLessThanOrEqual(1200);
  expect(roiY + roiHeight).toBeLessThanOrEqual(900);
  // AC3: only the adjacent sidecar may be opened for writing.
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('cv-viewer-test-write-targets') || '[]')))
    .toEqual(['lot42_frame_2.cvr.json']);

  await page.evaluate(() => {
    const key = 'cv-viewer-test-sidecars';
    const saved = JSON.parse(localStorage.getItem(key) || '{}');
    saved['lot42_frame_10.cvr.json'] = '{ malformed sidecar';
    localStorage.setItem(key, JSON.stringify(saved));
  });
  await page.getByRole('button', { name: '下一張' }).click();
  await expect(page.getByText('2 / 3')).toBeVisible();
  await expect(page.getByRole('button', { name: /lot42_frame_10\.png/ })).toHaveAttribute('aria-current', 'true');
  await expect(page.getByLabel('判讀備註')).toHaveValue('');
  await expect(page.getByLabel('判讀結果')).toHaveValue('unset');
  await expect(page.getByLabel('標籤')).toHaveValue('');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('☆');
  await page.getByRole('button', { name: '下一張' }).click();
  await expect(page.getByText('3 / 3')).toBeVisible();
  await expect(page.getByRole('button', { name: /wafer16_000\.tif/ })).toHaveAttribute('aria-current', 'true');
  await expect(page.getByText('1000 × 1000 · 16-bit · 灰階')).toBeVisible();
  await page.getByRole('button', { name: '重設檢視' }).click();
  const tiffBounds = await canvas.boundingBox();
  if (!tiffBounds) throw new Error('16-bit TIFF viewer is not positioned');
  await page.mouse.click(tiffBounds.x + tiffBounds.width / 2, tiffBounds.y + tiffBounds.height / 2);
  await expect(pixelReadout).toHaveText('像素 (500, 500) · 19585');
  await page.getByRole('button', { name: '上一張' }).click();
  await page.getByRole('button', { name: '上一張' }).click();
  await expect(page.getByLabel('判讀備註')).toHaveValue('React review round-trip');
  await expect(page.getByRole('img', { name: 'ROI 1' })).toBeVisible();

  await page.reload();
  await page.getByLabel('本機配對碼').fill('cv-viewer-playwright-test');
  await page.getByRole('button', { name: '連線到本機服務' }).click();
  await expect(page.getByText('本機服務已連線')).toBeVisible();
  await page.getByRole('button', { name: '選擇資料夾' }).click();
  await expect(page.getByText('1200 × 900 · 8-bit · 3 channels')).toBeVisible();
  await expect(page.getByLabel('判讀備註')).toHaveValue('React review round-trip');
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.getByLabel('標籤')).toHaveValue('scratch, edge');
  await expect(page.getByRole('img', { name: 'ROI 1' })).toBeVisible();
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('★');
  await page.screenshot({ path: resolve(root, '.artifacts/cv-viewer-react-e2e.png') });

  await page.getByRole('button', { name: '移除 ROI 1' }).click();
  await page.getByRole('button', { name: '保存判讀' }).click();
  await expect(page.getByRole('status').filter({ hasText: '已保存 lot42_frame_2.cvr.json' })).toBeVisible();
  const cleared = await page.evaluate(() => {
    const saved = JSON.parse(localStorage.getItem('cv-viewer-test-sidecars') || '{}');
    return JSON.parse(saved['lot42_frame_2.cvr.json']);
  });
  expect(cleared.rois).toEqual([]);
});
