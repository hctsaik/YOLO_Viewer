"""驗收測試:viewport(Tier A,純幾何,零 I/O)。

由 /pm 依 3_Architect_Design/01_viewport.md 第 6 節 AC + 第 5 節邊界落成。
- 只寫測試,不含任何實作(實作在 5_PG_Develop/viewport.py 由 /pg 生成)。
- 此時實作尚未存在,測試預期會「紅」;import error 不算紅(基礎設施/契約問題)。
- 每個測試以 # ACn 標出可追溯性;邊界各自獨立測試。
- 結尾另含「設計未明列」的推導 / property / metamorphic 測試(# DERIVED)。

import 方式:`import viewport`(conftest 已把 5_PG_Develop 加進 sys.path)。
"""
import pytest

import viewport


# ============================================================
# fit_zoom
# ============================================================

def test_fit_zoom_width_limited():
    # AC1:整張圖 fit,受限於寬(800/1000)
    assert viewport.fit_zoom(1000, 500, 800, 800) == pytest.approx(0.8)


def test_fit_zoom_height_limited():
    # AC2:整張圖 fit,受限於高(800/1000)
    assert viewport.fit_zoom(500, 1000, 800, 800) == pytest.approx(0.8)


def test_fit_zoom_small_image_upscale():
    # AC3:小圖放大填滿(300/100)
    assert viewport.fit_zoom(100, 100, 300, 300) == pytest.approx(3.0)


def test_fit_zoom_width_dominant():
    # AC4:寬主導(1000/2000)
    assert viewport.fit_zoom(2000, 1000, 1000, 1000) == pytest.approx(0.5)


# ============================================================
# clamp
# ============================================================

def test_clamp_int_values():
    # AC5:int 夾值(中段 / 低於下界 / 高於上界)
    assert viewport.clamp(5, 0, 10) == 5
    assert viewport.clamp(-3, 0, 10) == 0
    assert viewport.clamp(99, 0, 10) == 10


def test_clamp_type_preservation():
    # AC6:型別保真(float 進 float 出、int 進 int 出)
    r = viewport.clamp(2.5, 0.0, 1.0)
    assert r == pytest.approx(1.0)
    assert isinstance(r, float)
    assert isinstance(viewport.clamp(5, 0, 10), int)


# ============================================================
# crop_rect — 基本與置中
# ============================================================

def test_crop_rect_full_image_when_zoom_one():
    # AC7:整圖可見(zoom=1、disp>=src)
    assert viewport.crop_rect(1000, 800, 1.0, 500, 400, 1000, 800) == (0, 0, 1000, 800)


def test_crop_rect_centered_zoom_in():
    # AC8:置中放大 zoom=2、disp=400x400 -> view=200x200、中心 (500,400)
    assert viewport.crop_rect(1000, 800, 2.0, 500, 400, 400, 400) == (400, 300, 200, 200)


# ============================================================
# crop_rect — display<->source 往返閉環
# ============================================================

def test_roundtrip_corners_and_center():
    # AC9:往返一致(左上對左上、右下對 x0+w/y0+h、畫布中心對來源中心)
    rect = viewport.crop_rect(1000, 800, 2.0, 500, 400, 400, 400)
    assert rect == (400, 300, 200, 200)  # 前提 = AC8
    assert viewport.display_to_source(0, 0, rect, 400, 400) == pytest.approx((400.0, 300.0))
    assert viewport.display_to_source(400, 400, rect, 400, 400) == pytest.approx((600.0, 500.0))
    assert viewport.display_to_source(200, 200, rect, 400, 400) == pytest.approx((500.0, 400.0))


# ============================================================
# crop_rect — 中心超界平移夾回(不報錯、保寬高)
# ============================================================

def test_crop_rect_center_top_left_out_of_bounds():
    # AC10:中心 (0,0) 左上越界 -> 平移夾回、保 200x200
    assert viewport.crop_rect(1000, 800, 2.0, 0, 0, 400, 400) == (0, 0, 200, 200)


def test_crop_rect_center_bottom_right_out_of_bounds():
    # AC11:中心 (1000,800) 右下越界 -> x0=1000-200, y0=800-200
    assert viewport.crop_rect(1000, 800, 2.0, 1000, 800, 400, 400) == (800, 600, 200, 200)


@pytest.mark.parametrize("cx", [-500, 0, 250, 500, 1500])
@pytest.mark.parametrize("cy", [-200, 0, 400, 2000])
def test_crop_rect_invariant_always_inside_image(cx, cy):
    # AC12:不變式 — 任意中心,矩形恆落在影像內且 w,h>=1
    x0, y0, w, h = viewport.crop_rect(1000, 800, 2.0, cx, cy, 400, 400)
    assert x0 >= 0
    assert y0 >= 0
    assert x0 + w <= 1000
    assert y0 + h <= 800
    assert w >= 1
    assert h >= 1


# ============================================================
# crop_rect — zoom 太小時整圖且不溢出
# ============================================================

def test_crop_rect_zoom_too_small_clamps_to_full_image():
    # AC13:zoom=0.5(view=800x800 > src 寬 400)-> clamp 為整圖
    assert viewport.crop_rect(400, 600, 0.5, 200, 300, 400, 400) == (0, 0, 400, 600)


# ============================================================
# crop_rect — 邊界錯誤
# ============================================================

def test_crop_rect_zoom_zero_raises():
    # AC14:zoom=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.crop_rect(1000, 800, 0, 500, 400, 400, 400)


def test_crop_rect_zoom_negative_raises():
    # AC14:zoom<0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.crop_rect(1000, 800, -1.0, 500, 400, 400, 400)


def test_crop_rect_disp_w_zero_raises():
    # AC15:disp_w=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.crop_rect(1000, 800, 2.0, 500, 400, 0, 400)


def test_crop_rect_src_w_zero_raises():
    # AC15:src_w=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.crop_rect(0, 800, 2.0, 500, 400, 400, 400)


# ============================================================
# fit_zoom / minimap_rect — 邊界錯誤
# ============================================================

def test_fit_zoom_src_w_zero_raises():
    # AC16:src_w=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.fit_zoom(0, 800, 400, 400)


def test_fit_zoom_disp_w_zero_raises():
    # AC16:disp_w=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.fit_zoom(1000, 800, 0, 400)


def test_minimap_rect_src_w_zero_raises():
    # AC17:src_w=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.minimap_rect(0, 800, (0, 0, 10, 10))


def test_minimap_rect_src_h_zero_raises():
    # AC17:src_h=0 拋 ValueError
    with pytest.raises(ValueError):
        viewport.minimap_rect(1000, 0, (0, 0, 10, 10))


# ============================================================
# display_to_source — 線性映射與邊界錯誤
# ============================================================

def test_display_to_source_linear_interpolation():
    # AC18:線性內插 sx=400+100/400*200=450、sy=300+50/400*200=325
    rect = (400, 300, 200, 200)
    assert viewport.display_to_source(100, 50, rect, 400, 400) == pytest.approx((450.0, 325.0))


def test_display_to_source_disp_w_zero_raises():
    # AC19:disp_w=0 拋 ValueError(避免除零)
    with pytest.raises(ValueError):
        viewport.display_to_source(10, 10, (0, 0, 100, 100), 0, 100)


# ============================================================
# minimap_rect — 相對比例 ∈ [0,1]
# ============================================================

def test_minimap_rect_ratios():
    # AC20:rx=400/1000, ry=300/800, rw=200/1000, rh=200/800
    assert viewport.minimap_rect(1000, 800, (400, 300, 200, 200)) == pytest.approx(
        (0.4, 0.375, 0.2, 0.25))


def test_minimap_rect_full_image_full_ratio():
    # AC21:整圖矩形 -> 全幅比例 (0,0,1,1)
    assert viewport.minimap_rect(1000, 800, (0, 0, 1000, 800)) == pytest.approx(
        (0.0, 0.0, 1.0, 1.0))


def test_minimap_rect_ratios_within_unit_interval():
    # AC22:不變式 — 比例皆在 [0,1] 且視窗不超出縮圖
    rx, ry, rw, rh = viewport.minimap_rect(1000, 800, (400, 300, 200, 200))
    assert 0.0 <= rx <= 1.0
    assert 0.0 <= ry <= 1.0
    assert 0.0 <= rw <= 1.0
    assert 0.0 <= rh <= 1.0
    assert rx + rw <= 1.0
    assert ry + rh <= 1.0


# ============================================================
# 整合不變式(跨函式,坐實 virtual viewport)
# ============================================================

def test_crop_then_minimap_consistent():
    # AC23:crop 的輸出餵給 minimap 自洽(= AC20)
    rect = viewport.crop_rect(1000, 800, 2.0, 500, 400, 400, 400)
    assert viewport.minimap_rect(1000, 800, rect) == pytest.approx((0.4, 0.375, 0.2, 0.25))


def test_fit_then_crop_sees_full_image():
    # AC24:以 fit zoom(=0.4)裁切恰好涵蓋整張圖、不溢出
    z = viewport.fit_zoom(1000, 800, 400, 400)
    assert z == pytest.approx(0.4)
    assert viewport.crop_rect(1000, 800, z, 500, 400, 400, 400) == (0, 0, 1000, 800)


# ============================================================
# DERIVED — 設計未明列的推導 / property / metamorphic 測試
# 同源不防概念盲點,但能對實作施壓逼出 bug。
# ============================================================

def test_derived_clamp_identity_within_range():
    # DERIVED:v 已落在 [lo,hi] 內 -> 原值返回(clamp 的恆等性質)
    assert viewport.clamp(3, 0, 10) == 3
    assert viewport.clamp(0, 0, 10) == 0      # 下界端點
    assert viewport.clamp(10, 0, 10) == 10    # 上界端點
    assert viewport.clamp(0.5, 0.0, 1.0) == pytest.approx(0.5)


@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0, 4.0])
def test_derived_crop_rect_translation_invariant_size(zoom):
    # DERIVED(metamorphic):平移中心不改變可視寬高 w,h(只在放大且未撞邊時成立)。
    # 取兩個都不撞邊的中心點,w,h 應一致 = round(disp/zoom) clamp 後的值。
    src_w, src_h, disp_w, disp_h = 1000, 800, 400, 400
    _, _, w1, h1 = viewport.crop_rect(src_w, src_h, zoom, 500, 400, disp_w, disp_h)
    _, _, w2, h2 = viewport.crop_rect(src_w, src_h, zoom, 480, 420, disp_w, disp_h)
    assert (w1, h1) == (w2, h2)


def test_derived_crop_rect_higher_zoom_smaller_or_equal_view():
    # DERIVED(單調性):zoom 越大 -> 可視來源矩形寬高越小(或相等,撞 clamp 時)。
    src_w, src_h, disp_w, disp_h = 1000, 800, 400, 400
    cx, cy = 500, 400
    _, _, w_lo, h_lo = viewport.crop_rect(src_w, src_h, 1.0, cx, cy, disp_w, disp_h)
    _, _, w_hi, h_hi = viewport.crop_rect(src_w, src_h, 2.0, cx, cy, disp_w, disp_h)
    assert w_hi <= w_lo
    assert h_hi <= h_lo
    assert (w_hi, h_hi) != (w_lo, h_lo)  # 此設定下確實縮小,非全程 clamp


def test_derived_display_to_source_at_rect_origin_returns_top_left():
    # DERIVED:display (0,0) 永遠映回 rect 左上角 (x0,y0)(與 zoom/中心無關)。
    rect = viewport.crop_rect(1000, 800, 3.0, 123, 456, 400, 400)
    x0, y0, _, _ = rect
    assert viewport.display_to_source(0, 0, rect, 400, 400) == pytest.approx((float(x0), float(y0)))


def test_derived_display_to_source_full_extent_returns_bottom_right():
    # DERIVED:display (disp_w,disp_h) 永遠映回 rect 右下角 (x0+w, y0+h)。
    rect = viewport.crop_rect(1000, 800, 3.0, 123, 456, 400, 400)
    x0, y0, w, h = rect
    assert viewport.display_to_source(400, 400, rect, 400, 400) == pytest.approx(
        (float(x0 + w), float(y0 + h)))


def test_derived_display_to_source_monotonic_in_dx():
    # DERIVED(單調性):dx 增加 -> sx 不減(線性映射的單調保證)。
    rect = (400, 300, 200, 200)
    sx_a, _ = viewport.display_to_source(50, 0, rect, 400, 400)
    sx_b, _ = viewport.display_to_source(150, 0, rect, 400, 400)
    sx_c, _ = viewport.display_to_source(300, 0, rect, 400, 400)
    assert sx_a < sx_b < sx_c


def test_derived_minimap_rect_ratio_matches_crop_fraction():
    # DERIVED(跨函式一致):minimap 的 rw/rh 恰等於 crop rect 寬高佔影像的比例。
    src_w, src_h = 1000, 800
    rect = viewport.crop_rect(src_w, src_h, 2.0, 500, 400, 400, 400)
    x0, y0, w, h = rect
    rx, ry, rw, rh = viewport.minimap_rect(src_w, src_h, rect)
    assert rx == pytest.approx(x0 / src_w)
    assert ry == pytest.approx(y0 / src_h)
    assert rw == pytest.approx(w / src_w)
    assert rh == pytest.approx(h / src_h)


def test_derived_fit_zoom_symmetry_under_axis_swap():
    # DERIVED(對稱性):同時交換 (src_w<->src_h) 與 (disp_w<->disp_h),fit_zoom 不變
    # (min(disp_w/src_w, disp_h/src_h) 對「軸對調」對稱)。
    a = viewport.fit_zoom(1000, 500, 800, 600)
    b = viewport.fit_zoom(500, 1000, 600, 800)
    assert a == pytest.approx(b)


def test_derived_no_forbidden_imports_in_implementation():
    # DERIVED(反向稽查):viewport 刻意零依賴,實作不得 import numpy/PIL/cv2。
    # 設計第 2 節釘死:純 Python 算術,維持秒級單元測試。
    forbidden = ("numpy", "PIL", "cv2", "tifffile")
    mod_file = getattr(viewport, "__file__", None)
    assert mod_file is not None
    with open(mod_file, "r", encoding="utf-8") as f:
        src = f.read()
    for name in forbidden:
        assert ("import " + name) not in src, name + " 不應被 viewport import(設計第 2 節)"
        assert ("from " + name) not in src, name + " 不應被 viewport import(設計第 2 節)"
