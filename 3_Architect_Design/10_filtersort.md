# 設計:filtersort(M3 / Tier A,純邏輯)

> `/architect` 模組設計。純邏輯、零 I/O、零 GUI。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死確切順序/數值,**禁止代理式 AC**。
> 上游:`2_PO_PRD/01`(M3 模組分解第 54 行)、`ROADMAP.md`(第 37、40–43 行 M3 共用契約)。
> 相依資料形狀:`Detection`(PO 釘死)、`tagging` 的 `is_reviewed` 語義(複用「概念」不複用「實作」,見 §6)。

---

## 1. 目的 (Purpose)

對一組影像 item 提供「穩定、可重現的智慧排序」與「一條釘死的預設 Review Queue 優先規則」,作為 app 縮圖牆/filmstrip 排序與審查排程的純邏輯底座(吃 dict,不持久化、不畫圖、不 import 任何上游實作)。

---

## 2. I/O 契約(逐字採用,不得更動簽名)

純邏輯、無 I/O、無副作用、不 mutate 輸入。僅依賴 Python 標準庫。

```python
def sort_items(items: list[dict], key: str, reverse: bool = False) -> list[dict]:
    # 穩定排序,回新 list(原序資料不被 mutate);key ∈ SORT_KEYS
    ...

def review_queue(items: list[dict]) -> list[dict]:
    # 釘死的預設優先規則(見 §3.3),回新 list
    ...
```

### 2.1 模組常數(契約值,釘死)

```python
SORT_KEYS = ["name", "time", "conf", "n_det", "reviewed", "tagged"]
```
- `SORT_KEYS` — 6 個字串,**順序固定**如上(`len(SORT_KEYS) == 6`)。此即 `sort_items` 合法 `key` 的全集。
- `key` 不在 `SORT_KEYS` → 拋 `ValueError`(見 §4a)。

### 2.2 item 的形狀(契約,釘死;測試以 dict 模擬)

```python
item = {
    "name":       str,             # 必備。檔名,排序/tie-break 的最終裁決鍵
    "time":       float | int,     # 缺 → 0.0(視同 0)。時間戳/修改時間
    "sidecar":    dict,            # 缺 → {}。標記資料(欄位語義同 tagging §2.2)
    "detections": list[Detection], # 缺 → []。該圖的偵測清單
}
```
- `Detection = {"bbox":[x,y,w,h], "cls":str, "conf":float(0~1)}`(PO 釘死;本模組只讀 `conf`,不讀 bbox/cls)。
- 本模組對 item **只讀**上述 4 鍵,缺鍵一律套「預設視同值」(見 §4),**不得拋 `KeyError`**(`name` 除外:`name` 為契約必備鍵,缺 `name` 屬呼叫端違約,Tier A 不做防禦,見 §4h)。

### 2.3 由 item 衍生的排序量(派生欄位定義,釘死)

| 衍生量 | 定義 | 缺資料時的值 |
|--------|------|--------------|
| `name`     | `item["name"]`(字串字典序,Python 預設 `<`,大小寫敏感) | —(必備) |
| `time`     | `item.get("time", 0.0)` | `0.0` |
| `conf`     | `max(d["conf"] for d in dets)`;`dets` 為空 → `0.0` | `0.0` |
| `n_det`    | `len(item.get("detections", []))` | `0` |
| `reviewed` | `_is_reviewed(item.get("sidecar", {}))`(布林,見 §3.4) | `False` |
| `tagged`   | `len(item.get("sidecar", {}).get("tags", [])) > 0`(布林:有無 tags) | `False` |

> `conf` 取「該圖**最大**偵測 conf」;`n_det` 為「偵測**數量**」。布林衍生量(`reviewed`/`tagged`)在排序時依 Python `False < True`。

---

## 3. 資料流 (Data Flow)

### 3.1 排序鍵函式 `_keyfunc(key)`(內部;對單一 item 取派生量)
依 `key` 回上表對應的派生量(純讀,不修改 item)。`key` 非法在進入排序前先檢查並拋 `ValueError`。

### 3.2 `sort_items(items, key, reverse=False) -> list`
1. `key` 不在 `SORT_KEYS` → 拋 `ValueError`(訊息含該 key;見 §4a)。
2. 取每個 item 的派生量為「主鍵」,以 `name`(字典序)為**固定 tie-break 次鍵**。
3. 採**穩定排序**:用 Python `sorted(items, key=...)`,`key` 回傳 `(primary, name)` 的 tuple——
   - 因 tuple 第二元固定為 `name`,**所有 key 的 tie-break 皆為 name 字典序(升序),且不受 `reverse` 影響**(見 §3.2.1)。
4. `reverse=True` → 對「主鍵」做反序;**tie-break 的 name 仍維持升序**(見 §3.2.1 的精確定義)。
5. 回**新 list**(`sorted` 本就回新 list;item dict 物件為同一參考但內容不被改),不 mutate `items`。

#### 3.2.1 reverse 與 tie-break 的精確語義(釘死,避免 false-green)
- `reverse=False`:以 `(primary, name)` 升序排序。即主鍵升序;主鍵相同者 name 升序。
- `reverse=True`:**僅主鍵反轉為降序;主鍵相同者 name 維持升序(字典序由小到大)**。
  - 實作義務:`reverse=True` **不可**用 `sorted(..., reverse=True)` 直接整個 tuple 反轉(那會把 name 也反成降序,違反本契約)。
  - 釘死實作策略(擇一,結果須等同):
    - 數值型主鍵(`time`/`conf`/`n_det`):`sorted(items, key=lambda it: (-primary, name))`——主鍵取負得降序,name 仍升序。
    - 布林型主鍵(`reviewed`/`tagged`):視 `False=0/True=1`,`reverse=True` 時以 `-int(primary)` 為主鍵,name 升序(即 True 在前、False 在後;同組內 name 升序)。
    - 字串主鍵(`name`):`reverse=True` 時主鍵與 tie-break 同為 name,結果即 name 降序(此情況主鍵=tie-break,無分歧)。
- **不變式**:對任一 `key`,`sort_items(x, key, reverse=True)` 與「先 `sort_items(x, key, reverse=False)` 再對『主鍵分組』整組反轉、但組內維持 name 升序」結果相同(見 §5 metamorphic 提示)。

### 3.3 `review_queue(items) -> list`(預設優先規則,釘死)
回一條**確定、可被精確斷言**的排序。優先順序(由先到後,逐層 tie-break):

1. **第一鍵 — 待審優先**:`has_det_and_unreviewed`(該 item「有偵測(`n_det > 0`)**且** 未 reviewed(`reviewed == False`)」)為 `True` 者**排前面**。
2. **第二鍵 — 最大 conf 由高到低**:`conf`(該圖最大偵測 conf,無偵測=0.0)**降序**。
3. **第三鍵 — name 字典序由小到大**:`name` **升序**(最終 tie-break,保證全序唯一可斷言)。

實作策略(釘死,結果須等同):`sorted(items, key=lambda it: (0 if (n_det>0 and not reviewed) else 1, -conf, name))`。
- 第一元 `0/1`:待審群組得 0 排前、其餘得 1 排後(升序即「待審在前」)。
- 第二元 `-conf`:conf 降序。
- 第三元 `name`:字典序升序。
- 回**新 list**,不 mutate 輸入。空輸入 → 空輸出。

> 設計理由:Review Queue 的價值是「把人最該先看的(有模型偵測卻還沒人判)頂到最前」,同群內信心高的先看,最後以檔名穩定收斂為唯一順序(可精確斷言、無隨機性)。

### 3.4 `_is_reviewed(sidecar) -> bool`(內部,複用 tagging 語義但不 import 實作)
讀 `sidecar.get("verdict","unset")` 與 `sidecar.get("review_status","none")`,回 `verdict != "unset"` **或** `review_status == "done"`(布林 OR)。語義**逐字等同** `tagging.is_reviewed`(`3_Architect_Design/05_tagging.md` §3.1 / AC3..AC7)。
- **為何不 import tagging**:ROADMAP 第 43 行 M3 共用契約釘死「消費端不得 import yolo/sidecar/tagging 的實作(解耦、可獨立驗收)」。故本模組**自帶等價邏輯**,以「資料形狀 + 語義契約」對齊,不建立程式碼相依。

---

## 4. 邊界條件與錯誤處理

a. **非法 `key`**:`sort_items(items, "size")`(`"size"` ∉ `SORT_KEYS`)→ 拋 `ValueError`。**不得**靜默回原序或回空。
b. **空輸入**:`sort_items([], <任一合法 key>) == []`;`review_queue([]) == []`。
c. **缺 `time`**:視同 `0.0`,參與數值比較,不拋例外。
d. **缺/空 `detections`**:`conf` 派生為 `0.0`、`n_det` 為 `0`,不拋例外。
e. **缺 `sidecar`**:視同 `{}` → `reviewed=False`、`tagged=False`,不拋例外。
f. **`detections` 內 `conf` 缺鍵**:契約假設 Detection 形狀完整(PO 釘死含 `conf`);Tier A 信任契約,不對單筆 Detection 做缺鍵防禦。
g. **不 mutate 不變式**:`sort_items`/`review_queue` 回新 list;不修改 `items`、不修改任一 item dict、不修改其 `sidecar`/`detections` 子物件(以呼叫前後 deepcopy 相等驗證)。回傳 list 內為原 item 物件之參考(同一物件,順序重排)。
h. **缺 `name`**:`name` 為契約必備鍵。缺 `name` 屬呼叫端違約,Tier A 不做防禦(允許 `KeyError` 浮現),**不**靜默以空字串代替——以免遮蔽上游資料缺陷。測試只以「具備 name 的 item」驗收。
i. **`reverse` 對布林鍵**:`False < True`;`reverse=False` 時 `False` 群在前、`True` 群在後;`reverse=True` 時 `True` 群在前、`False` 群在後;**兩種情況同群內 name 皆升序**。
j. **重複 name**:允許;name 相同的 item 之間,因 tuple key 已無更細鍵,維持 Python 穩定排序的「原始相對順序」(等同 name 升序下的穩定性,見 AC 釘值用唯一 name 避免歧義)。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以 dict 模擬 item)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_filtersort.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import filtersort`)。
> **共用測試夾具 `FIX`(以下多條 AC 共用,請 PM 原樣建立)**:

```python
# 共用 items(name 唯一,便於釘死確切順序)
FIX = [
    {"name": "b.png", "time": 30.0,
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.90}],
     "sidecar": {"verdict":"unset","review_status":"none","tags":[]}},          # n_det=1 conf=0.90 reviewed=F tagged=F
    {"name": "a.png", "time": 10.0,
     "detections": [],
     "sidecar": {"verdict":"true_defect","tags":["True Defect"]}},               # n_det=0 conf=0.0  reviewed=T tagged=T
    {"name": "d.png", "time": 20.0,
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.50},
                    {"bbox":[0,0,1,1],"cls":"y","conf":0.95}],
     "sidecar": {"review_status":"done","tags":[]}},                             # n_det=2 conf=0.95 reviewed=T tagged=F
    {"name": "c.png", "time": 40.0,
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.70}],
     "sidecar": {}},                                                             # n_det=1 conf=0.70 reviewed=F tagged=F
]
# 派生量速查:
#   name  time  conf   n_det  reviewed  tagged
#   b.png 30.0  0.90   1      False     False
#   a.png 10.0  0.00   0      True      True
#   d.png 20.0  0.95   2      True      False
#   c.png 40.0  0.70   1      False     False
```

**常數契約**
- **AC1**:`filtersort.SORT_KEYS == ["name","time","conf","n_det","reviewed","tagged"]` 且 `len(filtersort.SORT_KEYS) == 6`。

**sort_items — name(字典序)**
- **AC2**:`[it["name"] for it in sort_items(FIX, "name")] == ["a.png","b.png","c.png","d.png"]`(升序)。
- **AC3**:`[it["name"] for it in sort_items(FIX, "name", reverse=True)] == ["d.png","c.png","b.png","a.png"]`(降序)。

**sort_items — time(數值)**
- **AC4**:`[it["name"] for it in sort_items(FIX, "time")] == ["a.png","d.png","b.png","c.png"]`(time 10,20,30,40 升序)。
- **AC5**:`[it["name"] for it in sort_items(FIX, "time", reverse=True)] == ["c.png","b.png","d.png","a.png"]`(time 降序)。

**sort_items — conf(該圖最大偵測 conf;無偵測=0)**
- **AC6**:`[it["name"] for it in sort_items(FIX, "conf")] == ["a.png","c.png","b.png","d.png"]`(conf 0.0,0.70,0.90,0.95 升序)。
- **AC7**:`[it["name"] for it in sort_items(FIX, "conf", reverse=True)] == ["d.png","b.png","c.png","a.png"]`(conf 降序)。

**sort_items — n_det(偵測數)**
- **AC8**:`[it["name"] for it in sort_items(FIX, "n_det")] == ["a.png","b.png","c.png","d.png"]`(n_det 0,1,1,2 升序;b 與 c 同為 1 → tie-break name 升序 b<c)。
- **AC9**:`[it["name"] for it in sort_items(FIX, "n_det", reverse=True)] == ["d.png","b.png","c.png","a.png"]`(n_det 降序;同為 1 的 b/c **tie-break 仍 name 升序 b<c**,不隨 reverse 反轉)。

**sort_items — reviewed(bool:False<True)**
- **AC10**:`[it["name"] for it in sort_items(FIX, "reviewed")] == ["b.png","c.png","a.png","d.png"]`(False 群在前:b,c(name 升序);True 群在後:a,d(name 升序))。
- **AC11**:`[it["name"] for it in sort_items(FIX, "reviewed", reverse=True)] == ["a.png","d.png","b.png","c.png"]`(True 群在前:a,d(name 升序);False 群在後:b,c(name 升序);**同群 name 不反轉**)。

**sort_items — tagged(bool:有無 tags)**
- **AC12**:`[it["name"] for it in sort_items(FIX, "tagged")] == ["b.png","c.png","d.png","a.png"]`(tagged=False 群:b,c,d(name 升序);tagged=True 群:a)。
- **AC13**:`[it["name"] for it in sort_items(FIX, "tagged", reverse=True)] == ["a.png","b.png","c.png","d.png"]`(tagged=True 群:a 在前;False 群:b,c,d(name 升序))。

**sort_items — 非法 key / 空輸入**
- **AC14**:`sort_items([], "name") == []` 且 `sort_items([], "conf", reverse=True) == []`(空輸入 → 空輸出)。
- **AC15**:`sort_items(FIX, "size")` 拋 `ValueError`(`"size"` ∉ SORT_KEYS);以 `pytest.raises(ValueError)` 驗證。

**sort_items — 不 mutate**
- **AC16**:`import copy; before = copy.deepcopy(FIX); _ = sort_items(FIX, "conf", reverse=True); assert FIX == before`(輸入(含各 item 之 sidecar/detections 子物件)呼叫後內容不變)。
- **AC17**:`sort_items(FIX, "name")` 回傳值是**新 list**(`sort_items(FIX,"name") is not FIX`),但其中元素為原 item 物件之參考(`sort_items(FIX,"name")[0] is FIX[1]` —— 排序後第一個是原 FIX[1] 的 a.png)。

**review_queue — 釘死預設順序**
- **AC18**:`[it["name"] for it in review_queue(FIX)] == ["b.png","c.png","d.png","a.png"]`(唯一期望值,完整推導見 §5.1 表)。
  待審群(`n_det>0 且 未reviewed`)= {b.png(conf0.90), c.png(conf0.70)},依 conf **降序**在前 → `b,c`;已審群 = {d.png(conf0.95), a.png(conf0.0)},依 conf 降序在後 → `d,a`。合併 = `["b.png","c.png","d.png","a.png"]`。

**review_queue — 空輸入 / 不 mutate**
- **AC19**:`review_queue([]) == []`。
- **AC20**:`import copy; before = copy.deepcopy(FIX); _ = review_queue(FIX); assert FIX == before`(不 mutate 輸入)。

**review_queue — 規則隔離驗證(各層獨立可斷言)**
- **AC21**(第一鍵:待審優先壓過 conf):給 `items = [`
  `{"name":"hi.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.99}],"sidecar":{"verdict":"true_defect"}},`  # 已審、conf 高
  `{"name":"lo.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.10}],"sidecar":{}}]`                         # 待審、conf 低
  `]` → `[it["name"] for it in review_queue(items)] == ["lo.png","hi.png"]`(待審 lo 即使 conf 低仍排在已審 hi 前)。
- **AC22**(第二鍵:同為待審時 conf 降序):給 `items = [`
  `{"name":"p.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.30}],"sidecar":{}},`
  `{"name":"q.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.80}],"sidecar":{}}]`
  `]` → `== ["q.png","p.png"]`(皆待審 → conf 0.80 在前)。
- **AC23**(第三鍵:同群同 conf 時 name 升序):給 `items = [`
  `{"name":"z.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.50}],"sidecar":{}},`
  `{"name":"y.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.50}],"sidecar":{}}]`
  `]` → `== ["y.png","z.png"]`(同待審、同 conf 0.50 → name 升序 y<z)。
- **AC24**(無偵測者落入「非待審」群):給 `items = [`
  `{"name":"m.png","detections":[],"sidecar":{}},`                                                    # n_det=0 → 非待審
  `{"name":"n.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.10}],"sidecar":{}}]`            # 待審
  `]` → `== ["n.png","m.png"]`(有偵測且未審的 n 在前;m 無偵測不算待審)。

**reviewed 語義對齊 tagging(複用語義、不 import)**
- **AC25**:`sort_items` 對 `reviewed` 的判定與 tagging 一致 —— 給
  `it_a = {"name":"a","detections":[],"sidecar":{"verdict":"true_defect"}}`(verdict 非 unset → reviewed),
  `it_b = {"name":"b","detections":[],"sidecar":{"review_status":"done"}}`(review_status done → reviewed),
  `it_c = {"name":"c","detections":[],"sidecar":{"verdict":"unset","review_status":"none"}}`(未 reviewed),
  則 `[it["name"] for it in sort_items([it_a,it_b,it_c], "reviewed")] == ["c","a","b"]`(c False 在前;a,b True 在後 name 升序)。
- **AC26**:`filtersort` 模組**不 import tagging / yolo / sidecar**(可由 `import filtersort, inspect; src = inspect.getsource(filtersort)` 斷言 `"import tagging"`、`"import yolo"`、`"import sidecar"` 皆不在 source 中;或讀 `5_PG_Develop/filtersort.py` 確認無對應 import 行)。證明複用的是「語義」非「實作相依」。

### 5.1 review_queue(FIX) 逐步推導表(AC18 唯一真相)

| name  | n_det | reviewed | 待審(n_det>0 且 未reviewed) | 第一鍵 | conf | 第二鍵(-conf) | 第三鍵(name) |
|-------|-------|----------|------------------------------|--------|------|----------------|----------------|
| b.png | 1     | False    | ✅ 是                         | 0      | 0.90 | -0.90          | b.png          |
| c.png | 1     | False    | ✅ 是                         | 0      | 0.70 | -0.70          | c.png          |
| d.png | 2     | True     | ❌ 否                         | 1      | 0.95 | -0.95          | d.png          |
| a.png | 0     | True     | ❌ 否                         | 1      | 0.00 | -0.00          | a.png          |

排序鍵 tuple `(第一鍵, -conf, name)` 升序:
- b.png `(0, -0.90, "b.png")`
- c.png `(0, -0.70, "c.png")`
- d.png `(1, -0.95, "d.png")`
- a.png `(1, -0.00, "a.png")`

升序排列 → **`["b.png","c.png","d.png","a.png"]`** ✅(此為 AC18 唯一期望值)。

---

## 5.2 給 /pm 的 Metamorphic 提示(額外健壯性,建議落成測試)

1. **與內建 sorted 等價(name)**:`[it["name"] for it in sort_items(items, "name")] == sorted(it["name"] for it in items)`(對任意 name 唯一的 items)。
2. **reverse 是主鍵反序、tie 穩定**:對任一數值/字串 key,`sort_items(x, key, reverse=True)` 的**主鍵序列**是 `sort_items(x, key, reverse=False)` 主鍵序列的反序;但**主鍵相同的群組內 name 仍為升序**(不隨 reverse 反轉)——可用「含 tie 的 n_det(AC8/AC9 的 b/c 同為 1)」對照驗證:reverse 前後 b/c 的相對順序皆 `b<c`。
3. **不變式 — 排序保留多重集合**:`sorted(it["name"] for it in sort_items(items, key, reverse)) == sorted(it["name"] for it in items)`(排序不增刪 item;對任一合法 key/reverse 成立)。
4. **冪等(同 key 再排不變)**:`sort_items(sort_items(items, key), key) == sort_items(items, key)`(穩定排序對同 key 冪等)。
5. **review_queue 為全序**:對 name 唯一的 items,`review_queue` 輸出唯一且 `len(review_queue(items)) == len(items)`(不增刪)。

---

## 6. 與其他模組的邊界(防越權)

- **不負責**讀檔/寫檔/持久化(`sidecar`/`imgio` 的事);item 與其 sidecar/detections 由呼叫端以 dict 傳入。
- **不負責**「產生」Detection(那是 `yolo`:load JSON→list[Detection],容錯)。本模組**只消費** Detection 的 `conf`,**嚴禁 import yolo**(ROADMAP 第 43 行釘死)。
- **不負責**畫 bbox / threshold-class 篩選(那是 `overlay`)。
- **不負責** sidecar 的查詢 predicate(那是 `tagging.matches`/`filter_records`);本模組與 tagging 的交集僅「reviewed 語義」,且以**自帶等價邏輯**對齊、**不建立 import 相依**(理由見 §3.4)。
- 本模組對外承諾:純函式、無副作用、輸入不被 mutate、穩定排序、非法 key 拋 `ValueError`、僅依賴 Python 標準庫。
