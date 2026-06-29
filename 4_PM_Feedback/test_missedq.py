"""missedq 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/13_missedq.md(AC1..AC27 + §4 邊界 + §5.2 metamorphic)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import missedq`。此時實作尚未生成,import 不到屬正常(非紅,為 test-first);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

心智模型:missedq 是 filtersort.review_queue 的「理由驅動版」——用一組釘死規則只挑
「需要人再看一眼」的 item(漏檢 / 誤報 / 低信心 / 未審有框),每筆附理由碼並依嚴重度排序。
兩者互不 import、各自獨立。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_missedq.py -p no:cacheprovider --strict-markers -q
"""
import copy
import inspect

import pytest

import missedq


# =====================================================================
# 共用夾具 FIX(設計 §5 原樣建立;name 唯一,便於釘死確切順序)
#   派生量速查(conf_low=0.3, conf_high=0.7):
#     name       n_det  max_conf  verdict       reviewed  → flags                      priority
#     miss.png   0      0.00      true_defect   True      → ["missed_detection"]        0
#     false.png  1      0.95      false_alarm   True      → ["false_alarm"]             1
#     low.png    1      0.20      true_defect   True      → ["low_confidence"]          2
#     unrev.png  1      0.80      unset         False     → ["unreviewed_with_det"]     3
#     clean.png  1      0.80      true_defect   True      → []                          —
#   佇列唯一順序(§5.1 推導表):["miss.png","false.png","low.png","unrev.png"]
# =====================================================================

def _fix():
    """每次回新的一份 FIX,避免測試間互相污染。"""
    return [
        # MISS: 人判 true_defect 但 0 框 → missed_detection(priority 0)
        {"name": "miss.png", "detections": [],
         "sidecar": {"verdict": "true_defect", "review_status": "done"}},
        # FALSE: 人判 false_alarm + 有 0.95(>=0.7)框 → false_alarm(priority 1)
        {"name": "false.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.95}],
         "sidecar": {"verdict": "false_alarm", "review_status": "done"}},
        # LOW: 有框、max_conf 0.20(<0.3)、已審 → low_confidence(priority 2)
        {"name": "low.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.20}],
         "sidecar": {"verdict": "true_defect", "review_status": "done"}},
        # UNREV: 有框 0.80、未審(verdict unset / review none)→ unreviewed_with_det(priority 3)
        {"name": "unrev.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.80}],
         "sidecar": {"verdict": "unset", "review_status": "none"}},
        # CLEAN: 有框 0.80、已審(true_defect)、conf 不低、非 false/miss → 無 flag,不進佇列
        {"name": "clean.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.80}],
         "sidecar": {"verdict": "true_defect", "review_status": "done"}},
    ]


def _names(entries):
    return [e["name"] for e in entries]


# =====================================================================
# 常數契約
# =====================================================================

def test_ac1_reasons_exact_order_and_len():
    # AC1:REASONS 內容與順序逐字相等,且長度為 4
    assert missedq.REASONS == [
        "missed_detection", "false_alarm", "low_confidence", "unreviewed_with_det"]
    assert len(missedq.REASONS) == 4


def test_ac2_reason_constants_match_reasons():
    # AC2:4 個 REASON_* 常數逐字等於 REASONS 對應元素
    assert missedq.REASON_MISSED == "missed_detection"
    assert missedq.REASON_FALSE == "false_alarm"
    assert missedq.REASON_LOWCONF == "low_confidence"
    assert missedq.REASON_UNREVIEWED == "unreviewed_with_det"
    assert [missedq.REASON_MISSED, missedq.REASON_FALSE,
            missedq.REASON_LOWCONF, missedq.REASON_UNREVIEWED] == missedq.REASONS


# =====================================================================
# flags_for — 單一規則命中(各規則隔離,確切 flags)
# =====================================================================

def test_ac3_flags_missed_detection():
    # AC3(漏檢):true_defect + 0 框 → ["missed_detection"]
    assert missedq.flags_for(_fix()[0]) == ["missed_detection"]


def test_ac4_flags_false_alarm():
    # AC4(誤報):false_alarm + conf 0.95>=0.7 → ["false_alarm"]
    assert missedq.flags_for(_fix()[1]) == ["false_alarm"]


def test_ac5_flags_low_confidence():
    # AC5(低信心):有框 + conf 0.20<0.3;已審故無 unreviewed → ["low_confidence"]
    assert missedq.flags_for(_fix()[2]) == ["low_confidence"]


def test_ac6_flags_unreviewed_with_det():
    # AC6(未審有框):有框 0.80 + 未審 → ["unreviewed_with_det"]
    assert missedq.flags_for(_fix()[3]) == ["unreviewed_with_det"]


def test_ac7_flags_clean_empty():
    # AC7(乾淨):有框、已審、conf 不低、verdict 非 false/miss 觸發條件 → []
    assert missedq.flags_for(_fix()[4]) == []


# =====================================================================
# flags_for — 否定/不觸發(規則邊界)
# =====================================================================

def test_ac8_missed_requires_zero_det():
    # AC8(漏檢需 0 框):true_defect 但有 1 框 → 不算漏檢;conf 0.5 不低、已審 → []
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.5}],
            "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    assert missedq.flags_for(item) == []


def test_ac9_low_confidence_strict_less_than_boundary():
    # AC9(low_confidence 嚴格 `<`,等於不觸發):max_conf 0.30 == conf_low 0.3 → 不算低信心 → []
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.30}],
            "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    assert missedq.flags_for(item) == []


def test_ac10_false_alarm_ge_boundary():
    # AC10(false_alarm `>=` 邊界,等於觸發):max_conf 0.70 == conf_high 0.7 → 算高信心 → ["false_alarm"]
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.70}],
            "sidecar": {"verdict": "false_alarm", "review_status": "done"}}
    assert missedq.flags_for(item) == ["false_alarm"]


def test_ac11_false_alarm_requires_high_conf():
    # AC11(false_alarm 需高信心):false_alarm 但 max_conf 0.40<0.7 → 不觸發 false_alarm;
    #   0.40>=conf_low 0.3 故非低信心;已審 → []
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.40}],
            "sidecar": {"verdict": "false_alarm", "review_status": "done"}}
    assert missedq.flags_for(item) == []


# =====================================================================
# flags_for — 多碼共存(順序 = REASONS,priority 由最小索引決定)
# =====================================================================

def test_ac12_multi_low_and_unreviewed_order():
    # AC12(低信心 + 未審同時命中,順序釘死):有框 + conf 0.10<0.3 + 未審
    #   → ["low_confidence","unreviewed_with_det"](low(2) 在 unrev(3) 前)
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.10}],
            "sidecar": {"verdict": "unset", "review_status": "none"}}
    assert missedq.flags_for(item) == ["low_confidence", "unreviewed_with_det"]


def test_ac13_reviewed_does_not_block_low_confidence():
    # AC13(已審不擋低信心):已審故無 unreviewed,但 conf 0.10<0.3 仍 low_confidence
    #   → 證明 §4j「已審不代表低信心框不需注意」
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.10}],
            "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    assert missedq.flags_for(item) == ["low_confidence"]


# =====================================================================
# flags_for — 缺鍵/預設(不拋例外)
# =====================================================================

def test_ac14_missing_sidecar_and_detections_no_error():
    # AC14(全缺 sidecar/detections):缺 detections→n_det 0、max_conf 0.0;
    #   缺 sidecar→verdict unset、reviewed False;四條皆不成立,不拋 KeyError → []
    assert missedq.flags_for({"name": "x"}) == []


def test_ac15_empty_detections_true_defect_is_missed():
    # AC15(空 detections + true_defect → 漏檢):缺 review_status 不影響;
    #   n_det 0 + true_defect → 漏檢;n_det 0 故 low/unrev 不成立 → ["missed_detection"]
    item = {"name": "x", "detections": [], "sidecar": {"verdict": "true_defect"}}
    assert missedq.flags_for(item) == ["missed_detection"]


# =====================================================================
# flags_for — 自訂門檻
# =====================================================================

def test_ac16_custom_conf_low_triggers_low_confidence():
    # AC16:自訂 conf_low=0.6 → max_conf 0.50<0.6 → 低信心;預設 0.3 時本不觸發
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50}],
            "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    assert missedq.flags_for(item, conf_low=0.6) == ["low_confidence"]


def test_ac17_custom_conf_high_triggers_false_alarm():
    # AC17:自訂 conf_high=0.4 → max_conf 0.50>=0.4 → false_alarm;預設 0.7 時本不觸發
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50}],
            "sidecar": {"verdict": "false_alarm", "review_status": "done"}}
    assert missedq.flags_for(item, conf_high=0.4) == ["false_alarm"]


# =====================================================================
# missed_queue — 輸出形狀
# =====================================================================

def test_ac18_queue_entry_keys_exactly_three():
    # AC18(每筆恰三鍵):每筆 set(keys) == {"name","reasons","priority"}(不多不少)
    q = missedq.missed_queue(_fix())
    assert all(set(e.keys()) == {"name", "reasons", "priority"} for e in q)


# =====================================================================
# missed_queue — 釘死順序(嚴重度 priority 升序,tie name 升序)
# =====================================================================

def test_ac19_queue_order_by_priority():
    # AC19(主排序 = priority):clean.png 無 flag 被排除;其餘依 priority 0,1,2,3 升序
    #   → ["miss.png","false.png","low.png","unrev.png"](§5.1 唯一真相)
    assert _names(missedq.missed_queue(_fix())) == \
        ["miss.png", "false.png", "low.png", "unrev.png"]


def test_ac20_queue_full_dicts_exact():
    # AC20(每筆 reasons/priority 正確):完整 dict 逐字相等
    assert missedq.missed_queue(_fix()) == [
        {"name": "miss.png", "reasons": ["missed_detection"], "priority": 0},
        {"name": "false.png", "reasons": ["false_alarm"], "priority": 1},
        {"name": "low.png", "reasons": ["low_confidence"], "priority": 2},
        {"name": "unrev.png", "reasons": ["unreviewed_with_det"], "priority": 3},
    ]


# =====================================================================
# missed_queue — priority tie-break(同 priority → name 升序)
# =====================================================================

def test_ac21_queue_tiebreak_name_asc_same_priority():
    # AC21:兩筆皆 priority 0(漏檢)→ name 升序 a<z → ["a.png","z.png"]
    items = [
        {"name": "z.png", "detections": [], "sidecar": {"verdict": "true_defect"}},
        {"name": "a.png", "detections": [], "sidecar": {"verdict": "true_defect"}},
    ]
    assert _names(missedq.missed_queue(items)) == ["a.png", "z.png"]


# =====================================================================
# missed_queue — priority 取最嚴重(多碼 item 的 priority 隔離驗證)
# =====================================================================

def test_ac22_queue_priority_is_most_severe_index():
    # AC22:multi 有兩碼 [low_confidence, unreviewed_with_det] → priority=min(2,3)=2;
    #   miss [missed_detection] priority 0 排前
    items = [
        {"name": "multi.png",
         "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.10}],
         "sidecar": {"verdict": "unset", "review_status": "none"}},
        {"name": "miss.png", "detections": [],
         "sidecar": {"verdict": "true_defect"}},
    ]
    assert missedq.missed_queue(items) == [
        {"name": "miss.png", "reasons": ["missed_detection"], "priority": 0},
        {"name": "multi.png",
         "reasons": ["low_confidence", "unreviewed_with_det"], "priority": 2},
    ]


# =====================================================================
# reviewed 語義對齊 tagging(複用語義、不 import 實作)
# =====================================================================

def test_ac23_no_import_of_tagging_yolo_sidecar_filtersort():
    # AC23:missedq 不 import tagging / yolo / sidecar / filtersort
    #   (證明複用的是「語義」非「實作相依」)
    src = inspect.getsource(missedq)
    assert "import tagging" not in src
    assert "import yolo" not in src
    assert "import sidecar" not in src
    assert "import filtersort" not in src


def test_ac24_reviewed_semantics_match_tagging():
    # AC24:reviewed 判定與 tagging 一致
    #   verdict 非 unset → reviewed → 無 unreviewed
    it_verdict = {"name": "x",
                  "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.8}],
                  "sidecar": {"verdict": "true_defect", "review_status": "none"}}
    assert missedq.flags_for(it_verdict) == []
    #   review_status done → reviewed → 無 unreviewed
    it_done = {"name": "x",
               "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.8}],
               "sidecar": {"review_status": "done"}}
    assert missedq.flags_for(it_done) == []
    #   兩條件皆否 → 未審 → unreviewed_with_det
    it_unrev = {"name": "x",
                "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.8}],
                "sidecar": {"verdict": "unset", "review_status": "none"}}
    assert missedq.flags_for(it_unrev) == ["unreviewed_with_det"]


# =====================================================================
# missed_queue — 空輸入 / 不 mutate
# =====================================================================

def test_ac25_empty_and_clean_only_produce_empty_queue():
    # AC25:空輸入 → 空輸出;只給乾淨 item → 空佇列(證明乾淨 item 不進佇列)
    assert missedq.missed_queue([]) == []
    assert missedq.missed_queue([_fix()[4]]) == []


def test_ac26_queue_does_not_mutate_input():
    # AC26:輸入(含各 item 之 sidecar/detections 子物件)呼叫後內容不變
    fix = _fix()
    before = copy.deepcopy(fix)
    _ = missedq.missed_queue(fix)
    assert fix == before


def test_ac27_queue_entry_is_new_object_not_item_ref():
    # AC27:輸出 dict 是新建,不是原 item 的參考
    fix = _fix()
    q = missedq.missed_queue([fix[0]])
    assert q[0] is not fix[0]


# =====================================================================
# Metamorphic / 推導測試(設計 §5.2;額外健壯性,逼出實作 bug)
# =====================================================================

def test_meta1_clean_item_never_enters_queue():
    # §5.2-1:乾淨 item 不進佇列(隔離,clean.png 的一般化)。
    #   verdict in {true_defect, reflection}、有框、max_conf>=conf_low、reviewed True → flags []。
    for verdict in ("true_defect", "reflection"):
        item = {"name": "c.png",
                "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50}],
                "sidecar": {"verdict": verdict, "review_status": "done"}}
        assert missedq.flags_for(item) == []
        assert missedq.missed_queue([item]) == []


def test_meta2_queue_subset_of_input_count_matches():
    # §5.2-2:佇列 ⊆ 輸入(只篩不增)。每筆 name 來自輸入;
    #   len(queue) == sum(1 for it if flags_for(it)) — 進佇列數 = 有 ≥1 flag 的 item 數。
    items = _fix()
    q = missedq.missed_queue(items)
    in_names = {it["name"] for it in items}
    assert all(e["name"] in in_names for e in q)
    expected_count = sum(1 for it in items if missedq.flags_for(it))
    assert len(q) == expected_count


def test_meta3_priority_equals_min_reason_index_and_in_range():
    # §5.2-3:priority 隔離 —— 每筆 priority == min(REASONS.index(r) for r in reasons),
    #   且 0 <= priority <= 3。
    q = missedq.missed_queue(_fix())
    for e in q:
        assert e["priority"] == min(missedq.REASONS.index(r) for r in e["reasons"])
        assert 0 <= e["priority"] <= 3


def test_meta3b_adding_more_severe_flag_lowers_priority():
    # §5.2-3(對照):給 low.png 改成 0 框 true_defect 使其得 missed_detection,
    #   priority 由 2(low_confidence)嚴格變小到 0,排序位置不後移。
    before = {"name": "low.png",
              "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.20}],
              "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    after = {"name": "low.png", "detections": [],
             "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    p_before = missedq.missed_queue([before])[0]["priority"]
    p_after = missedq.missed_queue([after])[0]["priority"]
    assert p_before == 2
    assert p_after == 0
    assert p_after < p_before


def test_meta4_flags_always_subsequence_of_reasons():
    # §5.2-4:flags 順序恆為 REASONS 子序列 —— [r for r in REASONS if r in flags] == flags。
    for item in _fix():
        flags = missedq.flags_for(item)
        assert [r for r in missedq.REASONS if r in flags] == flags
    # 並以多碼 item 直接施壓(low + unrev)
    multi = {"name": "x",
             "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.10}],
             "sidecar": {"verdict": "unset", "review_status": "none"}}
    flags = missedq.flags_for(multi)
    assert [r for r in missedq.REASONS if r in flags] == flags


def test_meta5_queue_deterministic_and_matches_hand_sort():
    # §5.2-5:priority 排序穩定可重現 —— 再跑一次完全相等;
    #   且輸出順序與「依 (priority,name) 手算」一致(無隨機性)。
    items = _fix()
    q1 = missedq.missed_queue(items)
    q2 = missedq.missed_queue(items)
    assert q1 == q2
    hand = sorted(q1, key=lambda e: (e["priority"], e["name"]))
    assert _names(q1) == _names(hand)


def test_meta6_low_confidence_threshold_monotonic():
    # §5.2-6:門檻單調性(low_confidence)—— 固定一個有框、未觸發其他碼的 item,
    #   提高 conf_low 跨過其 max_conf 後,low_confidence 從不命中變命中(方向不反)。
    item = {"name": "x",
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.50}],
            "sidecar": {"verdict": "true_defect", "review_status": "done"}}
    # conf_low 0.4 < max_conf 0.50 → 不命中
    assert "low_confidence" not in missedq.flags_for(item, conf_low=0.4)
    # 提高 conf_low 至 0.6 > max_conf 0.50 → 命中
    assert "low_confidence" in missedq.flags_for(item, conf_low=0.6)
