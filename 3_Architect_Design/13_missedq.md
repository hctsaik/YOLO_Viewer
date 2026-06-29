# 設計:missedq(M4 / Tier A,純邏輯)

> `/architect` 模組設計。純邏輯、零 I/O、零 GUI。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死確切 flags/順序,**禁止代理式 AC**。
> 上游:`ROADMAP.md`(第 46 行 M4 模組分解;第 97–101 行 M4 啟動與解耦原則)。
> 相依資料形狀:`Detection`(PO 釘死)、`filtersort` 的 item 形狀(§2.2 逐字延續)、`tagging` 的 reviewed 語義(複用「概念」不複用「實作」,見 §3.5)。
> 心智模型:這是 `filtersort.review_queue` 的「**理由驅動版**」——前者用一條固定優先規則排全部 item;本模組用一組**規則**只挑出「需要人再看一眼」的 item,每筆**附理由碼**並依嚴重度排序。兩者互不 import、各自獨立。

---

## 1. 目的 (Purpose)

對一組影像 item,用一組釘死的規則自動找出「需要人再看一眼」的圖(模型**漏檢** / **誤報** / **低信心** / **未審有框**),為每張附上**理由碼**並依嚴重度排成 Missed-Detection Review Queue(吃 dict,不持久化、不畫圖、不 import 任何上游實作)。

---

## 2. I/O 契約(逐字採用,不得更動簽名)

純邏輯、無 I/O、無副作用、不 mutate 輸入。僅依賴 Python 標準庫。

```python
def flags_for(item: dict, conf_low: float = 0.3, conf_high: float = 0.7) -> list[str]:
    # 回該 item 適用的理由碼(順序釘死,見 §3.3)。無問題 → []
    ...

def missed_queue(items: list[dict], conf_low: float = 0.3, conf_high: float = 0.7) -> list[dict]:
    # 回有 ≥1 flag 的 item,每筆 {"name","reasons","priority"};依 priority 排序(見 §3.4)
    ...
```

### 2.1 模組常數(契約值,釘死)

理由碼為**釘死字串常數**,以模組層級名稱導出(供 UI/測試逐字斷言,不得改字串內容):

```python
REASON_MISSED   = "missed_detection"   # 漏檢:人判缺陷但模型 0 框
REASON_FALSE    = "false_alarm"        # 誤報:有高信心框但人判 false_alarm
REASON_LOWCONF  = "low_confidence"     # 低信心:有框但最大 conf 低於門檻
REASON_UNREVIEWED = "unreviewed_with_det"  # 未審有框:有框但尚未 reviewed

# 順序固定 = flags_for 的輸出檢查順序,亦是同一 item 多碼時的排列順序(見 §3.3)
REASONS = ["missed_detection", "false_alarm", "low_confidence", "unreviewed_with_det"]
```

- `REASONS` — 4 個字串,**順序固定**如上(`len(REASONS) == 4`)。
- 4 個 `REASON_*` 常數值須**逐字等於** `REASONS` 內對應字串(見 AC1/AC2)。
- **嚴重度(priority)** 由 `REASONS` 的索引決定:索引越小越嚴重。一個 item 的 `priority` = 其所有 flag 中**最嚴重(索引最小)** 者的索引(見 §3.4)。即:漏檢(0)> 誤報(1)> 低信心(2)> 未審(3)。

> **嚴重度排序的設計理由**:`漏檢`(模型沒看到真缺陷,品質風險最高)> `誤報`(模型高信心卻判錯,信任風險次之)> `低信心`(框在但模型不確定,需確認)> `未審有框`(只是流程上還沒人看,風險最低)。priority 用「最嚴重 flag 的索引」而非「flag 數量」,讓嚴重度是**確定性的單一整數**、可精確斷言。

### 2.2 item 的形狀(契約,釘死;逐字延續 filtersort §2.2)

```python
item = {
    "name":       str,             # 必備。檔名;佇列 tie-break 的最終裁決鍵
    "sidecar":    dict,            # 缺 → {}。標記資料(欄位語義同 tagging §2.2)
    "detections": list[Detection], # 缺 → []。該圖的偵測清單
}
```

- `Detection = {"bbox":[x,y,w,h], "cls":str, "conf":float(0~1)}`(PO 釘死;本模組只讀 `conf`,不讀 bbox/cls)。
- 本模組對 item **只讀**上述 3 鍵,缺 `sidecar`/`detections` 一律套「預設視同值」(見 §4),**不得拋 `KeyError`**(`name` 除外:`name` 為契約必備鍵,缺 `name` 屬呼叫端違約,Tier A 不做防禦,見 §4g)。
- 與 filtersort 差異:本模組**不讀** `time`(missedq 不依時間排序),其餘形狀逐字一致,故 filtersort 的 FIX 夾具可直接被本模組消費(無需新增鍵)。

### 2.3 由 item / sidecar 衍生的判定量(派生欄位定義,釘死)

| 衍生量 | 定義 | 缺資料時的值 |
|--------|------|--------------|
| `n_det`     | `len(item.get("detections", []))` | `0` |
| `max_conf`  | `max(d["conf"] for d in dets)`;`dets` 為空 → `0.0` | `0.0` |
| `verdict`   | `item.get("sidecar", {}).get("verdict", "unset")` | `"unset"` |
| `reviewed`  | `_is_reviewed(item.get("sidecar", {}))`(布林,見 §3.5) | `False` |

> `max_conf` 取「該圖**最大**偵測 conf」;`n_det` 為「偵測**數量**」。`verdict` 限 `VERDICTS = ["unset","true_defect","false_alarm","reflection"]`(tagging 釘死),但本模組**不校驗**、按字串原值比較(見 §4e)。

### 2.4 門檻參數語義(釘死)

- `conf_low`(預設 `0.3`):低信心門檻。判定用 `max_conf < conf_low`(**嚴格小於**)。
- `conf_high`(預設 `0.7`):高信心門檻。判定用 `max_conf >= conf_high`(**大於等於**)。
- 邊界值釘死:`max_conf == conf_low` → **不**算低信心(因 `<` 嚴格);`max_conf == conf_high` → **算**高信心(因 `>=`)。見 §4d、AC9/AC10。
- 契約假設 `conf_low <= conf_high`,但兩者各自獨立判定(分屬不同理由碼),不因 `conf_low > conf_high` 拋例外(Tier A 信任契約,不做防禦)。

---

## 3. 資料流 (Data Flow)

### 3.1 派生量計算(內部;對單一 item,純讀不修改)
依 §2.3 表計算 `n_det`、`max_conf`、`verdict`、`reviewed`。`max_conf` 對空 `detections` 回 `0.0`(不對空序列呼叫 `max()` 致 `ValueError`)。

### 3.2 四條規則的判定條件(釘死;彼此獨立、可同時成立)

| 理由碼 | 觸發條件(全部為 `True` 才觸發) |
|--------|----------------------------------|
| `missed_detection`     | `verdict == "true_defect"` **且** `n_det == 0`(人判真缺陷,但模型 0 框) |
| `false_alarm`          | `verdict == "false_alarm"` **且** `max_conf >= conf_high`(人判誤報,但模型有高信心框) |
| `low_confidence`       | `n_det > 0` **且** `max_conf < conf_low`(有框但最大信心低於低門檻) |
| `unreviewed_with_det`  | `n_det > 0` **且** `reviewed == False`(有框但尚未 reviewed) |

> 四條規則**互不互斥**:同一 item 可同時命中多條(例:有框、未審、且 max_conf 低 → 同時 `low_confidence` + `unreviewed_with_det`)。`flags_for` 回傳所有命中者,順序依 §3.3。

### 3.3 `flags_for(item, conf_low=0.3, conf_high=0.7) -> list[str]`(釘死)
1. 計算 §2.3 派生量。
2. 依 `REASONS` 的**固定順序**逐一檢查 §3.2 四條件,命中者依序加入結果 list。
3. 回傳的 list **順序 = `REASONS` 索引升序**(即 `missed_detection` < `false_alarm` < `low_confidence` < `unreviewed_with_det`),保證同一 item 的 flags 順序確定可斷言。
4. 無任何條件命中 → 回 `[]`(空 list,不進佇列)。
5. **不 mutate** item。

> 實作策略(釘死,結果須等同):`[r for r, cond in zip(REASONS, [c_missed, c_false, c_lowconf, c_unrev]) if cond]`——保證輸出順序恆等於 REASONS 子序列。

### 3.4 `missed_queue(items, conf_low=0.3, conf_high=0.7) -> list[dict]`(釘死)
1. 對每個 item 算 `reasons = flags_for(item, conf_low, conf_high)`。
2. **只保留** `len(reasons) >= 1` 的 item(無 flag 者不進佇列)。
3. 每筆輸出為**新 dict**:`{"name": item["name"], "reasons": reasons, "priority": p}`,其中
   `p = min(REASONS.index(r) for r in reasons)`(= 該 item **最嚴重 flag** 的索引;reasons 非空故 `min` 必有值)。
4. **排序**(全序,確定可斷言):依 `(priority, name)` **升序**——
   - 第一鍵 `priority` 升序:索引小(越嚴重)排前。
   - 第二鍵 `name` 字典序升序:priority 相同者 name 由小到大(最終 tie-break,保證唯一順序)。
   實作策略(釘死,結果須等同):`sorted(out, key=lambda e: (e["priority"], e["name"]))`。
5. 回**新 list**,空輸入 → 空輸出。**不 mutate** 輸入 items 或其子物件;輸出 dict 為**新建**,不是原 item 的參考(`reasons` 亦為新 list)。

> 輸出 dict 的鍵集合釘死為**恰好** `{"name","reasons","priority"}`(三鍵,不多不少;見 AC18)。不回傳原 item 全文,避免把上游 sidecar/detections 一起拷貝出來造成隱性耦合。

### 3.5 `_is_reviewed(sidecar) -> bool`(內部,複用 tagging 語義但不 import 實作)
讀 `sidecar.get("verdict","unset")` 與 `sidecar.get("review_status","none")`,回 `verdict != "unset"` **或** `review_status == "done"`(布林 OR)。語義**逐字等同** `tagging.is_reviewed`(`3_Architect_Design/05_tagging.md` §3.1 / AC3..AC7)與 `filtersort._is_reviewed`(`10_filtersort.md` §3.4)。
- **為何不 import tagging/filtersort**:ROADMAP 第 100–101 行 M4 解耦原則釘死「missedq 自帶 reviewed 等價邏輯不 import tagging(沿用 M3 解耦慣例)」;且第 52 行釘死消費端「不得 import yolo/sidecar/tagging 的實作」。故本模組**自帶等價邏輯**,以「資料形狀 + 語義契約」對齊,**不建立程式碼相依**。以 `inspect.getsource` 反向稽查(AC23)。

---

## 4. 邊界條件與錯誤處理

a. **空輸入**:`missed_queue([], ...) == []`(空輸出)。`flags_for` 對「乾淨 item」回 `[]`。
b. **缺/空 `detections`**:`n_det = 0`、`max_conf = 0.0`,不對空序列呼叫 `max()`(不拋 `ValueError`)。`n_det == 0` 使 `low_confidence` / `unreviewed_with_det` 兩條(均要求 `n_det > 0`)**不成立**。
c. **缺 `sidecar`**:視同 `{}` → `verdict = "unset"`、`reviewed = False`,不拋 `KeyError`。`verdict == "unset"` 使 `missed_detection`(要求 `true_defect`)、`false_alarm`(要求 `false_alarm`)兩條**不成立**。
d. **門檻邊界(嚴格 vs 等於,釘死)**:`max_conf < conf_low` 用**嚴格 `<`**(`max_conf == conf_low` **不**觸發低信心);`max_conf >= conf_high` 用 **`>=`**(`max_conf == conf_high` **觸發**高信心)。見 AC9/AC10。
e. **`verdict` 為非法值**(不在 `VERDICTS`):不校驗、不拋例外,按字串原值比較(非 `"true_defect"`/`"false_alarm"` 的值不觸發對應規則)。
f. **不 mutate 不變式**:`flags_for`/`missed_queue` 回新物件;不修改 `items`、不修改任一 item dict、不修改其 `sidecar`/`detections` 子物件(以呼叫前後 deepcopy 相等驗證)。輸出 dict 與 `reasons` list 皆為**新建物件**,非原 item 之參考。
g. **缺 `name`**:`name` 為契約必備鍵。缺 `name` 屬呼叫端違約,Tier A 不做防禦(允許 `KeyError` 浮現),**不**靜默以空字串代替——以免遮蔽上游資料缺陷。測試只以「具備 name 的 item」驗收。
h. **`detections` 內 `conf` 缺鍵**:契約假設 Detection 形狀完整(PO 釘死含 `conf`);Tier A 信任契約,不對單筆 Detection 做缺鍵防禦。
i. **多碼共存**:同 item 命中多條時,`reasons` 含全部命中碼(順序依 REASONS),`priority` 取最嚴重(最小索引)。不去重(每碼至多出現一次,本就唯一)。
j. **`reviewed` 與 `unreviewed_with_det` 的關係**:`reviewed == True` 使 `unreviewed_with_det` 不成立,但**不影響** `low_confidence`(後者只看 `n_det>0` 且 `max_conf<conf_low`)——即「已審但低信心有框」仍會被 `low_confidence` 撈出(設計刻意:已審不代表低信心框不需注意)。見 AC13。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以 dict 模擬 item)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_missedq.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import missedq`)。
> **共用 items 夾具 `FIX`(以下多條 AC 共用,請 PM 原樣建立;name 唯一,便於釘死確切順序)**:

```python
FIX = [
    # MISS: 人判 true_defect 但 0 框 → missed_detection(priority 0)
    {"name": "miss.png", "detections": [],
     "sidecar": {"verdict": "true_defect", "review_status": "done"}},
    # FALSE: 人判 false_alarm + 有 0.95(>=0.7)框 → false_alarm(priority 1)
    {"name": "false.png",
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.95}],
     "sidecar": {"verdict": "false_alarm", "review_status": "done"}},
    # LOW: 有框、max_conf 0.20(<0.3)、已審 → low_confidence(priority 2)
    {"name": "low.png",
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.20}],
     "sidecar": {"verdict": "true_defect", "review_status": "done"}},
    # UNREV: 有框 0.80、未審(verdict unset / review none)→ unreviewed_with_det(priority 3)
    {"name": "unrev.png",
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.80}],
     "sidecar": {"verdict": "unset", "review_status": "none"}},
    # CLEAN: 有框 0.80、已審(true_defect)、conf 不低、非 false/miss → 無 flag,不進佇列
    {"name": "clean.png",
     "detections": [{"bbox":[0,0,1,1],"cls":"x","conf":0.80}],
     "sidecar": {"verdict": "true_defect", "review_status": "done"}},
]
# 派生量速查(conf_low=0.3, conf_high=0.7):
#   name       n_det  max_conf  verdict       reviewed  → flags                      priority
#   miss.png   0      0.00      true_defect   True      → ["missed_detection"]        0
#   false.png  1      0.95      false_alarm   True      → ["false_alarm"]             1
#   low.png    1      0.20      true_defect   True      → ["low_confidence"]          2
#   unrev.png  1      0.80      unset         False     → ["unreviewed_with_det"]     3
#   clean.png  1      0.80      true_defect   True      → []                          —
```

**常數契約**
- **AC1**:`missedq.REASONS == ["missed_detection","false_alarm","low_confidence","unreviewed_with_det"]` 且 `len(missedq.REASONS) == 4`。
- **AC2**:`missedq.REASON_MISSED == "missed_detection"` 且 `missedq.REASON_FALSE == "false_alarm"` 且 `missedq.REASON_LOWCONF == "low_confidence"` 且 `missedq.REASON_UNREVIEWED == "unreviewed_with_det"`(4 常數逐字等於 REASONS 對應元素;`[missedq.REASON_MISSED, missedq.REASON_FALSE, missedq.REASON_LOWCONF, missedq.REASON_UNREVIEWED] == missedq.REASONS`)。

**flags_for — 單一規則命中(各規則隔離,確切 flags)**
- **AC3**(漏檢):`flags_for(FIX[0]) == ["missed_detection"]`(miss.png:true_defect + 0 框)。
- **AC4**(誤報):`flags_for(FIX[1]) == ["false_alarm"]`(false.png:false_alarm + conf 0.95>=0.7)。
- **AC5**(低信心):`flags_for(FIX[2]) == ["low_confidence"]`(low.png:有框 + conf 0.20<0.3;已審故無 unreviewed)。
- **AC6**(未審有框):`flags_for(FIX[3]) == ["unreviewed_with_det"]`(unrev.png:有框 0.80 + 未審)。
- **AC7**(乾淨):`flags_for(FIX[4]) == []`(clean.png:有框、已審、conf 不低、verdict 非 false/miss 觸發條件)。

**flags_for — 否定/不觸發(規則邊界)**
- **AC8**(漏檢需 0 框):`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.5}],"sidecar":{"verdict":"true_defect","review_status":"done"}}) == []`(true_defect 但有 1 框 → 不算漏檢;conf 0.5 不低、已審 → 無其他碼)。
- **AC9**(low_confidence 嚴格 `<`,等於不觸發):`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.30}],"sidecar":{"verdict":"true_defect","review_status":"done"}}) == []`(max_conf 0.30 == conf_low 0.3,因 `<` 嚴格 → **不**算低信心)。
- **AC10**(false_alarm `>=` 邊界,等於觸發):`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.70}],"sidecar":{"verdict":"false_alarm","review_status":"done"}}) == ["false_alarm"]`(max_conf 0.70 == conf_high 0.7,因 `>=` → **算**高信心 → false_alarm)。
- **AC11**(false_alarm 需高信心):`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.40}],"sidecar":{"verdict":"false_alarm","review_status":"done"}}) == []`(false_alarm 但 max_conf 0.40 < conf_high 0.7 → 不觸發 false_alarm;0.40 >= conf_low 0.3 故也不低信心;已審 → 無 unreviewed)。

**flags_for — 多碼共存(順序 = REASONS,priority 由最小索引決定)**
- **AC12**(低信心 + 未審同時命中,順序釘死):`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.10}],"sidecar":{"verdict":"unset","review_status":"none"}}) == ["low_confidence","unreviewed_with_det"]`(有框 + conf 0.10<0.3 + 未審 → 兩碼;順序依 REASONS:low_confidence(2)在 unreviewed_with_det(3)前)。
- **AC13**(已審不擋低信心):`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.10}],"sidecar":{"verdict":"true_defect","review_status":"done"}}) == ["low_confidence"]`(已審故無 unreviewed,但 conf 0.10<0.3 仍 low_confidence;證明 §4j「已審不代表低信心框不需注意」)。

**flags_for — 缺鍵/預設(不拋例外)**
- **AC14**(全缺 sidecar/detections):`flags_for({"name":"x"}) == []`(缺 detections→n_det 0、max_conf 0.0;缺 sidecar→verdict unset、reviewed False;四條皆不成立,**不拋 KeyError**)。
- **AC15**(空 detections + true_defect → 漏檢):`flags_for({"name":"x","detections":[],"sidecar":{"verdict":"true_defect"}}) == ["missed_detection"]`(缺 review_status 不影響;n_det 0 + true_defect → 漏檢;n_det 0 故 low/unrev 不成立)。

**flags_for — 自訂門檻**
- **AC16**:`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.50}],"sidecar":{"verdict":"true_defect","review_status":"done"}}, conf_low=0.6) == ["low_confidence"]`(自訂 conf_low=0.6 → max_conf 0.50<0.6 → 低信心;預設 0.3 時本不觸發,證明門檻可調)。
- **AC17**:`flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.50}],"sidecar":{"verdict":"false_alarm","review_status":"done"}}, conf_high=0.4) == ["false_alarm"]`(自訂 conf_high=0.4 → max_conf 0.50>=0.4 → false_alarm;預設 0.7 時本不觸發)。

**missed_queue — 輸出形狀**
- **AC18**(每筆恰三鍵):對 `q = missed_queue(FIX)`,每筆 `set(e.keys()) == {"name","reasons","priority"}`(不多不少;以 `all(set(e.keys()) == {"name","reasons","priority"} for e in q)` 斷言)。

**missed_queue — 釘死順序(嚴重度 priority 升序,tie name 升序)**
- **AC19**(主排序 = priority):`[e["name"] for e in missed_queue(FIX)] == ["miss.png","false.png","low.png","unrev.png"]`(clean.png 無 flag 被排除;其餘依 priority 0,1,2,3 升序;完整推導見 §5.1)。
- **AC20**(每筆 reasons/priority 正確):`missed_queue(FIX) == [`
  `{"name":"miss.png","reasons":["missed_detection"],"priority":0},`
  `{"name":"false.png","reasons":["false_alarm"],"priority":1},`
  `{"name":"low.png","reasons":["low_confidence"],"priority":2},`
  `{"name":"unrev.png","reasons":["unreviewed_with_det"],"priority":3}]`(完整 dict 逐字相等)。

**missed_queue — priority tie-break(同 priority → name 升序)**
- **AC21**:給 `items = [`
  `{"name":"z.png","detections":[],"sidecar":{"verdict":"true_defect"}},`  # 漏檢 priority 0
  `{"name":"a.png","detections":[],"sidecar":{"verdict":"true_defect"}}]`   # 漏檢 priority 0
  `]` → `[e["name"] for e in missed_queue(items)] == ["a.png","z.png"]`(同 priority 0 → name 升序 a<z)。

**missed_queue — priority 取最嚴重(多碼 item 的 priority 隔離驗證)**
- **AC22**:給 `items = [`
  `{"name":"multi.png","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.10}],"sidecar":{"verdict":"unset","review_status":"none"}},`  # 兩碼 [low_confidence, unreviewed_with_det],priority=min(2,3)=2
  `{"name":"miss.png","detections":[],"sidecar":{"verdict":"true_defect"}}]`  # [missed_detection],priority 0
  `]` → `missed_queue(items) == [`
  `{"name":"miss.png","reasons":["missed_detection"],"priority":0},`
  `{"name":"multi.png","reasons":["low_confidence","unreviewed_with_det"],"priority":2}]`(multi 雖有兩碼但 priority=2 = 最嚴重(最小索引)碼;miss priority 0 排前)。

**reviewed 語義對齊 tagging(複用語義、不 import)**
- **AC23**:`missedq` 模組**不 import tagging / yolo / sidecar / filtersort**(以 `import missedq, inspect; src = inspect.getsource(missedq)` 斷言 `"import tagging"`、`"import yolo"`、`"import sidecar"`、`"import filtersort"` 皆不在 `src` 中)。證明複用的是「語義」非「實作相依」。
- **AC24**:reviewed 判定與 tagging 一致 —— `flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.8}],"sidecar":{"verdict":"true_defect","review_status":"none"}}) == []`(verdict 非 unset → reviewed True → 無 unreviewed;conf 0.8 不低、verdict 非 false_alarm → 無其他碼),且 `flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.8}],"sidecar":{"review_status":"done"}}) == []`(review_status done → reviewed True → 無 unreviewed)。對照 `flags_for({"name":"x","detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.8}],"sidecar":{"verdict":"unset","review_status":"none"}}) == ["unreviewed_with_det"]`(兩條件皆否 → 未審)。

**missed_queue — 空輸入 / 不 mutate(metamorphic)**
- **AC25**:`missed_queue([]) == []`(空輸入 → 空輸出);且 `missed_queue([FIX[4]]) == []`(只給乾淨 item → 空佇列,證明「乾淨 item 不進佇列」)。
- **AC26**:`import copy; before = copy.deepcopy(FIX); _ = missed_queue(FIX); assert FIX == before`(輸入(含各 item 之 sidecar/detections 子物件)呼叫後內容不變)。
- **AC27**(輸出為新物件、非原 item 參考):對 `q = missed_queue([FIX[0]])`,`q[0] is not FIX[0]`(輸出 dict 是新建,不是原 item)。

### 5.1 missed_queue(FIX) 逐步推導表(AC19/AC20 唯一真相)

| name      | n_det | max_conf | verdict     | reviewed | flags(REASONS 序)        | priority(min idx) | 進佇列 |
|-----------|-------|----------|-------------|----------|---------------------------|--------------------|--------|
| miss.png  | 0     | 0.00     | true_defect | True     | `["missed_detection"]`    | 0                  | ✅      |
| false.png | 1     | 0.95     | false_alarm | True     | `["false_alarm"]`         | 1                  | ✅      |
| low.png   | 1     | 0.20     | true_defect | True     | `["low_confidence"]`      | 2                  | ✅      |
| unrev.png | 1     | 0.80     | unset       | False    | `["unreviewed_with_det"]` | 3                  | ✅      |
| clean.png | 1     | 0.80     | true_defect | True     | `[]`                      | —                  | ❌      |

排序鍵 `(priority, name)` 升序:`(0,"miss.png") < (1,"false.png") < (2,"low.png") < (3,"unrev.png")`
→ **`["miss.png","false.png","low.png","unrev.png"]`** ✅(AC19 唯一期望值;AC20 為含 reasons/priority 的完整 dict 形式)。

---

## 5.2 給 /pm 的 Metamorphic 提示(額外健壯性,建議落成測試)

1. **乾淨 item 不進佇列(隔離)**:對任意「`verdict in {"true_defect","reflection"}`、有框、`max_conf >= conf_low`、且 `reviewed == True`」的 item,`flags_for(item) == []` 且該 item 不出現在 `missed_queue([item])`(即 §5.1 clean.png 的一般化)。
2. **佇列 ⊆ 輸入(保留多重集合,只篩不增)**:`missed_queue(items)` 內每筆 `name` 都來自 `items` 中某 item 的 `name`,且 `len(missed_queue(items)) == sum(1 for it in items if flags_for(it))`(進佇列數 = 有 ≥1 flag 的 item 數,不增不漏)。
3. **priority 隔離(最嚴重碼決定)**:對任一進佇列筆,`e["priority"] == min(REASONS.index(r) for r in e["reasons"])` 且 `0 <= e["priority"] <= 3`;改變 item 使其新增一個**更嚴重**(更小索引)的 flag → 其 priority 嚴格變小、排序位置不會後移(可用「給 low.png 再補成 0 框 true_defect 使其得 missed_detection」對照前後)。
4. **flags 順序恆為 REASONS 子序列**:對任意 item,`flags_for(item)` 是 `REASONS` 的子序列(`[r for r in REASONS if r in flags_for(item)] == flags_for(item)`),即輸出順序永遠不違反 REASONS 的固定排列。
5. **priority 排序穩定可重現**:對 name 唯一的 items,`missed_queue` 輸出唯一(再跑一次完全相等),且 `[e["name"] for e in q]` 與「依 `(priority,name)` 手算」一致(無隨機性)。
6. **門檻單調性(low_confidence)**:固定一個「有框、未觸發其他碼」的 item,提高 `conf_low` 跨過其 max_conf 後,`low_confidence` 從不命中變命中(門檻語義正確、方向不反)。

---

## 6. 與其他模組的邊界(防越權)

- **不負責**讀檔/寫檔/持久化(`sidecar`/`imgio` 的事);item 與其 sidecar/detections 由呼叫端以 dict 傳入。
- **不負責**「產生」Detection(那是 `yolo`:load JSON→list[Detection],容錯)。本模組**只消費** Detection 的 `conf`,**嚴禁 import yolo**(ROADMAP 第 52 行釘死)。
- **不負責**畫 bbox / threshold-class 篩選(那是 `overlay`)。
- **不負責**通用排序與「排全部 item」的預設 Review Queue(那是 `filtersort.review_queue`:吃同形 item、用一條固定優先規則排**全部**)。本模組與 filtersort 的差異:missedq 用**規則**只挑**子集**並附**理由碼** + 嚴重度 priority;兩者**互不 import**(ROADMAP 第 100 行),僅共用 item 形狀與 reviewed 語義(各自自帶等價邏輯)。
- **不負責** sidecar 的查詢 predicate(那是 `tagging.matches`/`filter_records`);本模組與 tagging 的交集僅「reviewed 語義」,以**自帶等價邏輯**對齊、**不建立 import 相依**(理由見 §3.5)。
- 本模組對外承諾:純函式、無副作用、輸入不被 mutate、確定性全序排序(`(priority,name)`)、缺鍵以預設視同值不拋 `KeyError`(`name` 除外)、僅依賴 Python 標準庫。
