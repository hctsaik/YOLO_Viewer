# 設計:`cocoio`(M5 / Tier B — 互通格式雙向轉換 + 薄檔案讀寫,需真實讀寫驗收)

> `/architect` 產物(module 粒度)。對應 `ROADMAP.md` 第 58 行 M5 `cocoio`、第 63-66 行跨模組 `Detection` 契約、第 133-135 行 PO M5 釘契約(COCO 原生 xywh 直通、cls↔category_id 映射釘死)。
> 上游資料形狀:PO 釘死的 `Detection` 形狀(`{"bbox":[x,y,w,h]絕對像素, "cls":str, "conf":float}`),與 `casepkg`(`3_Architect_Design/11`)同精神「只吃/吐 dict」。
> 本檔只定義契約與驗收,**不含任何實作**。實作由 `/pg` 寫進 `5_PG_Develop/cocoio.py`。
> 風格與 `casepkg` 對齊:純函式 + 薄 I/O 包裝,Tier B 用 `tmp_path` 真實寫讀 + json round-trip 釘死。

## 模組邊界 sanity check(開工前一句)

`cocoio` 一句話可講完:「在『我們的內部表示(item dict + `Detection` 清單)』與『COCO / LabelMe 標註格式』之間做**雙向、無損(就 bbox/cls 而言)** 的純資料轉換,再加一層薄檔案讀寫,供資料回流(把人工複審結果匯出給標註工具 / 把外部標註匯入回我們)」。
它**只消費/產出 dict**(`item["detections"]` 為一串 `Detection`、COCO/LabelMe 皆 dict),**不 import** `yolo`/`sidecar`/`overlay`/`casepkg` 任一實作 —— 完全靠資料形狀解耦,故可獨立設計、可用 `tmp_path` 真實 round-trip 驗收。
與 `casepkg` 不同:`casepkg` 是**我們自家**的扁平 CSV + 巢狀 JSON 摘要(對內);`cocoio` 是**標準互通格式**(對外標註生態系 COCO/LabelMe),兩者責任不同、不該合併。亦無須再拆:COCO 與 LabelMe 共享「同一組內部 item 形狀 + 同一個 bbox 直通規則」,內聚於「標註格式互通」單一責任。**結論:範圍 OK,不退回 `/po`。**

---

## 1. 目的 (Purpose)

把一批內部 item(每個含 `name/width/height/detections`)**雙向轉換**成兩種業界標準標註格式 —— **COCO**(單一聚合 dict,多影像)與 **LabelMe**(每影像一份 dict),並提供薄檔案讀寫(`write_coco`/`read_coco`/`write_labelme`/`read_labelme`),供「人工複審後的偵測結果回流到標註工具,或外部標註匯入回我們」。**只讀/寫傳入的 dict 與指定路徑,絕不讀寫原始影像、不 import 任何上游模組。**

---

## 2. 相依與限制

- 僅用 Python 標準庫:`json`、`os`(或 `pathlib`)。**不可新增任何 pip 依賴**(不 import `pycocotools`/`numpy`/`cv2`)。
- 模組層級**零 GUI、零 Streamlit、零網路**;**嚴禁 `import yolo` / `import sidecar` / `import overlay` / `import casepkg`**(只吃/吐 dict)。
- 進入點檔名:`5_PG_Develop/cocoio.py`(測試 `import cocoio`,conftest 已把 `5_PG_Develop` 置於 `sys.path`)。
- 純函式 `to_coco` / `from_coco` / `to_labelme` / `from_labelme` 無副作用、不就地改輸入(`bbox` 等以 `list(...)` 複製);唯一有 I/O 者為 `write_coco` / `read_coco` / `write_labelme` / `read_labelme`。
- 容錯(`from_coco`/`from_labelme`)靠**明確的形狀檢查 + 局部 try/except 限定在「`float()`/`int()` 轉型」與「`json.load`」**,**不得**用包山包海的 `try/except: return ...` 吞掉所有邏輯。

---

## 3. I/O 契約(逐字採用,簽名為硬契約,/pm 直接鎖)

```python
def to_coco(items: list[dict], categories=None) -> dict
# 一批內部 item → 單一 COCO dict(images/annotations/categories);見 §3.3
# categories=None → 由 detections 的 cls 名「首見順序、id 由 1 起」自動導出(§3.4)
# categories 若給,須為 list[str](類別名,順序即 id 順序,id 由 1 起);未在清單者的 det 跳過該標註(§3.4)

def from_coco(coco: dict) -> list[dict]
# COCO dict → list[內部 item];category_id→cls 名、bbox[x,y,w,h] 直通、score→conf(缺→1.0);容錯(§3.5)

def to_labelme(item: dict) -> dict
# 單一內部 item → 單一 LabelMe dict(shapes/imagePath/imageHeight/imageWidth/...);見 §3.6

def from_labelme(lm: dict) -> dict
# 單一 LabelMe dict → 單一內部 item;rectangle points→bbox[x,y,w,h](min/abs 正規化);容錯(§3.7)

def write_coco(path, items: list[dict], categories=None) -> str
# 把 to_coco(items, categories) 以 json 寫到 path(UTF-8);回傳 path(字串)。父目錄不存在則建立。

def read_coco(path) -> list[dict]
# 讀 path 的 COCO json → from_coco(json)。檔不存在/壞 JSON/非 dict → [](容錯,不丟錯)。

def write_labelme(path, item: dict) -> str
# 把 to_labelme(item) 以 json 寫到 path(UTF-8);回傳 path。父目錄不存在則建立。

def read_labelme(path) -> dict
# 讀 path 的 LabelMe json → from_labelme(json)。檔不存在/壞 JSON/非 dict → 空 item(§3.8 EMPTY_ITEM)。
```

> `to_*`/`from_*` 為純轉換器(便於釘死值);`write_*`/`read_*` 為薄 I/O 包裝(Tier B,`tmp_path` 真實寫讀)。所有八個函式皆對外承諾。

### 3.1 內部 `item` 形狀(契約,釘死)

```python
item = {
    "name":       str,              # 影像檔名(對應 COCO file_name / LabelMe imagePath);缺 → ""
    "width":      int,              # 影像寬(像素);缺 → 0
    "height":     int,              # 影像高(像素);缺 → 0
    "detections": list[Detection],  # 偵測/標註結果;缺 → []
}
```

缺鍵一律套預設視同值(`name→""`、`width→0`、`height→0`、`detections→[]`),**不丟 `KeyError`**。

### 3.1.1 `Detection` 形狀(PO 跨模組釘死,本模組消費/產出)

```python
Detection = {"bbox": [x, y, w, h], "cls": str, "conf": float}   # bbox 絕對像素左上原點;conf ∈ [0,1]
```

- COCO 原生 `bbox` 也是 `[x,y,w,h]`(左上原點),**與我們同序 → 直通,不換算**。
- 本模組產出 `Detection` 時:`bbox` 為長度 4 的 `list`(各值 `int`,見 §3.5/§3.7 取整規則)、`cls` 為 `str`、`conf` 為 `float`。

### 3.2 各方向的「忠實度」承諾(釘死,供 round-trip)

| 欄位 | to_coco / to_labelme(導出) | from_coco / from_labelme(匯入) | round-trip 還原 |
|------|------|------|------|
| `bbox` | `[x,y,w,h]` 原樣(COCO 直通;LabelMe 轉兩點 `[[x,y],[x+w,y+h]]`) | 直通(COCO)/ 兩點轉回 `[x,y,w,h]`(LabelMe,min/abs) | **完全還原**(值與順序) |
| `cls` | → COCO `category_id`(經 §3.4 映射)/ LabelMe `label`(字串原樣) | category_id→cls 名 / label 原樣 | **完全還原**(字串相等) |
| `conf` | → COCO annotation `score`(float)/ LabelMe **不帶**(LabelMe 無 score 欄) | COCO `score`→conf(缺→`1.0`)/ LabelMe 一律 `conf=1.0` | COCO **還原**;LabelMe **不保證**(LabelMe 無 score 欄 → 回程一律 `1.0`) |

> **明示**:LabelMe 格式原生沒有 conf/score 概念,故 `to_labelme` 丟棄 conf、`from_labelme` 一律給 `conf=1.0`。COCO 有 `score`(非標準必填但本模組採用),故 conf 在 COCO round-trip 中被保留。此為兩格式能力差異,非缺陷;AC 分別釘死。

### 3.3 COCO dict 形狀(**釘死**)

`to_coco(items, categories=None)` 產出一個 dict,鍵順序釘死為 `["images","annotations","categories"]`:

```python
coco = {
  "images": [
    {"id": <1-based 影像序號>, "file_name": item["name"], "width": item["width"], "height": item["height"]}
    for 每個 item(順序同 items)
  ],
  "annotations": [
    {"id": <1-based 標註全域序號>, "image_id": <該 det 所屬影像的 image id>,
     "category_id": <該 det.cls 對應的 category id>, "bbox": list(det["bbox"]),
     "area": <w*h,見下>, "iscrowd": 0, "score": float(det["conf"])}
    for 每個 item 的每個 det(影像外層序、det 內層序;見資料流 §4)
  ],
  "categories": [
    {"id": <1-based>, "name": <cls 名>}
    for 每個類別(順序見 §3.4)
  ],
}
```

- **image id**:由 **1** 起、依 `items` 順序遞增(第 1 個 item → id 1)。每個 image dict 鍵順序固定 `["id","file_name","width","height"]`。
- **annotation id**:由 **1** 起、跨所有影像的所有 det **全域**遞增(扁平編號;第一筆 det → id 1)。每個 annotation dict 鍵順序固定 `["id","image_id","category_id","bbox","area","iscrowd","score"]`。
- **area 規則**:`area = float(bbox[2]) * float(bbox[3])`(= `w*h`,float)。例 `bbox=[10,20,30,40]` → `area = 30*40 = 1200.0`。
- **iscrowd**:恆 `0`(int)。
- **score**:`float(det["conf"])`(不夾界、不四捨五入;上游 yolo 已保證 `[0,1]`,本模組原樣 float 化)。
- `width`/`height`:取 `item.get("width",0)`/`item.get("height",0)`,**不**轉型(假設上游給 int;缺則 0)。
- `bbox`:`list(det["bbox"])`(複製,不 mutate 原 det)。

### 3.4 category 映射規則(**釘死**)

- **`categories=None`(預設,自動導出)**:掃描所有 item 的所有 det,取 `det["cls"]` 字串,**去重、保留首見順序**,依此順序由 **id=1** 起編號。
  - 例:det cls 序列(跨影像扁平)`["scratch","dent","scratch","edge"]` → categories = `[{"id":1,"name":"scratch"},{"id":2,"name":"dent"},{"id":3,"name":"edge"}]`。
  - 空輸入或無任何 det → `categories == []`。
- **`categories` 給定(list[str])**:依清單**順序**由 **id=1** 起編號(`categories[0]`→id 1);`coco["categories"]` 即此清單映射(即使某類別無任何 det 也列出)。
  - det 的 `cls` **不在**清單中 → **跳過該 det 的 annotation**(不報錯、不自動擴充類別);其 image dict 仍照常產出。
  - 例:`categories=["dent","scratch"]` → category id:`dent`=1、`scratch`=2(與首見順序無關,以給定清單為準)。
- **映射方向(to_coco)**:`cls 名 → category_id`。**映射方向(from_coco)**:`category_id → name`(查 `coco["categories"]`)。

### 3.5 `from_coco` 解析規則(**釘死,容錯**)

`from_coco(coco)` 把 COCO dict 還原成 `list[item]`(每影像一個 item,順序同 `coco["images"]`):

```python
item = {
  "name":   image["file_name"]（缺→""）,
  "width":  image["width"]（缺→0）,
  "height": image["height"]（缺→0）,
  "detections": [ 該 image 的每筆 annotation 轉成的 Detection（依 annotation 在陣列中的原順序） ],
}
```

每筆 annotation → Detection:
- `bbox = list(annotation["bbox"])`,各值取 `int`(`int(v)`,向 0 截斷);非長度 4 / 含非數值 / 缺 `bbox` → **跳過該 annotation**(不丟錯)。
- `cls`:查 `annotation["category_id"]` 對應到 `coco["categories"]` 裡同 `id` 的 `name`(`str`);category_id 缺、或在 categories 中查無對應 → `cls = ""`(框仍保留,不丟棄)。
- `conf`:`float(annotation["score"])`;缺 `score` 或轉 float 失敗 → `conf = 1.0`。

容錯邊界:
- `coco` 非 dict、或缺 `images` / `images` 非 list → 回 `[]`。
- `annotations` 缺 / 非 list → 視為**所有影像皆無 detection**(每 image 仍產出 item,`detections=[]`)。
- `categories` 缺 / 非 list → 視為**空映射**(所有 `category_id` 查無 → `cls=""`)。
- annotation 缺 `image_id`、或 `image_id` 不對應任何 image → **跳過該 annotation**(不掛到任何影像)。

### 3.6 LabelMe dict 形狀(**釘死**)

`to_labelme(item)` 產出一個 dict,鍵順序釘死為
`["version","flags","shapes","imagePath","imageData","imageHeight","imageWidth"]`:

```python
lm = {
  "version": "5.0.1",          # 常數版本字串(本模組對外承諾此值)
  "flags": {},                 # 空 dict(常數)
  "shapes": [
    {"label": det["cls"], "points": [[x, y], [x+w, y+h]],
     "group_id": None, "shape_type": "rectangle", "flags": {}}
    for 每個 det（順序同 item["detections"]）
  ],
  "imagePath": item["name"]（缺→""）,
  "imageData": None,           # 不內嵌 base64 影像(常數 None)
  "imageHeight": item["height"]（缺→0）,
  "imageWidth": item["width"]（缺→0）,
}
```

- 每個 shape dict 鍵順序固定 `["label","points","group_id","shape_type","flags"]`。
- `points`:兩點 `[[x, y], [x+w, y+h]]`(左上、右下),數值為 `det["bbox"]` 的原值(不取整、不轉型;上游 bbox 已是 int)。
- `shape_type` 恆 `"rectangle"`;`group_id` 恆 `None`;每 shape 的 `flags` 恆 `{}`。
- **conf 不導出**(LabelMe 無 score 欄;見 §3.2)。

### 3.7 `from_labelme` 解析規則(**釘死,容錯**)

`from_labelme(lm)` 把單一 LabelMe dict 還原成單一 item:

```python
item = {
  "name":   lm["imagePath"]（缺→""）,
  "width":  lm["imageWidth"]（缺→0）,
  "height": lm["imageHeight"]（缺→0）,
  "detections": [ 每個 shape_type=="rectangle" 的 shape 轉成的 Detection（順序同 shapes） ],
}
```

每個 shape → Detection:
- 只處理 `shape_type == "rectangle"` 的 shape;其他 `shape_type`(polygon/circle/...)→ **跳過**(不丟錯)。
- `points` 須為兩個點(`[[ax,ay],[bx,by]]`);非此形狀(點數≠2 / 點非長度 2 / 含非數值)→ **跳過該 shape**。
- bbox 由兩點正規化(不假設哪點是左上):`x=int(min(ax,bx))`、`y=int(min(ay,by))`、`w=int(abs(bx-ax))`、`h=int(abs(by-ay))`。
- `cls = str(shape["label"])`(缺 `label` → `""`)。
- `conf = 1.0`(LabelMe 無 score;恆定)。

容錯邊界:
- `lm` 非 dict → 回 §3.8 `EMPTY_ITEM`。
- `shapes` 缺 / 非 list → `detections = []`(name/width/height 仍照 §3.7 取)。

### 3.8 空 / 容錯回傳常數(釘死)

```python
EMPTY_ITEM = {"name": "", "width": 0, "height": 0, "detections": []}
```

- `read_labelme` 於檔不存在 / 壞 JSON / 非 dict → 回 `EMPTY_ITEM`(值相等,不必同一物件)。
- `from_labelme(非 dict)` → 回 `EMPTY_ITEM`。
- `read_coco` 於檔不存在 / 壞 JSON / 非 dict → 回 `[]`。
- `from_coco(非 dict)` → 回 `[]`。

### 3.9 檔案 I/O 行為(**Tier B,真實寫入**)

```
write_coco(path, items, categories=None):
  父目錄不存在 → os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
  寫 path ← json.dumps(to_coco(items, categories), ensure_ascii=False, indent=2)   # UTF-8
  return path

read_coco(path):
  檔不存在 / 壞 JSON / 解析結果非 dict → return []
  否則 return from_coco(json.load(path))

write_labelme(path, item):
  父目錄不存在 → makedirs；寫 path ← json.dumps(to_labelme(item), ensure_ascii=False, indent=2)   # UTF-8
  return path

read_labelme(path):
  檔不存在 / 壞 JSON / 非 dict → return EMPTY_ITEM
  否則 return from_labelme(json.load(path))
```

- 檔案以 UTF-8、`ensure_ascii=False` 寫入(non-ASCII 如中文 cls/label 無損)。
- 回傳值為傳入的 `path`(字串化);父目錄不存在則 `os.makedirs(..., exist_ok=True)` 建立後再寫。
- **覆寫語義**:同 `path` 重複寫,後者完全覆寫前者(非附加)。

---

## 4. 資料流 (Data Flow)

```
items: list[item]  (每 item: name/width/height/detections=list[Detection])
  │
  ├─ to_coco(items, categories) ──► coco dict
  │     1) 掃所有 det.cls → 建 cls→id 映射(§3.4;categories=None 則首見序、否則照清單)
  │     2) for i, item in items: image id = i+1 → images[]
  │     3) 全域 ann_id=1;for item(序) → for det(序):
  │             cls 不在映射(僅 categories 給定時)→ 跳過
  │             否則 annotations.append({id:ann_id++, image_id, category_id, bbox, area=w*h, iscrowd:0, score:conf})
  │     4) categories[] 由映射輸出
  │
  ├─ from_coco(coco) ──► list[item]
  │     建 image_id→item、category_id→name 兩張表;逐 annotation 掛回對應 image 的 detections(容錯跳壞筆)
  │
  ├─ to_labelme(item) ──► lm dict        (det → rectangle shape [[x,y],[x+w,y+h]];丟 conf)
  ├─ from_labelme(lm) ──► item           (rectangle shape → bbox min/abs;conf 恆 1.0)
  │
  └─ write_coco/read_coco/write_labelme/read_labelme  (薄 I/O,UTF-8,父目錄自建,容錯讀)
```

- **round-trip(COCO)**:`from_coco(to_coco(items))` 還原每筆 det 的 `bbox`(直通)、`cls`(經 id 來回)、`conf`(經 score 來回);影像層 `name/width/height` 還原。**注意**:item 的鍵順序與某些「無 det 的類別」不影響 det 還原;round-trip 比較以 detections/影像欄位為準(見 AC)。
- **round-trip(LabelMe)**:`from_labelme(to_labelme(item))` 還原 `bbox`(兩點來回 min/abs)、`cls`(label 字串);`conf` **不保證**(回程恆 `1.0`)。

---

## 5. 邊界條件與錯誤處理

| 情境 | 行為(契約) |
|------|------|
| `to_coco([])`(空) | `{"images":[], "annotations":[], "categories":[]}`(三鍵皆空 list) |
| `to_coco(items, categories=[])`(空類別清單) | 映射為空 → 所有 det 的 cls 皆「不在清單」→ 全部 annotation 跳過;images 照出;categories=`[]` |
| item 缺 `name`/`width`/`height`/`detections` | 套 §3.1 預設(`""`/`0`/`0`/`[]`),不丟 `KeyError` |
| det 的 `cls` 不在給定 `categories` | 跳過該 det 的 annotation(image 仍出);`categories=None` 時不會發生(自動收錄所有 cls) |
| `from_coco(非 dict)` / 缺 `images` | 回 `[]` |
| `from_coco` 的 annotation 缺/壞 `bbox`(非長度 4 / 含非數值) | 跳過該 annotation,不影響同影像其他筆 |
| `from_coco` 的 annotation `category_id` 查無對應 | `cls=""`(框保留) |
| `from_coco` 的 annotation `image_id` 不對應任何 image | 跳過該 annotation(不掛到任何影像) |
| `from_coco` 的 annotation 缺 `score` | `conf=1.0` |
| `to_labelme` 的 det | 一律轉 rectangle;`points=[[x,y],[x+w,y+h]]` |
| `from_labelme` 非 rectangle 的 shape(polygon 等) | 跳過該 shape |
| `from_labelme` 的 rectangle points 非兩點 / 含非數值 | 跳過該 shape |
| `from_labelme` 的 rectangle 點順序顛倒(右下在前) | min/abs 正規化,`w,h ≥ 0`(等同正常順序) |
| `from_labelme(非 dict)` / `read_labelme`(缺檔/壞) | 回 `EMPTY_ITEM`(§3.8) |
| `read_coco`(缺檔/壞 JSON/非 dict) | 回 `[]` |
| 輸入 `items`/`item` mutate | 禁止;`bbox` 以 `list(...)` 複製,純函式不改原物件 |
| non-ASCII cls/label/name | UTF-8 + `ensure_ascii=False` 無損;`from_*` 原樣帶回 |
| `conf` 為 int(如 `1`) | `score = float(1) = 1.0`;`from_coco` `conf=float(...)` |

---

## 6. Acceptance Criteria(給 `/pm` 落成 pytest;每條帶具體期望值、可驗)

> 測試置於 `4_PM_Feedback/test_cocoio.py`(`write_*`/`read_*` 用 `tmp_path` 真實寫讀);`import cocoio`。
> 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_cocoio.py -p no:cacheprovider --strict-markers -q`
>
> 共用測試夾具(下列 AC 引用 `IT1`/`IT2`):
> ```python
> IT1 = {"name":"a.png", "width":200, "height":100,
>        "detections":[{"bbox":[10,20,30,40],"cls":"scratch","conf":0.9},
>                      {"bbox":[50,60,10,10],"cls":"dent","conf":0.5},
>                      {"bbox":[0,0,5,5],"cls":"scratch","conf":0.7}]}
> IT2 = {"name":"b.png", "width":640, "height":480, "detections":[]}   # 無 det
> ```

### A. to_coco 結構與值(釘死)
- **AC1(空輸入)**:`cocoio.to_coco([]) == {"images":[], "annotations":[], "categories":[]}`,且 `list(cocoio.to_coco([]).keys()) == ["images","annotations","categories"]`(三鍵順序釘死)。
- **AC2(完整聚合 dict)**:`cocoio.to_coco([IT1, IT2])` **逐欄等於**:
  ```python
  {
    "images": [
      {"id":1, "file_name":"a.png", "width":200, "height":100},
      {"id":2, "file_name":"b.png", "width":640, "height":480},
    ],
    "annotations": [
      {"id":1, "image_id":1, "category_id":1, "bbox":[10,20,30,40], "area":1200.0, "iscrowd":0, "score":0.9},
      {"id":2, "image_id":1, "category_id":2, "bbox":[50,60,10,10], "area":100.0,  "iscrowd":0, "score":0.5},
      {"id":3, "image_id":1, "category_id":1, "bbox":[0,0,5,5],     "area":25.0,   "iscrowd":0, "score":0.7},
    ],
    "categories": [{"id":1, "name":"scratch"}, {"id":2, "name":"dent"}],
  }
  ```
  (image id 1-based 依 items 序;annotation id 全域 1-based;category 首見序 scratch=1/dent=2;area=w*h 為 float;iscrowd=0;score=conf;IT2 無 det 故無 annotation 但仍有 image id 2。)
- **AC3(image dict 鍵順序)**:`list(cocoio.to_coco([IT1])["images"][0].keys()) == ["id","file_name","width","height"]`。
- **AC4(annotation dict 鍵順序)**:`list(cocoio.to_coco([IT1])["annotations"][0].keys()) == ["id","image_id","category_id","bbox","area","iscrowd","score"]`。
- **AC5(category 首見去重保序)**:`cocoio.to_coco([IT1])["categories"] == [{"id":1,"name":"scratch"},{"id":2,"name":"dent"}]`(scratch 首見=1、dent=2,第三筆 scratch 不再新增類別)。
- **AC6(area = w*h, float)**:`a = cocoio.to_coco([IT1])["annotations"]`;`a[0]["area"] == 1200.0 and isinstance(a[0]["area"], float)`;`a[1]["area"] == 100.0`。
- **AC7(score = conf, float;conf 為 int 也 float 化)**:對 `{"name":"c.png","width":10,"height":10,"detections":[{"bbox":[0,0,1,1],"cls":"x","conf":1}]}`,`cocoio.to_coco([那])["annotations"][0]["score"] == 1.0 and isinstance(..., float)`。
- **AC8(annotation id 全域跨影像遞增)**:對 `[IT1, IT3]`,其中 `IT3={"name":"c.png","width":10,"height":10,"detections":[{"bbox":[1,1,1,1],"cls":"edge","conf":0.2}]}` → `[a["id"] for a in cocoio.to_coco([IT1, IT3])["annotations"]] == [1,2,3,4]` 且第 4 筆 `image_id == 2`(IT3 是第 2 張影像)。
- **AC9(item 缺鍵套預設)**:`cocoio.to_coco([{"detections":[{"bbox":[0,0,2,2],"cls":"x","conf":0.5}]}])["images"][0] == {"id":1,"file_name":"","width":0,"height":0}`(name→""、width/height→0)。
- **AC10(不 mutate 輸入)**:呼叫 `cocoio.to_coco([IT1])` 後,`IT1` 以 `copy.deepcopy` 比對前後相等(`bbox` 以 `list(...)` 複製,未改原物件)。

### B. to_coco 的 categories 參數(釘死)
- **AC11(給定 categories 決定 id 順序)**:`coco = cocoio.to_coco([IT1], categories=["dent","scratch"])`;`coco["categories"] == [{"id":1,"name":"dent"},{"id":2,"name":"scratch"}]`,且 annotations 的 category_id 對應為 `[2,1,2]`(scratch=2、dent=1、scratch=2;依給定清單而非首見序)。
- **AC12(給定 categories 含未出現類別仍列出)**:`coco = cocoio.to_coco([IT2], categories=["scratch","dent"])`;`coco["categories"] == [{"id":1,"name":"scratch"},{"id":2,"name":"dent"}]`(IT2 無 det,但類別清單照列),`coco["annotations"] == []`。
- **AC13(det 的 cls 不在 categories → 跳過該 annotation)**:`coco = cocoio.to_coco([IT1], categories=["dent"])`;`coco["categories"]==[{"id":1,"name":"dent"}]`,`coco["annotations"]` 只剩 dent 那筆,即 `len(coco["annotations"])==1` 且 `coco["annotations"][0]["category_id"]==1 and coco["annotations"][0]["bbox"]==[50,60,10,10]`(兩筆 scratch 被跳過),但 `coco["images"]` 仍有 1 張(image 不受影響)。
- **AC14(空 categories 清單 → 全部 annotation 跳過)**:`coco = cocoio.to_coco([IT1], categories=[])`;`coco["categories"]==[]` 且 `coco["annotations"]==[]`,`len(coco["images"])==1`。

### C. from_coco(解析 + 容錯,釘死)
- **AC15(from_coco round-trip 還原 detections)**:`items2 = cocoio.from_coco(cocoio.to_coco([IT1, IT2]))`;`len(items2)==2`;`items2[0] == {"name":"a.png","width":200,"height":100,"detections":[{"bbox":[10,20,30,40],"cls":"scratch","conf":0.9},{"bbox":[50,60,10,10],"cls":"dent","conf":0.5},{"bbox":[0,0,5,5],"cls":"scratch","conf":0.7}]}` 且 `items2[1] == {"name":"b.png","width":640,"height":480,"detections":[]}`(bbox/cls/conf 完全還原、影像欄位還原、IT2 還原為空 det)。
- **AC16(category_id→cls 名)**:對手寫 COCO `{"images":[{"id":1,"file_name":"x.png","width":5,"height":5}],"annotations":[{"id":1,"image_id":1,"category_id":2,"bbox":[1,2,3,4],"area":12.0,"iscrowd":0,"score":0.8}],"categories":[{"id":1,"name":"a"},{"id":2,"name":"b"}]}` → `cocoio.from_coco(那) == [{"name":"x.png","width":5,"height":5,"detections":[{"bbox":[1,2,3,4],"cls":"b","conf":0.8}]}]`(category_id=2→"b"、bbox 直通、score→conf)。
- **AC17(bbox 直通且取 int)**:對 annotation `"bbox":[1.0,2.0,3.0,4.0]`(float 值),`from_coco` 後 `detections[0]["bbox"] == [1,2,3,4]` 且 `all(isinstance(v,int) for v in detections[0]["bbox"])`。
- **AC18(缺 score → conf=1.0)**:對 annotation 無 `score` 鍵者,`from_coco` 後該 det `conf == 1.0`。
- **AC19(category_id 查無 → cls="")**:annotation `category_id=99` 但 categories 無 id 99 → 該 det `cls == ""`(框仍保留,該影像 `len(detections)==1`)。
- **AC20(annotation 缺/壞 bbox → 跳過該筆)**:三筆 annotation `bbox` 分別為 `[1,2,3]`(長度 3)、`[1,2,"x",4]`(含非數值)、`[5,5,5,5]`(正常),皆掛同一 image → `from_coco` 後該影像 `detections == [{"bbox":[5,5,5,5],"cls":<對應>,"conf":<對應>}]`(前兩筆被跳過)。
- **AC21(annotation image_id 不對應任何 image → 跳過)**:image id=1,但某 annotation `image_id=7` → 該 annotation 不出現在任何 item 的 detections;對應 image=1 的 item `detections` 不含它。
- **AC22(非 dict / 缺 images → [])**:`cocoio.from_coco(42) == []`;`cocoio.from_coco("x") == []`;`cocoio.from_coco({"annotations":[]}) == []`(缺 images);`cocoio.from_coco({"images":[]}) == []`(images 為空 list → 無影像)。
- **AC23(缺 annotations → 每 image 空 det)**:`cocoio.from_coco({"images":[{"id":1,"file_name":"x.png","width":3,"height":3}]}) == [{"name":"x.png","width":3,"height":3,"detections":[]}]`(annotations 鍵缺 → detections=[])。

### D. to_labelme / from_labelme(釘死 + round-trip)
- **AC24(to_labelme 結構與鍵順序)**:`lm = cocoio.to_labelme(IT1)`;`list(lm.keys()) == ["version","flags","shapes","imagePath","imageData","imageHeight","imageWidth"]`;`lm["version"]=="5.0.1"`、`lm["flags"]=={}`、`lm["imagePath"]=="a.png"`、`lm["imageData"] is None`、`lm["imageHeight"]==100`、`lm["imageWidth"]==200`。
- **AC25(to_labelme shapes 精確)**:`lm = cocoio.to_labelme(IT1)`;`lm["shapes"] == [{"label":"scratch","points":[[10,20],[40,60]],"group_id":None,"shape_type":"rectangle","flags":{}},{"label":"dent","points":[[50,60],[60,70]],"group_id":None,"shape_type":"rectangle","flags":{}},{"label":"scratch","points":[[0,0],[5,5]],"group_id":None,"shape_type":"rectangle","flags":{}}]`(`points=[[x,y],[x+w,y+h]]`:`[10,20]`→`[10+30,20+40]=[40,60]`,以此類推;每 shape 鍵順序釘死)。
- **AC26(to_labelme 空 det)**:`cocoio.to_labelme(IT2)["shapes"] == []`,且 `cocoio.to_labelme(IT2)["imageWidth"]==640 and cocoio.to_labelme(IT2)["imageHeight"]==480`。
- **AC27(to_labelme 缺鍵 item)**:`cocoio.to_labelme({}) == {"version":"5.0.1","flags":{},"shapes":[],"imagePath":"","imageData":None,"imageHeight":0,"imageWidth":0}`。
- **AC28(from_labelme rectangle → bbox)**:對 `{"imagePath":"x.png","imageWidth":50,"imageHeight":60,"shapes":[{"label":"scratch","points":[[10,20],[40,60]],"shape_type":"rectangle"}]}` → `cocoio.from_labelme(那) == {"name":"x.png","width":50,"height":60,"detections":[{"bbox":[10,20,30,40],"cls":"scratch","conf":1.0}]}`(兩點→`x=10,y=20,w=40-10=30,h=60-20=40`;conf 恆 1.0)。
- **AC29(from_labelme 點顛倒 min/abs 正規化)**:對 shape `{"label":"x","points":[[40,60],[10,20]],"shape_type":"rectangle"}`(右下在前)→ 該 det `bbox == [10,20,30,40]`(min/abs 正規化,等同 AC28)。
- **AC30(from_labelme bbox 取 int)**:對 shape points `[[10.0,20.0],[40.5,60.9]]` → bbox 各值為 int:`x=int(10.0)=10`、`y=20`、`w=int(abs(40.5-10.0))=int(30.5)=30`、`h=int(abs(60.9-20.0))=int(40.9)=40` → `bbox==[10,20,30,40]` 且 `all(isinstance(v,int) for v in bbox)`。
- **AC31(from_labelme 跳非 rectangle / 壞點)**:對 `shapes=[{"label":"p","points":[[0,0],[1,1],[2,0]],"shape_type":"polygon"},{"label":"bad","points":[[0,0]],"shape_type":"rectangle"},{"label":"ok","points":[[1,1],[3,4]],"shape_type":"rectangle"}]` → `from_labelme` 的 `detections == [{"bbox":[1,1,2,3],"cls":"ok","conf":1.0}]`(polygon 跳過、單點 rectangle 跳過,只剩 ok)。
- **AC32(from_labelme 非 dict / 缺 shapes)**:`cocoio.from_labelme(42) == {"name":"","width":0,"height":0,"detections":[]}`;`cocoio.from_labelme({"imagePath":"y.png","imageWidth":8,"imageHeight":9}) == {"name":"y.png","width":8,"height":9,"detections":[]}`(缺 shapes → 空 det)。
- **AC33(LabelMe round-trip 還原 bbox/cls;conf 一律 1.0)**:`it = cocoio.from_labelme(cocoio.to_labelme(IT1))`;`[d["bbox"] for d in it["detections"]] == [[10,20,30,40],[50,60,10,10],[0,0,5,5]]` 且 `[d["cls"] for d in it["detections"]] == ["scratch","dent","scratch"]` 且 `all(d["conf"]==1.0 for d in it["detections"])`(bbox/cls 還原;conf 因 LabelMe 無 score 一律回 1.0,非還原 IT1 的 0.9/0.5/0.7),且 `it["name"]=="a.png" and it["width"]==200 and it["height"]==100`。

### E. write/read COCO(Tier B,tmp_path 真實寫讀)
- **AC34(write_coco 回路徑 + 檔存在)**:`p = str(tmp_path / "out" / "ann.json")`;`ret = cocoio.write_coco(p, [IT1, IT2])`;`ret == p` 且 `os.path.exists(p) is True`(父目錄 `out` 自動建立)。
- **AC35(write_coco 磁碟內容 == to_coco 的 json)**:
  ```python
  p = str(tmp_path / "ann.json")
  cocoio.write_coco(p, [IT1, IT2])
  with open(p, "r", encoding="utf-8") as f:
      disk = f.read()
  assert disk == json.dumps(cocoio.to_coco([IT1, IT2]), ensure_ascii=False, indent=2)
  assert json.load(open(p, encoding="utf-8")) == cocoio.to_coco([IT1, IT2])
  ```
- **AC36(read_coco round-trip == from_coco∘to_coco)**:`p=str(tmp_path/"ann.json")`;`cocoio.write_coco(p,[IT1,IT2])`;`cocoio.read_coco(p) == cocoio.from_coco(cocoio.to_coco([IT1, IT2]))`,且其 `[0]["detections"][0] == {"bbox":[10,20,30,40],"cls":"scratch","conf":0.9}`(磁碟讀回後 det 完整還原)。
- **AC37(read_coco 缺檔/壞 JSON → [])**:`cocoio.read_coco(str(tmp_path / "nope.json")) == []`(不建檔、不丟錯);另寫一檔內容 `"{not json"` → `cocoio.read_coco(那) == []`。
- **AC38(write_coco 空 items)**:`p=str(tmp_path/"empty.json")`;`cocoio.write_coco(p, [])`;`json.load(open(p, encoding="utf-8")) == {"images":[],"annotations":[],"categories":[]}` 且 `cocoio.read_coco(p) == []`。
- **AC39(write_coco 覆寫語義)**:對同一 `p` 先 `write_coco(p,[IT1,IT2])` 再 `write_coco(p,[IT2])` → `cocoio.read_coco(p)` 長度為 1 且 `[0]["name"]=="b.png"`(後者完全覆寫,非附加)。
- **AC40(write_coco non-ASCII 無損)**:對 `{"name":"圖.png","width":3,"height":3,"detections":[{"bbox":[0,0,1,1],"cls":"刮傷","conf":0.5}]}`,`write_coco`→`read_coco` 後 `[0]["name"]=="圖.png" and [0]["detections"][0]["cls"]=="刮傷"`(UTF-8/ensure_ascii=False)。

### F. write/read LabelMe(Tier B,tmp_path 真實寫讀)
- **AC41(write_labelme 回路徑 + 磁碟內容 == to_labelme 的 json)**:
  ```python
  p = str(tmp_path / "lm" / "a.json")
  ret = cocoio.write_labelme(p, IT1)
  assert ret == p and os.path.exists(p)            # 父目錄 lm 自動建立
  with open(p, "r", encoding="utf-8") as f:
      disk = f.read()
  assert disk == json.dumps(cocoio.to_labelme(IT1), ensure_ascii=False, indent=2)
  assert json.load(open(p, encoding="utf-8")) == cocoio.to_labelme(IT1)
  ```
- **AC42(read_labelme round-trip == from_labelme∘to_labelme)**:`p=str(tmp_path/"a.json")`;`cocoio.write_labelme(p, IT1)`;`cocoio.read_labelme(p) == cocoio.from_labelme(cocoio.to_labelme(IT1))`,且其 `["detections"][0] == {"bbox":[10,20,30,40],"cls":"scratch","conf":1.0}`(磁碟讀回後 bbox/cls 還原、conf=1.0)。
- **AC43(read_labelme 缺檔/壞 JSON → EMPTY_ITEM)**:`cocoio.read_labelme(str(tmp_path / "nope.json")) == {"name":"","width":0,"height":0,"detections":[]}`;另寫一檔內容 `"{bad"` → `cocoio.read_labelme(那) == {"name":"","width":0,"height":0,"detections":[]}`(不丟錯)。
- **AC44(write_labelme non-ASCII 無損)**:對 `{"name":"圖.png","width":3,"height":3,"detections":[{"bbox":[0,0,1,1],"cls":"刮傷","conf":0.5}]}`,`write_labelme`→`read_labelme` 後 `["name"]=="圖.png" and ["detections"][0]["cls"]=="刮傷"`(conf 回 1.0)。

---

## 7. 與其他模組的邊界(防越權)

- **不負責**載入 YOLO 原始 JSON / 多 schema 容錯(那是 `yolo`:本模組吃**已是 `Detection` 形狀**的 dict,不 import yolo)。
- **不負責**讀寫 sidecar 檔或人工判讀欄位(`review_status`/`verdict`/`tags` 等是 `sidecar`/`casepkg` 的事;COCO/LabelMe 標準格式不含這些,本模組不夾帶)。
- **不負責**畫圖、conf 過濾、class 篩選(那是 `overlay`)。
- **不負責**自家扁平 CSV / 巢狀摘要 JSON(那是 `casepkg`,對內格式);本模組只出**對外標準互通格式**(COCO/LabelMe)。
- **不負責**影像像素讀寫 / base64 內嵌(`to_labelme` 的 `imageData` 恆 `None`;不讀原圖)。
- **不負責**校驗 bbox 是否超出影像邊界 / cls 合法性(上游把關;本模組原樣帶或做 min/abs 與型別正規化)。
- 本模組對外承諾:除 `write_*`/`read_*` 外皆純函式、無副作用、輸入不被 mutate、僅依賴 Python 標準庫;COCO dict 形狀(§3.3)、category 映射(§3.4)、LabelMe dict 形狀(§3.6)、空/容錯回傳(§3.8)為對下游(app 互通匯入匯出 UI)鎖定的契約;`from_*` 永不拋例外(壞輸入回 `[]` / `EMPTY_ITEM`)。
