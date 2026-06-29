# 設計:`sidecar`(M2 / Tier B — 有 I/O,需真實讀寫驗收)

> `/architect` 產物。對應 PRD `2_PO_PRD/01` §3 M2、開放問題 4(sidecar 放置 / 多 ROI 結構與座標系)。
> 本檔只定義契約與驗收標準,**不含實作**。實作由 `/pg` 寫到 `5_PG_Develop/sidecar.py`。

## 邊界 sanity check(開工前一句話)
`sidecar` 內聚一句話講得完(每張圖一份 sidecar JSON 的讀寫與欄位變更,不碰原圖),
契約只耦合檔案系統、與 `roi`(幾何)/`tagging`(篩選 predicate)解耦且不成環,可用 `tmp_path` 獨立 round-trip 驗收。
→ **可獨立設計與驗收,不需合併或再拆。** 放行本輪設計。

---

## 1. 目的 (Purpose)
為每張影像維護一份「同目錄、同檔名」的 sidecar JSON(`<name>.cvr.json`),持久化人工判讀狀態
(review_status / tags / verdict / comment / bookmark / ROIs / reviewer / timestamp),**絕不修改原始影像檔**。

---

## 2. I/O 契約 (I/O Contract)

實作於 `5_PG_Develop/sidecar.py`。測試以 `import sidecar` 取用(conftest 已把 `5_PG_Develop` 加進 `sys.path`)。
**逐字採用**以下簽名,不得增刪參數或改名:

```python
def default() -> dict
def sidecar_path(image_path) -> str          # 同目錄 <name>.cvr.json
def load(image_path) -> dict                 # 不存在 → 回 default()(不丟錯)
def save(image_path, data) -> None           # 原子寫入(先寫 tmp 再 rename)
def set_status(data, status) -> dict
def toggle_bookmark(data) -> dict
def add_tag(data, tag) -> dict
def remove_tag(data, tag) -> dict
def add_roi(data, bbox, label="", verdict="unset", comment="") -> dict
```

### 2.1 資料結構 (schema)
`default()` 回傳的 dict 形狀(欄位、型別、初值)固定如下:

| 欄位 | 型別 | 初值 | 說明 |
|------|------|------|------|
| `review_status` | `str` ∈ {`"none"`,`"need_review"`,`"done"`} | `"none"` | 判讀進度狀態 |
| `tags` | `list[str]` | `[]` | 標籤(去重、保序) |
| `verdict` | `str` | `"unset"` | 整圖判定(預設 `"unset"`=未審,與 tagging `VERDICTS[0]` 哨兵 + ROI-level verdict 預設一致) |
| `comment` | `str` | `""` | 整圖註解 |
| `bookmarked` | `bool` | `False` | 是否書籤 |
| `rois` | `list[dict]` | `[]` | ROI 清單,元素見 2.2 |
| `reviewer` | `str` | `""` | 判讀者 |
| `timestamp` | `str` | `""` | ISO 字串,由呼叫端傳入(見 §5) |

### 2.2 ROI 元素結構
`add_roi` 追加進 `rois` 的每個元素形狀固定為:

| 欄位 | 型別 | 說明 |
|------|------|------|
| `bbox` | `list[int]`,長度 4 = `[x, y, w, h]` | 來源影像像素座標;原點左上,x 向右、y 向下;w/h 為寬高 |
| `label` | `str` | ROI 標籤,預設 `""` |
| `verdict` | `str` | ROI 判定,預設 `"unset"` |
| `comment` | `str` | ROI 註解,預設 `""` |

> 座標系定案(回應開放問題 4):ROI 一律以**來源影像像素 xywh**(非正規化、非 xyxy)存放,
> 與 `viewport`/`roi` 模組的 source 座標一致;與顯示縮放、`viewer_component` 回傳座標的換算由 `viewport` 負責,sidecar 只存不算。

### 2.3 純度與不可變性約定(對 `/pg` 的硬約束)
- `default`、`sidecar_path` 以外的所有函式皆為**純函式**:不讀寫檔案、**不得呼叫 `datetime.now()` 或任何時鐘/亂數**(測試要可重現;要時間戳一律由呼叫端當參數傳入並寫進 `data["timestamp"]`,見 §5)。
- 變異類函式(`set_status`/`toggle_bookmark`/`add_tag`/`remove_tag`/`add_roi`)採 **copy-on-write**:回傳「新的 dict」,**不得就地修改傳入的 `data`**(呼叫端可安全比較前後狀態)。回傳值即新狀態,須可直接餵回下一個變異函式或 `save`。
- 僅允許依賴:Python 標準庫(`os`、`json`、`tempfile`、`copy` 等)。**不可新增 pip 依賴。**

---

## 3. 資料流 (Data Flow)

```
影像路徑 image_path
   │  sidecar_path()                同目錄、副檔名換成 .cvr.json
   ▼
<dir>/<name>.cvr.json  ──load()──►  dict(存在則解析;不存在/空 → default())
   │                                   │
   │                          set_status / toggle_bookmark /
   │                          add_tag / remove_tag / add_roi   (純函式,copy-on-write)
   │                                   ▼
   │                                new dict(呼叫端在此填入 reviewer / timestamp)
   └────────────────────save(image_path, new_dict)──► 原子寫入(tmp → os.replace)
```

- **讀路徑**:`load` 永不丟錯;缺檔、空檔、壞 JSON 都回 `default()`(見 §4),確保 UI 永遠拿得到合法形狀。
- **寫路徑**:`save` 先寫同目錄暫存檔(如 `<name>.cvr.json.<unique>.tmp`)→ `flush`+`os.replace()` 原子換名,
  避免半寫檔;原圖檔(`.png/.tif/...`)在任何路徑下都不被開啟或寫入。
- **變更路徑**:UI 事件 → 對應變異函式 → 得到新 dict → `save`。時間戳/判讀者由 app 層注入,模組本身無副作用。

---

## 4. 邊界條件與錯誤處理 (Edge Cases & Error Handling)

| 情境 | 行為(契約) |
|------|------|
| sidecar 檔不存在 | `load` 回 `default()`,**不**建檔、不丟錯 |
| sidecar 檔存在但空字串 / 壞 JSON | `load` 回 `default()`(吞掉解析錯,不丟錯;不污染 UI) |
| sidecar 為合法 JSON 但缺欄位 | `load` 以 `default()` 補齊缺欄位(回傳 dict 一定含全部 §2.1 欄位);既有欄位值保留 |
| `set_status` 收到非法 status(不在三值內) | 丟 `ValueError`(及早失敗,避免寫入壞狀態) |
| `add_tag` 加入已存在的 tag | 不重複加入;`tags` 維持去重且保序 |
| `remove_tag` 移除不存在的 tag | 視為 no-op,回傳的 dict `tags` 不變(不丟錯) |
| `toggle_bookmark` | 將 `bookmarked` 反轉(`False↔True`) |
| `add_roi` 的 `bbox` | 原樣存成長度 4 的 `[x,y,w,h]`(允許 list/tuple 輸入,存成 list);不做裁剪/clamp(那是 `roi`/`viewport` 的事) |
| `image_path` 為 `pathlib.Path` 或 `str` | 兩者皆可接受;`sidecar_path` 回傳 `str` |
| `image_path` 無副檔名(如 `foo`) | `sidecar_path` 回 `foo.cvr.json`(附加 `.cvr.json`) |
| 變異函式輸入 `data` | 不就地改;回傳新 dict(copy-on-write) |
| `save` 寫入後殘留 tmp 檔 | 不允許;成功路徑結束後同目錄不得有 `*.tmp` 殘檔 |

---

## 5. 時間戳與判讀者注入(設計備註)
模組保持純淨,因此 `timestamp` / `reviewer` **不由模組產生**。app 層的寫入慣例為:

```python
d = sidecar.load(img)
d = sidecar.set_status(d, "done")
d["reviewer"] = current_user          # app 注入
d["timestamp"] = now_iso              # app 注入(如 datetime.now().isoformat())
sidecar.save(img, d)
```

這讓所有變異函式可被 pytest 用釘死的輸入/輸出驗證,無時鐘相依。

---

## 6. Acceptance Criteria(給 `/pm` 落成 pytest;每條帶具體期望值、可驗)

> 測試置於 `4_PM_Feedback/test_sidecar.py`;`import sidecar`;檔案讀寫一律用 `tmp_path`。
> 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_sidecar.py -p no:cacheprovider --strict-markers -q`

### A. 預設與 schema
- **AC1**:`d = sidecar.default()` 回傳的 dict,`set(d.keys()) == {"review_status","tags","verdict","comment","bookmarked","rois","reviewer","timestamp"}`(剛好八個欄位,不多不少)。
- **AC2**:`default()` 各欄位初值精確等於:`d["review_status"]=="none"`、`d["tags"]==[]`、`d["verdict"]=="unset"`、`d["comment"]==""`、`d["bookmarked"] is False`、`d["rois"]==[]`、`d["reviewer"]==""`、`d["timestamp"]==""`(`verdict` 預設 `"unset"`=未審哨兵,與 tagging 一致)。
- **AC3**:`default()` 每次回傳**獨立**物件:`a=default(); b=default(); a["tags"].append("x"); assert b["tags"]==[]`(不共用可變預設)。

### B. 路徑推導 `sidecar_path`
- **AC4**:`sidecar.sidecar_path(str(tmp_path / "a" / "img.png")) == str(tmp_path / "a" / "img.cvr.json")`(同目錄、檔名主幹不變、副檔名換成 `.cvr.json`)。
- **AC5**:對 `.tif`/大寫副檔名同理:`os.path.basename(sidecar.sidecar_path("X/scan001.TIF")) == "scan001.cvr.json"`。
- **AC6**:無副檔名時附加:`os.path.basename(sidecar.sidecar_path("X/foo")) == "foo.cvr.json"`。
- **AC7**:接受 `pathlib.Path`:`sidecar.sidecar_path(tmp_path / "img.png") == sidecar.sidecar_path(str(tmp_path / "img.png"))`,且回傳型別為 `str`。

### C. load 容錯(檔案不存在 / 壞檔)
- **AC8**:目標 sidecar 不存在時 `sidecar.load(tmp_path / "missing.png") == sidecar.default()`,且**不建立任何檔案**(`os.path.exists(sidecar.sidecar_path(tmp_path / "missing.png")) is False`)。
- **AC9**:sidecar 檔內容為壞 JSON(如寫入 `"{not json"`)時,`sidecar.load(img)` 不丟例外且 `== sidecar.default()`。
- **AC10**:sidecar 檔為空字串時,`sidecar.load(img) == sidecar.default()`。
- **AC11**:sidecar 為合法但缺欄位 JSON(如只有 `{"bookmarked": true}`)時,`load` 回傳補齊全 8 欄位的 dict:`r["bookmarked"] is True` 且 `r["tags"]==[]` 且 `r["review_status"]=="none"`(既有值保留、缺者補預設)。

### D. save 真實寫入 + round-trip(I/O 模組強制)
- **AC12(round-trip)**:
  ```
  img = tmp_path / "img.png"
  d = sidecar.default(); d = sidecar.set_status(d, "done")
  d = sidecar.add_tag(d, "scratch"); d["reviewer"]="alice"; d["timestamp"]="2026-06-22T10:00:00"
  sidecar.save(img, d)
  assert sidecar.load(img) == d            # 寫出再讀回,內容完全相等
  ```
- **AC13(真實落地且為合法 JSON)**:AC12 後,`p = sidecar.sidecar_path(img)`,`os.path.exists(p) is True`,且 `json.load(open(p, encoding="utf-8"))["review_status"] == "done"`(磁碟上是可被標準 `json` 解析的 UTF-8 檔)。
- **AC14(不改原圖)**:先寫入原圖 bytes(如 `img.write_bytes(b"PNGDATA")` 並記其 `mtime`/內容),`sidecar.save(img, sidecar.default())` 後,`img.read_bytes() == b"PNGDATA"`(原圖位元組完全不變)。
- **AC15(原子寫入無殘檔)**:AC12 之後,該目錄下**沒有** `*.tmp` 殘留:`[f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []`。
- **AC16(覆寫既有)**:對同一 `img` 連續 `save` 兩次不同內容,`load` 回傳的是**最後一次**內容:第一次存 `verdict="A"`、第二次存 `verdict="B"` → `sidecar.load(img)["verdict"]=="B"`。
- **AC17(中文/Unicode 無損)**:`d=sidecar.default(); d["comment"]="刮傷-α"; sidecar.save(img,d); assert sidecar.load(img)["comment"]=="刮傷-α"`(non-ASCII 字串 round-trip 不變)。

### E. 變異函式(純函式 + copy-on-write)
- **AC18(set_status)**:`sidecar.set_status(sidecar.default(), "need_review")["review_status"] == "need_review"`。
- **AC19(set_status 非法值)**:`sidecar.set_status(sidecar.default(), "bogus")` 丟 `ValueError`(`pytest.raises(ValueError)`)。
- **AC20(set_status 不就地改)**:`base=sidecar.default(); out=sidecar.set_status(base,"done"); assert base["review_status"]=="none" and out["review_status"]=="done" and out is not base`。
- **AC21(toggle_bookmark)**:`sidecar.toggle_bookmark(sidecar.default())["bookmarked"] is True`,再 toggle 一次 → `False`:`sidecar.toggle_bookmark(sidecar.toggle_bookmark(sidecar.default()))["bookmarked"] is False`。
- **AC22(add_tag 基本)**:`sidecar.add_tag(sidecar.default(), "x")["tags"] == ["x"]`。
- **AC23(add_tag 去重保序)**:`d=sidecar.default(); d=sidecar.add_tag(d,"a"); d=sidecar.add_tag(d,"b"); d=sidecar.add_tag(d,"a"); assert d["tags"]==["a","b"]`(重複不加、原順序保留)。
- **AC24(add_tag 不就地改)**:`base=sidecar.default(); out=sidecar.add_tag(base,"a"); assert base["tags"]==[] and out["tags"]==["a"]`。
- **AC25(remove_tag)**:`d=sidecar.add_tag(sidecar.default(),"a"); d=sidecar.add_tag(d,"b"); assert sidecar.remove_tag(d,"a")["tags"]==["b"]`。
- **AC26(remove_tag 不存在為 no-op)**:`d=sidecar.add_tag(sidecar.default(),"a"); assert sidecar.remove_tag(d,"zzz")["tags"]==["a"]`(不丟錯、不變)。

### F. ROI
- **AC27(add_roi 預設值)**:
  ```
  d = sidecar.add_roi(sidecar.default(), [10, 20, 30, 40])
  assert d["rois"] == [{"bbox":[10,20,30,40], "label":"", "verdict":"unset", "comment":""}]
  ```
- **AC28(add_roi 自訂欄位)**:`sidecar.add_roi(sidecar.default(), [1,2,3,4], label="L", verdict="bad", comment="c")["rois"][0] == {"bbox":[1,2,3,4],"label":"L","verdict":"bad","comment":"c"}`。
- **AC29(add_roi 多筆保序)**:對同一 data 連加兩個 ROI(bbox `[0,0,1,1]` 再 `[5,5,2,2]`)→ `len(d["rois"])==2` 且 `d["rois"][1]["bbox"]==[5,5,2,2]`。
- **AC30(add_roi bbox 存成 list 長度 4)**:傳入 tuple `(1,2,3,4)` 時,`d["rois"][0]["bbox"] == [1,2,3,4]` 且 `type(d["rois"][0]["bbox"]) is list`。
- **AC31(add_roi 不就地改)**:`base=sidecar.default(); out=sidecar.add_roi(base,[0,0,1,1]); assert base["rois"]==[] and len(out["rois"])==1`。
- **AC32(ROI round-trip)**:`d=sidecar.add_roi(sidecar.default(),[10,20,30,40],label="L"); sidecar.save(img,d); assert sidecar.load(img)["rois"]==d["rois"]`(ROI 經磁碟 round-trip 不變)。

### G. 組合行為(端到端,模擬一輪判讀)
- **AC33(完整一輪)**:
  ```
  img = tmp_path / "wafer.tif"
  d = sidecar.load(img)                      # 不存在 → default
  d = sidecar.set_status(d, "need_review")
  d = sidecar.toggle_bookmark(d)
  d = sidecar.add_tag(d, "defect")
  d = sidecar.add_roi(d, [100,100,50,50], label="crack", verdict="bad")
  d["reviewer"]="bob"; d["timestamp"]="2026-06-22T12:00:00"
  sidecar.save(img, d)
  r = sidecar.load(img)
  assert (r["review_status"]=="need_review" and r["bookmarked"] is True
          and r["tags"]==["defect"] and r["reviewer"]=="bob"
          and r["timestamp"]=="2026-06-22T12:00:00"
          and r["rois"]==[{"bbox":[100,100,50,50],"label":"crack","verdict":"bad","comment":""}])
  ```
- **AC34(可重現 / 無隱藏時鐘)**:在不手動設定 `timestamp` 的情況下,`d=sidecar.add_tag(sidecar.set_status(sidecar.default(),"done"),"t"); assert d["timestamp"]==""`(變異函式不偷寫時間戳,結果與呼叫時刻無關)。

---

## 7. 對下游的影響(契約鎖定點)
- `casepkg`(M3)會 `sidecar.load` 每張圖彙整判定 → CSV/JSON;依賴本檔 §2.1 欄位名與 §2.2 ROI 形狀穩定。
- `tagging`(M2,Tier A)的篩選 predicate 吃的就是這份 dict(`tags`/`verdict`/`bookmarked`/`review_status`),欄位名須與本檔一致。
- `roi`(M2,Tier A)負責 ROI 幾何/crop;sidecar 只存 `[x,y,w,h]` 源座標,不做幾何運算。
