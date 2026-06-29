"""tagging 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/05_tagging.md(AC1..AC35 + §4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import tagging`。此時實作尚未生成,import 不到屬正常(非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_tagging.py -p no:cacheprovider --strict-markers -q
"""
import copy

import pytest

import tagging


# =====================================================================
# 常數契約
# =====================================================================

def test_ac1_builtin_tags_exact_order_and_len():
    # AC1:BUILTIN_TAGS 內容與順序逐字相等,且長度為 11
    assert tagging.BUILTIN_TAGS == [
        "Need Review", "Need Discuss", "Potential Miss", "False Alarm",
        "True Defect", "Reflection", "Low Confidence", "New Pattern",
        "Golden Case", "Need Labeling", "Need Retrain",
    ]
    assert len(tagging.BUILTIN_TAGS) == 11


def test_ac2_verdicts_exact_and_first_is_unset():
    # AC2:VERDICTS 逐字相等,且 VERDICTS[0] == "unset"
    assert tagging.VERDICTS == ["unset", "true_defect", "false_alarm", "reflection"]
    assert tagging.VERDICTS[0] == "unset"


# =====================================================================
# is_reviewed
# =====================================================================

def test_ac3_is_reviewed_unset_none_false():
    # AC3:verdict=unset 且 review_status=none → False
    assert tagging.is_reviewed({"verdict": "unset", "review_status": "none"}) is False


def test_ac4_is_reviewed_verdict_not_unset_true():
    # AC4:verdict 非 unset → True
    assert tagging.is_reviewed({"verdict": "true_defect", "review_status": "none"}) is True


def test_ac5_is_reviewed_status_done_true():
    # AC5:review_status==done → True
    assert tagging.is_reviewed({"verdict": "unset", "review_status": "done"}) is True


def test_ac6_is_reviewed_empty_false():
    # AC6:全缺鍵 → 視同 unset/none → False
    assert tagging.is_reviewed({}) is False


def test_ac7_is_reviewed_either_condition_true():
    # AC7:任一條件成立即 True(只給 verdict / 只給 review_status)
    assert tagging.is_reviewed({"verdict": "false_alarm"}) is True
    assert tagging.is_reviewed({"review_status": "done"}) is True


# =====================================================================
# matches — 空 / 預設
# =====================================================================

def test_ac8_matches_empty_sidecar_empty_query_true():
    # AC8:空 sidecar、空 query → True
    assert tagging.matches({}, {}) is True


def test_ac9_matches_empty_query_always_true():
    # AC9:空 query 一律通過
    assert tagging.matches({"comment": "x"}, {}) is True


# =====================================================================
# matches — tags(any / all / 空)
# =====================================================================

def test_ac10_tags_any_intersection_true():
    # AC10:預設 any,含其一 → True
    assert tagging.matches(
        {"tags": ["True Defect", "Need Review"]}, {"tags": ["Need Review"]}) is True


def test_ac11_tags_any_no_intersection_false():
    # AC11:any 但無交集 → False
    assert tagging.matches(
        {"tags": ["True Defect"]}, {"tags": ["Need Review", "Need Retrain"]}) is False


def test_ac12_tags_all_full_subset_true():
    # AC12:mode=all 全含 → True
    assert tagging.matches(
        {"tags": ["True Defect", "Need Review"]},
        {"tags": ["True Defect", "Need Review"], "mode": "all"}) is True


def test_ac13_tags_all_missing_one_false():
    # AC13:mode=all 缺一 → False
    assert tagging.matches(
        {"tags": ["True Defect"]},
        {"tags": ["True Defect", "Need Review"], "mode": "all"}) is False


def test_ac14_empty_tags_condition_ignored():
    # AC14:query tags=[] 視為不參與(any 與 all 皆然)→ True
    assert tagging.matches({"tags": ["True Defect"]}, {"tags": []}) is True
    assert tagging.matches({"tags": []}, {"tags": [], "mode": "all"}) is True


def test_ac15_sidecar_missing_tags_any_false():
    # AC15:sidecar 無 tags 視同 [],any 無交集 → False
    assert tagging.matches({}, {"tags": ["Need Review"]}) is False


# =====================================================================
# matches — verdict / review_status
# =====================================================================

def test_ac16_verdict_exact_match():
    # AC16:verdict 精確相等
    assert tagging.matches({"verdict": "false_alarm"}, {"verdict": "false_alarm"}) is True
    assert tagging.matches({"verdict": "true_defect"}, {"verdict": "false_alarm"}) is False


def test_ac17_verdict_missing_defaults_unset():
    # AC17:缺鍵視同 "unset",精確相等
    assert tagging.matches({}, {"verdict": "unset"}) is True


def test_ac18_review_status_exact_match():
    # AC18:review_status 精確相等
    assert tagging.matches({"review_status": "done"}, {"review_status": "done"}) is True
    assert tagging.matches({"review_status": "none"}, {"review_status": "done"}) is False


# =====================================================================
# matches — reviewed(bool,可查未審)
# =====================================================================

def test_ac19_reviewed_true_hits_reviewed():
    # AC19:reviewed=True 命中已審
    assert tagging.matches({"verdict": "true_defect"}, {"reviewed": True}) is True


def test_ac20_reviewed_false_hits_unreviewed():
    # AC20:reviewed=False 命中未審
    assert tagging.matches(
        {"verdict": "unset", "review_status": "none"}, {"reviewed": False}) is True


def test_ac21_reviewed_false_misses_reviewed():
    # AC21:已審但要求未審 → False
    assert tagging.matches({"verdict": "true_defect"}, {"reviewed": False}) is False


# =====================================================================
# matches — bookmarked
# =====================================================================

def test_ac22_bookmarked_true():
    # AC22:bookmarked=True 命中;缺鍵視同 False 故不命中
    assert tagging.matches({"bookmarked": True}, {"bookmarked": True}) is True
    assert tagging.matches({}, {"bookmarked": True}) is False


def test_ac23_bookmarked_false():
    # AC23:bookmarked=False 相等命中
    assert tagging.matches({"bookmarked": False}, {"bookmarked": False}) is True


# =====================================================================
# matches — text(大小寫不敏感子字串)
# =====================================================================

def test_ac24_text_case_insensitive_substring():
    # AC24:大小寫不敏感子字串命中
    assert tagging.matches({"comment": "Scratch on edge"}, {"text": "scratch"}) is True


def test_ac25_text_substring_absent():
    # AC25:無此子字串 → False
    assert tagging.matches({"comment": "Scratch on edge"}, {"text": "dent"}) is False


def test_ac26_text_empty_passes_missing_comment_fails():
    # AC26:空 text 通過;缺 comment 視同 "" 故任意非空 text 不命中
    assert tagging.matches({"comment": "anything"}, {"text": ""}) is True
    assert tagging.matches({}, {"text": "x"}) is False


# =====================================================================
# matches — 多條件 AND
# =====================================================================

def test_ac27_multi_condition_all_match_true():
    # AC27:tags + verdict + bookmarked 三條件全中 → True
    assert tagging.matches(
        {"tags": ["True Defect"], "verdict": "true_defect", "bookmarked": True},
        {"tags": ["True Defect"], "verdict": "true_defect", "bookmarked": True}) is True


def test_ac28_multi_condition_one_fails_false():
    # AC28:verdict 不符 → AND 失敗 → False
    assert tagging.matches(
        {"tags": ["True Defect"], "verdict": "false_alarm", "bookmarked": True},
        {"tags": ["True Defect"], "verdict": "true_defect", "bookmarked": True}) is False


# =====================================================================
# filter_records — 保序 / 子集 / 不 mutate
# =====================================================================

def _items():
    return [
        ("a", {"tags": ["True Defect"]}),
        ("b", {"tags": ["False Alarm"]}),
        ("c", {"tags": ["True Defect", "Need Review"]}),
    ]


def test_ac29_filter_returns_records_in_order():
    # AC29:只回 record、保序
    assert tagging.filter_records(_items(), {"tags": ["True Defect"]}) == ["a", "c"]


def test_ac30_filter_empty_query_returns_all():
    # AC30:空 query 全回、原順序
    assert tagging.filter_records(_items(), {}) == ["a", "b", "c"]


def test_ac31_filter_empty_input_empty_output():
    # AC31:空輸入 → 空輸出
    assert tagging.filter_records([], {"tags": ["True Defect"]}) == []


def test_ac32_filter_does_not_mutate_and_subset_length():
    # AC32:不 mutate 輸入(deepcopy 前後相等),且回傳長度 <= 輸入長度
    items = _items()
    before = copy.deepcopy(items)
    out = tagging.filter_records(items, {"text": "x"})
    assert items == before
    assert len(out) <= len(items)


def test_ac33_filter_reviewed_semantics_consistent():
    # AC33:filter 與 matches 語義一致,reviewed 條件貫穿
    assert tagging.filter_records(
        [("r", {"verdict": "true_defect", "review_status": "none"})],
        {"reviewed": True}) == ["r"]


# =====================================================================
# 邊界 / 不拋例外
# =====================================================================

def test_ac34_missing_keys_no_exception_returns_false():
    # AC34:全缺鍵 sidecar 上多條件 query 不拋例外,且回 False(tags any 無交集)
    result = tagging.matches(
        {},
        {"tags": ["Need Review"], "verdict": "unset", "review_status": "none",
         "reviewed": False, "bookmarked": False, "text": ""})
    assert result is False


def test_ac35_custom_non_builtin_tag_allowed():
    # AC35:允許非 BUILTIN 自訂標籤參與比對,不校驗
    assert tagging.matches(
        {"tags": ["Custom Tag X"]}, {"tags": ["Custom Tag X"]}) is True


# =====================================================================
# 推導 / property 測試(設計未明列;由契約推導)
# =====================================================================

def test_property_empty_query_is_filter_identity_on_records():
    # 推導(§4a + §3.3):空 query 下 filter_records 等價於投影出所有 record(保序),
    # 對任意 (record, sidecar) 序列皆成立 —— 比 AC30 的單例更強的不變式。
    items = [
        (1, {"verdict": "true_defect"}),
        (2, {}),
        (3, {"tags": ["X"], "bookmarked": True}),
        (4, {"comment": "hello"}),
    ]
    expected = [r for r, _ in items]
    assert tagging.filter_records(items, {}) == expected


def test_property_default_mode_is_any():
    # 推導(§3.2.1):未給 mode 與顯式 mode="any" 必須等價(預設值即 any)。
    sidecar = {"tags": ["True Defect", "Need Review"]}
    q_default = {"tags": ["Need Review", "Need Retrain"]}
    q_explicit = {"tags": ["Need Review", "Need Retrain"], "mode": "any"}
    assert tagging.matches(sidecar, q_default) == tagging.matches(sidecar, q_explicit)
    # 兩者皆應為 True(any 有交集)
    assert tagging.matches(sidecar, q_default) is True


def test_property_duplicate_tags_deduped_no_effect():
    # 推導(§4i):sidecar.tags 內重複值經 set() 去重,不影響任何比對結果。
    base = {"tags": ["True Defect", "Need Review"]}
    dup = {"tags": ["True Defect", "True Defect", "Need Review", "Need Review"]}
    for q in (
        {"tags": ["True Defect"]},
        {"tags": ["True Defect", "Need Review"], "mode": "all"},
        {"tags": ["False Alarm"]},
    ):
        assert tagging.matches(base, q) == tagging.matches(dup, q)


def test_property_filter_equiv_listcomp_of_matches(tmp_path):
    # 推導(§3.3 不變式):filter_records 必等價於「對每筆套 matches 的保序篩選 + 投影 record」。
    # 用 tmp_path 寫一個無關緊要的暫存檔以符合「需要檔案時用 tmp_path」規範(此處僅示意取用)。
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    assert marker.read_text(encoding="utf-8") == "ok"

    items = [
        ("a", {"tags": ["True Defect"], "verdict": "true_defect"}),
        ("b", {"tags": ["False Alarm"], "verdict": "false_alarm"}),
        ("c", {"tags": ["True Defect", "Need Review"], "bookmarked": True}),
        ("d", {}),
    ]
    query = {"tags": ["True Defect"]}
    expected = [r for (r, sc) in items if tagging.matches(sc, query)]
    assert tagging.filter_records(items, query) == expected


def test_property_text_normalizes_both_sides():
    # 推導(§4f):text 比對對「query 與 comment 兩側」皆 .lower() 正規化,
    # 故大寫 query 命中小寫 comment(僅 AC24 驗了小寫 query / 混合 comment)。
    assert tagging.matches({"comment": "scratch on edge"}, {"text": "SCRATCH"}) is True


def test_property_invalid_verdict_makes_reviewed_true():
    # 推導(§4e):非法 verdict(不在 VERDICTS 但 != "unset")不校驗、不拋例外,
    # 因 != "unset" 故 is_reviewed 回 True。
    assert tagging.is_reviewed({"verdict": "garbage_value"}) is True
