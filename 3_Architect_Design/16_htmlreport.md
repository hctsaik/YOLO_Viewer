# 設計:`htmlreport`(M5 / Tier B — 自含 HTML Case Package 報告,純字串組裝 + 薄檔案寫入,需真實寫讀驗收)

> `/architect` 產物(module 粒度)。對應 `ROADMAP.md` 第 27-33 行 M5、第 59 行 `htmlreport`(B / 📝 / 依賴 `Detection`/`sidecar` 形狀)、第 33 行「PDF 列候選 → htmlreport 先出 HTML(瀏覽器可印 PDF)」。
> 上游資料形狀:同 `casepkg`(`3_Architect_Design/11`)的 `item` 形狀與欄位扁平化規則;`Detection` 為 PO 跨模組釘死形狀。
> 本檔只定義契約與驗收,**不含任何實作**。實作由 `/pg` 寫進 `5_PG_Develop/htmlreport.py`。
> 與 `casepkg` 關係:**同 item 形狀、同欄位扁平化(verdict 缺→`"unset"` 等)**,但輸出目標不同 —— casepkg 出 CSV/JSON(機器互通);本模組出**一份自含、可直接用瀏覽器開/列印的 HTML 報告**(人類分享/列印)。**兩者互不 import。**

## 模組邊界 sanity check(開工前一句)

`htmlreport` 內聚一句話可講完:「把一批已選案例(record 摘要 + sidecar 判讀 dict + model `Detection` 清單)扁平化後,組成**一份單檔、無外部 CSS/JS 相依、可直接以瀏覽器開啟與列印**的 HTML 報告(標題 + 摘要列 + 一張表),並可薄寫成 `.html` 檔」。
它**只消費 dict**(`item["sidecar"]`、`item["detections"]`),**不 import** `casepkg`/`sidecar`/`yolo`/`tagging` 任一實作 —— 完全靠資料形狀解耦,故可獨立設計、可用 `tmp_path` 真實寫讀驗收。
與 `casepkg` **不合併**(輸出格式與消費者不同:CSV/JSON 給機器互通 vs HTML 給人看/印);與 `filtersort` **不合併**(那是「選哪些、什麼順序」;本模組吃已選定 `items` 原序輸出)。**結論:範圍 OK,不退回 `/po`。**

---

## 1. 目的 (Purpose)

把一組「選定案例」渲染成**一份自含(self-contained,無外部 CSS/JS、無外部圖片相依)的 HTML 字串**,內含標題、摘要列(總案數 / 已審數)與一張每案一列的表格(name/verdict/tags/status/n_det/max_conf/comment),所有使用者/資料來源的文字皆經 HTML 逸出防止破版與 XSS;並可把該 HTML 薄寫成 UTF-8 `.html` 檔,供分享、列印(瀏覽器可印成 PDF)。**只讀傳入的 dict、只寫指定輸出檔,絕不讀寫原始影像或 sidecar 檔,不發網路請求。**

---

## 2. 相依與限制

- 僅用 Python 標準庫:`html`(逸出)、`os`(或 `pathlib`,僅 `write_report` 用)。**不可新增任何 pip 依賴。**
- 模組層級**零 GUI、零 Streamlit、零網路、零外部資源參照**(輸出 HTML **不得**含 `<link rel="stylesheet">`、`<script src=...>`、`<img src="http...">` 等外部相依;CSS 一律 `<style>` 內聯)。
- **嚴禁 `import casepkg` / `import sidecar` / `import yolo` / `import tagging`**(只吃 dict;扁平化規則與「已審」判定**逐字自含**於本模組,值與上游一致)。
- 進入點檔名:`5_PG_Develop/htmlreport.py`(測試 `import htmlreport`,conftest 已把 `5_PG_Develop` 置於 `sys.path`)。
- 純函式 `escape` / `build_html` 無副作用、不就地改輸入;唯一有 I/O 者為 `write_report`。

---

## 3. I/O 契約(逐字採用,簽名為硬契約,/pm 直接鎖)

```python
def escape(text) -> str
# 對任意輸入先 str(text),再做 HTML 逸出;逸出行為釘死見 §3.2(等價 html.escape(str(text), quote=True))

def build_html(items: list[dict], title: str = "CV Review Report") -> str
# 回完整 HTML 字串(以 "<!DOCTYPE html>" 開頭、以 "</html>" 結尾);結構見 §3.3 / §3.4

def write_report(out_path, items: list[dict], title: str = "CV Review Report") -> str
# 把 build_html(items, title) 以 UTF-8 寫進 out_path;回傳寫入的路徑字串(== str(out_path));見 §3.6
```

### 3.1 輸入 `item` 形狀(契約,釘死 —— 與 `casepkg` §3.1 完全一致)

```python
item = {
    "name":       str,              # 顯示名(通常影像檔名);缺 → ""
    "path":       str,              # 影像路徑;缺 → ""(本模組不渲染 path 欄,但接受其存在)
    "sidecar":    dict,             # 一份 sidecar dict(形狀同 sidecar 模組 default());缺 → {}
    "detections": list[Detection],  # model 結果;缺 → []
}
```

`sidecar` dict 本模組**只讀**下列鍵(其餘鍵忽略),缺鍵一律套「預設視同值」(**與 `casepkg` 同值**):

| sidecar 鍵 | 型別 | 缺鍵預設(視同值) | 對應表格欄 |
|------------|------|--------------------|------------|
| `review_status` | `str` | `"none"` | `status` |
| `verdict` | `str` | `"unset"` | `verdict` |
| `tags` | `list[str]` | `[]` | `tags`(以 `; ` 串接,見 §3.4) |
| `comment` | `str` | `""` | `comment` |

> 註:`verdict` 缺鍵預設 = `"unset"`(延續 `app.py` 第 201 行 `s.get("verdict","unset")` 與 `tagging.VERDICTS[0]`);`review_status` 缺鍵預設 = `"none"`。本模組對外承諾即此。
> 本模組**不渲染** `bookmarked` / `rois` 欄(報告聚焦判讀總覽;若 Phase 2 要加,屬新增欄、另議)。

### 3.1.1 `Detection` 形狀(PO 跨模組釘死,本模組只消費)

```python
Detection = {"bbox": [x, y, w, h], "cls": str, "conf": float}   # conf ∈ [0,1]
```

本模組只讀 `det["conf"]`(算 `n_det`/`max_conf`),**不讀 `bbox`/`cls`、不渲染、不驗證**。

### 3.2 `escape` 逸出行為(**釘死,等價 `html.escape(str(text), quote=True)`**)

`escape(text)` 先 `s = str(text)`,再對 `s` 做**恰好如下五種字元**取代(實作建議直接 `return html.escape(s, quote=True)`;契約以下方逐位元結果為準):

| 原字元 | 逸出為 | 說明 |
|--------|--------|------|
| `&` | `&amp;` | **必須最先換**(避免二次逸出);`html.escape` 內部已保證此序 |
| `<` | `&lt;` | |
| `>` | `&gt;` | |
| `"` | `&quot;` | 雙引號(`quote=True`) |
| `'` | `&#x27;` | 單引號(`html.escape(..., quote=True)` 的固定輸出;**契約即此確切字串**,非 `&#39;`、非 `&apos;`) |

- 其餘字元(含中文、空白、數字、`;`、`,`)**原樣保留**(`html.escape` 不動非上述五者;UTF-8 中文不被轉成 entity)。
- 非字串輸入先 `str()`:`escape(3)=="3"`、`escape(True)=="True"`、`escape(None)=="None"`、`escape(0.9)=="0.9"`。
- **逸出後輸出絕不含原始未逸出的 `<`、`>`、`&`(除非作為合法 entity 的 `&` 開頭,如 `&amp;`)、裸 `"`、裸 `'`**;故任何含 `<script>` 的使用者文字逸出後**不含子字串 `<script>`**(已成 `&lt;script&gt;`)。

逐字範例(契約,/pm 直接斷言):

```python
escape("<script>")            == "&lt;script&gt;"
escape("a & b")               == "a &amp; b"
escape('say "hi"')            == "say &quot;hi&quot;"
escape("it's")                == "it&#x27;s"
escape("Tom & Jerry <co>")    == "Tom &amp; Jerry &lt;co&gt;"
escape("刮傷,邊緣")           == "刮傷,邊緣"          # 中文與逗號原樣
escape("a<b>c&d\"e'f")        == "a&lt;b&gt;c&amp;d&quot;e&#x27;f"
escape("&amp;")               == "&amp;amp;"          # 已是 entity 的 & 仍被逸出(無智慧偵測)
```

### 3.3 整體 HTML 骨架(**釘死,自含**)

`build_html(items, title)` 回傳之字串**必須**:

1. 以 `"<!DOCTYPE html>"` 開頭(允許其後接換行)。
2. 以 `"</html>"` 結尾(允許結尾接單一換行 `\n`;即 `out.rstrip("\n").endswith("</html>")` 為真,且 `out.startswith("<!DOCTYPE html>")`)。
3. 依序包含這些**確切子字串**(由外而內,順序即出現順序):
   - `<html lang="zh-Hant">`(根元素,標明語系)
   - `<head>` … `</head>` 內含:
     - `<meta charset="utf-8">`
     - `<title>{escape(title)}</title>`(title 經 §3.2 逸出)
     - `<style>` … `</style>`(內聯 CSS;**不得**出現 `<link` 或 `href=`)
   - `<body>` … `</body>` 內含:
     - `<h1>{escape(title)}</h1>`(主標題,逸出後 title)
     - 摘要列(見 §3.5)
     - 一個 `<table>` … `</table>`(見 §3.4)
4. **自含性**:整份輸出**不得**包含子字串 `<link`、`href=`、`<script`(注意:即使是被逸出後的 `&lt;script&gt;` 也不含 `<script` 這個原始子字串,故此檢查同時保證 §3.4 的逸出正確)、`src=`、`http://`、`https://`(無任何外部資源參照)。
5. CSS 內聯於單一 `<style>` 區塊;極簡即可(至少含 `table`、`th`、`td` 的邊框/間距規則,使列印可讀;確切 CSS 內容不入 AC,只鎖「存在 `<style>...</style>` 且不引外部」)。

> 結構順序鎖定:`title 出現在 <title> 與 <h1>`、`<head>` 先於 `<body>`、摘要列先於 `<table>`。其餘空白/換行排版**不入 AC**(/pm 以「子字串包含」與「正則計數」斷言,不逐位元比對整份 HTML;唯 `escape`、單一 cell 文字、`write_report` round-trip 逐字)。

### 3.4 `<table>` 結構(**釘死**)

表格恰含 **7 欄**,表頭順序固定:

```
Name, Verdict, Tags, Status, Detections, Max Conf, Comment
```

- **表頭列**:一個 `<tr>`,內含恰 7 個 `<th>`,文字依序為上述 7 個英文標籤(這些是固定字面,不經 item 資料,故不逸出;確切 `<th>` 文字釘死見 AC)。
- **資料列**:每個 item 產生**恰一個** `<tr>`,內含恰 7 個 `<td>`,值依序為:

| # | 欄 | 來源 / 計算 | `<td>` 內文字(全部經 §3.2 `escape`) |
|---|-----|-------------|--------------------------------------|
| 1 | Name | `item.get("name","")` | `escape(name)` |
| 2 | Verdict | `sidecar.get("verdict","unset")` | `escape(verdict)` |
| 3 | Tags | `"; ".join(sidecar.get("tags",[]))` | `escape("; ".join(tags))`(分隔符 = 分號 + 空格;空清單 → `""` → 空 `<td></td>`) |
| 4 | Status | `sidecar.get("review_status","none")` | `escape(status)` |
| 5 | Detections | `len(item.get("detections",[]))` | `escape(str(n_det))`(整數轉字串;如 `"3"`) |
| 6 | Max Conf | 見「max_conf 規則」 | `escape(max_conf_text)`(見下) |
| 7 | Comment | `sidecar.get("comment","")` | `escape(comment)` |

- **max_conf 規則**:`detections` 為空 → 數值 `0.0`;否則 `= max(float(d["conf"]) for d in detections)`。**呈現文字**為**四捨五入至小數第 3 位、固定 3 位小數**的字串,即 `max_conf_text = f"{max_conf:.3f}"`(例:`0.9`→`"0.900"`、`0.0`→`"0.000"`、`0.5`→`"0.500"`、`0.873`→`"0.873"`、`0.8765`→`"0.877"`)。此為**呈現格式**(與 casepkg 不四捨五入的 row 值不同,因報告是給人看的);n_det 不四捨五入。
- 每個 `<tr>` **完整成對**(`<tr>`…`</tr>`),內 7 個 `<td>` 完整成對;故 `<tr>` 數 = `1(表頭) + len(items)`,`</tr>` 同數;表頭那列用 `<th>`、資料列用 `<td>`,使「資料 `<tr>` 數」可由「含 `<td>` 的列」或「總 `<tr>` 數 − 1」推得。
- **欄與 item 對齊**:第 i 個資料 `<tr>` 對應 `items[i]`(原序,不排序、不去重)。

> Tags 串接用 `"; "`(分號加空格,人類可讀),**與 casepkg 的 CSV `";"`(無空格)不同**——這是刻意的呈現差異,已釘死。

### 3.5 摘要列(**釘死**)

`<body>` 中、`<table>` 之前,有一段摘要,**必須**包含這兩個確切子字串(數字為十進位整數):

```
總案數:{N}
已審數:{R}
```

其中:
- `N = len(items)`。
- `R = 已審案數`,「已審」判定**逐字自含**(與 `tagging.is_reviewed` 同義,但不 import):
  ```
  reviewed(sidecar) := (sidecar.get("verdict","unset") != "unset") or (sidecar.get("review_status","none") == "done")
  ```
  `R = sum(1 for it in items if reviewed(it.get("sidecar", {})))`。
- 摘要文字本身為固定字面 + 整數,**不含使用者資料**,故不需逸出(整數以 `str()` 嵌入)。
- 兩個子字串各自完整出現(允許其間有 HTML 標籤/空白,如 `<p>總案數:2　已審數:1</p>`;/pm 以 `"總案數:2" in html` 與 `"已審數:1" in html` 斷言,不鎖兩者間排版)。

### 3.6 `write_report` 行為(**Tier B,真實寫入**)

```
write_report(out_path, items, title="CV Review Report"):
  html_str = build_html(items, title)
  以 open(out_path, "w", encoding="utf-8") 寫入 html_str       # UTF-8,不指定 newline(允許平台換行,但見下注)
  return str(out_path)
```

- 檔案以 **UTF-8** 寫入(中文 title/tag/comment 無損)。
- 回傳值 = `str(out_path)`(字串化傳入路徑;`out_path` 可為 `str` 或 `pathlib.Path`)。
- **round-trip 契約**:以 `open(ret, "r", encoding="utf-8").read()` 讀回的字串 **== `build_html(items, title)`**(內容逐字相等)。
  > 為使 round-trip 逐字成立,`build_html` 產生的字串**不得**自行使用 `\r\n`(一律用 `\n` 或不含換行的純串接);寫檔以 text 模式 UTF-8。若實作擔心平台換行轉換影響逐字比對,得以 `newline=""` 開檔(契約只要求「讀回 == build_html 輸出」,實作自選達成方式)。
- **覆寫語義**:同 `out_path` 重複呼叫,後者完全覆寫前者(非附加)。
- `write_report` **不負責**建立多層父目錄(契約不承諾 `makedirs`;與 casepkg `write_package` 寫「目錄」不同,本模組寫「單一檔」)。/pm 的 Tier B AC 一律寫進 `tmp_path` 下既存目錄的檔名(如 `tmp_path / "r.html"`),不依賴自動建目錄。

---

## 4. 資料流 (Data Flow)

```
items: list[item]
  │  (每 item: name/path/sidecar(dict)/detections(list[Detection]))
  └─ build_html(items, title)
        ├─ <head>: <title>escape(title)</title> + 內聯 <style>
        ├─ <h1>escape(title)</h1>
        ├─ 摘要:總案數 N=len(items) / 已審數 R=Σ reviewed(sidecar)
        └─ <table>:
             表頭 <tr><th>×7</th></tr>
             每 item → <tr><td>×7</td></tr>:
                name | verdict | "; ".join(tags) | status | n_det | f"{max_conf:.3f}" | comment
                （每 cell 文字皆 escape()）
        ⇒ 完整 HTML 字串("<!DOCTYPE html>" … "</html>")
  write_report(out_path, items, title)
        └─ build_html(items, title) ─→ out_path (UTF-8)，回 str(out_path)
```

- 所有彙整(`n_det` = `len(detections)`、`max_conf` = `max conf` 或 `0.0`、`reviewed`)在 `build_html` 內部一次算出。
- `escape` 在組裝每個會嵌入使用者/資料文字的位置呼叫(`<title>`、`<h1>`、每個資料 `<td>`);**固定字面**(`<th>` 標籤文字、摘要的「總案數:」「已審數:」、CSS、骨架標籤)**不**經 `escape`(它們不含使用者資料)。

---

## 5. 邊界條件與錯誤處理

| 情境 | 行為(契約) |
|------|------|
| `items == []`(空) | 仍回**合法 HTML 骨架**(`<!DOCTYPE html>`…`</html>`、含 `<title>`/`<h1>`/`<style>`/`<table>`);摘要為 `總案數:0` 與 `已審數:0`;表格**只有表頭列**(`<tr>` 計數 = 1,無資料 `<td>`);並含「無資料」訊息子字串 `沒有可顯示的案例`(見 AC) |
| item 缺 `sidecar` 鍵 | 視同 `{}`,各欄套 §3.1 預設(verdict→`unset`、status→`none`、tags→``、comment→``),不丟 `KeyError` |
| item 缺 `detections` 鍵 | 視同 `[]`:`n_det=0`、`max_conf=0.0` → Max Conf 欄 `"0.000"` |
| item 缺 `name` | 視同 `""`,Name 欄 → 空 `<td></td>` |
| `tags`/`comment`/`name` 含 `<`、`>`、`&`、`"`、`'` | 一律經 §3.2 `escape`;輸出**不含**原始未逸出形式(`<script>` → `&lt;script&gt;`),不破版、不可注入 |
| `tags` 為非空 list | 以 `"; "` 串接後再 `escape`(整串一次逸出);空 list → 空字串 → 空 cell |
| `comment` 含中文/逗號 | 原樣保留(`escape` 不動中文與逗號),UTF-8 寫檔無損 |
| `conf` 為 int(如 `1`) | `float(1)=1.0` → Max Conf 欄 `"1.000"` |
| `title` 含特殊字元(如 `<b>&"` ) | `<title>` 與 `<h1>` 內皆為 `escape(title)`;不破版、不注入 |
| `title` 省略 | 用預設 `"CV Review Report"`(出現在 `<title>` 與 `<h1>`) |
| `out_path` 父目錄不存在 | **不承諾自動建立**(write_report 只寫單檔);/pm 一律寫進既存目錄(`tmp_path`),不測自動建目錄 |
| 輸入 `items` mutate | 禁止;純函式不就地改 `items`、`sidecar`、`detections`、`tags`(以呼叫前後 `deepcopy` 相等驗證) |

---

## 6. Acceptance Criteria(給 `/pm` 落成 pytest;每條帶具體期望值、可驗)

> 測試置於 `4_PM_Feedback/test_htmlreport.py`(`write_report` 用 `tmp_path` 真實寫讀);`import htmlreport`;部分 AC 用 `import re`。
> 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_htmlreport.py -p no:cacheprovider --strict-markers -q`
>
> 共用測試夾具(下列 AC 引用 `IT1`/`IT2`/`ITX`):
> ```python
> IT1 = {"name":"a.png", "path":"/img/a.png",
>        "sidecar":{"review_status":"done","verdict":"true_defect",
>                   "tags":["True Defect","Need Review"],
>                   "bookmarked":True,"rois":[{"bbox":[1,2,3,4]}],"comment":"刮傷,邊緣"},
>        "detections":[{"bbox":[10,20,30,40],"cls":"scratch","conf":0.9},
>                      {"bbox":[50,60,10,10],"cls":"dent","conf":0.5},
>                      {"bbox":[0,0,5,5],"cls":"scratch","conf":0.7}]}
> IT2 = {"name":"b.png", "path":"/img/b.png", "sidecar":{}, "detections":[]}   # 全缺鍵
> # 對抗用 item:name/comment 帶 XSS 與特殊字元
> ITX = {"name":"<script>alert(1)</script>", "path":"/img/x.png",
>        "sidecar":{"verdict":"unset","review_status":"none",
>                   "tags":["a<b>","c&d"], "comment":'He said "hi" & <b>bye</b>'},
>        "detections":[{"bbox":[0,0,1,1],"cls":"scratch","conf":0.8765}]}
> ```

### A. escape(逸出行為,釘死)
- **AC1**:`htmlreport.escape("<script>") == "&lt;script&gt;"`。
- **AC2**:`htmlreport.escape("a & b") == "a &amp; b"`(`&` → `&amp;`)。
- **AC3**:`htmlreport.escape('say "hi"') == "say &quot;hi&quot;"`(雙引號 → `&quot;`)。
- **AC4**:`htmlreport.escape("it's") == "it&#x27;s"`(單引號 → `&#x27;`,確切字串)。
- **AC5(混合)**:`htmlreport.escape("a<b>c&d\"e'f") == "a&lt;b&gt;c&amp;d&quot;e&#x27;f"`(五種字元同時、順序正確、`&` 不二次逸出)。
- **AC6(中文/逗號原樣)**:`htmlreport.escape("刮傷,邊緣") == "刮傷,邊緣"`(非五種字元一律不動)。
- **AC7(非字串先 str)**:`htmlreport.escape(3) == "3"` 且 `htmlreport.escape(True) == "True"` 且 `htmlreport.escape(None) == "None"` 且 `htmlreport.escape(0.9) == "0.9"`。
- **AC8(已是 entity 仍逸出)**:`htmlreport.escape("&amp;") == "&amp;amp;"`(無智慧偵測,`&` 一律 → `&amp;`)。
- **AC9(逸出後不含危險原形)**:`out = htmlreport.escape("<script>x</script>")`;`("<script>" not in out) and ("</script>" not in out) and (out == "&lt;script&gt;x&lt;/script&gt;")`。

### B. build_html 骨架與自含性(釘死)
- **AC10(DOCTYPE/結尾)**:`h = htmlreport.build_html([IT1, IT2])`;`h.startswith("<!DOCTYPE html>")` 且 `h.rstrip("\n").endswith("</html>")`。
- **AC11(必含骨架子字串)**:對 `h = htmlreport.build_html([IT1])`,下列子字串**皆 `in h`**:`'<html lang="zh-Hant">'`、`'<meta charset="utf-8">'`、`"<head>"`、`"</head>"`、`"<body>"`、`"</body>"`、`"<style>"`、`"</style>"`、`"<table>"`、`"</table>"`。
- **AC12(自含:無外部資源)**:對 `h = htmlreport.build_html([IT1, IT2, ITX])`,下列子字串**皆不在** `h` 中:`"<link"`、`"href="`、`"<script"`、`"src="`、`"http://"`、`"https://"`(注意:含 `<script>` 的 `ITX["name"]` 已被逸出成 `&lt;script&gt;`,故 `"<script"` 不出現,本條同時驗逸出正確)。
- **AC13(head 先於 body,摘要先於 table)**:`h = htmlreport.build_html([IT1])`;`h.index("<head>") < h.index("<body>")` 且 `h.index("總案數") < h.index("<table>")`。

### C. 標題(出現在 <title> 與 <h1>,逸出)
- **AC14(預設標題)**:`h = htmlreport.build_html([IT1])`;`"<title>CV Review Report</title>" in h` 且 `"<h1>CV Review Report</h1>" in h`。
- **AC15(自訂標題)**:`h = htmlreport.build_html([IT1], title="我的報告")`;`"<title>我的報告</title>" in h` 且 `"<h1>我的報告</h1>" in h`。
- **AC16(標題逸出)**:`h = htmlreport.build_html([], title='X<b>&"')`;`'<title>X&lt;b&gt;&amp;&quot;</title>' in h` 且 `'<h1>X&lt;b&gt;&amp;&quot;</h1>' in h`(`<title>`/`<h1>` 內 title 經逸出,無原始 `<b>`)。

### D. 摘要列(總案數 / 已審數,釘死計數)
- **AC17(IT1+IT2)**:`h = htmlreport.build_html([IT1, IT2])`;`"總案數:2" in h` 且 `"已審數:1" in h`(IT1 verdict=`true_defect`≠unset 且 status=`done` → 已審;IT2 全缺鍵 → 未審)。
- **AC18(空 items)**:`h = htmlreport.build_html([])`;`"總案數:0" in h` 且 `"已審數:0" in h`。
- **AC19(已審判定:僅 verdict)**:對 `it = {"name":"v","sidecar":{"verdict":"false_alarm","review_status":"none"},"detections":[]}`,`htmlreport.build_html([it])` 含 `"已審數:1"`(verdict≠unset 即已審,即使 status=none)。
- **AC20(已審判定:僅 status=done)**:對 `it = {"name":"s","sidecar":{"verdict":"unset","review_status":"done"},"detections":[]}`,`htmlreport.build_html([it])` 含 `"已審數:1"`(status=done 即已審,即使 verdict=unset)。
- **AC21(未審)**:對 `it = {"name":"n","sidecar":{"verdict":"unset","review_status":"none"},"detections":[]}`,`htmlreport.build_html([it])` 含 `"已審數:0"` 且 `"總案數:1"`。

### E. 表格結構與列數(釘死)
- **AC22(表頭 7 個 th,文字精確)**:`h = htmlreport.build_html([IT1])`;以 `re.findall(r"<th>(.*?)</th>", h)` 取得的清單 **== `["Name","Verdict","Tags","Status","Detections","Max Conf","Comment"]`**(恰 7 欄、順序固定)。
- **AC23(資料列數 = len(items))**:對 `items` 各種長度,`len(re.findall(r"<tr>", htmlreport.build_html(items)))` **== `1 + len(items)`**(1 表頭 + 每案一列);驗 `items=[IT1,IT2]`→3、`items=[IT1]`→2、`items=[]`→1、`items=[IT1,IT2,ITX]`→4。
- **AC24(`<tr>` 與 `</tr>` 成對)**:`h = htmlreport.build_html([IT1, IT2])`;`h.count("<tr>") == h.count("</tr>") == 3`。
- **AC25(每資料列 7 個 td)**:`h = htmlreport.build_html([IT1])`;`h.count("<td>") == 7`(單一 item → 一列 7 cell);`htmlreport.build_html([IT1, IT2]).count("<td>") == 14`。
- **AC26(空 items 只有表頭)**:`h = htmlreport.build_html([])`;`h.count("<tr>") == 1` 且 `h.count("<td>") == 0` 且 `"沒有可顯示的案例" in h`(無資料訊息)。

### F. 資料列逐 cell 值(釘死,含逸出與格式)
- **AC27(IT1 七個 cell 確切)**:`h = htmlreport.build_html([IT1])`;以 `re.findall(r"<td>(.*?)</td>", h)` 取得 **== `["a.png","true_defect","True Defect; Need Review","done","3","0.900","刮傷,邊緣"]`**(Name/Verdict/Tags(以 `"; "` 串接)/Status/n_det=3/Max Conf=`f"{0.9:.3f}"`=`"0.900"`/中文 comment 原樣)。
- **AC28(IT2 全缺鍵 cell 確切)**:`h = htmlreport.build_html([IT2])`;`re.findall(r"<td>(.*?)</td>", h)` **== `["b.png","unset","","none","0","0.000","" ]`**(name=b.png、verdict→unset、tags→空、status→none、n_det=0、max_conf→`"0.000"`、comment→空)。
- **AC29(max_conf 格式 = 三位小數)**:對 `it = {"name":"c","sidecar":{},"detections":[{"bbox":[0,0,1,1],"cls":"x","conf":0.5}]}`,`re.findall(r"<td>(.*?)</td>", htmlreport.build_html([it]))[5] == "0.500"`;對 IT1(max conf 0.9)為 `"0.900"`;對 `conf` 為 int `1` 的 item 為 `"1.000"`;對 `conf=0.8765` 為 `"0.877"`(四捨五入至 3 位)。
- **AC30(XSS/特殊字元逸出進 cell)**:`h = htmlreport.build_html([ITX])`;`cells = re.findall(r"<td>(.*?)</td>", h)`;
  ```python
  assert cells[0] == "&lt;script&gt;alert(1)&lt;/script&gt;"          # name 逸出,無原始 <script>
  assert cells[2] == "a&lt;b&gt;; c&amp;d"                            # tags "a<b>","c&d" → "; " 串接後逸出
  assert cells[6] == "He said &quot;hi&quot; &amp; &lt;b&gt;bye&lt;/b&gt;"   # comment 逸出
  assert "<script>" not in h and "alert(1)" in cells[0]              # 危險標籤已成文字,內容仍可見
  ```
- **AC31(多 item 列序對齊 items)**:`h = htmlreport.build_html([IT1, IT2])`;`names = re.findall(r"<tr>.*?<td>(.*?)</td>", h, re.S)`(各列首 cell);`names == ["a.png","b.png"]`(原序、與 items 一致)。

### G. 不 mutate 輸入
- **AC32(build_html 不改輸入)**:`import copy`;`snap = copy.deepcopy([IT1, IT2, ITX])`;呼叫 `htmlreport.build_html([IT1, IT2, ITX])` 後 `[IT1, IT2, ITX] == snap`(`tags`/`sidecar`/`detections` 皆未被 mutate)。

### H. write_report(Tier B,tmp_path 真實寫讀,逐字)
- **AC33(回傳路徑 == str(out_path) 且檔存在)**:`p = tmp_path / "r.html"`;`ret = htmlreport.write_report(p, [IT1, IT2])`;`ret == str(p)` 且 `os.path.exists(ret) is True`。
- **AC34(寫入內容 == build_html,讀回逐字相等)**:
  ```python
  p = tmp_path / "r.html"
  ret = htmlreport.write_report(p, [IT1, IT2], title="我的報告")
  with open(ret, "r", encoding="utf-8") as f:
      disk = f.read()
  assert disk == htmlreport.build_html([IT1, IT2], title="我的報告")   # 內容逐字一致
  ```
- **AC35(UTF-8 中文無損 + 逸出正確)**:承 AC34 的 `disk`;`"刮傷,邊緣" in disk`(中文 comment 無損)且 `"<title>我的報告</title>" in disk` 且(以 ITX 寫一份時)`"&lt;script&gt;" in disk and "<script>" not in disk`(用另一檔 `p2 = tmp_path / "x.html"` 寫 `[ITX]` 後讀回斷言)。
- **AC36(out_path 接受 str)**:`p = str(tmp_path / "s.html")`;`ret = htmlreport.write_report(p, [IT1])`;`ret == p` 且讀回 `== htmlreport.build_html([IT1])`。
- **AC37(空 items 仍寫合法 HTML)**:`p = tmp_path / "empty.html"`;`htmlreport.write_report(p, [])`;讀回字串 `startswith("<!DOCTYPE html>")` 且 `"沒有可顯示的案例" in` 讀回字串 且 `"總案數:0" in` 讀回字串。
- **AC38(覆寫語義)**:對同一 `p = tmp_path / "ow.html"` 先 `write_report(p, [IT1, IT2])` 再 `write_report(p, [IT2])`;讀回 `re.findall(r"<tr>", disk)` 長度 == 2(1 表頭 + 1 資料列,完全覆寫非附加)且 `"a.png" not in disk` 且 `"b.png" in disk`。

---

## 7. 與其他模組的邊界(防越權)

- **不負責**「選哪些案例、什麼順序」(那是 `filtersort` / app:本模組吃已選定的 `items`,原序輸出)。
- **不負責**讀寫 sidecar 檔或產生 `Detection`(`sidecar`/`yolo` 的事:本模組**只吃 dict**,不 import 任一實作)。
- **不負責**校驗 `verdict`/`tag`/`bbox`/`conf` 合法性(上游把關;本模組原樣帶或做純彙整 + 逸出 + 呈現格式化)。
- **不負責**產生 CSV/JSON(那是 `casepkg`:**不 import casepkg**,雖共用 item 形狀與扁平化規則,實作各自自含)。
- **不負責**渲染 ROI crop 影像、嵌入縮圖、PDF 直出(本輪只出純文字 HTML;PDF 由使用者在瀏覽器「列印成 PDF」達成;嵌圖/PDF 列 Phase 2 候選)。
- **不負責**渲染 `bbox`/`cls` 細節或 `bookmarked`/`rois` 欄(本輪報告聚焦 7 欄判讀總覽)。
- 本模組對外承諾:除 `write_report` 外皆純函式、無副作用、輸入不被 mutate、僅依賴 Python 標準庫(`html`/`os`);逸出行為(§3.2)、HTML 骨架與自含性(§3.3)、表格 7 欄與列數(§3.4)、摘要計數(§3.5)、寫讀 round-trip(§3.6)為對下游(app 匯出 UI / 使用者瀏覽器)鎖定的契約。
```
