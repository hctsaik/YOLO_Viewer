# 設計:viewer_workbench_redesign(M7 / Tier B GUI 大改 — Viewer-First UI/UX 重設計)

> `/architect` 模組設計。**Tier B GUI 整合大改**:動 `5_PG_Develop/app.py`、`5_PG_Develop/viewer_component/index.html`、`5_PG_Develop/viewer.py`、`5_PG_Develop/thumbwall_component/index.html`、`5_PG_Develop/thumbwall.py`,**新增** linked-viewport 比較元件(`compare_component/` + `compare.py`,M7c)。
> **無 Python 單元 gate**(本變更不產出可純邏輯驗收的新函式;繪框/篩選/比較演算法一律複用既有 overlay/framecompare/sidecar/tagging)。**機器判綠 = 真實 playwright E2E 全綠 + 截圖實證 + 效能量測**(`4_PM_Feedback/test_viewer_workbench_e2e.py`、`@pytest.mark.e2e`),像素級項以 `[截圖實證]` 視覺驗收。
> 上游:User 用 /loop 多 agent 收斂出版面、裁決「都要做」=全範圍;**生死點 spike 已 PASS(5 條全綠 + 對照組)**,鍵盤橋 + 固定 key viewer + zoom/pan 保存物理可行(見 `spike/kbd_component/index.html`、`spike/kbd_spike.py`)。本設計據此採用,不再當風險重議。
> 相依資料形狀(沿用,不新造):`Detection = {"bbox":[x,y,w,h]絕對像素, "cls":str, "conf":float}`;`verdict ∈ {"unset","true_defect","false_alarm","reflection"}`(= `tagging.VERDICTS`);`review_status ∈ {"none","need_review","done"}`(= sidecar `_LEGAL_STATUS`);`bookmarked: bool`。
> 下游:`/pm` 依本檔 AC 落成 E2E + 效能斷言;`/pg` 依 §3/§4 契約改 HTML/JS/py、跑 E2E 到綠。

---

## 0. 開工前 sanity check(切分成立、是否觸發反向閘門)

全範圍落在「既有 viewer 元件 + 縮圖牆 + app.py 版面骨架 + 新增一個 linked compare 元件」四處,無新純邏輯演算法、無新 I/O 契約。生死點(固定 key viewer 跨 rerun 存活 / 鍵盤 nav / 焦點不吃首鍵 / zoom·pan 跨切張保存)**已由 spike 實證物理可行**。切分成立,**不觸發反向閘門**。

三處必須誠實標註而非當缺陷處理的物理界線(列 §6 語義界線,非 bug):
- **autosave 並非「絕對零遺失」**:Streamlit widget→session_state 的回寫有 rerun 邊界;設計採「切張前 flush 未存變更 + 改值即時寫」雙保險,但 user 在「改值的同一 run 內直接關瀏覽器」這種極端情形不在保證內(見 §3.5)。
- **hover RGB = 8-bit 顯示值,非真值**(沿用 M6 §6 界線,點擊才走 `value_at` 取真值);本次版面位移不改此語義。
- **DZI 主 viewer 自動瓦片化(M7c-AC)為「評估後可能誠實降級」項**:若量測到「建金字塔 + data URL 編碼」成本使切張 P95 超門檻,則維持 M5 的手動 DZI 開關(工具台內),設計明文允許此降級(見 §3.9 / M7c-AC8 判準)。

---

## 1. 目的、收斂版面、與 User-role agent 反覆未滿足項

### 1.1 收斂版面(採用)— Viewer-First 單舞台 + 召喚式抽屜

```
┌──────────────────────────────────────────────────────────────────────┐
│ Command Bar(全寬一行,薄)                                               │
│  ⟵  ⟶ │ [N]/total │ 📄 name · 偵測N框 │ 🔎篩選 🚩漏檢[2] 🧰工具台 ⬇匯出 ⚙資料源│
├──────────┬───────────────────────────────────────────────┬────────────┤
│ 縮圖牆     │  主 viewer(最大化,height 由 JS 量視窗高動態給)    │  判定 Rail  │
│(可收 0 寬)│  [固定 key,跨 rerun 不 remount]                  │ (可收 0 寬)│
│  ▤ ▤ ▤   │                                                │ verdict     │
│  ▤ ▤ ▤   │                                                │ status      │
│  (虛擬化:  │                                                │ bookmark    │
│   只算可視 │                                                │ tags        │
│   窗+緩衝) │                                                │ comment     │
│          ├───────────────────────────────────────────────┤ ROIs        │
│          │ viewer-footer(薄,常駐):                          │            │
│          │  ☑顯示偵測框 │ 信心門檻━━●━ 0.25 [−][+] │ 顯示N/總N │ │            │
│          │  │ 最後點擊 (x,y)=值 │ undo 可撤 3 筆 [u]            │            │
└──────────┴───────────────────────────────────────────────┴────────────┘
召喚層(預設不渲染、0 計算):🧰工具台 expander + st.tabs[比較|相似|聚類|DZI|漏檢|匯出]
收合 sidebar:篩選 / 排序 / 資料源
```

- **Stage 佔 ~85% 高度**:主 viewer height 由元件端 JS 量 `window.innerHeight` 經 `setFrameHeight` 動態回報(預設 ~720,而非 M6 固定 600)。
- **召喚式**:次要功能(比較/相似/聚類/DZI/漏檢/匯出)收進**單一**「🧰工具台」`st.expander` + `st.tabs`;未展開時其重函式 **0 次呼叫**(§3.8 計數器驗證)。篩選/排序/資料源留收合 `st.sidebar`。

### 1.2 User-role agent 反覆未滿足項 → AC 對應表

| # | 未滿足項 | 落點 | 切片 / 主要 AC |
|---|----------|------|----------------|
| 1 | verdict 一等熱鍵 1/2/3;r 循環 status、b bookmark(別把流程狀態冒名成 verdict) | index.html keydown + app nav 協定 | M7b-AC2、AC3 |
| 2 | 鍵盤連切 ←/→、j 聚焦跳頁;焦點不被 number_input 吃 | index.html keydown + 焦點守衛 | M7b-AC1、AC9 |
| 3 | 信心門檻常駐 footer + 細微調(step 0.01、−/+ 快跳)、即時反映疊框與「顯示N框」 | app footer + viewer dets/draw | M7a-AC5、M7b-AC8 |
| 4 | 切張自動存 + 改值入 undo 軌跡 | app autosave + undo model | M7b-AC4、AC5 |
| 5 | 跨圖 undo(跳回那張+還原值+toast、多步、footer 顯示可撤筆數) | app undo stack | M7b-AC6、AC7 |
| 6 | linked-viewport 比較(並排+閃爍、沿用主 viewer zoom/pan、一鍵可達) | 新 compare 元件 | M7c-AC1、AC2 |
| 7 | 縮圖牆虛擬化(只算可視窗+緩衝、改門檻不重建整牆、per-image 成本可量測) | thumbwall 元件 + app | M7c-AC3、AC4、AC5 |
| 8 | 收合狀態全域持久(縮圖牆/Rail 收合旗標跨圖不重置) | app session_state | M7a-AC4 |
| 9 | 窄載體(nativeApp iframe)RWD(width<X → Rail 收成底部 strip) | app RWD 斷點 | M7c-AC6 |
| 10 | DZI 大圖自動瓦片(夠大自動,無感) | viewer 自動瓦片門檻 | M7c-AC7、AC8 |
| 11 | HUD 語義界線保留(hover=8-bit 顯示值、click=真值)在新版面仍清楚 | viewer HUD + footer | M7a-AC6 |
| 12 | 判定單一真相(Rail 與任何 popover 綁同一 session_state + 同一 undo 軌跡) | app verdict 單一真相 | M7b-AC10 |

---

## 2. 涉及檔案與對外契約變更(逐字採用,不得更動簽名)

### 2.1 `viewer.py` — `osd_viewer` 新增 zoom/pan 還原 + 鍵盤 nav 參數

```python
def osd_viewer(image_url: str = None, rois=None, tiles=None, height: int = 600,
               key: str = "cv_viewer",
               meta: dict = None, dets=None, max_zoom_pixel_ratio: float = 24.0,
               restore_zoom: float = None, restore_center=None,
               nav_keys: bool = False, auto_height: bool = False):
    """M7 新增四參數(皆可選、預設保留 M6 行為):
    restore_zoom:float|None    切張後要還原的 viewport zoom(來自上次 nav 回傳的 getZoom(true));
                               None → 新圖預設 fit(M6 行為)。
    restore_center:list|None   要還原的 viewport center [x,y](getCenter(true));None → 不還原 pan。
    nav_keys:bool              True → 元件啟用 document keydown 熱鍵(←/→/j/1/2/3/r/b/[/]/u),
                               以 {"type":"nav",...} 回傳事件(見 §2.1b 協定);False → M6 行為(無熱鍵)。
    auto_height:bool           True → 元件端量 window.innerHeight 動態 setFrameHeight(忽略 height 當下限),
                               False → 用傳入 height(M6 行為)。
    回傳值形狀『擴充』:除既有 {"type":"click"...}/{"type":"roi"...}/None 外,
                       nav_keys=True 時新增 {"type":"nav", ...}(見 §2.1b);hover 仍不回傳事件、不 round-trip。"""
```

> **向後相容**:不傳新參數 → 行為與 M6 逐位元組相同。`key` 由 app 端**固定為不含 idx**(見 §2.5 / M7a 修 remount bug),viewer.py 本身不強制。

#### 2.1b 元件協定新事件 `type:"nav"`(JS → Python,`setComponentValue`)

```python
{
  "type": "nav",
  "action": str,    # 見鍵位表 §3.4:"prev"/"next"/"jump"/"verdict"/"status"/"bookmark"/
                    #   "thumb_prev"/"thumb_next"/"undo"
  "value": any,     # action 相關 payload:verdict→"true_defect"|"false_alarm"|"reflection";
                    #   status/bookmark/undo→None;prev/next/thumb_*→None
  "n": int,         # 單調遞增事件序號(去重,語義同既有 click/roi 的 n)
  "zoom": float,    # 觸發當下 viewer.viewport.getZoom(true)(供 app 存起來給下一張還原)
  "center": [x,y],  # 觸發當下 getCenter(true)
}
```

> app 端用 `n > ss.last_nav_n` 判新事件;讀 `zoom`/`center` 存進 `ss.restore_zoom`/`ss.restore_center`,下次 render 經 args 帶回(機制照搬 spike,§3.2)。

### 2.2 `thumbwall.py` — 虛擬化簽名(M7c)

```python
def thumbwall(items, selected: int = 0, height: int = 620, key: str = "thumbwall",
              window: dict = None):
    """M7c 新增 window(虛擬化視窗)。
    items: 仍是 list[dict]{"img","label","mark","nd"};但 app 端只塞『可視窗 + 前後緩衝』
           範圍內的縮圖 data URL,窗外項以佔位 {"img":None,"label":str,"mark":"","nd":0} 帶入
           (元件渲染為等高佔位塊,維持捲動條長度與點擊 index 正確)。
    window:dict|None  {"start":int,"end":int,"total":int}(半開區間 [start,end));
                      None → 不虛擬化(M6 行為,全塞)。
    回傳值形狀不變:{"index":int,"n":int}(index 為『全域 index』,非窗內偏移);
                   去重邏輯不變(n>last_thumb_n)。
    元件端新增:document 內捲動可上報目前可視窗起訖(供 app 重算 window),見 §2.2a。"""
```

#### 2.2a thumbwall 虛擬化協定(回傳擴充)

- 元件端監看 `#wall` 捲動,當可視範圍變動超過緩衝閾值,以 `setComponentValue({"type":"viewport","start":i0,"end":i1,"n":++n})` 上報(去重序號 `n`);app 讀後更新 `ss.tw_window` 並只重算窗內縮圖。
- 點擊回傳保持 `{"index":<全域index>,"n":...}`(佔位塊也可點 → 但 app 對 `img:None` 的佔位塊不渲染可點縮圖,僅渲染高度;點擊只發生在已載入縮圖)。

### 2.3 新元件 `compare_component/index.html` + `compare.py`(M7c,linked-viewport)

```python
def linked_compare(image_a: str, image_b: str, name_a: str = "", name_b: str = "",
                   restore_zoom: float = None, restore_center=None,
                   mode: str = "side_by_side", height: int = 600, key: str = "cv_compare"):
    """並排雙 OSD,viewport 連動(linked):任一邊 zoom/pan,另一邊同步;
    初始 viewport 沿用主 viewer 傳入的 restore_zoom/restore_center(linked 到主舞台)。
    mode: "side_by_side"(並排雙 OSD,連動) | "blink"(單 OSD,A/B 定時切換,沿用同一 viewport)。
    image_a/image_b: data URL(app 端用 imgio.to_data_url 產生,B 已 resize 對齊 A 形狀)。
    回傳:最近一次 {"type":"compare_state","zoom":float,"center":[x,y],"n":int} 或 None
         (供把比較視圖的 viewport 回灌主 session_state,維持 linked 一致;不切張)。"""
```

> **複用**:並排幾何不另寫——兩個 OSD 各自 `tileSources:{type:'image'}`,以 `viewer_a.addHandler('zoom'|'pan', sync→viewer_b)` 雙向綁定(節流防回授風暴)。blink 沿用單 OSD 切 image。**不** import `framecompare`(framecompare 是 server-side numpy 像素運算,linked viewport 是 client-side OSD viewport 連動,兩者並存:difference/blend/swipe 仍走工具台 framecompare,linked 並排/閃爍走本元件)。

### 2.4 `app.py` 版面骨架重組(無新簽名,僅組裝順序/容器/session_state)

新增 session_state 旗標(全域持久,跨圖不重置 — #8):
```
ss.thumb_collapsed : bool   # 縮圖牆收合(0 寬)
ss.rail_collapsed  : bool   # 判定 Rail 收合(0 寬)
ss.restore_zoom    : float|None   # 跨切張保存的 viewport zoom(spike 機制)
ss.restore_center  : list|None
ss.undo_stack      : list[dict]   # 跨圖 undo 軌跡(§3.6 資料模型)
ss.last_nav_n      : int          # nav 事件去重序號
ss.tw_window       : dict|None    # 縮圖牆虛擬化視窗
ss.dirty           : dict|None    # 當前圖未存的判定變更(autosave flush 用,§3.5)
```

### 2.5 修 remount bug(M7a,核心)

現況 `app.py:350` `key=f"viewer_{ss.idx}"` → 每切張 iframe remount(焦點丟、可能重置 zoom/pan)。**改為固定 key `key="cv_viewer"`(不含 idx)**。據 spike 對照組實證:固定 key → iframe 跨 rerun 不 remount(`__loadCount` 恆 1);idx-key → 每切張新生 iframe(births 累加)。同理 `dziview_*`/`dzi_*` 等工具台內 key 維持其區域 key 即可(它們本就在召喚層,non-critical)。

---

## 3. 資料流與機制(虛擬步驟,非可執行實作)

### 3.1 固定 key viewer + 跨 rerun 不 remount(M7a)
照搬 spike:主 viewer `key="cv_viewer"` 固定。元件端 `message` handler 只在 `args.image !== lastImage` 時才 `buildViewer`(換 OSD 影像),否則只更新 HUD/dets/rois → 同一 iframe 整輪存活,焦點與既有 viewport 不被 remount 摧毀。

### 3.2 zoom/pan 跨切張保存(M7a,照搬 spike 命題4)
1. 任一 nav 事件(鍵盤或鈕)觸發前,元件回傳當下 `getZoom(true)`/`getCenter(true)`(隨 `type:"nav"` 帶 `zoom`/`center`,或 click/roi 既有事件不帶)。
2. app 存入 `ss.restore_zoom`/`ss.restore_center`,下次 render 經 args `restore_zoom`/`restore_center` 帶回。
3. 元件 `open` handler:若 `pendingRestore && restoreZoom != null` → `viewport.zoomTo(restoreZoom,null,true)` + `panTo(Point(cx,cy),true)` + `applyConstraints(true)`(immediately=true 不留殘影)。
4. **`maxZoomPixelRatio` 必須沿用 24.0**:預設 1.1 會把還原 clamp 回 fit(spike 已驗;§6 界線釘死)。

### 3.3 焦點守衛(M7a/M7b,照搬 spike 命題3+5)
- `open` handler 末尾 `osdEl.focus()`(osdEl 加 `tabindex=0`)→ rerun 後第二鍵有宿主。
- keydown handler 開頭:`activeElement ∈ {INPUT,TEXTAREA} || isContentEditable` → `return`(不誤觸熱鍵)。元件 iframe 的 document 只看得到自己 iframe 內焦點;主文件的 number_input/text_area 天然不把鍵傳進元件 iframe(§6 界線)。

### 3.4 鍵盤鍵位表(完整 — M7b 核心)

| 鍵 | action | value | 語義 | 焦點守衛後生效 |
|----|--------|-------|------|----------------|
| `←` | prev | — | 上一張(連切;切前存 zoom/pan) | ✔ |
| `→` | next | — | 下一張 | ✔ |
| `1` | verdict | `"true_defect"` | 設 verdict=真缺陷(即時寫+入 undo) | ✔ |
| `2` | verdict | `"false_alarm"` | 設 verdict=誤報 | ✔ |
| `3` | verdict | `"reflection"` | 設 verdict=反思 | ✔ |
| `r` | status | — | 循環 review_status(none→need_review→done→none) | ✔ |
| `b` | bookmark | — | toggle bookmarked | ✔ |
| `[` | thumb_prev | — | 縮圖牆選取上移(同 prev,語義別名;實作可等同 ←) | ✔ |
| `]` | thumb_next | — | 縮圖牆選取下移(同 next) | ✔ |
| `u` | undo | — | 跨圖 undo(跳回那張+還原值+toast) | ✔ |
| `j` | (前端聚焦跳頁) | — | `e.preventDefault()` 後元件**不**回傳 nav,改 `setComponentValue({type:"focus_jump",n})`;app 收到後**不**搬焦點到主文件(iframe 不能跨文件 focus 主文件 widget,§6 界線),而是**展開/捲動到 Command Bar 的跳頁 number_input 並提示**;務實降級:`j` 等同「把 Command Bar 跳頁框 scrollIntoView + 視覺高亮」,實際輸入仍需使用者點該框(焦點守衛確保點進框後鍵盤不再切張) | ✔ |

> **verdict 值域釘死** = `tagging.VERDICTS[1:]`(`unset` 是哨兵不綁熱鍵);**不得**把 `review_status`/`bookmarked` 冒名成 verdict(User-role 第1點)。`r`/`b` 是獨立鍵,改 status/bookmark,不寫 verdict。

### 3.5 autosave 觸發點 + dirty flush(M7b)
- **改值即時寫**:Rail 的 verdict/status/bookmark 任一變更(widget on_change 或本 run 偵測到值 != sidecar 載入值)→ 立即 `sidecar.save(...)` 並把「舊值→新值」推入 undo_stack(§3.6)。
- **切張前 flush**:任何 nav(鍵盤/鈕/縮圖點擊)在改 `ss.idx` 之前,先檢 `ss.dirty`(當前圖未存變更),非空則 `sidecar.save` flush 再切。
- **單一真相**(#12):Rail 與工具台/任何 popover 若都能改 verdict,一律綁**同一** `ss` 鍵(如 `ss.verdict_<path>` 或直接讀寫該圖 sidecar)+ **同一** undo_stack;不得各自存一份(避免漂移)。tags/comment 仍保留「💾儲存判定」顯式存(text 類非高頻、非熱鍵),但 verdict/status/bookmark 即時存。
- **界線**:autosave 在 rerun 邊界 flush,非「絕對零遺失」(§0、§6)。

### 3.6 undo 資料模型(M7b)
```python
undo_entry = {
  "path": str,         # 那張圖的路徑(undo 要跳回它)
  "idx": int,          # 那張圖在當前 shown_items 的 index(跳轉用;失配時以 path 重新定位)
  "field": str,        # "verdict" | "review_status" | "bookmarked"
  "old": any,          # 變更前的值(undo 還原成此值)
  "new": any,          # 變更後的值(僅供顯示/除錯)
}
# ss.undo_stack: list[undo_entry],append-only push,pop 從尾端(LIFO);保留近 N=5 筆(超過丟最舊)
```
- **undo 語義釘死**:`u` → pop 尾端 entry → `ss.idx = locate(entry["path"])`(跳回那張圖)→ `sidecar.save(還原 field=old)` → `st.toast("已撤銷:{name} {field} → {old}")` → `st.rerun()`。**撤銷會跳轉**(這是刻意,User-role 第5點要求「跳回那張圖」)。
- footer 顯示 `可撤 {len(ss.undo_stack)} 筆`。空 stack 時 `u` no-op(toast「無可撤銷」)。

### 3.7 信心門檻常駐 footer + 即時反映(M7a/M7b)
- footer slider `st.slider("信心門檻",0.0,1.0,0.25,step=0.01)`(step 0.01 細微調)+ 旁置 `[−]`/`[+]` 鈕(各 ±0.05 快跳,改 `ss.conf_thr` 後 rerun)。常駐、不收。
- 改門檻 → 重算 `kept = overlay.filter_detections(dets, conf_threshold, classes)` → 主 viewer dets/燒框與 footer「顯示 {len(kept)}/{總} 框」**即時更新**(同一 rerun);縮圖牆只重算「可視窗內」縮圖(§3.8 不重建整牆)。

### 3.8 縮圖牆虛擬化視窗策略(M7c)
- **視窗** = `[max(0, selected-B), min(total, selected+B+W))`,B=緩衝(預設 12)、W=可視槽估計(預設 16);或由元件捲動上報的 `start/end` ± 緩衝。
- app 只對窗內 index 呼叫 `_thumb(...)`(重算只發生在窗內);窗外塞佔位(`img:None`),元件渲染等高佔位塊維持捲動長度。
- **改信心門檻不重建整牆**:門檻只影響「燒框」;設計要求 `_thumb` 的 cache key 已含 `conf_thr`/`dets_key`,故門檻變只重算窗內、且 cache 命中跨 rerun。**per-image 切張成本可量測**(§5 效能量測)。
- **現況病灶對照**:現 `app.py:229` 對整資料夾每張 `_item_for`(sidecar.load + _detections),`app.py:322-330` 每張算/疊縮圖 → 上千張每 rerun 重掃。M7c 要求:(a) 縮圖牆只算窗內;(b) `_item_for` 的 sidecar/detection 載入對「非窗內且非當前圖」可延後/快取(cache_data 已快取 _detections,但 sidecar.load 每 rerun 重讀 → 設計要求 app 對 sidecar 也快取或只在窗內+當前圖 load)。

### 3.9 DZI 主 viewer 自動瓦片門檻(M7c — 評估後可能誠實降級)
- **判準**:當前圖 `w*h > DZI_AUTO_THRESHOLD`(預設候選 8_000_000 px,約 2828² / 或 max(w,h)>4096)→ 主 viewer 自動走 tiles 模式(`_dzi_tiles(path)` → `osd_viewer(tiles=...)`),使用者無感;否則走單圖 data URL。
- **降級判準(誠實)**:PG 量測「建金字塔 + data URL 編碼」對一張臨界大圖的耗時。**若該耗時使切張 P95 超過 M7c-AC4 門檻** → **放棄自動瓦片**,維持 M5 手動 DZI 開關(工具台「🧩 DZI」tab),並在設計校準後標明「自動瓦片降級為手動」。M7c-AC8 即驗此決策有被誠實量測與記錄(非默默跳過)。
- tiles 模式 hover RGB 降級(無全圖)沿用 M6 §3.4(只 x,y+zoom,不 RGB)。

### 3.10 linked-viewport 比較機制(M7c)
- Command Bar / Rail 一鍵「🔀 比較」→ 工具台「比較」tab 內(或 Rail 內嵌)呼叫 `linked_compare(A, B, restore_zoom=ss.restore_zoom, restore_center=ss.restore_center, mode=...)`。**初始 viewport = 主舞台當前 zoom/pan**(linked,User-role 第6點)。
- 並排雙 OSD 連動:`viewer_a` zoom/pan → 節流同步 `viewer_b`(反之亦然);blink = 單 OSD 定時切 A/B image、viewport 不變。
- 比較視圖 viewport 變動回灌 `ss.restore_zoom`(`type:"compare_state"`)→ 關閉比較回主 viewer 時 viewport 一致。
- **一鍵可達**:比較入口在 Command Bar 「🧰工具台」首 tab(或 Rail 旁),**不**埋兩層(User-role 第6點)。

### 3.11 RWD 斷點規則(M7c)
- app 端以 `st.columns` 權重 + session 旗標控制三欄寬。**窄載體判定**:無法直接讀視窗寬於 server,故由**主 viewer 元件回報** `window.innerWidth`(隨 `auto_height` 量測一併經 `setComponentValue({"type":"layout","vw":int,"n":...})` 上報一次/變動時),app 讀 `ss.viewport_w`。
- 斷點:`vw < 1100` → Rail 自動收成「底部 strip」(verdict 1/2/3 + bookmark icon 一行,置於 footer 下方),縮圖牆可由使用者收 0 寬;`vw < 800` → 縮圖牆預設收合、Rail 為 icon strip。斷點數值允許 PG 量實際 nativeApp iframe 寬後由 architect 校準。

### 3.12 右鍵釘選 hover 點(2026-07-04 新增,設計演進 — 純元件端,無 Python 契約變更)

> 需求來源:`1_user_needs/04_pin_point_right_click.md`。**純 client 端功能**:`viewer.py` 的 `osd_viewer()` 簽名、`meta`/`dets`/`rois` 資料形狀**皆不變**——這與 §2.1「M7 新增四參數」等 Python 側契約無關,只動 `viewer_component/index.html`。因此**無新 Python 單元 gate 可言**(本來就沒有),機器判綠沿用既有「真實 E2E」路線。

- **狀態**:元件端新增模組層級 `let pinPoint = null;`(`{x:int, y:int, rgb:[r,g,b]|null}`)。**每次 `buildViewer()`(換圖,含單圖與瓦片模式)重置為 `null`**——這是既有「新圖 = 新的 OSD 物件」生命週期的自然掛鉤點,不需要額外的「換圖清空」邏輯。
- **觸發**:`osdEl` 新增 `contextmenu` 監聽,`e.preventDefault()`(蓋掉瀏覽器原生右鍵選單,僅在 viewer 畫布範圍內);用既有 `imgPtFromEvent(e)` 換算影像座標,若 `sampleReady`(單圖模式)且座標在圖內 → 用既有 offscreen canvas `getImageData` 取樣 RGB(與 hover 同一套零 round-trip取樣,語義一致:顯示值非真值);瓦片模式(`tiledMode`)下 `rgb=null`(與 hover 既有降級語義一致,見 §6 hover=顯示值界線)。**右鍵一次即覆蓋** `pinPoint`(不累積清單,符合 User 原文「換成新的」)。
- **繪製**:`drawRois(rois)` 除既有 ROI/偵測框外,**若 `pinPoint` 非 null** 也畫一個小型十字/圓點 overlay(`viewer.addOverlay({element, location: viewer.viewport.imageToViewportCoordinates(new OpenSeadragon.Point(pinPoint.x, pinPoint.y)), placement: OpenSeadragon.Placement.CENTER})`)——與 ROI/偵測框同路徑重繪,故縮放/平移後位置自動隨 `imageToViewportCoordinates` 換算跟著對,不需要額外的『重新定位』程式碼。標記樣式獨立 CSS class(區別於偵測框顏色,避免使用者誤認成模型框)。
- **HUD**:`renderHud()` 新增一列(獨立於既有『hover』列,不覆蓋它——兩者同時顯示):若 `pinPoint` 非 null → `📌 (x=.., y=..) RGB=(r,g,b)`(`rgb=null` 時比照 hover 瓦片降級文案)。此列**不隨滑鼠移開而消失**(這是與 hover 列的本質差異、也是本功能存在的理由)。
- **不做**(對齊 §3 User 原文「不在乎」):不持久化到 sidecar/磁碟、不匯出、不支援多點清單、無獨立清除鈕(換圖或右鍵新位置即等同清除/覆蓋)。

### 3.13 Focus Object 模式(2026-07-04 新增,設計演進 — 純轉發,無新純邏輯;`kept` 挑選在 app 端)

> 需求來源:`1_user_needs/05_focus_object_mode.md`。目的:一鍵切換每張圖預設放大到「目前顯示框(已依信心/類別過濾)裡信心最高」的那個,幫審圖員快速掃過模型最有把握的判斷。

- **控制**:Command Bar 上方新增 `st.toggle("🎯 Focus Object（自動放大到最高信心物件）", key="focus_object_on")`,與既有 `🔀 比較模式` toggle 同一位置區塊。**依 §4.l 鐵律,必須排在本節開頭、任何 Command Bar 按鈕之前實例化**(否則複製「filter 消失」bug,見 §4.l 附記)。
- **挑選邏輯(app 端,純 Python,無新模組)**:`focus_bbox = max(kept, key=lambda d: d["conf"])["bbox"] if kept else []`(當 `ss.focus_object_on` 為真時計算;`kept` 即既有信心雙界 + Object 類別過濾後的清單,見 §7)。**不新增排序/挑選函式**——`max(...)` 一行內嵌足矣,不值得為此開一個純邏輯模組。
- **三態契約(§4.m)**:`osd_viewer(..., focus_bbox=...)` 新參數,`None`=模式關閉(沿用既有 M7a 跨切張保存 + M7b restore)、`[]`=模式開啟但本圖 `kept` 為空(退回一般 fit-to-image)、非空 `[x,y,w,h]`=聚焦該框。
- **元件端(viewer_component/index.html)**:
  - `curFocusBbox` 模組層級狀態,每次 render 從 `args.focus_bbox` 更新;獨立簽名 `lastFocusBbox` 追蹤變化(**不能只靠既有 `detsJson`/`roisJson` 判斷**——切換模式開關本身不改 dets/rois 內容,若只靠那兩個簽名會漏判,見 §4.l 附記的踩坑記錄)。
  - `focusOnBbox(bbox)`:以 35% 留白包住框(`pad=0.35`,框本身不頂到 viewer 邊緣、看得到周邊脈絡),`imageToViewportRectangle` 換算後 `fitBounds(rect, true)`(沿用既有 restoreBounds 手法)。
  - 觸發點兩處:①`open` handler(換圖時,三態分支見上);②同圖下 `focusJson !== lastFocusBbox` 時(涵蓋模式開關切換 + 信心/類別篩選導致 kept 換了目標)。
- **與既有機制的優先權**:Focus Object 非 null/非空 list 時**蓋掉** M7a 的 zoom/pan 跨切張保存與 M7b 的 restore_zoom/restore_center(使用者已明確選擇「每次都聚焦最高信心框」,原保存的視角不再有意義)。模式關閉時兩者行為完全不變(向後相容)。
- **不做**:不記錄/持久化「使用者手動又縮放到別處」這件事(下一次切圖或 kept 變動,一律重新 fit 回最高信心框,對齊 User 原文「不需要記住我手動縮放過的位置」)。

---

## 4. 邊界條件與錯誤處理

a. **首張按 ←** / **末張按 →**:夾界(`max(0,idx-1)`/`min(total-1,idx+1)`),不 wrap(與現有鈕一致);連按到邊界 no-op,不報錯。
b. **無偵測 / 全被濾掉**:footer「顯示 0/0 框」;HUD 框命中列空;縮圖無框;熱鍵 1/2/3 仍可設 verdict(verdict 與有無框無關)。
c. **未存切張**:§3.5 切張前 flush dirty;若 dirty 為空則直接切。
d. **撤銷跨圖(空 stack)**:`u` no-op + toast「無可撤銷」;**撤銷會跳轉**到 entry.path,若該圖已被篩掉不在 shown_items → 以 path 在 `items`(未篩全集)定位並提示「該圖不在當前篩選範圍」(或暫解篩選跳轉,實作擇一,AC 只釘「跳回 + 還原值 + toast」)。
e. **窄寬(vw 缺值)**:首 render 尚未收到元件 layout 上報 → 用預設三欄(不收);收到後再 rerun 套斷點。不得因缺 vw 崩。
f. **大圖自動瓦片門檻臨界**:恰好等於門檻 → 走單圖(`>` 嚴格);瓦片建構失敗(memory)→ 退單圖 data URL 並 caption 提示(不崩、不 false-green)。
g. **焦點在 number_input 連打數字**:焦點守衛 return,熱鍵 1/2/3 不誤觸成 verdict(§3.3、M7b-AC9)。
h. **收合到 0 寬後**:被收的欄不渲染其重內容(縮圖牆收合 → 不算任何縮圖;Rail 收合 → 仍可用熱鍵改 verdict,單一真相不依賴 Rail widget 存在 — 即 verdict 寫入路徑不可只掛在 Rail widget 的 on_change,否則收合後熱鍵失效)。
i. **同一 nav 的 zoom/pan 還原**:若 `restore_zoom` 為 None(首次/被清)→ 新圖 fit(不報錯)。
j. **thumbwall 佔位塊點擊**:`img:None` 佔位不可點(只佔高度);點擊只在已載入縮圖,index 為全域 index。
k. **信心 triage 把清單篩空(2026-07-04 新增,防卡死)**:`shown_items` 因信心區間 triage 變空時,既有 `st.warning(...); st.stop()` **不得單獨使用**——`st.stop()` 之前若信心 slider 尚未在本 run 渲染過(它原本在 Command Bar、於 `shown_items` 判空**之後**才畫),使用者會連能拉寬回去的控制都從畫面消失、卡死無法恢復。**修正**:空清單分支必須**先重畫同 `key="footer_conf_thr"` 的信心 slider(值沿用當下 `(lo,hi)`)**,使用者仍可拉寬,才 `st.stop()`(Streamlit 同 key 各分支互斥渲染一次即合法,不衝突)。此為 PG 實作時發現的邊界,非 User 需求原文,但**必要**(見 AC-conf5)。
l. **keyed widget 必須搶在任何 `st.rerun()` 之前實例化(2026-07-04 新增,User 回報「filter 切下一張就不見了」嚴重 bug 之修正)**:Streamlit 對『本輪指令碼跑完前都沒被實例化』的 keyed widget 會清空其 `session_state`(孤兒 widget 狀態清理)。凡是 Command Bar 內「可能呼叫 `st.rerun()` 的按鈕」(⟵/⟶/跳頁/⭐)都必須排在 `footer_conf_thr`(信心 slider)/`cls_filter`(Object 下拉)**之後**宣告——不是視覺順序,是**程式碼執行順序**(`st.columns` 的視覺欄位順序只由 `bar=st.columns([...])` 當下決定,與後續往哪個 `bar[i]` 寫入的程式碼順序無關,故提前實例化不影響版面)。同理,任何**跨多輪需要持久**的 widget(如縮圖牆「排序」`sort_mode`)**不得**包在會隨互動狀態變 False 的條件式內(原本包在 `if not ss.thumb_collapsed:`,收合縮圖期間整輪不被呼叫 → 同一機制清空)——這類 widget 必須恆渲染。**任何未來新增的 Command Bar / 縮圖牆控制,新增前都要檢查這條規則**,否則會複製同一個 bug。**本規則本身在 Focus Object 模式(§3.13)實作時就複製過一次**(`focus_object_on` 原排在 Command Bar 之後,同一機制被清空;修法是移到本節開頭、任何按鈕之前,見 §3.13)。
   **勘誤(2026-07-04,見 §4.n)**:本條原建議「收合時只能靠外層容器寬度趨近 0」——這個建議本身是**錯的**,已被 §4.n 的真實 bug 推翻:容器寬度趨近 0 時,Streamlit 不會優雅隱藏內容,而是把文字擠成逐字直排、把按鈕擠成 `width=0` 不可點,反而製造新的卡死。**恆渲染 + 容器寬度趨近 0 兩者不可同時成立**——若 widget 需要「跨收合狀態持久」,就必須把它移到一個**不隨收合狀態變窄的獨立容器**,而不是留在會變窄的容器內恆渲染。
m. **Focus Object 三態,不可用單一 `None` 代表兩種語義(2026-07-04 新增,實測抓到)**:`focus_bbox` 若只分「有值」/`None` 兩態,「模式關閉」與「模式開啟但本圖無偵測」會被迫共用 `None`,導致後者誤入 M7a 的 `pendingRestore` 分支、沿用上一張殘留的 zoom 顯示一張無關的裁切畫面(實測:啟用模式聚焦某框後切到 0 偵測圖,zoom 停在上一張的高倍率不變)。**修正為三態**:`None`=模式關閉(沿用既有行為)、`[]`=模式開啟但本圖無框(退回 `goHome()` fit)、非空 list=聚焦該框;三態在元件端須各自獨立分支處理(見 §3.13)。
n. **收合欄的「寬度趨近 0」trick 會連內含 widget 一起擠壞(2026-07-04 新增,User 回報「收合後再也展開不回來」+「版面跑掉、文字變直排」,實測 bounding_box 確認)**:縮圖牆收合(`_left_w=0.0001`)是靠把 `st.columns` 的其中一欄比例壓到近乎 0 來「隱藏」內容——但若「收合/展開」切換鈕本身或 `sort_mode` 之類需跨收合狀態持久的 widget **留在這個會變窄的欄內**,它們會被**一起擠壞**:文字被迫逐字換行成直排、按鈕 `bounding_box().width` 變 0 且 `is_visible()==False`,使用者連點擊「展開縮圖」都做不到,永久卡在收合狀態(且此時 §4.l 建議的「恆渲染」本身也無法補救,因為問題不是『有沒有渲染』而是『渲染的容器太窄』)。**修正**:把「收合/展開」切換鈕、`sort_mode`、符合張數 caption 移到一個**獨立、不隨 `ss.thumb_collapsed` 變窄的欄**(仍用與縮圖欄相同的比例對齊視覺位置,但寬度恆定);縮圖格本身(真正需要「讓出空間給 viewer」的部分)才依收合旗標變窄——即「控制項容器」與「內容格容器」必須是兩個獨立的 `st.columns` 呼叫,不可共用同一個會變窄的欄。
o. **Object 類別與信心門檻現在共同觸發清單 triage,兩者的「篩空防卡死」必須同步擴充(2026-07-04 新增,User 回報「縮圖沒消失、右邊也沒框」之後順勢擴充,見 §7)**:單獨為信心門檻寫的 §4.k 防卡死(篩空時重畫同 key 的信心 slider)在 Object 類別也會導致篩空之後**不夠**——若篩空成因是類別選擇本身(信心範圍其實沒問題),使用者只看到信心 slider 被重畫、看不到能把類別選回「全部」的下拉,一樣卡死,只是換了個觸發源。**修正**:篩空分支必須**同時**重畫信心 slider **與** Object 類別下拉(兩個 key 各自在互斥分支重畫一次皆合法)。**教訓,供未來任何新增的 triage 維度參考**:凡是新增一個會讓清單變空的過濾維度,篩空的防卡死分支就必須同步納入該維度的重置控制,不能只補最早那一個。

---

## 5. Acceptance Criteria(依切片編號;每條標 [E2E可斷言] / [截圖實證] / [效能量測] 與量測法)

> E2E 入口(沿用既有 conftest `app_server` + playwright `page`):`cd C:/code/claude/CV_Viewer && pytest 4_PM_Feedback/test_viewer_workbench_e2e.py -m e2e -v`。viewer/thumbwall/compare 各在巢狀 iframe,定位沿用既有 `_find_viewer_frame`/`_find_thumbwall_frame`(掃 `page.frames`、以 canvas/img 數分辨;compare frame = 含 ≥2 canvas 或專屬 `#compare`)。三切片可獨立 E2E 綠、階段間有 gate。

### 效能量測機制(可機器斷言 — 先釘手段,門檻允許 PG 量實際值後 architect 校準)

PG 必須提供下列**可被 Playwright 客觀讀取**的量測探針(三選一落地,設計釘「至少 server 端 render 計時 + rerun 計數 + 重函式呼叫計數」皆可讀):

- **(P1) server render 計時**:app 在每次 render 結尾把「本 run server 端耗時(ms)」與「累積 rerun 次數」寫進一個隱藏探針 DOM(沿用 spike 的 `<div id='perf' data-render-ms=... data-reruns=... data-thumb-recalc=... data-tool-calls=...>`,主文件 DOM、跨 iframe 可讀)。Playwright 讀 `data-*` 即得數值。
- **(P2) 元件端 `performance.now()`**:viewer 元件在 nav 觸發→下一張 open 完成之間量 `performance.mark`/`measure`,經 `setComponentValue({"type":"perf","nav_ms":...})` 回報;app 寫進 P1 探針供讀。
- **(P3) 重函式呼叫計數**:`ss.counters = {"thumb_recalc":int, "tool_dzi_build":int, "tool_compare":int, ...}`,在 `_thumb_cached` 實算分支、`_dzi_tiles`、`linked_compare` 組裝處 `+=1`,寫進 P1 探針 `data-*`。**未召喚層 0 計算 = 工具台未展開時對應 counter 增量為 0**。

#### 三條效能量測法(對應 User-role 效能訴求)

- **(PerfA)「切下一張 per-image 成本」**:E2E 連按 `→` K 次(如 20 次),每次讀 P1 `data-render-ms`(或 P2 `nav_ms`),取 **P95**。門檻初值 **P95 < 1200ms**(含 server render + viewer open;**允許 PG 量實際值後校準**,以「連切不卡頓的可感知體驗」為準)。**[效能量測]**。
- **(PerfB)「未召喚層 0 計算」**:工具台 expander **未展開**時連續切張 N 次,讀 P3 `data-tool-calls`(DZI build + compare 組裝 + framecompare/simhash/embcluster 重算的計數總和)應**恆為 0**;展開後操作對應 tab 才 >0。**[效能量測]**(機器斷言計數器==0)。
- **(PerfC)「信心 slider 改值不重建整牆」**:記錄改門檻前 `data-thumb-recalc`,把 footer slider 改一格(±0.01)後讀新值,**增量 ≤ 視窗大小(W+2B,如 ≤ 40)**,而非 = total(上千張)。**[效能量測]**(機器斷言 Δthumb_recalc ≤ 窗大小,且 < total)。

---

### M7a — 版面 + viewer 基座(收疊 / viewer 最大化 / 固定 key + zoom·pan 保存 + 修 remount / footer 常駐 slider)

- **M7a-AC1** `[E2E可斷言]` 版面骨架:存在 Command Bar(⟵/⟶ 鈕 + 跳頁 number_input + 檔名/偵測N框 caption),主 viewer canvas frame 可見,footer 區存在 label=「信心門檻」slider 與 label=「顯示偵測框」checkbox(皆在 sidebar 外、在 viewer 之下/同主舞台區)。
- **M7a-AC2** `[E2E可斷言]` **修 remount bug**:連續切張(點縮圖或按 ⟵/⟶)後,viewer iframe **不 remount**——元件端 `window.__loadCount === 1` 恆成立(固定 key);對照「若 idx-key 會 >1」由設計釘死。斷言法:切張 3 次後 `viewer_frame.evaluate("()=>window.__loadCount")` 仍 `=== 1`。**(沿用 spike 命題1 證據手段。)**
- **M7a-AC3** `[E2E可斷言]` **zoom/pan 跨切張保存**:在第 N 張放大(`viewer.viewport.zoomBy(3);applyConstraints`)記下 `getZoom(true)=z0`、`getCenter(true)=c0`,按 `→` 再按 `←` 回來後,viewer `getZoom(true)` 與 z0 差 < 容差(如 |Δ|<0.05*z0),center 同理。**(沿用 spike 命題4;maxZoomPixelRatio=24 沿用,§6。)**
- **M7a-AC4** `[E2E可斷言]` **收合狀態全域持久**:收合縮圖牆(點「收縮圖」鈕)後切張 2 次,縮圖牆仍維持收合(thumbwall iframe 不渲染或 0 寬可斷);展開 Rail / 收 Rail 同理跨圖持久(`ss.rail_collapsed` 不被切張重置)。
- **M7a-AC5** `[E2E可斷言]` **footer 信心 slider 常駐 + 即時反映**:footer slider 在三欄牆下方常駐(不在任何 expander 內);改門檻一格後,主 viewer caption/HUD「顯示 k/總 框」之 k **即時變化**(同一 rerun 後讀文字確認 k 改變)。step=0.01 可由 slider DOM 屬性或連續微調生效斷言。
- **M7a-AC6** `[E2E可斷言]` **HUD 語義界線保留**:對 16-bit 樣本(wafer16_*.tif)hover 後,HUD 或 footer caption 明示 hover RGB=「顯示值」、點擊取真值(含「顯示值」或「點擊取」或「取真值」其一)。**(承接 M6-AC9,版面位移後仍清楚。)**
- **M7a-AC7** `[截圖實證]` viewer 最大化:主 viewer 佔 stage ~85% 高(height 由 JS 量視窗動態給,~720 起);截圖確認 viewer 顯著大於 M6 的 600 固定高、三欄比例為「窄縮圖 | 寬 viewer | 窄 Rail」。
- **M7a-AC8** `[效能量測]` 探針就緒:P1 隱藏探針 DOM 存在且 `data-render-ms`/`data-reruns`/`data-thumb-recalc`/`data-tool-calls` 皆為可解析數字(為後續 PerfA/B/C 鋪底;本 AC 只驗探針可讀)。

### M7b — 鍵盤工作流(←/→ nav / verdict 熱鍵 1/2/3 / r·b / 切張自動存 / 跨圖 undo / 焦點守衛)

- **M7b-AC1** `[E2E可斷言]` ←/→ 連切:viewer canvas focus 後(或 open 後元件自動 focus),對 viewer frame `keydown ArrowRight` ×2,主進度文字變 `3/總`(連按不吃首鍵);`ArrowLeft` 回 `2/總`。**(沿用 spike 命題2。)**
- **M7b-AC2** `[E2E可斷言]` verdict 熱鍵:在已知圖按 `1`,該圖 sidecar `verdict` 變 `"true_defect"`(E2E 經 Rail 顯示的 verdict 控制讀回值,或讀探針回寫的 `data-verdict`);`2`→`"false_alarm"`、`3`→`"reflection"`。**值不得是 review_status/bookmarked**(防冒名)。
- **M7b-AC3** `[E2E可斷言]` r/b:按 `r` review_status 循環(none→need_review→done,讀 Rail status radio 當前值或探針);按 `b` bookmarked toggle(Rail bookmark checkbox 狀態翻轉)。
- **M7b-AC4** `[E2E可斷言]` 切張自動存:在 A 圖按 `1`(verdict=true_defect),**不**按「💾儲存」,按 `→` 切到 B 再按 `←` 回 A,A 的 verdict 仍是 `true_defect`(已即時/flush 寫入 sidecar,讀回確認)。
- **M7b-AC5** `[E2E可斷言]` 改值入 undo 軌跡:按 `1` 後 footer「可撤 N 筆」之 N **+1**;再按 `2` 之 N 再 +1(讀 footer 文字數字)。
- **M7b-AC6** `[E2E可斷言]` 跨圖 undo:A 圖按 `1`→`→`切到 B→按 `u`,**跳回 A**(進度文字回 A 的序號)且 A verdict **還原**為按 `1` 前的舊值(如 `unset`),並出現 toast(`st.toast` 文字含「撤銷」)。**撤銷會跳轉**(語義釘死)。
- **M7b-AC7** `[E2E可斷言]` 多步 undo:連改 3 次(`1`→`→`→`2`→`→`→`3`)後連按 `u` ×3,每次跳回對應圖 + 還原,footer「可撤 N 筆」遞減到 0;第 4 次 `u` no-op(N=0、toast「無可撤銷」)。
- **M7b-AC8** `[E2E可斷言]` 信心細微調 + 即時:footer slider step=0.01(連 +0.01 兩次門檻變 0.02 量);`[+]`/`[−]` 鈕各 ±0.05;改門檻即時反映「顯示 k/總 框」k(承接 M7a-AC5,此處驗 step 細度與 −/+ 鈕)。
- **M7b-AC9** `[E2E可斷言]` 焦點守衛:點 Command Bar 跳頁 number_input 取得焦點後按 `1`/`2`/`3`,**verdict 不變**(熱鍵被守衛擋下,鍵進 number_input);點開 viewer 後同鍵才生效。**(沿用 spike 命題5。)**
- **M7b-AC10** `[E2E可斷言]` 判定單一真相:用熱鍵 `1` 設 verdict 後,Rail 的 verdict 控制顯示同值;反之用 Rail 改 verdict 後再 `u` 也能撤(同一 undo 軌跡);收合 Rail 後熱鍵 `2` 仍能改 verdict(verdict 寫入不只掛 Rail widget)。
- **M7b-AC11** `[效能量測]` 連切 per-image 成本(PerfA):連按 `→` 20 次,P95 render/nav_ms < 門檻(初值 1200ms,PG 量後校準)。**[效能量測]**。

### M7c — 進階(linked-viewport 比較 / 縮圖牆虛擬化 / 窄載體 RWD / DZI 自動瓦片)

- **M7c-AC1** `[E2E可斷言]` linked-viewport 並排:工具台「比較」一鍵開 `linked_compare`,出現**並排雙 canvas**(compare frame ≥2 canvas);在 A 邊 zoom 後 B 邊 `getZoom(true)` **同步**改變(linked,差 < 容差)。
- **M7c-AC2** `[E2E可斷言]` 比較沿用主 viewer viewport:主 viewer 放大到 z0 後開比較,比較雙 viewer 初始 `getZoom(true)` ≈ z0(linked 到主舞台;差 < 容差);blink 模式存在(A/B 切換,單 canvas)。
- **M7c-AC3** `[E2E可斷言]` 縮圖牆虛擬化:大資料夾下(E2E 可用既有 8 張驗「窗機制存在」、或 PM 造 >50 張臨時集)thumbwall iframe 內**已載入縮圖 `<img>` 數 ≤ 視窗大小(W+2B)**,非 = total;捲動後窗外項補載(`img` 數仍受窗界)。小資料夾(≤窗)退化為全載(向後相容)。
- **M7c-AC4** `[效能量測]` 虛擬化 per-image 成本(PerfA 在大集):>窗大小的資料夾下連切 per-image render P95 < 門檻(與 M7b-AC11 同手段,驗「整牆不隨 total 線性膨脹」)。**[效能量測]**。
- **M7c-AC5** `[效能量測]` 改門檻不重建整牆(PerfC):footer slider 改一格,`data-thumb-recalc` 增量 ≤ 窗大小且 < total。**[效能量測]**。
- **M7c-AC6** `[E2E可斷言]`(+`[截圖實證]`) 窄載體 RWD:模擬窄寬(`page.set_viewport_size({width:1000,...})` 或注入 `ss.viewport_w`)後,Rail 收成底部 strip(verdict 1/2/3 icon 一行可見、原右欄 0 寬);截圖確認版面不破。斷點數值 PG 量 nativeApp iframe 後校準。
- **M7c-AC7** `[E2E可斷言]`(+`[截圖實證]`) DZI 自動瓦片(**若未降級**):對 `w*h > 門檻` 的大圖,主 viewer **自動**走 tiles 模式(viewer frame `viewer.source` 為自訂 tile source / 多瓦片請求,hover HUD 不含 RGB 降級);使用者無手動開關。**若 §3.9 量測判定降級**,本 AC 改驗「手動 DZI 開關仍在工具台可用 + 設計已記錄降級決策」(見 M7c-AC8)。
- **M7c-AC8** `[效能量測]`(誠實降級判準) DZI 決策有量測:PG 量臨界大圖「建金字塔+編碼」耗時並寫入探針/報告;若使切張 P95 超門檻 → 誠實標記「自動瓦片降級為手動」並維持 M5 手動開關(此時 M7c-AC7 走降級分支)。**本 AC 驗「決策是被量測 + 記錄的,不是默默跳過」**。**[效能量測]**。
- **M7c-AC9** `[效能量測]` 未召喚層 0 計算(PerfB):工具台未展開時連切 N 次,`data-tool-calls`(DZI/compare/framecompare/simhash/embcluster 重算計數)恆 0;展開對應 tab 操作後才 >0。**[效能量測]**。

### 右鍵釘選 hover 點(§3.12,2026-07-04 新增)

- **AC-pin1** `[E2E可斷言]` 在主 viewer 畫布上對某已知影像座標 dispatch `contextmenu` → HUD 出現新增一行含該座標(如 `x=600, y=450`)與 RGB,且**瀏覽器原生右鍵選單未出現**(`e.preventDefault()` 生效,可用「該事件的 `defaultPrevented === true`」或「頁面 DOM 內無原生 context menu 元素」代理斷言)。
- **AC-pin2** `[E2E可斷言]` 釘選後把滑鼠移到別處(觸發一般 `mousemove` hover)→ HUD 內**釘選那一行文字不變**(與 hover 列是兩個獨立、同時並存的欄位;移開滑鼠不會讓釘選消失)。
- **AC-pin3** `[E2E可斷言]` 在另一個已知座標再次 `contextmenu` → HUD 的釘選行**更新為新座標**(覆蓋,而非新增第二行/清單)。
- **AC-pin4** `[E2E可斷言]` 導覽到下一張圖後,HUD **不再含**釘選行(新圖清空舊釘選;`buildViewer` 換圖生命週期自然重置)。
- **AC-pin5** `[E2E可斷言]`(可選,視覺代理)釘選後 viewer 內出現一個新增的 overlay 元素(與既有 `.roi-ov`/`.det-ov` 用不同 class 名,計數 `viewer.currentOverlays`長度較釘選前 +1,或直接查詢新 class 選擇器計數 ==1)。

### Focus Object 模式(§3.13,2026-07-04 新增)

> 樣本集數值沿用 conf_range 系列 AC 已釘死的分布(見 §7):`lot42_frame_000` 最高信心框 conf=0.91 bbox=[180,135,360,315];`lot42_frame_001` 唯一框 conf=0.77 bbox=[20,20,60,60];`lot42_frame_002/003/004`、`wafer16_000/001/002` 皆 0 偵測。

- **AC-focus1** `[E2E可斷言]` 導覽到 `lot42_frame_000`(name 排序下第 1 張),開啟 Focus Object toggle → viewer `getZoom(true)` 顯著大於開啟前(fit 狀態 zoom≈1.0),且可視範圍(`viewport.getBounds` 換算回影像座標)包住 bbox `[180,135,360,315]`(含 §3.13 留白,允許容差)。
- **AC-focus2** `[E2E可斷言]` 開啟狀態下切到下一張(`lot42_frame_001`,唯一框 conf=0.77)→ 自動重新聚焦到該圖的框 `[20,20,60,60]`(可視範圍改變、對應新框,非停留在上一張的視角——這是實作時抓到的真 bug,見 §4.l 附記)。
- **AC-focus3** `[E2E可斷言]` 開啟狀態下切到 0 偵測圖(`lot42_frame_002` 等)→ `getZoom(true)` 回到 fit 狀態(≈1.0,容差內),**不得**停留在前一張聚焦時的高倍率(§4.m 三態契約的存在理由,實作時抓到的真 bug)。
- **AC-focus4** `[E2E可斷言]` 關閉 Focus Object toggle 後,行為回到 M7a 既有的『zoom/pan 跨切張保存』(不強制 fit、不強制聚焦),即關閉後的切張行為與本功能上線前逐位元組相同(向後相容)。

---

## 6. 語義界線(誠實標註,防 false-green 與誤解)

- **autosave ≠ 絕對零遺失**:切張前 flush + 改值即時寫已涵蓋連切遺失(User-role 第4點主訴);但「改值同一 run 內直接關閉/崩潰」在 Streamlit rerun 模型下不在保證內。文件須讓使用者知道「正常切張/undo 路徑零遺失,硬關不保證」。
- **hover RGB = 8-bit 顯示值,非真值**(沿 M6):點擊才走 `imgio.value_at` 取原始(含 16-bit)真值。瓦片/自動瓦片模式 hover 不提供 RGB(無 client 全圖,降級)。
- **`maxZoomPixelRatio` 必須 = 24.0**:預設 1.1 會把 zoom 還原 clamp 回 fit,使 M7a-AC3 跨切張還原失效(spike 已驗,釘死)。
- **`j` 跳頁是務實降級**:元件 iframe 無法跨文件 focus 主文件的 number_input;`j` 落地為「捲到 + 高亮 Command Bar 跳頁框」,實際輸入仍需點該框(點進後焦點守衛確保不誤切張)。不假裝能直接搶焦點。
- **DZI 自動瓦片為可降級項**:成本量測超門檻則維持手動(§3.9 / M7c-AC8),這是設計允許的誠實降級,非 false-green。
- **linked-viewport 比較與 framecompare 並存、不互取代**:linked 是 client-side OSD viewport 連動(並排/閃爍);difference/blend/swipe/變化偵測仍是 server-side numpy(framecompare/framediff,工具台內),兩者語義不同、各司其職。
- **縮圖框是縮放後近似視覺提示**(沿 M6),不用於量測。

---

## 7. 被本次版面取代/搬遷的 M6 AC 清單(交代 PM 如何更新對應 E2E)

> 這是**合法的設計演進**(版面位移使部分 M6 斷言的定位前提改變),不是破壞契約。M6 的**行為**(hover RGB、放大上限、縮圖疊框、HUD、可點縮圖、總開關同管兩處)**全部保留可達**;只是**位置/定位**改變。PM 應在新 `test_viewer_workbench_e2e.py` 以新定位重寫,或調整既有 `test_viewer_ux_e2e.py` 的定位(由 /pm 裁量;`test_viewer_ux_e2e.py` 屬 PM 擁有的測試基建)。

| M6 AC | 原斷言前提 | M7 變化 | 取代/搬遷後對應 | PM 動作 |
|-------|-----------|---------|-----------------|---------|
| **M6-AC16** | 「顯示偵測框」checkbox + 「信心門檻」slider 在 **st.title 之下、三欄牆之前** | 控制搬到 **viewer-footer**(三欄牆內、viewer 下方)而非 title 下方 | **M7a-AC1 / M7a-AC5**(footer 常駐,sidebar 外) | 重寫定位:不再斷言「title 下、牆之前」,改斷言「footer 區、sidebar 外、viewer 下方」 |
| **M6-AC8(zoom% 來源)** | HUD zoom% 來自固定 height=600 的 viewer | viewer height 動態(auto_height ~720) | **M7a-AC7 + 保留 HUD zoom% 文字斷言** | zoom% 文字斷言保留;不綁固定高 |
| **M6-AC4 / AC10(hover/框命中)** | viewer 在「中欄」、canvas 定位法 | 版面位移、固定 key viewer(iframe 不 remount) | 行為保留,**定位沿用 `_find_viewer_frame`** | 確認固定 key 後 frame 偵測仍穩(canvas 數不變);hover/框命中斷言內容不變,僅確保切張後 frame 不換 |
| **M6-AC12(點第2張縮圖→進度)** | thumbwall 全載、idx-key viewer | 縮圖牆虛擬化 + 固定 key viewer | **M7c-AC3 + 保留點擊→進度斷言** | 點擊→進度斷言保留;大集下改用「窗內可見縮圖」定位(窗外佔位不可點) |
| **M6-AC11(縮圖是可點 img)** | 全部縮圖都是 img | 虛擬化後窗外是佔位塊(img:None) | **M7c-AC3** | 斷言改為「可見縮圖(窗內)為可點 img、數 ≤ 窗」,而非「= total」 |
| **M6-AC17/AC18(sidebar 無重複/總開關同管)** | 開關在 title 下 | 開關在 footer | **保留語義**(sidebar 仍無重複、一個開關同管縮圖+viewer) | 定位改 footer;同管兩處的斷言內容不變 |

> 其餘 M6 AC(AC1 禁選圖、AC2/AC3 放大上限、AC5/AC6 hover/瓦片降級、AC7/AC9 HUD meta/16-bit 語義、AC13 徽章、AC14/AC15 縮圖疊框)**行為與斷言內容不變**,僅可能因 viewer 固定 key / footer 搬遷而需微調 frame/控制定位。**既有 `test_app_e2e.py` 核心(載入/進度/canvas/切張)精神續綠**,可能因 Command Bar 鈕文字/進度文字位置微調定位(⟵/⟶ 鈕文字保留「上一張」「下一張」語義供既有斷言)。

### 設計演進(2026-06-26,User 回饋:頂列資訊徽章整條移除)

User 實跑後要求把頂列 Command Bar 的**資訊徽章**「`N/total · 判定 {verdict} · 偵測N框 · 📄檔名`」(原 §6 ASCII 版面與 M7a-AC1 內的 caption)**整條移除**。這是**合法的設計演進、行為保留**:位置(N/total)與檔名其實仍在 viewer 內 HUD 可見(M6-AC7);verdict 仍由鍵盤 1/2/3 設定、寫入 sidecar。對應契約調整:

| 受影響 | 原斷言前提 | 本輪變化 | 取代後對應 |
|--------|-----------|---------|-----------|
| **M7a-AC1**(偵測N框 caption) | Command Bar 含可見「偵測N框」caption | 該 caption 隨資訊徽章移除 | 改驗常駐「**顯示 k/n 框**」caption(仍證偵測數在主舞台可見) |
| **§5 P1 進度錨點**(可見「N / 8」) | E2E ready/進度讀可見徽章文字「N / total」 | 可見徽章移除 | P1 探針新增 `data-idx`/`data-total`;`_wait_app_ready`/`_progress_index` 改讀探針(主文件 DOM 機器讀面) |
| **M7b-AC10**(verdict 單一真相) | 熱鍵設 verdict 後「頂列徽章顯示同值」 | 頂列 verdict 徽章移除(Rail 早已移除) | 單一真相 = sidecar + P1 探針 `data-verdict`;驗法改為熱鍵→探針反映、再按仍可改(不依賴任何已移除 widget/徽章) |

> 跨 5 個 E2E 檔(m7a/m7b/app_e2e/viewer_ux/compare_e2e)的 `_wait_app_ready`/`_progress_index`/點縮圖→進度/「有框」代理 全部從「可見徽章文字」改讀 P1 探針 `data-*` 或常駐「顯示 k/n 框」caption。行為(進度/verdict/偵測數)全保留,僅**觀測位置**從可見徽章 → P1 探針(設計 §5 P1 早已是機器讀面)。**無斷言被放寬,僅重新歸位**。

### 設計演進(2026-07-04,User 回饋:信心門檻要卡縮圖牆、且要雙邊)

> 需求來源:`1_user_needs/03_confidence_range_thumbwall_triage.md`。**這是契約演進**(單張檢視模式的信心門檻從「單值、只濾主圖疊框」升級為「雙界、同時濾影像清單」),不影響比較模式(其 `cmp_conf` 已是雙界,見 §7.2/24_modeldiff.md,本輪未動)。`overlay.py`/`filtersort.py` 簽名**不變**(沿用 §8 module 邊界承諾)——雙界過濾比照既有 `_cmp_filter`(§7.2 app inline 慣例)以 app 層內嵌邏輯達成,不擴充 `overlay.filter_detections` 的單下界契約。

**契約變更**:

1. **`footer_conf_thr`(session_state key)語義變更**:值型別由 `float` 改為 `tuple[float,float]`(`(lo,hi)`)。footer slider 改為 `st.slider("信心門檻", 0.0, 1.0, (lo,hi), 0.01, key="footer_conf_thr")`(Streamlit 原生 range-slider,兩個滑塊)。
2. **新增影像清單 triage 述詞**(app 層,套用於 `shown_items` 組裝的 `_passes(it)`):

   ```python
   def _in_conf_range(it, lo, hi):
       if lo <= 0.0 and hi >= 1.0:
           return True  # 全開 = 向後相容關閉點:不 triage(含 0 框圖在內,清單與現狀一致)
       return any(lo <= float(d.get("conf", 0.0)) <= hi for d in it["detections"])
   ```

   `_passes` 回傳 `False` 者**不進入** `shown_items`(不是「顯示但淡化」)——沿用既有「篩選後清單為空 → `st.warning` + `st.stop()`」機制(app.py 既有邏輯,無需新錯誤路徑)。
   - **AskUserQuestion 裁決(2026-07-04,關鍵發現後二次確認)**:樣本集 8 張圖僅 2 張(`lot42_frame_000`/`001`)有偵測 JSON,其餘 3 張 lot42 圖 + 全部 3 張 wafer16(16-bit)皆為 0 偵測。若「0 框恆濾掉」不設全開例外,**預設(未動 slider)就會讓這 5 張圖從單張模式清單消失**,破壞現有 42 項 E2E 對 `TOTAL=8` 的假設、且使 16-bit 測試圖在單張模式下預設不可達——真實審圖場景也一樣:模型判斷「乾淨無缺陷」或「根本沒跑出偵測檔」的圖會預設消失、滑鼠鍵盤切不到。User 二次確認**採「全開時不 triage」**:0 框圖只在使用者**主動**把下界拉高於 0 或上界拉低於 1(即偏離全開)時才被濾除;維持全開時清單與現狀行為一致(含 0 框圖),不破壞既有測試基準與預設可達性。
   - **推論**:一旦偏離全開(`lo>0.0` 或 `hi<1.0`),`detections == []` 的圖恆不滿足 `any(...)`(空清單無元素可比對)→ 此時恆被濾除,不需要獨立的「排除 0 框圖」開關——這與 User 原始裁決「0 框一併濾掉」一致,只是**限定生效範圍為「使用者已縮小範圍」時**,而非任何時刻皆生效。
3. **主圖疊框 `kept` 改雙界**(取代原 `overlay.filter_detections(cur["detections"], conf_threshold=conf_thr, classes=overlay_classes)` 單下界呼叫):比照 `_cmp_filter` 的內嵌雙界寫法,`kept = [d for d in cur["detections"] if lo <= float(d.get("conf",0.0)) <= hi and (not overlay_classes or d.get("cls") in overlay_classes)]`。`overlay.py` 模組本體不改。
4. **thumbwall 縮圖燒框不受影響**:`_TW_CONF=0.0` 固定值(§3.7 效能設計,縮圖恆燒全部框)維持不變;改變的是「哪些圖的縮圖會出現在牆上」(由 `shown_items` 已 triage 決定),不是「牆上每張縮圖燒哪些框」。
5. **P1 探針契約變更**:`data-conf`(單值)拆為 `data-conf-lo` / `data-conf-hi`(各可解析為 0~1 浮點數)。原讀 `data-conf` 的測試改讀兩者。

**樣本集實際 conf 分布(逐字採用,AC 數值依此釘死;來源:`sample_images/lot42_frame_000.json`/`001.json`,git-tracked、非 `make_samples.py` 產生)**:
- `lot42_frame_000`:3 個偵測,conf = {0.91(scratch), 0.62(dent), 0.40(edge)}。
- `lot42_frame_001`:1 個偵測,conf = {0.77(scratch)}。
- 其餘 6 張(`lot42_frame_002/003/004`、`wafer16_000/001/002`):**0 偵測**。
- `TOTAL_ALL = 8`(資料夾總圖數,含 0 偵測圖,即 M7b `TOTAL` 常數)。

**新增 Acceptance Criteria**(`[E2E可斷言]`,數值逐字釘死、禁代理式 AC):

- **AC-conf1**:Command Bar 信心門檻控制為 range slider(該 slider 對應 2 個滑塊 thumb 元素,而非單一滑塊)。
- **AC-conf2**(向後相容關閉點):信心範圍維持預設全開 `(0.00, 1.00)` → `data-total == 8`(等於 `TOTAL_ALL`,0 偵測圖**仍在清單內**;此為既有 42 項 E2E 賴以成立的前提,**不得回歸**)。
- **AC-conf3**(下界隔離):設 `lo=0.80, hi=1.00`(偏離全開)→ 只有 `lot42_frame_000`(0.91∈[0.80,1.00])滿足 → `data-total == 1`;`lot42_frame_001`(0.77<0.80)與全部 0 偵測圖被排除。
- **AC-conf4**(上界隔離,刻意選一組使存活圖與 AC-conf3 不同,證明非巧合):設 `lo=0.65, hi=0.80`→ 只有 `lot42_frame_001`(0.77∈[0.65,0.80])滿足 → `data-total == 1`;`lot42_frame_000` 的三個 conf(0.40/0.62/0.91)皆不落在 `[0.65,0.80]` 內、故被排除,全部 0 偵測圖同樣排除。
- **AC-conf5**(空集合邊界,含防卡死):設 `lo=0.95, hi=1.00`(高於樣本集最大 conf 0.91)→ `data-total == 0`,既有「沒有符合篩選條件的影像」`st.warning` 出現,app 不崩潰;**且信心 slider(2 個 thumb)仍存在於畫面上、仍可操作**(§4k)——把下界拉回 `<=0.91` 後,清單應恢復非空(可用「再把 slider 拉回全開後 `data-total == 8`」驗證使用者確實能自行脫困,不需重新整理頁面)。
- **AC-conf6**(探針型別):`data-conf-lo`/`data-conf-hi` 皆存在且可解析為 `float`;調整 slider 後兩值隨之更新為新設定值。
- **AC-conf7**(主圖疊框雙界、與清單 triage 獨立驗證):導覽到 `lot42_frame_000`(清單內索引固定,設全開避免被 AC-conf3/4/5 排除),設 `lo=0.00, hi=0.50` → 該圖仍在清單內(0.40∈[0,0.50]滿足 triage)但 `data-shown-k == 1`(只有 0.40 的框通過雙界,0.62/0.91 被上界濾掉)、`data-shown-n == 3`(該圖總偵測數不變)——證明 `kept` 的雙界對主圖疊框生效,且與清單層級的 triage 是兩個獨立、可分別斷言的機制。

**PM 動作**:`test_m7b_e2e.py` 讀 `data-conf` 的斷言(AC8 一帶)改讀 `data-conf-lo`/`data-conf-hi`;新增/擴充 E2E 覆蓋 AC-conf1..7,直接沿用上述已釘死的樣本集數值與 conf 分布,**不需新增/修改 fixture**(`fixtures/make_samples.py`、`sample_images/*.json` 皆不變)。

#### 再演進(2026-07-04 同日,User 回報「選了 Object 類別後,某圖沒有該類別的框卻仍留在清單、右邊自然畫不出框」)

`_in_conf_range` 擴充第三參數 `classes`,與清單觸發條件從「只看信心」改成「信心 **且** 類別同時滿足(同一筆偵測)」,語義與 `_cmp_filter`(`kept` 用的框級過濾)完全一致——不再是「信心管清單、類別管畫框」兩套各管一半的邏輯:

```python
def _in_conf_range(it, lo, hi, classes=None):
    if lo <= 0.0 and hi >= 1.0 and not classes:
        return True  # 全開且未選類別 = 向後相容關閉點
    return len(_cmp_filter(it["detections"], lo, hi, classes)) > 0
```

**衍生的循環依賴與解法**:Object 類別下拉的選項(`_all_classes`)以往是從 `shown_items`(已用信心+類別雙重過濾後的結果)推導——若類別本身也觸發 triage,這會自我循環(選了某類別後,選項只剩它自己)。解法:`_all_classes` 改由「只套信心範圍、不套類別」的中繼結果 `_conf_only_items` 推導,`cls_filter` 的消毒(sanitize)也提前到 `shown_items` 組裝之前執行(與信心門檻同樣的「先讀後畫」慣例)。

**防卡死擴充(§4.o)**:清單篩空的復原分支原本只重畫信心 slider,現在**必須同時重畫 Object 類別下拉**——否則類別選擇單獨造成篩空時,使用者看不到能選回「全部」的控制,一樣卡死。

**新增 AC**:
- **AC-conf8**:選 Object 類別「dent」(僅 `lot42_frame_000` 含 dent,conf=0.62)→ `data-total == 1`;選回「全部」→ 完全恢復 `data-total == 8`(可逆、無殘留狀態)。
- **AC-conf9**(疊加驗證,證明非兩套獨立邏輯):設信心下界 `lo=0.65`(> dent 的 0.62)+ 選類別「dent」→ 清單應為空(兩條件疊加在同一筆偵測上都不滿足),既有「沒有符合篩選條件的影像」警告出現、且信心 slider 與 Object 類別下拉皆仍可操作脫困(§4.o)。

---

## 8. 與其他模組的邊界(防越權)
- **不重寫**繪框/篩選/比較/標記邏輯:一律複用 `overlay.draw`/`filter_detections`、`framecompare.*`/`framediff.*`、`sidecar.*`、`tagging.*`、`imgio.*`、`dzitiles.*`。本變更**不**改這些模組契約。
- **不碰** `conftest.py` / `fixtures/` / `verify/` / `.unet/`(PM 擁有測試基建;本檔只描述 E2E + 效能量測**需求**,落成由 /pm)。效能探針 DOM 由 app(PG)寫、conftest/page fixture 不需改(Playwright 讀 `data-*` 即可)。
- 對外承諾:`osd_viewer` 新參數全可選且向後相容;`thumbwall` 新 `window` 可選、None=M6 行為;`compare.py`/`compare_component/` 為**新增**;`app.py` 版面重組不破壞既有區塊功能可達性。**無 Python 單元 gate,機器判綠 = playwright E2E + 截圖實證 + 效能量測三者皆過**。
