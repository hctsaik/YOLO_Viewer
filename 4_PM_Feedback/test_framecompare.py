"""framecompare 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/09_framecompare.md(AC1..AC27 + §2/§3/§4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import framecompare`。此時實作尚未生成,import 不到屬正常(非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

純邏輯 Tier A 模組:五種兩張同形 RGB uint8 影像比較運算
(side_by_side / difference / blend / swipe / blink_sequence)。
測試以設計 §5 的合成小陣列(2x2 / 2x3 / 2x4 / 1x1)釘死 shape + 具體像素值,
以 np.array_equal(...) / pytest.raises(ValueError) 斷言。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_framecompare.py -p no:cacheprovider --strict-markers -q
"""
import numpy as np
import pytest

import framecompare


# =====================================================================
# 共用合成陣列(設計 §5 釘死)
# =====================================================================

def _A10():
    # 2x2x3 純色:全 10
    return np.full((2, 2, 3), 10, dtype=np.uint8)


def _B20():
    # 2x2x3 純色:全 20
    return np.full((2, 2, 3), 20, dtype=np.uint8)


# =====================================================================
# dtype / 形狀基本契約
# =====================================================================

def test_ac1_difference_dtype_and_shape():
    # AC1:difference 回 uint8、shape 不變 (2,2,3)
    out = framecompare.difference(_A10(), _B20())
    assert out.dtype == np.uint8
    assert out.shape == (2, 2, 3)


def test_ac2_blend_dtype_and_shape():
    # AC2:blend 回 uint8、shape 不變 (2,2,3)
    out = framecompare.blend(_A10(), _B20(), 0.5)
    assert out.dtype == np.uint8
    assert out.shape == (2, 2, 3)


# =====================================================================
# side_by_side — 寬度 / 內容 / gap / 錯誤
# =====================================================================

def test_ac3_side_by_side_different_widths_shape():
    # AC3:寬不同合法,輸出寬 = 3 + 0 + 4 = 7
    A = np.zeros((2, 3, 3), np.uint8)
    B = np.zeros((2, 4, 3), np.uint8)
    assert framecompare.side_by_side(A, B).shape == (2, 7, 3)


def test_ac4_side_by_side_gap0_content():
    # AC4:gap=0,輸出寬 4;左半全 10(A)、右半全 20(B),逐元素
    out = framecompare.side_by_side(_A10(), _B20(), gap=0)
    assert out.shape == (2, 4, 3)
    assert np.array_equal(out[:, 0:2], np.full((2, 2, 3), 10, np.uint8))
    assert np.array_equal(out[:, 2:4], np.full((2, 2, 3), 20, np.uint8))


def test_ac5_side_by_side_gap_fill_color():
    # AC5:gap=3 + gap_color=(5,6,7),輸出寬 7;左 A 右 B,中間 gap 欄逐像素 == [5,6,7]
    out = framecompare.side_by_side(_A10(), _B20(), gap=3, gap_color=(5, 6, 7))
    assert out.shape == (2, 7, 3)
    assert np.array_equal(out[:, 0:2], np.full((2, 2, 3), 10, np.uint8))
    assert np.array_equal(out[:, 5:7], np.full((2, 2, 3), 20, np.uint8))
    assert np.array_equal(
        out[:, 2:5], np.broadcast_to(np.array([5, 6, 7], np.uint8), (2, 3, 3)))


def test_ac6_side_by_side_height_mismatch_raises():
    # AC6:高度不等 → ValueError
    with pytest.raises(ValueError):
        framecompare.side_by_side(
            np.zeros((2, 2, 3), np.uint8), np.zeros((3, 2, 3), np.uint8))


def test_ac7_side_by_side_negative_gap_raises():
    # AC7:gap < 0 → ValueError
    with pytest.raises(ValueError):
        framecompare.side_by_side(_A10(), _B20(), gap=-1)


# =====================================================================
# difference — 絕對差 / metamorphic 對稱 / 自差為 0 / 溢位
# =====================================================================

def test_ac8_difference_absolute_value():
    # AC8:|10-20| == 10,逐元素
    assert np.array_equal(
        framecompare.difference(_A10(), _B20()), np.full((2, 2, 3), 10, np.uint8))


def test_ac9_difference_self_is_zero():
    # AC9:自差全 0(metamorphic 釘死)
    assert np.array_equal(
        framecompare.difference(_A10(), _A10()), np.zeros((2, 2, 3), np.uint8))


def test_ac10_difference_symmetric():
    # AC10:對稱 |A-B| == |B-A|(metamorphic 釘死)
    assert np.array_equal(
        framecompare.difference(_A10(), _B20()),
        framecompare.difference(_B20(), _A10()))


def test_ac11_difference_overflow_safe():
    # AC11:溢位安全 — |0-255| == 255(非 uint8 wrap 後的 1)
    P = np.full((1, 1, 3), 0, np.uint8)
    Q = np.full((1, 1, 3), 255, np.uint8)
    assert framecompare.difference(P, Q)[0, 0, 0] == 255


def test_ac12_difference_shape_mismatch_raises():
    # AC12:形狀不符 → ValueError
    with pytest.raises(ValueError):
        framecompare.difference(
            np.zeros((2, 2, 3), np.uint8), np.zeros((2, 3, 3), np.uint8))


# =====================================================================
# blend — 端點 / 0.5 平均 / round-half-up / 錯誤
# =====================================================================

def test_ac13_blend_alpha0_equals_A():
    # AC13:alpha=0 → 逐元素等於 A
    assert np.array_equal(framecompare.blend(_A10(), _B20(), 0.0), _A10())


def test_ac14_blend_alpha1_equals_B():
    # AC14:alpha=1 → 逐元素等於 B
    assert np.array_equal(framecompare.blend(_A10(), _B20(), 1.0), _B20())


def test_ac15_blend_half_is_mean():
    # AC15:alpha=0.5 → (10+20)/2 = 15,釘死具體像素值
    out = framecompare.blend(_A10(), _B20(), 0.5)
    assert out[0, 0, 0] == 15
    assert np.array_equal(out, np.full((2, 2, 3), 15, np.uint8))


def test_ac16_blend_round_half_up():
    # AC16:round-half-away-from-zero — 100.5 進位為 101(非 round-half-to-even 的 100)
    C = np.full((1, 1, 3), 100, np.uint8)
    D = np.full((1, 1, 3), 101, np.uint8)
    assert framecompare.blend(C, D, 0.5)[0, 0, 0] == 101


def test_ac17_blend_alpha_out_of_range_raises():
    # AC17:alpha 超界 → ValueError(上下界各驗)
    with pytest.raises(ValueError):
        framecompare.blend(_A10(), _B20(), 1.5)
    with pytest.raises(ValueError):
        framecompare.blend(_A10(), _B20(), -0.1)


def test_ac18_blend_shape_mismatch_raises():
    # AC18:形狀不符 → ValueError
    with pytest.raises(ValueError):
        framecompare.blend(
            np.zeros((2, 2, 3), np.uint8), np.zeros((1, 2, 3), np.uint8), 0.5)


# =====================================================================
# swipe — 欄邊界精確 / x=0 / x=W / 中間 / 不 mutate / 錯誤
# =====================================================================

def _A10_4():
    # 2x4x3 純色:全 10
    return np.full((2, 4, 3), 10, np.uint8)


def _B20_4():
    # 2x4x3 純色:全 20
    return np.full((2, 4, 3), 20, np.uint8)


def test_ac19_swipe_x0_all_B():
    # AC19:x=0 → 全 B
    assert np.array_equal(framecompare.swipe(_A10_4(), _B20_4(), 0), _B20_4())


def test_ac20_swipe_xW_all_A():
    # AC20:x=W=4 → 全 A
    assert np.array_equal(framecompare.swipe(_A10_4(), _B20_4(), 4), _A10_4())


def test_ac21_swipe_mid_column_boundary():
    # AC21:x=1 → 欄 0 取 A(全 10)、欄 1..3 取 B(全 20);欄 index < x 取 A
    out = framecompare.swipe(_A10_4(), _B20_4(), 1)
    assert np.array_equal(out[:, 0:1], np.full((2, 1, 3), 10, np.uint8))
    assert np.array_equal(out[:, 1:4], np.full((2, 3, 3), 20, np.uint8))


def test_ac22_swipe_does_not_mutate_inputs():
    # AC22:不 mutate — 呼叫後 A 仍全 10、B 仍全 20
    A = _A10_4()
    B = _B20_4()
    framecompare.swipe(A, B, 2)
    assert np.array_equal(A, np.full((2, 4, 3), 10, np.uint8))
    assert np.array_equal(B, np.full((2, 4, 3), 20, np.uint8))


def test_ac23_swipe_x_out_of_range_raises():
    # AC23:x 超界 → ValueError(x<0 與 x>W 各驗,W=4 故 5>W)
    with pytest.raises(ValueError):
        framecompare.swipe(_A10_4(), _B20_4(), -1)
    with pytest.raises(ValueError):
        framecompare.swipe(_A10_4(), _B20_4(), 5)


def test_ac24_swipe_shape_mismatch_raises():
    # AC24:形狀不符 → ValueError
    with pytest.raises(ValueError):
        framecompare.swipe(
            np.zeros((2, 2, 3), np.uint8), np.zeros((2, 3, 3), np.uint8), 1)


# =====================================================================
# blink_sequence — 內容 / 順序 / 參照 / 錯誤
# =====================================================================

def test_ac25_blink_sequence_content_and_order():
    # AC25:回 [A, B],長度 2,順序釘死
    A = _A10()
    B = _B20()
    seq = framecompare.blink_sequence(A, B)
    assert len(seq) == 2
    assert np.array_equal(seq[0], A)
    assert np.array_equal(seq[1], B)


def test_ac26_blink_sequence_returns_same_references():
    # AC26:回傳原物件參照,不複製
    A = _A10()
    B = _B20()
    seq = framecompare.blink_sequence(A, B)
    assert seq[0] is A
    assert seq[1] is B


def test_ac27_blink_sequence_shape_mismatch_raises():
    # AC27:形狀不符 → ValueError
    with pytest.raises(ValueError):
        framecompare.blink_sequence(
            np.zeros((2, 2, 3), np.uint8), np.zeros((3, 2, 3), np.uint8))


# =====================================================================
# 推導 / property 測試(設計未明列;由 §2/§3/§4 契約推導)
# =====================================================================

def test_property_difference_self_is_zero_arbitrary(np_seed=None):
    # 推導(§3.2 metamorphic):對任意 uint8 RGB 影像,difference(X, X) 恆全 0,
    # 比 AC9 的單一純色更強的不變式。
    rng = np.random.default_rng(0)
    X = rng.integers(0, 256, size=(3, 5, 3), dtype=np.uint8)
    assert np.array_equal(framecompare.difference(X, X), np.zeros((3, 5, 3), np.uint8))


def test_property_difference_symmetric_arbitrary():
    # 推導(§3.2 metamorphic):對任意同形 X、Y,|X-Y| == |Y-X| 逐元素恆等,
    # 比 AC10 的純色對更強。
    rng = np.random.default_rng(1)
    X = rng.integers(0, 256, size=(3, 5, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(3, 5, 3), dtype=np.uint8)
    assert np.array_equal(
        framecompare.difference(X, Y), framecompare.difference(Y, X))


def test_property_difference_never_wraps_full_range():
    # 推導(§2.2 + §4e 溢位):涵蓋 0..255 全程任意配對,差值恆等於 Python int 絕對差,
    # 證明全程無 uint8 wrap(AC11 只驗 0 vs 255 單點)。
    a = np.arange(256, dtype=np.uint8).reshape(1, 256, 1)
    a = np.repeat(a, 3, axis=2)            # (1,256,3)
    b = a[:, ::-1, :].copy()              # 反序配對,涵蓋多種 |a-b|
    out = framecompare.difference(a, b)
    expected = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8)
    assert np.array_equal(out, expected)
    assert out.max() <= 255 and out.min() >= 0


def test_property_blend_endpoints_exact_arbitrary():
    # 推導(§3.3 端點):對任意 X、Y,blend(X,Y,0)==X 且 blend(X,Y,1)==Y 逐元素精確,
    # 比 AC13/AC14 的純色對更強(浮點 1.0*x 對整數精確還原)。
    rng = np.random.default_rng(2)
    X = rng.integers(0, 256, size=(4, 4, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(4, 4, 3), dtype=np.uint8)
    assert np.array_equal(framecompare.blend(X, Y, 0.0), X)
    assert np.array_equal(framecompare.blend(X, Y, 1.0), Y)


def test_property_blend_symmetric_at_half():
    # 推導(§3.3):alpha=0.5 時 blend(X,Y) 與 blend(Y,X) 對「偶數和」逐元素相等;
    # 此處用偶數差純色(10,20→15)確保無 .5 歧義,驗對稱性不依賴順序。
    assert np.array_equal(
        framecompare.blend(_A10(), _B20(), 0.5),
        framecompare.blend(_B20(), _A10(), 0.5))


def test_property_blend_stays_in_uint8_range():
    # 推導(§2.2 凸組合):任意 alpha∈[0,1] 下 blend 結果恆在 0..255、dtype uint8,
    # 無需 clip(凸組合天然不越界)。
    rng = np.random.default_rng(3)
    X = rng.integers(0, 256, size=(4, 4, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(4, 4, 3), dtype=np.uint8)
    for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = framecompare.blend(X, Y, alpha)
        assert out.dtype == np.uint8
        assert out.min() >= 0 and out.max() <= 255


def test_property_swipe_x0_and_xW_partition_endpoints():
    # 推導(§3.4):對任意同形 X、Y,swipe(X,Y,0)==Y(全右)、swipe(X,Y,W)==X(全左),
    # 比 AC19/AC20 純色更強;同時驗端點互補。
    rng = np.random.default_rng(4)
    X = rng.integers(0, 256, size=(3, 6, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(3, 6, 3), dtype=np.uint8)
    W = X.shape[1]
    assert np.array_equal(framecompare.swipe(X, Y, 0), Y)
    assert np.array_equal(framecompare.swipe(X, Y, W), X)


def test_property_swipe_column_partition_arbitrary():
    # 推導(§3.4 不變式):對任意 x∈[0,W],swipe 結果欄 <x 取自 X、欄 >=x 取自 Y,
    # 逐欄驗證(AC21 只驗 x=1 單點)。
    rng = np.random.default_rng(5)
    X = rng.integers(0, 256, size=(2, 5, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(2, 5, 3), dtype=np.uint8)
    W = X.shape[1]
    for x in range(W + 1):
        out = framecompare.swipe(X, Y, x)
        assert np.array_equal(out[:, 0:x], X[:, 0:x])
        assert np.array_equal(out[:, x:W], Y[:, x:W])


def test_property_side_by_side_width_is_sum_with_gap():
    # 推導(§3.1):輸出寬恆為 wA + gap + wB,對多組 (wA, wB, gap) 釘死。
    for wa, wb, gap in [(3, 4, 0), (2, 2, 1), (1, 5, 3), (4, 1, 2)]:
        A = np.zeros((2, wa, 3), np.uint8)
        B = np.zeros((2, wb, 3), np.uint8)
        out = framecompare.side_by_side(A, B, gap=gap)
        assert out.shape == (2, wa + gap + wb, 3)


def test_property_side_by_side_does_not_mutate_inputs():
    # 推導(§4f 不 mutate):side_by_side 配置新陣列,呼叫後 A、B 內容不變。
    A = _A10()
    B = _B20()
    framecompare.side_by_side(A, B, gap=2, gap_color=(1, 2, 3))
    assert np.array_equal(A, np.full((2, 2, 3), 10, np.uint8))
    assert np.array_equal(B, np.full((2, 2, 3), 20, np.uint8))


def test_property_blend_does_not_mutate_inputs():
    # 推導(§4f 不 mutate):blend 配置新陣列,呼叫後 A、B 內容不變。
    A = _A10()
    B = _B20()
    framecompare.blend(A, B, 0.5)
    assert np.array_equal(A, np.full((2, 2, 3), 10, np.uint8))
    assert np.array_equal(B, np.full((2, 2, 3), 20, np.uint8))


def test_property_difference_does_not_mutate_inputs():
    # 推導(§4f 不 mutate):difference 配置新陣列,呼叫後 A、B 內容不變。
    A = _A10()
    B = _B20()
    framecompare.difference(A, B)
    assert np.array_equal(A, np.full((2, 2, 3), 10, np.uint8))
    assert np.array_equal(B, np.full((2, 2, 3), 20, np.uint8))
