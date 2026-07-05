# 設計:`yolo`(M3 / Tier B — 有 I/O,容錯檔案載入器,需真實讀寫驗收)

> `/architect` 產物。對應 PRD `2_PO_PRD/01` §3 M3(模組表第 51 行)、`ROADMAP.md`(第 34、40-43 行)、開放問題 5(YOLO 結果格式 / 座標系)。
> 本檔只定義契約與驗收標準,**不含實作**。實作由 `/pg` 寫到 `5_PG_Develop/yolo.py`。

## 邊界 sanity check(開工前一句話)
`yolo` 內聚一句話講得完(把單張影像的偵測 JSON 載入並正規化成標準 `list[Detection]`,容錯第一,不碰原圖、不依賴其他模組),
契約只耦合「檔案系統 + 共用 `Detection` 形狀」,與消費端(overlay/filtersort/casepkg)以**資料形狀**解耦(它們不 import yolo),
可用 `tmp_path` 寫一份 JSON 獨立 round-trip 驗收。
→ **可獨立設計與驗收,不需合併或再拆。** 放行本輪設計。

---

## 1. 目的 (Purpose)
把單張影像的 YOLO 偵測結果 JSON(多種來源 schema)載入並正規化成跨模組共用的 `list[Detection]`(絕對像素 `[x,y,w,h]` bbox),**容錯第一**:任何髒資料只跳過該筆或回空清單,**絕不拋例外**。

---

## 2. I/O 契約 (I/O Contract)

實作於 `5_PG_Develop/yolo.py`。測試以 `import yolo` 取用(conftest 已把 `5_PG_Develop` 加進 `sys.path`)。
**逐字採用**以下簽名,不得增刪參數或改名:

```python
def load(json_path, img_w=None, img_h=None) -> list[dict]:
    # 讀單張影像的偵測 JSON → 正規化成 list[Detection]。
    # json_path: str | pathlib.Path。檔不存在/壞 JSON/空 → []。
    # img_w, img_h: 正整數或 None;僅在需要把正規化座標(xywhn)換絕對時使用。
    # 永不拋例外。
    ...

def normalize_one(obj, img_w=None, img_h=None) -> dict | None:
    # 把單一原始偵測 dict 正規化成一筆 Detection;無法正規化(缺框/座標不足)→ None。
    # 純函式、不做 I/O、不拋例外(壞輸入回 None)。load() 內部對每筆呼叫它。
    ...
```

> `load` 是對外主入口(I/O + 批次容錯);`normalize_one` 是被抽出的純邏輯單筆轉換器(便於釘死座標換算 AC,且讓 load 的「跳過壞筆」語義 = 「`normalize_one` 回 `None` 即跳過」)。兩者皆對外承諾。

### 2.1 共用契約形狀 `Detection`(PO 釘死,逐字採用)
`load` 回傳 `list[Detection]`,每筆 `Detection` 為**剛好三鍵**的 dict:

| 鍵 | 型別 | 語義 |
|----|------|------|
| `bbox` | `list[int]`,長度 4 = `[x, y, w, h]` | **絕對像素**;原點左上,x 向右、y 向下;`x,y` 為左上角,`w,h` 為寬高(皆 `int`) |
| `cls`  | `str` | 類別名稱 |
| `conf` | `float` ∈ `[0.0, 1.0]` | 信心分數(**夾到** `[0,1]`,見 §4) |

> `set(det.keys()) == {"bbox","cls","conf"}`,不多不少。與 overlay/filtersort/casepkg 共用同一形狀。

### 2.2 接受的來源 schema(頂層容器)
`load` 解析出的頂層 JSON 可為以下任一,皆抽出「偵測陣列」:
- **頂層即 list**:`[ {det}, {det}, ... ]` → 偵測陣列就是它本身。
- **頂層為 dict**,依序找第一個存在且為 list 的鍵:`detections` → `predictions` → `objects`。取到的 list 即偵測陣列。
- 頂層為 dict 但上述三鍵都不存在 / 都不是 list → 偵測陣列視為 `[]`(回 `[]`,不拋錯)。
- 頂層既非 list 也非 dict(如 JSON 是純數字 / 字串)→ `[]`。

### 2.3 單筆偵測(`normalize_one` 接受的鍵,皆別名擇一)
對偵測陣列中的每個元素(須為 dict;非 dict → 跳過):

**框座標(三選一,依優先序找第一個「存在且為長度 4 的數值序列」)**:
1. `bbox`:`[x, y, w, h]` — **絕對像素 xywh**(左上原點)。直接採用。
2. `xyxy`:`[x1, y1, x2, y2]` — **絕對像素**對角點。換算:`x=min(x1,x2)`、`y=min(y1,y2)`、`w=abs(x2-x1)`、`h=abs(y2-y1)`。
3. `xywhn`:`[xc, yc, wn, hn]` — **正規化**(0~1),`xc,yc` 為**中心點**、`wn,hn` 為正規化寬高。換算需 `img_w,img_h`(見 §4.d):
   `w = wn*img_w`、`h = hn*img_h`、`x = xc*img_w - w/2`、`y = yc*img_h - h/2`。
   三框鍵皆不存在 / 都不是長度 4 數值序列 → `normalize_one` 回 `None`(該筆跳過)。

**類別名(依序 `cls` → `class` → `name` → `label`,取第一個存在者)**:
- 值若非字串(如 int 類別 id `3`)→ `str(value)`(轉成 `"3"`)。
- 四鍵都缺 → `cls = ""`(空字串;**不**因缺類別丟棄該筆,框仍有效)。

**信心(依序 `conf` → `confidence` → `score`,取第一個存在者)**:
- 轉 `float` 後**夾到** `[0.0, 1.0]`(`<0 → 0.0`、`>1 → 1.0`)。
- 三鍵都缺 / 轉 float 失敗 → `conf = 1.0`(視為「未標信心,當作確定」;**不**丟棄該筆)。

### 2.4 純度與依賴約定(對 `/pg` 的硬約束)
- 僅允許依賴 Python 標準庫(`os`、`json`、`pathlib` 等)。**不可新增 pip 依賴**(不 import `ultralytics` / `numpy` / `cv2`)。
- **不**修改、不開啟原始影像檔;只讀 `json_path`。
- `normalize_one` 為純函式(無 I/O、無副作用)。
- 容錯靠**明確的形狀檢查 + 局部 try/except 限定在「`float()`/`int()` 轉型」與「`json.load`」**,**不得**用一個包山包海的 `try/except: return []` 吞掉所有邏輯(那會遮蔽真錯)。逐筆失敗 = `normalize_one` 回 `None`。

---

## 3. 資料流 (Data Flow)

```
json_path (+ img_w,img_h)
   │  存在?               否 → return []
   ▼
讀檔 + json.loads        壞 JSON / 空字串 → return []
   │
   ▼
抽偵測陣列 (§2.2)         頂層型別不符 / 無有效鍵 → []
   │
   ▼  for each raw in 陣列:
   │     normalize_one(raw, img_w, img_h)
   │        ├─ 非 dict          → None(跳過)
   │        ├─ 找框鍵 bbox/xyxy/xywhn → 換算絕對 xywh;都無 → None
   │        ├─ xywhn 但缺 img_w/img_h → None(見 §4.d)
   │        ├─ 類別:cls/class/name/label → str;缺 → ""
   │        └─ 信心:conf/confidence/score → float clamp[0,1];缺/壞 → 1.0
   │     回 None 的筆 → 丟棄(不整批失敗)
   ▼
list[Detection]  (bbox 各值取 int,見 §4.e;保留原陣列順序)
```

- **讀路徑**:`load` 永不丟錯;缺檔、空檔、壞 JSON 全回 `[]`(對齊 sidecar `load` 容錯精神)。
- **轉換順序**:保留來源陣列順序;輸出 `Detection` 順序 == 來源有效筆順序。
- **bbox 取整**:換算後對 `x,y,w,h` 各取 `int`(見 §4.e 取整規則)。

---

## 4. 邊界條件與錯誤處理 (Edge Cases & Error Handling)

| # | 情境 | 行為(契約) |
|---|------|------|
| a | `json_path` 不存在 | `load` 回 `[]`,**不**建檔、不丟錯 |
| b | 檔存在但內容為空字串 / 壞 JSON(如 `"{not json"`) | `load` 回 `[]`(吞 `json` 解析錯,不丟錯) |
| c | 合法 JSON 但頂層非 list/dict,或 dict 無 `detections`/`predictions`/`objects` list | `load` 回 `[]` |
| d | 偵測用 `xywhn`(正規化)但 `img_w` 或 `img_h` 為 `None`(或 ≤0) | **該筆** `normalize_one` 回 `None` → 被跳過(無尺寸無法換絕對;不臆測尺寸、不丟錯)。同檔中以絕對 `bbox`/`xyxy` 表示的其他筆仍正常載入 |
| e | bbox 取整規則 | 換算後 `x = int(x)`、`y = int(y)`、`w = int(w)`、`h = int(h)`(Python `int()` 向 0 截斷)。輸入若已是整數則不變 |
| f | 單筆缺框(三框鍵皆無 / 非長度 4 / 含非數值) | `normalize_one` 回 `None`,**只跳過該筆**,不影響同檔其他筆 |
| g | 單筆缺類別 | `cls = ""`(框仍有效,不丟棄) |
| h | 單筆缺信心 / 信心非數值 | `conf = 1.0`(框仍有效,不丟棄) |
| i | 信心超界 | 夾到 `[0,1]`:`-0.3 → 0.0`、`1.7 → 1.0`、`0.42 → 0.42` |
| j | 類別為 int id(如 `"cls": 3`) | `str(3) == "3"` |
| k | 偵測陣列元素非 dict(如 `5`、`"x"`、`null`、`[...]`) | 跳過該元素(不丟錯) |
| l | 同一筆同時有多個框鍵(如同時有 `bbox` 與 `xyxy`) | 依 §2.3 優先序 `bbox` > `xyxy` > `xywhn`,只用第一個有效者 |
| m | `xyxy` 角點順序顛倒(x2<x1) | 用 `min`/`abs` 正規化(見 §2.3),`w,h` 恆 ≥0 |
| n | `bbox`/`xyxy`/`xywhn` 長度不為 4(如 3 或 5 個元素) | 視為無效框 → 該框鍵不採用;若無其他有效框鍵 → 該筆回 `None` |
| o | 空偵測陣列(`[]` 或 `{"detections":[]}`) | `load` 回 `[]`(合法、非錯誤) |

> **不做的事**:不對 bbox 做影像邊界 clamp(座標可超出影像、可為負;裁切是 overlay/viewport 的事,本模組只忠實換算)。不去重、不排序、不過 NMS、不依 conf 過濾(那些是 overlay/filtersort 的事)。

---

## 5. Acceptance Criteria(給 `/pm` 落成 pytest;每條帶具體期望值、用真實檔案 I/O 驗)

> 測試置於 `4_PM_Feedback/test_yolo.py`;`import yolo`;**JSON 一律寫到 `tmp_path` 再 `load` 回來**,逐欄等值斷言(不得只查「非空」)。
> 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_yolo.py -p no:cacheprovider --strict-markers -q`
> 寫檔慣例(供 PM 參考,不入契約):`p = tmp_path / "img.json"; p.write_text(json.dumps(payload), encoding="utf-8"); dets = yolo.load(str(p))`。

### A. 容錯:檔案層級(Tier B 真實 I/O)
- **AC1(缺檔)**:對不存在的路徑,`yolo.load(str(tmp_path / "nope.json")) == []`,且**不建立任何檔案**(`os.path.exists(str(tmp_path / "nope.json")) is False`)。
- **AC2(壞 JSON)**:`p` 內容為 `"{not json"` 時,`yolo.load(str(p)) == []`(不丟例外)。
- **AC3(空檔)**:`p` 內容為空字串 `""` 時,`yolo.load(str(p)) == []`。
- **AC4(頂層型別不符)**:`p` 內容為 `json.dumps(42)`(純數字)時,`yolo.load(str(p)) == []`;內容為 `json.dumps("hi")` 時亦 `== []`。
- **AC5(dict 無已知鍵)**:`p` 內容為 `json.dumps({"foo": [1,2,3]})` 時,`yolo.load(str(p)) == []`。
- **AC6(空偵測陣列)**:`p` 內容為 `json.dumps([])` 時 `== []`;為 `json.dumps({"detections": []})` 時亦 `== []`。
- **AC7(接受 pathlib.Path)**:同一份合法內容,`yolo.load(tmp_path / "img.json") == yolo.load(str(tmp_path / "img.json"))`(`Path` 與 `str` 皆可)。

### B. 頂層容器 schema(list / detections / predictions / objects)
- **AC8(頂層 list)**:`p` = `json.dumps([{"bbox":[10,20,30,40],"cls":"defect","conf":0.9}])` → `yolo.load(str(p)) == [{"bbox":[10,20,30,40],"cls":"defect","conf":0.9}]`(逐欄精確相等,三鍵不多不少)。
- **AC9(detections 鍵)**:`p` = `json.dumps({"detections":[{"bbox":[1,2,3,4],"cls":"a","conf":0.5}]})` → `== [{"bbox":[1,2,3,4],"cls":"a","conf":0.5}]`。
- **AC10(predictions 鍵)**:`p` = `json.dumps({"predictions":[{"bbox":[1,2,3,4],"cls":"a","conf":0.5}]})` → `== [{"bbox":[1,2,3,4],"cls":"a","conf":0.5}]`。
- **AC11(objects 鍵)**:`p` = `json.dumps({"objects":[{"bbox":[1,2,3,4],"cls":"a","conf":0.5}]})` → `== [{"bbox":[1,2,3,4],"cls":"a","conf":0.5}]`。
- **AC12(鍵優先序)**:`p` = `json.dumps({"detections":[{"bbox":[1,1,1,1],"cls":"d","conf":1.0}], "predictions":[{"bbox":[9,9,9,9],"cls":"p","conf":1.0}]})` → 結果 `== [{"bbox":[1,1,1,1],"cls":"d","conf":1.0}]`(優先用 `detections`)。

### C. 座標換算(釘死具體數值)
- **AC13(absolute bbox 直通)**:`{"bbox":[10,20,30,40],"cls":"x","conf":0.8}` → `Detection["bbox"] == [10,20,30,40]`(原樣,不縮放)。
- **AC14(xyxy → xywh)**:`{"xyxy":[10,20,50,80],"cls":"x","conf":0.8}` → `bbox == [10,20,40,60]`(`x=10,y=20,w=50-10=40,h=80-20=60`)。
- **AC15(xyxy 顛倒角點)**:`{"xyxy":[50,80,10,20],"cls":"x","conf":1.0}` → `bbox == [10,20,40,60]`(`min`/`abs` 正規化,等同 AC14)。
- **AC16(xywhn → absolute,給尺寸)**:`yolo.load(<{"xywhn":[0.5,0.5,0.2,0.4],"cls":"x","conf":0.7}>, img_w=200, img_h=100)` → `bbox == [80,30,40,40]`
  (`w=0.2*200=40`、`h=0.4*100=40`、`x=0.5*200-20=80`、`y=0.5*100-20=30`)。
- **AC17(xywhn 缺尺寸 → 跳過該筆)**:同 AC16 的 payload 但 `img_w=None,img_h=None` 呼叫 `load` → `== []`(該筆無法換算被跳過,不丟錯)。
- **AC18(bbox 取整)**:`{"xywhn":[0.5,0.5,0.3,0.3],"cls":"x","conf":1.0}` 配 `img_w=101,img_h=101` → `w=int(0.3*101)=int(30.3)=30`、`h=30`、`x=int(0.5*101-15.15)=int(35.35)=35`、`y=35` → `bbox == [35,35,30,30]`(各值為 `int`,且 `all(isinstance(v,int) for v in bbox)` 為真)。

### D. 類別與信心別名 + 預設
- **AC19(類別別名)**:四份各只用 `class`/`name`/`label`/`cls` 之一(值 `"alias"`)、皆配 `{"bbox":[0,0,1,1],"conf":1.0}` → 四者 `Detection["cls"] == "alias"`。
- **AC20(類別為 int id)**:`{"bbox":[0,0,1,1],"cls":3,"conf":1.0}` → `Detection["cls"] == "3"`(轉字串)。
- **AC21(缺類別 → 空字串)**:`{"bbox":[0,0,1,1],"conf":0.9}`(無任何類別鍵)→ `Detection["cls"] == ""` 且該筆**仍被保留**(`len==1`)。
- **AC22(信心別名)**:`{"bbox":[0,0,1,1],"cls":"x","confidence":0.33}` → `conf == 0.33`;`{"bbox":[0,0,1,1],"cls":"x","score":0.66}` → `conf == 0.66`。
- **AC23(缺信心 → 1.0)**:`{"bbox":[0,0,1,1],"cls":"x"}`(無信心鍵)→ `conf == 1.0` 且該筆保留。
- **AC24(信心夾界)**:三筆 `conf` 分別 `-0.3` / `1.7` / `0.42` → 對應 `Detection["conf"]` 為 `0.0` / `1.0` / `0.42`。
- **AC25(信心非數值 → 1.0)**:`{"bbox":[0,0,1,1],"cls":"x","conf":"high"}` → `conf == 1.0`(轉 float 失敗回預設,不丟錯)且該筆保留。

### E. 逐筆容錯(混入髒資料只跳過壞筆)
- **AC26(缺框 → 跳過該筆)**:`[{"cls":"a","conf":0.9}, {"bbox":[0,0,2,2],"cls":"b","conf":0.8}]` → `load == [{"bbox":[0,0,2,2],"cls":"b","conf":0.8}]`(無框者被跳過,有框者保留)。
- **AC27(框長度錯 → 跳過該筆)**:`[{"bbox":[1,2,3],"cls":"a","conf":1.0}, {"bbox":[1,2,3,4,5],"cls":"b","conf":1.0}, {"bbox":[5,5,5,5],"cls":"c","conf":1.0}]` → `load == [{"bbox":[5,5,5,5],"cls":"c","conf":1.0}]`(長度非 4 的兩筆被跳過)。
- **AC28(陣列元素非 dict → 跳過)**:`[5, "x", null, {"bbox":[0,0,1,1],"cls":"ok","conf":1.0}]`(JSON 內含數字/字串/null)→ `load == [{"bbox":[0,0,1,1],"cls":"ok","conf":1.0}]`。
- **AC29(框含非數值 → 跳過該筆)**:`[{"bbox":[0,0,"x",2],"cls":"a","conf":1.0}, {"bbox":[1,1,2,2],"cls":"b","conf":1.0}]` → `load == [{"bbox":[1,1,2,2],"cls":"b","conf":1.0}]`。
- **AC30(多框鍵優先序)**:`{"bbox":[1,1,1,1],"xyxy":[0,0,9,9],"cls":"x","conf":1.0}` → `bbox == [1,1,1,1]`(`bbox` 優先於 `xyxy`)。

### F. 端到端(ultralytics-ish 真實檔 + 順序 + 形狀)
- **AC31(ultralytics-ish 整檔)**:`p` 寫入
  ```json
  {"image":"wafer_001.png","detections":[
    {"xyxy":[100,100,150,180],"name":"scratch","confidence":0.91},
    {"bbox":[10,20,30,40],"cls":2,"conf":0.5},
    {"cls":"missing_box","conf":0.99},
    {"xywhn":[0.5,0.5,0.1,0.2],"name":"edge","conf":1.3}
  ]}
  ```
  以 `yolo.load(str(p), img_w=200, img_h=100)` 載入,結果**逐欄等於**:
  ```python
  [
    {"bbox":[100,100,50,80], "cls":"scratch",     "conf":0.91},   # xyxy→xywh, name 別名
    {"bbox":[10,20,30,40],   "cls":"2",           "conf":0.5},    # int cls→"2"
    # 第三筆缺框 → 被跳過
    {"bbox":[90,40,20,20],   "cls":"edge",        "conf":1.0},    # xywhn→abs(w=20,h=20,x=100-10=90,y=50-10=40), conf 1.3 夾到 1.0
  ]
  ```
  即 `len == 3`、順序為 `["scratch","2","edge"]`、缺框筆被跳過、各別名/換算/夾界值如上。
- **AC32(每筆形狀恰三鍵)**:對 AC31 結果,`all(set(d.keys()) == {"bbox","cls","conf"} for d in dets)` 為真,且 `all(isinstance(d["bbox"],list) and len(d["bbox"])==4 for d in dets)`、`all(isinstance(v,int) for d in dets for v in d["bbox"])`、`all(isinstance(d["conf"],float) for d in dets)`、`all(isinstance(d["cls"],str) for d in dets)`。
- **AC33(順序保留)**:`p` = `json.dumps([{"bbox":[0,0,1,1],"cls":"first","conf":1.0},{"bbox":[2,2,1,1],"cls":"second","conf":1.0},{"bbox":[3,3,1,1],"cls":"third","conf":1.0}])` → `[d["cls"] for d in yolo.load(str(p))] == ["first","second","third"]`。

### G. `normalize_one` 純函式直驗(單筆,不經檔案)
- **AC34(normalize_one 正常)**:`yolo.normalize_one({"xyxy":[10,20,50,80],"name":"x","score":0.6}) == {"bbox":[10,20,40,60],"cls":"x","conf":0.6}`。
- **AC35(normalize_one 壞輸入回 None)**:`yolo.normalize_one({"cls":"x","conf":0.9}) is None`(缺框);`yolo.normalize_one(5) is None`(非 dict);`yolo.normalize_one({"xywhn":[0.5,0.5,0.1,0.1],"cls":"x","conf":1.0}, img_w=None, img_h=None) is None`(正規化缺尺寸)。

---

## 6. 與其他模組的邊界(防越權)
- **本模組是 `Detection` 形狀的唯一「生產者」**(load JSON → list[Detection]);overlay/filtersort/casepkg 為「消費者」,測試用 dict 模擬、**不得 import yolo**(解耦、可平行驗收)。見 `ROADMAP.md` 第 40-43 行。
- **不負責**畫圖、conf threshold 過濾、class 篩選(那是 `overlay`,Tier A,吃 dict)。
- **不負責**排序 / Review Queue(那是 `filtersort`,吃 dict)。
- **不負責**把偵測寫進 case package(那是 `casepkg`,吃 dict)。
- **不負責**影像邊界裁切 / 座標換顯示尺度(那是 `viewport`/`overlay`)。
- 本模組對外承諾:`load` 永不拋例外;回傳形狀恆為 `list[Detection]`(每筆恰三鍵 `bbox`/`cls`/`conf`、`bbox` 為四個 `int`、`conf` 為 `[0,1]` 內的 `float`、`cls` 為 `str`);僅依賴 Python 標準庫;不修改原圖、不寫任何檔。

## 設計演進(2026-06-27,User 用真實 YOLO 資料集:新增 `.txt` 格式支援)

`load(label_path, img_w, img_h, names=None)` 依**副檔名**分派:`.json` = 原多 schema 容錯;**`.txt` = YOLO 標註格式**(每行 `cls_id cx cy w h [conf]`,空白分隔、座標正規化 0~1)。
- 換算:`w=wn·img_w`、`h=hn·img_h`、`x=cx·img_w − w/2`、`y=cy·img_h − h/2` → `[int(x),int(y),int(w),int(h)]`(同 .json 截斷規約);需有效 `img_w/img_h`(否則回 `[]`)。
- `conf`:第 6 欄存在則取之(clamp `[0,1]`),缺則 `1.0`(YOLO 真值標註無信心 = 全信心)。
- `cls`:`names[cls_id]`(`names` 為 id→名清單,如自 `data.yaml` 載入);缺/越界 → `str(cls_id)`。
- 容錯:空行 / 欄位 <5 / 非數值 → 跳過該行,永不拋。輸出與 `.json` **同形** Detection。
- **不變**:`.json` 路徑與既有 AC 全保留;`names` 僅 `.txt` 用、預設 `None`(向後相容)。
- app 整合層(非本模組契約):YOLO 切分佈局(`<夾>/images/` + `<夾>/labels/`)的影像夾偵測、Model A 標註 sibling `labels/` 解析、
  `data.yaml`/`classes.txt` 類別名載入、`.txt`/`.json` 標註路徑選擇,皆在 `app.py`;本模組只負責「給一個標註檔路徑 → Detection」。

## 設計演進(2026-07-05,port 自 LV:`.txt` 加 segmentation/OBB 守衛)

配合新增 `labelfmt` 多格式支援(見 `26_labelfmt.md`),`_load_yolo_txt` 補上 LV `parse_yolo_boxes` 早有的防呆:
- **≥7 欄的行一律跳過**——那是 segmentation 多邊形(`cls x1 y1 x2 y2 x3 y3 …`)或 OBB(8 座標)格式,
  前 4 個座標會被誤讀成 `cx cy w h`(silent-wrong,畫出一個亂框)。偵測框只認 **5 欄**(GT `cls cx cy w h`)
  或 **6 欄**(pred `cls cx cy w h conf`)。
- 判斷式由 `len(parts) < 5` 改為 `len(parts) < 5 or len(parts) >= 7`;其餘(換算、conf、names、容錯)不變。
- **契約影響**:`load` 回傳形狀、`.json` 路徑、既有 5/6 欄 `.txt` 行為**全不變**;只多擋掉本來就不該被當偵測框的 seg/OBB 行
  (對齊 `1_user_needs/08` User『混了 seg 行不要誤讀成亂框』)。新增測試見 `test_yolo.py` 的 seg/OBB 守衛條目。
