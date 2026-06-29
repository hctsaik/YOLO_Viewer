"""cocoio:內部 item(含 Detection 清單)與 COCO / LabelMe 標註格式的雙向轉換 + 薄檔案讀寫。

設計來源:3_Architect_Design/15_cocoio.md(§3 I/O 契約、§3.1~§3.9 釘死規則、§5 邊界、§6 AC1..AC44)。

僅用 Python 標準庫(json/os)。不 import 任何上游模組(yolo/sidecar/overlay/casepkg)。
to_* / from_* 為純函式、不 mutate 輸入;write_* / read_* 為薄 I/O 包裝(UTF-8、父目錄自建、容錯讀)。
from_* 永不拋例外(壞輸入回 [] / EMPTY_ITEM)。
"""
import json
import os

# §3.8 空 / 容錯回傳常數(釘死)。
EMPTY_ITEM = {"name": "", "width": 0, "height": 0, "detections": []}


# ---------------------------------------------------------------------------
# 內部小工具
# ---------------------------------------------------------------------------

def _is_number(v):
    """v 是可作數值的型別(int/float 但非 bool)。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# COCO 方向
# ---------------------------------------------------------------------------

def to_coco(items, categories=None):
    """一批內部 item → 單一 COCO dict(§3.3)。

    categories=None → 由 det.cls 首見順序自動導出(§3.4);
    categories 給 list[str] → 依清單順序由 id=1 編號,未在清單的 det 跳過(§3.4)。
    鍵順序釘死:["images","annotations","categories"]。
    """
    # 1) 建 cls→category_id 映射(§3.4)。
    if categories is None:
        # 自動導出:掃所有 det.cls,去重保留首見順序,id 由 1 起。
        cls_to_id = {}
        cat_list = []
        for item in items:
            for det in item.get("detections", []) or []:
                cls = det.get("cls", "")
                if cls not in cls_to_id:
                    cls_to_id[cls] = len(cat_list) + 1
                    cat_list.append({"id": cls_to_id[cls], "name": cls})
    else:
        # 給定清單:依清單順序由 id=1 起;即使無 det 也列出。
        cls_to_id = {}
        cat_list = []
        for name in categories:
            if name not in cls_to_id:
                cls_to_id[name] = len(cat_list) + 1
                cat_list.append({"id": cls_to_id[name], "name": name})

    images = []
    annotations = []
    ann_id = 1  # 全域、跨影像扁平遞增(§3.3)。
    for idx, item in enumerate(items):
        image_id = idx + 1  # image id 1-based 依 items 順序(§3.3)。
        images.append({
            "id": image_id,
            "file_name": item.get("name", ""),
            "width": item.get("width", 0),
            "height": item.get("height", 0),
        })
        for det in item.get("detections", []) or []:
            cls = det.get("cls", "")
            if cls not in cls_to_id:
                # cls 不在映射(僅 categories 給定時可能)→ 跳過該 annotation(image 仍出)。
                continue
            bbox = list(det["bbox"])  # 複製,不 mutate 原 det。
            annotations.append({
                "id": ann_id,
                "image_id": image_id,
                "category_id": cls_to_id[cls],
                "bbox": bbox,
                "area": float(bbox[2]) * float(bbox[3]),  # w*h,float(§3.3)。
                "iscrowd": 0,
                "score": float(det["conf"]),
            })
            ann_id += 1

    return {"images": images, "annotations": annotations, "categories": cat_list}


def from_coco(coco):
    """COCO dict → list[內部 item](§3.5,容錯)。非 dict / 缺 images / images 非 list → []。"""
    if not isinstance(coco, dict):
        return []
    images = coco.get("images")
    if not isinstance(images, list):
        return []

    # category_id → name 映射(categories 缺/非 list → 空映射,所有 id 查無 → cls="")。
    cat_map = {}
    categories = coco.get("categories")
    if isinstance(categories, list):
        for cat in categories:
            if isinstance(cat, dict) and "id" in cat:
                cat_map[cat.get("id")] = str(cat.get("name", ""))

    # image_id → item(保留 images 順序)。
    items = []
    id_to_item = {}
    for image in images:
        if not isinstance(image, dict):
            # 非 dict 的 image 視為缺鍵套預設;仍佔一個 item 位置但無有效 id 對應。
            item = {"name": "", "width": 0, "height": 0, "detections": []}
            items.append(item)
            continue
        item = {
            "name": image.get("file_name", ""),
            "width": image.get("width", 0),
            "height": image.get("height", 0),
            "detections": [],
        }
        items.append(item)
        img_id = image.get("id")
        if img_id is not None:
            id_to_item[img_id] = item

    # annotations 缺/非 list → 每 image 仍為空 det。
    annotations = coco.get("annotations")
    if isinstance(annotations, list):
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            image_id = ann.get("image_id")
            target = id_to_item.get(image_id)
            if target is None:
                # image_id 不對應任何 image → 跳過(§3.5)。
                continue
            det = _ann_to_detection(ann, cat_map)
            if det is not None:
                target["detections"].append(det)

    return items


def _ann_to_detection(ann, cat_map):
    """單筆 annotation → Detection;壞 bbox 回 None(跳過)。"""
    raw_bbox = ann.get("bbox")
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None  # 缺 / 非長度 4 → 跳過。
    bbox = []
    for v in raw_bbox:
        if not _is_number(v):
            return None  # 含非數值 → 跳過。
        try:
            bbox.append(int(v))  # 向 0 截斷。
        except (ValueError, TypeError):
            return None

    # cls:category_id 查 cat_map;缺/查無 → ""。
    cat_id = ann.get("category_id")
    cls = cat_map.get(cat_id, "") if cat_id is not None else ""

    # conf:float(score);缺/轉型失敗 → 1.0。
    if "score" in ann:
        try:
            conf = float(ann["score"])
        except (ValueError, TypeError):
            conf = 1.0
    else:
        conf = 1.0

    return {"bbox": bbox, "cls": cls, "conf": conf}


# ---------------------------------------------------------------------------
# LabelMe 方向
# ---------------------------------------------------------------------------

def to_labelme(item):
    """單一內部 item → LabelMe dict(§3.6)。鍵順序釘死;conf 不導出。"""
    shapes = []
    for det in item.get("detections", []) or []:
        bbox = det["bbox"]
        x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
        shapes.append({
            "label": det.get("cls", ""),
            "points": [[x, y], [x + w, y + h]],  # 兩點:左上、右下(原值,不取整)。
            "group_id": None,
            "shape_type": "rectangle",
            "flags": {},
        })
    return {
        "version": "5.0.1",
        "flags": {},
        "shapes": shapes,
        "imagePath": item.get("name", ""),
        "imageData": None,
        "imageHeight": item.get("height", 0),
        "imageWidth": item.get("width", 0),
    }


def from_labelme(lm):
    """單一 LabelMe dict → 單一內部 item(§3.7,容錯)。非 dict → EMPTY_ITEM。"""
    if not isinstance(lm, dict):
        return dict(EMPTY_ITEM, detections=[])  # 值相等的新物件。

    detections = []
    shapes = lm.get("shapes")
    if isinstance(shapes, list):
        for shape in shapes:
            det = _shape_to_detection(shape)
            if det is not None:
                detections.append(det)

    return {
        "name": lm.get("imagePath", ""),
        "width": lm.get("imageWidth", 0),
        "height": lm.get("imageHeight", 0),
        "detections": detections,
    }


def _shape_to_detection(shape):
    """單一 LabelMe shape → Detection;非 rectangle / 壞點回 None(跳過)。"""
    if not isinstance(shape, dict):
        return None
    if shape.get("shape_type") != "rectangle":
        return None  # 非 rectangle(polygon/circle...)→ 跳過。

    points = shape.get("points")
    if not isinstance(points, (list, tuple)) or len(points) != 2:
        return None  # 點數 ≠ 2 → 跳過。
    pa, pb = points[0], points[1]
    if (not isinstance(pa, (list, tuple)) or len(pa) != 2
            or not isinstance(pb, (list, tuple)) or len(pb) != 2):
        return None  # 點非長度 2 → 跳過。
    ax, ay = pa[0], pa[1]
    bx, by = pb[0], pb[1]
    if not (_is_number(ax) and _is_number(ay) and _is_number(bx) and _is_number(by)):
        return None  # 含非數值 → 跳過。

    # min/abs 正規化(不假設哪點是左上);各值取 int(向 0 截斷)。
    x = int(min(ax, bx))
    y = int(min(ay, by))
    w = int(abs(bx - ax))
    h = int(abs(by - ay))
    cls = str(shape.get("label", "")) if "label" in shape else ""
    return {"bbox": [x, y, w, h], "cls": cls, "conf": 1.0}


# ---------------------------------------------------------------------------
# 薄檔案 I/O(§3.9,Tier B)
# ---------------------------------------------------------------------------

def _ensure_parent(path):
    """父目錄不存在則建立。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def write_coco(path, items, categories=None):
    """to_coco(items, categories) → json 寫到 path(UTF-8、ensure_ascii=False、indent=2)。回傳 path。"""
    _ensure_parent(path)
    data = json.dumps(to_coco(items, categories), ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return path


def read_coco(path):
    """讀 path 的 COCO json → from_coco。檔不存在 / 壞 JSON / 非 dict → []。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return from_coco(data)


def write_labelme(path, item):
    """to_labelme(item) → json 寫到 path(UTF-8、ensure_ascii=False、indent=2)。回傳 path。"""
    _ensure_parent(path)
    data = json.dumps(to_labelme(item), ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return path


def read_labelme(path):
    """讀 path 的 LabelMe json → from_labelme。檔不存在 / 壞 JSON / 非 dict → EMPTY_ITEM。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return dict(EMPTY_ITEM, detections=[])
    if not isinstance(data, dict):
        return dict(EMPTY_ITEM, detections=[])
    return from_labelme(data)
