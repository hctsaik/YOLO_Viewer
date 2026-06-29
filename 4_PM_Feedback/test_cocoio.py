"""cocoio 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/15_cocoio.md(AC1..AC44 + §3 I/O 契約 + §5 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import cocoio`。此時實作尚未生成,import 不到屬正常(test-first,非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

cocoio 為 Tier B「資料轉換 + 薄檔案讀寫」模組,但**零 GUI / 零網路 / 零外部編解碼**:
write_*/read_* 的「真實」驗收靠 tmp_path 實際寫檔再讀回(json round-trip),
故全部測試皆為單元層(無 @pytest.mark.e2e)。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_cocoio.py -p no:cacheprovider --strict-markers -q
"""
import copy
import json
import os

import cocoio


# =====================================================================
# 共用測試夾具(設計 §6 引用 IT1/IT2/IT3)。
# 每個取用者自取一份「全新」夾具,避免測試間因 mutate 互相污染。
# =====================================================================

def _IT1():
    return {
        "name": "a.png", "width": 200, "height": 100,
        "detections": [
            {"bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 0.9},
            {"bbox": [50, 60, 10, 10], "cls": "dent", "conf": 0.5},
            {"bbox": [0, 0, 5, 5], "cls": "scratch", "conf": 0.7},
        ],
    }


def _IT2():
    return {"name": "b.png", "width": 640, "height": 480, "detections": []}


def _IT3():
    return {"name": "c.png", "width": 10, "height": 10,
            "detections": [{"bbox": [1, 1, 1, 1], "cls": "edge", "conf": 0.2}]}


# =====================================================================
# A. to_coco 結構與值(釘死)
# =====================================================================

def test_ac1_to_coco_empty_input():
    # AC1:空輸入 → 三鍵皆空 list,且鍵順序釘死 images/annotations/categories
    assert cocoio.to_coco([]) == {"images": [], "annotations": [], "categories": []}
    assert list(cocoio.to_coco([]).keys()) == ["images", "annotations", "categories"]


def test_ac2_to_coco_full_aggregate_exact():
    # AC2:完整聚合 dict 逐欄等於設計釘死值
    assert cocoio.to_coco([_IT1(), _IT2()]) == {
        "images": [
            {"id": 1, "file_name": "a.png", "width": 200, "height": 100},
            {"id": 2, "file_name": "b.png", "width": 640, "height": 480},
        ],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 20, 30, 40],
             "area": 1200.0, "iscrowd": 0, "score": 0.9},
            {"id": 2, "image_id": 1, "category_id": 2, "bbox": [50, 60, 10, 10],
             "area": 100.0, "iscrowd": 0, "score": 0.5},
            {"id": 3, "image_id": 1, "category_id": 1, "bbox": [0, 0, 5, 5],
             "area": 25.0, "iscrowd": 0, "score": 0.7},
        ],
        "categories": [{"id": 1, "name": "scratch"}, {"id": 2, "name": "dent"}],
    }


def test_ac3_image_dict_key_order():
    # AC3:image dict 鍵順序釘死
    assert list(cocoio.to_coco([_IT1()])["images"][0].keys()) == [
        "id", "file_name", "width", "height"]


def test_ac4_annotation_dict_key_order():
    # AC4:annotation dict 鍵順序釘死
    assert list(cocoio.to_coco([_IT1()])["annotations"][0].keys()) == [
        "id", "image_id", "category_id", "bbox", "area", "iscrowd", "score"]


def test_ac5_category_first_seen_dedup_order():
    # AC5:category 首見去重保序(scratch=1、dent=2,第三筆 scratch 不再新增)
    assert cocoio.to_coco([_IT1()])["categories"] == [
        {"id": 1, "name": "scratch"}, {"id": 2, "name": "dent"}]


def test_ac6_area_is_w_times_h_float():
    # AC6:area = w*h 且為 float
    a = cocoio.to_coco([_IT1()])["annotations"]
    assert a[0]["area"] == 1200.0 and isinstance(a[0]["area"], float)
    assert a[1]["area"] == 100.0


def test_ac7_score_equals_conf_float_even_int():
    # AC7:score = float(conf);conf 為 int 也 float 化
    item = {"name": "c.png", "width": 10, "height": 10,
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 1}]}
    s = cocoio.to_coco([item])["annotations"][0]["score"]
    assert s == 1.0 and isinstance(s, float)


def test_ac8_annotation_id_global_across_images():
    # AC8:annotation id 全域跨影像遞增;IT3 的 det 為第 4 筆且 image_id==2
    coco = cocoio.to_coco([_IT1(), _IT3()])
    assert [a["id"] for a in coco["annotations"]] == [1, 2, 3, 4]
    assert coco["annotations"][3]["image_id"] == 2


def test_ac9_item_missing_keys_defaults():
    # AC9:item 缺鍵套預設(name→""、width/height→0)
    item = {"detections": [{"bbox": [0, 0, 2, 2], "cls": "x", "conf": 0.5}]}
    assert cocoio.to_coco([item])["images"][0] == {
        "id": 1, "file_name": "", "width": 0, "height": 0}


def test_ac10_to_coco_does_not_mutate_input():
    # AC10:不 mutate 輸入(deepcopy 前後相等;bbox 以 list(...) 複製)
    it1 = _IT1()
    before = copy.deepcopy(it1)
    cocoio.to_coco([it1])
    assert it1 == before


# =====================================================================
# B. to_coco 的 categories 參數(釘死)
# =====================================================================

def test_ac11_given_categories_decide_id_order():
    # AC11:給定 categories 決定 id 順序(dent=1、scratch=2,依清單非首見序)
    coco = cocoio.to_coco([_IT1()], categories=["dent", "scratch"])
    assert coco["categories"] == [
        {"id": 1, "name": "dent"}, {"id": 2, "name": "scratch"}]
    assert [a["category_id"] for a in coco["annotations"]] == [2, 1, 2]


def test_ac12_given_categories_lists_unused():
    # AC12:給定 categories 含未出現類別仍列出;IT2 無 det → annotations 空
    coco = cocoio.to_coco([_IT2()], categories=["scratch", "dent"])
    assert coco["categories"] == [
        {"id": 1, "name": "scratch"}, {"id": 2, "name": "dent"}]
    assert coco["annotations"] == []


def test_ac13_cls_not_in_categories_skips_annotation():
    # AC13:det 的 cls 不在 categories → 跳過該 annotation;image 不受影響
    coco = cocoio.to_coco([_IT1()], categories=["dent"])
    assert coco["categories"] == [{"id": 1, "name": "dent"}]
    assert len(coco["annotations"]) == 1
    assert coco["annotations"][0]["category_id"] == 1
    assert coco["annotations"][0]["bbox"] == [50, 60, 10, 10]
    assert len(coco["images"]) == 1


def test_ac14_empty_categories_skips_all_annotations():
    # AC14:空 categories 清單 → 全部 annotation 跳過;images 照出
    coco = cocoio.to_coco([_IT1()], categories=[])
    assert coco["categories"] == []
    assert coco["annotations"] == []
    assert len(coco["images"]) == 1


# =====================================================================
# C. from_coco(解析 + 容錯,釘死)
# =====================================================================

def test_ac15_from_coco_roundtrip_restores_detections():
    # AC15:from_coco∘to_coco 還原 detections / 影像欄位;IT2 還原為空 det
    items2 = cocoio.from_coco(cocoio.to_coco([_IT1(), _IT2()]))
    assert len(items2) == 2
    assert items2[0] == {
        "name": "a.png", "width": 200, "height": 100,
        "detections": [
            {"bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 0.9},
            {"bbox": [50, 60, 10, 10], "cls": "dent", "conf": 0.5},
            {"bbox": [0, 0, 5, 5], "cls": "scratch", "conf": 0.7},
        ],
    }
    assert items2[1] == {
        "name": "b.png", "width": 640, "height": 480, "detections": []}


def test_ac16_category_id_to_cls_name():
    # AC16:category_id→cls 名(id=2→"b")、bbox 直通、score→conf
    coco = {
        "images": [{"id": 1, "file_name": "x.png", "width": 5, "height": 5}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 2,
                         "bbox": [1, 2, 3, 4], "area": 12.0, "iscrowd": 0, "score": 0.8}],
        "categories": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
    }
    assert cocoio.from_coco(coco) == [{
        "name": "x.png", "width": 5, "height": 5,
        "detections": [{"bbox": [1, 2, 3, 4], "cls": "b", "conf": 0.8}]}]


def test_ac17_bbox_passthrough_int():
    # AC17:bbox 直通且取 int(float 值 → int)
    coco = {
        "images": [{"id": 1, "file_name": "x.png", "width": 5, "height": 5}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 1,
                         "bbox": [1.0, 2.0, 3.0, 4.0], "score": 0.5}],
        "categories": [{"id": 1, "name": "a"}],
    }
    bbox = cocoio.from_coco(coco)[0]["detections"][0]["bbox"]
    assert bbox == [1, 2, 3, 4]
    assert all(isinstance(v, int) for v in bbox)


def test_ac18_missing_score_conf_default_one():
    # AC18:annotation 缺 score → conf=1.0
    coco = {
        "images": [{"id": 1, "file_name": "x.png", "width": 5, "height": 5}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 1,
                         "bbox": [1, 2, 3, 4]}],
        "categories": [{"id": 1, "name": "a"}],
    }
    assert cocoio.from_coco(coco)[0]["detections"][0]["conf"] == 1.0


def test_ac19_category_id_not_found_cls_empty():
    # AC19:category_id 查無對應 → cls=""(框仍保留)
    coco = {
        "images": [{"id": 1, "file_name": "x.png", "width": 5, "height": 5}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 99,
                         "bbox": [1, 2, 3, 4], "score": 0.5}],
        "categories": [{"id": 1, "name": "a"}],
    }
    item = cocoio.from_coco(coco)[0]
    assert len(item["detections"]) == 1
    assert item["detections"][0]["cls"] == ""


def test_ac20_bad_bbox_skips_annotation():
    # AC20:缺/壞 bbox(長度 3 / 含非數值)跳過,不影響同影像其他筆
    coco = {
        "images": [{"id": 1, "file_name": "x.png", "width": 9, "height": 9}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [1, 2, 3], "score": 0.1},
            {"id": 2, "image_id": 1, "category_id": 1, "bbox": [1, 2, "x", 4], "score": 0.2},
            {"id": 3, "image_id": 1, "category_id": 1, "bbox": [5, 5, 5, 5], "score": 0.3},
        ],
        "categories": [{"id": 1, "name": "a"}],
    }
    dets = cocoio.from_coco(coco)[0]["detections"]
    assert dets == [{"bbox": [5, 5, 5, 5], "cls": "a", "conf": 0.3}]


def test_ac21_annotation_image_id_unmatched_skipped():
    # AC21:annotation image_id 不對應任何 image → 跳過,不掛任何 item
    coco = {
        "images": [{"id": 1, "file_name": "x.png", "width": 5, "height": 5}],
        "annotations": [{"id": 1, "image_id": 7, "category_id": 1,
                         "bbox": [1, 2, 3, 4], "score": 0.5}],
        "categories": [{"id": 1, "name": "a"}],
    }
    items = cocoio.from_coco(coco)
    assert len(items) == 1
    assert items[0]["detections"] == []


def test_ac22_non_dict_or_missing_images_returns_empty():
    # AC22:非 dict / 缺 images / images 空 → []
    assert cocoio.from_coco(42) == []
    assert cocoio.from_coco("x") == []
    assert cocoio.from_coco({"annotations": []}) == []
    assert cocoio.from_coco({"images": []}) == []


def test_ac23_missing_annotations_each_image_empty_det():
    # AC23:缺 annotations → 每 image 空 det
    coco = {"images": [{"id": 1, "file_name": "x.png", "width": 3, "height": 3}]}
    assert cocoio.from_coco(coco) == [
        {"name": "x.png", "width": 3, "height": 3, "detections": []}]


# =====================================================================
# D. to_labelme / from_labelme(釘死 + round-trip)
# =====================================================================

def test_ac24_to_labelme_structure_key_order():
    # AC24:to_labelme 結構與鍵順序釘死 + 常數值
    lm = cocoio.to_labelme(_IT1())
    assert list(lm.keys()) == [
        "version", "flags", "shapes", "imagePath",
        "imageData", "imageHeight", "imageWidth"]
    assert lm["version"] == "5.0.1"
    assert lm["flags"] == {}
    assert lm["imagePath"] == "a.png"
    assert lm["imageData"] is None
    assert lm["imageHeight"] == 100
    assert lm["imageWidth"] == 200


def test_ac25_to_labelme_shapes_exact():
    # AC25:to_labelme shapes 精確(points=[[x,y],[x+w,y+h]];每 shape 鍵序釘死)
    lm = cocoio.to_labelme(_IT1())
    assert lm["shapes"] == [
        {"label": "scratch", "points": [[10, 20], [40, 60]],
         "group_id": None, "shape_type": "rectangle", "flags": {}},
        {"label": "dent", "points": [[50, 60], [60, 70]],
         "group_id": None, "shape_type": "rectangle", "flags": {}},
        {"label": "scratch", "points": [[0, 0], [5, 5]],
         "group_id": None, "shape_type": "rectangle", "flags": {}},
    ]
    # 鍵順序額外釘死(== 比較不保證鍵序)
    assert list(lm["shapes"][0].keys()) == [
        "label", "points", "group_id", "shape_type", "flags"]


def test_ac26_to_labelme_empty_det():
    # AC26:to_labelme 空 det → shapes 空;imageWidth/Height 仍照出
    lm = cocoio.to_labelme(_IT2())
    assert lm["shapes"] == []
    assert lm["imageWidth"] == 640 and lm["imageHeight"] == 480


def test_ac27_to_labelme_missing_keys_item():
    # AC27:to_labelme 缺鍵 item → 全套預設
    assert cocoio.to_labelme({}) == {
        "version": "5.0.1", "flags": {}, "shapes": [], "imagePath": "",
        "imageData": None, "imageHeight": 0, "imageWidth": 0}


def test_ac28_from_labelme_rectangle_to_bbox():
    # AC28:from_labelme rectangle → bbox(兩點→x,y,w,h;conf 恆 1.0)
    lm = {"imagePath": "x.png", "imageWidth": 50, "imageHeight": 60,
          "shapes": [{"label": "scratch", "points": [[10, 20], [40, 60]],
                      "shape_type": "rectangle"}]}
    assert cocoio.from_labelme(lm) == {
        "name": "x.png", "width": 50, "height": 60,
        "detections": [{"bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 1.0}]}


def test_ac29_from_labelme_reversed_points_min_abs():
    # AC29:點顛倒(右下在前)→ min/abs 正規化,等同 AC28
    lm = {"shapes": [{"label": "x", "points": [[40, 60], [10, 20]],
                      "shape_type": "rectangle"}]}
    assert cocoio.from_labelme(lm)["detections"][0]["bbox"] == [10, 20, 30, 40]


def test_ac30_from_labelme_bbox_int():
    # AC30:from_labelme bbox 取 int(向 0 截斷)
    lm = {"shapes": [{"label": "x", "points": [[10.0, 20.0], [40.5, 60.9]],
                      "shape_type": "rectangle"}]}
    bbox = cocoio.from_labelme(lm)["detections"][0]["bbox"]
    assert bbox == [10, 20, 30, 40]
    assert all(isinstance(v, int) for v in bbox)


def test_ac31_from_labelme_skip_non_rectangle_and_bad_points():
    # AC31:跳過 polygon 與單點 rectangle,只剩 ok
    lm = {"shapes": [
        {"label": "p", "points": [[0, 0], [1, 1], [2, 0]], "shape_type": "polygon"},
        {"label": "bad", "points": [[0, 0]], "shape_type": "rectangle"},
        {"label": "ok", "points": [[1, 1], [3, 4]], "shape_type": "rectangle"},
    ]}
    assert cocoio.from_labelme(lm)["detections"] == [
        {"bbox": [1, 1, 2, 3], "cls": "ok", "conf": 1.0}]


def test_ac32_from_labelme_non_dict_or_missing_shapes():
    # AC32:非 dict → EMPTY_ITEM;缺 shapes → 空 det(name/w/h 仍取)
    assert cocoio.from_labelme(42) == {
        "name": "", "width": 0, "height": 0, "detections": []}
    assert cocoio.from_labelme(
        {"imagePath": "y.png", "imageWidth": 8, "imageHeight": 9}) == {
        "name": "y.png", "width": 8, "height": 9, "detections": []}


def test_ac33_labelme_roundtrip_restores_bbox_cls_conf_one():
    # AC33:LabelMe round-trip 還原 bbox/cls;conf 一律 1.0(LabelMe 無 score)
    it = cocoio.from_labelme(cocoio.to_labelme(_IT1()))
    assert [d["bbox"] for d in it["detections"]] == [
        [10, 20, 30, 40], [50, 60, 10, 10], [0, 0, 5, 5]]
    assert [d["cls"] for d in it["detections"]] == ["scratch", "dent", "scratch"]
    assert all(d["conf"] == 1.0 for d in it["detections"])
    assert it["name"] == "a.png" and it["width"] == 200 and it["height"] == 100


# =====================================================================
# E. write/read COCO(Tier B,tmp_path 真實寫讀)
# =====================================================================

def test_ac34_write_coco_returns_path_and_creates_parent_dir(tmp_path):
    # AC34:write_coco 回路徑 + 檔存在(父目錄自動建立)
    p = str(tmp_path / "out" / "ann.json")
    ret = cocoio.write_coco(p, [_IT1(), _IT2()])
    assert ret == p
    assert os.path.exists(p) is True


def test_ac35_write_coco_disk_equals_to_coco_json(tmp_path):
    # AC35:磁碟內容 == to_coco 的 json(逐字 + round-trip 解析相等)
    p = str(tmp_path / "ann.json")
    cocoio.write_coco(p, [_IT1(), _IT2()])
    with open(p, "r", encoding="utf-8") as f:
        disk = f.read()
    assert disk == json.dumps(
        cocoio.to_coco([_IT1(), _IT2()]), ensure_ascii=False, indent=2)
    with open(p, encoding="utf-8") as f:
        assert json.load(f) == cocoio.to_coco([_IT1(), _IT2()])


def test_ac36_read_coco_roundtrip_equals_from_coco(tmp_path):
    # AC36:read_coco == from_coco∘to_coco;det 完整還原
    p = str(tmp_path / "ann.json")
    cocoio.write_coco(p, [_IT1(), _IT2()])
    got = cocoio.read_coco(p)
    assert got == cocoio.from_coco(cocoio.to_coco([_IT1(), _IT2()]))
    assert got[0]["detections"][0] == {
        "bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 0.9}


def test_ac37_read_coco_missing_or_bad_json_returns_empty(tmp_path):
    # AC37:缺檔 / 壞 JSON → [](不建檔、不丟錯)
    assert cocoio.read_coco(str(tmp_path / "nope.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert cocoio.read_coco(str(bad)) == []


def test_ac38_write_coco_empty_items(tmp_path):
    # AC38:空 items → 磁碟為三空 list;read_coco 回 []
    p = str(tmp_path / "empty.json")
    cocoio.write_coco(p, [])
    with open(p, encoding="utf-8") as f:
        assert json.load(f) == {"images": [], "annotations": [], "categories": []}
    assert cocoio.read_coco(p) == []


def test_ac39_write_coco_overwrite_semantics(tmp_path):
    # AC39:覆寫語義(後者完全覆寫,非附加)
    p = str(tmp_path / "ann.json")
    cocoio.write_coco(p, [_IT1(), _IT2()])
    cocoio.write_coco(p, [_IT2()])
    got = cocoio.read_coco(p)
    assert len(got) == 1
    assert got[0]["name"] == "b.png"


def test_ac40_write_coco_non_ascii_lossless(tmp_path):
    # AC40:non-ASCII 無損(中文 name/cls round-trip 不變)
    item = {"name": "圖.png", "width": 3, "height": 3,
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "刮傷", "conf": 0.5}]}
    p = str(tmp_path / "u.json")
    cocoio.write_coco(p, [item])
    got = cocoio.read_coco(p)
    assert got[0]["name"] == "圖.png"
    assert got[0]["detections"][0]["cls"] == "刮傷"


# =====================================================================
# F. write/read LabelMe(Tier B,tmp_path 真實寫讀)
# =====================================================================

def test_ac41_write_labelme_returns_path_and_disk_equals_json(tmp_path):
    # AC41:回路徑 + 父目錄自建 + 磁碟內容 == to_labelme 的 json
    p = str(tmp_path / "lm" / "a.json")
    ret = cocoio.write_labelme(p, _IT1())
    assert ret == p and os.path.exists(p)
    with open(p, "r", encoding="utf-8") as f:
        disk = f.read()
    assert disk == json.dumps(
        cocoio.to_labelme(_IT1()), ensure_ascii=False, indent=2)
    with open(p, encoding="utf-8") as f:
        assert json.load(f) == cocoio.to_labelme(_IT1())


def test_ac42_read_labelme_roundtrip_equals_from_labelme(tmp_path):
    # AC42:read_labelme == from_labelme∘to_labelme;bbox/cls 還原、conf=1.0
    p = str(tmp_path / "a.json")
    cocoio.write_labelme(p, _IT1())
    got = cocoio.read_labelme(p)
    assert got == cocoio.from_labelme(cocoio.to_labelme(_IT1()))
    assert got["detections"][0] == {
        "bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 1.0}


def test_ac43_read_labelme_missing_or_bad_returns_empty_item(tmp_path):
    # AC43:缺檔 / 壞 JSON → EMPTY_ITEM(不丟錯)
    assert cocoio.read_labelme(str(tmp_path / "nope.json")) == {
        "name": "", "width": 0, "height": 0, "detections": []}
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    assert cocoio.read_labelme(str(bad)) == {
        "name": "", "width": 0, "height": 0, "detections": []}


def test_ac44_write_labelme_non_ascii_lossless(tmp_path):
    # AC44:non-ASCII 無損(中文 name/cls;conf 回 1.0)
    item = {"name": "圖.png", "width": 3, "height": 3,
            "detections": [{"bbox": [0, 0, 1, 1], "cls": "刮傷", "conf": 0.5}]}
    p = str(tmp_path / "u.json")
    cocoio.write_labelme(p, item)
    got = cocoio.read_labelme(p)
    assert got["name"] == "圖.png"
    assert got["detections"][0]["cls"] == "刮傷"
    assert got["detections"][0]["conf"] == 1.0


# =====================================================================
# 推導 / property 測試(設計未明列;由契約推導,即使同源也能逼出實作 bug)
# =====================================================================

def test_invariant_to_coco_does_not_mutate_bbox_object(tmp_path):
    # 推導(§3.3「bbox: list(det["bbox"]) 複製」):to_coco 產出的 bbox 必須是
    # 與原 det 不同的物件(改 COCO bbox 不該回灌原 item)。比 AC10 多驗「物件身分」。
    it1 = _IT1()
    coco = cocoio.to_coco([it1])
    coco["annotations"][0]["bbox"][0] = 999
    assert it1["detections"][0]["bbox"][0] == 10  # 原物件未被改


def test_invariant_from_coco_never_raises_on_garbage():
    # 推導(§7「from_* 永不拋例外」):各種垃圾輸入皆回 [],不丟 exception。
    for bad in [None, 42, "x", [], {"images": "notalist"},
                {"images": [{"id": 1}], "annotations": "bad"},
                {"images": [{"id": 1}], "categories": "bad"}]:
        out = cocoio.from_coco(bad)
        assert isinstance(out, list)


def test_invariant_from_labelme_never_raises_on_garbage():
    # 推導(§7「from_* 永不拋例外」):非 dict / 壞 shapes 皆回 dict,不丟 exception。
    for bad in [None, 42, "x", [1, 2], {"shapes": "notalist"},
                {"shapes": [{"shape_type": "rectangle", "points": "bad"}]}]:
        out = cocoio.from_labelme(bad)
        assert isinstance(out, dict)
        assert set(out.keys()) == {"name", "width", "height", "detections"}


def test_invariant_coco_roundtrip_bbox_cls_conf_preserved():
    # 推導(§4 round-trip 不變式):對任意整數 bbox / [0,1] conf,
    # from_coco(to_coco([item])) 還原每筆 det 的 bbox(直通)、cls、conf(score 來回)。
    item = {"name": "z.png", "width": 7, "height": 8,
            "detections": [
                {"bbox": [3, 4, 5, 6], "cls": "foo", "conf": 0.33},
                {"bbox": [0, 0, 1, 1], "cls": "bar", "conf": 1.0}]}
    back = cocoio.from_coco(cocoio.to_coco([item]))[0]
    assert back["detections"] == item["detections"]
    assert back["name"] == "z.png" and back["width"] == 7 and back["height"] == 8


def test_invariant_to_labelme_does_not_mutate_input():
    # 推導(§2「純函式不就地改輸入」):to_labelme 不得 mutate 傳入 item。
    it1 = _IT1()
    before = copy.deepcopy(it1)
    cocoio.to_labelme(it1)
    assert it1 == before


def test_invariant_labelme_bbox_w_h_non_negative():
    # 推導(§5「min/abs 正規化 → w,h ≥ 0」):無論點順序,w/h 皆非負。
    for pts in [[[40, 60], [10, 20]], [[10, 20], [40, 60]],
                [[10, 60], [40, 20]], [[40, 20], [10, 60]]]:
        lm = {"shapes": [{"label": "x", "points": pts, "shape_type": "rectangle"}]}
        bbox = cocoio.from_labelme(lm)["detections"][0]["bbox"]
        assert bbox[2] >= 0 and bbox[3] >= 0
        assert bbox == [10, 20, 30, 40]
