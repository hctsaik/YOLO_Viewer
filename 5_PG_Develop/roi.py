"""roi — ROI 框幾何(Tier A,純邏輯)。

依契約 3_Architect_Design/04_roi.md 實作。
所有框為整數 (x, y, w, h),座標系為影像 source 像素座標(原點左上)。
僅依賴 numpy 與 Python 標準庫。純函式、無狀態、無副作用。
"""


def normalize(x, y, w, h):
    """把可能反向(負寬/負高)的框轉成左上角原點 + 正寬高的標準框,並轉 int。

    先做幾何(反向處理),再 int() 截斷向 0。
    """
    if w < 0:
        x = x + w
        w = -w
    if h < 0:
        y = y + h
        h = -h
    return (int(x), int(y), int(w), int(h))


def clamp_box(box, img_w, img_h):
    """先 normalize,再用 xyxy 夾到影像範圍;完全在界外 → 退化為空交集。"""
    x, y, w, h = normalize(*box)
    img_w = int(img_w)
    img_h = int(img_h)
    x1, y1, x2, y2 = x, y, x + w, y + h
    x1 = min(max(x1, 0), img_w)
    x2 = min(max(x2, 0), img_w)
    y1 = min(max(y1, 0), img_h)
    y2 = min(max(y2, 0), img_h)
    return (int(x1), int(y1), int(x2 - x1), int(y2 - y1))


def crop(array, box):
    """回 array[y:y+h, x:x+w];空框 → 對應軸長度為 0 的陣列。"""
    x, y, w, h = box
    return array[y:y + h, x:x + w]


def area(box):
    """w * h;空框 → 0。"""
    _, _, w, h = box
    return int(w * h)


def contains(box, x, y):
    """半開區間命中:x_box <= x < x_box+w and y_box <= y < y_box+h。"""
    bx, by, bw, bh = box
    return bool(bx <= x < bx + bw and by <= y < by + bh)


def to_xyxy(box):
    """(x, y, x+w, y+h);右下端點為排除端點(exclusive)。"""
    x, y, w, h = box
    return (int(x), int(y), int(x + w), int(y + h))


def from_xyxy(x1, y1, x2, y2):
    """由兩角點建框,內部走 normalize,允許 x2<x1 / y2<y1。"""
    return normalize(x1, y1, x2 - x1, y2 - y1)
