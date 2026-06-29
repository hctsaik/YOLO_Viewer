"""overlay 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/08_overlay.md(AC1..AC36 + §3 資料流 + §4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import overlay`。此時實作尚未生成,import 不到屬正常(test-first,非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

純邏輯 / 零 I/O / 零 GUI(Tier A)。像素級 AC 統一用全黑畫布
`np.zeros((10,10,3), np.uint8)`、`bbox=[2,3,4,5]`、半開區間邊框定義(§3.3b)。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_overlay.py -p no:cacheprovider --strict-markers -q
"""
import copy

import numpy as np
import pytest

import overlay


# =====================================================================
# helpers
# =====================================================================

def _black():
    # 像素級 AC 統一畫布:全黑 10x10x3 uint8(§5)
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _gradient():
    # metamorphic AC 的非全黑輸入:base = arange(...).reshape(10,10,3)(AC28)
    return np.arange(10 * 10 * 3, dtype=np.uint8).reshape(10, 10, 3)


# =====================================================================
# 常數契約
# =====================================================================

def test_ac1_default_color_is_red():
    # AC1:DEFAULT_COLOR == (255,0,0)
    assert overlay.DEFAULT_COLOR == (255, 0, 0)


def test_ac2_class_colors_fixed_mapping():
    # AC2:CLASS_COLORS 三筆釘死對映
    assert overlay.CLASS_COLORS["defect"] == (255, 0, 0)
    assert overlay.CLASS_COLORS["scratch"] == (0, 255, 0)
    assert overlay.CLASS_COLORS["dent"] == (0, 0, 255)


# =====================================================================
# color_for
# =====================================================================

def test_ac3_color_for_hit_mapping():
    # AC3:cls=scratch 命中對照 → 綠
    assert overlay.color_for({"cls": "scratch"}) == (0, 255, 0)


def test_ac4_color_for_miss_defaults():
    # AC4:未命中 cls → DEFAULT_COLOR 紅
    assert overlay.color_for({"cls": "unknown_xyz"}) == (255, 0, 0)


def test_ac5_color_for_explicit_color_overrides():
    # AC5:顯式 color 覆蓋對照
    assert overlay.color_for({"cls": "scratch"}, color=(7, 8, 9)) == (7, 8, 9)


def test_ac6_color_for_missing_cls_defaults():
    # AC6:無 cls 鍵 → DEFAULT_COLOR,不拋例外
    assert overlay.color_for({}) == (255, 0, 0)


# =====================================================================
# filter_detections — conf / class / 保序 / 不 mutate
# =====================================================================

def test_ac7_filter_drops_low_conf():
    # AC7:過濾低 conf(0.3 < 0.5 被除、0.9 >= 0.5 保留)
    assert overlay.filter_detections(
        [{"cls": "a", "conf": 0.9}, {"cls": "b", "conf": 0.3}],
        conf_threshold=0.5) == [{"cls": "a", "conf": 0.9}]


def test_ac8_filter_boundary_equal_kept():
    # AC8:邊界相等保留(0.5 >= 0.5)
    assert len(overlay.filter_detections(
        [{"cls": "a", "conf": 0.5}], conf_threshold=0.5)) == 1


def test_ac9_filter_by_class():
    # AC9:class 篩選
    assert overlay.filter_detections(
        [{"cls": "a", "conf": 0.9}, {"cls": "b", "conf": 0.9}],
        classes=["a"]) == [{"cls": "a", "conf": 0.9}]


def test_ac10_filter_defaults_keep_all():
    # AC10:classes=None + conf_threshold=0.0(預設)→ 全保留(0.0>=0.0)
    assert len(overlay.filter_detections(
        [{"cls": "a", "conf": 0.0}, {"cls": "b", "conf": 1.0}])) == 2


def test_ac11_filter_preserves_order():
    # AC11:保序(保留原相對順序)
    d = [{"cls": "a", "conf": 0.9}, {"cls": "b", "conf": 0.8}, {"cls": "c", "conf": 0.95}]
    assert [x["cls"] for x in overlay.filter_detections(d, conf_threshold=0.85)] == ["a", "c"]


def test_ac12_filter_missing_conf_treated_as_zero():
    # AC12:conf 缺鍵視同 0.0(threshold=0.0 通過、threshold=0.1 被除)
    assert overlay.filter_detections([{"cls": "a"}], conf_threshold=0.0) == [{"cls": "a"}]
    assert overlay.filter_detections([{"cls": "a"}], conf_threshold=0.1) == []


def test_ac13_filter_does_not_mutate_and_new_list():
    # AC13:不 mutate(deepcopy 比對不變)且回傳 is not d(新 list)
    d = [{"cls": "a", "conf": 0.9}, {"cls": "b", "conf": 0.3}]
    before = copy.deepcopy(d)
    out = overlay.filter_detections(d, conf_threshold=0.5)
    assert d == before
    assert out is not d


# =====================================================================
# draw — 像素級交叉驗證(全黑 10x10,bbox=[2,3,4,5],thickness=1,color=(255,0,0))
# 由 §3.3b:左 col=2、右 col=5、上 row=3、下 row=7
# =====================================================================

def test_ac14_draw_top_left_corner_on_border():
    # AC14:左上角 (row=3,col=2) 在框上
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert out[3, 2].tolist() == [255, 0, 0]


def test_ac15_draw_bottom_right_corner_on_border():
    # AC15:右下角 (row=7,col=5) 在框上
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert out[7, 5].tolist() == [255, 0, 0]


def test_ac16_draw_edge_midpoints_on_border():
    # AC16:上邊中段 (3,4) 與左邊中段 (5,2) 皆在框上
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert out[3, 4].tolist() == [255, 0, 0]
    assert out[5, 2].tolist() == [255, 0, 0]


def test_ac17_draw_interior_hollow_thickness1():
    # AC17:thickness=1 框內部 (5,4) 未塗(空心邊框)
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert out[5, 4].tolist() == [0, 0, 0]


def test_ac18_draw_outside_stays_black():
    # AC18:框外像素仍黑(含框上緣外一列 row=2)
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert out[0, 0].tolist() == [0, 0, 0]
    assert out[9, 9].tolist() == [0, 0, 0]
    assert out[2, 2].tolist() == [0, 0, 0]


def test_ac19_draw_does_not_mutate_input_and_new_object():
    # AC19:輸入未被 mutate(仍全 0)且回傳 out is not img(新物件)
    img = _black()
    out = overlay.draw(img, [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert np.array_equal(img, np.zeros((10, 10, 3), np.uint8))
    assert out is not img


def test_ac20_draw_shape_and_dtype_preserved():
    # AC20:回傳形狀/型別不變
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=1)
    assert out.shape == (10, 10, 3)
    assert out.dtype == np.uint8


# =====================================================================
# draw — class→顏色(color=None 時用對照)
# =====================================================================

def test_ac21_draw_class_color_hit_scratch_green():
    # AC21:不給 color、scratch 命中對照 → 綠
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "scratch", "conf": 1.0}])
    assert out[3, 2].tolist() == [0, 255, 0]


def test_ac22_draw_class_color_miss_default_red():
    # AC22:未命中 cls → DEFAULT_COLOR 紅
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "unknown", "conf": 1.0}])
    assert out[3, 2].tolist() == [255, 0, 0]


def test_ac23_draw_explicit_color_overrides_mapping():
    # AC23:顯式 color 對所有框生效、覆蓋對照
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "scratch", "conf": 1.0}],
                       color=(0, 0, 255))
    assert out[3, 2].tolist() == [0, 0, 255]


# =====================================================================
# draw — thickness
# =====================================================================

def test_ac24_draw_thick_fills_interior():
    # AC24:thickness 夠大(10)框內部 (5,4) 也被塗(對照 AC17 空心)
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=10)
    assert out[5, 4].tolist() == [255, 0, 0]


def test_ac25_draw_thickness_zero_draws_nothing():
    # AC25:thickness<=0 → 逐像素等於輸入
    img = _black()
    out = overlay.draw(img, [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=0)
    assert np.array_equal(out, img)


# =====================================================================
# draw — 篩選貫穿(conf / class 與 filter_detections 一致)
# =====================================================================

def test_ac26_draw_conf_filter_passthrough():
    # AC26:被 conf 濾掉 → 不畫,逐像素等於輸入
    img = _black()
    out = overlay.draw(img, [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 0.2}],
                       color=(255, 0, 0), conf_threshold=0.5)
    assert np.array_equal(out, img)


def test_ac27_draw_class_filter_passthrough():
    # AC27:被 class 濾掉 → 不畫,逐像素等於輸入
    img = _black()
    out = overlay.draw(img, [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), classes=["b"])
    assert np.array_equal(out, img)


# =====================================================================
# draw — 可推導不變量(metamorphic)
# =====================================================================

def test_ac28_empty_dets_pixelwise_identity():
    # AC28:空 dets → 逐像素等於輸入(非全黑 base)且回傳 is not base
    base = _gradient()
    out = overlay.draw(base, [])
    assert np.array_equal(out, base) is True
    assert out is not base


def test_ac29_all_filtered_pixelwise_identity():
    # AC29:全濾掉(門檻濾光)→ 逐像素等於輸入
    base = _gradient()
    out = overlay.draw(base, [{"bbox": [1, 1, 3, 3], "cls": "a", "conf": 0.1}],
                       conf_threshold=0.9)
    assert np.array_equal(out, base) is True


def test_ac30_partial_out_of_bounds_clips_no_exception():
    # AC30:bbox 部分超界 → 只畫可見部分、不拋例外;界內角被畫、界內最後一格合法 uint8
    img = _black()
    out = overlay.draw(img, [{"bbox": [8, 8, 5, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0))
    assert out[8, 8].tolist() == [255, 0, 0]
    # 界內最後一格仍是合法 uint8(不越界存取 / 不環繞)
    val = out[9, 9].tolist()
    assert all(0 <= c <= 255 for c in val)


def test_ac31_fully_out_of_bounds_no_draw_no_exception():
    # AC31:完全在影像外 → 不畫、不拋例外、逐像素等於輸入
    img = _black()
    out = overlay.draw(img, [{"bbox": [100, 100, 5, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0))
    assert np.array_equal(out, img) is True


def test_ac32_negative_coords_clip_no_wraparound():
    # AC32:負座標夾界 → 不拋例外;改動處皆等於 color(無環繞寫入到負索引尾端)
    img = _black()
    out = overlay.draw(img, [{"bbox": [-3, -3, 5, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0))
    # 輸入全黑 → 任何非黑像素都應恰為 color(若有環繞寫入會出現別處被改成 color)
    changed = np.argwhere(np.any(out != img, axis=2))
    for row, col in changed:
        assert out[row, col].tolist() == [255, 0, 0]
    # 框右下可見部分:bbox[-3,-3,5,5] 半開覆蓋 col/row in [-3, 2),界內為 0,1
    # 右下角 (1,1) 應在框內圈被畫到(下邊 row=-3+5-1=1、右邊 col=1)
    assert out[1, 1].tolist() == [255, 0, 0]


def test_ac33_nonpositive_wh_draws_nothing():
    # AC33:w=0 或 h=0 → 無可見框,逐像素等於輸入
    img = _black()
    out_w0 = overlay.draw(img, [{"bbox": [2, 3, 0, 5], "cls": "a", "conf": 1.0}],
                          color=(255, 0, 0))
    out_h0 = overlay.draw(img, [{"bbox": [2, 3, 4, 0], "cls": "a", "conf": 1.0}],
                          color=(255, 0, 0))
    assert np.array_equal(out_w0, img) is True
    assert np.array_equal(out_h0, img) is True


# =====================================================================
# draw — 重疊覆蓋(順序語義)
# =====================================================================

def test_ac34_overlap_later_overwrites_earlier():
    # AC34:兩框同位,後畫者(scratch 綠)覆蓋先畫者(defect 紅)
    out = overlay.draw(_black(), [
        {"bbox": [2, 2, 4, 4], "cls": "defect", "conf": 1.0},
        {"bbox": [2, 2, 4, 4], "cls": "scratch", "conf": 1.0},
    ])
    assert out[2, 2].tolist() == [0, 255, 0]


# =====================================================================
# draw_label — 不破壞 bbox 像素、不拋例外
# =====================================================================

def test_ac35_draw_label_keeps_bbox_pixels():
    # AC35:draw_label=True 不拋例外、形狀/型別不變、bbox 邊像素不受影響
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "defect", "conf": 0.87}],
                       draw_label=True)
    assert out.shape == (10, 10, 3)
    assert out.dtype == np.uint8
    assert out[3, 2].tolist() == [255, 0, 0]


def test_ac36_draw_label_empty_dets_pixelwise_identity():
    # AC36:draw_label=True 對空 dets 仍逐像素等於輸入
    base = _gradient()
    out = overlay.draw(base, [], draw_label=True)
    assert np.array_equal(out, base) is True


# =====================================================================
# 推導 / property 測試(設計未明列;由 §3 / §4 契約推導,對同源也能逼出實作 bug)
# =====================================================================

def test_property_filter_classes_none_with_missing_cls_kept():
    # 推導(§4d):classes=None 時 cls 缺鍵不受影響 → 仍依 conf 保留。
    assert overlay.filter_detections([{"conf": 1.0}], classes=None) == [{"conf": 1.0}]


def test_property_filter_missing_cls_with_classes_dropped():
    # 推導(§4d):classes 有給且 det 無 cls(→ None)且 None not in classes → 被除。
    assert overlay.filter_detections([{"conf": 1.0}], classes=["a"]) == []
    # 但 None in classes 時應保留
    assert overlay.filter_detections([{"conf": 1.0}], classes=[None]) == [{"conf": 1.0}]


def test_property_filter_returns_same_dict_objects_not_copies():
    # 推導(§2.3 / §3.1):回傳元素為原 dict 物件的「參照」(淺層,不複製 dict)。
    d0 = {"cls": "a", "conf": 0.9}
    out = overlay.filter_detections([d0], conf_threshold=0.5)
    assert out[0] is d0


def test_property_draw_filter_equiv_invariant():
    # 推導(§3.3 step2):draw 畫的框集合 == filter_detections 通過的集合。
    # 構造:一框會被 conf 濾掉、一框通過 → 結果應與只畫通過框等價(逐像素相等)。
    img = _black()
    mixed = overlay.draw(img, [
        {"bbox": [2, 3, 4, 5], "cls": "a", "conf": 0.2},   # 被濾
        {"bbox": [2, 3, 4, 5], "cls": "a", "conf": 0.9},   # 通過
    ], color=(255, 0, 0), conf_threshold=0.5)
    only_kept = overlay.draw(img, [
        {"bbox": [2, 3, 4, 5], "cls": "a", "conf": 0.9},
    ], color=(255, 0, 0), conf_threshold=0.5)
    assert np.array_equal(mixed, only_kept) is True


def test_property_draw_does_not_mutate_input_dets():
    # 推導(§4h):draw 不得 mutate 傳入的 dets(list 與其中 dict)。
    dets = [{"bbox": [2, 3, 4, 5], "cls": "scratch", "conf": 1.0}]
    before = copy.deepcopy(dets)
    overlay.draw(_black(), dets, draw_label=True)
    assert dets == before


def test_property_draw_thickness_full_fills_when_ge_min_wh():
    # 推導(§3.3d):t >= min(w,h) 時整框實心填滿 → 框內每個半開覆蓋像素皆 color。
    # bbox=[2,3,4,5] → min(w,h)=4;thickness=4 應已填滿內部 (5,4)。
    out = overlay.draw(_black(), [{"bbox": [2, 3, 4, 5], "cls": "a", "conf": 1.0}],
                       color=(255, 0, 0), thickness=4)
    assert out[5, 4].tolist() == [255, 0, 0]


def test_property_color_for_returns_tuple_when_color_given():
    # 推導(§3.2):color is not None → 回 tuple(color)(即使傳入 list 也轉 tuple)。
    assert overlay.color_for({"cls": "scratch"}, color=[1, 2, 3]) == (1, 2, 3)
