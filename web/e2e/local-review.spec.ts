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
        if (localStorage.getItem('cv-viewer-test-fail-write') === name) throw new Error('Test write blocked');
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
  const hoverInfo = page.getByLabel('游標資訊');
  await page.mouse.move(centerX, centerY);
  await expect(hoverInfo).toContainText('x=600');
  await expect(hoverInfo).toContainText('y=450');
  await expect(hoverInfo).toContainText('RGB=(40, 44, 60)');
  await expect(hoverInfo).toContainText('zoom=100%');
  await expect(hoverInfo).toContainText('hover RGB 為顯示值；點擊讀取原始真值');
  await page.screenshot({ path: resolve(root, '.artifacts/cv-viewer-react-hover-hud.png') });
  await page.mouse.move(Math.max(2, bounds.x - 12), centerY);
  await expect(hoverInfo).not.toContainText('RGB=(');
  await page.mouse.move(centerX, centerY);
  await expect(hoverInfo).toContainText('RGB=(40, 44, 60)');
  const initialHoverZoom = Number((await hoverInfo.innerText()).match(/zoom=(\d+)%/)?.[1]);
  const pixelReadout = page.locator('.pixel-readout');
  await page.mouse.click(centerX, centerY);
  await expect(pixelReadout).toHaveText('像素 (600, 450) · 40, 44, 60');
  const initialPixel = await pixelReadout.textContent();

  // AC2: zoom, pan, then click the same viewport location and require a new source coordinate.
  await page.getByRole('button', { name: '放大' }).click();
  await expect.poll(async () => Number((await hoverInfo.innerText()).match(/zoom=(\d+)%/)?.[1]))
    .toBeGreaterThan(initialHoverZoom);
  const navigator = page.locator('.navigator').first();
  await expect(navigator).toBeVisible();
  const navigatorBounds = await navigator.boundingBox();
  if (!navigatorBounds) throw new Error('OpenSeadragon navigator is not positioned');
  await page.mouse.click(navigatorBounds.x + navigatorBounds.width * 0.92,
    navigatorBounds.y + navigatorBounds.height * 0.9);
  await page.mouse.click(centerX, centerY);
  await expect(pixelReadout).not.toHaveText(initialPixel!);
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

  // AC5: sidecar edits auto-save before image/folder navigation; a failed write retains the current image and edits.
  let dialogCount = 0;
  page.on('dialog', async (dialog) => { dialogCount += 1; await dialog.dismiss(); });
  await page.getByLabel('審查狀態').selectOption('need_review');
  await page.getByLabel('判讀結果').selectOption('true_defect');
  await page.getByLabel('標籤').fill('autosave probe');
  await page.evaluate(() => localStorage.setItem('cv-viewer-test-fail-write', 'lot42_frame_2.cvr.json'));
  await page.getByRole('button', { name: '下一張' }).click();
  expect(dialogCount).toBe(0);
  await expect(page.getByText('1 / 3')).toBeVisible();
  await expect(page.locator('.status-copy')).toContainText('Test write blocked');
  await expect(page.getByLabel('標籤')).toHaveValue('autosave probe');
  await expect(page.getByRole('img', { name: 'ROI 1' })).toBeVisible();

  await page.evaluate(() => localStorage.removeItem('cv-viewer-test-fail-write'));
  await page.getByRole('button', { name: '下一張' }).click();
  expect(dialogCount).toBe(0);
  await expect(page.getByText('2 / 3')).toBeVisible();
  await page.getByRole('button', { name: '上一張' }).click();
  await expect(page.getByText('1 / 3')).toBeVisible();
  await expect(page.getByLabel('審查狀態')).toHaveValue('need_review');
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.getByLabel('標籤')).toHaveValue('autosave probe');
  await expect(page.getByRole('img', { name: 'ROI 1' })).toBeVisible();

  // AC6: viewer hotkeys navigate and edit sidecar state; focused form controls keep their native keys.
  const keyboardCanvas = page.locator('.openseadragon-canvas').first();
  await keyboardCanvas.focus();
  await expect(keyboardCanvas).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByText('2 / 3')).toBeVisible();
  await keyboardCanvas.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByText('1 / 3')).toBeVisible();
  await keyboardCanvas.focus();
  await page.keyboard.press('1');
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await page.keyboard.press('2');
  await expect(page.getByLabel('判讀結果')).toHaveValue('false_alarm');
  await page.keyboard.press('3');
  await expect(page.getByLabel('判讀結果')).toHaveValue('reflection');
  await expect(page.getByLabel('審查狀態')).toHaveValue('need_review');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('☆');
  await page.keyboard.press('r');
  await expect(page.getByLabel('審查狀態')).toHaveValue('done');
  await page.keyboard.press('r');
  await expect(page.getByLabel('審查狀態')).toHaveValue('none');
  await page.keyboard.press('r');
  await expect(page.getByLabel('審查狀態')).toHaveValue('need_review');
  await page.keyboard.press('b');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('★');
  await page.keyboard.press('b');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('☆');
  const tagsField = page.getByLabel('標籤');
  const tagsBeforeFocusedKey = await tagsField.inputValue();
  await tagsField.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('1');
  await expect(page.getByText('1 / 3')).toBeVisible();
  await expect(tagsField).not.toHaveValue(tagsBeforeFocusedKey);
  await expect(page.getByLabel('判讀結果')).toHaveValue('reflection');
  await expect(page.getByLabel('審查狀態')).toHaveValue('need_review');

  await page.getByLabel('判讀備註').fill('folder reselection autosave');
  await page.getByRole('button', { name: '選擇資料夾' }).click();
  expect(dialogCount).toBe(0);
  await expect(page.getByText('1 / 3')).toBeVisible();
  await expect(page.getByLabel('判讀備註')).toHaveValue('folder reselection autosave');

  // AC7-AC9: review-field changes have a bounded, cross-image undo history.
  const undoCount = async () => {
    const text = await page.locator('.undo-count').textContent();
    const match = text?.match(/\d+/);
    if (!match) throw new Error(`Undo count is missing: ${text}`);
    return Number(match[0]);
  };
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');
  await keyboardCanvas.focus();
  await page.keyboard.press('1');
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.locator('.undo-count')).toHaveText('可撤 1 筆');
  await page.evaluate(() => localStorage.setItem('cv-viewer-test-fail-write', 'lot42_frame_2.cvr.json'));
  await page.keyboard.press('u');
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.locator('.undo-count')).toHaveText('可撤 1 筆');
  await expect(page.locator('.status-copy')).toContainText('Test write blocked');
  await page.evaluate(() => localStorage.removeItem('cv-viewer-test-fail-write'));
  await page.keyboard.press('u');
  await expect(page.getByLabel('判讀結果')).toHaveValue('reflection');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');
  await expect(page.locator('.status-copy')).toContainText('已撤銷');

  await page.keyboard.press('3');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');
  for (const key of ['1', '2', '3', '1', '2', '3']) await page.keyboard.press(key);
  await expect(page.getByLabel('判讀結果')).toHaveValue('reflection');
  await expect(page.locator('.undo-count')).toHaveText('可撤 5 筆');
  for (let i = 0; i < 5; i += 1) {
    await page.keyboard.press('u');
    await expect(page.locator('.undo-count')).toHaveText(`可撤 ${4 - i} 筆`);
  }
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');

  await page.keyboard.press('r');
  await expect(page.getByLabel('審查狀態')).toHaveValue('done');
  await expect(page.locator('.undo-count')).toHaveText('可撤 1 筆');
  await page.keyboard.press('u');
  await expect(page.getByLabel('審查狀態')).toHaveValue('need_review');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');
  await page.keyboard.press('b');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('★');
  await expect(page.locator('.undo-count')).toHaveText('可撤 1 筆');
  await page.keyboard.press('u');
  await expect(page.getByRole('button', { name: '切換書籤' })).toHaveText('☆');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');

  await keyboardCanvas.focus();
  await page.keyboard.press('2');
  await expect(page.getByLabel('判讀結果')).toHaveValue('false_alarm');
  await page.keyboard.press('ArrowRight');
  await expect(page.getByText('2 / 3')).toBeVisible();
  await keyboardCanvas.focus();
  await page.keyboard.press('2');
  await expect(page.getByLabel('判讀結果')).toHaveValue('false_alarm');
  await page.keyboard.press('ArrowRight');
  await expect(page.getByText('3 / 3')).toBeVisible();
  await keyboardCanvas.focus();
  await page.keyboard.press('3');
  await expect(page.getByLabel('判讀結果')).toHaveValue('reflection');
  await expect(page.locator('.undo-count')).toHaveText('可撤 3 筆');
  await page.keyboard.press('u');
  await expect(page.getByText('3 / 3')).toBeVisible();
  await expect(page.getByLabel('判讀結果')).toHaveValue('unset');
  await expect(page.locator('.undo-count')).toHaveText('可撤 2 筆');
  await page.keyboard.press('u');
  await expect(page.getByText('2 / 3')).toBeVisible();
  await expect(page.getByLabel('判讀結果')).toHaveValue('unset');
  await expect(page.locator('.undo-count')).toHaveText('可撤 1 筆');
  await page.keyboard.press('u');
  await expect(page.getByText('1 / 3')).toBeVisible();
  await expect(page.getByLabel('判讀結果')).toHaveValue('true_defect');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');
  await page.keyboard.press('u');
  await expect(page.locator('.undo-count')).toHaveText('可撤 0 筆');
  await expect(page.locator('.status-copy')).toContainText('無可撤銷');
  const afterUndo = await page.evaluate(() => JSON.parse(localStorage.getItem('cv-viewer-test-sidecars') || '{}'));
  expect(JSON.parse(afterUndo['lot42_frame_2.cvr.json']).verdict).toBe('true_defect');
  expect(JSON.parse(afterUndo['lot42_frame_10.cvr.json']).verdict).toBe('unset');
  expect(JSON.parse(afterUndo['wafer16_000.cvr.json']).verdict).toBe('unset');

  await page.getByLabel('判讀備註').fill('React review round-trip');
  await page.getByLabel('判讀結果').selectOption('true_defect');
  await page.getByLabel('標籤').fill('scratch, edge');
  await page.getByRole('button', { name: '切換書籤' }).click();
  await page.getByRole('button', { name: '保存判讀' }).click();
  await expect(page.getByRole('status').filter({ hasText: '已保存 lot42_frame_2.cvr.json' })).toBeVisible();

  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('cv-viewer-test-sidecars') || '{}'));
  const sidecar = JSON.parse(saved['lot42_frame_2.cvr.json']);
  expect(sidecar.comment).toBe('React review round-trip');
  expect(sidecar.review_status).toBe('need_review');
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
  const writeTargets = await page.evaluate(() => JSON.parse(localStorage.getItem('cv-viewer-test-write-targets') || '[]'));
  expect(writeTargets.length).toBeGreaterThan(0);
  expect(writeTargets.every((target: string) => target.endsWith('.cvr.json'))).toBe(true);

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
  await page.mouse.move(tiffBounds.x + tiffBounds.width / 2, tiffBounds.y + tiffBounds.height / 2);
  await expect(page.getByLabel('游標資訊')).toContainText('RGB=(');
  await expect(page.getByLabel('游標資訊')).toContainText('hover RGB 為顯示值；點擊讀取原始真值');
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

  const readZoomPercent = async () => {
    const match = (await page.getByLabel('游標資訊').innerText()).match(/zoom=(\d+)%/);
    if (!match) throw new Error('Viewer zoom percentage is missing');
    return Number(match[1]);
  };
  const zoomButton = page.getByRole('button', { name: '放大' });
  let previousZoom = await readZoomPercent();
  let reachedZoomLimit = false;
  for (let step = 0; step < 40; step += 1) {
    await zoomButton.click();
    await page.waitForTimeout(300);
    const nextZoom = await readZoomPercent();
    if (nextZoom === previousZoom) {
      reachedZoomLimit = true;
      break;
    }
    expect(nextZoom).toBeGreaterThan(previousZoom);
    previousZoom = nextZoom;
  }
  expect(reachedZoomLimit).toBe(true);
  await zoomButton.click();
  await page.waitForTimeout(300);
  await expect(page.getByLabel('游標資訊')).toContainText(`zoom=${previousZoom}%`);
});
