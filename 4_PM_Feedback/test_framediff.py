"""framediff 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/12_framediff.md(AC1..AC35 + §2/§3/§4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import framediff`。此時實作尚未生成,import 不到屬正常(非紅,test-first);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

純邏輯 Tier A 模組:兩張同形 RGB uint8 影像 A、B 的進階變化分析
(change_mask / change_ratio / change_regions / highlight)。
測試以設計 §5 的合成小陣列(2x2 / 1x1 / 1x4 / 4x5)釘死 shape + 具體
像素值 / 遮罩 / bbox 清單,以 np.array_equal(...) / pytest.raises(ValueError) 斷言。
灰階加權對純灰(R=G=B=v)像素:0.299v+0.587v+0.114v = v(係數和 == 1.0),
故純色像素灰階 == 該值,差 == 兩值之差(下列 AC 多用純灰陣列以便心算)。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_framediff.py -p no:cacheprovider --strict-markers -q
"""
import numpy as np
import pytest

import framediff


# =====================================================================
# 共用合成陣列(設計 §5 釘死)
# =====================================================================

def _A10():
    # 2x2x3 純色:全 10(灰階 10)
    return np.full((2, 2, 3), 10, dtype=np.uint8)


def _B200():
    # 2x2x3 純色:全 200(灰階 200;與 A10 灰階差 = 190 > 30 → 全變化)
    return np.full((2, 2, 3), 200, dtype=np.uint8)


def _regions_AB():
    # 設計 §5 / AC16 構造:4x5,B 在 (0,0)(0,1)(1,0)(0,4)(1,4)(2,2)(3,2)(3,3)
    # 設純灰 200,其餘 0,threshold=30 →
    #   row0: 1 1 0 0 1
    #   row1: 1 0 0 0 1
    #   row2: 0 0 1 0 0
    #   row3: 0 0 1 1 0
    # 4-連通三元件:①{(0,0),(0,1),(1,0)} ②{(0,4),(1,4)} ③{(2,2),(3,2),(3,3)}
    A = np.zeros((4, 5, 3), np.uint8)
    B = np.zeros((4, 5, 3), np.uint8)
    for (y, x) in [(0, 0), (0, 1), (1, 0), (0, 4), (1, 4), (2, 2), (3, 2), (3, 3)]:
        B[y, x] = (200, 200, 200)
    return A, B


def _ratio_AB():
    # AC14 構造:1x4,前 2 欄純灰 200、後 2 欄 0 → 2/4 變化
    A = np.zeros((1, 4, 3), np.uint8)
    B = np.zeros((1, 4, 3), np.uint8)
    B[0, 0] = (200, 200, 200)
    B[0, 1] = (200, 200, 200)
    return A, B


# =====================================================================
# dtype / 形狀基本契約 (AC1..AC4)
# =====================================================================

def test_ac1_change_mask_dtype_and_shape():
    # AC1:change_mask 回 uint8、shape (2,2)(二維、無通道軸)
    out = framediff.change_mask(_A10(), _B200())
    assert out.dtype == np.uint8
    assert out.shape == (2, 2)


def test_ac2_change_mask_values_subset_of_01():
    # AC2:值集合 ⊆ {0,1}
    out = framediff.change_mask(_A10(), _B200())
    assert set(np.unique(out).tolist()).issubset({0, 1})


def test_ac3_change_ratio_returns_builtin_float():
    # AC3:change_ratio 回內建 float(非 np.float64)
    r = framediff.change_ratio(_A10(), _B200())
    assert isinstance(r, float)
    assert not isinstance(r, np.floating)


def test_ac4_highlight_dtype_and_shape():
    # AC4:highlight 回 uint8、shape (2,2,3)
    out = framediff.highlight(_A10(), _B200())
    assert out.dtype == np.uint8
    assert out.shape == (2, 2, 3)


# =====================================================================
# change_mask — 門檻語義 / 嚴格大於 / 灰階加權 / 自差 / 對稱 (AC5..AC10)
# =====================================================================

def test_ac5_change_mask_all_changed():
    # AC5:全變化 — 灰階差 190 > 30 → 全 1
    assert np.array_equal(
        framediff.change_mask(_A10(), _B200()), np.ones((2, 2), np.uint8))


def test_ac6_change_mask_self_is_zero():
    # AC6:自差全 0(metamorphic 釘死;d≡0,0>threshold 恆 False)
    assert np.array_equal(
        framediff.change_mask(_A10(), _A10()), np.zeros((2, 2), np.uint8))


def test_ac7_change_mask_symmetric():
    # AC7:對稱 |gA-gB| == |gB-gA| → mask(A,B) == mask(B,A)
    assert np.array_equal(
        framediff.change_mask(_A10(), _B200()),
        framediff.change_mask(_B200(), _A10()))


def test_ac8_change_mask_strict_greater_than():
    # AC8:嚴格大於門檻(> 非 >=)— 灰階差恰 30:30>30 為 False、30>29 為 True
    P = np.full((1, 1, 3), 100, np.uint8)
    Q = np.full((1, 1, 3), 130, np.uint8)
    assert framediff.change_mask(P, Q, threshold=30)[0, 0] == 0
    assert framediff.change_mask(P, Q, threshold=29)[0, 0] == 1


def test_ac9_change_mask_luma_weight_not_average():
    # AC9:灰階加權(非三通道平均)釘死 — 純綠灰階 0.587*255≈149.685
    #   threshold=100 → 變化(149.7>100);threshold=150 → 不變(149.7>150 False)。
    #   若用三通道平均(255/3=85)則 threshold=100 會得 0,故此 AC 可區辨灰階公式。
    R0 = np.zeros((1, 1, 3), np.uint8)
    G255 = np.array([[[0, 255, 0]]], np.uint8)
    assert framediff.change_mask(R0, G255, threshold=100)[0, 0] == 1
    assert framediff.change_mask(R0, G255, threshold=150)[0, 0] == 0


def test_ac10_change_mask_threshold_upper_bound():
    # AC10:閾值上界 — 差 190,190>255 恆 False → 全 0
    assert np.array_equal(
        framediff.change_mask(_A10(), _B200(), threshold=255),
        np.zeros((2, 2), np.uint8))


# =====================================================================
# change_ratio — 值域 / 自差 0 / 對稱 / 門檻單調 / 部分變化 (AC11..AC15)
# =====================================================================

def test_ac11_change_ratio_all_changed_is_one():
    # AC11:全變化 ratio == 1.0
    assert framediff.change_ratio(_A10(), _B200()) == 1.0


def test_ac12_change_ratio_self_is_zero():
    # AC12:自差 ratio == 0.0(metamorphic 釘死,內建 float 比較)
    assert framediff.change_ratio(_A10(), _A10()) == 0.0


def test_ac13_change_ratio_symmetric():
    # AC13:對稱 — ratio(A,B) == ratio(B,A)
    assert framediff.change_ratio(_A10(), _B200()) == \
        framediff.change_ratio(_B200(), _A10())


def test_ac14_change_ratio_partial_pinned():
    # AC14:部分變化釘值 — 4 像素中 2 個變化 → 0.5
    A, B = _ratio_AB()
    assert framediff.change_ratio(A, B, threshold=30) == 0.5


def test_ac15_change_ratio_threshold_monotonic():
    # AC15(門檻單調,metamorphic):門檻越高、變化率單調不增
    A, B = _ratio_AB()
    r10 = framediff.change_ratio(A, B, 10)
    r100 = framediff.change_ratio(A, B, 100)
    r255 = framediff.change_ratio(A, B, 255)
    assert r10 >= r100 >= r255
    assert r10 == 0.5
    assert r255 == 0.0


# =====================================================================
# change_regions — 連通元件像素級釘死(核心) (AC16..AC23)
# =====================================================================

def test_ac16_change_regions_three_components_order_bbox():
    # AC16(核心:三元件、順序、bbox 全釘)
    #   ①[0,0,2,2] ②[4,0,1,2] ③[2,2,2,2];raster 發現順序 ①→②→③
    A, B = _regions_AB()
    assert framediff.change_regions(A, B, threshold=30) == \
        [[0, 0, 2, 2], [4, 0, 1, 2], [2, 2, 2, 2]]


def test_ac17_change_regions_4connectivity_excludes_diagonal():
    # AC17(4-連通不含對角):只有對角兩像素變化 → 兩個 1x1 元件,非一個
    #   (8-連通會合成 1 個 [0,0,2,2];此 AC 可區辨 4 vs 8)
    A = np.zeros((2, 2, 3), np.uint8)
    B = np.zeros((2, 2, 3), np.uint8)
    B[0, 0] = (200, 200, 200)
    B[1, 1] = (200, 200, 200)
    assert framediff.change_regions(A, B, threshold=30) == \
        [[0, 0, 1, 1], [1, 1, 1, 1]]


def test_ac18_change_regions_min_area_filter():
    # AC18(min_area 過濾):元件像素數 ①3 ②2 ③3;min_area=3 濾掉②、保序保留①③
    A, B = _regions_AB()
    assert framediff.change_regions(A, B, threshold=30, min_area=3) == \
        [[0, 0, 2, 2], [2, 2, 2, 2]]


def test_ac19_change_regions_min_area_boundary_inclusive():
    # AC19(min_area 邊界含等於):min_area=2 → area>=2 三者皆保留(2>=2 保留)
    A, B = _regions_AB()
    assert framediff.change_regions(A, B, threshold=30, min_area=2) == \
        [[0, 0, 2, 2], [4, 0, 1, 2], [2, 2, 2, 2]]


def test_ac20_change_regions_self_diff_empty():
    # AC20(自差無元件):全 0 遮罩 → [](metamorphic)
    assert framediff.change_regions(_A10(), _A10()) == []


def test_ac21_change_regions_all_changed_single():
    # AC21(全變化單一元件):2x2 全變化 → 一個涵蓋全圖的 bbox
    assert framediff.change_regions(_A10(), _B200(), threshold=30) == \
        [[0, 0, 2, 2]]


def test_ac22_change_regions_connectivity_not_4_raises():
    # AC22(connectivity 非 4 拋例外):本輪僅支援 4-連通
    with pytest.raises(ValueError):
        framediff.change_regions(_A10(), _B200(), connectivity=8)


def test_ac23_change_regions_return_types_int_and_positive_wh():
    # AC23(回傳型別):每個 bbox 四元素皆 Python int,且 w>=1, h>=1
    A, B = _regions_AB()
    regions = framediff.change_regions(A, B, threshold=30)
    assert all(isinstance(v, int) for r in regions for v in r)
    assert all(r[2] >= 1 and r[3] >= 1 for r in regions)


# =====================================================================
# highlight — 不 mutate / 畫框 / 無變化 / thickness / 形狀 (AC24..AC29)
# =====================================================================

def test_ac24_highlight_new_array_no_mutate():
    # AC24(回新陣列、不 mutate):out is not B 且 B 逐像素不變
    A, B = _regions_AB()
    B_before = B.copy()
    out = framediff.highlight(A, B, threshold=30)
    assert out is not B
    assert np.array_equal(B, B_before)


def test_ac25_highlight_border_pixels_painted():
    # AC25(框邊像素被塗):元件③ bbox=[2,2,2,2](半開:左 col2、右 col3、上 row2、下 row3)
    #   左上角 (2,2) 與右下角 (3,3) 皆為 color
    A, B = _regions_AB()
    out = framediff.highlight(A, B, threshold=30)
    assert out[2, 2].tolist() == [255, 0, 0]
    assert out[3, 3].tolist() == [255, 0, 0]


def test_ac26_highlight_no_change_equals_B():
    # AC26(無變化 → 等於 B):自差無框,只 copy;且回傳 is not A10
    out = framediff.highlight(_A10(), _A10(), threshold=30)
    assert np.array_equal(out, _A10())
    a = _A10()
    assert framediff.highlight(a, a, threshold=30) is not a


def test_ac27_highlight_thickness_zero_no_draw():
    # AC27(thickness<=0 不畫):逐像素等於 B
    A, B = _regions_AB()
    out = framediff.highlight(A, B, threshold=30, color=(255, 0, 0), thickness=0)
    assert np.array_equal(out, B)


def test_ac28_highlight_shape_and_dtype():
    # AC28(形狀/型別):(4,5,3) uint8
    A, B = _regions_AB()
    out = framediff.highlight(A, B, threshold=30)
    assert out.shape == (4, 5, 3)
    assert out.dtype == np.uint8


def test_ac29_highlight_color_takes_effect():
    # AC29(color 生效):換 (0,0,255),元件③左上 (2,2) 即為該色
    A, B = _regions_AB()
    out = framediff.highlight(A, B, threshold=30, color=(0, 0, 255))
    assert out[2, 2].tolist() == [0, 0, 255]


# =====================================================================
# 錯誤路徑 — 形狀不符四函式皆拋 (AC30..AC33)
# =====================================================================

def test_ac30_change_mask_shape_mismatch_raises():
    # AC30:change_mask 形狀不符 → ValueError
    with pytest.raises(ValueError):
        framediff.change_mask(
            np.zeros((2, 2, 3), np.uint8), np.zeros((2, 3, 3), np.uint8))


def test_ac31_change_ratio_shape_mismatch_raises():
    # AC31:change_ratio 形狀不符 → ValueError
    with pytest.raises(ValueError):
        framediff.change_ratio(
            np.zeros((2, 2, 3), np.uint8), np.zeros((3, 2, 3), np.uint8))


def test_ac32_change_regions_shape_mismatch_raises():
    # AC32:change_regions 形狀不符(末軸不符亦算)→ ValueError
    with pytest.raises(ValueError):
        framediff.change_regions(
            np.zeros((2, 2, 3), np.uint8), np.zeros((2, 2, 4), np.uint8))


def test_ac33_highlight_shape_mismatch_raises():
    # AC33:highlight 形狀不符 → ValueError
    with pytest.raises(ValueError):
        framediff.highlight(
            np.zeros((2, 2, 3), np.uint8), np.zeros((4, 2, 3), np.uint8))


# =====================================================================
# 跨函式一致性(三者共用同一變化定義) (AC34..AC35)
# =====================================================================

def test_ac34_mask_sum_consistent_with_ratio():
    # AC34:change_mask 的 1 像素數 == ratio * H * W(同一定義導出,彼此一致)
    A, B = _ratio_AB()
    H, W = 1, 4
    mask_sum = int(framediff.change_mask(A, B, 30).sum())
    assert mask_sum == round(framediff.change_ratio(A, B, 30) * H * W)
    assert mask_sum == 2


def test_ac35_regions_pixel_count_equals_mask_sum():
    # AC35:三元件像素數總和 == change_mask.sum()(連通元件不漏不重)
    #   ①3 + ②2 + ③3 == 8 == mask.sum()
    A, B = _regions_AB()
    region_pixels = 3 + 2 + 3
    assert region_pixels == int(framediff.change_mask(A, B, 30).sum())
    assert region_pixels == 8


# =====================================================================
# 推導 / property 測試(設計未明列;由 §2/§3/§4 契約推導)
# 每個測試比對應 AC 的單點更強,以同源也能逼出實作 bug。
# =====================================================================

def test_property_change_mask_self_is_zero_arbitrary():
    # 推導(§3.1 metamorphic):對任意 uint8 RGB 影像,change_mask(X, X) 恆全 0,
    # 比 AC6 的單一純色更強的不變式(任意內容、任意門檻 >= 0)。
    rng = np.random.default_rng(0)
    X = rng.integers(0, 256, size=(4, 6, 3), dtype=np.uint8)
    for t in (0, 30, 255):
        assert np.array_equal(
            framediff.change_mask(X, X, threshold=t), np.zeros((4, 6), np.uint8))


def test_property_change_mask_symmetric_arbitrary():
    # 推導(§3.1 metamorphic):對任意同形 X、Y,mask(X,Y) == mask(Y,X) 逐元素恆等,
    # 比 AC7 的純色對更強。
    rng = np.random.default_rng(1)
    X = rng.integers(0, 256, size=(4, 6, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(4, 6, 3), dtype=np.uint8)
    assert np.array_equal(
        framediff.change_mask(X, Y), framediff.change_mask(Y, X))


def test_property_change_mask_values_only_0_or_1_arbitrary():
    # 推導(§2.3):對任意 X、Y 與任意門檻,mask 值恆 ⊆ {0,1}、dtype uint8、二維。
    rng = np.random.default_rng(2)
    X = rng.integers(0, 256, size=(5, 7, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(5, 7, 3), dtype=np.uint8)
    for t in (0, 15, 30, 200, 255):
        m = framediff.change_mask(X, Y, threshold=t)
        assert m.dtype == np.uint8
        assert m.shape == (5, 7)
        assert set(np.unique(m).tolist()).issubset({0, 1})


def test_property_change_ratio_in_unit_interval_arbitrary():
    # 推導(§2.3 + §3.2 值域):對任意 X、Y 與任意門檻,ratio ∈ [0.0,1.0] 且為內建 float。
    rng = np.random.default_rng(3)
    X = rng.integers(0, 256, size=(5, 7, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(5, 7, 3), dtype=np.uint8)
    for t in (0, 30, 128, 255):
        r = framediff.change_ratio(X, Y, threshold=t)
        assert isinstance(r, float) and not isinstance(r, np.floating)
        assert 0.0 <= r <= 1.0


def test_property_change_ratio_threshold_monotonic_arbitrary():
    # 推導(§3.2 門檻單調):對任意 X、Y,門檻遞增 ⇒ ratio 單調不增(逐對驗證)。
    rng = np.random.default_rng(4)
    X = rng.integers(0, 256, size=(6, 8, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(6, 8, 3), dtype=np.uint8)
    thresholds = [0, 10, 30, 60, 100, 150, 200, 255]
    ratios = [framediff.change_ratio(X, Y, threshold=t) for t in thresholds]
    for prev, cur in zip(ratios, ratios[1:]):
        assert prev >= cur


def test_property_change_ratio_equals_mask_mean_arbitrary():
    # 推導(§3.2 一致性):ratio 必等於 mask 的平均(sum/(H*W)),跨函式不得各算各的。
    rng = np.random.default_rng(5)
    X = rng.integers(0, 256, size=(4, 5, 3), dtype=np.uint8)
    Y = rng.integers(0, 256, size=(4, 5, 3), dtype=np.uint8)
    for t in (0, 30, 90, 255):
        m = framediff.change_mask(X, Y, threshold=t)
        r = framediff.change_ratio(X, Y, threshold=t)
        assert r == float(int(m.sum()) / (4 * 5))


def test_property_change_regions_self_empty_arbitrary():
    # 推導(§3.3 metamorphic):對任意 X,change_regions(X, X) == []。
    rng = np.random.default_rng(6)
    X = rng.integers(0, 256, size=(5, 7, 3), dtype=np.uint8)
    assert framediff.change_regions(X, X) == []


def test_property_change_regions_min_area_monotone_subset():
    # 推導(§3.3 min_area 單調):min_area 越大,保留元件數越少(子集/單調不增)。
    # 用 AC16 構造(三元件 area 3/2/3),min_area 由 1→2→3→4 數量 3→3→2→0。
    A, B = _regions_AB()
    counts = [len(framediff.change_regions(A, B, threshold=30, min_area=k))
              for k in (1, 2, 3, 4)]
    assert counts == [3, 3, 2, 0]
    for prev, cur in zip(counts, counts[1:]):
        assert prev >= cur


def test_property_change_regions_min_area_below_one_equals_one():
    # 推導(§2.6 / §4d):min_area < 1(含 0、負值)一律當 1 處理,不拋例外,
    # 結果與 min_area=1 完全相同。
    A, B = _regions_AB()
    base = framediff.change_regions(A, B, threshold=30, min_area=1)
    assert framediff.change_regions(A, B, threshold=30, min_area=0) == base
    assert framediff.change_regions(A, B, threshold=30, min_area=-5) == base


def test_property_change_regions_pixels_partition_mask():
    # 推導(§3.3 + AC35 強化):任意輸入下,所有元件 bbox 內 mask==1 像素數總和
    # 恰等於 mask.sum()(連通元件對變化像素做完整分割,不漏不重)。
    # 用確定性構造避免 raster 順序歧義即可驗 partition 不變式。
    A, B = _regions_AB()
    m = framediff.change_mask(A, B, 30)
    regions = framediff.change_regions(A, B, threshold=30)
    total = 0
    for (x, y, w, h) in regions:
        total += int(m[y:y + h, x:x + w].sum())
    assert total == int(m.sum())


def test_property_highlight_does_not_mutate_inputs():
    # 推導(§4g 不 mutate):highlight 以 B.copy() 起手,呼叫後 A、B 內容皆不變。
    A, B = _regions_AB()
    A_before = A.copy()
    B_before = B.copy()
    framediff.highlight(A, B, threshold=30)
    assert np.array_equal(A, A_before)
    assert np.array_equal(B, B_before)


def test_property_highlight_no_change_returns_copy_of_B():
    # 推導(§3.4 端點 + §4f):門檻濾光(threshold 過大 → regions 空)時,
    # highlight 逐像素等於 B 且為新陣列(is not B),涵蓋「regions 空但 A!=B」這條路徑。
    A, B = _regions_AB()
    out = framediff.highlight(A, B, threshold=255)  # 差 200 < 255? 200>255 False → 全濾光
    assert out is not B
    assert np.array_equal(out, B)


def test_property_change_mask_does_not_mutate_inputs():
    # 推導(§4g 不 mutate):change_mask 不寫輸入,呼叫後 A、B 內容不變。
    A = _A10()
    B = _B200()
    framediff.change_mask(A, B)
    assert np.array_equal(A, np.full((2, 2, 3), 10, np.uint8))
    assert np.array_equal(B, np.full((2, 2, 3), 200, np.uint8))
