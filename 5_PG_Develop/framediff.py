"""framediff 模組實作(PG / U-Net 上採樣)。

依契約:3_Architect_Design/12_framediff.md(§2 I/O、§2.4 BT.601 灰階加權、
§2.5 嚴格 > 二值化、§3.3 4-連通 iterative flood-fill / raster 發現順序、
§3.4 highlight 半開區間 + thickness 向內加厚、§4 邊界)。

兩張同形 RGB uint8 影像 A、B 的進階變化分析:
  change_mask  → (H,W) uint8 {0,1} 變化遮罩
  change_ratio → 內建 float [0,1] 變化率
  change_regions → list[[x,y,w,h]] 連通變化區 bbox
  highlight    → (H,W,3) uint8,在 B 的 copy 上畫變化區外框

純函式、無副作用、不 mutate 輸入;僅依賴 numpy(本檔不 import 任何業務模組)。
"""
import numpy as np

# BT.601 luma 加權係數(§2.4):gray = 0.299R + 0.587G + 0.114B(係數和 == 1.0)。
_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float64)


def _gray(img: np.ndarray) -> np.ndarray:
    # §2.4:在 float64 上做加權,不在灰階階段取整。img: (H,W,3) → (H,W) float64。
    return img.astype(np.float64) @ _LUMA


def _check_same_shape(A: np.ndarray, B: np.ndarray) -> None:
    # §4a:四函式皆要求 A.shape == B.shape(完全相等),否則 ValueError。
    if A.shape != B.shape:
        raise ValueError(
            "A.shape != B.shape: %r vs %r" % (A.shape, B.shape))


def change_mask(A: np.ndarray, B: np.ndarray, threshold: int = 30) -> np.ndarray:
    """灰階化 A、B → 逐像素灰階絕對差 → diff > threshold 為「變化」。

    回 (H, W) 的 np.uint8 遮罩,值僅 {0, 1}(1=變化)。要求 A.shape == B.shape。
    """
    _check_same_shape(A, B)
    gA = _gray(A)
    gB = _gray(B)
    d = np.abs(gA - gB)               # §2.5-2:float64 逐像素灰階絕對差,不先取整。
    mask = (d > threshold)            # §2.5-3:嚴格大於 >(d == threshold 視為未變化)。
    return mask.astype(np.uint8)      # §2.3:值 ∈ {0,1},dtype uint8,(H,W)。


def change_ratio(A: np.ndarray, B: np.ndarray, threshold: int = 30) -> float:
    """變化像素數 / 總像素數(總數 = H*W);回 Python float,值域 [0.0, 1.0]。

    要求 A.shape == B.shape。
    """
    _check_same_shape(A, B)
    m = change_mask(A, B, threshold)           # §3.2:共用同一變化定義。
    H, W = m.shape
    return float(int(m.sum()) / (H * W))       # §2.3:內建 float,非 np.float64。


def change_regions(A: np.ndarray, B: np.ndarray, threshold: int = 30,
                   min_area: int = 1, connectivity: int = 4) -> list:
    """對 change_mask 做 4-連通元件標記,每個元件回 [x, y, w, h](絕對像素)。

    僅保留 area(元件像素數) >= min_area 者。回 list[list[int]],發現順序見 §3.3。
    要求 A.shape == B.shape;connectivity 非 4 → ValueError。
    """
    _check_same_shape(A, B)
    if connectivity != 4:                       # §2.6 / §4e:本輪僅支援 4-連通。
        raise ValueError(
            "connectivity must be 4 (got %r); 8-connectivity not supported"
            % (connectivity,))

    eff_min_area = max(int(min_area), 1)        # §2.6 / §4d:min_area < 1 當 1。

    m = change_mask(A, B, threshold)            # §3.3-2:共用同一變化定義。
    H, W = m.shape
    visited = np.zeros((H, W), dtype=bool)

    regions = []
    # §3.3-3:raster 掃描順序(row 由上而下、col 由左而右);種子首次被遇到的順序
    # 即元件的「發現順序」。
    for y in range(H):
        for x in range(W):
            if m[y, x] != 1 or visited[y, x]:
                continue
            # iterative flood fill(顯式 stack,4-鄰),收集整個連通元件。
            visited[y, x] = True
            stack = [(y, x)]
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            while stack:
                cy, cx = stack.pop()
                area += 1
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                # 4-鄰:(y-1,x),(y+1,x),(y,x-1),(y,x+1),須在影像內且 m==1 且未標記。
                for ny, nx in ((cy - 1, cx), (cy + 1, cx),
                               (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < H and 0 <= nx < W \
                            and m[ny, nx] == 1 and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            # §3.3-5:過濾 area >= eff_min_area。
            if area >= eff_min_area:
                # §3.3-4:bbox = [x, y, w, h] 半開寬高,皆 Python int。
                regions.append([
                    int(min_x), int(min_y),
                    int(max_x - min_x + 1), int(max_y - min_y + 1),
                ])
    return regions


def highlight(A: np.ndarray, B: np.ndarray, threshold: int = 30,
              color=(255, 0, 0), thickness: int = 1) -> np.ndarray:
    """回 B 的 copy(輸入永不 mutate),在每個變化區 bbox 畫空心外框。

    回 (H, W, 3) uint8,shape 同 B。要求 A.shape == B.shape。
    """
    _check_same_shape(A, B)
    # §3.4-2:固定 min_area=1, connectivity=4 取變化區。
    regions = change_regions(A, B, threshold, min_area=1, connectivity=4)
    out = B.copy()                              # §3.4-3 / §4g:不 mutate B。
    H, W = out.shape[0], out.shape[1]

    if thickness <= 0:                          # §2.7 / §4f:t<=0 → 不畫任何像素。
        return out

    for x, y, w, h in regions:
        # §2.7:thickness 向框內加厚;t >= min(w,h) → 實心填滿。
        t = min(int(thickness), min(w, h))
        for i in range(t):
            top = y + i
            bottom = y + h - 1 - i
            left = x + i
            right = x + w - 1 - i
            # 半開區間外框第 i 圈:col ∈ [left, right]、row ∈ [top, bottom]。
            # 夾界防禦(overlay 同款;regions 天然在界內,仍防禦)。
            r0 = max(top, 0)
            r1 = min(bottom, H - 1)
            c0 = max(left, 0)
            c1 = min(right, W - 1)
            if r0 > r1 or c0 > c1:
                continue
            # 上、下邊(整列 col ∈ [c0,c1]),左、右邊(整行 row ∈ [r0,r1])。
            if top >= 0 and top <= H - 1:
                out[top, c0:c1 + 1, :] = color
            if bottom >= 0 and bottom <= H - 1:
                out[bottom, c0:c1 + 1, :] = color
            if left >= 0 and left <= W - 1:
                out[r0:r1 + 1, left, :] = color
            if right >= 0 and right <= W - 1:
                out[r0:r1 + 1, right, :] = color
    return out
