"""驗收測試 — imgio 模組(Tier B, M1b)

由 /pm 依 3_Architect_Design/02_imgio.md 的 I/O 契約與 Acceptance Criteria 轉成的
可執行 pytest。test-first:此時 5_PG_Develop/imgio.py 尚未實作,測試預期會「紅」
(import 不到模組是正常,屬實作未生,不算驗收失敗)。

- import 方式:`import imgio`(conftest 已把 5_PG_Develop 置於 sys.path 最前,遮蔽
  同名第三方套件)。
- 需要實體檔案時一律用 pytest 的 tmp_path,做真實讀寫 round-trip(非只驗物件存在)。
- 每個測試以註解標出對應 AC,供可追溯性稽核。
- 末段 # DERIVED-* 為設計未明列、由 PM 推導的不變量 / property / 反向稽查測試,
  即使與設計同源也能逼出實作 bug。

跑:cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_imgio.py \
        -p no:cacheprovider --strict-markers -q
"""
import base64
import io

import numpy as np
import pytest
from PIL import Image

import imgio  # conftest 已設好 sys.path → 解析到 5_PG_Develop/imgio.py


# ============================================================================
# A. load — 真實讀寫 round-trip
# ============================================================================

def test_load_gray8_png_roundtrip(tmp_path):
    # AC1 — 8-bit 灰階 PNG round-trip
    g8 = np.array([[0, 128, 255], [10, 20, 30]], np.uint8)
    p = tmp_path / "g8.png"
    Image.fromarray(g8, mode="L").save(p)
    d = imgio.load(str(p))
    assert d["bit_depth"] == 8
    assert d["channels"] == 1
    assert d["width"] == 3
    assert d["height"] == 2
    assert d["array"].dtype == np.uint8
    assert d["array"].ndim == 2
    assert np.array_equal(d["array"], g8)


def test_load_gray16_tiff_roundtrip(tmp_path):
    # AC2 — 16-bit 灰階 TIFF round-trip(16-bit 真值不得被截成 8-bit)
    import tifffile
    g16 = np.array([[0, 1000, 65535], [40000, 256, 257]], np.uint16)
    p = tmp_path / "g16.tif"
    tifffile.imwrite(str(p), g16)
    d = imgio.load(str(p))
    assert d["bit_depth"] == 16
    assert d["channels"] == 1
    assert d["array"].dtype == np.uint16
    assert np.array_equal(d["array"], g16)


def test_load_rgb8_png_roundtrip(tmp_path):
    # AC3 — 8-bit RGB PNG round-trip
    rgb = np.zeros((2, 2, 3), np.uint8)
    rgb[0, 0] = [10, 20, 30]
    rgb[1, 1] = [200, 100, 50]
    p = tmp_path / "rgb.png"
    Image.fromarray(rgb, mode="RGB").save(p)
    d = imgio.load(str(p))
    assert d["channels"] == 3
    assert d["bit_depth"] == 8
    assert d["array"].shape == (2, 2, 3)
    assert np.array_equal(d["array"], rgb)


def test_load_tiff_extension_case_insensitive(tmp_path):
    # AC4 — .TIFF 副檔名亦可、大小寫不敏感
    import tifffile
    g8 = np.array([[0, 128, 255], [10, 20, 30]], np.uint8)
    p = tmp_path / "G8.TIFF"
    tifffile.imwrite(str(p), g8)
    d = imgio.load(str(p))
    assert np.array_equal(d["array"], g8)
    assert d["bit_depth"] == 8


def test_load_missing_path_raises_filenotfound(tmp_path):
    # AC5 — 不存在路徑 → FileNotFoundError
    with pytest.raises(FileNotFoundError):
        imgio.load(str(tmp_path / "nope.png"))


def test_load_non_image_raises_valueerror(tmp_path):
    # AC6 — 檔案存在但非影像 → ValueError
    p = tmp_path / "x.png"
    p.write_bytes(b"not an image")
    with pytest.raises(ValueError):
        imgio.load(str(p))


def test_load_width_height_align_shape(tmp_path):
    # AC7 — width/height 對齊 shape(對讀回的 dict 驗不變量)
    rgb = np.zeros((5, 7, 3), np.uint8)
    rgb[1, 2] = [1, 2, 3]
    p = tmp_path / "wh.png"
    Image.fromarray(rgb, mode="RGB").save(p)
    d = imgio.load(str(p))
    assert d["width"] == d["array"].shape[1]
    assert d["height"] == d["array"].shape[0]


# ============================================================================
# B. to_display_rgb — window/level
# ============================================================================

def test_display_auto_normalize_endpoints():
    # AC8 — auto normalize 端點:min→0、max→255
    arr = np.array([[0, 255]], np.uint8)
    out = imgio.to_display_rgb(arr)
    assert out.dtype == np.uint8
    assert out.shape == (1, 2, 3)
    assert out[0, 0, 0] == 0
    assert out[0, 1, 0] == 255


def test_display_auto_normalize_16bit():
    # AC9 — 16-bit auto normalize(min=100, max=4140)
    arr = np.array([[100, 100, 4140]], np.uint16)
    out = imgio.to_display_rgb(arr)
    assert tuple(out[0, 0]) == (0, 0, 0)
    assert tuple(out[0, 2]) == (255, 255, 255)
    assert tuple(out[0, 1]) == (0, 0, 0)  # 值 == min → 0
    assert out.shape == (1, 3, 3)
    assert out.dtype == np.uint8


def test_display_manual_window_linear_midpoint():
    # AC10 — 手動 window/level 線性中點:50/100*255=127.5 → round 128
    arr = np.array([[0, 50, 100]], np.uint16)
    out = imgio.to_display_rgb(arr, lo=0, hi=100)
    assert out[0, 0, 0] == 0
    assert out[0, 2, 0] == 255
    assert out[0, 1, 0] == 128


def test_display_window_clipping():
    # AC11 — window 截斷:value<=lo→0、value>=hi→255、value==lo→0
    arr = np.array([[10, 40, 90]], np.uint16)
    out = imgio.to_display_rgb(arr, lo=40, hi=80)
    assert out[0, 0, 0] == 0    # 10 <= lo
    assert out[0, 2, 0] == 255  # 90 >= hi
    assert out[0, 1, 0] == 0    # 40 == lo → 0


def test_display_gray_to_3channel_equal():
    # AC12 — 灰階→3 通道相等(R==G==B)
    arr = np.array([[0, 255]], np.uint8)
    out = imgio.to_display_rgb(arr)
    assert np.array_equal(out[..., 0], out[..., 1])
    assert np.array_equal(out[..., 1], out[..., 2])


def test_display_rgb_uint8_passthrough():
    # AC13 — RGB uint8 原樣回傳(忽略 lo/hi 不變更內容)
    rgb = np.array([[[10, 20, 30], [200, 100, 50]]], np.uint8)
    out = imgio.to_display_rgb(rgb)
    assert np.array_equal(out, rgb)


def test_display_uniform_no_div_zero():
    # AC14 — 均勻影像(max==min)不除零,回 shape (2,2,3) uint8 全 0
    arr = np.full((2, 2), 7, np.uint8)
    out = imgio.to_display_rgb(arr)
    assert out.shape == (2, 2, 3)
    assert out.dtype == np.uint8
    assert np.all(out == 0)


def test_display_lo_gt_hi_raises():
    # AC15 — 非法 lo>hi → ValueError
    with pytest.raises(ValueError):
        imgio.to_display_rgb(np.zeros((1, 1), np.uint8), lo=200, hi=10)


# ============================================================================
# C. value_at — 原始真值
# ============================================================================

def test_value_at_gray_int_truth():
    # AC16 — 灰階回 int 真值(x=col, y=row;16-bit 不失真)
    arr = np.array([[5, 9], [12, 40000]], np.uint16)
    assert int(imgio.value_at(arr, 0, 0)) == 5
    assert int(imgio.value_at(arr, 1, 0)) == 9     # x=1(col1), y=0(row0)
    assert int(imgio.value_at(arr, 1, 1)) == 40000


def test_value_at_rgb_tuple():
    # AC17 — RGB 回長度 3 的 tuple(x=0, y=1 → row1, col0)
    rgb = np.zeros((2, 2, 3), np.uint8)
    rgb[1, 0] = [7, 8, 9]
    v = imgio.value_at(rgb, 0, 1)
    assert isinstance(v, tuple)
    assert len(v) == 3
    assert tuple(int(c) for c in v) == (7, 8, 9)


def test_value_at_out_of_bounds_x_high():
    # AC18a — x 超界(>=width)→ IndexError
    arr = np.array([[5, 9], [12, 40000]], np.uint16)
    with pytest.raises(IndexError):
        imgio.value_at(arr, 2, 0)


def test_value_at_out_of_bounds_y_high():
    # AC18b — y 超界(>=height)→ IndexError
    arr = np.array([[5, 9], [12, 40000]], np.uint16)
    with pytest.raises(IndexError):
        imgio.value_at(arr, 0, 2)


def test_value_at_out_of_bounds_negative():
    # AC18c — 負座標 → IndexError(契約以 [0,width)/[0,height) 為界,負值不得回繞)
    arr = np.array([[5, 9], [12, 40000]], np.uint16)
    with pytest.raises(IndexError):
        imgio.value_at(arr, -1, 0)


# ============================================================================
# D. crop — 安全 clamp 裁切
# ============================================================================

def test_crop_inside_exact():
    # AC19 — 界內精確:crop(arr,1,1,2,2) == arr[1:3,1:3] == [[5,6],[9,10]]
    arr = np.arange(16, dtype=np.uint8).reshape(4, 4)
    out = imgio.crop(arr, 1, 1, 2, 2)
    assert np.array_equal(out, arr[1:3, 1:3])
    assert np.array_equal(out, np.array([[5, 6], [9, 10]], np.uint8))


def test_crop_overflow_clamp_no_exception():
    # AC20 — 超界 clamp 不丟例外:crop(arr,2,2,10,10) → arr[2:4,2:4],shape (2,2)
    arr = np.arange(16, dtype=np.uint8).reshape(4, 4)
    out = imgio.crop(arr, 2, 2, 10, 10)
    assert out.shape == (2, 2)
    assert np.array_equal(out, arr[2:4, 2:4])


def test_crop_fully_outside_empty():
    # AC21 — 完全界外回空陣列:ndarray、size==0、dtype 一致,不丟例外
    arr = np.arange(16, dtype=np.uint8).reshape(4, 4)
    out = imgio.crop(arr, 100, 100, 5, 5)
    assert isinstance(out, np.ndarray)
    assert out.size == 0
    assert out.dtype == np.uint8


def test_crop_negative_coords_clamp():
    # AC22 — 負座標 clamp:crop(arr,-5,-5,7,7) == arr[0:2,0:2],shape (2,2)
    arr = np.arange(16, dtype=np.uint8).reshape(4, 4)
    out = imgio.crop(arr, -5, -5, 7, 7)
    assert out.shape == (2, 2)
    assert np.array_equal(out, arr[0:2, 0:2])


def test_crop_rgb_keeps_channel_dim():
    # AC23 — RGB 保留通道維:crop(rgb,0,0,2,2).shape == (2,2,3)
    rgb = np.zeros((4, 4, 3), np.uint8)
    out = imgio.crop(rgb, 0, 0, 2, 2)
    assert out.shape == (2, 2, 3)


# ============================================================================
# E. to_png_bytes / to_data_url — 真實可解碼 round-trip
# ============================================================================

def test_png_magic():
    # AC24 — PNG magic header
    b = imgio.to_png_bytes(np.zeros((3, 3, 3), np.uint8))
    assert isinstance(b, bytes)
    assert b[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_decodes_back_pixel_identical():
    # AC25 — PNG 真能被 PIL 解回且像素一致(非只看 bytes 非空)
    rgb = np.zeros((2, 2, 3), np.uint8)
    rgb[0, 0] = [10, 20, 30]
    rgb[1, 1] = [200, 100, 50]
    png = imgio.to_png_bytes(rgb)
    img = Image.open(io.BytesIO(png))
    assert np.array_equal(np.asarray(img), rgb)


def test_data_url_prefix():
    # AC26 — data_url 前綴與型別
    u = imgio.to_data_url(np.zeros((2, 2, 3), np.uint8))
    assert isinstance(u, str)
    assert u.startswith("data:image/png;base64,")


def test_data_url_payload_decodes_to_png_and_pixels():
    # AC27 — data_url payload 解 base64 後為 PNG 且重新解碼像素一致
    rgb = np.zeros((2, 2, 3), np.uint8)
    rgb[0, 0] = [10, 20, 30]
    rgb[1, 1] = [200, 100, 50]
    u = imgio.to_data_url(rgb)
    payload = base64.b64decode(u.split(",", 1)[1])
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(payload))), rgb)


def test_png_non_uint8_raises():
    # AC28 — 非 uint8 → ValueError(避免靜默產生壞 PNG)
    with pytest.raises(ValueError):
        imgio.to_png_bytes(np.zeros((2, 2, 3), np.uint16))


# ============================================================================
# F. thumbnail — 長邊縮放
# ============================================================================

def test_thumbnail_shrink_long_edge_exact():
    # AC29 — 縮小:長邊精確 == max_px,短邊等比例(100*200/400=50)
    arr = np.zeros((100, 400), np.uint16)
    t = imgio.thumbnail(arr, max_px=200)
    assert t.dtype == np.uint8
    assert t.ndim == 3 and t.shape[2] == 3
    assert max(t.shape[0], t.shape[1]) == 200
    assert t.shape[0] == 50


def test_thumbnail_no_upscale():
    # AC30 — 不放大:長邊 40<=256,維持原尺寸
    arr = np.zeros((30, 40, 3), np.uint8)
    t = imgio.thumbnail(arr, max_px=256)
    assert t.shape == (30, 40, 3)


def test_thumbnail_default_max_px_256():
    # AC31 — 預設 max_px=256 生效:長邊→256、短邊→128
    arr = np.zeros((512, 1024), np.uint8)
    t = imgio.thumbnail(arr)
    assert max(t.shape[:2]) == 256
    assert t.shape[0] == 128


# ============================================================================
# DERIVED — 設計未明列、由 PM 推導的不變量 / property / 反向稽查測試
# (即使與設計同源,metamorphic 性質仍能逼出實作 bug)
# ============================================================================

def test_derived_load_value_at_crop_consistency_16bit(tmp_path):
    # DERIVED-1 — 跨函式不變量(真值路線一致性):
    #   16-bit TIFF round-trip 後,value_at 在每個座標的真值
    #   必須等於 load["array"] 與 crop 全圖切出來的同一像素。
    #   這把 AC2/AC16/AC19 串成端到端真值守恆,沒有任何單條 AC 明列。
    import tifffile
    g16 = np.array([[0, 1000, 65535], [40000, 256, 257]], np.uint16)
    p = tmp_path / "consist.tif"
    tifffile.imwrite(str(p), g16)
    arr = imgio.load(str(p))["array"]
    h, w = arr.shape
    full = imgio.crop(arr, 0, 0, w, h)
    assert np.array_equal(full, g16)  # crop 全圖 == 原圖
    for y in range(h):
        for x in range(w):
            # value_at(x=col, y=row) 必須命中 array[y, x](契約座標語意)
            assert int(imgio.value_at(arr, x, y)) == int(g16[y, x])


def test_derived_display_monotonic_no_inversion():
    # DERIVED-2 — property(單調性):auto window/level 是非遞減映射 ——
    #   輸入愈大,顯示值不得變小。設計只給端點,沒保證中間不反轉/不亂跳。
    #   反轉會讓暗的看起來比亮的還亮,是顯示路線的隱性 bug。
    rng = np.random.default_rng(0)
    vals = np.sort(rng.integers(0, 65536, size=64).astype(np.uint16))
    out = imgio.to_display_rgb(vals.reshape(1, -1))[0, :, 0].astype(np.int64)
    assert np.all(np.diff(out) >= 0)


def test_derived_display_idempotent_on_its_own_output():
    # DERIVED-3 — property(冪等):to_display_rgb 的輸出已是 HxWx3 uint8 RGB,
    #   再餵回 to_display_rgb 應原樣回傳(對應 RGB passthrough 契約)。
    #   設計只講「已是 RGB uint8 原樣回傳」,沒講「自家輸出再進去也穩定」——
    #   若實作對 3D 仍做 normalize,這條會抓到。
    arr = np.array([[0, 50, 100, 200]], np.uint16)
    once = imgio.to_display_rgb(arr)
    twice = imgio.to_display_rgb(once)
    assert np.array_equal(once, twice)


def test_derived_crop_is_view_or_equal_subarray():
    # DERIVED-4 — 不變量:任意界內 crop 的每個元素都必須等於原 array 對應位置,
    #   且 dtype 不變。用隨機座標壓多組,擴大覆蓋面(設計只給少數固定座標)。
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, size=(8, 8)).astype(np.uint8)
    for _ in range(20):
        x = int(rng.integers(0, 8))
        y = int(rng.integers(0, 8))
        w = int(rng.integers(1, 6))
        h = int(rng.integers(1, 6))
        out = imgio.crop(arr, x, y, w, h)
        assert out.dtype == np.uint8
        x1 = min(x + w, 8)
        y1 = min(y + h, 8)
        assert np.array_equal(out, arr[y:y1, x:x1])


def test_derived_thumbnail_preserves_aspect_ratio():
    # DERIVED-5 — property(長寬比守恆):縮圖長寬比與原圖一致(±1 px 容差),
    #   設計只逐例給出特定 shape,沒把「比例不被壓扁」抽象成通則。
    arr = np.zeros((300, 900), np.uint16)  # 比例 1:3
    t = imgio.thumbnail(arr, max_px=300)
    assert max(t.shape[:2]) == 300
    # 原比例 height/width = 1/3 → 短邊應約 100
    assert abs(t.shape[0] - 100) <= 1


def test_derived_no_third_party_imgio_shadow():
    # DERIVED-6 — 反向稽查(基礎設施健全性):import imgio 必須解析到
    #   5_PG_Develop/ 的本地模組,而非 PyPI 的同名 imgio 套件。
    #   若 sys.path 遮蔽失效,所有 round-trip 會「假綠」於別人的實作上。
    import os
    assert os.path.normpath("5_PG_Develop") in os.path.normpath(
        os.path.abspath(imgio.__file__))
