"""驗收測試:sidecar 模組(M2 / Tier B — 有 I/O,真實讀寫驗收)。

對應設計 3_Architect_Design/06_sidecar.md §6 的 AC1~AC34,逐條落成可執行 pytest;
邊界(§4)各自獨立測試;另含若干「設計未明列」的推導 / property 測試(見檔尾 H 段)。

跑法:
  cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_sidecar.py \
       -p no:cacheprovider --strict-markers -q

此時實作尚未寫;import 不到 sidecar 屬正常(實作由 /pg 寫到 5_PG_Develop/sidecar.py)。
conftest 已把 5_PG_Develop 加進 sys.path,故測試直接 `import sidecar`。
"""
import json
import os
import pathlib

import pytest

import sidecar


# 設計 §2.1 固定的 8 個欄位
EXPECTED_KEYS = {
    "review_status", "tags", "verdict", "comment",
    "bookmarked", "rois", "reviewer", "timestamp",
}


# =====================================================================
# A. 預設與 schema
# =====================================================================

def test_default_has_exactly_eight_keys():
    # AC1:default() 剛好八個欄位,不多不少
    d = sidecar.default()
    assert set(d.keys()) == EXPECTED_KEYS


def test_default_initial_values():
    # AC2:各欄位初值精確相等
    d = sidecar.default()
    assert d["review_status"] == "none"
    assert d["tags"] == []
    assert d["verdict"] == "unset"  # 未審哨兵,與 tagging VERDICTS[0] 一致
    assert d["comment"] == ""
    assert d["bookmarked"] is False
    assert d["rois"] == []
    assert d["reviewer"] == ""
    assert d["timestamp"] == ""


def test_default_returns_independent_objects():
    # AC3:每次回傳獨立物件,不共用可變預設
    a = sidecar.default()
    b = sidecar.default()
    a["tags"].append("x")
    assert b["tags"] == []


# =====================================================================
# B. 路徑推導 sidecar_path
# =====================================================================

def test_sidecar_path_same_dir_swap_ext(tmp_path):
    # AC4:同目錄、檔名主幹不變、副檔名換成 .cvr.json
    src = str(tmp_path / "a" / "img.png")
    expected = str(tmp_path / "a" / "img.cvr.json")
    assert sidecar.sidecar_path(src) == expected


def test_sidecar_path_uppercase_tif(tmp_path):
    # AC5:.TIF / 大寫副檔名同理(basename 比對)
    assert os.path.basename(sidecar.sidecar_path("X/scan001.TIF")) == "scan001.cvr.json"


def test_sidecar_path_no_extension_appends(tmp_path):
    # AC6:無副檔名時附加 .cvr.json
    assert os.path.basename(sidecar.sidecar_path("X/foo")) == "foo.cvr.json"


def test_sidecar_path_accepts_pathlib_and_returns_str(tmp_path):
    # AC7:接受 pathlib.Path,與 str 等價,且回傳型別為 str
    from_path = sidecar.sidecar_path(tmp_path / "img.png")
    from_str = sidecar.sidecar_path(str(tmp_path / "img.png"))
    assert from_path == from_str
    assert type(from_path) is str


# =====================================================================
# C. load 容錯(檔案不存在 / 壞檔)
# =====================================================================

def test_load_missing_returns_default_no_file_created(tmp_path):
    # AC8:不存在 → 回 default(),且不建立任何檔案
    img = tmp_path / "missing.png"
    assert sidecar.load(img) == sidecar.default()
    assert os.path.exists(sidecar.sidecar_path(img)) is False


def test_load_bad_json_returns_default(tmp_path):
    # AC9:壞 JSON → 不丟例外且 == default()
    img = tmp_path / "img.png"
    pathlib.Path(sidecar.sidecar_path(img)).write_text("{not json", encoding="utf-8")
    assert sidecar.load(img) == sidecar.default()


def test_load_empty_string_returns_default(tmp_path):
    # AC10:空字串檔 → == default()
    img = tmp_path / "img.png"
    pathlib.Path(sidecar.sidecar_path(img)).write_text("", encoding="utf-8")
    assert sidecar.load(img) == sidecar.default()


def test_load_partial_json_filled_with_defaults(tmp_path):
    # AC11:合法但缺欄位 → 補齊全 8 欄位,既有值保留
    img = tmp_path / "img.png"
    pathlib.Path(sidecar.sidecar_path(img)).write_text(
        json.dumps({"bookmarked": True}), encoding="utf-8")
    r = sidecar.load(img)
    assert set(r.keys()) == EXPECTED_KEYS
    assert r["bookmarked"] is True
    assert r["tags"] == []
    assert r["review_status"] == "none"


# =====================================================================
# D. save 真實寫入 + round-trip(I/O 模組強制)
# =====================================================================

def test_save_load_round_trip(tmp_path):
    # AC12:寫出再讀回,內容完全相等
    img = tmp_path / "img.png"
    d = sidecar.default()
    d = sidecar.set_status(d, "done")
    d = sidecar.add_tag(d, "scratch")
    d["reviewer"] = "alice"
    d["timestamp"] = "2026-06-22T10:00:00"
    sidecar.save(img, d)
    assert sidecar.load(img) == d


def test_save_lands_real_valid_json_on_disk(tmp_path):
    # AC13:真實落地、可被標準 json 解析的 UTF-8 檔
    img = tmp_path / "img.png"
    d = sidecar.default()
    d = sidecar.set_status(d, "done")
    sidecar.save(img, d)
    p = sidecar.sidecar_path(img)
    assert os.path.exists(p) is True
    with open(p, encoding="utf-8") as f:
        disk = json.load(f)
    assert disk["review_status"] == "done"


def test_save_does_not_touch_original_image(tmp_path):
    # AC14:不改原圖位元組
    img = tmp_path / "img.png"
    img.write_bytes(b"PNGDATA")
    sidecar.save(img, sidecar.default())
    assert img.read_bytes() == b"PNGDATA"


def test_save_atomic_no_tmp_residue(tmp_path):
    # AC15:原子寫入,成功後同目錄無 *.tmp 殘檔
    img = tmp_path / "img.png"
    d = sidecar.default()
    d = sidecar.set_status(d, "done")
    d = sidecar.add_tag(d, "scratch")
    sidecar.save(img, d)
    assert [f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []


def test_save_overwrites_existing(tmp_path):
    # AC16:連續兩次不同內容,load 回傳最後一次
    img = tmp_path / "img.png"
    a = sidecar.default(); a["verdict"] = "A"
    b = sidecar.default(); b["verdict"] = "B"
    sidecar.save(img, a)
    sidecar.save(img, b)
    assert sidecar.load(img)["verdict"] == "B"


def test_save_unicode_round_trip(tmp_path):
    # AC17:中文 / non-ASCII 字串 round-trip 不變
    img = tmp_path / "img.png"
    d = sidecar.default()
    d["comment"] = "刮傷-α"
    sidecar.save(img, d)
    assert sidecar.load(img)["comment"] == "刮傷-α"


# =====================================================================
# E. 變異函式(純函式 + copy-on-write)
# =====================================================================

def test_set_status_basic():
    # AC18:set_status 設定合法值
    assert sidecar.set_status(sidecar.default(), "need_review")["review_status"] == "need_review"


def test_set_status_invalid_raises():
    # AC19:非法 status 丟 ValueError
    with pytest.raises(ValueError):
        sidecar.set_status(sidecar.default(), "bogus")


def test_set_status_copy_on_write():
    # AC20:不就地改;回傳新物件
    base = sidecar.default()
    out = sidecar.set_status(base, "done")
    assert base["review_status"] == "none"
    assert out["review_status"] == "done"
    assert out is not base


def test_toggle_bookmark_flips():
    # AC21:toggle 一次 True,toggle 兩次回 False
    assert sidecar.toggle_bookmark(sidecar.default())["bookmarked"] is True
    twice = sidecar.toggle_bookmark(sidecar.toggle_bookmark(sidecar.default()))
    assert twice["bookmarked"] is False


def test_add_tag_basic():
    # AC22:add_tag 基本
    assert sidecar.add_tag(sidecar.default(), "x")["tags"] == ["x"]


def test_add_tag_dedup_keep_order():
    # AC23:去重且保序
    d = sidecar.default()
    d = sidecar.add_tag(d, "a")
    d = sidecar.add_tag(d, "b")
    d = sidecar.add_tag(d, "a")
    assert d["tags"] == ["a", "b"]


def test_add_tag_copy_on_write():
    # AC24:add_tag 不就地改
    base = sidecar.default()
    out = sidecar.add_tag(base, "a")
    assert base["tags"] == []
    assert out["tags"] == ["a"]


def test_remove_tag_basic():
    # AC25:remove_tag 移除既有
    d = sidecar.add_tag(sidecar.default(), "a")
    d = sidecar.add_tag(d, "b")
    assert sidecar.remove_tag(d, "a")["tags"] == ["b"]


def test_remove_tag_missing_is_noop():
    # AC26:移除不存在的 tag → no-op,不丟錯、不變
    d = sidecar.add_tag(sidecar.default(), "a")
    assert sidecar.remove_tag(d, "zzz")["tags"] == ["a"]


# =====================================================================
# F. ROI
# =====================================================================

def test_add_roi_defaults():
    # AC27:add_roi 預設值
    d = sidecar.add_roi(sidecar.default(), [10, 20, 30, 40])
    assert d["rois"] == [
        {"bbox": [10, 20, 30, 40], "label": "", "verdict": "unset", "comment": ""}
    ]


def test_add_roi_custom_fields():
    # AC28:add_roi 自訂欄位
    d = sidecar.add_roi(sidecar.default(), [1, 2, 3, 4],
                        label="L", verdict="bad", comment="c")
    assert d["rois"][0] == {
        "bbox": [1, 2, 3, 4], "label": "L", "verdict": "bad", "comment": "c"
    }


def test_add_roi_multiple_keep_order():
    # AC29:連加兩個 ROI 保序
    d = sidecar.add_roi(sidecar.default(), [0, 0, 1, 1])
    d = sidecar.add_roi(d, [5, 5, 2, 2])
    assert len(d["rois"]) == 2
    assert d["rois"][1]["bbox"] == [5, 5, 2, 2]


def test_add_roi_bbox_stored_as_list_len4():
    # AC30:tuple 輸入 → 存成 list 長度 4
    d = sidecar.add_roi(sidecar.default(), (1, 2, 3, 4))
    assert d["rois"][0]["bbox"] == [1, 2, 3, 4]
    assert type(d["rois"][0]["bbox"]) is list


def test_add_roi_copy_on_write():
    # AC31:add_roi 不就地改
    base = sidecar.default()
    out = sidecar.add_roi(base, [0, 0, 1, 1])
    assert base["rois"] == []
    assert len(out["rois"]) == 1


def test_add_roi_round_trip(tmp_path):
    # AC32:ROI 經磁碟 round-trip 不變
    img = tmp_path / "img.png"
    d = sidecar.add_roi(sidecar.default(), [10, 20, 30, 40], label="L")
    sidecar.save(img, d)
    assert sidecar.load(img)["rois"] == d["rois"]


# =====================================================================
# G. 組合行為(端到端,模擬一輪判讀)
# =====================================================================

def test_full_review_round(tmp_path):
    # AC33:完整一輪判讀
    img = tmp_path / "wafer.tif"
    d = sidecar.load(img)                       # 不存在 → default
    d = sidecar.set_status(d, "need_review")
    d = sidecar.toggle_bookmark(d)
    d = sidecar.add_tag(d, "defect")
    d = sidecar.add_roi(d, [100, 100, 50, 50], label="crack", verdict="bad")
    d["reviewer"] = "bob"
    d["timestamp"] = "2026-06-22T12:00:00"
    sidecar.save(img, d)
    r = sidecar.load(img)
    assert r["review_status"] == "need_review"
    assert r["bookmarked"] is True
    assert r["tags"] == ["defect"]
    assert r["reviewer"] == "bob"
    assert r["timestamp"] == "2026-06-22T12:00:00"
    assert r["rois"] == [
        {"bbox": [100, 100, 50, 50], "label": "crack", "verdict": "bad", "comment": ""}
    ]


def test_no_hidden_clock():
    # AC34:變異函式不偷寫時間戳,結果與呼叫時刻無關
    d = sidecar.add_tag(sidecar.set_status(sidecar.default(), "done"), "t")
    assert d["timestamp"] == ""


# =====================================================================
# H. 推導 / property 測試(設計未明列,從契約推導的硬約束)
# =====================================================================

def test_all_three_legal_statuses_accepted():
    # 推導(§2.1 status 列舉):三個合法值都必須被接受,逐一驗證
    for s in ("none", "need_review", "done"):
        assert sidecar.set_status(sidecar.default(), s)["review_status"] == s


def test_set_status_invalid_does_not_mutate_input():
    # 推導(§2.3 copy-on-write + §4 及早失敗):set_status 丟錯時,
    # 輸入 data 不得被就地破壞(及早失敗也不能留下半改狀態)
    base = sidecar.default()
    with pytest.raises(ValueError):
        sidecar.set_status(base, "bogus")
    assert base["review_status"] == "none"


def test_mutators_preserve_full_schema():
    # 推導(§2.1 形狀穩定 + §2.3 copy-on-write):任一變異函式回傳的 dict
    # 都應維持完整 8 欄位 schema(不增刪欄位),確保結果可直接餵回下一個變異或 save
    base = sidecar.default()
    for out in (
        sidecar.set_status(base, "done"),
        sidecar.toggle_bookmark(base),
        sidecar.add_tag(base, "a"),
        sidecar.remove_tag(sidecar.add_tag(base, "a"), "a"),
        sidecar.add_roi(base, [0, 0, 1, 1]),
    ):
        assert set(out.keys()) == EXPECTED_KEYS


def test_mutators_do_not_alias_input_mutable_fields():
    # 推導(§2.3 「不得就地修改傳入的 data」的深層含義):copy-on-write 必須是
    # 真複製,回傳 dict 的可變欄位不能與輸入共用同一物件(否則後續就地改會回滲)。
    base = sidecar.default()
    out_tag = sidecar.add_tag(base, "a")
    assert out_tag["tags"] is not base["tags"]
    out_roi = sidecar.add_roi(base, [0, 0, 1, 1])
    assert out_roi["rois"] is not base["rois"]


def test_load_after_save_is_idempotent(tmp_path):
    # 推導(§3 讀/寫路徑的閉合性):save 後 load 的結果再次 save+load 應穩定不變
    # (round-trip 為冪等;序列化/反序列化不引入飄移)。
    img = tmp_path / "img.png"
    d = sidecar.add_roi(
        sidecar.add_tag(sidecar.set_status(sidecar.default(), "done"), "scratch"),
        [3, 4, 5, 6], label="L", verdict="bad", comment="刮傷",
    )
    d["reviewer"] = "alice"
    d["timestamp"] = "2026-06-22T10:00:00"
    sidecar.save(img, d)
    once = sidecar.load(img)
    sidecar.save(img, once)
    twice = sidecar.load(img)
    assert once == twice == d


def test_remove_tag_copy_on_write():
    # 推導(§2.3 對 remove_tag 同樣適用 copy-on-write,設計 AC 只測了
    # add_tag/set_status/add_roi 的不就地改,remove_tag 漏列):移除既有 tag
    # 不得就地改輸入。
    base = sidecar.add_tag(sidecar.default(), "a")
    snapshot = list(base["tags"])
    out = sidecar.remove_tag(base, "a")
    assert base["tags"] == snapshot      # 輸入未被就地改
    assert out["tags"] == []
    assert out is not base
