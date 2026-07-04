"""imgadjust 模組實作(PG 產物;依 3_Architect_Design/25_imgadjust.md 契約)。

純邏輯、零 I/O、零 GUI(Tier A)。純顯示層工具:只影響畫面,不影響偵測/判定/匯出。
輸入輸出皆為 uint8 RGB ndarray,shape (H, W, 3);不 mutate 輸入,回新陣列。
"""
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def brightness_contrast(img, brightness=0.0, contrast=1.0):
    """亮度(加法)+ 對比(乘法,支點 128):out = clip(round((img-128)*contrast+128+brightness), 0, 255)。"""
    out = (img.astype(np.float32) - 128.0) * float(contrast) + 128.0 + float(brightness)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def gamma(img, g=1.0):
    """標準 gamma correction:out = round(255*(img/255)**(1/g))。g<=0 視為 0.01。"""
    g = float(g) if g > 0 else 0.01
    inv = 1.0 / g
    table = np.round((np.arange(256, dtype=np.float64) / 255.0) ** inv * 255.0)
    table = np.clip(table, 0, 255).astype(np.uint8)
    return table[img]


def invert(img):
    """反色:out = 255 - img(先轉 int16 運算避免 uint8 減法環繞)。"""
    return (255 - img.astype(np.int16)).astype(np.uint8)


def stretch_contrast(img):
    """對比度極限拉伸(min-max stretch),逐 channel 各自拉伸;max==min 該 channel 原樣輸出。"""
    out = img.astype(np.float32).copy()
    for c in range(img.shape[2]):
        ch = out[:, :, c]
        lo, hi = float(ch.min()), float(ch.max())
        if hi > lo:
            out[:, :, c] = (ch - lo) / (hi - lo) * 255.0
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def equalize_histogram(img):
    """直方圖均衡化:轉 YCrCb 只均衡 Y(亮度)通道,保留色相/飽和度。缺 cv2 → 回複製品。"""
    if not HAS_CV2:
        return img.copy()
    ycrcb = cv2.cvtColor(img, cv2.COLOR_RGB2YCrCb)
    ycrcb[:, :, 0] = cv2.equalizeHist(ycrcb[:, :, 0])
    return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)


def threshold(img, thresh=128.0):
    """二值化:BT.601 灰階加權,> thresh -> 255,否則 0;複製到三通道。"""
    gray = 0.299 * img[:, :, 0].astype(np.float32) \
        + 0.587 * img[:, :, 1].astype(np.float32) \
        + 0.114 * img[:, :, 2].astype(np.float32)
    binary = np.where(gray > float(thresh), 255, 0).astype(np.uint8)
    return np.stack([binary, binary, binary], axis=-1)


def canny_edges(img, low=100.0, high=200.0):
    """Canny 邊緣偵測:轉灰階 -> cv2.Canny -> 白邊黑底,複製到三通道。缺 cv2 → 回複製品。"""
    if not HAS_CV2:
        return img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, int(low), int(high))
    return np.stack([edges, edges, edges], axis=-1)
