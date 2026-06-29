# 設計:viewer_ux(M6 / Tier B GUI 整合 — 縮圖/viewer UX 回饋輪)

> `/architect` 模組設計。**Tier B GUI 整合**:動 `5_PG_Develop/viewer_component/index.html`、`5_PG_Develop/viewer.py`、`5_PG_Develop/app.py`,新增宣告式縮圖元件 `thumbwall_component/`。
> **無 Python 單元 gate**(本變更不產出可純邏輯驗收的新函式;沿用既有 imgio/overlay 的單元覆蓋)。**機器判綠 = 真實 playwright E2E 全綠**(`4_PM_Feedback/test_app_e2e.py` 擴充或新增 `test_viewer_ux_e2e.py`,標 `@pytest.mark.e2e`)+ 像素級項目以 `[截圖實證]` 人/視覺驗收。
> 上游:User 已逐輪鎖定的 7 點需求(見 §1)。
> 相依資料形狀:`Detection = {"bbox":[x,y,w,h]絕對像素, "cls":str, "conf":float}`(yolo 產生、overlay 消費);本設計**只傳遞、不新造**這個形狀。
> 下游:`/pm` 依本檔 AC 落成 E2E;`/pg` 依 §3/§4 契約改 HTML/JS/py。

---

## 開工前 sanity check(切分是否成立、是否觸發反向閘門)

7 點需求全部落在「既有 viewer 元件 + 縮圖牆 + sidebar→主頁 控制搬遷」三處,無新純邏輯演算法、無新 I/O 模組;繪框複用 `overlay.draw`、縮圖複用 `imgio.thumbnail`/`to_png_bytes`、真值複用 `imgio.value_at`。切分成立,**不觸發反向閘門**。

一處**已知的物理限制必須誠實標註而非當缺陷退件**:hover 即時 RGB 採「client 端零 round-trip 取樣」,代價是 hover RGB = **8-bit 顯示值**(`to_display_rgb` 後的 data URL 像素),**非 16-bit/原始真值**;真值仍只能靠點擊走伺服器 `value_at`。瓦片(tiles)模式瀏覽器端**無單一全圖**可取樣 → hover RGB 必須**優雅降級**(只顯示 x,y+zoom)。這兩點是設計決策、列為 AC 與語義界線(§5、§6),不是 bug。

---

## 1. 目的與 7 點需求(逐點對應 AC)

讓 review 者「看得懂、點得到、量得準」:

| # | 需求 | 落點 | 主要 AC |
|---|------|------|---------|
| 1 | 點圖不觸發原生選圖/拖曳 | index.html(CSS + 事件) | AC1 |
| 2 | 最大放大上限(可看清單像素、但有界) | index.html(OSD `maxZoomPixelRatio`) | AC2、AC3 |
| 3 | hover 即時 x,y + RGB(client 零 round-trip;tiles 降級) | index.html(offscreen canvas 取樣) | AC4、AC5、AC6 |
| 4 | HUD 顯示推薦組合(檔名+序號/尺寸·bit·通道/zoom%/hover(x,y)+RGB/游標下框 class·conf) | viewer.py 新 `meta`/`dets` 參數 + index.html HUD | AC7、AC8、AC9、AC10 |
| 5 | 整張縮圖可點→載進主 viewer | 新 `thumbwall` 宣告式元件 + app.py | AC11、AC12、AC13 |
| 6 | 縮圖畫 YOLO 框(縮放疊框) | app.py `_thumb` 階段複用 `overlay.draw` | AC14、AC15 |
| 7 | YOLO 框總開關移到最上面(同管縮圖與主 viewer) | app.py(`st.title` 之下) | AC16、AC17、AC18 |

---

## 2. 涉及檔案與對外契約變更(逐字採用,不得更動簽名)

### 2.1 `5_PG_Develop/viewer.py` — `osd_viewer` 新簽名

```python
def osd_viewer(image_url: str = None, rois=None, tiles=None, height: int = 600,
               key: str = "cv_viewer",
               meta: dict = None, dets=None, max_zoom_pixel_ratio: float = 24.0):
    """新增三參數,皆可選、預設保留 M5 行為(meta=None/dets=None → HUD 退回舊版座標列)。
    meta:dict|None  HUD 頂列要顯示的影像中繼資料(形狀見 §2.1a),不影響取樣。
    dets:list|None  「過濾後」的偵測 list(形狀=Detection;app 端已套 conf/class 篩選),
                    供『游標落在框內顯示 class·conf』與(未來)client 端框內判定;data url 已燒框,
                    dets 只供 HUD 文字命中,不再次繪製。
    max_zoom_pixel_ratio:float  傳給 OSD 的 maxZoomPixelRatio(放大上限;契約預設 24.0,見 §3.2)。
    回傳值形狀『不變』(仍是最近一次事件 dict 或 None;hover 不回傳事件、不 round-trip)。"""
```

> **回傳契約不變**:仍只回 `{"type":"click",...}` / `{"type":"roi",...}` / `None`。**hover 不產生 component value**(避免 Streamlit rerun 風暴)。

#### 2.1a `meta` dict 形狀(viewer.py → 元件 `args.meta`)

```python
meta = {
    "name": str,        # 檔名,如 "lot42_frame_000.png"
    "idx1": int,        # 1-based 序號(= ss.idx + 1)
    "total": int,       # 總張數
    "w": int, "h": int, # 影像寬高(像素)
    "bit": int,         # 位元深度(8/16)
    "channels": int,    # 1=Gray、3=RGB
}
```

> 缺鍵或 `meta=None` → HUD 對應欄位省略(不拋例外)。`channels` 由 app 既有 `_meta()` 第四元素提供。

### 2.2 新元件 `5_PG_Develop/thumbwall_component/index.html` + `thumbwall.py`(宣告式,無 build,無第三方依賴)

**選型取捨(釘死)**:沿用本專案既有「`declare_component` + 手寫 HTML」慣例,**不**引入 `streamlit-image-select` 等第三方套件(理由:① 與 viewer 一致、零新依賴、可離線;② 完全掌控 postMessage 協定與徽章/框語義;③ E2E 可控)。stock 替代(每張一個 `st.button` + 其下 `st.image`)即現狀,**已被 User 否決**(「看不懂的索引鈕 N」)——本元件取代之。

`thumbwall.py` 包裝簽名(逐字採用):

```python
def thumbwall(items, selected: int = 0, height: int = 620, key: str = "thumbwall"):
    """渲染可點縮圖牆。回傳被點的縮圖 index(int)或 None(本 run 無點擊)。
    items: list[dict],每筆 = {
        "img":   str,   # 縮圖 data URL(已含框,見 §3.6;由 app 用 imgio.to_data_url 產生)
        "label": str,   # 角標文字,如 "3"
        "mark":  str,   # ⭐/✓ 標記(可空)
        "nd":    int,   # 偵測框數(0 → 不顯示徽章)
    }
    selected: 目前選中的 index(高亮邊框用)。
    """
```

#### 2.2a thumbwall 元件協定(args / 回傳值形狀)

- **args(Python → JS,`args.*`)**:`items`(上表 list)、`selected`(int)、`height`(int)。
- **回傳值(JS → Python,`setComponentValue`)**:`{"index": int, "n": int}`(`n` 單調遞增的事件序號,讓 app 用「`n > last_thumb_n`」判斷是否本次新點擊,語義與 viewer 的 `n` 一致,避免 rerun 重複觸發)。app 端讀 `index` 設 `ss.idx`。
- 點擊任一縮圖的可點區(整張 `<img>` + 角標)即 postMessage 回該 index;**整張圖可點**(滿足 #5)。

### 2.3 `5_PG_Develop/app.py` `_thumb` 行為變更(#6)

`_thumb` 由「純縮圖」變成「縮圖 +(可選)縮放疊框」。**新簽名(逐字採用)**:

```python
@st.cache_data(show_spinner=False)
def _thumb(path, max_px=130, dets=None, show=False, conf_thr=0.0, classes=None):
    """show=False 或 dets 空 → 行為與 M5 完全相同(純縮圖,向後相容)。
    show=True 且 dets 非空 → 在縮圖座標系上複用 overlay.draw 疊『過濾後』框:
      1. thumb = imgio.thumbnail(_array(path), max_px)  # HxWx3 uint8(顯示縮圖)
      2. 縮放比例 sx=thumb_w/orig_w, sy=thumb_h/orig_h;
         把每筆 det 的 bbox=[x,y,w,h] 乘上 (sx,sy) → 縮圖座標 bbox(見 §3.6 釘死換算)
      3. overlay.draw(thumb, scaled_dets, thickness=1, conf_threshold=conf_thr,
                      classes=classes, draw_label=False)  # 縮圖不畫文字標籤(太小)
      4. return imgio.to_png_bytes(...)  # 或 to_data_url 供 thumbwall
    dets 進 cache_data 的 key:傳『可雜湊投影』(見 §3.6 註),避免 unhashable list 破 cache。"""
```

> **契約相容性**:`_thumb(path)`(舊呼叫法)行為**逐位元組不變**(`show=False` 預設)。新增參數皆可選。

### 2.4 控制搬遷(#7)

`show_overlay` checkbox 與 `conf_thr` slider **從 sidebar §「模型疊圖」搬到主頁 `st.title("🔬 CV Review Workbench")` 之下**(三欄牆之前),成為**單一真相**,同管縮圖牆(`_thumb(..., show=show_overlay, conf_thr=conf_thr)`)與主 viewer(既有 `overlay.draw` 與新 `dets` 傳參)。`overlay_classes` 文字輸入**可留 sidebar 或一併上移**(實作者擇一,AC 只釘 checkbox + slider 在頂部)。sidebar 原「模型疊圖」段移除重複控制(避免雙真相)。

---

## 3. 資料流與機制(虛擬步驟,非可執行實作)

### 3.1 #1 禁原生選圖/拖曳(index.html)
在 `#osd`(及其 canvas)套 CSS:`user-select:none; -webkit-user-select:none; -webkit-user-drag:none;`,並對 `dragstart` / `selectstart` 事件 `preventDefault()`。目標:在影像上按下拖曳只觸發 OSD 平移 / Shift-ROI,**不**出現瀏覽器藍色選取或 ghost image 拖影。OSD 既有 `gestureSettingsMouse` 不變。

### 3.2 #2 放大上限(index.html / OSD)
`buildViewer` 的 OSD 設定加 `maxZoomPixelRatio: <args.max_zoom_pixel_ratio || 24>`。**釘死預設 = 24.0**:語義為「1 影像像素最多放大成 24×24 螢幕像素」,足以看清單一像素方塊(肉眼可辨色塊邊界),但**有界**(滾到底就停,不再放大)。OSD 內部會把此值換成 `viewport.getMaxZoom()` 上限;HUD 的 zoom% 以 `viewport.getZoom(true)` 顯示,封頂後不再增長。

### 3.3 #3 hover 即時 x,y + RGB(client 零 round-trip,單圖模式)
1. `initViewer(imageUrl, ...)` 載圖時,另把 `imageUrl`(data URL)畫到一個 **offscreen `<canvas>`**(原始影像像素尺寸),取得 `CanvasRenderingContext2D`;影像 onload 後標記 `sampleReady=true`。
2. `mousemove`:用既有 `imgPtFromEvent(e)` 算出影像座標 `(x,y)`(已有,§index.html L36)。
3. 若 `sampleReady && 0<=x<W && 0<=y<H`:`ctx.getImageData(x,y,1,1).data` → `[r,g,b,a]`,組 HUD 的 `RGB=(r,g,b)`。界外 → 不顯示 RGB(只 x,y)。
4. **零 round-trip**:全程瀏覽器端,不 postMessage、不 rerun。hover RGB = **8-bit 顯示值**(來源是 `to_display_rgb` 後的 data URL,見 §6 界線)。

### 3.4 #3 瓦片模式降級(tiles)
`initTiledViewer` 路徑**無單一全圖** → `sampleReady=false`,`mousemove` 只顯示 `(x=…, y=…) zoom=…%`,**不顯示 RGB**(HUD 明示「RGB:瓦片模式不可用,點擊取真值」或省略 RGB 欄)。此為 #3 的優雅降級,列 AC6。

### 3.5 #4 HUD 版面(index.html `#hud`)
HUD 由「單行座標」升級為**多欄推薦組合**(同一 `#hud` 容器、`pointer-events:none` 不擋滑鼠)。版面示意(文字、非實作):

```
lot42_frame_000.png · 3/8        ← name · idx1/total（來自 args.meta）
1024×768 · 16-bit · RGB · 38%    ← w×h · bit-bit · 通道 · zoom%
(x=512, y=311)  RGB=(128, 64, 30)← hover 即時座標 + 8-bit 顯示 RGB（單圖）
▸ defect 0.87                    ← 游標落在某『過濾後』框內 → 顯示其 cls·conf（否則此列空）
```

- meta 列來自 `args.meta`;缺 meta → 退回 M5 舊版單行(向後相容,AC7 容許「至少含檔名與序號」)。
- zoom% = `(viewport.getZoom(true) * <基準>)` 取整;實作可用 `imageToViewport` 比例換算成「相對 100%=fit」或「相對原尺寸」百分比,**AC 只要求是隨縮放單調變化的整數%字串**(避免脆弱)。
- **游標下框命中(#4 末項)**:JS 端對 `args.dets`(過濾後 list)逐筆判 `x∈[bx,bx+bw) && y∈[by,by+bh)`(影像座標、半開區間,與 overlay 一致);命中多框時顯示**最後一筆**(或面積最小者,實作擇一,AC 不釘選擇策略,只釘「在框內顯示某 cls·conf、在框外不顯示」)。

### 3.6 #6 縮圖疊框換算(app.py `_thumb`)
- 縮圖長邊縮到 `max_px`(`imgio.thumbnail` 只縮不放、auto window/level)。設縮圖實際尺寸 `(th, tw)`、原圖 `(h, w)`。
- 每筆過濾後 det 的 `bbox=[x,y,w,h]` 換算:`sx=tw/w, sy=th/h`;`scaled=[round(x*sx), round(y*sy), max(1,round(w*sx)), max(1,round(h*sy))]`(寬高至少 1 像素,避免縮成 0 不可見)。
- `overlay.draw(thumb, scaled_dets, thickness=1, draw_label=False)`(縮圖不畫文字)。**複用 overlay**,不另寫繪框邏輯。
- **cache_data 可雜湊性**:`dets` 是 list[dict](unhashable)。`_thumb` 對外仍接 list,但 `@st.cache_data` 的 key 用**投影成 tuple** 的輔助(如 `tuple((d["cls"], round(d["conf"],3), tuple(map(int,d["bbox"]))) for d in dets)`)或把疊框算成獨立 cache 函式 `_thumb_with_dets(path, max_px, dets_key, ...)`;實作擇一,**契約只要求**:相同輸入相同輸出、開關切換時縮圖正確更新、不因 unhashable 崩潰。

### 3.7 #5 + #7 app.py 串接(縮圖牆 / 頂部控制)
1. 頂部(`st.title` 之下):`show_overlay = st.columns(...)[..].checkbox("顯示偵測框", value=True)`、`conf_thr = ...slider("信心門檻", 0.0,1.0,0.25,0.05)`。**label 文字釘死**=「顯示偵測框」(供 E2E 定位,AC16)。
2. 縮圖牆(`with left`):組 `tw_items`(每筆 `img`=`_thumb(path, dets=it["detections"], show=show_overlay, conf_thr=conf_thr, classes=overlay_classes)` 轉 data URL、`label`=`str(i+1)`、`mark`、`nd`),呼叫 `clicked = thumbwall(tw_items, selected=ss.idx, key="thumbwall")`;`clicked` 是新點擊 index → `ss.idx=clicked; st.rerun()`。**移除**逐張 `st.button` + `st.image` 寫法。
3. 主 viewer:`osd_viewer(url, rois=..., height=600, key=f"viewer_{ss.idx}", meta={...}, dets=kept)`(`kept`=既有 `overlay.filter_detections(...)` 結果),`max_zoom_pixel_ratio` 用預設或常數。

---

## 4. 邊界條件與錯誤處理

a. **meta=None / dets=None**(舊呼叫法或無偵測):HUD 退回 M5 行為(座標列);viewer 不拋例外。`osd_viewer` 三新參數皆有預設。
b. **tiles 模式 hover**:無全圖 → 不取樣 RGB(§3.4),只座標+zoom;**不**因取樣失敗拋錯。
c. **hover 界外**(x<0 / x>=W / y<0 / y>=H):不顯示 RGB(顯示 x,y 仍可為夾界值或省略,實作擇一),不 `getImageData` 越界。
d. **空偵測 / 全被濾掉**:縮圖與 HUD 都「無框」;`_thumb(show=True, dets=[])` 等同純縮圖(複用 overlay 的「空 dets → 逐像素等於輸入」不變量);HUD 框命中列空。
e. **縮圖 bbox 縮成 0**:寬/高 `max(1,…)` 保底(§3.6),避免不可見。完全在縮圖外的框由 overlay 夾界只畫可見部分(複用既有 overlay 邊界語義,不另處理)。
f. **thumbwall 連點 / rerun**:用 `n` 單調序號去重(§2.2a),`n <= last_thumb_n` 視為舊事件忽略,避免無限 rerun。
g. **Gray(channels=1)影像**:`_display_rgb` 已轉 3 通道顯示;hover RGB 三分量會相等(灰)——HUD 照常顯示 `RGB=(g,g,g)`,語義正確(顯示值),不特判。
h. **16-bit 影像**:hover RGB 是 `to_display_rgb`(window/level)後的 8-bit 顯示值,**非原始 16-bit**;HUD 須標 hover=顯示值(§6、AC9 容許),真值仍靠點擊 `value_at`。
i. **maxZoomPixelRatio 未傳**:用元件內預設 24(§3.2),不依賴 app 必傳。
j. **無 overlay_classes**(None):縮圖與 HUD 不做 class 篩(全顯),與 overlay 既有語義一致。

---

## 5. Acceptance Criteria(每條標 [E2E可斷言] / [截圖實證])

> E2E 入口(沿用既有 conftest `app_server` + playwright `page`):`cd C:/code/claude/CV_Viewer && pytest 4_PM_Feedback/test_app_e2e.py -m e2e -v`(或新增 `test_viewer_ux_e2e.py`)。viewer canvas 在巢狀 iframe(定位法見既有 `test_app_e2e.py` L17-30)。`[E2E可斷言]`=headless 可由 DOM/文字/導覽/可見性斷言;`[截圖實證]`=像素級渲染,headless 難精準,需截圖人/視覺驗。

**#1 禁原生選圖/拖曳**
- **AC1** `[截圖實證]`(可加 E2E 代理):在主 viewer canvas 上做 `mousedown→mousemove→mouseup` 拖曳後,頁面**無原生文字選取**(`window.getSelection().toString() === ""` 可由 E2E 在該 frame 斷言為 **[E2E可斷言] 代理**);ghost-image 拖影之不出現屬 [截圖實證]。

**#2 放大上限**
- **AC2** `[E2E可斷言]`:OSD 設定含 `maxZoomPixelRatio`(可由 frame 內 `viewer.viewport.getMaxZoom()` 為**有限數**斷言,或對 viewer 連續 `zoomBy` 多次後 `getZoom()` **收斂不再增長**)。
- **AC3** `[截圖實證]`:放到最大時單一像素呈可辨識色塊(看得清像素方塊),且**不能再放大**(視覺確認封頂)。

**#3 hover x,y+RGB(單圖)與瓦片降級**
- **AC4** `[E2E可斷言]`:單圖模式對 canvas 派發 `mousemove` 後,HUD(frame 內 `#hud` 文字)**同時含 `x=` 與 `RGB`**(字串存在即可,不釘數值)。
- **AC5** `[截圖實證]`:HUD 顯示的 RGB **數值正確**對應游標下顯示像素(像素級,需人對照)。
- **AC6** `[E2E可斷言]`:瓦片(大圖)模式 hover 時 HUD 含 `x=`/`zoom` **但不含 `RGB`**(降級;若大圖樣本難在 E2E 構造,退為 [截圖實證])。

**#4 HUD 推薦組合**
- **AC7** `[E2E可斷言]`:HUD 文字含**目前檔名**(如 `cur['name']`)與**序號**(形如 `N/總數`,如 `1/8`)。
- **AC8** `[E2E可斷言]`:HUD 文字含**尺寸與位元/通道**(形如 `1024×768`、`-bit`、`RGB`/`Gray` 其一可斷言)與 **zoom%**(含 `%`)。
- **AC9** `[E2E可斷言]`:HUD 對 16-bit 樣本標示 hover RGB 為**顯示值**語義(HUD 或 caption 含明示文字;真值靠點擊不變——既有 📍 `value_at` 行為仍綠)。
- **AC10** `[截圖實證]`(+E2E 代理):游標移入某偵測框內時 HUD 出現該框 `cls conf`(如 `defect 0.87`);移到框外該列消失。E2E 代理:在已知有框的樣本上 hover 框中心後 HUD 文字含該樣本某 `cls` 字串。

**#5 整張縮圖可點 → 載入主 viewer**
- **AC11** `[E2E可斷言]`:縮圖牆渲染為**可點 `<img>`**(thumbwall iframe 內 `img` count ≥ 縮圖數;非 `st.button`「N」)。
- **AC12** `[E2E可斷言]`:點第 2 張縮圖後,主進度文字變為 `2/<總數>`(沿用既有 `imageset.progress`,如 `2 / 8`),且主 viewer canvas 仍可見(切換成功、不崩)。
- **AC13** `[E2E可斷言]`:既有 mark/徽章語義保留 —— 對有 `nd>0` 的縮圖,thumbwall 內可見偵測數徽章文字(如含 `🟥` 或數字);bookmark/reviewed 的 `⭐`/`✓` 標記可見。

**#6 縮圖畫 YOLO 框**
- **AC14** `[截圖實證]`:`show_overlay=True` 時,有偵測的縮圖上**疊出框**(縮放到縮圖尺寸、顏色依 class);`show_overlay=False` 時縮圖**無框**(純縮圖)。
- **AC15** `[E2E可斷言]` 代理:切換頂部「顯示偵測框」checkbox 後,thumbwall 縮圖 `img` 的 `src`(data URL)**改變**(off→on 內容不同;代理「有/無框」差異,headless 可斷 src 變更而非肉眼判框)。

**#7 總開關移到最上面、同管兩處**
- **AC16** `[E2E可斷言]`:**主頁 `st.title` 之下、三欄牆之前**存在 label=「顯示偵測框」的 checkbox 與「信心門檻」slider(DOM 順序/位置可斷言其在 sidebar 外、在 viewer 之上)。
- **AC17** `[E2E可斷言]`:sidebar **不再**有重複的「顯示偵測框」checkbox(單一真相;sidebar 內該 label 計數為 0)。
- **AC18** `[E2E可斷言]`:關閉頂部「顯示偵測框」後,**主 viewer**燒框消失(主 viewer 影像 data URL 改變,代理 `kept` 過濾;既有 caption「顯示 k/n 框」之 k 變 0 亦可斷言)**且**縮圖牆同步無框(AC15 src 變更同因)——一個開關同管兩處。

> **回歸不破**:既有 `test_app_loads_viewer_and_navigates`(載入/進度/canvas/下一張)須**持續綠**;本批 AC 為增量,不得改既有契約檔(`3_`/`4_` 不被竄改,gate 仍稽核)。

---

## 6. 語義界線(誠實標註,防 false-green 與誤解)

- **hover RGB = 8-bit 顯示值,非真值。** 來源是 `to_display_rgb`(window/level)後餵入 data URL 的瀏覽器像素;對 16-bit / 特殊位元深影像,hover 顯示的不是原始量測值。**真值唯一來源 = 點擊**(走伺服器 `imgio.value_at(原始陣列, x, y)`,既有 📍 行為不變)。HUD/caption 必須讓使用者分得清「hover=快速顯示值、click=精確真值」。
- **瓦片(大圖)模式無 client 全圖** → hover **不提供 RGB**(只 x,y+zoom);這是 #3 的優雅降級,非缺陷。大圖要量真值仍靠點擊。
- **放大有界**(`maxZoomPixelRatio`)是刻意:看得清單像素即足,不需無限放大;封頂後 zoom% 不再增長為正常。
- **縮圖框是「縮放後的近似視覺提示」**:縮圖座標四捨五入、寬高保底 1px,**不**用於量測,只為「這張有沒有框、框在哪一帶」的快速掃描;精確框幾何看主 viewer。
- **dets 傳入元件只供 HUD 文字命中**:主 viewer 影像 data URL 已由 `overlay.draw` 燒框,元件**不重複繪製**;避免「燒框 + 元件再畫」雙重疊。

---

## 7. 與其他模組的邊界(防越權)
- **不重寫**繪框/篩選邏輯:縮圖與(若未來需要)任何框繪製一律複用 `overlay.draw`/`filter_detections`;本變更**不**改 `overlay` 契約。
- **不改** `imgio` / `yolo` / `sidecar` 契約:只**呼叫** `thumbnail`/`to_display_rgb`/`to_data_url`/`to_png_bytes`/`value_at` 與既有 `Detection` 形狀。
- **不碰** `conftest.py` / `fixtures/` / `verify/` / `.unet/`(PM 擁有測試基建;本檔只描述 E2E 需求,落成由 /pm)。
- 本變更對外承諾:`osd_viewer` 新參數**全可選且向後相容**;`_thumb` 舊呼叫法**逐位元組不變**;新 `thumbwall` 為**新增**元件,不破壞既有頁面其他區塊;**無 Python 單元 gate,機器判綠 = playwright E2E 全綠**(像素項 [截圖實證] 人/視覺驗收)。
