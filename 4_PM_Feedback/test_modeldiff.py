"""modeldiff 單元驗收(對應設計 3_Architect_Design/24_modeldiff.md §3 AC1–AC26)。
Tier A 純邏輯:IoU 框級配對 + 每圖覆蓋差異 + 資料集彙總/篩選/佇列。
所有 IoU/配對數值已在設計逐項手算釘死;另含推導 property(對稱/純度/計數一致)。
跑法:pytest 4_PM_Feedback/test_modeldiff.py -v ;閘門:python verify/gate.py modeldiff
"""
import pytest

import modeldiff


def d(x, y, w, h, cls="s", conf=0.9):
    return {"bbox": [x, y, w, h], "cls": cls, "conf": conf}


# ============================== iou ==============================
def test_iou_identical():  # AC1
    assert modeldiff.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_iou_half_overlap():  # AC2  inter=50 union=150
    assert modeldiff.iou([0, 0, 10, 10], [5, 0, 10, 10]) == pytest.approx(1 / 3)


def test_iou_no_overlap():  # AC3
    assert modeldiff.iou([0, 0, 10, 10], [10, 0, 10, 10]) == 0.0


def test_iou_contained():  # AC4  inter=36 union=100
    assert modeldiff.iou([0, 0, 10, 10], [2, 2, 6, 6]) == pytest.approx(0.36)


def test_iou_degenerate_zero_area():  # AC5  w=0 → union 由另一框決定,inter=0 → 0.0,不除零
    assert modeldiff.iou([0, 0, 0, 10], [0, 0, 10, 10]) == 0.0
    assert modeldiff.iou([0, 0, 0, 0], [0, 0, 0, 0]) == 0.0  # 全退化也不崩


@pytest.mark.parametrize("a,b", [
    ([0, 0, 10, 10], [5, 0, 10, 10]),
    ([0, 0, 10, 10], [2, 2, 6, 6]),
    ([3, 4, 7, 9], [1, 1, 20, 20]),
])
def test_iou_symmetric(a, b):  # AC6
    assert modeldiff.iou(a, b) == pytest.approx(modeldiff.iou(b, a))


# ============================== match ==============================
def test_match_identical_lists_all_matched():  # AC7
    A = [d(0, 0, 10, 10), d(50, 50, 8, 8)]
    B = [d(0, 0, 10, 10), d(50, 50, 8, 8)]
    r = modeldiff.match(A, B, iou_thr=0.5)
    assert len(r["matched"]) == 2
    assert r["only_a"] == [] and r["only_b"] == []


def test_match_threshold_boundary():  # AC8  iou=81/119≈0.6807
    A = [d(0, 0, 10, 10)]
    B = [d(1, 1, 10, 10)]
    assert modeldiff.iou([0, 0, 10, 10], [1, 1, 10, 10]) == pytest.approx(81 / 119)
    r_lo = modeldiff.match(A, B, iou_thr=0.5)
    assert len(r_lo["matched"]) == 1 and r_lo["only_a"] == [] and r_lo["only_b"] == []
    r_hi = modeldiff.match(A, B, iou_thr=0.7)
    assert r_hi["matched"] == [] and r_hi["only_a"] == [0] and r_hi["only_b"] == [0]


def test_match_same_class_blocks_cross_class():  # AC9
    A = [d(0, 0, 10, 10, cls="scratch")]
    B = [d(0, 0, 10, 10, cls="dent")]
    r = modeldiff.match(A, B, iou_thr=0.5, same_class=True)
    assert r["matched"] == [] and r["only_a"] == [0] and r["only_b"] == [0]


def test_match_same_class_false_allows_cross_class():  # AC10
    A = [d(0, 0, 10, 10, cls="scratch")]
    B = [d(0, 0, 10, 10, cls="dent")]
    r = modeldiff.match(A, B, iou_thr=0.5, same_class=False)
    assert len(r["matched"]) == 1 and r["only_a"] == [] and r["only_b"] == []


def test_match_greedy_multi():  # AC11
    A = [d(0, 0, 10, 10), d(20, 20, 10, 10)]
    B = [d(1, 1, 10, 10), d(100, 100, 10, 10)]
    r = modeldiff.match(A, B, iou_thr=0.5)
    assert len(r["matched"]) == 1
    assert r["matched"][0][0] == 0 and r["matched"][0][1] == 0  # a0 配 b0
    assert r["only_a"] == [1] and r["only_b"] == [1]


def test_match_contested_highest_iou_wins_deterministic():  # AC12
    A = [d(0, 0, 10, 10)]
    B = [d(0, 0, 10, 10), d(1, 1, 10, 10)]  # b0 iou=1.0, b1 iou≈0.6807
    r = modeldiff.match(A, B, iou_thr=0.5)
    assert len(r["matched"]) == 1
    assert r["matched"][0][1] == 0  # 配到 IoU 最高的 b0
    assert r["only_b"] == [1] and r["only_a"] == []


# ============================== diff_image ==============================
def test_diff_image_conf_range_filters():  # AC13
    A = [d(0, 0, 10, 10, conf=0.9), d(50, 50, 10, 10, conf=0.2)]
    B = [d(0, 0, 10, 10, conf=0.8)]
    r = modeldiff.diff_image(A, B, iou_thr=0.5, conf_range=(0.5, 1.0))
    assert r["n_a"] == 1 and r["n_b"] == 1   # 低 conf 的 a1 被濾掉
    assert r["matched"] == 1 and r["status"] == "agree"


def test_diff_image_classes_filter():  # AC14
    A = [d(0, 0, 10, 10, cls="scratch"), d(50, 50, 10, 10, cls="dent")]
    B = [d(0, 0, 10, 10, cls="scratch")]
    r = modeldiff.diff_image(A, B, classes=["scratch"])
    assert r["n_a"] == 1 and r["n_b"] == 1 and r["status"] == "agree"


def test_diff_image_status_a_only():  # AC15
    A = [d(0, 0, 10, 10), d(50, 50, 10, 10)]
    B = [d(0, 0, 10, 10)]
    r = modeldiff.diff_image(A, B)
    assert (r["n_a"], r["n_b"], r["matched"], r["only_a"], r["only_b"]) == (2, 1, 1, 1, 0)
    assert r["status"] == "a_only"


def test_diff_image_status_b_only():  # AC16
    A = [d(0, 0, 10, 10)]
    B = [d(0, 0, 10, 10), d(50, 50, 10, 10)]
    r = modeldiff.diff_image(A, B)
    assert r["status"] == "b_only" and r["only_b"] == 1 and r["only_a"] == 0


def test_diff_image_status_disagree():  # AC17
    A = [d(0, 0, 10, 10), d(50, 50, 10, 10)]
    B = [d(0, 0, 10, 10), d(200, 200, 10, 10)]
    r = modeldiff.diff_image(A, B)
    assert r["status"] == "disagree" and r["only_a"] == 1 and r["only_b"] == 1


def test_diff_image_status_agree():  # AC18
    r = modeldiff.diff_image([d(0, 0, 10, 10)], [d(0, 0, 10, 10)])
    assert r["status"] == "agree" and r["matched"] == 1


def test_diff_image_status_both_empty():  # AC19
    assert modeldiff.diff_image([], [])["status"] == "both_empty"
    # 全被 conf 濾掉也算 both_empty
    r = modeldiff.diff_image([d(0, 0, 10, 10, conf=0.1)], [], conf_range=(0.5, 1.0))
    assert r["status"] == "both_empty" and r["n_a"] == 0


def test_diff_image_missing_a():  # AC20  缺檔 ≠ both_empty
    r = modeldiff.diff_image([], [d(0, 0, 10, 10)], a_present=False)
    assert r["status"] == "missing_a" and r["a_present"] is False


def test_diff_image_missing_b():  # AC21
    r = modeldiff.diff_image([d(0, 0, 10, 10)], [], b_present=False)
    assert r["status"] == "missing_b" and r["b_present"] is False


# ============================== summarize ==============================
def _records():
    return [
        {"name": "i0", "n_a": 2, "n_b": 1, "matched": 1, "only_a": 1, "only_b": 0,
         "status": "a_only", "a_present": True, "b_present": True},
        {"name": "i1", "n_a": 1, "n_b": 1, "matched": 1, "only_a": 0, "only_b": 0,
         "status": "agree", "a_present": True, "b_present": True},
        {"name": "i2", "n_a": 0, "n_b": 0, "matched": 0, "only_a": 0, "only_b": 0,
         "status": "missing_b", "a_present": True, "b_present": False},
    ]


def test_summarize_aggregates():  # AC22
    s = modeldiff.summarize(_records())
    assert s["total_a"] == 3 and s["total_b"] == 2
    assert s["imgs_a"] == 2 and s["imgs_b"] == 2
    assert s["total_matched"] == 2 and s["total_only_a"] == 1 and s["total_only_b"] == 0
    assert s["delta_boxes"] == 1 and s["delta_imgs"] == 0
    assert s["n_missing_a"] == 0 and s["n_missing_b"] == 1


# ============================== filter_images ==============================
def test_filter_images_modes():  # AC23
    recs = _records()
    assert [r["name"] for r in modeldiff.filter_images(recs, "a_only")] == ["i0"]
    assert [r["name"] for r in modeldiff.filter_images(recs, "disagree")] == ["i0"]
    assert [r["name"] for r in modeldiff.filter_images(recs, "missing")] == ["i2"]
    assert [r["name"] for r in modeldiff.filter_images(recs, "agree")] == ["i1"]
    assert len(modeldiff.filter_images(recs, "all")) == 3


# ============================== queue ==============================
def test_queue_ordering():  # AC24
    recs = [
        {"name": "b", "status": "agree", "only_a": 0, "only_b": 0},
        {"name": "a", "status": "disagree", "only_a": 1, "only_b": 1},
        {"name": "c", "status": "missing_b", "only_a": 0, "only_b": 0},
        {"name": "d", "status": "a_only", "only_a": 1, "only_b": 0},
        {"name": "e", "status": "a_only", "only_a": 3, "only_b": 0},
    ]
    assert [r["name"] for r in modeldiff.queue(recs)] == ["c", "a", "e", "d", "b"]


# ============================== property / metamorphic ==============================
def test_purity_inputs_not_mutated():  # AC25
    A = [d(0, 0, 10, 10), d(50, 50, 10, 10)]
    B = [d(0, 0, 10, 10)]
    import copy
    A0, B0 = copy.deepcopy(A), copy.deepcopy(B)
    modeldiff.match(A, B)
    modeldiff.diff_image(A, B, conf_range=(0.3, 0.95), classes=["s"])
    assert A == A0 and B == B0


@pytest.mark.parametrize("A,B", [
    ([d(0, 0, 10, 10), d(50, 50, 10, 10)], [d(0, 0, 10, 10)]),
    ([d(0, 0, 10, 10)], [d(0, 0, 10, 10), d(50, 50, 10, 10), d(99, 99, 5, 5)]),
    ([d(0, 0, 10, 10), d(1, 1, 10, 10)], [d(0, 0, 10, 10)]),
    ([], [d(0, 0, 10, 10)]),
])
def test_count_consistency_metamorphic(A, B):  # AC26  matched+only==n
    r = modeldiff.diff_image(A, B)
    assert r["matched"] + r["only_a"] == r["n_a"]
    assert r["matched"] + r["only_b"] == r["n_b"]
