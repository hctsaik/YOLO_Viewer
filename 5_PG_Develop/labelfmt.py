"""labelfmt — 多格式標註自動偵測(COCO / VOC / LabelMe / NDJSON)→ Detection。

/pg 產物,依 3_Architect_Design/26_labelfmt.md 契約。port 自使用者另一專案
`C:\\code\\claude\\LV\\visuallatent\\scripts\\label_formats.py`(純 stdlib + PIL、已測),
加一層 adapter 把 LV 的正規化 rows 轉成 CV_Viewer 既有的
`Detection = {"bbox":[x,y,w,h] 絕對像素 int, "cls":str, "conf":float}`。

**YOLO `.txt`/`.json` 不由本模組處理**(仍走 yolo.load);本模組只認 COCO/VOC/LabelMe/NDJSON。
統一入口 `load_for_image` 依 COCO→VOC→LabelMe→NDJSON 順序自動查:任一來源命中回該圖 list[Detection]、
找不到任何來源回 None(呼叫端退回 yolo.load)、有來源但該圖無框回 []。

依賴:json / functools / pathlib / xml.etree(標準庫)+ PIL。永不拋例外、不寫檔、不 mutate。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image


def _safe_read_text(path, default: str = "") -> str:
    """讀文字檔;壞編碼以 errors='ignore' 容忍,讀不到回 default。永不拋。"""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return default


def _pos(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


# ── adapter:LV 正規化 row (cid|None, cx, cy, w, h, score, name|None) → Detection ──
def _row_to_det(row, img_w, img_h):
    """正規化框(0~1)+ 影像尺寸 → 絕對像素 Detection。int 向 0 截斷(對齊 yolo.load §4.e)。"""
    cid, cx, cy, w, h, score, name = row
    x = int((cx - w / 2.0) * img_w)
    y = int((cy - h / 2.0) * img_h)
    bw = int(w * img_w)
    bh = int(h * img_h)
    if name:
        cls = str(name)
    elif cid is not None:
        cls = f"class_{cid}"
    else:
        cls = ""
    if score is None:
        conf = 1.0
    else:
        try:
            conf = float(score)
        except (TypeError, ValueError):
            conf = 1.0
        conf = 0.0 if conf < 0.0 else (1.0 if conf > 1.0 else conf)
    return {"bbox": [x, y, bw, bh], "cls": cls, "conf": conf}


# ── COCO JSON ────────────────────────────────────────────────────────────────
_COCO_FILENAMES = ("_annotations.coco.json", "annotations.json", "coco.json")


def coco_file_for_root(root: Path):
    """資料夾根層的 COCO 標註檔(Roboflow `_annotations.coco.json` 等常見名)。"""
    for name in _COCO_FILENAMES:
        p = Path(root) / name
        if p.exists():
            return p
    return None


@lru_cache(maxsize=16)
def _load_coco_cached(json_path_str: str, mtime_ns: int) -> dict:
    """COCO JSON → {"by_name": {檔名: [(cid,cx,cy,w,h,score,name),…]}, "names_by_id": {id:name}}。
    bbox 由絕對像素 [x,y,w,h] 用 images 的 width/height 正規化;缺尺寸/w≤0/h≤0 跳過。壞 JSON 回空。"""
    try:
        data = json.loads(_safe_read_text(Path(json_path_str)))
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"by_name": {}, "names_by_id": {}}
    if not isinstance(data, dict):
        return {"by_name": {}, "names_by_id": {}}
    cats = {int(c["id"]): str(c.get("name", f"class_{c['id']}"))
            for c in data.get("categories", []) if isinstance(c, dict) and "id" in c}
    imgs = {im.get("id"): im for im in data.get("images", []) if isinstance(im, dict)}
    by_name: dict = {}
    # 先把每張有登記的影像建空清單(有來源但該圖無框 → [])。
    for im in imgs.values():
        fn = Path(str(im.get("file_name", ""))).name
        if fn:
            by_name.setdefault(fn, [])
    for a in data.get("annotations", []):
        if not isinstance(a, dict):
            continue
        im = imgs.get(a.get("image_id"))
        bb = a.get("bbox")
        if not im or not isinstance(bb, (list, tuple)) or len(bb) < 4:
            continue
        W, H = im.get("width") or 0, im.get("height") or 0
        if not W or not H:
            continue
        try:
            x, y, w, h = (float(v) for v in bb[:4])
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        cid = int(a.get("category_id", -1))
        score = float(a["score"]) if "score" in a else None
        fname = Path(str(im.get("file_name", ""))).name
        by_name.setdefault(fname, []).append(
            (cid, (x + w / 2) / W, (y + h / 2) / H, w / W, h / H, score, cats.get(cid)))
    return {"by_name": by_name, "names_by_id": cats}


def _coco_for_image(image_path: Path):
    """影像所屬資料夾(本層或上一層)的 COCO 標註(涵蓋平鋪與 images/ 佈局)。"""
    for root in (image_path.parent, image_path.parent.parent):
        jf = coco_file_for_root(root)
        if jf:
            try:
                return _load_coco_cached(str(jf), jf.stat().st_mtime_ns)
            except OSError:
                return None
    return None


def coco_boxes_for_image(image_path: Path):
    """該影像的 COCO 框 rows;無 COCO 檔回 None(有檔但該影像無框回 [])。"""
    coco = _coco_for_image(Path(image_path))
    if coco is None:
        return None
    return coco["by_name"].get(Path(image_path).name, [])


# ── Pascal VOC XML ───────────────────────────────────────────────────────────
def _voc_xml_for_image(image_path: Path):
    """該影像的 VOC XML:同名(Roboflow VOC)或 Annotations/ 慣例(含經典 VOC JPEGImages/ 佈局)。"""
    ip = Path(image_path)
    for cand in (
        ip.with_suffix(".xml"),
        ip.parent / "Annotations" / f"{ip.stem}.xml",
        ip.parent / "annotations" / f"{ip.stem}.xml",
        ip.parent.parent / "Annotations" / f"{ip.stem}.xml",
        ip.parent.parent / "annotations" / f"{ip.stem}.xml",
    ):
        if cand.exists():
            return cand
    return None


def parse_voc_boxes(xml_path: Path, img_path: Path | None = None):
    """VOC XML → [(None, cx, cy, w, h, None, name), …]。<size> 缺就讀影像標頭補。壞 XML/影像回 []。"""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(_safe_read_text(Path(xml_path)))
    except ET.ParseError:
        return []
    W = H = 0
    size = root.find("size")
    if size is not None:
        try:
            W = int(float(size.findtext("width") or 0))
            H = int(float(size.findtext("height") or 0))
        except (TypeError, ValueError):
            W = H = 0
    if (not W or not H) and img_path is not None:
        try:
            with Image.open(img_path) as im:  # 只讀標頭取尺寸
                W, H = im.size
        except (OSError, Image.DecompressionBombError):
            return []
    if not W or not H:
        return []
    out = []
    for obj in root.iter("object"):
        name = (obj.findtext("name") or "").strip() or "unknown"
        bb = obj.find("bndbox")
        if bb is None:
            continue
        try:
            x0 = float(bb.findtext("xmin") or "")
            y0 = float(bb.findtext("ymin") or "")
            x1 = float(bb.findtext("xmax") or "")
            y1 = float(bb.findtext("ymax") or "")
        except (TypeError, ValueError):
            continue
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            continue
        out.append((None, (x0 + x1) / 2 / W, (y0 + y1) / 2 / H, w / W, h / H, None, name))
    return out


# ── LabelMe JSON ─────────────────────────────────────────────────────────────
def parse_labelme_boxes(json_path: Path):
    """LabelMe .json → [(None, cx, cy, w, h, None, label), …];rectangle 兩角、polygon 取外接框。
    非 LabelMe 結構(無 shapes list)回 None(讓呼叫端試其他來源)。"""
    try:
        data = json.loads(_safe_read_text(Path(json_path)))
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
        return None
    W = data.get("imageWidth") or 0
    H = data.get("imageHeight") or 0
    if not W or not H:
        return []
    out = []
    for s in data["shapes"]:
        if not isinstance(s, dict):
            continue
        pts = s.get("points") or []
        if not isinstance(pts, list) or len(pts) < 2:
            continue
        try:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
        except (TypeError, ValueError, IndexError):
            continue
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            continue
        out.append((None, (x0 + x1) / 2 / W, (y0 + y1) / 2 / H,
                    w / W, h / H, None, str(s.get("label") or "unknown")))
    return out


# ── NDJSON / JSONL ───────────────────────────────────────────────────────────
_NDJSON_IMG_KEYS = ("image", "image_path", "file_name", "filename", "source-ref", "path")
_NDJSON_BOX_KEYS = ("boxes", "annotations", "objects", "bboxes")
_NDJSON_LABEL_KEYS = ("label", "class", "name", "category")
_NDJSON_EXCLUDE = {"manifest.jsonl"}  # 資料契約檔(path/sha…),非標註


@lru_cache(maxsize=32)
def _ndjson_qualifies(path_str: str, mtime_ns: int) -> bool:
    """抽樣前 50 行:至少一行同時有影像鍵 + 「含 dict 的框清單」才算標註檔。
    擋掉只有 path/sha 的資料契約類 jsonl(如 manifest.jsonl)。"""
    text = _safe_read_text(Path(path_str))
    for line in text.splitlines()[:50]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if not any(isinstance(row.get(k), str) and row.get(k) for k in _NDJSON_IMG_KEYS):
            continue
        if any(isinstance(row.get(k), list)
               and any(isinstance(x, dict) for x in row[k])
               for k in _NDJSON_BOX_KEYS):
            return True
    return False


def ndjson_file_for_root(root: Path):
    """資料夾根層的 NDJSON/JSONL 標註檔(內容驗證過;取字典序第一個合格者)。"""
    root = Path(root)
    if not root.is_dir():
        return None
    for pat in ("*.ndjson", "*.jsonl"):
        for p in sorted(root.glob(pat)):
            if p.name.lower() in _NDJSON_EXCLUDE:
                continue
            try:
                if _ndjson_qualifies(str(p), p.stat().st_mtime_ns):
                    return p
            except OSError:
                continue
    return None


@lru_cache(maxsize=16)
def _load_ndjson_cached(json_path_str: str, mtime_ns: int) -> dict:
    """NDJSON(一行一影像)→ {"by_name": {檔名: [(None,cx,cy,w,h,score,label),…]}}。
    寬容 schema:影像鍵/框清單鍵/label 別名見常數;bbox 收四種慣例
    (bbox=[x,y,w,h] 像素、xmin/ymin/xmax/ymax、left/top/width/height、cx/cy/w/h 0-1)。壞行跳過。"""
    by_name: dict = {}
    text = _safe_read_text(Path(json_path_str))
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        fname = next((Path(str(row[k]).replace("\\", "/")).name
                      for k in _NDJSON_IMG_KEYS
                      if isinstance(row.get(k), str) and row.get(k)), None)
        if not fname:
            continue
        W, H = row.get("width") or 0, row.get("height") or 0
        if not W or not H:
            isz = row.get("image_size")
            if isinstance(isz, list) and isz and isinstance(isz[0], dict):
                W, H = isz[0].get("width") or 0, isz[0].get("height") or 0
        boxes = next((row[k] for k in _NDJSON_BOX_KEYS if isinstance(row.get(k), list)), [])
        rows = []
        for b in boxes:
            if not isinstance(b, dict):
                continue
            label = next((str(b[k]) for k in _NDJSON_LABEL_KEYS if b.get(k)), None)
            if label is None and b.get("class_id") is not None:
                label = f"class_{b['class_id']}"
            label = label or "unknown"
            got = None
            try:
                bb = b.get("bbox")
                if isinstance(bb, list) and len(bb) >= 4 and W and H:
                    x, y, w, h = (float(v) for v in bb[:4])
                    if w > 0 and h > 0:
                        got = ((x + w / 2) / W, (y + h / 2) / H, w / W, h / H)
                if got is None and W and H and all(
                        k in b for k in ("xmin", "ymin", "xmax", "ymax")):
                    x0, y0 = float(b["xmin"]), float(b["ymin"])
                    x1, y1 = float(b["xmax"]), float(b["ymax"])
                    if x1 > x0 and y1 > y0:
                        got = ((x0 + x1) / 2 / W, (y0 + y1) / 2 / H,
                               (x1 - x0) / W, (y1 - y0) / H)
                if got is None and W and H and all(
                        k in b for k in ("left", "top", "width", "height")):
                    x, y = float(b["left"]), float(b["top"])
                    w, h = float(b["width"]), float(b["height"])
                    if w > 0 and h > 0:
                        got = ((x + w / 2) / W, (y + h / 2) / H, w / W, h / H)
                if got is None and all(k in b for k in ("cx", "cy", "w", "h")):
                    cx, cy = float(b["cx"]), float(b["cy"])
                    w, h = float(b["w"]), float(b["h"])
                    if 0 < w <= 1 and 0 < h <= 1 and 0 <= cx <= 1 and 0 <= cy <= 1:
                        got = (cx, cy, w, h)
            except (TypeError, ValueError):
                continue
            if got:
                rows.append((None, *got, None, label))
        by_name[fname] = rows  # 空也記:有來源但該影像無框
    return {"by_name": by_name}


# ── 統一入口(rows)──────────────────────────────────────────────────────────
def _annotation_boxes_for_image(image_path: Path):
    """COCO → VOC → LabelMe → NDJSON 依序查;回 rows 或 None(找不到任何來源)。"""
    ip = Path(image_path)
    rows = coco_boxes_for_image(ip)
    if rows is not None:
        return rows
    xml = _voc_xml_for_image(ip)
    if xml is not None:
        return parse_voc_boxes(xml, ip)
    lm = ip.with_suffix(".json")
    if lm.exists():
        rows = parse_labelme_boxes(lm)
        if rows is not None:
            return rows
    for root in (ip.parent, ip.parent.parent):
        nd = ndjson_file_for_root(root)
        if nd:
            try:
                data = _load_ndjson_cached(str(nd), nd.stat().st_mtime_ns)
            except OSError:
                return None
            return data["by_name"].get(ip.name, [])
    return None


# ── 對外契約 ─────────────────────────────────────────────────────────────────
def load_for_image(image_path, img_w, img_h):
    """多格式標註(COCO/VOC/LabelMe/NDJSON)自動偵測 → list[Detection] | None。

    None = 找不到任何(非 YOLO-txt)標註來源(呼叫端退回 yolo.load);
    []   = 有來源但該影像無框;img_w/img_h = 目前顯示影像實際寬高(把正規化框換算絕對像素)。
    """
    rows = _annotation_boxes_for_image(Path(image_path))
    if rows is None:
        return None
    if not _pos(img_w) or not _pos(img_h):
        return []
    return [_row_to_det(r, img_w, img_h) for r in rows]


def folder_has_annotations(folder, probe: int = 25) -> bool:
    """資料夾是否帶任一支援的(非 YOLO-txt)標註(供 sidebar 標示偵測到的格式)。"""
    folder = Path(folder)
    if coco_file_for_root(folder) or ndjson_file_for_root(folder):
        return True
    for sub in ("Annotations", "annotations"):
        d = folder / sub
        if d.is_dir() and next(iter(d.glob("*.xml")), None) is not None:
            return True
    base = next((folder / s for s in ("images", "JPEGImages")
                 if (folder / s).is_dir()), folder)
    n = 0
    if base.is_dir():
        for p in sorted(base.iterdir()):
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            if _annotation_boxes_for_image(p) is not None:
                return True
            n += 1
            if n >= probe:
                break
    return False
