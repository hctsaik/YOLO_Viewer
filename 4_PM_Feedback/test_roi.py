"""驗收測試:`roi` — ROI 框幾何(Tier A,純邏輯)。

來源契約:3_Architect_Design/04_roi.md(AC1–AC18 + §4 邊界表)。
角色:/pm 產物(回饋契約)。**只含測試,無實作。**

規則落實:
- 每條 AC 至少一個測試;AC 內子項(AC3/AC7/AC8/...)各自獨立測試。
- §4 邊界(負寬高 / float 截斷 / 部分超界 / 完全界外 / 零寬高 / 空交集 crop /
  點在邊界 / img 尺寸為 0)各自獨立測試。
- 每個測試以 # ACn 註記對應的 AC(邊界若對應某 AC 則標該 AC,純邊界補強標來源)。
- 另加「設計未明列」的推導 / property 測試(見檔尾 PROPERTY 區段),
  涵蓋:normalize 冪等、clamp 冪等、clamp 結果恆在界內、to/from_xyxy 雙向 round-trip、
  area 與 crop.size 一致、空框不變量、contains 隨機 oracle 等。

import 方式:`import roi`(conftest 已把 5_PG_Develop 加入 sys.path)。
此時實作尚未產出 → 預期紅;import 不到模組屬正常(實作未生),非「測試本身錯」。
"""
import numpy as np
import pytest

import roi  # conftest 已把 5_PG_Develop 加入 sys.path;實作未生時這裡會 ImportError(正常)


# =====================================================================
# normalize
# =====================================================================

def test_normalize_already_positive_keeps_values():
    # AC1:寬高已正,值不變
    assert roi.normalize(45, 105, 30, 150) == (45, 105, 30, 150)


def test_normalize_already_positive_returns_int_tuple():
    # AC1:回傳 tuple 四元素皆為 Python int 型別
    out = roi.normalize(45, 105, 30, 150)
    assert all(isinstance(v, int) for v in out)


def test_normalize_negative_width_and_height_moves_origin():
    # AC2:負寬 + 負高 → 轉正並移動左上角原點
    assert roi.normalize(10, 20, -4, -6) == (6, 14, 4, 6)


def test_normalize_single_axis_negative_width_float_trunc():
    # AC3:單軸負寬 + float 截斷向 0
    # 反向處理:x = int(0 + (-5.9)) = int(-5.9) = -5;w = int(5.9) = 5;h = int(5.9) = 5
    assert roi.normalize(0.0, 0.0, -5.9, 5.9) == (-5, 0, 5, 5)


def test_normalize_pure_float_truncation_toward_zero():
    # AC3:純截斷(無反向),向 0 截斷
    assert roi.normalize(2.9, 2.9, 5.9, 5.9) == (2, 2, 5, 5)


# =====================================================================
# area
# =====================================================================

def test_area_general():
    # AC4:一般面積 = w * h
    assert roi.area((45, 105, 30, 150)) == 4500


def test_area_zero_width_is_zero():
    # AC5:零寬框面積為 0
    assert roi.area((45, 105, 0, 150)) == 0


def test_area_zero_height_is_zero():
    # AC5:零高框面積為 0
    assert roi.area((45, 105, 30, 0)) == 0


# =====================================================================
# clamp_box
# =====================================================================

def test_clamp_box_bottom_right_overflow():
    # AC6:右下超界 → 夾到影像內
    assert roi.clamp_box((90, 90, 50, 50), 100, 100) == (90, 90, 10, 10)


def test_clamp_box_fully_outside_empty_intersection_width_zero():
    # AC7a:框完全在界外 → 空交集(w = 0)
    assert roi.clamp_box((200, 10, 30, 30), 100, 100) == (100, 10, 0, 30)


def test_clamp_box_fully_outside_area_is_zero():
    # AC7a:空交集面積為 0(邊界表「框完全在界外 → area==0」)
    assert roi.area(roi.clamp_box((200, 10, 30, 30), 100, 100)) == 0


def test_clamp_box_negative_topleft_clamped_to_zero():
    # AC7b:左上負座標被夾;同時驗證先 normalize
    assert roi.clamp_box((-10, -10, 50, 50), 100, 100) == (0, 0, 40, 40)


def test_clamp_box_negative_size_normalized_then_clamped():
    # AC7c:負寬高框先 normalize 再夾
    # normalize((50,50,-100,-100)) -> (-50,-50,100,100);夾後左上補到 0、右下保 50
    assert roi.clamp_box((50, 50, -100, -100), 100, 100) == (0, 0, 50, 50)


def test_clamp_box_zero_image_size_yields_empty():
    # §4 邊界:img_w / img_h = 0 → 合法,clamp 後 area == 0
    b = roi.clamp_box((0, 0, 30, 30), 0, 0)
    assert roi.area(b) == 0


# =====================================================================
# contains(半開區間)
# =====================================================================

def test_contains_interior_point_true():
    # AC8a:框內點為 True
    assert roi.contains((10, 10, 20, 20), 15, 15) is True


def test_contains_top_left_edge_included():
    # AC8b:含左 / 上界
    assert roi.contains((10, 10, 20, 20), 10, 10) is True


def test_contains_bottom_right_edge_excluded():
    # AC8c:排除右 / 下界(x+w, y+h 為 exclusive)
    assert roi.contains((10, 10, 20, 20), 30, 30) is False


def test_contains_just_inside_bottom_right():
    # AC8c:右下界內一格(29,29)仍命中
    assert roi.contains((10, 10, 20, 20), 29, 29) is True


def test_contains_outside_point_false():
    # AC8d:界外點為 False
    assert roi.contains((10, 10, 20, 20), 9, 15) is False


def test_contains_empty_box_never_hits():
    # AC8e:空框(w=h=0)永不命中
    assert roi.contains((10, 10, 0, 0), 10, 10) is False


# =====================================================================
# to_xyxy / from_xyxy
# =====================================================================

def test_to_xyxy_exclusive_bottom_right():
    # AC9:to_xyxy = (x, y, x+w, y+h),右下端點 exclusive
    assert roi.to_xyxy((45, 105, 30, 150)) == (45, 105, 75, 255)


def test_from_xyxy_normal_corners():
    # AC10:from_xyxy 正常兩角點 → box
    assert roi.from_xyxy(45, 105, 75, 255) == (45, 105, 30, 150)


def test_from_xyxy_reversed_corners_normalized():
    # AC11:from_xyxy 容許反向角點(走 normalize)
    assert roi.from_xyxy(75, 255, 45, 105) == (45, 105, 30, 150)


def test_to_from_xyxy_round_trip_identity():
    # AC12:round-trip 恆等 from_xyxy(*to_xyxy(b)) == b
    b = (45, 105, 30, 150)
    assert roi.from_xyxy(*roi.to_xyxy(b)) == b


# =====================================================================
# crop
# =====================================================================

def test_crop_grayscale_shape_and_content():
    # AC13:灰階一般裁切;shape 為 (h, w),內容對齊 array[y:y+h, x:x+w]
    a = np.arange(100, dtype=np.uint8).reshape(10, 10)
    out = roi.crop(a, (2, 3, 4, 5))
    assert out.shape == (5, 4)
    assert out[0, 0] == a[3, 2]            # == 32
    assert out[0, 0] == 32
    assert np.array_equal(out, a[3:8, 2:6])


def test_crop_multichannel_keeps_channel_axis():
    # AC14:多通道裁切保留通道軸 → (h, w, C)
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    assert roi.crop(a, (1, 1, 4, 6)).shape == (6, 4, 3)


def test_crop_empty_box_grayscale_zero_size():
    # AC15:空框 → 0 大小陣列(灰階)
    a = np.zeros((10, 10), dtype=np.uint8)
    out = roi.crop(a, (5, 5, 0, 0))
    assert out.shape == (0, 0)
    assert out.size == 0


def test_crop_empty_intersection_after_clamp_multichannel():
    # AC16:空交集 box 經 clamp 後 crop → 0 大小;多通道保留 C 軸
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = roi.clamp_box((200, 5, 4, 4), 10, 10)
    assert roi.area(b) == 0
    out = roi.crop(a, b)
    assert out.size == 0
    assert out.shape[2] == 3


def test_crop_does_not_mutate_input():
    # AC17:crop 不修改輸入陣列(純函式、無副作用)
    a = np.arange(100, dtype=np.uint8).reshape(10, 10)
    a0 = a.copy()
    roi.crop(a, (2, 3, 4, 5))
    assert np.array_equal(a, a0)


# =====================================================================
# 整合(管線串接)
# =====================================================================

def test_pipeline_from_xyxy_clamp_area_crop_consistent():
    # AC18:from_xyxy → clamp → area → crop 串接一致
    a = np.arange(100, dtype=np.uint8).reshape(10, 10)
    b = roi.clamp_box(roi.from_xyxy(8, 8, 14, 14), 10, 10)
    assert b == (8, 8, 2, 2)
    assert roi.area(b) == 4
    assert roi.crop(a, b).shape == (2, 2)


# =====================================================================
# PROPERTY / 推導測試(設計未明列;由契約不變量推導出來的性質)
#   來源:§2.1 不變量、§2.3 語義表、§2.4 算法。屬「加分」推導測試,
#   目的:抓出個別固定數值 AC 漏掉的一般性違反。
# =====================================================================

# 用一組涵蓋正/負/零/部分超界/完全界外的代表性框做表格驅動。
_BOXES = [
    (0, 0, 10, 10),
    (45, 105, 30, 150),
    (10, 20, -4, -6),        # 負寬高
    (50, 50, -100, -100),    # 負寬高且會超界
    (-10, -10, 50, 50),      # 左上負
    (90, 90, 50, 50),        # 右下超界
    (200, 10, 30, 30),       # 完全界外
    (5, 5, 0, 0),            # 空框
    (3, 7, 0, 9),            # 零寬
    (3, 7, 9, 0),            # 零高
]


@pytest.mark.parametrize("box", _BOXES)
def test_property_normalize_idempotent(box):
    # 推導(由 normalize 語義):normalize 一次後再 normalize 不應再變(冪等)。
    once = roi.normalize(*box)
    twice = roi.normalize(*once)
    assert once == twice


@pytest.mark.parametrize("box", _BOXES)
def test_property_normalize_nonneg_int_invariant(box):
    # 推導(§2.1 不變量):normalize 輸出 w>=0、h>=0,且四元素皆為 int。
    x, y, w, h = roi.normalize(*box)
    assert w >= 0 and h >= 0
    assert all(isinstance(v, int) for v in (x, y, w, h))


@pytest.mark.parametrize("box", _BOXES)
def test_property_clamp_result_within_image_bounds(box):
    # 推導(§2.3 clamp 語義):clamp 後框必落在 [0,img_w]x[0,img_h] 內,且 w,h>=0。
    img_w, img_h = 100, 100
    x, y, w, h = roi.clamp_box(box, img_w, img_h)
    assert 0 <= x <= img_w
    assert 0 <= y <= img_h
    assert w >= 0 and h >= 0
    assert x + w <= img_w
    assert y + h <= img_h


@pytest.mark.parametrize("box", _BOXES)
def test_property_clamp_idempotent(box):
    # 推導:已夾過的框再夾一次不應改變(clamp 冪等)。
    once = roi.clamp_box(box, 100, 100)
    twice = roi.clamp_box(once, 100, 100)
    assert once == twice


@pytest.mark.parametrize("box", _BOXES)
def test_property_to_from_xyxy_roundtrip_for_normalized(box):
    # 推導(AC12 的一般化):任意框先 normalize 成標準框後,from_xyxy(*to_xyxy(.)) 恆等。
    nb = roi.normalize(*box)
    assert roi.from_xyxy(*roi.to_xyxy(nb)) == nb


@pytest.mark.parametrize("box", _BOXES)
def test_property_area_matches_crop_size_after_clamp(box):
    # 推導(area 與 crop 語義一致):
    # 對灰階圖,clamp 後 area(b) 必等於 crop(a,b).size(空框兩者皆 0)。
    a = np.zeros((100, 100), dtype=np.uint8)
    b = roi.clamp_box(box, 100, 100)
    assert roi.area(b) == roi.crop(a, b).size


@pytest.mark.parametrize("box", _BOXES)
def test_property_crop_shape_equals_box_hw_after_clamp(box):
    # 推導(crop shape 必為 (h, w)):clamp 後 crop 的前兩軸 == (h, w)。
    a = np.zeros((100, 100), dtype=np.uint8)
    _, _, w, h = roi.clamp_box(box, 100, 100)
    out = roi.crop(a, roi.clamp_box(box, 100, 100))
    assert out.shape[:2] == (h, w)


def test_property_empty_box_area_zero_and_contains_false():
    # 推導(空框不變量):w 或 h 為 0 的框,area==0 且任何點都不命中。
    for box in [(5, 5, 0, 0), (5, 5, 10, 0), (5, 5, 0, 10)]:
        assert roi.area(box) == 0
        # 用框左上角當查詢點:非空框會命中、空框必不命中
        assert roi.contains(box, 5, 5) is False


def test_property_contains_matches_halfopen_oracle_random():
    # 推導(contains 半開語義的一般化):在小網格上以獨立 oracle 對拍,
    # 任一點 (px,py) 的 contains 必等於 (x<=px<x+w and y<=py<y+h)。
    rng = np.random.default_rng(20260621)
    for _ in range(40):
        x = int(rng.integers(0, 20))
        y = int(rng.integers(0, 20))
        w = int(rng.integers(0, 8))
        h = int(rng.integers(0, 8))
        box = (x, y, w, h)
        for _ in range(15):
            px = int(rng.integers(-2, 30))
            py = int(rng.integers(-2, 30))
            expected = (x <= px < x + w) and (y <= py < y + h)
            assert roi.contains(box, px, py) is expected


def test_property_from_xyxy_symmetric_in_corner_order():
    # 推導(from_xyxy 走 normalize → 對角點順序對稱):
    # 交換兩角點(或單軸交換)應得到同一個標準框。
    base = roi.from_xyxy(45, 105, 75, 255)
    assert roi.from_xyxy(75, 255, 45, 105) == base   # 兩軸皆反
    assert roi.from_xyxy(75, 105, 45, 255) == base   # 只反 x
    assert roi.from_xyxy(45, 255, 75, 105) == base   # 只反 y
