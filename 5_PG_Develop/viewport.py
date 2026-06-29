"""viewport(Tier A,純幾何,零 I/O)。

縮放/平移/座標換算的純幾何核心。
契約見 3_Architect_Design/01_viewport.md;驗收見 4_PM_Feedback/test_viewport.py。
刻意零依賴:只用 Python 內建算術(int/float/min/max/round),
不依賴任何外部影像函式庫(見設計第 2 節)。
"""


def fit_zoom(src_w, src_h, disp_w, disp_h):
    """整張圖 fit 進顯示框的 zoom = min(disp_w/src_w, disp_h/src_h)。"""
    if src_w <= 0 or src_h <= 0:
        raise ValueError("src_w/src_h must be > 0")
    if disp_w <= 0 or disp_h <= 0:
        raise ValueError("disp_w/disp_h must be > 0")
    return float(min(disp_w / src_w, disp_h / src_h))


def clamp(v, lo, hi):
    """把 v 夾在 [lo, hi];回傳型別同 v(int 進 int 出、float 進 float 出)。"""
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def crop_rect(src_w, src_h, zoom, cx, cy, disp_w, disp_h):
    """zoom 下、以來源座標 (cx,cy) 為中心的可視來源矩形 (x0,y0,w,h)。
    整數;clamp 在影像內;中心超界由內部 clamp 修正。"""
    if src_w <= 0 or src_h <= 0:
        raise ValueError("src_w/src_h must be > 0")
    if disp_w <= 0 or disp_h <= 0:
        raise ValueError("disp_w/disp_h must be > 0")
    if zoom <= 0:
        raise ValueError("zoom must be > 0")

    view_w = disp_w / zoom
    view_h = disp_h / zoom

    w = clamp(round(view_w), 1, int(src_w))
    h = clamp(round(view_h), 1, int(src_h))

    x0 = round(cx - w / 2)
    y0 = round(cy - h / 2)

    x0 = clamp(x0, 0, int(src_w) - w)
    y0 = clamp(y0, 0, int(src_h) - h)

    return (int(x0), int(y0), int(w), int(h))


def display_to_source(dx, dy, rect, disp_w, disp_h):
    """顯示像素 (dx,dy) → 來源座標 (sx,sy)。rect 為 crop_rect 的輸出。"""
    if disp_w <= 0 or disp_h <= 0:
        raise ValueError("disp_w/disp_h must be > 0")
    x0, y0, w, h = rect
    sx = x0 + dx / disp_w * w
    sy = y0 + dy / disp_h * h
    return (float(sx), float(sy))


def minimap_rect(src_w, src_h, rect):
    """可視矩形 rect 在縮圖上的相對比例 (rx,ry,rw,rh),每個值 ∈ [0,1]。"""
    if src_w <= 0 or src_h <= 0:
        raise ValueError("src_w/src_h must be > 0")
    x0, y0, w, h = rect
    rx = x0 / src_w
    ry = y0 / src_h
    rw = w / src_w
    rh = h / src_h
    return (float(rx), float(ry), float(rw), float(rh))
