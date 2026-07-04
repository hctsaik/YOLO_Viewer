# 設計:compare 雙區塊比較模式(V3 比較 — User 細化規格)

> `/architect`。**Tier B GUI 整合**(動 `5_PG_Develop/app.py`,複用既有 framecompare/imgio/thumbwall 慣例)。
> **無新 Python 純邏輯函式**(差異/混合一律複用 `framecompare`;選圖/縮圖複用既有 `_thumb`/`_display_rgb`/`_resize_to`)。
> **機器判綠 = 真實 playwright E2E 全綠 + 截圖實證**(`4_PM_Feedback/test_compare2_e2e.py`,`@pytest.mark.e2e`)。
> 上游:User 實跑後細化比較 UI 規格(ROADMAP 2026-06-26 決策日誌);dual-OSD 連動 spike 已 PASS 為『要連動時』的已驗底座,
> **但本規格未要求 viewport 連動** → 本切片用 server-side `st.image`(完整圖)+ framecompare,linked OSD 列為日後可選升級。

---

## 1. 目的與 User 規格(逐字對應)

User 原話:「比較功能點下去的時候,右半部變成是分左右兩個大區塊。左區塊的上半部是縮圖,可以透過左右去切換縮圖,
下半部是完整圖。然後右區塊也是這樣的感覺。然後有一個做差異以及混合的功能,對於左右的圖去運算。」

收斂版面:
```
[頂列 Command Bar(不變)]
[🔀 比較模式 toggle]  ← 點下去進入比較
─ 比較模式 OFF:現況(縮圖牆 | 單一主 viewer)──────────────────
─ 比較模式 ON:stage 中欄 → 左右兩大區塊 ───────────────────────
┌─ 區塊 A ───────────────┬─ 區塊 B ───────────────┐
│ ◀ [縮圖條:○ ● ○ ○ ○] ▶ │ ◀ [縮圖條:○ ○ ● ○ ○] ▶ │  ← 上半:縮圖,←/▶ 或點選切換
│ A: lot42_000.png (1/8)  │ B: lot42_001.png (2/8)  │
│ ┌────────────────────┐ │ ┌────────────────────┐ │
│ │   A 完整圖           │ │   B 完整圖           │ │  ← 下半:完整圖
│ └────────────────────┘ │ └────────────────────┘ │
└────────────────────────┴────────────────────────┘
┌─ 差異 / 混合運算(左A vs 右B)────────────────────────────────┐
│ 運算:[差異] [混合]   (混合時:alpha ━━●━ 0.5)                 │
│ ┌──────────────────────────────────────────┐                 │
│ │  運算結果圖(framecompare.difference/blend)│                 │
│ └──────────────────────────────────────────┘                 │
└────────────────────────────────────────────────────────────────┘
```

- **區塊 A / B 各有獨立選圖索引**(`ss.cmpA` / `ss.cmpB`,互不影響),預設 A=目前圖、B=下一張。
- 上半縮圖條:顯示『以選中圖為中心的視窗(W 張)』小縮圖,選中者高亮;`◀`/`▶` 步進、點縮圖直接跳選。
- 下半完整圖:`st.image(_display_rgb(該圖))`(完整影像,等比縮放至欄寬)。
- 差異/混合:對 A、B 兩圖運算(B 先 `_resize_to` 對齊 A 形狀);差異=`framecompare.difference`,混合=`framecompare.blend(A,B,alpha)`。

---

## 2. 工具台收斂(User:其餘功能全移除,只留比較)

User 明示「這些功能全部都移除,我都不要 …… 留下這個比較」→ 移除既有「🧰 工具台」expander 內
**標記 / 相似 / 聚類 / DZI / 漏檢 / 匯出** 六個 tab,以「🔀 比較模式」單一入口取代。
- 被移除者**僅是 UI 入口**;底層模組(simhash/embcluster/dzitiles/missedq/casepkg/cocoio/htmlreport)程式碼保留,可日後重新接線。
- verdict / 狀態 / bookmark 仍走鍵盤(1/2/3·r·b/空白)+ 頂列徽章(單一真相,不依賴被移除的標記 tab)。
- **誠實附記**:Tags/Comment/ROI 明確編輯 UI 與 匯出 UI 隨標記/匯出 tab 移除而暫時不可達(User 裁決;模組仍在,可回退重接)。

---

## 3. 對外契約 / 機制(虛擬步驟)

### 3.1 進入點與 session_state
```
ss.compare_on : bool        # 🔀 比較模式 toggle(預設 False → 現況單 viewer,既有 E2E 不受影響)
ss.cmpA : int               # 區塊 A 選中影像 index(進 shown_items),預設 = ss.idx
ss.cmpB : int               # 區塊 B 選中影像 index,預設 = min(total-1, ss.idx+1)
ss.cmp2_mode : "差異"|"混合"
ss.cmp2_alpha : float       # 混合 alpha
```
- toggle 在頂列 Command Bar 之後、stage 之前渲染 → `ss.compare_on` 在中欄渲染前已知。
- **向後相容**:`compare_on` 預設 False → 中欄走現況單一 viewer,既有 M6/M7a/M7b/app E2E 全不受影響(它們不開比較)。

### 3.2 中欄分支
```
with center:
    if ss.compare_on:  _render_compare()       # 雙區塊 + 差異/混合
    else:              <現況單一 osd_viewer + 鍵盤 + last_click>
```
左欄縮圖牆(thumbwall)維持(主導覽);比較模式只改中欄。

### 3.3 區塊渲染(A / B 對稱)
- 索引夾界 `0..total-1`;`◀`/`▶` 改 `ss.cmpA`/`ss.cmpB` 後 `st.rerun()`。
- 縮圖條:視窗 `[max(0,i-W//2) .. min(total, start+W))`(W 預設 5);每格 `st.image(_thumb(path,max_px≈70))` + 一顆選取鈕(選中顯示 `●`、其餘 `○`),點擊設該 index。
- 完整圖:`st.image(_display_rgb(path), width=stretch)`,caption=`{tag} 完整圖`。
- 區塊標題 caption:`{tag}: {name} ({i+1}/{total})`(供 E2E 讀選圖變化)。

### 3.4 差異 / 混合(對 A、B 運算)
- `A = _display_rgb(shown_items[ss.cmpA].path)`;`B = _resize_to(_display_rgb(shown_items[ss.cmpB].path), A.h, A.w)`(framecompare 要求同形)。
- `差異` → `framecompare.difference(A, B)`,`st.image(res, caption="差異 |A−B|")`。
- `混合` → `framecompare.blend(A, B, alpha)`,`st.image(res, caption="混合 A/B")`;alpha slider step 0.05。
- **誠實界線**(沿 M6 §6):A/B 不同尺寸時 B 經 `_resize_to`(插值)→ 差異為『縮放後近似』非像素真值;caption 在尺寸不一致時加註。

### 3.5 效能(沿用既有閘門精神)
- 比較模式 OFF → `_render_compare` 完全不呼叫(中欄走 else 分支)→ 重函式(framecompare/縮圖批)0 計算(同 PerfB 精神,連切不卡)。
- 縮圖條只算『視窗 W 張』(複用 `_thumb` 的 cache);完整圖/差異/混合走 `_display_rgb` cache + `framecompare`(server numpy)。

---

## 4. 邊界條件
a. `total < 2`:比較模式仍可開,但 A、B 可指同一張(差異=全 0、混合=原圖);caption 提示『A、B 為同一張』。
b. A、B 指同一張:合法(差異全 0);不崩。
c. 索引到邊界:`◀`/`▶` 夾界 no-op,不報錯。
d. A/B 尺寸不同:`_resize_to` 對齊 + caption 註明『差異為縮放後近似』。
e. 比較模式切回 OFF:中欄還原單一 viewer(`cv_viewer` 固定 key 仍在,zoom/pan 還原機制不受影響)。
f. 縮圖條視窗在資料夾頭/尾:夾界,視窗不越界(`start=max(0,min(i-W//2, total-W))`)。

---

## 5. Acceptance Criteria(E2E,標 [E2E可斷言] / [截圖實證])

> E2E 入口沿用既有 conftest `app_server` + `page`。比較預設 OFF;測試先開「🔀 比較模式」toggle 再驗。

- **AC1** `[E2E可斷言]` 進入比較:勾「🔀 比較模式」toggle 後,出現**兩個完整圖**(caption 含「A 完整圖」與「B 完整圖」)+ 差異/混合「運算」radio。關閉 toggle → 兩區塊消失、單一 viewer canvas 回來。
- **AC2** `[E2E可斷言]` 區塊各自選圖:區塊 A 按 `▶`,A 標題 caption 的圖名/序號改變(`A: … (i/total)` 的 i +1);區塊 B **不受影響**(B 序號不變)→ 證兩塊獨立索引。
- **AC3** `[E2E可斷言]` 縮圖條切換:區塊 A 縮圖條至少有 2 張小縮圖(`<img>`);點某一格選取鈕後 A 選中圖改變(caption 序號變)。
- **AC4** `[E2E可斷言]` 差異運算:`運算`選「差異」→ 出現 caption 含「差異」的結果 `st.image`(`<img>`)。
- **AC5** `[E2E可斷言]` 混合運算:選「混合」→ 出現 alpha slider(label 含「alpha」或「混合」)+ caption 含「混合」的結果圖;改 alpha 一格不報錯、結果圖仍在。
- **AC6** `[E2E可斷言]` 向後相容:比較模式 OFF(預設)時,頂列「上一張/下一張」鈕 + 單一 viewer canvas 仍在(既有 M7a 版面不被破壞)。
- **AC7** `[截圖實證]` 版面:截圖確認左右兩大區塊(各 縮圖條 + 完整圖)並排、下方差異/混合結果區;由 `/ux-test` 或人視覺驗收。

---

## 6. 與其他模組邊界(防越權)
- **不重寫**差異/混合:複用 `framecompare.difference` / `framecompare.blend` + `app._resize_to`(同形)。
- **不碰** `conftest.py` / `verify/` / `.unet/`;不改 `viewer.py` / `index.html`(本切片不用 linked OSD)。
- 既有 M7a/M7b/viewer_ux/app E2E:比較預設 OFF → 行為不變,須全數續綠(回歸保契約)。
- 被移除的 6 個工具台 tab:**僅移除 UI 入口**,底層模組與既有單元測試(simhash/embcluster/dzitiles/missedq/casepkg/cocoio/htmlreport)不動、續綠。

---

## 7. 設計演進(2026-06-26 第二輪 — User 實跑後細化:點圖選取 + 橫向可捲縮圖條 + 雙界信心 + 類別篩選)

User 實跑 §1 版本後再給規格(逐字):「希望能點圖就可以,不需要下面那個點的區域。如果圖被選到,就會有框來讓我知道他被選到。
圖上面會有檔名,圖的順序是用檔案名稱。底下有一個 scroll bar,可以快速拉到特定某一張圖。左右都要有信心度的 filter,
但改成是兩個上下界都能夠設定。有可能一個畫面有多個 Object,因此也要能夠選特定的 object type。」

### 7.1 縮圖條:窗化 ◀/▶/○● → **橫向可捲、整圖可點**(取代 §3.3 縮圖條與 §1 ASCII 的 ○/●)
- **擴充 `thumbwall` 加 `horizontal=True`**(向後相容:預設 False = 現況縱向縮圖牆,主縮圖牆 / viewer_ux E2E 完全不變)。
  橫向模式:`#wall{flex-direction:row; overflow-x:auto; flex-wrap:nowrap}` → **原生水平捲軸**(滿足「下方 scroll bar 快速拉到某張」);
  每格固定寬(如 96px)、整列渲染**全部 N 張**(非視窗)。`setFrameHeight` = 縮圖高 + 捲軸 + 檔名標。
- **點圖即選**:沿用 thumbwall「整張 `<img>` 可點 → 回 index」;**移除** ◀/▶ 步進鈕與 ○/● 選取鈕(§1 ASCII 的點選區整塊拿掉)。
- **選中有框**:沿用 thumbwall `.cell.sel`(黃框)= 選中標示(滿足「被選到就有框」)。
- **檔名在圖上**:thumbwall `corner` label 由「序號」改放**檔名**(`it.label = name`);順序 = `shown_items`(imageset 已自然檔名排序)。
- **偵測數徽章**保留(`nd`)。A/B 各一條橫向 thumbwall,key=`cmp_A_wall`/`cmp_B_wall`;點 A 條只改 `ss.cmpA`、B 條只改 `ss.cmpB`(獨立)。

### 7.2 每區塊:信心**雙界** range + **類別**多選(過濾該塊完整圖上疊的偵測框)
- 完整圖由「純圖」升為「**疊框圖**」:`overlay.draw(_display_rgb(path), kept, draw_label=True, conf_threshold=0.0)`。
- **conf 雙界**:per-block `st.slider("信心門檻(下界,上界)", 0.0, 1.0, (lo, hi), 0.01)` 回 `(lo, hi)`;`ss.cmpA_conf`/`ss.cmpB_conf`,預設 `(0.0, 1.0)`。
- **類別多選**:per-block `st.multiselect("Object 類別(空=全部)", classes_present)`;`classes_present` = 該塊當前圖 detections 的 `cls` 去重排序;空選=不過濾。
- **過濾(app inline,不動 overlay 契約)**:`kept=[d for d in dets if lo<=float(d.conf)<=hi and (not sel or d.cls in sel)]`。
  > 為何 inline:`overlay.filter_detections` 契約只有單一下界 `conf_threshold` + `classes`(白名單);雙界上界由 app 端過濾,**不擴充 overlay**(避免動 `test_overlay.py` 釘死 AC)。class 白名單則直接餵 overlay/inline 皆可,統一走 inline。
- **diff/混合不變**:仍對**原始** `_display_rgb`(像素運算,與框/篩選無關;§3.4 誠實界線不變)。

### 7.3 AC 變更(對應 `4_PM_Feedback/test_compare_e2e.py`)
| AC | 原 | 本輪演進 |
|----|----|---------|
| AC2(各自選圖獨立) | 按 `▶` 改序號 | 改:**點 A 橫向 thumbwall 某格** → A 標題序號變、B 不變(▶ 鈕移除) |
| AC3(縮圖條) | 視窗 ≥2 小縮圖 + 點選取鈕 | 改:A 區塊**橫向 thumbwall iframe** 存在、含 ≥2 `<img>`;點某格 → A 序號變 |
| **AC8(新)** | — | A、B 各有 **conf 雙界 slider**(label 含「信心」;range slider 有兩個 handle) |
| **AC9(新)** | — | A、B 各有 **Object 類別 multiselect**(label 含「類別」或「Object」) |
| AC1/AC4/AC5/AC6/AC7 | — | 保留(完整圖 caption 仍在,現含疊框;diff/blend/向後相容/截圖不變) |

### 7.4 邊界補充
- 橫向 thumbwall:N 很大時整列渲染 + `overflow-x:auto` 仍順(縮圖是 cache 的 data URL,DOM 為輕量 `<img>`);若日後 N 破千再議虛擬化(YAGNI)。
- conf range `lo>hi`:`st.slider` range 天然保證 `lo<=hi`(同一控制兩 handle),不會反置。
- 類別多選選項取「**當前該塊圖**」的 cls:切圖後選項隨之更新;已選但新圖不含的 class → 該塊無框(合理,不崩)。
- thumbwall 橫向預設關 → 主縮圖牆(縱向)與 viewer_ux 的 AC11/13/15/18 全不受影響(回歸保契約)。

---

## 8. 設計取代(2026-06-26 第三輪 — User 釐清真意:比較=【兩個 model 對同一包資料】的覆蓋 triage)

> **§1–§7 的『兩張圖目視 diff/混合』為先前對需求的誤解,本節起取代。** User 原話:「我的 filter 是要濾掉
> 【所有的影像】,而不是對單一圖過濾。這是因為我想要透過【兩個 model】來對【同一包資料】做整理,有可能較弱的
> model 逮的資料更少。」→ 比較模式的 A/B = 兩個偵測 model 對同一影像集的結果;filter 對【整個影像集】triage。

裁決(AskUserQuestion):① **取代**舊 image-vs-image 比較(其 8 條 E2E 一併改寫,因它們驗的是被否決的設計);
② 主視圖 = **覆蓋率儀表板 + 分歧 triage 佇列**(點圖下鑽);③ **IoU 框級配對**(matched/only-A/only-B per box);
④ 兩 model 來源 = A 用現有(自動判定/覆寫)、新增一欄 model B 資料夾(留空=不比較),打錯路徑/缺檔以 **missing_b** 明示。

### 8.1 純邏輯底座
配對/收斂判斷抽成 **`modeldiff`(Tier A,設計 24_modeldiff.md,verify/gate.py modeldiff 判綠,31 測試)**:
iou / match(貪婪 IoU) / diff_image(每圖 status:agree/a_only/b_only/disagree/both_empty/missing_*) /
summarize / filter_images / queue。app 只呼叫、不重寫過濾邏輯(消雙份漂移),且把『缺檔 vs 0 框』鎖成不同 status。

### 8.2 app 整合(取代 _cmp_block/_render_compare)
- sidebar 新增「第二個 model 結果資料夾 B」;_item_for 每圖多讀 detections_b + a_present/b_present(os.path.exists 標註檔)。
- _render_compare 重寫:控制列(看哪種差異 selectbox / IoU 門檻 / 信心雙界 / Object 類別)→ 對 shown_items 全量算 diff_image
  → summarize 出儀表板「🔵A:n 框/張 · 🟠B · **B 比 A 少 ΔN 張/Δ框** · 只A/只B · B 缺檔 N」→ filter_images(mode)+queue
  出分歧佇列(橫向 thumbwall,狀態色標,點圖設 ss.cmp_sel 下鑽)→ 下鑽用 overlay.draw 疊兩色(A 藍 (0,160,255) / B 橘 (255,90,0))。
- 比較模式仍隱藏左主縮圖牆;framecompare/framediff 模組保留未用。
- P1 探針(設計 §5)新增 data-cmp-queue-n/only-a/only-b/missing-b/delta-imgs 供 E2E 穩定數字斷言。

### 8.3 E2E(取代,4_PM_Feedback/test_compare_e2e.py)
fixture:sample_images/model_b/(較弱 model B,只逮 frame_000 1 框、缺 frame_001)。AC1 進出比較;AC2 儀表板量化『B 比 A 少』+ delta_imgs≥1;
AC3 分歧佇列 + 下鑽雙色疊框(配對/只A);AC4 dataset triage(分歧佇列<全部、切『全部』張數增);AC5 缺檔 vs 0 框(missing_b≥1);
AC6 控制齊全;AC7 向後相容(預設 OFF 單 viewer);AC8 未填 model B 引導不崩。

> **回歸保契約**:比較預設 OFF → M7a/M7b/viewer_ux/app_e2e 不受影響;thumbwall 橫向(§7)續用、縱向主牆不動;
> overlay/viewer.py/index.html/conftest/verify 全不改;新增僅 modeldiff(純邏輯 gate)+ app 整合 + 改寫 compare E2E。

---

## 9. 設計取代(2026-07-05 第四輪 — User:比較改成【在縮圖牆標記兩張影像】疊圖,不再需要第二個資料夾)

> 需求來源:`1_user_needs/07_two_image_mark_overlay_compare.md`。User 原話:「我想要把原本的資料夾疊圖
> 功能改成是,我在縮圖牆裡面標註兩張影像來做疊圖就好(不再需要兩個資料夾)」。**§8 的『雙 model 覆蓋
> triage』被本節取代**——不是回到 §1-§7 的舊設計(那是獨立 A/B 選圖器並排),而是全新的「在**同一個**
> 縮圖牆上標記兩張影像」互動。AskUserQuestion 兩項裁決:①疊圖內容 = 像素疊合 **與** 偵測框疊合,可切換;
> ②雙 model 覆蓋率儀表板/分歧佇列**整個移除**(modeldiff.py/test_modeldiff.py 本體保留、比照
> framecompare/framediff 慣例可回退,只是 app.py 不再呼叫)。

### 9.1 移除項
- sidebar「第二個 model 結果資料夾 B」欄位、`model_b_folder` 解析、`_item_for` 的
  `detections_b`/`a_present`/`b_present`(連帶 `_label_exists` 一併移除,唯一呼叫者消失)。
- `_CMP_STATUS`/`_CMP_MODES`、覆蓋率儀表板、分歧 triage 佇列、`modeldiff.*` 呼叫、
  P1 探針 `data-cmp-queue-n`/`only-a`/`only-b`/`missing-b`/`delta-imgs`。
- `app.py` 的 `import modeldiff`(模組本體 `modeldiff.py` 與其 31 條單元測試**不刪**,
  `verify/gate.py modeldiff` 仍可判綠,僅與 app 整合斷開——同 framecompare/framediff 的既有慣例)。

### 9.2 縮圖牆標記機制(thumbwall 元件擴充,新增 `markable` 參數)
- `thumbwall_component/index.html` 每格新增第 4 個角標 `.cmpmark`(左下角,其餘三角已用:
  `.corner`=左上索引、`.mark`=右上⭐/✓、`.badge`=右下偵測數)。只在 `markable=true` 時渲染。
  - 未標記:顯示淡色「○」提示(可點,discoverable)。
  - 第 1 張標記:顯示「①」(藍色文字,呼應既有 A=藍 慣例)。
  - 第 2 張標記:顯示「②」(橘色文字,呼應既有 B=橘 慣例)。
  - 點擊 `.cmpmark` 自己的 handler 呼叫 `e.stopPropagation()`,送 `{type:'mark', index, n}`,
    不觸發整格既有的「點圖選取/導覽」click(該 handler 同步改送 `{type:'select', index, n}`)。
- `thumbwall.py` 包裝函式新增 `markable: bool = False` 參數;回傳值行為:
  `markable=False`(預設,向後相容既有呼叫)→ 回傳同舊版的 `int|None`;
  `markable=True` → 回傳 `{"type": "select"|"mark", "index": int}|None`,呼叫端自行分派。
- app 端 `ss.setdefault("cmp_marks", [])`(list[str],存 image `name`,非 index——排序/篩選可能
  改變 index,`name` 才是穩定 key)。`_toggle_cmp_mark(name)`:已標記則移除;否則附加,
  超過 2 張時 FIFO 踢掉最舊一張(不需要使用者先想好「取消哪一張」,永遠點了就有效)。
  主縮圖牆(`app.py` 主 thumbwall 呼叫處)傳 `markable=True`,依 `ev["type"]` 分派
  select(沿用既有導覽邏輯)或 mark(呼叫 `_toggle_cmp_mark` + rerun)。

### 9.3 疊圖比較視圖(取代 `_render_compare`)
- 進入點不變:沿用既有「🔀 比較模式」toggle(help 文字改寫)。標記 <2 張時顯示提示
  「請在縮圖牆標記兩張影像(目前已標記 N/2 張)」,不崩、不显示假疊圖。
- 標記恰好 2 張後:第 1 張標記 = A(藍)、第 2 張標記 = B(橘)(標記順序,非縮圖牆順序)。
  `arr_a = _display_rgb(itA.path)`;`arr_b = _resize_to(_display_rgb(itB.path), *arr_a.shape[:2])`
  ——兩張影像不必同尺寸,B 尺寸不同時縮放對齊 A(沿用既有 `_resize_to`,同 §8 舊 modeldiff 的
  縮放慣例)。
- **檢視方式**下拉(英文 token 內部值 + 中文 `format_func`顯示,同既有 `_CMP_MODES` 慣例,
  供 E2E 讀穩定 probe 值):
  - `pixel`(🖼️ 像素疊合):再選「並排/差異/混合」(英文 token `side`/`diff`/`blend`),
    直接呼叫既有、已 39 測試全綠的 **`framecompare.side_by_side`/`.difference`/`.blend`**
    (混合模式另出 alpha slider,0.0–1.0,預設 0.5)——零新純邏輯程式碼,原封不動重用 M3 模組。
  - `box`(📦 偵測框疊合):沿用既有信心雙界 + Object 類別 multiselect(`_cmp_filter`,
    與單張模式共用同一函式);base canvas = `framecompare.blend(arr_a, arr_b, 0.5)`(讓兩張
    影像內容都隱約可見),疊 A 自己的偵測框(藍 `overlay.draw(...,color=(0,160,255))`)+
    B 自己的偵測框(橘,B 框座標依 A/B 尺寸比例縮放,若有 resize)。
- 一顆「✖️ 清除標記」鈕可重新開始標記(不綁 toggle 本身,避免 §4.l 那個 widget-cleanup 陷阱
  ——按鈕本身若觸發 `st.rerun()` 仍需排在本節任何 widget 之後,依既有鐵律)。
- P1 探針(設計 §5)取代舊 5 個 `data-cmp-*`:新增 `data-cmp-marks-n`(0/1/2,**不論**
  compare_on 與否皆回寫,標記本身發生在主縮圖牆、與 toggle 正交)、`data-cmp-view-mode`
  (`pixel`/`box`,僅 compare_on 且已標記 2 張時有值,否則空字串)。

### 9.4 Acceptance Criteria(E2E,`4_PM_Feedback/test_compare_e2e.py` 全面改寫)
- **AC1** 標記 0/1 張時,開「比較模式」顯示「請在縮圖牆標記兩張影像」提示 + `data-cmp-marks-n`
  正確反映標記數(0 或 1),不顯示疊圖畫面、不崩。
- **AC2** 縮圖牆可點 `.cmpmark` 標記任兩張(不同縮圖各點一次)→ `data-cmp-marks-n == 2`;
  再點第 3 張的 `.cmpmark` → FIFO 踢掉最舊一張,`data-cmp-marks-n` 仍為 2(不會變 3)。
- **AC3** 標記 2 張 + 開比較模式 → 預設「像素疊合」顯示影像(`st.image` 有內容,非崩潰);
  切換「檢視方式」→「偵測框疊合」→ 疊框畫面出現,`data-cmp-view-mode` 對應切換為
  `pixel`/`box`。
- **AC4** 像素疊合下切「疊合方式」並排/差異/混合三種皆可正常顯示(不 raise);混合模式
  下有 alpha slider 可調。
- **AC5** 偵測框疊合下,信心範圍與 Object 類別 filter 仍可用(沿用既有 `_cmp_filter`)。
- **AC6** 點「✖️ 清除標記」→ `data-cmp-marks-n` 回到 0,再次開比較模式回到 AC1 提示狀態。
- **AC7** 向後相容:預設(未標記任何影像、比較模式 OFF)不受影響 —— 上一張/下一張鈕、
  單一 viewer canvas 皆正常,`data-cmp-marks-n=='0'`。
- **AC8** 標記動作**不影響**單張導覽(點 `.cmpmark` 不應觸發 `ss.idx` 改變 —— 這是
  `stopPropagation()` 是否正確接線的關鍵回歸點)。

> **回歸保契約**:比較預設 OFF、標記預設 0 張 → M7a/M7b/viewer_ux/app_e2e 不受影響;
> `thumbwall()` 新增的 `markable` 參數預設 `False`,任何未傳此參數的既有呼叫端(理論上已無,
> 因分歧佇列呼叫點隨 §8 一併移除)行為完全不變;overlay/viewer.py/index.html(viewer 元件,
> 非 thumbwall)/conftest/verify 全不改。
