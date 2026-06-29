# 設計:tagging(M2 / Tier A,純邏輯)

> `/architect` 模組設計。純邏輯、零 I/O、零 GUI。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死數值/行為。
> 上游:`2_PO_PRD/01`(M2 模組分解第 45 行)、`ROADMAP.md`(第 28 行)。相依資料形狀:`sidecar` 模組(同輪設計;本模組測試自行用 dict 模擬)。

---

## 1. 目的 (Purpose)
把「三層標記模型(Bookmark / Verdict / Action-tags)+ 內建標籤清單」固定成一組常數與純函式,提供「一筆 sidecar 是否符合查詢條件」的判定 predicate 與集合篩選,作為 app 搜尋面板與 M3 `filtersort` Review Queue 的共用底座。

---

## 2. I/O 契約 (逐字採用,不得更動簽名)

純邏輯、無 I/O。

```python
BUILTIN_TAGS = ["Need Review","Need Discuss","Potential Miss","False Alarm","True Defect","Reflection","Low Confidence","New Pattern","Golden Case","Need Labeling","Need Retrain"]
VERDICTS = ["unset","true_defect","false_alarm","reflection"]

def matches(sidecar: dict, query: dict) -> bool:
    # query 條件 AND;支援 tags(預設含任一,query 可給 mode="all")、verdict、review_status、reviewed(bool)、bookmarked(bool)、text(comment 子字串)
    ...

def filter_records(items: list[(record, sidecar)], query: dict) -> list:
    # 回符合的 record
    ...

def is_reviewed(sidecar) -> bool:
    # verdict!="unset" 或 review_status=="done"
    ...
```

### 2.1 模組常數(契約值,釘死)
- `BUILTIN_TAGS` — 11 個字串,**順序固定**如上(`len(BUILTIN_TAGS) == 11`)。此順序即 UI 呈現順序,亦是契約。
- `VERDICTS` — 4 個字串:`"unset"`(預設/未判)、`"true_defect"`、`"false_alarm"`、`"reflection"`。`VERDICTS[0] == "unset"`。

### 2.2 三層標記模型(語義說明,非另開函式)
| 層 | sidecar 欄位 | 型別 | 預設(欄位缺漏時的視同值) | 角色 |
|----|--------------|------|----------------------------|------|
| Bookmark | `bookmarked` | `bool` | `False` | 快速書籤(布林開關) |
| Verdict  | `verdict`    | `str`(限 `VERDICTS`) | `"unset"` | 單選的人工判定結論 |
| Action   | `tags`       | `list[str]` | `[]` | 可多選的行動/狀態標籤(內建 `BUILTIN_TAGS`,亦允許自訂字串) |
| (輔助) review 狀態 | `review_status` | `str` | `"none"` | 審查流程狀態;`"done"` 視為已審 |
| (輔助) 文字 | `comment` | `str` | `""` | 自由註解,供 `text` 子字串搜尋 |

> 本模組**只讀** sidecar dict 的上述鍵,**不寫、不持久化**;鍵缺漏一律以「預設視同值」處理(見 §4)。

### 2.3 sidecar 的最小形狀(測試以 dict 模擬即可)
```python
sidecar = {
    "bookmarked":    bool,        # 缺 → False
    "verdict":       str,         # 缺 → "unset"；屬於 VERDICTS
    "tags":          list[str],   # 缺 → []
    "review_status": str,         # 缺 → "none"；"done" 表已審
    "comment":       str,         # 缺 → ""
}
```

### 2.4 query 的形狀(所有鍵皆選用;AND 組合)
```python
query = {
    "tags":          list[str],   # 篩選含的 Action 標籤
    "mode":          str,         # "any"(預設)| "all"；僅作用於 tags 條件
    "verdict":       str,         # 要求 sidecar.verdict 完全等於此值
    "review_status": str,         # 要求 sidecar.review_status 完全等於此值
    "reviewed":      bool,        # 要求 is_reviewed(sidecar) == 此值
    "bookmarked":    bool,        # 要求 sidecar.bookmarked == 此值
    "text":          str,         # 要求(大小寫不敏感)為 sidecar.comment 的子字串
}
```

---

## 3. 資料流 (Data Flow)

### 3.1 `is_reviewed(sidecar) -> bool`
讀 `sidecar.get("verdict","unset")` 與 `sidecar.get("review_status","none")` → 回 `verdict != "unset"` **或** `review_status == "done"`(布林 OR)。不讀其他欄位。

### 3.2 `matches(sidecar, query) -> bool`
逐條件求值,以 **AND** 合併;query 未給的鍵 = 該條件不參與(視為通過)。空 query → 一律 `True`。各條件:

1. **tags** — 設 `S = set(sidecar.get("tags", []))`、`Q = query["tags"]`。
   - `mode == "all"` → 條件成立 ⇔ `set(Q).issubset(S)`(Q 為空集合 → 視同無此條件 → 通過)。
   - 否則(`mode` 預設 `"any"` 或缺)→ 條件成立 ⇔ `S & set(Q)` 非空(Q 為空 → 不通過,因「要求含任一」但沒給任何 → 視為無此條件 → 通過,見 §4 邊界 b)。
2. **verdict** — 成立 ⇔ `sidecar.get("verdict","unset") == query["verdict"]`(精確相等)。
3. **review_status** — 成立 ⇔ `sidecar.get("review_status","none") == query["review_status"]`(精確相等)。
4. **reviewed** — 成立 ⇔ `is_reviewed(sidecar) == query["reviewed"]`(布林相等;可查「未審」)。
5. **bookmarked** — 成立 ⇔ `sidecar.get("bookmarked", False) == query["bookmarked"]`。
6. **text** — 成立 ⇔ `query["text"].lower() in sidecar.get("comment","").lower()`(大小寫不敏感子字串;空字串 `""` 是任何字串的子字串 → 通過)。

所有「有給」的條件須**全部**成立才回 `True`。

### 3.3 `filter_records(items, query) -> list`
`items` 為 `(record, sidecar)` 二元組序列。對每個元素計算 `matches(sidecar, query)`,**保留原順序**輸出符合者的 `record`(僅 record,不含 sidecar)。回傳新 list,不修改輸入。

---

## 4. 邊界條件與錯誤處理

a. **空 query(`{}`)**:`matches` 回 `True`;`filter_records` 原樣回傳所有 record(順序不變)。
b. **query 給了 `tags: []`**(空清單,無論 mode):視為「未指定 tags 條件」→ 該條件通過(不因空清單把全部刷掉)。
c. **sidecar 缺鍵**:一律套 §2.2 預設視同值;`matches`/`is_reviewed` 不得拋 `KeyError`。
d. **`sidecar.tags` 含自訂(非 BUILTIN)字串**:照常參與集合比對;本模組不校驗 tag 是否屬於 `BUILTIN_TAGS`(允許自訂標籤)。
e. **`verdict` 為非法值**(不在 `VERDICTS`):`matches`/`is_reviewed` 不校驗、不拋例外,按字串原值比較(非法但非 `"unset"` 的 verdict 會使 `is_reviewed` 回 `True`,因 `!= "unset"`)。
f. **`text` 大小寫**:比對一律以 `.lower()` 正規化兩側;`text == ""` → 通過。
g. **`tags`/`verdict` 等 query 值型別**:契約假設呼叫端給對型別;本模組不做型別防禦(Tier A 純邏輯,信任契約)。`tags` 條件以 `set()` 包裹故對 list/tuple 皆可。
h. **`filter_records` 不變式**:輸出長度 `<= len(items)`;輸出為輸入 record 的子序列(保序);輸入物件不被 mutate。
i. **重複 tag**:`sidecar.tags` 內重複值經 `set()` 去重不影響結果。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以 dict 模擬 sidecar)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_tagging.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import tagging`)。

**常數契約**
- **AC1**：`tagging.BUILTIN_TAGS == ["Need Review","Need Discuss","Potential Miss","False Alarm","True Defect","Reflection","Low Confidence","New Pattern","Golden Case","Need Labeling","Need Retrain"]`,且 `len(tagging.BUILTIN_TAGS) == 11`。
- **AC2**：`tagging.VERDICTS == ["unset","true_defect","false_alarm","reflection"]`,且 `tagging.VERDICTS[0] == "unset"`。

**is_reviewed**
- **AC3**：`is_reviewed({"verdict":"unset","review_status":"none"}) == False`。
- **AC4**：`is_reviewed({"verdict":"true_defect","review_status":"none"}) == True`(verdict 非 unset)。
- **AC5**：`is_reviewed({"verdict":"unset","review_status":"done"}) == True`(review_status==done)。
- **AC6**：`is_reviewed({}) == False`(全缺鍵 → unset/none)。
- **AC7**：`is_reviewed({"verdict":"false_alarm"}) == True` 且 `is_reviewed({"review_status":"done"}) == True`(任一條件成立即 True)。

**matches — 空 / 預設**
- **AC8**：`matches({}, {}) == True`(空 sidecar、空 query)。
- **AC9**：`matches({"comment":"x"}, {}) == True`(空 query 一律通過)。

**matches — tags(any / all / 空)**
- **AC10**:`matches({"tags":["True Defect","Need Review"]}, {"tags":["Need Review"]}) == True`(預設 any,含其一)。
- **AC11**:`matches({"tags":["True Defect"]}, {"tags":["Need Review","Need Retrain"]}) == False`(any 但無交集)。
- **AC12**:`matches({"tags":["True Defect","Need Review"]}, {"tags":["True Defect","Need Review"],"mode":"all"}) == True`(all 全含)。
- **AC13**:`matches({"tags":["True Defect"]}, {"tags":["True Defect","Need Review"],"mode":"all"}) == False`(all 缺一)。
- **AC14**:`matches({"tags":["True Defect"]}, {"tags":[]}) == True` 且 `matches({"tags":[]}, {"tags":[],"mode":"all"}) == True`(空 tags 條件視為不參與)。
- **AC15**:`matches({}, {"tags":["Need Review"]}) == False`(sidecar 無 tags 視同 `[]`,any 無交集)。

**matches — verdict / review_status**
- **AC16**:`matches({"verdict":"false_alarm"}, {"verdict":"false_alarm"}) == True` 且 `matches({"verdict":"true_defect"}, {"verdict":"false_alarm"}) == False`。
- **AC17**:`matches({}, {"verdict":"unset"}) == True`(缺鍵視同 `"unset"`,精確相等)。
- **AC18**:`matches({"review_status":"done"}, {"review_status":"done"}) == True` 且 `matches({"review_status":"none"}, {"review_status":"done"}) == False`。

**matches — reviewed(bool,可查未審)**
- **AC19**:`matches({"verdict":"true_defect"}, {"reviewed":True}) == True`。
- **AC20**:`matches({"verdict":"unset","review_status":"none"}, {"reviewed":False}) == True`(查未審命中)。
- **AC21**:`matches({"verdict":"true_defect"}, {"reviewed":False}) == False`(已審但要求未審)。

**matches — bookmarked**
- **AC22**:`matches({"bookmarked":True}, {"bookmarked":True}) == True` 且 `matches({}, {"bookmarked":True}) == False`(缺鍵視同 False)。
- **AC23**:`matches({"bookmarked":False}, {"bookmarked":False}) == True`。

**matches — text(大小寫不敏感子字串)**
- **AC24**:`matches({"comment":"Scratch on edge"}, {"text":"scratch"}) == True`(大小寫不敏感)。
- **AC25**:`matches({"comment":"Scratch on edge"}, {"text":"dent"}) == False`(無此子字串)。
- **AC26**:`matches({"comment":"anything"}, {"text":""}) == True` 且 `matches({}, {"text":"x"}) == False`(空 text 通過;缺 comment 視同 `""`)。

**matches — 多條件 AND**
- **AC27**:`matches({"tags":["True Defect"],"verdict":"true_defect","bookmarked":True}, {"tags":["True Defect"],"verdict":"true_defect","bookmarked":True}) == True`(三條件全中)。
- **AC28**:`matches({"tags":["True Defect"],"verdict":"false_alarm","bookmarked":True}, {"tags":["True Defect"],"verdict":"true_defect","bookmarked":True}) == False`(verdict 不符 → AND 失敗)。

**filter_records — 保序 / 子集 / 不 mutate**
- **AC29**:對 `items = [("a",{"tags":["True Defect"]}), ("b",{"tags":["False Alarm"]}), ("c",{"tags":["True Defect","Need Review"]})]`,`filter_records(items, {"tags":["True Defect"]}) == ["a","c"]`(僅回 record、保序)。
- **AC30**:`filter_records(items, {}) == ["a","b","c"]`(空 query 全回、原順序)。
- **AC31**:`filter_records([], {"tags":["True Defect"]}) == []`(空輸入 → 空輸出)。
- **AC32**:呼叫 `filter_records(items, {"text":"x"})` 後,原 `items` 物件與其中各 sidecar dict 內容不變(不被 mutate;以呼叫前後 deepcopy 相等驗證),且回傳值長度 `<= len(items)`。
- **AC33**:`filter_records([("r",{"verdict":"true_defect","review_status":"none"})], {"reviewed":True}) == ["r"]`(filter 與 matches 語義一致,reviewed 條件貫穿)。

**邊界 / 不拋例外**
- **AC34**:`matches({}, {"tags":["Need Review"],"verdict":"unset","review_status":"none","reviewed":False,"bookmarked":False,"text":""})` 在全缺鍵 sidecar 上**不拋例外**且回 `False`(tags any 無交集致 AND 失敗),證明缺鍵以預設視同值處理而非 `KeyError`。
- **AC35**:`matches({"tags":["Custom Tag X"]}, {"tags":["Custom Tag X"]}) == True`(允許非 BUILTIN 自訂標籤參與比對,不校驗)。

---

## 6. 與其他模組的邊界(防越權)
- **不負責**持久化(那是 `sidecar` 模組:讀寫 `<name>.json`、不改原圖)。
- **不負責**跨集合的排序與 Review Queue 排程(那是 M3 `filtersort`,將 import 並複用本模組的 `matches`/`filter_records` 作為 predicate)。
- **不負責**校驗/寫入合法 verdict 或 tag(寫入時的合法性由 `sidecar`/app 層把關;本模組只讀、只比對)。
- 本模組對外承諾:純函式、無副作用、輸入不被 mutate、僅依賴 Python 標準庫(實際上零 import 即可實作)。
