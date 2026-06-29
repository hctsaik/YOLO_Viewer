# 設計:`casepkg`(M3 / Tier B — 匯出序列化 + 薄檔案寫入,需真實讀寫驗收)

> `/architect` 產物(module 粒度)。對應 `ROADMAP.md` 第 38 行 M3 `casepkg`、第 40-43 行跨模組 `Detection` 契約。
> 上游資料形狀:`sidecar`(`3_Architect_Design/06`)的 sidecar dict、PO 釘死的 `Detection` 形狀。
> 本檔只定義契約與驗收,**不含任何實作**。實作由 `/pg` 寫進 `5_PG_Develop/casepkg.py`。
> 風格延續既有 `app.py` 第 193-212「簡易匯出 Review List」(同欄位精神,本模組是更完整、可被 pytest 釘死的版本)。

## 模組邊界 sanity check(開工前一句)

`casepkg` 內聚一句話可講完:「把一批已選案例(record 摘要 + sidecar 判讀 dict + model `Detection` 清單)
扁平化成一張 CSV 表 + 一份可巢狀的 JSON case list,並寫出兩個檔」。
它**只消費 dict**(`item["sidecar"]`、`item["detections"]`),**不 import** `sidecar`/`yolo`/`tagging` 任一實作 —— 完全靠資料形狀解耦,故可獨立設計、可用 `tmp_path` 真實 round-trip 驗收。
不需與 `filtersort`(排序/Queue)合併(那是「選哪些、什麼順序」;本模組是「選定後怎麼輸出」);亦無須再拆(序列化與薄寫入內聚同一責任)。**結論:範圍 OK,不退回 `/po`。**

---

## 1. 目的 (Purpose)

把一組「選定案例」序列化成兩種人類/機器可讀格式:一張**每案一列**的扁平 CSV(快速總覽 / Excel),與一份保留巢狀 `detections` 的 **JSON case list**(完整結構),並把兩者寫進指定輸出目錄,供匯出 Review Package。**只讀傳入的 dict、只寫輸出目錄,絕不讀寫原始影像或 sidecar 檔。**

---

## 2. 相依與限制

- 僅用 Python 標準庫:`csv`、`json`、`io`、`os`(或 `pathlib`)。**不可新增任何 pip 依賴。**
- 模組層級**零 GUI、零 Streamlit、零網路**;**嚴禁 `import sidecar` / `import yolo` / `import tagging`**(只吃 dict)。
- 進入點檔名:`5_PG_Develop/casepkg.py`(測試 `import casepkg`,conftest 已把 `5_PG_Develop` 置於 `sys.path`)。
- 純函式 `build_rows` / `to_csv` / `to_json` / `build_case_list` 無副作用、不就地改輸入;唯一有 I/O 者為 `write_package`。

---

## 3. I/O 契約(逐字採用,簽名為硬契約,/pm 直接鎖)

```python
def build_rows(items: list[dict]) -> list[dict]
# 每個 item → 一個扁平 row dict;欄位順序見 §3.2(以 OrderedDict/dict 保序)

def to_csv(rows: list[dict]) -> str
# rows(build_rows 的輸出)→ CSV 字串;表頭順序見 §3.2;行尾 \r\n;見 §3.3

def build_case_list(items: list[dict]) -> list[dict]
# 每個 item → 一個巢狀 case dict(保留 detections 結構);見 §3.4

def to_json(items: list[dict]) -> str
# == json.dumps(build_case_list(items), ensure_ascii=False, indent=2);round-trip 可還原(見 §3.4)

def write_package(out_dir, items: list[dict]) -> dict
# 在 out_dir 寫 case_list.csv + case_list.json;回 {"csv": <csv絕對或結合路徑>, "json": <json路徑>}
# csv 內容 == to_csv(build_rows(items));json 內容 == to_json(items)
# out_dir 不存在則建立(os.makedirs(out_dir, exist_ok=True));回傳路徑用 os.path.join(out_dir, ...)
```

### 3.1 輸入 `item` 形狀(契約,釘死)

```python
item = {
    "name":       str,              # 顯示名(通常影像檔名);缺 → ""
    "path":       str,              # 影像路徑;缺 → ""
    "sidecar":    dict,             # 一份 sidecar dict(形狀同 sidecar 模組 default());缺 → {}
    "detections": list[Detection],  # model 結果;缺 → []
}
```

`sidecar` dict 本模組**只讀**下列鍵(其餘鍵忽略),缺鍵一律套「預設視同值」:

| sidecar 鍵 | 型別 | 缺鍵預設(視同值) | 對應 row 欄位 |
|------------|------|--------------------|----------------|
| `review_status` | `str` | `"none"` | `status` |
| `verdict` | `str` | `"unset"` | `verdict` |
| `tags` | `list[str]` | `[]` | `tags`(以 `;` 串接) |
| `bookmarked` | `bool` | `False` | `bookmarked` |
| `rois` | `list` | `[]` | `n_rois`(取 `len`) |
| `comment` | `str` | `""` | `comment` |

> 註:`verdict` 缺鍵預設定為 `"unset"`(延續既有 `app.py` 第 201 行 `s.get("verdict","unset")` 與 `tagging.VERDICTS[0]`);非 sidecar 模組 `default()` 的 `""`。本模組對外承諾即此 `"unset"`。

### 3.1.1 `Detection` 形狀(PO 跨模組釘死,本模組只消費)

```python
Detection = {"bbox": [x, y, w, h], "cls": str, "conf": float}   # conf ∈ [0,1]
```

本模組只讀 `det["cls"]` 與 `det["conf"]`(算 `n_det`/`max_conf`/`classes`),**不讀/不驗證 `bbox`**(bbox 僅原樣帶進 JSON case list)。

### 3.2 CSV / row 欄位順序(**釘死,不得增刪改序**)

共 **11 欄**,順序固定:

```
name, path, status, verdict, tags, bookmarked, n_rois, n_det, max_conf, classes, comment
```

每欄的值規則(釘死):

| # | 欄位 | 來源 / 計算 | 型別(row dict 內) | 缺漏 / 空時的值 |
|---|------|-------------|--------------------|------------------|
| 1 | `name` | `item.get("name","")` | `str` | `""` |
| 2 | `path` | `item.get("path","")` | `str` | `""` |
| 3 | `status` | `sidecar.get("review_status","none")` | `str` | `"none"` |
| 4 | `verdict` | `sidecar.get("verdict","unset")` | `str` | `"unset"` |
| 5 | `tags` | `";".join(sidecar.get("tags",[]))` | `str` | `""`(空清單 → 空字串) |
| 6 | `bookmarked` | `bool(sidecar.get("bookmarked",False))` | `bool` | `False` |
| 7 | `n_rois` | `len(sidecar.get("rois",[]))` | `int` | `0` |
| 8 | `n_det` | `len(item.get("detections",[]))` | `int` | `0` |
| 9 | `max_conf` | 見下「max_conf 規則」 | `float` | `0.0`(無 detection) |
| 10 | `classes` | 見下「classes 規則」 | `str` | `""`(無 detection) |
| 11 | `comment` | `sidecar.get("comment","")` | `str` | `""` |

- **max_conf 規則**:`detections` 為空 → `0.0`(float);否則 `= max(float(d["conf"]) for d in detections)`,回傳 `float`(不四捨五入)。
- **classes 規則**:`detections` 為空 → `""`;否則取每個 `d["cls"]` 字串,**去重、保留首見順序**,以 `","` 串接(逗號、無空白)。例:`cls` 序列 `["scratch","dent","scratch"]` → `"scratch,dent"`。

> `build_rows` 回傳的每個 row 是「鍵順序 == §3.2 欄位順序」的 dict(Python 3.7+ dict 保序即契約;`to_csv` 表頭由此順序產生)。

### 3.3 CSV 字串格式(**釘死**)

- 用標準庫 `csv.DictWriter`,`fieldnames` = §3.2 的 11 欄順序。
- **第一列為表頭**(即上述 11 欄名,逗號分隔)。
- **行尾終止符 = `\r\n`**(`csv` 模組預設 `lineterminator="\r\n"`;契約即此,測試以 `\r\n` 斷言)。
- 逸出策略 = `csv.QUOTE_MINIMAL`(預設):值含逗號 `,`、雙引號 `"`、或換行時才加雙引號並把內部 `"` 重複成 `""`;否則不加引號。
- `bookmarked` 布林寫成 Python `str(bool)` → `"True"` / `"False"`(`csv` 對非字串呼叫 `str()`);`n_rois`/`n_det` 寫成整數字串(如 `"2"`);`max_conf` 寫成 `str(float)`(如 `"0.9"`、`"0.0"`)。
- `rows == []`(空)時,`to_csv` 仍輸出**僅表頭一行**(含結尾 `\r\n`):`"name,path,status,verdict,tags,bookmarked,n_rois,n_det,max_conf,classes,comment\r\n"`。

### 3.4 JSON case list 形狀(**釘死,round-trip**)

`build_case_list(items)` 對每個 item 產一個 case dict,鍵順序釘死:

```python
case = {
    "name":       item.get("name",""),
    "path":       item.get("path",""),
    "review": {                                  # 扁平化前的人工判讀(巢狀子物件)
        "status":     sidecar.get("review_status","none"),
        "verdict":    sidecar.get("verdict","unset"),
        "tags":       list(sidecar.get("tags",[])),    # 複製,保序,不去重
        "bookmarked": bool(sidecar.get("bookmarked",False)),
        "comment":    sidecar.get("comment",""),
        "n_rois":     len(sidecar.get("rois",[])),
    },
    "detections": [                              # 保留巢狀;每筆原樣帶 bbox/cls/conf
        {"bbox": list(d["bbox"]), "cls": d["cls"], "conf": float(d["conf"])}
        for d in item.get("detections",[])
    ],
    "summary": {
        "n_det":    len(item.get("detections",[])),
        "max_conf": <§3.2 max_conf 規則>,
        "classes":  [ <去重保序的 cls 清單,list[str]> ],   # 同 §3.2 classes,但回 list 非字串
    },
}
```

- `to_json(items) == json.dumps(build_case_list(items), ensure_ascii=False, indent=2)`。
- **round-trip 契約**:`json.loads(to_json(items)) == build_case_list(items)`(經 JSON 編解碼後結構與值完全相等;故 `detections[i]["bbox"]` 還原為 list、`conf` 為 float)。
- 不就地改輸入:`bbox`、`tags` 皆以 `list(...)` 複製;`build_case_list`/`build_rows`/`to_json` 呼叫後原 `items` 物件與其中 sidecar/detections 不被 mutate。

### 3.5 `write_package` 行為(**Tier B,真實寫入**)

```
write_package(out_dir, items):
  os.makedirs(out_dir, exist_ok=True)
  csv_path  = os.path.join(out_dir, "case_list.csv")
  json_path = os.path.join(out_dir, "case_list.json")
  寫 csv_path  ← to_csv(build_rows(items))      # UTF-8;newline="" 開檔(避免 csv 雙重換行)
  寫 json_path ← to_json(items)                  # UTF-8
  return {"csv": csv_path, "json": json_path}
```

- 檔案以 UTF-8 寫入(non-ASCII 如中文 tag/comment 無損)。
- CSV 開檔須用 `open(..., "w", newline="", encoding="utf-8")`,使磁碟上的行尾恰為 §3.3 的 `\r\n`(不被平台再轉換)。
- **覆寫語義**:同 `out_dir` 重複呼叫,後者完全覆寫前者內容(非附加)。
- 回傳 dict 的鍵固定為 `{"csv", "json"}`,值為 `os.path.join(out_dir, ...)` 的路徑字串。

---

## 4. 資料流 (Data Flow)

```
items: list[item]
  │  (每 item: name/path/sidecar(dict)/detections(list[Detection]))
  ├─ build_rows ─────────► list[row]  (11 欄扁平,保序) ──► to_csv ──► CSV str (\r\n)
  ├─ build_case_list ────► list[case] (巢狀 review/detections/summary) ──► to_json ──► JSON str
  └─ write_package(out_dir, items)
         ├─ to_csv(build_rows(items))  ──► <out_dir>/case_list.csv   (UTF-8, newline="")
         └─ to_json(items)             ──► <out_dir>/case_list.json  (UTF-8)
         回 {"csv": ..., "json": ...}
```

- 所有彙整(`n_det`/`max_conf`/`classes`)在 `build_rows`/`build_case_list` 內部一次算出;`to_csv`/`to_json` 只做格式化,不再讀 sidecar/detection 原鍵。
- `to_csv` 吃的是 `build_rows` 的輸出(row dict),**不是** `items`;`to_json`/`write_package` 吃的是原始 `items`。

---

## 5. 邊界條件與錯誤處理

| 情境 | 行為(契約) |
|------|------|
| `items == []`(空) | `build_rows([]) == []`;`to_csv([]) ==` 僅表頭行(見 §3.3);`build_case_list([]) == []`;`to_json([]) == "[]"`;`write_package(d, [])` 仍寫出「只有表頭的 CSV」與「`[]` 的 JSON」兩檔並回路徑 |
| item 缺 `sidecar` 鍵 | 視同 `{}`,各欄套 §3.1/§3.2 預設視同值,不丟 `KeyError` |
| item 缺 `detections` 鍵 | 視同 `[]`:`n_det=0`、`max_conf=0.0`、`classes=""`(CSV)/`[]`(JSON) |
| item 缺 `name`/`path` | 視同 `""` |
| `sidecar.tags` 含 non-ASCII / 自訂字串 | 原樣 `;`(CSV)/原樣 list(JSON)輸出,不校驗、不去重(CSV 的 tags 不去重,保 sidecar 原序) |
| `tags`/`comment` 值含逗號或引號 | 由 `csv.QUOTE_MINIMAL` 自動加引號/逸出(見 §3.3),JSON 端由 `json` 自動逸出 |
| `detections` 多筆同 `cls` | `classes` 去重保序(首見);`n_det` 仍計全部筆數(不去重) |
| `conf` 為 int(如 `1`) | `max_conf` 以 `float(...)` 正規化為 `1.0` |
| `out_dir` 不存在 | `write_package` 先 `os.makedirs(out_dir, exist_ok=True)` 再寫;不丟錯 |
| 輸入 `items` mutate | 禁止;`bbox`/`tags` 以 `list(...)` 複製,純函式不改原物件 |
| `bbox` 內容 | 原樣 `list(d["bbox"])` 帶進 JSON,本模組不驗長度/型別/數值範圍(那是 yolo/overlay 的事) |

---

## 6. Acceptance Criteria(給 `/pm` 落成 pytest;每條帶具體期望值、可驗)

> 測試置於 `4_PM_Feedback/test_casepkg.py`(`write_package` 用 `tmp_path` 真實寫讀);`import casepkg`。
> 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_casepkg.py -p no:cacheprovider --strict-markers -q`
>
> 共用測試夾具(下列 AC 引用 `IT1`/`IT2`):
> ```python
> IT1 = {"name":"a.png", "path":"/img/a.png",
>        "sidecar":{"review_status":"done","verdict":"true_defect","tags":["True Defect","Need Review"],
>                   "bookmarked":True,"rois":[{"bbox":[1,2,3,4]}],"comment":"刮傷,邊緣"},
>        "detections":[{"bbox":[10,20,30,40],"cls":"scratch","conf":0.9},
>                      {"bbox":[50,60,10,10],"cls":"dent","conf":0.5},
>                      {"bbox":[0,0,5,5],"cls":"scratch","conf":0.7}]}
> IT2 = {"name":"b.png", "path":"/img/b.png", "sidecar":{}, "detections":[]}   # 全缺鍵
> ```

### A. 欄位順序與常數(契約)
- **AC1**:`casepkg.build_rows([])  == []`(空輸入 → 空列)。
- **AC2**:`list(casepkg.build_rows([IT1])[0].keys()) == ["name","path","status","verdict","tags","bookmarked","n_rois","n_det","max_conf","classes","comment"]`(row 鍵順序 == §3.2,剛好 11 欄)。

### B. build_rows 逐欄值(釘死)
- **AC3(完整 item)**:`casepkg.build_rows([IT1])[0] == {"name":"a.png","path":"/img/a.png","status":"done","verdict":"true_defect","tags":"True Defect;Need Review","bookmarked":True,"n_rois":1,"n_det":3,"max_conf":0.9,"classes":"scratch,dent","comment":"刮傷,邊緣"}`(tags 以 `;` 串接、classes 去重保序以 `,` 串接、max_conf=最大 conf、n_rois/n_det 為計數)。
- **AC4(全缺鍵 item)**:`casepkg.build_rows([IT2])[0] == {"name":"b.png","path":"/img/b.png","status":"none","verdict":"unset","tags":"","bookmarked":False,"n_rois":0,"n_det":0,"max_conf":0.0,"classes":"","comment":""}`(每欄取 §3.2 缺漏預設值)。
- **AC5(max_conf 型別與值)**:`r = casepkg.build_rows([IT1])[0]`;`r["max_conf"] == 0.9 and isinstance(r["max_conf"], float)`;且 `casepkg.build_rows([IT2])[0]["max_conf"] == 0.0`(無 detection → `0.0` float)。
- **AC6(classes 去重保序)**:`casepkg.build_rows([IT1])[0]["classes"] == "scratch,dent"`(首見 scratch、再 dent,第三筆 scratch 不重複出現)。
- **AC7(多 item 保序)**:`rows = casepkg.build_rows([IT1, IT2])`;`len(rows)==2 and rows[0]["name"]=="a.png" and rows[1]["name"]=="b.png"`。
- **AC8(不 mutate 輸入)**:呼叫 `casepkg.build_rows([IT1])` 後,`IT1["sidecar"]["tags"] == ["True Defect","Need Review"]` 且 `IT1["detections"]` 長度仍為 3(輸入未被改;以呼叫前後 `copy.deepcopy` 相等驗證)。

### C. to_csv(表頭 / 行尾 / 逸出,釘死)
- **AC9(空 rows 仍出表頭)**:`casepkg.to_csv([]) == "name,path,status,verdict,tags,bookmarked,n_rois,n_det,max_conf,classes,comment\r\n"`(僅表頭一行、`\r\n` 結尾)。
- **AC10(表頭精確)**:`casepkg.to_csv(casepkg.build_rows([IT1])).split("\r\n")[0] == "name,path,status,verdict,tags,bookmarked,n_rois,n_det,max_conf,classes,comment"`。
- **AC11(資料列精確,含逗號逸出)**:
  ```python
  csv_str = casepkg.to_csv(casepkg.build_rows([IT1]))
  lines = csv_str.split("\r\n")
  # lines[0]=表頭, lines[1]=資料列, lines[2]="" (末尾 \r\n 後的空段)
  assert lines[1] == 'a.png,/img/a.png,done,true_defect,True Defect;Need Review,True,1,3,0.9,"scratch,dent","刮傷,邊緣"'
  assert lines[2] == ""
  ```
  (`tags` 用 `;` 不需逸出;`classes`=`scratch,dent` 與 `comment`=`刮傷,邊緣` 含逗號 → 由 QUOTE_MINIMAL 加雙引號;布林寫 `True`、整數寫 `1`/`3`、float 寫 `0.9`。)
- **AC12(行尾為 CRLF)**:`casepkg.to_csv(casepkg.build_rows([IT1])).endswith("\r\n") and casepkg.to_csv(casepkg.build_rows([IT1])).count("\r\n") == 2`(表頭 + 一筆資料,共兩個 `\r\n`)。
- **AC13(全缺鍵列)**:`casepkg.to_csv(casepkg.build_rows([IT2])).split("\r\n")[1] == "b.png,/img/b.png,none,unset,,False,0,0,0.0,,"`(空 tags/classes/comment → 連續逗號;max_conf=`0.0`)。

### D. build_case_list / to_json(巢狀 + round-trip,釘死)
- **AC14(case 結構與鍵順序)**:`cl = casepkg.build_case_list([IT1])`;`list(cl[0].keys()) == ["name","path","review","detections","summary"]`,且 `list(cl[0]["review"].keys()) == ["status","verdict","tags","bookmarked","comment","n_rois"]`,`list(cl[0]["summary"].keys()) == ["n_det","max_conf","classes"]`。
- **AC15(review 子物件值)**:`cl = casepkg.build_case_list([IT1])`;`cl[0]["review"] == {"status":"done","verdict":"true_defect","tags":["True Defect","Need Review"],"bookmarked":True,"comment":"刮傷,邊緣","n_rois":1}`(tags 為 list、不去重保序)。
- **AC16(detections 巢狀原樣)**:`cl = casepkg.build_case_list([IT1])`;`cl[0]["detections"] == [{"bbox":[10,20,30,40],"cls":"scratch","conf":0.9},{"bbox":[50,60,10,10],"cls":"dent","conf":0.5},{"bbox":[0,0,5,5],"cls":"scratch","conf":0.7}]`(三筆原序、bbox 為 list、conf 為 float)。
- **AC17(summary)**:`cl = casepkg.build_case_list([IT1])`;`cl[0]["summary"] == {"n_det":3,"max_conf":0.9,"classes":["scratch","dent"]}`(classes 為去重保序 list)。
- **AC18(全缺鍵 case)**:`cl = casepkg.build_case_list([IT2])`;`cl[0] == {"name":"b.png","path":"/img/b.png","review":{"status":"none","verdict":"unset","tags":[],"bookmarked":False,"comment":"","n_rois":0},"detections":[],"summary":{"n_det":0,"max_conf":0.0,"classes":[]}}`。
- **AC19(空 items)**:`casepkg.build_case_list([]) == []` 且 `casepkg.to_json([]) == "[]"`。
- **AC20(to_json == dumps(build_case_list))**:`casepkg.to_json([IT1]) == json.dumps(casepkg.build_case_list([IT1]), ensure_ascii=False, indent=2)`。
- **AC21(round-trip 結構正確)**:`json.loads(casepkg.to_json([IT1, IT2])) == casepkg.build_case_list([IT1, IT2])`(經 JSON 編解碼後逐欄相等;`detections`/`bbox`/`conf`/`tags` 結構與型別還原一致)。
- **AC22(non-ASCII 無損)**:`json.loads(casepkg.to_json([IT1]))[0]["review"]["comment"] == "刮傷,邊緣"`(中文 + 逗號 round-trip 不變;`ensure_ascii=False`)。
- **AC23(不 mutate 輸入)**:呼叫 `casepkg.to_json([IT1])` 後,`IT1` 以 `copy.deepcopy` 比對前後相等(`bbox`/`tags` 以 `list(...)` 複製,未動到原物件)。

### E. write_package(Tier B,tmp_path 真實寫讀,逐欄斷言)
- **AC24(回傳路徑)**:`out = casepkg.write_package(str(tmp_path / "pkg"), [IT1, IT2])`;`set(out.keys()) == {"csv","json"}`,`out["csv"] == os.path.join(str(tmp_path / "pkg"), "case_list.csv")`,`out["json"] == os.path.join(str(tmp_path / "pkg"), "case_list.json")`,且兩檔 `os.path.exists(...) is True`。
- **AC25(out_dir 自動建立)**:對一個尚不存在的子目錄 `tmp_path / "nope" / "deep"` 呼叫 `write_package` 不丟錯,且事後該目錄與兩檔皆存在。
- **AC26(CSV 內容 == to_csv∘build_rows,讀回逐位元相等)**:
  ```python
  out = casepkg.write_package(str(tmp_path / "pkg"), [IT1, IT2])
  with open(out["csv"], "r", encoding="utf-8", newline="") as f:
      disk = f.read()
  assert disk == casepkg.to_csv(casepkg.build_rows([IT1, IT2]))   # 含 \r\n,無平台雙轉換
  ```
- **AC27(CSV 讀回逐欄,用 csv 解析)**:用 `csv.DictReader(open(out["csv"], encoding="utf-8", newline=""))` 解析:`rows[0]["name"]=="a.png"`、`rows[0]["classes"]=="scratch,dent"`、`rows[0]["comment"]=="刮傷,邊緣"`、`rows[0]["bookmarked"]=="True"`、`rows[0]["n_det"]=="3"`、`rows[0]["max_conf"]=="0.9"`,且 `rows[1]["name"]=="b.png"`、`rows[1]["tags"]==""`、`rows[1]["max_conf"]=="0.0"`(注意 DictReader 回字串)。
- **AC28(JSON 內容 == to_json,讀回 round-trip)**:
  ```python
  out = casepkg.write_package(str(tmp_path / "pkg"), [IT1, IT2])
  with open(out["json"], "r", encoding="utf-8") as f:
      disk = f.read()
  assert disk == casepkg.to_json([IT1, IT2])
  assert json.load(open(out["json"], encoding="utf-8")) == casepkg.build_case_list([IT1, IT2])
  ```
- **AC29(空 items 仍寫兩檔)**:`out = casepkg.write_package(str(tmp_path / "empty"), [])`;讀回 `out["csv"]` == 僅表頭行(`"name,...,comment\r\n"`),讀回 `out["json"]` 經 `json.load` == `[]`,兩檔皆存在。
- **AC30(覆寫語義)**:對同一 `out_dir` 先 `write_package(d, [IT1, IT2])` 再 `write_package(d, [IT2])`,之後 `csv.DictReader` 讀 `case_list.csv` 只得 1 筆資料列(`name=="b.png"`),`json.load(case_list.json)` 長度為 1(後者完全覆寫前者,非附加)。

---

## 7. 與其他模組的邊界(防越權)

- **不負責**「選哪些案例、什麼順序」(那是 `filtersort` / app:本模組吃已選定的 `items`,原序輸出)。
- **不負責**讀寫 sidecar 檔或產生 `Detection`(`sidecar`/`yolo` 的事:本模組**只吃 dict**,不 import 任一實作)。
- **不負責**校驗 `verdict`/`tag`/`bbox` 合法性或 `conf` 範圍(上游把關;本模組原樣帶或做純彙整,唯 `conf` 以 `float()` 正規化)。
- **不負責**輸出 ROI crop 影像、HTML/PDF/資料夾打包(Phase 2 候選);本輪只出 `case_list.csv` + `case_list.json`。
- 本模組對外承諾:除 `write_package` 外皆純函式、無副作用、輸入不被 mutate、僅依賴 Python 標準庫;欄位順序(§3.2)、CSV 格式(§3.3)、JSON case 形狀(§3.4)為對下游(app 匯出 UI)鎖定的契約。
