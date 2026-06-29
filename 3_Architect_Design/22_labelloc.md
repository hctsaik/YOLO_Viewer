# 設計:`labelloc`(Tier B — 有檔案系統 I/O,但無 GUI、無跨模組契約;可純單元判綠)

> `/architect` 產物。對應 User 需求(`1_user_needs/`):「我想要選一個 YOLO 資料夾,然後這個資料夾裡面,他自己會判斷是 labels 在子資料夾 或是和影像同一個資料夾」。
> 本檔只定義**契約與驗收標準**,**不含實作**。實作由 `/pg` 寫到 `5_PG_Develop/labelloc.py`;驗收測試由 `/pm` 寫到 `4_PM_Feedback/test_labelloc.py`(同名對齊 skip connection)。
> 檔號 `22`(接續現有最高 `20_viewer_workbench_redesign.md`;`21` 留空無妨,以本檔為準)。

---

## 邊界 sanity check(開工前一句話)

`labelloc` 內聚一句話講得完:**給定一個 YOLO 資料夾,自動判斷該批影像的偵測標註檔(`<stem>.json`)放在 `<folder>/labels/` 子資料夾、還是和影像同一層 `<folder>/`,回傳「該去哪讀標註」的目錄絕對路徑。**

它只耦合「檔案系統(`os.path.isdir`/`listdir`/`abspath`)」與「既有命名慣例 `<stem>.json`(與 `app._pred_path`、`yolo.load` 對齊)」,**不 import 任何本專案模組**(只吃 `folder` 字串 + 影像 `stem` 清單,回字串/`None`),與消費端(`app.py` sidebar)以**字串介面**解耦。可用 `tmp_path` 自造目錄結構獨立 round-trip 驗收。

→ **可獨立設計與驗收,不需合併或再拆。** 放行本輪設計。

### 關鍵事實校正(給 `/pm` 與 `/pg`,避免接不上鏈)

- 本專案標註檔是 **`<stem>.json`**(`yolo.load` 讀 JSON、`app._pred_path` 組 `.json`),**不是**經典 YOLO 的 `<stem>.txt`。`ext` 預設**必須**為 `'.json'`,否則整條鏈接不上。
- `.txt` 支援**不入本輪契約**(YAGNI);保留 `ext` 參數是為未來,但本輪 AC 只驗 `'.json'`。若 User 之後要 `.txt`,**回退 `/po`** 開規格(在 ROADMAP 決策日誌記一行)。

---

## 1. 目的 (Purpose)

把「選一個資料夾」這件事的**標註位置判定**收斂成單一可解釋規則:

- 若 `<folder>/labels/` **存在且被證實含這批圖的對應標註**(至少 1 個 `<stem>.json`)→ 採子資料夾。
- 否則(`labels/` 不存在 / 存在但空 / 存在但沒有任何對應 stem 的 `.json`)→ 退化為**同層** `<folder>/`。
- `folder` 不存在 / 不是資料夾 → 回 `None`(呼叫端沿用既有「找不到資料夾」錯誤路徑)。

**容錯第一**:純讀檔(`os.path.isdir`/`listdir`),不建檔、不寫檔、不解析 JSON 內容、**絕不拋例外**(`OSError` 一律吞成 fallback 同層)。

---

## 2. I/O 契約 (I/O Contract)

實作於 `5_PG_Develop/labelloc.py`。測試以 `import labelloc` 取用(conftest 已把 `5_PG_Develop` 加進 `sys.path`)。
**逐字採用**以下簽名,不得增刪參數或改名(改名 = 破壞 skip connection 與 PM 測試):

```python
def resolve_label_dir(folder, stems=None, *, ext=".json", subdir="labels") -> str | None:
    """主入口(資料夾層級判定)。給定 YOLO 資料夾 folder,回傳「該去哪讀偵測標註檔」的目錄『絕對路徑』。
    - 規則見 §3 precedence。
    - stems: 可迭代的影像 stem(取自 imageset record 的 Path(name).stem);用來「證實」子夾確實裝這批圖的標註。
      stems=None → 退化規則(labels/ 含任一 *<ext> 即採子夾);stems=[](空清單)→ 視同「無對應檔」→ 不採子夾。
    - folder 不存在 / 不是資料夾 → None。
    - 純讀檔,不建檔、不拋例外(OSError 吞成 fallback 同層)。回傳一律 os.path.abspath 正規化。"""
    ...

def label_path(label_dir, image_path, *, ext=".json") -> str:
    """per-image 路徑解析(純字串,不碰檔案系統、不檢存在、不拋例外)。
    回 os.path.join(label_dir, Path(image_path).stem + ext)。
    語義對齊現行 app._pred_path(label_dir, image_path),以便直接替換。存在性與壞檔交給 yolo.load 容錯。"""
    ...

def has_labels(label_dir, stems, *, ext=".json") -> bool:
    """(helper,可對外)label_dir 內是否含 ≥1 個對應的 <stem><ext>。
    - stems 非空 → 取「label_dir 內 .json 的 stem 集合」與「stems 集合」的交集是否非空。
    - stems 為 None 或空 → 是否含任一 *<ext>(退化規則,見 resolve_label_dir 的 stems=None 路徑)。
      (註:resolve_label_dir 對 stems=[] 走「不採子夾」;has_labels 對空清單的語義由 resolve 決定,見 §3/§4。)
    - 以單次 os.listdir + set 比對(O(n),不逐 stem isfile,省 syscall)。
    - label_dir 不存在 / 不可讀(OSError)→ False,不拋例外。"""
    ...
```

> `resolve_label_dir` 是對外主入口(folder 層級決策,`app.py` 用它決定 `pred_folder`)。
> `label_path` 等價於現行 `app._pred_path`,提供出來是為了**語義對齊與防 regression**(AC 釘死它與 `_pred_path` 同結果);但整合時 `app.py` 甚至可不 import 它(`_pred_path` 不改,只餵入解析後的 `pred_folder`,見 §6)。
> `has_labels` 是 `resolve_label_dir` 的判定核心,抽出對外是為了讓 PM 能單獨釘死「子夾被證實」邏輯。

### 2.1 大小寫 / 跨平台正規化(硬約束,給 `/pg`)

Windows 檔名不分大小寫但 `os.listdir` 回**原樣**;Linux 分大小寫。為了跨平台一致:

- **子夾名比對**:`subdir`(預設 `"labels"`)與 `os.listdir(folder)` 的項目,以 `os.path.normcase` normalize 後比對(精神同 `imageset._norm_folder`)。命中後**用磁碟上的真實名**組路徑(例:實體是 `Labels/` 時回 `<folder>/Labels` 的 abspath,而非寫死 `labels`)。
- **stem 比對**:`stems` 與「`label_dir` 內檔案的 stem」皆以 `os.path.normcase` normalize 後比交集(避免 `IMG1.json` vs `img1` 在 Linux 漏配、在 Windows 又重複)。
- **`ext` 比對**:亦以 `normcase` 比(`'.JSON'` 視同 `'.json'`)。
- 僅做**比對**用 normcase;回傳路徑用**真實名 + `os.path.abspath`**。

### 2.2 純度與依賴約定(對 `/pg` 的硬約束)

- 僅允許依賴 Python 標準庫(`os`、`pathlib`)。**不可新增 pip 依賴**,**不 import 任何本專案模組**(尤其不 import `imageset`/`yolo`)。
- **不**讀、不解析、不開啟標註 JSON 內容;`has_labels` 只看「檔名是否存在」,不開檔(內容合法與否、壞檔一律交給 `yolo.load` 容錯)。
- **不**掃影像、不排序(那是 `imageset.scan`);`labelloc` 吃 `imageset` 已產出的 `stems`,兩者解耦。
- `label_path` 為**純字串函式**,不碰 FS、不拋例外。
- 容錯靠**明確的形狀/存在性檢查 + 局部 `try/except OSError`(僅限 `os.listdir` 不可讀目錄這個邊界)**,**不得**用一個包山包海的 `try/except: return <folder>` 吞掉所有邏輯。`resolve_label_dir` / `label_path` **永不拋例外**。

---

## 3. precedence(判定規則 — `labels/` 子夾「條件式優先」,非無條件優先)

`resolve_label_dir(folder, stems, ext, subdir)` 判定順序:

1. **`folder` 非資料夾**(`os.path.isdir(folder)` 為 False;含不存在、是檔案)→ 回 `None`。
   呼叫端 fallback 既有 `st.error("找不到資料夾…")` 路徑。
2. **探 `<folder>/<subdir>/`**(以 §2.1 normcase 枚舉 `listdir(folder)` 找真實子夾名):
   找到一個 `os.path.isdir` 為真且 normcase 命中 `subdir` 的子夾 `D`,**且** `has_labels(D, stems, ext=ext)` 為真
   (子夾被「證實」含這批圖的對應 `<stem><ext>`,至少 1 個)→ **採子夾**,回 `os.path.abspath(D)`。
3. **否則**(`labels/` 不存在、或是檔案非目錄、或存在但空、或存在但沒有任何對應 stem 的 `.json`、或 `listdir` 不可讀)
   → 回 `os.path.abspath(folder)`(**同層**)。

### 為什麼「條件式優先」而非「只看子夾存不存在」

- **(a) 空的或無關的 `labels/` 不該蓋掉同層真檔。** 本專案 `sample_images/` 就是**同層**放 `<stem>.json`;若哪天多了個空 `labels/`,絕不能讓全部偵測憑空消失。
- **(b) 子夾被「證實」才採用。** 對 User 原話「他自己會判斷」給出**穩健、可解釋的單一規則**,而非脆弱的「資料夾存不存在」。

### 平手取捨(刻意,需 PM 釘死)

- **同一 stem 同層與子夾各放一份(內容不同)→ 子夾優先。** 理由:`labels/` 是 YOLO(Ultralytics)慣例的標準位置,視為較權威。
- 此為刻意取捨,**PM 必須**用「同層與子夾各放一份、內容可辨識不同」的測試**釘死回傳子夾路徑**(見 AC9)。若 User/PO 之後要翻案成「同層優先」→ **回退 `/po`**。

### `subdir` 不發散

固定預設 `subdir="labels"`(YOLO 慣例);**不**掃描其他可能名(如 `annotations`)以免規則發散。若 User 之後要更多別名,**回退 `/po`** 擴規格,不在本模組自行加。

---

## 4. 邊界條件與錯誤處理 (Edge Cases & Error Handling)

| # | 情境 | 行為(契約) |
|---|------|------|
| a | `folder` 不存在 / 是檔案而非資料夾 | `resolve_label_dir` 回 `None`(不拋);呼叫端沿用既有「找不到資料夾」錯誤 |
| b | `<folder>/labels/` 存在且含 ≥1 個對應 `<stem>.json` | 回 `<folder>/labels/` 的 abspath(採子夾) |
| c | `<folder>/labels/` 存在但**為空** | **不採子夾**,回 `<folder>` abspath(空子夾不得讓偵測全消失) |
| d | `<folder>/labels/` 含 `*.json` 但**都不對應這批 stems**(stems 給定時) | 不採子夾,回 `<folder>` abspath(避免別批標註誤套) |
| e | `<folder>/labels/` 不存在,同層 `<folder>/` 含 `<stem>.json` | 回 `<folder>` abspath(同層;此為 `sample_images` 現況) |
| f | `stems=None`(呼叫端未提供圖清單) | 退化規則:`labels/` 含**任一** `*<ext>` 即採子夾(較寬鬆便利路徑);文件註明「建議傳 stems 以精準判定」 |
| g | `stems=[]`(空清單;資料夾無支援影像) | `resolve_label_dir` **不採子夾** → 回同層 abspath。(實務上 `app` 在 `records` 為空時已先 `st.stop()`,`labelloc` 通常拿到非空 stems) |
| h | 同一 stem 同層與子夾各有一份(內容不同) | **子夾優先**(見 §3 平手取捨);PM 釘死回傳子夾路徑 |
| i | `labels/` 是**檔案**(不是目錄) | `os.path.isdir` 為 False → 視為無子夾 → 回同層 abspath |
| j | `os.listdir` 權限/`OSError` | `has_labels` / 枚舉吞成 False/略過 → fallback 同層(容錯第一,不拋) |
| k | 子夾名大小寫變體(`Labels/`、`LABELS/`) | 以 normcase 枚舉命中,**用磁碟真實名**組路徑回傳(§2.1);Linux 上 `Labels` 與 `labels` 視為不同夾,枚舉法同樣正確 |
| l | stem / `ext` 大小寫(`IMG1.json` vs stem `img1`;`.JSON` vs `.json`) | 比對以 normcase normalize(§2.1);PM 用混大小寫檔名測試釘死跨平台行為 |
| m | `label_path` 對**不存在**的檔 | 仍回完整路徑字串(不檢存在);存在性與壞檔交給 `yolo.load` 容錯(回 `[]`)—— 維持 `yolo`「永不拋例外」契約,`labelloc` **不**重複該責任 |
| n | `folder` 為相對路徑 / 含 `..` / symlink | 一律 `os.path.abspath` 正規化後回絕對路徑(與 `imageset.scan` 回 abspath 一致),確保下游 `_pred_path` / `_detections` cache key 穩定 |
| o | stem 含 Unicode / 中文 / 特殊字元 | 純字串組路徑 + `Path`,無編碼假設;與既有 sidecar unicode round-trip 一致 |
| p | 影像同名不同副檔(`a.png` 與 `a.jpg` 共用 stem `a`) | 沿用既有 `_pred_path` 語義(共用 `a.json`);`labelloc` **不改變**此語義(要區分需上游改命名規則,非本模組職責) |

> **不做的事**:不讀 JSON 內容、不解析偵測、不判斷標註合法性、不掃影像、不排序、不過濾、不去重。本模組只「定位目錄 + 組路徑」。

---

## 5. Acceptance Criteria(給 `/pm` 落成 pytest;每條帶具體期望值、用真實檔案 I/O 驗)

> 測試置於 `4_PM_Feedback/test_labelloc.py`;`import labelloc`;**目錄結構一律以 `tmp_path` 自造**(造 `<folder>/`、`<folder>/labels/`,各放 `<stem>.json` 空檔或小 JSON),再呼叫斷言。
> **不得** import `imageset` / `yolo`(解耦驗收)。`.json` 內容可為 `""` 或 `"[]"`(本模組不讀內容,只看檔名存在)。
> 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_labelloc.py -p no:cacheprovider --strict-markers -q`
> 閘門:`python verify/gate.py labelloc`(`test_path=4_PM_Feedback/test_labelloc.py`,pytest 全綠 + 契約未竄改 → `GREEN`)。
> 造檔慣例(供 PM 參考,不入契約):
> ```python
> sub = tmp_path / "labels"; sub.mkdir()
> (sub / "img1.json").write_text("[]", encoding="utf-8")
> got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
> assert got == os.path.abspath(str(sub))
> ```

### A. 主入口 `resolve_label_dir` — 核心判定(最具鑑別力)

- **AC1(labels/ 含對應 json → 回子夾)**:`tmp_path/labels/img1.json` 存在,`stems=["img1"]` →
  `resolve_label_dir(str(tmp_path), ["img1"]) == os.path.abspath(str(tmp_path / "labels"))`。
- **AC2(無 labels/、同層含 json → 回同層)**:`tmp_path/img1.json` 存在、**無** `labels/` 子夾,`stems=["img1"]` →
  回 `os.path.abspath(str(tmp_path))`。
- **AC3(labels/ 存在但空 → 回同層)**:`tmp_path/labels/` 存在但**內無任何檔**、`tmp_path/img1.json` 存在,`stems=["img1"]` →
  回 `os.path.abspath(str(tmp_path))`(空子夾不得吃掉同層)。
- **AC4(labels/ 有 json 但 stem 不對應 → 回同層)**:`tmp_path/labels/other.json` 存在(但 `stems=["img1"]`,無 `img1.json`)、`tmp_path/img1.json` 存在 →
  回 `os.path.abspath(str(tmp_path))`(避免別批標註誤套)。
- **AC5(folder 不存在 → None)**:`resolve_label_dir(str(tmp_path / "nope"), ["img1"]) is None`,且**不建立任何檔案/資料夾**(`os.path.exists(str(tmp_path / "nope")) is False`)。
- **AC6(folder 是檔案而非資料夾 → None)**:`f = tmp_path / "afile"; f.write_text("x")` → `resolve_label_dir(str(f), ["img1"]) is None`。
- **AC7(labels/ 是檔案不是目錄 → 回同層)**:`tmp_path/labels`(寫成檔案而非目錄)、`tmp_path/img1.json` 存在,`stems=["img1"]` →
  回 `os.path.abspath(str(tmp_path))`(`isdir` 為 False → 視為無子夾)。
- **AC8(子夾優先於同層:兩處皆有同 stem → 回子夾)**:`tmp_path/labels/img1.json` **與** `tmp_path/img1.json` 皆存在,`stems=["img1"]` →
  回 `os.path.abspath(str(tmp_path / "labels"))`(子夾優先,釘死平手取捨;見 §3)。
- **AC9(子夾優先:內容不同也回子夾路徑)**:同 AC8 但兩份 `.json` 內容刻意不同(如子夾 `'[{"bbox":[1,1,1,1]}]'`、同層 `'[]'`),`stems=["img1"]` →
  `resolve_label_dir` 仍回 `os.path.abspath(str(tmp_path / "labels"))`(本模組不讀內容,只釘死「回的是子夾目錄」)。
- **AC10(回傳恆為絕對路徑)**:對 AC1 與 AC2 的回傳值,`os.path.isabs(got) is True`(即使傳入相對 `folder` 亦然)。
- **AC11(部分對應即採子夾)**:`stems=["img1","img2","img3"]`,但 `tmp_path/labels/` 只有 `img2.json`(其餘缺)→
  回 `os.path.abspath(str(tmp_path / "labels"))`(交集非空即「被證實」,至少 1 個對應即採)。

### B. 退化與空清單

- **AC12(stems=None → 退化:labels/ 含任一 *.json 即採子夾)**:`tmp_path/labels/whatever.json` 存在,`resolve_label_dir(str(tmp_path), None)` →
  回 `os.path.abspath(str(tmp_path / "labels"))`(不要求對應特定 stem)。
- **AC13(stems=None + labels/ 空 → 回同層)**:`tmp_path/labels/` 存在但空、`stems=None` → 回 `os.path.abspath(str(tmp_path))`。
- **AC14(stems=[] 空清單 → 不採子夾 → 回同層)**:`tmp_path/labels/img1.json` 存在但 `stems=[]` →
  回 `os.path.abspath(str(tmp_path))`(空清單視同無對應檔)。

### C. 跨平台大小寫(枚舉法 + normcase)

- **AC15(子夾名大小寫變體 → 命中並回真實名)**:在**子夾名為 `Labels`(首字大寫)** 時造 `tmp_path/Labels/img1.json`,`stems=["img1"]`,`subdir="labels"`(預設)→
  回 `os.path.abspath(str(tmp_path / "Labels"))`(回**磁碟真實名**,而非寫死小寫 `labels`)。
  > PM 註:此測試在 Linux(case-sensitive)上是真鑑別;在 Windows 上 `Labels`/`labels` 同物,回傳真實名仍須等於磁碟枚舉到的名。斷言用磁碟上實際建立的名組期望值,不要寫死字面 `"labels"`。
- **AC16(ext 大小寫 → 視同對應)**:`tmp_path/labels/img1.JSON`(大寫副檔)、`stems=["img1"]`、`ext=".json"`(預設)→
  回 `os.path.abspath(str(tmp_path / "labels"))`(`.JSON` 以 normcase 視同 `.json`)。
  > PM 註:在 case-insensitive FS 上此恆成立;在 case-sensitive FS 上由 normcase 比對保證命中。
- **AC17(stem 大小寫 → 視同對應)**:`tmp_path/labels/IMG1.json`、`stems=["img1"]`(小寫)→
  回 `os.path.abspath(str(tmp_path / "labels"))`(stem 以 normcase 比對)。

### D. `has_labels` helper 直驗

- **AC18(has_labels:含對應 stem → True)**:`tmp_path/labels/img1.json` 存在 →
  `has_labels(str(tmp_path / "labels"), ["img1"]) is True`。
- **AC19(has_labels:空目錄 → False)**:`tmp_path/labels/` 存在但空 →
  `has_labels(str(tmp_path / "labels"), ["img1"]) is False`。
- **AC20(has_labels:有 json 但 stem 不對應 → False)**:`tmp_path/labels/other.json` 存在 →
  `has_labels(str(tmp_path / "labels"), ["img1"]) is False`。
- **AC21(has_labels:不存在目錄 → False 不拋)**:`has_labels(str(tmp_path / "nope"), ["img1"]) is False`(不拋例外)。
- **AC22(has_labels:stems=None → 含任一 *.json 即 True)**:`tmp_path/labels/x.json` 存在 →
  `has_labels(str(tmp_path / "labels"), None) is True`;若目錄空 → `False`。

### E. `label_path` 純字串(對齊既有 `_pred_path`,防 regression)

- **AC23(label_path 純組合)**:`label_path("/some/dir", "/imgs/wafer_001.png") == os.path.join("/some/dir", "wafer_001.json")`。
- **AC24(label_path 不碰 FS / 不檢存在)**:對一個**不存在**的 `label_dir` 與 `image_path`,`label_path` 仍回完整路徑字串、**不拋例外**、**不建立任何檔案**。
- **AC25(label_path 對齊 `_pred_path` 語義)**:對同一 `(dir, image_path)`,`label_path(dir, image_path)` 的結果與「`Path(image_path).stem + '.json'` 接在 `dir` 後」一致
  (即等價於現行 `app._pred_path(dir, image_path)`;PM 以 `os.path.normpath` 比對兩者相等,防 integration regression)。
- **AC26(label_path 接受 stem 取法一致)**:`label_path("/d", "/a/b/IMG_前綴.後綴.png")` 的檔名部分 == `"IMG_前綴.後綴".rsplit` ⇒ 實際為 `Path(...).stem + ".json"`(即 `"IMG_前綴.後綴.json"`,Unicode 安全)。

### F. 容錯不拋(全程)

- **AC27(resolve 永不拋)**:對以下各輸入,`resolve_label_dir` 皆**回值(`str` 或 `None`)而非拋例外**:不存在路徑、檔案路徑、空字串 `""`、含 Unicode 的存在資料夾。
- **AC28(label_path 永不拋)**:`label_path("", "")`、`label_path("/d", "")` 皆回字串、不拋例外。

> **不必驗的**:JSON 內容是否合法、偵測是否解析得出(那是 `yolo.load` 的 AC,見 `07_yolo.md`)。`labelloc` 的 AC **只**驗「定位到哪個目錄 / 組出哪條路徑」。

---

## 6. 整合說明(供 `/pg`:如何接進 `app.py` sidebar 與 `_pred_path`/`_detections`)

> 原則:**最小侵入、單點接入**。不改 `yolo`、不改 `_detections` 的容錯鏈、不動 `conftest.py`/`fixtures/`(PM 擁有)。

### (A) `import`(app.py 模組 import 區,約 32–49 行)

加一行 `import labelloc`(與其他本地模組並列)。

### (B) sidebar「資料來源」(app.py 246–251 行):`pred_folder` 改為「自動判斷 + 可覆寫」

現況:
```python
folder = st.text_input("影像資料夾", value=SAMPLE)
pred_folder = st.text_input("模型結果資料夾(YOLO JSON)", value=folder, help="...")
```
改成:`pred_folder` 由 `labelloc.resolve_label_dir` 自動判定,`text_input` 降級為**可選覆寫**(留空 = 自動)。建議:
- label 改為 `「模型結果資料夾(留空=自動判斷 labels/ 或同層)」`,`value=""`。
- 自動判定需要 `stems`,而 `stems` 來自 `records`;`records` 在 `folder` 通過 `os.path.isdir` 檢查後(app.py 274 行 `if not os.path.isdir(folder)` 與 278 行 `records = _records(folder, fs_sort)`)才取得。
  故**判定點放在 278 行 `records` 取得之後**:
  ```python
  records = _records(folder, fs_sort)
  if not records:
      ...
  # 自動判定 pred 目錄(stems 來自 records);手動覆寫優先
  stems = [Path(r["name"]).stem for r in records]
  resolved = _resolve_pred(folder, tuple(stems))     # 見 (D) 快取
  pred_folder = pred_override.strip() or resolved or folder
  ```
  其中 `pred_override` 是 sidebar 那個「可選覆寫」`text_input` 的值(空字串 = 自動)。
- **可選 UX**:在判定後以 `st.caption` 顯示一行摘要,讓 User 知道「他自己判斷」的結果。摘要字串由 app 端組(例:`偵測到標註於 labels/ 子資料夾` / `同層`),判斷依據 = `resolved` 是否以 `os.sep + "labels"`(或真實子夾名)結尾、或 `resolved == os.path.abspath(folder)`。此為展示層,不入 `labelloc` 契約。

> 注意 sidebar 與判定的**順序**:目前 sidebar 區塊(246–272 行)在 `folder` 的 `isdir` 檢查(274 行)**之前**就 render 完。若要在 sidebar 內顯示摘要 caption,需把「可選覆寫 `text_input`」留在 sidebar(246–251 行區),而把「`resolve` 計算 + caption 顯示」放到 `records` 之後(278 行後),caption 可改用 `st.sidebar.caption(...)` 補回 sidebar。PG 自行取捨擺位,但**判定計算必須在 `records` 之後**(因需 `stems`)。

### (C) `_pred_path`(app.py 205–208)：**完全不改**

它已是 `<pred_folder>/<stem>.json`,只要餵進 `labelloc` 解析出的 `pred_folder` 即生效。`label_path` 與 `_pred_path` 語義等價(AC25 釘死),故 app 端**不需 import `label_path`**,只用 `resolve_label_dir` 決定 `pred_folder`。

### (D) `_detections`(app.py 211–214)：**不改**

它呼叫 `yolo.load(_pred_path(pred_folder, image_path), ...)`。`pred_folder` 換成解析後目錄即生效。雙層容錯仍在:`resolve_label_dir` 回 `None` 時 `pred_folder = folder`(同層),`_pred_path` 組出同層路徑,`yolo.load` 對不存在路徑再回 `[]` → 全鏈不崩。

### (E) cache 一致性(避免每 rerun 多 syscall)

`resolve_label_dir` 做 `listdir`,屬輕量 I/O,但每 rerun 都跑會多 syscall。建議在 app 端包一層快取(**屬 app 整合層,不入 `labelloc` 契約**):
```python
@st.cache_data(show_spinner=False)
def _resolve_pred(folder, stems_key):   # stems_key = tuple(stems),可雜湊
    return labelloc.resolve_label_dir(folder, list(stems_key))
```
與 `_records` 同層快取;`folder` 內容變動時 User 重整即可(取捨與現行 `_records`/`scan` 快取一致 —— 中途新增/移動標註檔需重跑才更新,`labelloc` 不引入新例外)。`resolve_label_dir` 為純函式且對固定磁碟狀態確定性 → 同 key 同結果,cache 安全。

### (F) E2E 影響(給 `/pm` / `/ux-test`,本輪非必需)

現有 `sample_images/` 是**同層**放 `<stem>.json` → 自動判定會回同層(= `folder`),既有 `test_app_e2e` / `test_m7*` 行為**不變**(預設仍讀同層)。若要新增「labels/ 子夾」的 E2E,屬整合層測試,標 `@pytest.mark.e2e` 另置 `test_labelloc_e2e.py`,**不進 PG 自主修綠迴圈**(本模組單元綠即可判 done,整合行為由既有 app E2E 覆蓋)。

---

## 7. 與其他模組的邊界(防越權)

- **`labelloc` 只「定位目錄 + 組路徑」**;**絕不**讀/解析 JSON 內容、不判斷標註是否合法、不判斷檔案內容 —— 存在性與壞檔一律交給 `yolo.load` 容錯回 `[]`(呼應 `07_yolo.md` §6:`yolo` 是 `Detection` 唯一生產者、容錯第一)。`has_labels` 只看「檔名是否存在」,**不開檔**。
- **不**掃影像、**不**排序(那是 `imageset.scan`);`labelloc` 吃 `imageset` 已產出的 `stems`,兩者解耦,`labelloc` 測試**不 import `imageset`**。
- **不**畫圖、**不**做 conf 過濾 / class 篩選(那是 `overlay`)。
- 本模組對外承諾:`resolve_label_dir` / `label_path` **永不拋例外**;回傳為「絕對路徑字串 / `None`」(resolve)或「路徑字串」(label_path);僅依賴 Python 標準庫;不建檔、不寫檔、不讀標註內容、不改原圖。

---

## 8. Tier 與 done 定義

- **Tier B**(有檔案系統 I/O:`os.path.isdir`/`listdir`/`abspath`),但**無 GUI、無跨模組 import 契約** → **可純單元判綠**:`tmp_path` 造 `<folder>/`、`<folder>/labels/`、各放 `<stem>.json`,`verify/gate.py` 跑 `test_labelloc.py` 全綠即 `GREEN`,**E2E 非必需**(整合行為由既有 app E2E 覆蓋)。
- 這是**新增**模組,不動 `3_/4_` 既有契約檔,不會觸發 `gate.py` 的契約竄改偵測。

---

## 9. 給 PO 的回報(ROADMAP 決策日誌建議記一行)

- 新增模組 `labelloc`(Tier B,純單元判綠):讓 sidebar 從「手填 `pred_folder`」演進為「選一個資料夾,自動判定 `labels/` 子夾 vs 同層」,回應 User 原話「他自己會判斷」。
- **裁決記錄**:平手(同層與子夾都有同 stem)採「**子夾優先**」(YOLO 慣例,視為較權威);若要翻案成同層優先 → 回退 `/po`。
- **範圍裁切**:本輪 `ext` 固定 `'.json'`(對齊既有鏈);`.txt` 經典 YOLO 與其他子夾別名(`annotations`)**不入本輪契約**(YAGNI),需要時回退 `/po` 開規格。

---

## 10. 設計開放問題的裁決(architect 已決,記錄留痕)

兩個探索視角提出的開放問題,本設計裁決如下(避免 PG/PM 重新發散):

1. **「folder 層級單一 `pred_folder`」 vs 「per-image 逐張解析(支援 mixed 佈局)」**:
   本輪採**folder 層級單一 `pred_folder`**(`resolve_label_dir`),理由 = **最小侵入**(`_pred_path`/`_detections`/`yolo` 全不改,只換 `pred_folder` 來源),且對齊 User 原話「判斷 labels 在子資料夾**或**同層」(二擇一的資料夾級語義,非逐張混合)。
   「逐張混合(部分圖在子夾、部分在同層)」屬**過度設計**,本輪**不納入契約**;若 User 之後真有混合佈局需求 → 回退 `/po` 開規格(屆時可加 `resolve(folder, image_path)` 逐張入口 + sidebar `mixed` 摘要)。**本輪 PM 不需為 mixed 寫 AC。**
2. **Linux 副檔名 / stem 大小寫**:採 **`os.listdir` 枚舉 + `os.path.normcase` 比對**(非直接字串 `isfile` 拼接),以跨平台一致(見 §2.1);AC15–AC17 釘死。
3. **`subdir` 別名(`annotations` 等)**:本輪**只認 `labels`**(§3),不發散;要擴張回退 `/po`。
4. **同名不同副檔影像共用 stem 標註**:**沿用既有 `_pred_path` 語義**(可接受),`labelloc` 不改變(§4.p)。
