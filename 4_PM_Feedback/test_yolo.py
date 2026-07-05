"""yolo 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/07_yolo.md(AC1..AC35 + §2/§4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import yolo`。此時實作尚未生成,import 不到屬正常(test-first);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

此模組為 Tier B(真實檔案 I/O 容錯載入器):凡 `load` 的 AC 一律
**把 JSON 寫到 pytest 的 `tmp_path` 再 `yolo.load(...)` 回來**,逐欄等值斷言
(不得只查「非空」)。`normalize_one`(AC34/35)以純函式直接呼叫驗證。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_yolo.py -p no:cacheprovider --strict-markers -q
"""
import json
import os

import pytest

import yolo


# ---------------------------------------------------------------------
# 寫檔小工具(設計 §5 寫檔慣例):把 payload 寫成 JSON 檔,回傳 Path。
# ---------------------------------------------------------------------
def _write_json(tmp_path, payload, name="img.json"):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _write_raw(tmp_path, raw_text, name="img.json"):
    # 寫入「原始字串」(用於壞 JSON / 空字串等非 json.dumps 內容)。
    p = tmp_path / name
    p.write_text(raw_text, encoding="utf-8")
    return p


# =====================================================================
# A. 容錯:檔案層級(Tier B 真實 I/O)
# =====================================================================

def test_ac1_missing_file_returns_empty_and_creates_nothing(tmp_path):
    # AC1:不存在的路徑 → load == [];且不建立任何檔案
    missing = tmp_path / "nope.json"
    assert yolo.load(str(missing)) == []
    assert os.path.exists(str(missing)) is False


def test_ac2_bad_json_returns_empty(tmp_path):
    # AC2:內容為壞 JSON "{not json" → load == [](不丟例外)
    p = _write_raw(tmp_path, "{not json")
    assert yolo.load(str(p)) == []


def test_ac3_empty_file_returns_empty(tmp_path):
    # AC3:內容為空字串 → load == []
    p = _write_raw(tmp_path, "")
    assert yolo.load(str(p)) == []


def test_ac4_toplevel_number_or_string_returns_empty(tmp_path):
    # AC4:頂層為純數字 42 → [];頂層為字串 "hi" → []
    p_num = _write_json(tmp_path, 42, name="num.json")
    p_str = _write_json(tmp_path, "hi", name="str.json")
    assert yolo.load(str(p_num)) == []
    assert yolo.load(str(p_str)) == []


def test_ac5_dict_without_known_keys_returns_empty(tmp_path):
    # AC5:dict 無 detections/predictions/objects 鍵 → []
    p = _write_json(tmp_path, {"foo": [1, 2, 3]})
    assert yolo.load(str(p)) == []


def test_ac6_empty_detection_array_returns_empty(tmp_path):
    # AC6:頂層 [] → [];{"detections": []} → []
    p_list = _write_json(tmp_path, [], name="list.json")
    p_dict = _write_json(tmp_path, {"detections": []}, name="dict.json")
    assert yolo.load(str(p_list)) == []
    assert yolo.load(str(p_dict)) == []


def test_ac7_accepts_pathlib_path_equals_str(tmp_path):
    # AC7:同份合法內容,Path 與 str 兩種傳法結果一致
    payload = [{"bbox": [10, 20, 30, 40], "cls": "defect", "conf": 0.9}]
    p = _write_json(tmp_path, payload)
    assert yolo.load(p) == yolo.load(str(p))
    # 並且確實載入到內容(非兩邊都空導致的假相等)
    assert yolo.load(p) == [{"bbox": [10, 20, 30, 40], "cls": "defect", "conf": 0.9}]


# =====================================================================
# B. 頂層容器 schema(list / detections / predictions / objects)
# =====================================================================

def test_ac8_toplevel_list(tmp_path):
    # AC8:頂層即 list → 偵測陣列就是它本身
    p = _write_json(tmp_path, [{"bbox": [10, 20, 30, 40], "cls": "defect", "conf": 0.9}])
    assert yolo.load(str(p)) == [{"bbox": [10, 20, 30, 40], "cls": "defect", "conf": 0.9}]


def test_ac9_detections_key(tmp_path):
    # AC9:dict.detections
    p = _write_json(tmp_path, {"detections": [{"bbox": [1, 2, 3, 4], "cls": "a", "conf": 0.5}]})
    assert yolo.load(str(p)) == [{"bbox": [1, 2, 3, 4], "cls": "a", "conf": 0.5}]


def test_ac10_predictions_key(tmp_path):
    # AC10:dict.predictions
    p = _write_json(tmp_path, {"predictions": [{"bbox": [1, 2, 3, 4], "cls": "a", "conf": 0.5}]})
    assert yolo.load(str(p)) == [{"bbox": [1, 2, 3, 4], "cls": "a", "conf": 0.5}]


def test_ac11_objects_key(tmp_path):
    # AC11:dict.objects
    p = _write_json(tmp_path, {"objects": [{"bbox": [1, 2, 3, 4], "cls": "a", "conf": 0.5}]})
    assert yolo.load(str(p)) == [{"bbox": [1, 2, 3, 4], "cls": "a", "conf": 0.5}]


def test_ac12_key_priority_detections_over_predictions(tmp_path):
    # AC12:同時有 detections 與 predictions → 取 detections
    p = _write_json(tmp_path, {
        "detections": [{"bbox": [1, 1, 1, 1], "cls": "d", "conf": 1.0}],
        "predictions": [{"bbox": [9, 9, 9, 9], "cls": "p", "conf": 1.0}],
    })
    assert yolo.load(str(p)) == [{"bbox": [1, 1, 1, 1], "cls": "d", "conf": 1.0}]


# =====================================================================
# C. 座標換算(釘死具體數值)
# =====================================================================

def test_ac13_absolute_bbox_passthrough(tmp_path):
    # AC13:絕對 bbox 原樣直通,不縮放
    p = _write_json(tmp_path, [{"bbox": [10, 20, 30, 40], "cls": "x", "conf": 0.8}])
    dets = yolo.load(str(p))
    assert dets[0]["bbox"] == [10, 20, 30, 40]


def test_ac14_xyxy_to_xywh(tmp_path):
    # AC14:xyxy [10,20,50,80] → bbox [10,20,40,60]
    p = _write_json(tmp_path, [{"xyxy": [10, 20, 50, 80], "cls": "x", "conf": 0.8}])
    dets = yolo.load(str(p))
    assert dets[0]["bbox"] == [10, 20, 40, 60]


def test_ac15_xyxy_swapped_corners(tmp_path):
    # AC15:xyxy 顛倒角點 [50,80,10,20] → 仍 [10,20,40,60](min/abs 正規化)
    p = _write_json(tmp_path, [{"xyxy": [50, 80, 10, 20], "cls": "x", "conf": 1.0}])
    dets = yolo.load(str(p))
    assert dets[0]["bbox"] == [10, 20, 40, 60]


def test_ac16_xywhn_to_absolute_with_size(tmp_path):
    # AC16:xywhn [0.5,0.5,0.2,0.4] 配 img_w=200,img_h=100 → bbox [80,30,40,40]
    p = _write_json(tmp_path, [{"xywhn": [0.5, 0.5, 0.2, 0.4], "cls": "x", "conf": 0.7}])
    dets = yolo.load(str(p), img_w=200, img_h=100)
    assert dets[0]["bbox"] == [80, 30, 40, 40]


def test_ac17_xywhn_missing_size_skips_record(tmp_path):
    # AC17:xywhn 但缺 img_w/img_h → 該筆被跳過 → load == [](不丟錯)
    p = _write_json(tmp_path, [{"xywhn": [0.5, 0.5, 0.2, 0.4], "cls": "x", "conf": 0.7}])
    assert yolo.load(str(p), img_w=None, img_h=None) == []


def test_ac18_bbox_truncated_to_int(tmp_path):
    # AC18:xywhn [0.5,0.5,0.3,0.3] 配 101x101 → bbox [35,35,30,30],各值為 int
    p = _write_json(tmp_path, [{"xywhn": [0.5, 0.5, 0.3, 0.3], "cls": "x", "conf": 1.0}])
    dets = yolo.load(str(p), img_w=101, img_h=101)
    assert dets[0]["bbox"] == [35, 35, 30, 30]
    assert all(isinstance(v, int) for v in dets[0]["bbox"])


# =====================================================================
# D. 類別與信心別名 + 預設
# =====================================================================

def test_ac19_class_aliases(tmp_path):
    # AC19:class / name / label / cls 四別名各擇一,值 "alias" → cls == "alias"
    for i, key in enumerate(("class", "name", "label", "cls")):
        payload = [{"bbox": [0, 0, 1, 1], key: "alias", "conf": 1.0}]
        p = _write_json(tmp_path, payload, name=f"alias_{i}.json")
        dets = yolo.load(str(p))
        assert dets[0]["cls"] == "alias", f"alias key={key}"


def test_ac20_class_int_id_to_str(tmp_path):
    # AC20:cls 為 int 3 → "3"
    p = _write_json(tmp_path, [{"bbox": [0, 0, 1, 1], "cls": 3, "conf": 1.0}])
    dets = yolo.load(str(p))
    assert dets[0]["cls"] == "3"


def test_ac21_missing_class_empty_string_kept(tmp_path):
    # AC21:無任何類別鍵 → cls == "" 且該筆保留
    p = _write_json(tmp_path, [{"bbox": [0, 0, 1, 1], "conf": 0.9}])
    dets = yolo.load(str(p))
    assert len(dets) == 1
    assert dets[0]["cls"] == ""


def test_ac22_conf_aliases(tmp_path):
    # AC22:confidence 0.33 → 0.33;score 0.66 → 0.66
    p_c = _write_json(tmp_path, [{"bbox": [0, 0, 1, 1], "cls": "x", "confidence": 0.33}], name="c.json")
    p_s = _write_json(tmp_path, [{"bbox": [0, 0, 1, 1], "cls": "x", "score": 0.66}], name="s.json")
    assert yolo.load(str(p_c))[0]["conf"] == 0.33
    assert yolo.load(str(p_s))[0]["conf"] == 0.66


def test_ac23_missing_conf_defaults_one(tmp_path):
    # AC23:無信心鍵 → conf == 1.0 且該筆保留
    p = _write_json(tmp_path, [{"bbox": [0, 0, 1, 1], "cls": "x"}])
    dets = yolo.load(str(p))
    assert len(dets) == 1
    assert dets[0]["conf"] == 1.0


def test_ac24_conf_clamped(tmp_path):
    # AC24:三筆 conf -0.3 / 1.7 / 0.42 → 0.0 / 1.0 / 0.42
    p = _write_json(tmp_path, [
        {"bbox": [0, 0, 1, 1], "cls": "a", "conf": -0.3},
        {"bbox": [0, 0, 1, 1], "cls": "b", "conf": 1.7},
        {"bbox": [0, 0, 1, 1], "cls": "c", "conf": 0.42},
    ])
    dets = yolo.load(str(p))
    assert [d["conf"] for d in dets] == [0.0, 1.0, 0.42]


def test_ac25_non_numeric_conf_defaults_one_and_kept(tmp_path):
    # AC25:conf "high"(非數值)→ conf == 1.0 且該筆保留
    p = _write_json(tmp_path, [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": "high"}])
    dets = yolo.load(str(p))
    assert len(dets) == 1
    assert dets[0]["conf"] == 1.0


# =====================================================================
# E. 逐筆容錯(混入髒資料只跳過壞筆)
# =====================================================================

def test_ac26_missing_box_skips_that_record(tmp_path):
    # AC26:缺框筆被跳過,有框筆保留
    p = _write_json(tmp_path, [
        {"cls": "a", "conf": 0.9},
        {"bbox": [0, 0, 2, 2], "cls": "b", "conf": 0.8},
    ])
    assert yolo.load(str(p)) == [{"bbox": [0, 0, 2, 2], "cls": "b", "conf": 0.8}]


def test_ac27_wrong_box_length_skips(tmp_path):
    # AC27:bbox 長度 3 與 5 的兩筆被跳過,長度 4 者保留
    p = _write_json(tmp_path, [
        {"bbox": [1, 2, 3], "cls": "a", "conf": 1.0},
        {"bbox": [1, 2, 3, 4, 5], "cls": "b", "conf": 1.0},
        {"bbox": [5, 5, 5, 5], "cls": "c", "conf": 1.0},
    ])
    assert yolo.load(str(p)) == [{"bbox": [5, 5, 5, 5], "cls": "c", "conf": 1.0}]


def test_ac28_non_dict_elements_skipped(tmp_path):
    # AC28:陣列含 5 / "x" / null → 跳過,只留合法 dict 筆
    p = _write_json(tmp_path, [5, "x", None, {"bbox": [0, 0, 1, 1], "cls": "ok", "conf": 1.0}])
    assert yolo.load(str(p)) == [{"bbox": [0, 0, 1, 1], "cls": "ok", "conf": 1.0}]


def test_ac29_non_numeric_box_value_skips_record(tmp_path):
    # AC29:框含非數值 "x" → 該筆跳過,合法筆保留
    p = _write_json(tmp_path, [
        {"bbox": [0, 0, "x", 2], "cls": "a", "conf": 1.0},
        {"bbox": [1, 1, 2, 2], "cls": "b", "conf": 1.0},
    ])
    assert yolo.load(str(p)) == [{"bbox": [1, 1, 2, 2], "cls": "b", "conf": 1.0}]


def test_ac30_multi_box_key_priority_bbox_over_xyxy(tmp_path):
    # AC30:同筆 bbox 與 xyxy 並存 → 取 bbox [1,1,1,1]
    p = _write_json(tmp_path, [{"bbox": [1, 1, 1, 1], "xyxy": [0, 0, 9, 9], "cls": "x", "conf": 1.0}])
    dets = yolo.load(str(p))
    assert dets[0]["bbox"] == [1, 1, 1, 1]


# =====================================================================
# F. 端到端(ultralytics-ish 真實檔 + 混髒資料 + 順序 + 形狀)
# =====================================================================

def _ultralytics_ish_payload():
    return {
        "image": "wafer_001.png",
        "detections": [
            {"xyxy": [100, 100, 150, 180], "name": "scratch", "confidence": 0.91},
            {"bbox": [10, 20, 30, 40], "cls": 2, "conf": 0.5},
            {"cls": "missing_box", "conf": 0.99},
            {"xywhn": [0.5, 0.5, 0.1, 0.2], "name": "edge", "conf": 1.3},
        ],
    }


def test_ac31_ultralytics_ish_whole_file(tmp_path):
    # AC31:整檔(含 xyxy/int cls/缺框/xywhn 超界 conf)逐欄等於期望
    p = _write_json(tmp_path, _ultralytics_ish_payload())
    dets = yolo.load(str(p), img_w=200, img_h=100)
    assert dets == [
        {"bbox": [100, 100, 50, 80], "cls": "scratch", "conf": 0.91},  # xyxy→xywh, name 別名
        {"bbox": [10, 20, 30, 40], "cls": "2", "conf": 0.5},           # int cls→"2"
        # 第三筆缺框 → 被跳過
        {"bbox": [90, 40, 20, 20], "cls": "edge", "conf": 1.0},        # xywhn→abs, conf 1.3 夾到 1.0
    ]
    # 額外:長度、順序、缺框筆確實被跳過
    assert len(dets) == 3
    assert [d["cls"] for d in dets] == ["scratch", "2", "edge"]


def test_ac32_each_detection_exactly_three_keys_and_types(tmp_path):
    # AC32:每筆恰三鍵 + bbox 為四個 int + conf 為 float + cls 為 str
    p = _write_json(tmp_path, _ultralytics_ish_payload())
    dets = yolo.load(str(p), img_w=200, img_h=100)
    assert all(set(d.keys()) == {"bbox", "cls", "conf"} for d in dets)
    assert all(isinstance(d["bbox"], list) and len(d["bbox"]) == 4 for d in dets)
    assert all(isinstance(v, int) for d in dets for v in d["bbox"])
    assert all(isinstance(d["conf"], float) for d in dets)
    assert all(isinstance(d["cls"], str) for d in dets)


def test_ac33_order_preserved(tmp_path):
    # AC33:輸出順序 == 來源有效筆順序
    p = _write_json(tmp_path, [
        {"bbox": [0, 0, 1, 1], "cls": "first", "conf": 1.0},
        {"bbox": [2, 2, 1, 1], "cls": "second", "conf": 1.0},
        {"bbox": [3, 3, 1, 1], "cls": "third", "conf": 1.0},
    ])
    assert [d["cls"] for d in yolo.load(str(p))] == ["first", "second", "third"]


# =====================================================================
# G. normalize_one 純函式直驗(單筆,不經檔案)
# =====================================================================

def test_ac34_normalize_one_happy_path():
    # AC34:normalize_one xyxy + name + score → 完整 Detection
    assert yolo.normalize_one(
        {"xyxy": [10, 20, 50, 80], "name": "x", "score": 0.6}
    ) == {"bbox": [10, 20, 40, 60], "cls": "x", "conf": 0.6}


def test_ac35_normalize_one_bad_input_returns_none():
    # AC35:缺框 / 非 dict / xywhn 缺尺寸 三種壞輸入皆回 None
    assert yolo.normalize_one({"cls": "x", "conf": 0.9}) is None           # 缺框
    assert yolo.normalize_one(5) is None                                   # 非 dict
    assert yolo.normalize_one(                                             # xywhn 缺尺寸
        {"xywhn": [0.5, 0.5, 0.1, 0.1], "cls": "x", "conf": 1.0},
        img_w=None, img_h=None) is None


# =====================================================================
# 推導 / property 測試(設計未明列;由契約 §2/§4 推導,對同源實作施壓)
# =====================================================================

def test_prop_load_never_raises_on_arbitrary_garbage(tmp_path):
    # 推導(§4 + §6「load 永不拋例外」):對各式各樣的髒輸入,load 一律回 list,絕不拋例外。
    garbage_payloads = [
        {"detections": "not a list"},          # 已知鍵但值非 list → []
        {"detections": 123},                   # 非 list
        [None, None, None],                    # 全非 dict
        [[1, 2, 3, 4]],                        # 元素是 list 而非 dict → 跳過
        {"predictions": [{"bbox": "nope"}]},   # 框值非序列
        [{"bbox": [1, 2, 3, 4], "cls": {}, "conf": 0.5}],  # cls 為 dict → str(dict),不拋錯
        [{"bbox": [1, 2, 3, 4], "conf": [1, 2]}],          # conf 非數值 → 預設 1.0
        {"objects": [{}]},                     # 空 dict 偵測(缺框)→ 跳過
    ]
    for i, payload in enumerate(garbage_payloads):
        p = _write_json(tmp_path, payload, name=f"garbage_{i}.json")
        out = yolo.load(str(p))
        assert isinstance(out, list), f"payload#{i} 應回 list"


def test_prop_load_equals_normalize_one_filter(tmp_path):
    # 推導(§2「load 內部對每筆呼叫 normalize_one」+ §3 資料流):
    # load 必等價於「抽偵測陣列後對每筆套 normalize_one、丟掉 None、保序」。
    # 這是比任何單例 AC 更強的不變式,逼出 load 與 normalize_one 兩者間的不一致。
    raw_array = [
        {"xyxy": [100, 100, 150, 180], "name": "scratch", "confidence": 0.91},
        {"bbox": [10, 20, 30, 40], "cls": 2, "conf": 0.5},
        {"cls": "missing_box", "conf": 0.99},                 # 缺框 → None
        {"xywhn": [0.5, 0.5, 0.1, 0.2], "name": "edge", "conf": 1.3},
        5,                                                    # 非 dict → None
    ]
    p = _write_json(tmp_path, {"detections": raw_array})
    expected = [
        d for d in (yolo.normalize_one(r, img_w=200, img_h=100) for r in raw_array)
        if d is not None
    ]
    assert yolo.load(str(p), img_w=200, img_h=100) == expected


def test_prop_normalize_one_is_pure_no_side_effects():
    # 推導(§2.4「normalize_one 為純函式、不做 I/O、不拋例外」):
    # 同一輸入多次呼叫結果恆等(referential transparency),且不 mutate 輸入 dict。
    src = {"xyxy": [10, 20, 50, 80], "name": "x", "score": 0.6}
    src_snapshot = json.loads(json.dumps(src))  # 深拷貝快照
    out1 = yolo.normalize_one(src)
    out2 = yolo.normalize_one(src)
    assert out1 == out2                          # 冪等 / 引用透明
    assert src == src_snapshot                   # 不 mutate 輸入


def test_prop_normalize_one_three_keys_invariant():
    # 推導(§2.1「set(keys)=={bbox,cls,conf}」):任何成功正規化的單筆,
    # 形狀恆為恰三鍵、bbox 四個 int、conf 為 [0,1] 內 float、cls 為 str。
    samples = [
        {"bbox": [10, 20, 30, 40], "cls": "x", "conf": 0.8},
        {"xyxy": [50, 80, 10, 20], "cls": "x", "conf": 1.0},
        {"bbox": [0, 0, 1, 1]},                              # 缺類別 + 缺信心 → 預設
        {"bbox": [0, 0, 1, 1], "cls": 7, "conf": 5.0},       # int cls + 超界 conf
    ]
    for s in samples:
        d = yolo.normalize_one(s)
        assert d is not None
        assert set(d.keys()) == {"bbox", "cls", "conf"}
        assert isinstance(d["bbox"], list) and len(d["bbox"]) == 4
        assert all(isinstance(v, int) for v in d["bbox"])
        assert isinstance(d["conf"], float) and 0.0 <= d["conf"] <= 1.0
        assert isinstance(d["cls"], str)


def test_prop_does_not_clamp_to_image_bounds():
    # 推導(§4 註「不對 bbox 做影像邊界 clamp,座標可超界/可負」):
    # xyxy 角點為負時,bbox 忠實保留負值,不被夾到 0。
    d = yolo.normalize_one({"xyxy": [-10, -20, 5, 5], "cls": "x", "conf": 1.0})
    assert d["bbox"] == [-10, -20, 15, 25]  # x=-10,y=-20,w=abs(5-(-10))=15,h=abs(5-(-20))=25


# ============================== YOLO .txt 格式(`cls cx cy w h [conf]` 正規化座標)==============================
def _wtxt(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_txt_basic_normalized_to_abs(tmp_path):
    # 正規化中心點+寬高 → 絕對 [x,y,w,h](x,y 為左上角)。img_w=100,img_h=200。
    out = yolo.load(_wtxt(tmp_path, "a.txt", "0 0.5 0.5 0.2 0.4\n"), img_w=100, img_h=200)
    assert len(out) == 1
    assert out[0]["bbox"] == [40, 60, 20, 80]   # w=20,h=80,x=50-10,y=100-40
    assert out[0]["cls"] == "0"                 # 無 names → str(id)
    assert out[0]["conf"] == 1.0                # 無第 6 欄 → 1.0


def test_txt_names_mapping(tmp_path):
    p = _wtxt(tmp_path, "a.txt", "0 0.5 0.5 0.2 0.4\n8 0.5 0.5 0.1 0.1\n")
    names = ["door", "win", "x", "y", "z", "a", "b", "c", "openedDoor"]
    assert [d["cls"] for d in yolo.load(p, img_w=100, img_h=100, names=names)] == ["door", "openedDoor"]


def test_txt_class_id_out_of_names_falls_back_to_str_id(tmp_path):
    p = _wtxt(tmp_path, "a.txt", "5 0.5 0.5 0.1 0.1\n")
    assert yolo.load(p, img_w=100, img_h=100, names=["door"])[0]["cls"] == "5"


def test_txt_optional_conf_sixth_column(tmp_path):
    p = _wtxt(tmp_path, "a.txt", "0 0.5 0.5 0.2 0.2 0.87\n")
    assert yolo.load(p, img_w=100, img_h=100)[0]["conf"] == pytest.approx(0.87)


def test_txt_conf_clamped(tmp_path):
    p = _wtxt(tmp_path, "a.txt", "0 0.5 0.5 0.1 0.1 1.5\n1 0.5 0.5 0.1 0.1 -0.2\n")
    out = yolo.load(p, img_w=100, img_h=100)
    assert out[0]["conf"] == 1.0 and out[1]["conf"] == 0.0


def test_txt_skips_malformed_lines(tmp_path):
    # 空行 / 欄位不足 / 非數值 → 跳過;合法行保留。
    p = _wtxt(tmp_path, "a.txt", "\n0 0.5 0.5 0.2 0.2\nbad line here\n1 0.1\n2 a b c d\n")
    out = yolo.load(p, img_w=100, img_h=100)
    assert len(out) == 1 and out[0]["cls"] == "0"


def test_txt_requires_valid_dims(tmp_path):
    p = _wtxt(tmp_path, "a.txt", "0 0.5 0.5 0.2 0.2\n")
    assert yolo.load(p, img_w=None, img_h=None) == []
    assert yolo.load(p, img_w=0, img_h=100) == []


def test_txt_missing_file_returns_empty(tmp_path):
    assert yolo.load(str(tmp_path / "nope.txt"), img_w=100, img_h=100) == []


def test_txt_output_shape_same_as_json(tmp_path):
    # 與 .json 同形契約:bbox 四 int、cls str、conf float。
    d = yolo.load(_wtxt(tmp_path, "a.txt", "3 0.5 0.5 0.3 0.3 0.5\n"), img_w=100, img_h=100)[0]
    assert set(d) == {"bbox", "cls", "conf"}
    assert len(d["bbox"]) == 4 and all(isinstance(v, int) for v in d["bbox"])
    assert isinstance(d["cls"], str) and isinstance(d["conf"], float)


# ============================== seg/OBB 守衛(2026-07-05,設計 07_yolo.md 演進 + 26_labelfmt.md §5)==============================
# ≥7 欄的行 = segmentation 多邊形 / OBB;前 4 座標會被誤讀成 cx cy w h(silent-wrong)。一律跳過。
def test_txt_skips_segmentation_lines(tmp_path):
    # seg 行(class + 4 對多邊形點 = 9 欄)必須被跳過,不得畫出亂框。
    seg = "0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n"
    out = yolo.load(_wtxt(tmp_path, "a.txt", seg), img_w=100, img_h=100)
    assert out == [], f"≥7 欄 seg 行應被跳過,實得 {out}"


def test_txt_skips_obb_lines(tmp_path):
    # OBB(class + 8 座標 = 9 欄)同樣跳過。
    obb = "2 0.1 0.1 0.5 0.1 0.5 0.5 0.1 0.5\n"
    assert yolo.load(_wtxt(tmp_path, "a.txt", obb), img_w=100, img_h=100) == []


def test_txt_still_accepts_5_and_6_col_detection_lines(tmp_path):
    # 守衛不得誤傷正常偵測框:5 欄(GT)與 6 欄(pred+conf)仍照收。
    mixed = "0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1 0.87\n" \
            "9 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n"  # 第三行 seg,應被跳
    out = yolo.load(_wtxt(tmp_path, "a.txt", mixed), img_w=100, img_h=100)
    assert len(out) == 2, f"5/6 欄偵測行應保留、seg 行跳過,實得 {out}"
    assert out[1]["conf"] == pytest.approx(0.87)
