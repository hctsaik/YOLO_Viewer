"""filtersort 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/10_filtersort.md(AC1..AC26 + §4 邊界 + §5.2 metamorphic)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import filtersort`。此時實作尚未生成,import 不到屬正常(非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_filtersort.py -p no:cacheprovider --strict-markers -q
"""
import copy
import inspect

import pytest

import filtersort


# =====================================================================
# 共用夾具 FIX(設計 §5 原樣建立;name 唯一,便於釘死確切順序)
#   派生量速查:
#     name  time  conf   n_det  reviewed  tagged
#     b.png 30.0  0.90   1      False     False
#     a.png 10.0  0.00   0      True      True
#     d.png 20.0  0.95   2      True      False
#     c.png 40.0  0.70   1      False     False
# =====================================================================

def _fix():
    """每次回新的一份 FIX,避免測試間互相污染。"""
    return [
        {"name": "b.png", "time": 30.0,
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.90}],
         "sidecar": {"verdict": "unset", "review_status": "none", "tags": []}},
        {"name": "a.png", "time": 10.0,
         "detections": [],
         "sidecar": {"verdict": "true_defect", "tags": ["True Defect"]}},
        {"name": "d.png", "time": 20.0,
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50},
                        {"bbox": [0, 0, 1, 1], "cls": "y", "conf": 0.95}],
         "sidecar": {"review_status": "done", "tags": []}},
        {"name": "c.png", "time": 40.0,
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.70}],
         "sidecar": {}},
    ]


def _names(items):
    return [it["name"] for it in items]


# =====================================================================
# 常數契約
# =====================================================================

def test_ac1_sort_keys_exact_order_and_len():
    # AC1:SORT_KEYS 內容與順序逐字相等,且長度為 6
    assert filtersort.SORT_KEYS == ["name", "time", "conf", "n_det", "reviewed", "tagged"]
    assert len(filtersort.SORT_KEYS) == 6


# =====================================================================
# sort_items — name(字典序)
# =====================================================================

def test_ac2_sort_name_asc():
    # AC2:name 升序
    assert _names(filtersort.sort_items(_fix(), "name")) == ["a.png", "b.png", "c.png", "d.png"]


def test_ac3_sort_name_desc():
    # AC3:name 降序(reverse=True)
    assert _names(filtersort.sort_items(_fix(), "name", reverse=True)) == \
        ["d.png", "c.png", "b.png", "a.png"]


# =====================================================================
# sort_items — time(數值)
# =====================================================================

def test_ac4_sort_time_asc():
    # AC4:time 10,20,30,40 升序
    assert _names(filtersort.sort_items(_fix(), "time")) == ["a.png", "d.png", "b.png", "c.png"]


def test_ac5_sort_time_desc():
    # AC5:time 降序
    assert _names(filtersort.sort_items(_fix(), "time", reverse=True)) == \
        ["c.png", "b.png", "d.png", "a.png"]


# =====================================================================
# sort_items — conf(該圖最大偵測 conf;無偵測=0)
# =====================================================================

def test_ac6_sort_conf_asc():
    # AC6:conf 0.0,0.70,0.90,0.95 升序
    assert _names(filtersort.sort_items(_fix(), "conf")) == ["a.png", "c.png", "b.png", "d.png"]


def test_ac7_sort_conf_desc():
    # AC7:conf 降序
    assert _names(filtersort.sort_items(_fix(), "conf", reverse=True)) == \
        ["d.png", "b.png", "c.png", "a.png"]


# =====================================================================
# sort_items — n_det(偵測數;b/c 同為 1 → tie-break name 升序)
# =====================================================================

def test_ac8_sort_n_det_asc():
    # AC8:n_det 0,1,1,2 升序;b 與 c 同為 1 → tie-break name 升序 b<c
    assert _names(filtersort.sort_items(_fix(), "n_det")) == ["a.png", "b.png", "c.png", "d.png"]


def test_ac9_sort_n_det_desc_tiebreak_not_reversed():
    # AC9:n_det 降序;同為 1 的 b/c tie-break 仍 name 升序 b<c(不隨 reverse 反轉)
    assert _names(filtersort.sort_items(_fix(), "n_det", reverse=True)) == \
        ["d.png", "b.png", "c.png", "a.png"]


# =====================================================================
# sort_items — reviewed(bool:False<True)
# =====================================================================

def test_ac10_sort_reviewed_asc():
    # AC10:False 群在前 b,c(name 升序);True 群在後 a,d(name 升序)
    assert _names(filtersort.sort_items(_fix(), "reviewed")) == \
        ["b.png", "c.png", "a.png", "d.png"]


def test_ac11_sort_reviewed_desc_same_group_name_not_reversed():
    # AC11:True 群在前 a,d(name 升序);False 群在後 b,c(name 升序);同群 name 不反轉
    assert _names(filtersort.sort_items(_fix(), "reviewed", reverse=True)) == \
        ["a.png", "d.png", "b.png", "c.png"]


# =====================================================================
# sort_items — tagged(bool:有無 tags)
# =====================================================================

def test_ac12_sort_tagged_asc():
    # AC12:tagged=False 群 b,c,d(name 升序);tagged=True 群 a
    assert _names(filtersort.sort_items(_fix(), "tagged")) == \
        ["b.png", "c.png", "d.png", "a.png"]


def test_ac13_sort_tagged_desc():
    # AC13:tagged=True 群 a 在前;False 群 b,c,d(name 升序)
    assert _names(filtersort.sort_items(_fix(), "tagged", reverse=True)) == \
        ["a.png", "b.png", "c.png", "d.png"]


# =====================================================================
# sort_items — 非法 key / 空輸入
# =====================================================================

def test_ac14_sort_empty_input_empty_output():
    # AC14:空輸入 → 空輸出(任一合法 key / reverse)
    assert filtersort.sort_items([], "name") == []
    assert filtersort.sort_items([], "conf", reverse=True) == []


def test_ac15_sort_illegal_key_raises_valueerror():
    # AC15:非法 key "size" ∉ SORT_KEYS → 拋 ValueError
    with pytest.raises(ValueError):
        filtersort.sort_items(_fix(), "size")


# =====================================================================
# sort_items — 不 mutate
# =====================================================================

def test_ac16_sort_does_not_mutate_input():
    # AC16:輸入(含各 item 之 sidecar/detections 子物件)呼叫後內容不變
    fix = _fix()
    before = copy.deepcopy(fix)
    _ = filtersort.sort_items(fix, "conf", reverse=True)
    assert fix == before


def test_ac17_sort_returns_new_list_with_same_item_refs():
    # AC17:回傳是新 list(非同一參考);元素為原 item 物件之參考(排序後第一個是原 fix[1] 的 a.png)
    fix = _fix()
    out = filtersort.sort_items(fix, "name")
    assert out is not fix
    assert out[0] is fix[1]


# =====================================================================
# review_queue — 釘死預設順序
# =====================================================================

def test_ac18_review_queue_fix_order():
    # AC18:唯一期望值(§5.1 推導表):待審群 b(0.90),c(0.70) conf 降序在前;
    #      已審群 d(0.95),a(0.0) conf 降序在後 → ["b.png","c.png","d.png","a.png"]
    assert _names(filtersort.review_queue(_fix())) == ["b.png", "c.png", "d.png", "a.png"]


# =====================================================================
# review_queue — 空輸入 / 不 mutate
# =====================================================================

def test_ac19_review_queue_empty_input():
    # AC19:空輸入 → 空輸出
    assert filtersort.review_queue([]) == []


def test_ac20_review_queue_does_not_mutate_input():
    # AC20:不 mutate 輸入
    fix = _fix()
    before = copy.deepcopy(fix)
    _ = filtersort.review_queue(fix)
    assert fix == before


# =====================================================================
# review_queue — 規則隔離驗證(各層獨立可斷言)
# =====================================================================

def test_ac21_review_queue_unreviewed_beats_conf():
    # AC21:第一鍵 — 待審優先壓過 conf。lo 待審 conf 低仍排在已審 hi 前
    items = [
        {"name": "hi.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.99}],
         "sidecar": {"verdict": "true_defect"}},   # 已審、conf 高
        {"name": "lo.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.10}],
         "sidecar": {}},                            # 待審、conf 低
    ]
    assert _names(filtersort.review_queue(items)) == ["lo.png", "hi.png"]


def test_ac22_review_queue_same_group_conf_desc():
    # AC22:第二鍵 — 同為待審時 conf 降序(0.80 在 0.30 前)
    items = [
        {"name": "p.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.30}],
         "sidecar": {}},
        {"name": "q.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.80}],
         "sidecar": {}},
    ]
    assert _names(filtersort.review_queue(items)) == ["q.png", "p.png"]


def test_ac23_review_queue_same_conf_name_asc():
    # AC23:第三鍵 — 同群同 conf 時 name 升序(y<z)
    items = [
        {"name": "z.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50}],
         "sidecar": {}},
        {"name": "y.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50}],
         "sidecar": {}},
    ]
    assert _names(filtersort.review_queue(items)) == ["y.png", "z.png"]


def test_ac24_review_queue_no_detection_not_pending():
    # AC24:無偵測者落入「非待審」群;有偵測且未審的 n 在前,m 無偵測不算待審
    items = [
        {"name": "m.png", "detections": [], "sidecar": {}},                                   # n_det=0 → 非待審
        {"name": "n.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.10}],
         "sidecar": {}},                                                                       # 待審
    ]
    assert _names(filtersort.review_queue(items)) == ["n.png", "m.png"]


# =====================================================================
# reviewed 語義對齊 tagging(複用語義、不 import 實作)
# =====================================================================

def test_ac25_reviewed_semantics_match_tagging():
    # AC25:sort_items 對 reviewed 的判定與 tagging 一致
    #   verdict 非 unset → reviewed;review_status done → reviewed;否則未 reviewed
    it_a = {"name": "a", "detections": [], "sidecar": {"verdict": "true_defect"}}
    it_b = {"name": "b", "detections": [], "sidecar": {"review_status": "done"}}
    it_c = {"name": "c", "detections": [], "sidecar": {"verdict": "unset", "review_status": "none"}}
    assert _names(filtersort.sort_items([it_a, it_b, it_c], "reviewed")) == ["c", "a", "b"]


def test_ac26_no_import_of_tagging_yolo_sidecar():
    # AC26:filtersort 模組不 import tagging / yolo / sidecar(證明複用語義非實作相依)
    src = inspect.getsource(filtersort)
    assert "import tagging" not in src
    assert "import yolo" not in src
    assert "import sidecar" not in src


# =====================================================================
# Metamorphic / 推導測試(設計 §5.2;額外健壯性,逼出實作 bug)
# =====================================================================

def test_meta1_name_sort_equiv_builtin_sorted():
    # §5.2-1:name 排序與內建 sorted 等價(name 唯一)
    items = _fix()
    assert _names(filtersort.sort_items(items, "name")) == sorted(it["name"] for it in items)


def test_meta2_reverse_is_primary_reversal_tie_stable():
    # §5.2-2:reverse 為主鍵反序、tie 穩定。
    #   用含 tie 的 n_det(b/c 同為 1)對照:reverse 前後 b/c 相對順序皆 b<c。
    items = _fix()
    asc = _names(filtersort.sort_items(items, "n_det"))
    desc = _names(filtersort.sort_items(items, "n_det", reverse=True))
    # b 在 c 前(tie-break 不隨 reverse 反轉),兩方向皆然
    assert asc.index("b.png") < asc.index("c.png")
    assert desc.index("b.png") < desc.index("c.png")
    # 以無 tie 的 time key 驗「主鍵序列」確為反序
    asc_time = _names(filtersort.sort_items(items, "time"))
    desc_time = _names(filtersort.sort_items(items, "time", reverse=True))
    assert desc_time == list(reversed(asc_time))


def test_meta3_sort_preserves_multiset():
    # §5.2-3:排序保留多重集合(不增刪 item),對任一合法 key/reverse 成立
    items = _fix()
    base = sorted(it["name"] for it in items)
    for key in filtersort.SORT_KEYS:
        for rev in (False, True):
            out = filtersort.sort_items(items, key, reverse=rev)
            assert sorted(it["name"] for it in out) == base


def test_meta4_sort_idempotent_same_key():
    # §5.2-4:冪等 — 同 key 再排不變(穩定排序對同 key 冪等),對任一合法 key 成立
    items = _fix()
    for key in filtersort.SORT_KEYS:
        once = filtersort.sort_items(items, key)
        twice = filtersort.sort_items(once, key)
        assert _names(twice) == _names(once)


def test_meta5_review_queue_is_total_order():
    # §5.2-5:review_queue 為全序 — name 唯一時輸出唯一且不增刪(len 不變)
    items = _fix()
    out = filtersort.review_queue(items)
    assert len(out) == len(items)
    assert sorted(it["name"] for it in out) == sorted(it["name"] for it in items)
