"""imgadjust 驗收測試(對應 3_Architect_Design/25_imgadjust.md AC1..AC23)。

跑法:cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_imgadjust.py -p no:cacheprovider --strict-markers -q
"""
import numpy as np
import pytest

import imgadjust


def _solid(value, h=4, w=4):
    """建一張 (h,w,3) uint8 純色圖,每個 channel 都是同一值。"""
    return np.full((h, w, 3), value, dtype=np.uint8)


# ============================== brightness_contrast ==============================
# AC1
def test_brightness_contrast_identity():
    img = np.array([[[0, 50, 128], [200, 255, 30]]], dtype=np.uint8)
    out = imgadjust.brightness_contrast(img, 0.0, 1.0)
    assert np.array_equal(out, img)


# AC2
def test_brightness_contrast_pure_brightness():
    img = _solid(100)
    out = imgadjust.brightness_contrast(img, 50.0, 1.0)
    assert np.all(out == 150)


# AC3
def test_brightness_contrast_brightness_clips_high():
    img = _solid(220)
    out = imgadjust.brightness_contrast(img, 50.0, 1.0)
    assert np.all(out == 255)


# AC4
def test_brightness_contrast_pure_contrast_pivot_128():
    img = _solid(138)
    out = imgadjust.brightness_contrast(img, 0.0, 2.0)
    assert np.all(out == 148)  # (138-128)*2+128 = 148


# AC5
def test_brightness_contrast_contrast_below_pivot():
    img = _solid(108)
    out = imgadjust.brightness_contrast(img, 0.0, 2.0)
    assert np.all(out == 88)  # (108-128)*2+128 = 88


def test_brightness_contrast_contrast_clips_low():
    img = _solid(10)
    out = imgadjust.brightness_contrast(img, 0.0, 2.0)
    assert np.all(out == 0)  # (10-128)*2+128 = -108 -> clip 0


# AC6
def test_brightness_contrast_dtype_and_no_mutate():
    img = _solid(100)
    before = img.copy()
    out = imgadjust.brightness_contrast(img, 50.0, 2.0)
    assert out.dtype == np.uint8
    assert np.array_equal(img, before), "輸入不應被 mutate"


# ============================== gamma ==============================
# AC7
def test_gamma_identity_at_one():
    img = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, axis=2)
    out = imgadjust.gamma(img, 1.0)
    assert np.array_equal(out, img), "gamma=1.0 應為單位映射(逐值相等)"


# AC8
def test_gamma_endpoints_fixed():
    for g in (0.3, 1.0, 2.5, 5.0):
        assert imgadjust.gamma(_solid(0), g)[0, 0, 0] == 0
        assert imgadjust.gamma(_solid(255), g)[0, 0, 0] == 255


# AC9
def test_gamma_nonpositive_clamped():
    img = _solid(64)
    out_neg = imgadjust.gamma(img, -1.0)
    out_clamped = imgadjust.gamma(img, 0.01)
    assert np.array_equal(out_neg, out_clamped)


# AC10
def test_gamma_lut_monotonic():
    img = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, axis=2)
    out = imgadjust.gamma(img, 2.0)
    vals = out[0, :, 0].astype(int)
    assert np.all(np.diff(vals) >= 0), "gamma LUT 應單調不遞減"


# ============================== invert ==============================
# AC11
def test_invert_known_values():
    img = np.array([[[0, 0, 0], [128, 128, 128], [255, 255, 255]]], dtype=np.uint8)
    out = imgadjust.invert(img)
    assert list(out[0, 0]) == [255, 255, 255]
    assert list(out[0, 1]) == [127, 127, 127]
    assert list(out[0, 2]) == [0, 0, 0]


# AC12
def test_invert_is_involution():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(6, 6, 3), dtype=np.uint8)
    assert np.array_equal(imgadjust.invert(imgadjust.invert(img)), img)


# ============================== stretch_contrast ==============================
# AC13
def test_stretch_contrast_maps_min_max():
    ch = np.array([[50, 200], [100, 150]], dtype=np.uint8)
    img = np.stack([ch, ch, ch], axis=-1)
    out = imgadjust.stretch_contrast(img)
    assert out[0, 0, 0] == 0    # 50 -> min -> 0
    assert out[0, 1, 0] == 255  # 200 -> max -> 255


# AC14
def test_stretch_contrast_flat_channel_no_div_zero():
    img = _solid(128)
    out = imgadjust.stretch_contrast(img)
    assert np.all(out == 128), "全同一值的 channel 應原樣輸出,不除以 0"
    assert not np.any(np.isnan(out.astype(float)))


# ============================== equalize_histogram ==============================
# AC15
def test_equalize_histogram_shape_dtype_and_no_color_cast_on_gray():
    rng = np.random.default_rng(1)
    gray_vals = rng.integers(0, 256, size=(10, 10), dtype=np.uint8)
    img = np.stack([gray_vals, gray_vals, gray_vals], axis=-1)
    out = imgadjust.equalize_histogram(img)
    assert out.shape == img.shape
    assert out.dtype == np.uint8
    assert np.array_equal(out[:, :, 0], out[:, :, 1]) and np.array_equal(out[:, :, 1], out[:, :, 2]), \
        "灰階輸入均衡化後不應染色(三通道仍相等)"


# AC16
def test_equalize_histogram_without_cv2_returns_copy(monkeypatch):
    monkeypatch.setattr(imgadjust, "HAS_CV2", False)
    img = _solid(100)
    out = imgadjust.equalize_histogram(img)
    assert np.array_equal(out, img)
    assert out is not img, "應回複製品,不是同一物件參考"


# ============================== threshold ==============================
# AC17 + AC18
def test_threshold_binarizes():
    img = np.array([[[10, 10, 10], [200, 200, 200]]], dtype=np.uint8)
    out = imgadjust.threshold(img, 128)
    assert list(out[0, 0]) == [0, 0, 0]
    assert list(out[0, 1]) == [255, 255, 255]
    uniques = set(np.unique(out).tolist())
    assert uniques <= {0, 255}


# ============================== canny_edges ==============================
# AC19
def test_canny_edges_shape_and_channels_equal():
    rng = np.random.default_rng(2)
    img = rng.integers(0, 256, size=(20, 20, 3), dtype=np.uint8)
    out = imgadjust.canny_edges(img, 100, 200)
    assert out.shape == img.shape
    assert out.dtype == np.uint8
    assert np.array_equal(out[:, :, 0], out[:, :, 1]) and np.array_equal(out[:, :, 1], out[:, :, 2])


# AC20
def test_canny_edges_without_cv2_returns_copy(monkeypatch):
    monkeypatch.setattr(imgadjust, "HAS_CV2", False)
    img = _solid(100)
    out = imgadjust.canny_edges(img, 100, 200)
    assert np.array_equal(out, img)
    assert out is not img


# AC21
def test_canny_edges_flat_image_has_no_edges():
    img = _solid(128, h=20, w=20)
    out = imgadjust.canny_edges(img, 100, 200)
    assert np.all(out == 0)


# ============================== 通用:不 mutate + 型別/形狀不變性 ==============================
# AC22 + AC23
@pytest.mark.parametrize("fn,kwargs", [
    (imgadjust.brightness_contrast, {"brightness": 30.0, "contrast": 1.5}),
    (imgadjust.gamma, {"g": 1.8}),
    (imgadjust.invert, {}),
    (imgadjust.stretch_contrast, {}),
    (imgadjust.equalize_histogram, {}),
    (imgadjust.threshold, {"thresh": 100}),
    (imgadjust.canny_edges, {"low": 80, "high": 160}),
])
def test_no_mutate_and_shape_dtype_invariant(fn, kwargs):
    rng = np.random.default_rng(3)
    img = rng.integers(0, 256, size=(12, 12, 3), dtype=np.uint8)
    before = img.copy()
    out = fn(img, **kwargs)
    assert np.array_equal(img, before), f"{fn.__name__} 不應 mutate 輸入"
    assert out.dtype == np.uint8
    assert out.shape == img.shape
