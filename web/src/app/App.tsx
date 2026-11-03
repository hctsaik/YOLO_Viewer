import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';

type ReviewStatus = 'none' | 'need_review' | 'done';
type Verdict = 'unset' | 'true_defect' | 'false_alarm' | 'reflection';
type UndoField = 'verdict' | 'review_status' | 'bookmarked';
type UndoEntry = {
  imageName: string;
  field: UndoField;
  oldValue: Verdict | ReviewStatus | boolean;
};
type Roi = {
  bbox: [number, number, number, number];
  label: string;
  verdict: Verdict;
  comment: string;
};
type Sidecar = {
  review_status: ReviewStatus;
  tags: string[];
  verdict: Verdict;
  comment: string;
  bookmarked: boolean;
  rois: Roi[];
  reviewer: string;
  timestamp: string;
};
type ImageEntry = { name: string; handle: FileSystemFileHandle };
type View = {
  imageHandle: string;
  displayUrl: string;
  width: number;
  height: number;
  bitDepth: number;
  channels: number;
};
type PickerWindow = Window & {
  showDirectoryPicker?: (options?: { mode?: 'read' | 'readwrite' }) => Promise<FileSystemDirectoryHandle>;
};
type RoiDrag = { startX: number; startY: number; endX: number; endY: number };

const supported = /\.(png|jpe?g|tiff?)$/i;
const sessionHeader = (token: string) => ({ 'X-CV-Session': token });

function emptySidecar(): Sidecar {
  return {
    review_status: 'none', tags: [], verdict: 'unset', comment: '',
    bookmarked: false, rois: [], reviewer: '', timestamp: '',
  };
}

function normalizeRoi(value: unknown): Roi | null {
  const source = Array.isArray(value) ? { bbox: value } : value;
  if (!source || typeof source !== 'object') return null;
  const record = source as Record<string, unknown>;
  const bbox = record.bbox;
  if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every((item) => typeof item === 'number' && Number.isFinite(item))) {
    return null;
  }
  const values = bbox.map(Math.trunc) as [number, number, number, number];
  const verdicts: Verdict[] = ['unset', 'true_defect', 'false_alarm', 'reflection'];
  return {
    bbox: values,
    label: typeof record.label === 'string' ? record.label : '',
    verdict: verdicts.includes(record.verdict as Verdict) ? record.verdict as Verdict : 'unset',
    comment: typeof record.comment === 'string' ? record.comment : '',
  };
}

function normalizeSidecar(value: unknown): Sidecar {
  const defaults = emptySidecar();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return defaults;
  const source = value as Record<string, unknown>;
  for (const key of Object.keys(defaults) as Array<keyof Sidecar>) {
    if (Object.hasOwn(source, key)) defaults[key] = source[key] as never;
  }
  defaults.rois = Array.isArray(source.rois)
    ? source.rois.map(normalizeRoi).filter((roi): roi is Roi => roi !== null)
    : [];
  return defaults;
}

function naturalCompare(left: string, right: string) {
  const a = left.match(/\d+|\D+/g) ?? [left];
  const b = right.match(/\d+|\D+/g) ?? [right];
  for (let i = 0; i < Math.min(a.length, b.length); i += 1) {
    const an = /^\d+$/.test(a[i]);
    const bn = /^\d+$/.test(b[i]);
    if (an && bn) {
      const av = BigInt(a[i]);
      const bv = BigInt(b[i]);
      if (av !== bv) return av < bv ? -1 : 1;
    } else if (an !== bn) {
      return an ? 1 : -1;
    } else {
      const order = a[i].toLowerCase().localeCompare(b[i].toLowerCase());
      if (order) return order;
    }
  }
  return a.length - b.length || left.localeCompare(right);
}

function sidecarName(imageName: string) {
  return imageName.replace(/\.[^.]+$/, '') + '.cvr.json';
}

async function readSidecar(directory: FileSystemDirectoryHandle, imageName: string): Promise<Sidecar> {
  try {
    const handle = await directory.getFileHandle(sidecarName(imageName));
    const parsed = JSON.parse(await (await handle.getFile()).text());
    return normalizeSidecar(parsed);
  } catch (error) {
    if ((error as DOMException).name === 'NotFoundError' || error instanceof SyntaxError) return emptySidecar();
    throw error;
  }
}

async function writeSidecar(directory: FileSystemDirectoryHandle, imageName: string, value: Sidecar) {
  const handle = await directory.getFileHandle(sidecarName(imageName), { create: true });
  const writable = await handle.createWritable();
  await writable.write(JSON.stringify(value, null, 2) + String.fromCharCode(10));
  await writable.close();
}

export default function App() {
  const [pairingCode, setPairingCode] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [directory, setDirectory] = useState<FileSystemDirectoryHandle | null>(null);
  const [entries, setEntries] = useState<ImageEntry[]>([]);
  const [index, setIndex] = useState(-1);
  const [view, setView] = useState<View | null>(null);
  const [sidecar, setSidecar] = useState<Sidecar>(emptySidecar);
  const [tagText, setTagText] = useState('');
  const [pixelText, setPixelText] = useState('點擊影像讀取像素真值');
  const [hoverPoint, setHoverPoint] = useState<{ x: number; y: number; rgb: [number, number, number] | null } | null>(null);
  const [zoomPercent, setZoomPercent] = useState(100);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [undoStack, setUndoStack] = useState<UndoEntry[]>([]);
  const [notice, setNotice] = useState('本機服務尚未連線');
  const [roiDraft, setRoiDraft] = useState<RoiDrag | null>(null);
  const viewerElement = useRef<HTMLDivElement>(null);
  const viewer = useRef<any>(null);
  const currentHandle = useRef('');
  const displayCanvas = useRef<HTMLCanvasElement | null>(null);
  const viewportBoundsToRestore = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const roiDrag = useRef<{ startX: number; startY: number } | null>(null);
  const roiOverlayElements = useRef<HTMLElement[]>([]);
  const sidecarRef = useRef(sidecar);
  const undoStackRef = useRef<UndoEntry[]>([]);
  const undoRunning = useRef(false);
  const viewRef = useRef(view);
  const currentEntry = index >= 0 ? entries[index] : null;

  useEffect(() => { sidecarRef.current = sidecar; }, [sidecar]);
  useEffect(() => { viewRef.current = view; }, [view]);

  const drawRoiOverlays = useCallback((instance: any, rois: Roi[], image: View | null) => {
    roiOverlayElements.current.forEach((element) => instance.removeOverlay(element));
    roiOverlayElements.current = [];
    if (!image || !instance.isOpen()) return;
    rois.forEach((roi, roiIndex) => {
      const [x, y, width, height] = roi.bbox;
      const left = Math.max(0, Math.min(image.width, x));
      const top = Math.max(0, Math.min(image.height, y));
      const right = Math.max(left, Math.min(image.width, x + width));
      const bottom = Math.max(top, Math.min(image.height, y + height));
      if (right <= left || bottom <= top) return;
      const rect = instance.viewport.imageToViewportRectangle(
        new (window.OpenSeadragon as any).Rect(left, top, right - left, bottom - top),
      );
      const element = document.createElement('div');
      element.className = 'roi-overlay';
      element.setAttribute('role', 'img');
      element.setAttribute('aria-label', `ROI ${roiIndex + 1}`);
      element.title = `ROI ${roiIndex + 1} · ${left}, ${top}, ${right - left}, ${bottom - top}`;
      instance.addOverlay({ element, location: rect });
      roiOverlayElements.current.push(element);
    });
  }, []);

  const progress = useMemo(
    () => index >= 0 && entries.length ? `${index + 1} / ${entries.length}` : '— / —',
    [index, entries.length],
  );

  const connect = async () => {
    setNotice('正在建立本機工作階段…');
    try {
      const response = await fetch('/api/session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pairing_code: pairingCode }),
      });
      if (!response.ok) throw new Error('配對碼錯誤或來源未授權');
      const result = await response.json();
      setSessionToken(result.session_token);
      setNotice('本機工作階段已連線');
      setPairingCode('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '連線失敗');
    }
  };

  const saveSidecar = useCallback(async (): Promise<boolean> => {
    if (!directory || !currentEntry) return false;
    setBusy(true);
    try {
      const next = { ...sidecar, tags: tagText.split(',').map((tag) => tag.trim()).filter(Boolean),
        timestamp: new Date().toISOString() };
      const handle = await directory.getFileHandle(sidecarName(currentEntry.name), { create: true });
      const writable = await handle.createWritable();
      await writable.write(`${JSON.stringify(next, null, 2)}\n`);
      await writable.close();
      sidecarRef.current = next;
      setSidecar(next);
      setDirty(false);
      setNotice(`已保存 ${sidecarName(currentEntry.name)}；原始影像保持不變`);
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'sidecar 保存失敗');
      return false;
    } finally {
      setBusy(false);
    }
  }, [currentEntry, directory, sidecar, tagText]);

  const openImage = useCallback(async (
    nextIndex: number,
    nextEntries = entries,
    nextDirectory = directory,
    currentAlreadySaved = false,
    preserveViewport = true,
  ) => {
    if (!sessionToken || !nextDirectory || nextIndex < 0 || nextIndex >= nextEntries.length) return false;
    if (dirty && !currentAlreadySaved && !(await saveSidecar())) return false;
    setBusy(true);
    setNotice('正在解碼影像…');
    try {
      const entry = nextEntries[nextIndex];
      const file = await entry.handle.getFile();
      const form = new FormData();
      form.append('file', file, entry.name);
      const response = await fetch('/api/images/view', {
        method: 'POST', headers: sessionHeader(sessionToken), body: form,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail?.code ?? `影像解碼失敗 (${response.status})`);
      }
      const result = await response.json();
      const display = await fetch(`/api/images/${result.image_handle}/display`, {
        headers: sessionHeader(sessionToken),
      });
      if (!display.ok) throw new Error(`無法讀取顯示影像 (${display.status})`);
      const blobUrl = URL.createObjectURL(await display.blob());
      const previousUrl = view?.displayUrl;
      const viewport = viewer.current?.isOpen() ? viewer.current.viewport : null;
      const previousBounds = preserveViewport && viewport ? viewport.getBounds(false) : null;
      viewportBoundsToRestore.current = previousBounds ? {
        x: previousBounds.x, y: previousBounds.y,
        width: previousBounds.width, height: previousBounds.height,
      } : null;
      setView({
        imageHandle: result.image_handle, displayUrl: blobUrl,
        width: result.width, height: result.height,
        bitDepth: result.bit_depth, channels: result.channels,
      });
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      const loadedSidecar = await readSidecar(nextDirectory, entry.name);
      sidecarRef.current = loadedSidecar;
      setSidecar(loadedSidecar);
      setTagText(loadedSidecar.tags.join(', '));
      setIndex(nextIndex);
      setDirty(false);
      setPixelText('點擊影像讀取像素真值');
      setNotice(`${entry.name} · ${result.width} × ${result.height} · ${result.bit_depth}-bit`);
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '影像載入失敗');
      return false;
    } finally {
      setBusy(false);
    }
  }, [directory, dirty, entries, saveSidecar, sessionToken, view?.displayUrl]);

  const chooseFolder = async () => {
    const picker = (window as PickerWindow).showDirectoryPicker;
    if (!picker) {
      setNotice('此瀏覽器沒有資料夾授權 API；請使用最新版 Edge 或 Chrome。');
      return;
    }
    try {
      const granted = await picker({ mode: 'readwrite' });
      const found: ImageEntry[] = [];
      for await (const [name, handle] of granted.entries()) {
        if (handle.kind === 'file' && supported.test(name)) {
          found.push({ name, handle: handle as FileSystemFileHandle });
        }
      }
      found.sort((a, b) => naturalCompare(a.name, b.name));
      if (!found.length) {
        setNotice('此資料夾沒有支援的 PNG、JPEG 或 TIFF 影像。');
        return;
      }
      let currentAlreadySaved = false;
      if (dirty) {
        currentAlreadySaved = await saveSidecar();
        if (!currentAlreadySaved) return;
      }
      if (view?.displayUrl) URL.revokeObjectURL(view.displayUrl);
      if (view?.imageHandle) {
        void fetch(`/api/images/${view.imageHandle}`, { method: 'DELETE', headers: sessionHeader(sessionToken) });
      }
      setDirectory(granted);
      setEntries(found);
      undoStackRef.current = [];
      setUndoStack([]);
      setView(null);
      setIndex(-1);
      setNotice(`已授權資料夾 · ${found.length} 張影像`);
      await openImage(0, found, granted, currentAlreadySaved, false);
    } catch (error) {
      if ((error as DOMException).name !== 'AbortError') {
        setNotice(error instanceof Error ? error.message : '資料夾讀取失敗');
      }
    }
  };

  const zoomBy = (factor: number) => {
    const viewport = viewer.current?.viewport;
    if (!viewport) return;
    viewport.zoomBy(factor);
    viewport.applyConstraints(false);
  };

  const updateSidecar = (patch: Partial<Sidecar>) => {
    const next = { ...sidecarRef.current, ...patch };
    sidecarRef.current = next;
    setSidecar(next);
    setDirty(true);
  };

  const updateReviewField = <Field extends UndoField>(field: Field, value: Sidecar[Field]) => {
    if (!currentEntry) return;
    const oldValue = sidecarRef.current[field];
    if (Object.is(oldValue, value)) return;
    const nextHistory = [...undoStackRef.current, {
      imageName: currentEntry.name,
      field,
      oldValue,
    }].slice(-5);
    undoStackRef.current = nextHistory;
    setUndoStack(nextHistory);
    const next = { ...sidecarRef.current, [field]: value };
    sidecarRef.current = next;
    setSidecar(next);
    setDirty(true);
  };

  const undoReviewChange = async () => {
    if (undoRunning.current) return;
    const entry = undoStackRef.current.at(-1);
    if (!entry) {
      setNotice('無可撤銷');
      return;
    }
    if (!directory) {
      setNotice('目前資料夾無法執行撤銷');
      return;
    }
    const targetIndex = entries.findIndex((item) => item.name === entry.imageName);
    if (targetIndex < 0) {
      setNotice('找不到待撤銷的影像');
      return;
    }

    undoRunning.current = true;
    setBusy(true);
    try {
      const alreadyOnTarget = currentEntry?.name === entry.imageName;
      if (!alreadyOnTarget && !(await openImage(targetIndex))) return;
      // Keep controls locked between opening the target and writing its restored sidecar.
      setBusy(true);
      const targetSidecar = alreadyOnTarget
        ? {
            ...sidecarRef.current,
            tags: tagText.split(',').map((tag) => tag.trim()).filter(Boolean),
          }
        : await readSidecar(directory, entry.imageName);
      const restored: Sidecar = {
        ...targetSidecar,
        [entry.field]: entry.oldValue,
        timestamp: new Date().toISOString(),
      };
      await writeSidecar(directory, entry.imageName, restored);
      sidecarRef.current = restored;
      setSidecar(restored);
      setTagText(restored.tags.join(', '));
      setDirty(false);
      const nextHistory = undoStackRef.current.slice(0, -1);
      undoStackRef.current = nextHistory;
      setUndoStack(nextHistory);
      setNotice('已撤銷');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '撤銷保存失敗');
    } finally {
      setBusy(false);
      undoRunning.current = false;
    }
  };

  const handleWorkbenchKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const target = event.target;
    if (!viewerElement.current || !(target instanceof Node) || !viewerElement.current.contains(target)) return;
    if (target instanceof HTMLElement && (
      target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(target.tagName)
    )) return;
    if (!currentEntry || busy || undoRunning.current) return;

    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      event.stopPropagation();
      const nextIndex = index + (event.key === 'ArrowRight' ? 1 : -1);
      if (nextIndex >= 0 && nextIndex < entries.length) void openImage(nextIndex);
      return;
    }

    const verdictKeys: Record<string, Verdict> = {
      '1': 'true_defect', '2': 'false_alarm', '3': 'reflection',
    };
    const verdict = verdictKeys[event.key];
    if (verdict) {
      event.preventDefault();
      event.stopPropagation();
      updateReviewField('verdict', verdict);
      return;
    }

    if (event.key.toLowerCase() === 'u') {
      event.preventDefault();
      event.stopPropagation();
      void undoReviewChange();
    } else if (event.key.toLowerCase() === 'r') {
      event.preventDefault();
      event.stopPropagation();
      const statuses: ReviewStatus[] = ['none', 'need_review', 'done'];
      const currentStatus = statuses.indexOf(sidecar.review_status);
      updateReviewField('review_status', statuses[(currentStatus + 1) % statuses.length]);
    } else if (event.key.toLowerCase() === 'b') {
      event.preventDefault();
      event.stopPropagation();
      updateReviewField('bookmarked', !sidecar.bookmarked);
    }
  };

  useEffect(() => {
    if (!viewerElement.current || !window.OpenSeadragon) return;
    const instance = window.OpenSeadragon({
      element: viewerElement.current,
      showNavigationControl: false,
      showNavigator: true,
      animationTime: 0.25,
      maxZoomPixelRatio: 24,
      visibilityRatio: 1,
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: false },
    });
    const syncZoomPercent = () => {
      if (!instance.isOpen()) return;
      const homeZoom = instance.viewport.getHomeZoom();
      if (homeZoom > 0) setZoomPercent(Math.max(1, Math.round(instance.viewport.getZoom(true) / homeZoom * 100)));
    };
    instance.addHandler('open', () => {
      const bounds = viewportBoundsToRestore.current;
      viewportBoundsToRestore.current = null;
      if (bounds && window.OpenSeadragon) {
        const Rect = (window.OpenSeadragon as any).Rect;
        instance.viewport.fitBounds(new Rect(bounds.x, bounds.y, bounds.width, bounds.height), true);
        instance.viewport.applyConstraints(true);
      }
      drawRoiOverlays(instance, sidecarRef.current.rois, viewRef.current);
      syncZoomPercent();
    });
    instance.addHandler('animation', syncZoomPercent);
    instance.addHandler('zoom', syncZoomPercent);
    instance.addHandler('canvas-click', async (event: any) => {
      if (!event.quick || !currentHandle.current || !sessionToken) return;
      const point = instance.viewport.viewportToImageCoordinates(
        instance.viewport.pointFromPixel(event.position),
      );
      const x = Math.floor(point.x);
      const y = Math.floor(point.y);
      const response = await fetch(`/api/images/${currentHandle.current}/pixel?x=${x}&y=${y}`, {
        headers: sessionHeader(sessionToken),
      });
      if (!response.ok) return;
      const result = await response.json();
      setPixelText(`像素 (${result.x}, ${result.y}) · ${Array.isArray(result.value) ? result.value.join(', ') : result.value}`);
    });
    const element = viewerElement.current;
    const onPointerDown = (event: PointerEvent) => {
      if (!event.shiftKey || event.button !== 0 || !currentHandle.current || !viewRef.current) return;
      const bounds = element!.getBoundingClientRect();
      const startX = event.clientX - bounds.left;
      const startY = event.clientY - bounds.top;
      roiDrag.current = { startX, startY };
      setRoiDraft({ startX, startY, endX: startX, endY: startY });
      instance.setMouseNavEnabled(false);
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    };
    const onPointerMove = (event: PointerEvent) => {
      const start = roiDrag.current;
      const bounds = element!.getBoundingClientRect();
      if (start) {
        setRoiDraft({
          ...start,
          endX: event.clientX - bounds.left,
          endY: event.clientY - bounds.top,
        });
        return;
      }
      const image = viewRef.current;
      if (!element!.contains(event.target as Node) || !image || !currentHandle.current || !instance.isOpen()) return;
      const pixel = new (window.OpenSeadragon as any).Point(event.clientX - bounds.left, event.clientY - bounds.top);
      const sourcePoint = instance.viewport.viewportToImageCoordinates(instance.viewport.pointFromPixel(pixel, true));
      const x = Math.floor(sourcePoint.x);
      const y = Math.floor(sourcePoint.y);
      let rgb: [number, number, number] | null = null;
      const sampleCanvas = displayCanvas.current;
      if (sampleCanvas && x >= 0 && y >= 0 && x < image.width && y < image.height) {
        try {
          const sample = sampleCanvas.getContext('2d', { willReadFrequently: true })?.getImageData(x, y, 1, 1).data;
          if (sample) rgb = [sample[0], sample[1], sample[2]];
        } catch {
          rgb = null;
        }
      }
      setHoverPoint({ x, y, rgb });
    };
    const onPointerLeave = () => setHoverPoint(null);
    const onPointerUp = (event: PointerEvent) => {
      const start = roiDrag.current;
      if (!start) return;
      roiDrag.current = null;
      setRoiDraft(null);
      instance.setMouseNavEnabled(true);
      const image = viewRef.current;
      if (!image || !instance.isOpen()) return;
      const bounds = element!.getBoundingClientRect();
      const sourcePoint = (x: number, y: number) => {
        const point = new (window.OpenSeadragon as any).Point(x, y);
        const viewportPoint = instance.viewport.pointFromPixel(point, true);
        return instance.viewport.viewportToImageCoordinates(viewportPoint);
      };
      const first = sourcePoint(start.startX, start.startY);
      const second = sourcePoint(event.clientX - bounds.left, event.clientY - bounds.top);
      const left = Math.max(0, Math.floor(Math.min(first.x, second.x)));
      const top = Math.max(0, Math.floor(Math.min(first.y, second.y)));
      const right = Math.min(image.width, Math.ceil(Math.max(first.x, second.x)));
      const bottom = Math.min(image.height, Math.ceil(Math.max(first.y, second.y)));
      const width = right - left;
      const height = bottom - top;
      if (width < 3 || height < 3) return;
      const roi: Roi = { bbox: [left, top, width, height], label: '', verdict: 'unset', comment: '' };
      setSidecar((current) => ({ ...current, rois: [...current.rois, roi] }));
      setDirty(true);
      setNotice('已新增 ROI；保存判讀以寫入 sidecar');
    };
    const onPointerCancel = () => {
      if (!roiDrag.current) return;
      roiDrag.current = null;
      setRoiDraft(null);
      instance.setMouseNavEnabled(true);
    };
    element?.addEventListener('pointerdown', onPointerDown, true);
    element?.addEventListener('pointerleave', onPointerLeave);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
    viewer.current = instance;
    return () => {
      element?.removeEventListener('pointerdown', onPointerDown, true);
      element?.removeEventListener('pointerleave', onPointerLeave);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerCancel);
      instance.destroy();
      viewer.current = null;
    };
  }, [drawRoiOverlays, sessionToken]);

  useEffect(() => {
    currentHandle.current = view?.imageHandle ?? '';
    if (!viewer.current) return;
    if (view?.displayUrl) viewer.current.open({ type: 'image', url: view.displayUrl });
    else viewer.current.close();
  }, [view]);

  useEffect(() => {
    displayCanvas.current = null;
    if (!view?.displayUrl) {
      setHoverPoint(null);
      return;
    }
    let active = true;
    const image = new Image();
    image.onload = () => {
      if (!active) return;
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (context) {
        context.drawImage(image, 0, 0);
        displayCanvas.current = canvas;
      }
    };
    image.src = view.displayUrl;
    return () => {
      active = false;
      displayCanvas.current = null;
    };
  }, [view?.displayUrl]);

  useEffect(() => {
    if (view && viewer.current?.isOpen()) drawRoiOverlays(viewer.current, sidecar.rois, view);
  }, [drawRoiOverlays, sidecar.rois, view]);

  useEffect(() => () => {
    if (view?.displayUrl) URL.revokeObjectURL(view.displayUrl);
    if (view?.imageHandle && sessionToken) {
      void fetch(`/api/images/${view.imageHandle}`, { method: 'DELETE', headers: sessionHeader(sessionToken) });
    }
  }, [sessionToken, view?.displayUrl, view?.imageHandle]);

  if (!sessionToken) {
    return (
      <main className="connect-screen">
        <section className="connect-card">
          <div className="brand-mark">CV</div>
          <p className="eyebrow">LOCAL REVIEW WORKBENCH</p>
          <h1>影像判讀工作台</h1>
          <p className="muted">連線只限本機。配對碼會顯示在 Python 服務視窗。</p>
          <label htmlFor="pairing-code">本機配對碼</label>
          <input id="pairing-code" type="password" autoComplete="off" value={pairingCode}
            onChange={(event) => setPairingCode(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void connect()} />
          <button className="primary wide" onClick={() => void connect()}>連線到本機服務</button>
          <p className="connect-note">影像留在已授權的資料夾；服務只接收目前顯示影像的暫存副本。</p>
          <p className="notice" role="status">{notice}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="workbench" onKeyDownCapture={handleWorkbenchKeyDown}>
      <header className="topbar">
        <div className="brand"><span className="brand-mark small">CV</span><div><strong>Review Workbench</strong><small>LOCAL IMAGE REVIEW</small></div></div>
        <div className="top-actions">
          <span className="connection"><i /> 本機服務已連線</span>
          <button className="primary" onClick={() => void chooseFolder()} disabled={busy}>選擇資料夾</button>
        </div>
      </header>
      <div className="workspace">
        <aside className="image-rail" aria-label="影像清單">
          <div className="rail-head"><div><span className="eyebrow">DATASET</span><h2>{directory?.name ?? '尚未選擇'}</h2></div><span className="count">{entries.length}</span></div>
          {entries.length ? <div className="image-list">
            {entries.map((entry, itemIndex) => (
              <button key={entry.name} className={`image-row ${index === itemIndex ? 'selected' : ''}`}
                onClick={() => void openImage(itemIndex)} disabled={busy} aria-current={index === itemIndex ? 'true' : undefined}>
                <span className="row-index">{String(itemIndex + 1).padStart(2, '0')}</span>
                <span className="row-name">{entry.name}</span>
                {index === itemIndex && <span className="active-dot" />}
              </button>
            ))}
          </div> : <div className="empty-rail"><span className="folder-icon">▤</span><p>授權資料夾後<br />影像會顯示在這裡</p></div>}
          <div className="rail-foot">只列 PNG · JPEG · TIFF</div>
        </aside>

        <section className="viewer-column">
          <div className="viewer-toolbar">
            <div className="image-title"><strong>{currentEntry?.name ?? '影像檢視器'}</strong><span>{progress}</span></div>
            <div className="viewer-actions">
              <button aria-label="上一張" title="上一張" disabled={index <= 0 || busy} onClick={() => void openImage(index - 1)}>←</button>
              <button aria-label="下一張" title="下一張" disabled={index < 0 || index >= entries.length - 1 || busy} onClick={() => void openImage(index + 1)}>→</button>
              <span className="tool-divider" />
              <button aria-label="縮小" title="縮小" disabled={!view} onClick={() => zoomBy(0.75)}>−</button>
              <button aria-label="放大" title="放大" disabled={!view} onClick={() => zoomBy(1.35)}>＋</button>
              <button aria-label="重設檢視" title="重設檢視" disabled={!view} onClick={() => viewer.current?.viewport.goHome()}>⌂</button>
            </div>
          </div>
          <div className="viewer-stage">
            <div ref={viewerElement} className="osd-canvas" aria-label="影像畫布" />
            {view && <div className="hover-readout" aria-label="游標資訊">
              {hoverPoint?.rgb
                ? `x=${hoverPoint.x}, y=${hoverPoint.y} · RGB=(${hoverPoint.rgb.join(', ')})`
                : hoverPoint ? `x=${hoverPoint.x}, y=${hoverPoint.y}` : '移入影像查看顯示值'}
              {` · zoom=${zoomPercent}% · hover RGB 為顯示值；點擊讀取原始真值`}
            </div>}
            {roiDraft && <div className="roi-draft" style={{
              left: Math.min(roiDraft.startX, roiDraft.endX),
              top: Math.min(roiDraft.startY, roiDraft.endY),
              width: Math.abs(roiDraft.endX - roiDraft.startX),
              height: Math.abs(roiDraft.endY - roiDraft.startY),
            }} />}
            {!view && <div className="viewer-empty"><div className="image-glyph">▧</div><strong>選擇資料夾開始判讀</strong><span>滾輪縮放 · 拖曳平移 · 點擊讀取像素真值</span><button onClick={() => void chooseFolder()}>開啟本機資料夾</button></div>}
            {busy && <div className="loading"><span className="spinner" />影像載入中…</div>}
            {view && <div className="pixel-readout" role="status">{pixelText}</div>}
          </div>
          <footer className="viewer-footer">
            <span>{view ? `${view.width} × ${view.height} · ${view.bitDepth}-bit · ${view.channels === 1 ? '灰階' : `${view.channels} channels`}` : '尚未載入影像'}</span>
            <span className="undo-count">可撤 {undoStack.length} 筆</span>
            <span className="status-copy" role="status">{notice}</span>
          </footer>
        </section>

        <aside className="inspector" aria-label="判讀資訊">
          <div className="inspector-head"><div><span className="eyebrow">REVIEW</span><h2>影像標記</h2></div><button className={`bookmark ${sidecar.bookmarked ? 'on' : ''}`} aria-label="切換書籤" disabled={!currentEntry || busy} onClick={() => updateReviewField('bookmarked', !sidecar.bookmarked)}>{sidecar.bookmarked ? '★' : '☆'}</button></div>
          <label htmlFor="review-status">審查狀態</label>
          <select id="review-status" value={sidecar.review_status} disabled={!currentEntry || busy} onChange={(event) => updateReviewField('review_status', event.target.value as ReviewStatus)}>
            <option value="none">未審查</option><option value="need_review">需要複查</option><option value="done">已完成</option>
          </select>
          <label htmlFor="verdict">判讀結果</label>
          <select id="verdict" value={sidecar.verdict} disabled={!currentEntry || busy} onChange={(event) => updateReviewField('verdict', event.target.value as Verdict)}>
            <option value="unset">尚未判定</option><option value="true_defect">真缺陷</option><option value="false_alarm">誤報</option><option value="reflection">反光／非缺陷</option>
          </select>
          <label htmlFor="tags">標籤 <span>以逗號分隔</span></label>
          <input id="tags" value={tagText} disabled={!currentEntry || busy} placeholder="例如：scratch, edge" onChange={(event) => { setTagText(event.target.value); setDirty(true); }} />
          <label htmlFor="comment">判讀備註</label>
          <textarea id="comment" rows={5} value={sidecar.comment} disabled={!currentEntry || busy} placeholder="記錄觀察與後續處理…" onChange={(event) => updateSidecar({ comment: event.target.value })} />
          <section className="roi-panel" aria-label="ROI 標記">
            <div className="roi-panel-heading"><strong>ROI 區域</strong><span>{sidecar.rois.length}</span></div>
            {sidecar.rois.length ? <ul>
              {sidecar.rois.map((roi, roiIndex) => (
                <li key={`${roiIndex}-${roi.bbox.join('-')}`}>
                  <div><strong>ROI {roiIndex + 1}</strong><small>x={roi.bbox[0]} · y={roi.bbox[1]} · w={roi.bbox[2]} · h={roi.bbox[3]}</small></div>
                  <button type="button" aria-label={`移除 ROI ${roiIndex + 1}`} disabled={!currentEntry || busy}
                    onClick={() => updateSidecar({ rois: sidecar.rois.filter((_, itemIndex) => itemIndex !== roiIndex) })}>×</button>
                </li>
              ))}
            </ul> : <p>尚無 ROI</p>}
            <small className="roi-hint">在影像上按住 Shift 拖曳新增</small>
          </section>
          <div className="sidecar-path"><span className="file-icon">▤</span><div><small>保存為相鄰 sidecar</small><strong>{currentEntry ? sidecarName(currentEntry.name) : '尚未選擇影像'}</strong></div></div>
          <button className="primary save-button" disabled={!currentEntry || !dirty || busy} onClick={() => void saveSidecar()}>{busy ? '處理中…' : dirty ? '保存判讀' : '內容已保存'}</button>
          <p className="immutable-note"><span>●</span> 原始影像保持唯讀</p>
        </aside>
      </div>
      {!('showDirectoryPicker' in window) && <div className="browser-warning" role="status">請以最新版 Edge 或 Chrome 使用資料夾授權功能。</div>}
    </main>
  );
}
