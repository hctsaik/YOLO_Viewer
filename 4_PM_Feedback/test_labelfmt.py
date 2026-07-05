"""labelfmt 驗收測試(對應設計 3_Architect_Design/26_labelfmt.md 的 AC1–AC21)。

port 自 LV/visuallatent 的多格式標註自動偵測(COCO / VOC / LabelMe / NDJSON),
加一層 adapter 轉成 CV_Viewer 的 Detection 形狀。合成資料建在 tmp_path,真實寫讀驗證。

跑法:pytest 4_PM_Feedback/test_labelfmt.py -v;閘門:python verify/gate.py labelfmt
"""
import json

import pytest
from PIL import Image

import labelfmt


# ============================== 共用 fixture ==============================
def _mk_img(p, w=64, h=48, color=(120, 160, 200)):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color).save(p)


def _is_det(d):
    """一筆合法 Detection:恰三鍵、bbox 四個 int、cls str、conf float∈[0,1]。"""
    return (isinstance(d, dict) and set(d) == {"bbox", "cls", "conf"}
            and isinstance(d["bbox"], list) and len(d["bbox"]) == 4
            and all(isinstance(v, int) for v in d["bbox"])
            and isinstance(d["cls"], str)
            and isinstance(d["conf"], float) and 0.0 <= d["conf"] <= 1.0)


# ============================== AC1-3 — adapter(正規化 row → Detection)==============================
def test_ac1_row_to_det_canonical():  # AC1
    # 正規化框 (0.25,0.25,0.25,0.25) @64x48 → 絕對 [8,6,16,12];name/score 帶入。
    det = labelfmt._row_to_det((7, 0.25, 0.25, 0.25, 0.25, 0.9, "cat"), 64, 48)
    assert det == {"bbox": [8, 6, 16, 12], "cls": "cat", "conf": 0.9}


def test_ac2_row_to_det_no_name_no_score():  # AC2
    det = labelfmt._row_to_det((None, 0.5, 0.5, 0.5, 0.5, None, None), 100, 100)
    assert det["bbox"] == [25, 25, 50, 50]
    assert det["cls"] == ""
    assert det["conf"] == 1.0


def test_ac3_row_to_det_cid_fills_name():  # AC3
    det = labelfmt._row_to_det((3, 0.5, 0.5, 0.2, 0.2, None, None), 50, 50)
    assert det["cls"] == "class_3"


# ============================== AC4-6 — COCO JSON ==============================
def _write_coco_flat(root):
    """Roboflow 平鋪:影像在根層 + _annotations.coco.json;類名 id=7 cat / id=9 dog(非連號)。"""
    for n in ("a.jpg", "b.jpg", "c.jpg"):
        _mk_img(root / n)
    coco = {
        "images": [{"id": 1, "file_name": "a.jpg", "width": 64, "height": 48},
                   {"id": 2, "file_name": "b.jpg", "width": 64, "height": 48},
                   {"id": 3, "file_name": "c.jpg", "width": 64, "height": 48}],
        "categories": [{"id": 7, "name": "cat"}, {"id": 9, "name": "dog"}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 7, "bbox": [8, 6, 16, 12]},
            {"id": 2, "image_id": 1, "category_id": 9, "bbox": [32, 24, 16, 12]},
            {"id": 3, "image_id": 2, "category_id": 9, "bbox": [4, 4, 24, 20]},
        ],
    }
    (root / "_annotations.coco.json").write_text(json.dumps(coco), encoding="utf-8")


def test_ac4_coco_flat(tmp_path):  # AC4
    _write_coco_flat(tmp_path)
    dets_a = labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48)
    assert dets_a is not None and len(dets_a) == 2
    assert all(_is_det(d) for d in dets_a)
    assert {d["cls"] for d in dets_a} == {"cat", "dog"}      # 類名取自 categories(非 id)
    cat = next(d for d in dets_a if d["cls"] == "cat")
    assert cat["bbox"] == [8, 6, 16, 12]                     # 絕對框正確
    # c.jpg 有來源但無標註 → []
    assert labelfmt.load_for_image(tmp_path / "c.jpg", 64, 48) == []


def test_ac5_coco_images_layout(tmp_path):  # AC5
    (tmp_path / "images").mkdir()
    for n in ("a.jpg",):
        _mk_img(tmp_path / "images" / n)
    coco = {"images": [{"id": 1, "file_name": "a.jpg", "width": 64, "height": 48}],
            "categories": [{"id": 0, "name": "obj"}],
            "annotations": [{"id": 1, "image_id": 1, "category_id": 0, "bbox": [8, 6, 16, 12]}]}
    (tmp_path / "coco.json").write_text(json.dumps(coco), encoding="utf-8")  # 上一層
    dets = labelfmt.load_for_image(tmp_path / "images" / "a.jpg", 64, 48)
    assert dets is not None and len(dets) == 1 and dets[0]["cls"] == "obj"


def test_ac6_coco_score_to_conf(tmp_path):  # AC6
    _mk_img(tmp_path / "a.jpg")
    coco = {"images": [{"id": 1, "file_name": "a.jpg", "width": 64, "height": 48}],
            "categories": [{"id": 0, "name": "obj"}],
            "annotations": [
                {"id": 1, "image_id": 1, "category_id": 0, "bbox": [8, 6, 16, 12], "score": 0.8},
                {"id": 2, "image_id": 1, "category_id": 0, "bbox": [32, 24, 8, 8]}]}
    (tmp_path / "annotations.json").write_text(json.dumps(coco), encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48)
    confs = sorted(d["conf"] for d in dets)
    assert confs == [0.8, 1.0]                               # 有 score→0.8;無→1.0


# ============================== AC7-9 — Pascal VOC XML ==============================
_VOC_XML = """<annotation>
  <size><width>{W}</width><height>{H}</height></size>
  <object><name>cat</name>
    <bndbox><xmin>0</xmin><ymin>0</ymin><xmax>16</xmax><ymax>12</ymax></bndbox>
  </object>
</annotation>"""


def test_ac7_voc_sibling_xml(tmp_path):  # AC7
    _mk_img(tmp_path / "x.jpg")
    (tmp_path / "x.xml").write_text(_VOC_XML.format(W=64, H=48), encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "x.jpg", 64, 48)
    assert dets is not None and len(dets) == 1
    assert dets[0]["cls"] == "cat" and dets[0]["bbox"] == [0, 0, 16, 12]


def test_ac8_voc_no_size_reads_image(tmp_path):  # AC8
    _mk_img(tmp_path / "x.jpg", 64, 48)
    xml = "<annotation><object><name>cat</name><bndbox>" \
          "<xmin>0</xmin><ymin>0</ymin><xmax>16</xmax><ymax>12</ymax></bndbox></object></annotation>"
    (tmp_path / "x.xml").write_text(xml, encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "x.jpg", 64, 48)
    assert dets is not None and len(dets) == 1 and dets[0]["bbox"] == [0, 0, 16, 12]


def test_ac9_voc_annotations_dir(tmp_path):  # AC9
    (tmp_path / "JPEGImages").mkdir()
    (tmp_path / "Annotations").mkdir()
    _mk_img(tmp_path / "JPEGImages" / "x.jpg")
    (tmp_path / "Annotations" / "x.xml").write_text(_VOC_XML.format(W=64, H=48), encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "JPEGImages" / "x.jpg", 64, 48)
    assert dets is not None and len(dets) == 1 and dets[0]["cls"] == "cat"


# ============================== AC10-12 — LabelMe JSON ==============================
def test_ac10_labelme_rectangle(tmp_path):  # AC10
    _mk_img(tmp_path / "x.jpg")
    lm = {"imageWidth": 64, "imageHeight": 48,
          "shapes": [{"label": "cat", "shape_type": "rectangle",
                      "points": [[8, 6], [24, 18]]}]}
    (tmp_path / "x.json").write_text(json.dumps(lm), encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "x.jpg", 64, 48)
    assert dets is not None and len(dets) == 1
    assert dets[0]["cls"] == "cat" and dets[0]["bbox"] == [8, 6, 16, 12]


def test_ac11_labelme_polygon_bbox(tmp_path):  # AC11
    _mk_img(tmp_path / "x.jpg")
    lm = {"imageWidth": 64, "imageHeight": 48,
          "shapes": [{"label": "poly", "shape_type": "polygon",
                      "points": [[8, 6], [24, 6], [24, 18], [8, 18]]}]}  # 外接框 = [8,6,16,12]
    (tmp_path / "x.json").write_text(json.dumps(lm), encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "x.jpg", 64, 48)
    assert dets is not None and dets[0]["bbox"] == [8, 6, 16, 12]


def test_ac12_non_labelme_json_returns_none(tmp_path):  # AC12
    # 一個沒有 shapes 的 .json(YOLO 風 dict)→ parse_labelme_boxes 回 None(不吞掉)。
    (tmp_path / "x.json").write_text(json.dumps({"detections": []}), encoding="utf-8")
    assert labelfmt.parse_labelme_boxes(tmp_path / "x.json") is None


# ============================== AC13-16 — NDJSON / JSONL ==============================
def test_ac13_ndjson_bbox_pixel(tmp_path):  # AC13
    _mk_img(tmp_path / "a.jpg")
    row = {"image": "a.jpg", "width": 64, "height": 48,
           "boxes": [{"bbox": [8, 6, 16, 12], "label": "cat"}]}
    (tmp_path / "labels.ndjson").write_text(json.dumps(row) + "\n", encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48)
    assert dets is not None and len(dets) == 1
    assert dets[0]["cls"] == "cat" and dets[0]["bbox"] == [8, 6, 16, 12]


def test_ac14_ndjson_four_bbox_conventions(tmp_path):  # AC14
    _mk_img(tmp_path / "a.jpg")
    rows = [
        {"image": "a.jpg", "width": 64, "height": 48,
         "boxes": [{"xmin": 8, "ymin": 6, "xmax": 24, "ymax": 18, "label": "xyxy"}]},
        {"image": "b.jpg", "width": 64, "height": 48,
         "boxes": [{"left": 8, "top": 6, "width": 16, "height": 12, "label": "ltwh"}]},
        {"image": "c.jpg",
         "boxes": [{"cx": 0.25, "cy": 0.25, "w": 0.25, "h": 0.25, "label": "cxcywh"}]},
    ]
    for n in ("b.jpg", "c.jpg"):
        _mk_img(tmp_path / n)
    (tmp_path / "labels.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    for name, lbl in (("a.jpg", "xyxy"), ("b.jpg", "ltwh"), ("c.jpg", "cxcywh")):
        dets = labelfmt.load_for_image(tmp_path / name, 64, 48)
        assert dets is not None and len(dets) == 1, (name, dets)
        assert dets[0]["cls"] == lbl and dets[0]["bbox"] == [8, 6, 16, 12], (name, dets)


def test_ac15_ndjson_excludes_manifest(tmp_path):  # AC15
    # manifest.jsonl(只有 path/sha,無框清單)不得被當標註來源。
    _mk_img(tmp_path / "a.jpg")
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps({"path": "a.jpg", "sha": "deadbeef"}) + "\n", encoding="utf-8")
    assert labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48) is None


def test_ac16_ndjson_label_aliases_and_class_id(tmp_path):  # AC16
    _mk_img(tmp_path / "a.jpg")
    _mk_img(tmp_path / "b.jpg")
    rows = [
        {"image": "a.jpg", "width": 64, "height": 48,
         "boxes": [{"bbox": [8, 6, 16, 12], "category": "aliased"}]},
        {"image": "b.jpg", "width": 64, "height": 48,
         "boxes": [{"bbox": [8, 6, 16, 12], "class_id": 2}]},
    ]
    (tmp_path / "d.ndjson").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48)[0]["cls"] == "aliased"
    assert labelfmt.load_for_image(tmp_path / "b.jpg", 64, 48)[0]["cls"] == "class_2"


# ============================== AC17 — 優先序 ==============================
def test_ac17_coco_precedence_over_labelme(tmp_path):  # AC17
    _mk_img(tmp_path / "a.jpg")
    coco = {"images": [{"id": 1, "file_name": "a.jpg", "width": 64, "height": 48}],
            "categories": [{"id": 0, "name": "from_coco"}],
            "annotations": [{"id": 1, "image_id": 1, "category_id": 0, "bbox": [8, 6, 16, 12]}]}
    (tmp_path / "coco.json").write_text(json.dumps(coco), encoding="utf-8")
    lm = {"imageWidth": 64, "imageHeight": 48,
          "shapes": [{"label": "from_labelme", "points": [[8, 6], [24, 18]]}]}
    (tmp_path / "a.json").write_text(json.dumps(lm), encoding="utf-8")
    dets = labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48)
    assert dets is not None and dets[0]["cls"] == "from_coco"    # COCO 先於 LabelMe


# ============================== AC18 — 無來源回 None ==============================
def test_ac18_no_source_returns_none(tmp_path):  # AC18
    _mk_img(tmp_path / "a.jpg")
    (tmp_path / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")  # 只有 YOLO txt
    assert labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48) is None


# ============================== AC19 — 永不拋(壞輸入)==============================
@pytest.mark.parametrize("payload,fname", [
    ("{ not json", "_annotations.coco.json"),
    ("<annotation><object><name>x</name></object", "x.xml"),   # 壞 XML(無 bndbox/壞結構)
    ("", "coco.json"),                                          # 空檔
])
def test_ac19_never_raises_on_garbage(tmp_path, payload, fname):  # AC19
    _mk_img(tmp_path / "x.jpg")
    (tmp_path / fname).write_text(payload, encoding="utf-8")
    # 不論回 None 或 [],都不得拋例外
    res = labelfmt.load_for_image(tmp_path / "x.jpg", 64, 48)
    assert res is None or isinstance(res, list)


# ============================== AC20 — 純讀不 mutate ==============================
def test_ac20_pure_read_no_file_mutation(tmp_path):  # AC20
    _write_coco_flat(tmp_path)
    coco_path = tmp_path / "_annotations.coco.json"
    before = coco_path.read_bytes()
    labelfmt.load_for_image(tmp_path / "a.jpg", 64, 48)
    labelfmt.folder_has_annotations(tmp_path)
    assert coco_path.read_bytes() == before      # 位元不變(讀不寫)


# ============================== AC21 — folder_has_annotations ==============================
def test_ac21_folder_has_annotations(tmp_path):  # AC21
    # 空夾 / 只有 YOLO txt → False
    empty = tmp_path / "empty"
    empty.mkdir()
    _mk_img(empty / "a.jpg")
    assert labelfmt.folder_has_annotations(empty) is False
    (empty / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    assert labelfmt.folder_has_annotations(empty) is False    # YOLO txt 不算(走 yolo 路徑)
    # 有 COCO → True
    coco_dir = tmp_path / "coco"
    coco_dir.mkdir()
    _write_coco_flat(coco_dir)
    assert labelfmt.folder_has_annotations(coco_dir) is True
