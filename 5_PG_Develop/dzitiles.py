"""dzitiles — 把一張 HxWx3 uint8 RGB 大圖切成 Deep Zoom(DZI)金字塔瓦片 + .dzi 描述。

實作(/pg 產物),依 3_Architect_Design/18_dzitiles.md 契約 + 4_PM_Feedback/test_dzitiles.py。

核心純函式(num_levels / level_dimensions / dzi_descriptor / tile / build_tiles /
to_png_bytes / to_data_url)零檔案 I/O、零 GUI、零網路;唯一碰檔案者為薄 write 包裝
write_dzi。降採樣一律用 PIL.Image.BOX(面積平均,數學上正確的影像金字塔),每層只縮一次整圖。

僅依賴 numpy / Pillow / Python 標準庫;不 import 任何業務模組(imgio/viewport/app)。
"""
import base64
import io
import math
import os

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# 層級 / 尺寸幾何
# ---------------------------------------------------------------------------

def num_levels(width: int, height: int) -> int:
    """DZI 層數 = ceil(log2(max(width, height))) + 1。

    max(width,height) == 1 → 回 1(log2(1)=0,公式自然成立)。
    width/height <= 0 → ValueError。
    """
    if width <= 0 or height <= 0:
        raise ValueError("width/height 必須 > 0:width=%r height=%r" % (width, height))
    longest = max(width, height)
    return int(math.ceil(math.log2(longest))) + 1


def level_dimensions(width: int, height: int, level: int) -> tuple:
    """回 (levelW, levelH)。

    max_level = num_levels(width,height) - 1;scale = 2 ** (max_level - level);
    levelW = ceil(width / scale);levelH = ceil(height / scale)。
    level < 0 或 level > max_level → ValueError。
    """
    max_level = num_levels(width, height) - 1  # 順帶守 width/height>0
    if level < 0 or level > max_level:
        raise ValueError(
            "level 超界:level=%r 合法範圍 [0, %d]" % (level, max_level))
    scale = 2 ** (max_level - level)
    level_w = int(math.ceil(width / scale))
    level_h = int(math.ceil(height / scale))
    return (level_w, level_h)


# ---------------------------------------------------------------------------
# .dzi descriptor(逐字釘死)
# ---------------------------------------------------------------------------

def dzi_descriptor(width: int, height: int, tile_size: int = 254,
                   overlap: int = 1, fmt: str = "png") -> str:
    """回標準單行 .dzi XML 字串(屬性順序 Format→Overlap→TileSize、Size 為 Height→Width)。"""
    if width <= 0 or height <= 0:
        raise ValueError("width/height 必須 > 0:width=%r height=%r" % (width, height))
    if tile_size <= 0:
        raise ValueError("tile_size 必須 > 0:%r" % (tile_size,))
    if overlap < 0:
        raise ValueError("overlap 必須 >= 0:%r" % (overlap,))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        'Format="%s" Overlap="%d" TileSize="%d">'
        '<Size Height="%d" Width="%d"/></Image>'
        % (fmt, overlap, tile_size, height, width)
    )


# ---------------------------------------------------------------------------
# 縮放 + 切片
# ---------------------------------------------------------------------------

def _scaled_level(array: np.ndarray, level: int) -> np.ndarray:
    """把 array(HxWx3 uint8)縮到該 level 尺寸(PIL BOX),回 HxWx3 uint8。

    最高層(scale=1)尺寸 == 原尺寸,resize 為 no-op(精確切片來源)。
    """
    height, width = array.shape[0], array.shape[1]
    level_w, level_h = level_dimensions(width, height, level)
    if (level_w, level_h) == (width, height):
        # 最高層:精確複製(不縮放、不失真),並與 PIL 路徑一致回 uint8 拷貝。
        return np.array(array, dtype=np.uint8, copy=True)
    img = Image.fromarray(array)  # 從 array 複製,不 mutate 輸入
    # PIL resize 取 (width, height) 序;面積平均降採樣用 BOX。
    scaled = img.resize((level_w, level_h), Image.BOX)
    return np.asarray(scaled, dtype=np.uint8)


def tile(array: np.ndarray, level: int, col: int, row: int,
         tile_size: int = 254, overlap: int = 1) -> np.ndarray:
    """縮到該 level 尺寸後裁出 (col,row) 含 overlap 的瓦片;回 HxWx3 uint8。

    瓦片像素區間(Deep Zoom,半開區間):
      x0 = max(0, col*ts - ov);  x1 = min(levelW, col*ts + ts + ov)
      y0 = max(0, row*ts - ov);  y1 = min(levelH, row*ts + ts + ov)
    col/row 超出該 level 格數 → ValueError;level 超界 → ValueError;
    tile_size<=0 / overlap<0 → ValueError。
    """
    if tile_size <= 0:
        raise ValueError("tile_size 必須 > 0:%r" % (tile_size,))
    if overlap < 0:
        raise ValueError("overlap 必須 >= 0:%r" % (overlap,))
    height, width = array.shape[0], array.shape[1]
    # level_dimensions 會在 level 超界時拋 ValueError。
    level_w, level_h = level_dimensions(width, height, level)
    cols = int(math.ceil(level_w / tile_size))
    rows = int(math.ceil(level_h / tile_size))
    if col < 0 or col >= cols or row < 0 or row >= rows:
        raise ValueError(
            "col/row 超界:col=%r row=%r 該層格數 cols=%d rows=%d"
            % (col, row, cols, rows))
    scaled = _scaled_level(array, level)
    x0 = max(0, col * tile_size - overlap)
    x1 = min(level_w, col * tile_size + tile_size + overlap)
    y0 = max(0, row * tile_size - overlap)
    y1 = min(level_h, row * tile_size + tile_size + overlap)
    return scaled[y0:y1, x0:x1]


# ---------------------------------------------------------------------------
# PNG 編碼
# ---------------------------------------------------------------------------

def to_png_bytes(rgb_uint8: np.ndarray) -> bytes:
    """把 HxWx3 uint8 編成 PNG 檔位元組;以 PNG magic 開頭。

    非 uint8 / 形狀非 HxWx3 → ValueError。
    """
    if not isinstance(rgb_uint8, np.ndarray):
        raise ValueError("需要 numpy.ndarray,得到 %r" % (type(rgb_uint8),))
    if rgb_uint8.dtype != np.uint8:
        raise ValueError("需要 uint8,得到 dtype=%r" % (rgb_uint8.dtype,))
    if rgb_uint8.ndim != 3 or rgb_uint8.shape[2] != 3:
        raise ValueError("需要 HxWx3,得到 shape=%r" % (rgb_uint8.shape,))
    img = Image.fromarray(rgb_uint8, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def to_data_url(rgb_uint8: np.ndarray) -> str:
    """回 "data:image/png;base64,<b64>"。"""
    b64 = base64.b64encode(to_png_bytes(rgb_uint8)).decode("ascii")
    return "data:image/png;base64," + b64


# ---------------------------------------------------------------------------
# 完整金字塔
# ---------------------------------------------------------------------------

def build_tiles(array: np.ndarray, tile_size: int = 254, overlap: int = 1,
                fmt: str = "png") -> dict:
    """回完整金字塔 dict(見設計 §3.3)。tiles 值 = 該瓦片 PNG bytes(fmt=="png")。

    每層只縮一次整圖,再對該層 scaled 切多片。
    """
    if tile_size <= 0:
        raise ValueError("tile_size 必須 > 0:%r" % (tile_size,))
    if overlap < 0:
        raise ValueError("overlap 必須 >= 0:%r" % (overlap,))
    height, width = array.shape[0], array.shape[1]
    n_levels = num_levels(width, height)  # 守 width/height>0
    max_level = n_levels - 1

    tiles = {}
    for level in range(n_levels):
        level_w, level_h = level_dimensions(width, height, level)
        scaled = _scaled_level(array, level)  # 每層只縮一次整圖
        cols = int(math.ceil(level_w / tile_size))
        rows = int(math.ceil(level_h / tile_size))
        level_tiles = {}
        for row in range(rows):
            for col in range(cols):
                x0 = max(0, col * tile_size - overlap)
                x1 = min(level_w, col * tile_size + tile_size + overlap)
                y0 = max(0, row * tile_size - overlap)
                y1 = min(level_h, row * tile_size + tile_size + overlap)
                patch = scaled[y0:y1, x0:x1]
                level_tiles["%d_%d" % (col, row)] = to_png_bytes(patch)
        tiles[level] = level_tiles

    return {
        "width": int(width),
        "height": int(height),
        "tile_size": int(tile_size),
        "overlap": int(overlap),
        "max_level": int(max_level),
        "num_levels": int(n_levels),
        "dzi": dzi_descriptor(width, height, tile_size, overlap, fmt),
        "tiles": tiles,
    }


# ---------------------------------------------------------------------------
# 薄 write 包裝(唯一碰檔案者)
# ---------------------------------------------------------------------------

def write_dzi(out_dir, array: np.ndarray, name: str = "image",
              tile_size: int = 254, overlap: int = 1, fmt: str = "png") -> str:
    """落 OSD 標準 DZI 佈局到磁碟,回 .dzi 檔的絕對路徑字串。

      <out_dir>/<name>.dzi                              ← descriptor(UTF-8)
      <out_dir>/<name>_files/<level>/<col>_<row>.<fmt>  ← 各瓦片 bytes
    out_dir 不存在 → 自動建立(含 _files 子目錄樹)。
    """
    pyramid = build_tiles(array, tile_size=tile_size, overlap=overlap, fmt=fmt)
    out_dir = os.fspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    dzi_path = os.path.join(out_dir, "%s.dzi" % name)
    with open(dzi_path, "w", encoding="utf-8") as f:
        f.write(pyramid["dzi"])

    files_root = os.path.join(out_dir, "%s_files" % name)
    for level, level_tiles in pyramid["tiles"].items():
        level_dir = os.path.join(files_root, str(level))
        os.makedirs(level_dir, exist_ok=True)
        for key, png in level_tiles.items():
            with open(os.path.join(level_dir, "%s.%s" % (key, fmt)), "wb") as f:
                f.write(png)

    return os.path.abspath(dzi_path)
