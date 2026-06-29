"""casepkg 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/11_casepkg.md(AC1..AC30 + §3 I/O 契約 + §5 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import casepkg`。此時實作尚未生成,import 不到屬正常(test-first,非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_casepkg.py -p no:cacheprovider --strict-markers -q

⚠ 一致性註記:IT1 的 comment "刮傷,邊緣" 與 classes "scratch,dent" 內的逗號
皆為 ASCII 逗號 U+002C(可用本檔最底的 test_invariant_ascii_comma_in_fixtures
自我稽核),以觸發 csv.QUOTE_MINIMAL 加引號(AC11/AC13/AC27)。
"""
import copy
import csv
import io
import json
import os

import pytest

import casepkg


# =====================================================================
# 共用測試夾具(設計 §6 引用 IT1/IT2)。
# 重要:comment / classes 內逗號為 ASCII U+002C(見檔頭與底部稽核測試)。
# 每個取用 IT1/IT2 的測試自取一份「全新」夾具,避免測試間因 mutate 互相污染。
# =====================================================================

def _IT1():
    return {
        "name": "a.png", "path": "/img/a.png",
        "sidecar": {
            "review_status": "done", "verdict": "true_defect",
            "tags": ["True Defect", "Need Review"],
            "bookmarked": True, "rois": [{"bbox": [1, 2, 3, 4]}],
            "comment": "刮傷,邊緣",
        },
        "detections": [
            {"bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 0.9},
            {"bbox": [50, 60, 10, 10], "cls": "dent", "conf": 0.5},
            {"bbox": [0, 0, 5, 5], "cls": "scratch", "conf": 0.7},
        ],
    }


def _IT2():
    return {"name": "b.png", "path": "/img/b.png", "sidecar": {}, "detections": []}


# =====================================================================
# A. 欄位順序與常數(契約)
# =====================================================================

def test_ac1_build_rows_empty_input_empty_output():
    # AC1:build_rows([]) == []
    assert casepkg.build_rows([]) == []


def test_ac2_row_key_order_is_11_columns():
    # AC2:row 鍵順序 == §3.2,剛好 11 欄
    assert list(casepkg.build_rows([_IT1()])[0].keys()) == [
        "name", "path", "status", "verdict", "tags", "bookmarked",
        "n_rois", "n_det", "max_conf", "classes", "comment",
    ]


# =====================================================================
# B. build_rows 逐欄值(釘死)
# =====================================================================

def test_ac3_build_rows_full_item_exact():
    # AC3:完整 item 逐欄值(tags 以 ; 串接、classes 去重保序以 , 串接、max_conf=最大、計數)
    assert casepkg.build_rows([_IT1()])[0] == {
        "name": "a.png", "path": "/img/a.png", "status": "done",
        "verdict": "true_defect", "tags": "True Defect;Need Review",
        "bookmarked": True, "n_rois": 1, "n_det": 3, "max_conf": 0.9,
        "classes": "scratch,dent", "comment": "刮傷,邊緣",
    }


def test_ac4_build_rows_all_missing_keys_defaults():
    # AC4:全缺鍵 item 取 §3.2 缺漏預設值
    assert casepkg.build_rows([_IT2()])[0] == {
        "name": "b.png", "path": "/img/b.png", "status": "none",
        "verdict": "unset", "tags": "", "bookmarked": False,
        "n_rois": 0, "n_det": 0, "max_conf": 0.0, "classes": "", "comment": "",
    }


def test_ac5_max_conf_type_and_value():
    # AC5:max_conf 為 float;IT1 → 0.9,IT2(無 detection)→ 0.0
    r = casepkg.build_rows([_IT1()])[0]
    assert r["max_conf"] == 0.9 and isinstance(r["max_conf"], float)
    assert casepkg.build_rows([_IT2()])[0]["max_conf"] == 0.0


def test_ac6_classes_dedup_keep_first_order():
    # AC6:classes 去重保序(首見 scratch、再 dent,第三筆 scratch 不重複)
    assert casepkg.build_rows([_IT1()])[0]["classes"] == "scratch,dent"


def test_ac7_multi_item_order_preserved():
    # AC7:多 item 保序
    rows = casepkg.build_rows([_IT1(), _IT2()])
    assert len(rows) == 2 and rows[0]["name"] == "a.png" and rows[1]["name"] == "b.png"


def test_ac8_build_rows_does_not_mutate_input():
    # AC8:build_rows 不 mutate 輸入(deepcopy 前後相等;tags 長度與 detections 數不變)
    it1 = _IT1()
    before = copy.deepcopy(it1)
    casepkg.build_rows([it1])
    assert it1 == before
    assert it1["sidecar"]["tags"] == ["True Defect", "Need Review"]
    assert len(it1["detections"]) == 3


# =====================================================================
# C. to_csv(表頭 / 行尾 / 逸出,釘死)
# =====================================================================

def test_ac9_to_csv_empty_rows_header_only():
    # AC9:空 rows 仍出僅表頭一行,\r\n 結尾
    assert casepkg.to_csv([]) == (
        "name,path,status,verdict,tags,bookmarked,"
        "n_rois,n_det,max_conf,classes,comment\r\n"
    )


def test_ac10_to_csv_header_exact():
    # AC10:表頭精確(split \r\n 第一段)
    header = casepkg.to_csv(casepkg.build_rows([_IT1()])).split("\r\n")[0]
    assert header == (
        "name,path,status,verdict,tags,bookmarked,"
        "n_rois,n_det,max_conf,classes,comment"
    )


def test_ac11_to_csv_data_row_exact_with_comma_escape():
    # AC11:資料列精確,含逗號逸出(classes 與 comment 含 ASCII 逗號 → QUOTE_MINIMAL 加雙引號)
    csv_str = casepkg.to_csv(casepkg.build_rows([_IT1()]))
    lines = csv_str.split("\r\n")
    assert lines[1] == (
        'a.png,/img/a.png,done,true_defect,True Defect;Need Review,'
        'True,1,3,0.9,"scratch,dent","刮傷,邊緣"'
    )
    assert lines[2] == ""


def test_ac12_to_csv_line_terminator_crlf():
    # AC12:行尾為 CRLF;表頭 + 一筆資料共兩個 \r\n
    s = casepkg.to_csv(casepkg.build_rows([_IT1()]))
    assert s.endswith("\r\n")
    assert s.count("\r\n") == 2


def test_ac13_to_csv_all_missing_keys_row():
    # AC13:全缺鍵列 → 空 tags/classes/comment 連續逗號;max_conf=0.0
    line = casepkg.to_csv(casepkg.build_rows([_IT2()])).split("\r\n")[1]
    assert line == "b.png,/img/b.png,none,unset,,False,0,0,0.0,,"


# =====================================================================
# D. build_case_list / to_json(巢狀 + round-trip,釘死)
# =====================================================================

def test_ac14_case_structure_and_key_order():
    # AC14:case 結構與鍵順序(case / review / summary 三層鍵序釘死)
    cl = casepkg.build_case_list([_IT1()])
    assert list(cl[0].keys()) == ["name", "path", "review", "detections", "summary"]
    assert list(cl[0]["review"].keys()) == [
        "status", "verdict", "tags", "bookmarked", "comment", "n_rois",
    ]
    assert list(cl[0]["summary"].keys()) == ["n_det", "max_conf", "classes"]


def test_ac15_review_subobject_values():
    # AC15:review 子物件值(tags 為 list、不去重保序)
    cl = casepkg.build_case_list([_IT1()])
    assert cl[0]["review"] == {
        "status": "done", "verdict": "true_defect",
        "tags": ["True Defect", "Need Review"], "bookmarked": True,
        "comment": "刮傷,邊緣", "n_rois": 1,
    }


def test_ac16_detections_nested_verbatim():
    # AC16:detections 巢狀原樣(三筆原序、bbox 為 list、conf 為 float)
    cl = casepkg.build_case_list([_IT1()])
    assert cl[0]["detections"] == [
        {"bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 0.9},
        {"bbox": [50, 60, 10, 10], "cls": "dent", "conf": 0.5},
        {"bbox": [0, 0, 5, 5], "cls": "scratch", "conf": 0.7},
    ]


def test_ac17_summary_values():
    # AC17:summary(classes 為去重保序 list)
    cl = casepkg.build_case_list([_IT1()])
    assert cl[0]["summary"] == {
        "n_det": 3, "max_conf": 0.9, "classes": ["scratch", "dent"],
    }


def test_ac18_case_all_missing_keys():
    # AC18:全缺鍵 case 整體相等
    cl = casepkg.build_case_list([_IT2()])
    assert cl[0] == {
        "name": "b.png", "path": "/img/b.png",
        "review": {"status": "none", "verdict": "unset", "tags": [],
                   "bookmarked": False, "comment": "", "n_rois": 0},
        "detections": [],
        "summary": {"n_det": 0, "max_conf": 0.0, "classes": []},
    }


def test_ac19_empty_items_case_list_and_json():
    # AC19:空 items → build_case_list([]) == [] 且 to_json([]) == "[]"
    assert casepkg.build_case_list([]) == []
    assert casepkg.to_json([]) == "[]"


def test_ac20_to_json_equals_dumps_build_case_list():
    # AC20:to_json == json.dumps(build_case_list, ensure_ascii=False, indent=2)
    assert casepkg.to_json([_IT1()]) == json.dumps(
        casepkg.build_case_list([_IT1()]), ensure_ascii=False, indent=2)


def test_ac21_round_trip_structure_correct():
    # AC21:round-trip 結構正確(經 JSON 編解碼後逐欄相等)
    items = [_IT1(), _IT2()]
    assert json.loads(casepkg.to_json(items)) == casepkg.build_case_list(items)


def test_ac22_non_ascii_lossless():
    # AC22:non-ASCII 無損(中文 + 逗號 round-trip 不變;ensure_ascii=False)
    loaded = json.loads(casepkg.to_json([_IT1()]))
    assert loaded[0]["review"]["comment"] == "刮傷,邊緣"


def test_ac23_to_json_does_not_mutate_input():
    # AC23:to_json 不 mutate 輸入(deepcopy 前後相等)
    it1 = _IT1()
    before = copy.deepcopy(it1)
    casepkg.to_json([it1])
    assert it1 == before


# =====================================================================
# E. write_package(Tier B,tmp_path 真實寫讀,逐欄斷言)
# =====================================================================

def test_ac24_write_package_returns_paths(tmp_path):
    # AC24:回傳路徑;鍵為 {csv,json};值為 out_dir/case_list.*;兩檔存在
    out_dir = str(tmp_path / "pkg")
    out = casepkg.write_package(out_dir, [_IT1(), _IT2()])
    assert set(out.keys()) == {"csv", "json"}
    assert out["csv"] == os.path.join(out_dir, "case_list.csv")
    assert out["json"] == os.path.join(out_dir, "case_list.json")
    assert os.path.exists(out["csv"]) is True
    assert os.path.exists(out["json"]) is True


def test_ac25_write_package_creates_missing_dir(tmp_path):
    # AC25:out_dir 不存在 → 自動建立(os.makedirs exist_ok),不丟錯,事後目錄與兩檔存在
    out_dir = str(tmp_path / "nope" / "deep")
    out = casepkg.write_package(out_dir, [_IT1()])
    assert os.path.isdir(out_dir)
    assert os.path.exists(out["csv"]) and os.path.exists(out["json"])


def test_ac26_csv_disk_bytes_equal_to_csv(tmp_path):
    # AC26:CSV 內容 == to_csv∘build_rows,讀回逐位元相等(含 \r\n,無平台雙轉換)
    items = [_IT1(), _IT2()]
    out = casepkg.write_package(str(tmp_path / "pkg"), items)
    with io.open(out["csv"], "r", encoding="utf-8", newline="") as f:
        disk = f.read()
    assert disk == casepkg.to_csv(casepkg.build_rows(items))


def test_ac27_csv_readback_per_field(tmp_path):
    # AC27:CSV 讀回逐欄(csv.DictReader 回字串)
    out = casepkg.write_package(str(tmp_path / "pkg"), [_IT1(), _IT2()])
    with io.open(out["csv"], "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["name"] == "a.png"
    assert rows[0]["classes"] == "scratch,dent"
    assert rows[0]["comment"] == "刮傷,邊緣"
    assert rows[0]["bookmarked"] == "True"
    assert rows[0]["n_det"] == "3"
    assert rows[0]["max_conf"] == "0.9"
    assert rows[1]["name"] == "b.png"
    assert rows[1]["tags"] == ""
    assert rows[1]["max_conf"] == "0.0"


def test_ac28_json_disk_equals_to_json_and_roundtrip(tmp_path):
    # AC28:JSON 內容 == to_json,讀回 round-trip == build_case_list
    items = [_IT1(), _IT2()]
    out = casepkg.write_package(str(tmp_path / "pkg"), items)
    with io.open(out["json"], "r", encoding="utf-8") as f:
        disk = f.read()
    assert disk == casepkg.to_json(items)
    with io.open(out["json"], "r", encoding="utf-8") as f:
        assert json.load(f) == casepkg.build_case_list(items)


def test_ac29_empty_items_still_writes_two_files(tmp_path):
    # AC29:空 items 仍寫兩檔;CSV 為僅表頭行;JSON 為 []
    out = casepkg.write_package(str(tmp_path / "empty"), [])
    with io.open(out["csv"], "r", encoding="utf-8", newline="") as f:
        csv_disk = f.read()
    assert csv_disk == (
        "name,path,status,verdict,tags,bookmarked,"
        "n_rois,n_det,max_conf,classes,comment\r\n"
    )
    with io.open(out["json"], "r", encoding="utf-8") as f:
        assert json.load(f) == []
    assert os.path.exists(out["csv"]) and os.path.exists(out["json"])


def test_ac30_overwrite_semantics(tmp_path):
    # AC30:同 out_dir 重複呼叫,後者完全覆寫前者(非附加)
    out_dir = str(tmp_path / "pkg")
    casepkg.write_package(out_dir, [_IT1(), _IT2()])
    out = casepkg.write_package(out_dir, [_IT2()])
    with io.open(out["csv"], "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["name"] == "b.png"
    with io.open(out["json"], "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1


# =====================================================================
# 推導 / property 測試(設計未明列;由契約推導,即使同源也能逼出實作 bug)
# =====================================================================

def test_invariant_ascii_comma_in_fixtures():
    # 推導(檔頭一致性鐵則):IT1 夾具內 comment / classes 的逗號必須是 ASCII U+002C,
    # 否則 AC11/AC13/AC27 的 QUOTE_MINIMAL 期望會自相矛盾。本測試把該假設變成硬斷言。
    it1 = _IT1()
    assert "," in it1["sidecar"]["comment"]      # 刮傷,邊緣
    assert "，" not in it1["sidecar"]["comment"]  # 不可為全形逗號
    # classes 串接後應含 ASCII 逗號(scratch,dent)
    classes = casepkg.build_rows([it1])[0]["classes"]
    assert classes == "scratch,dent"
    assert "," in classes and "，" not in classes


def test_invariant_to_json_equals_write_then_read(tmp_path):
    # 推導(§3.5):磁碟 JSON 必與 to_json 字串逐字相等,且 write_package 不 mutate 輸入。
    # 比 AC28 多驗「寫檔不改原 items」這條跨 I/O 不變式。
    items = [_IT1(), _IT2()]
    before = copy.deepcopy(items)
    out = casepkg.write_package(str(tmp_path / "pkg"), items)
    assert items == before  # write_package 不得 mutate
    with io.open(out["json"], "r", encoding="utf-8") as f:
        assert f.read() == casepkg.to_json(before)


def test_invariant_conf_int_normalized_to_float():
    # 推導(§5「conf 為 int」):conf=1(int)應被 float() 正規化為 1.0;
    # 影響 max_conf(row)與 detections[i]["conf"](case list)。
    item = {"name": "x", "path": "p", "sidecar": {},
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "c", "conf": 1}]}
    r = casepkg.build_rows([item])[0]
    assert r["max_conf"] == 1.0 and isinstance(r["max_conf"], float)
    cl = casepkg.build_case_list([item])[0]
    assert cl["detections"][0]["conf"] == 1.0
    assert isinstance(cl["detections"][0]["conf"], float)
    assert cl["summary"]["max_conf"] == 1.0


def test_invariant_to_csv_consumes_rows_not_items():
    # 推導(§4「to_csv 吃 build_rows 的輸出,不是 items」):
    # to_csv(build_rows(X)) 對任意 X 應一致;且 to_csv 對空 row list 與對 build_rows([]) 同結果。
    assert casepkg.to_csv(casepkg.build_rows([])) == casepkg.to_csv([])


def test_invariant_filter_free_order_preserved_in_json():
    # 推導(§7「原序輸出」):build_case_list 不重排,case[i] 對應 items[i]。
    items = [_IT2(), _IT1()]  # 故意反序
    cl = casepkg.build_case_list(items)
    assert [c["name"] for c in cl] == ["b.png", "a.png"]
