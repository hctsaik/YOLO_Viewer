# M7 開發過程記錄 — 用 `/loop` 多代理討論驅動的 UI/UX 重設計

> 本文記錄 CV_Viewer 專案 **M7(Viewer-First 工作台重設計)** 這一輪的完整開發過程。
> 它的特殊之處:**起點是 User 用 `/loop` 開的「多代理討論」**,而非一句直白需求 ——
> 這是本專案目前唯一一次以 `/loop` 自我步調(dynamic mode)收斂版面、再導入正規 U-Net 五階段管線的回合。
>
> 來源:`ROADMAP.md` 決策日誌(2026-06-24)、`3_Architect_Design/20_viewer_workbench_redesign.md`、
> `spike/kbd_*`、`4_PM_Feedback/test_m7a_e2e.py`。**狀態以人的判斷為準,非檔案存在自動推斷。**

---

## 0. TL;DR(一句話版)

User 用 `/loop` 起一個**沒有 interval 的多代理討論**(讓模型自我步調),由 `user` 角色子代理對版面方案
**連跑 5 輪評分(74 / 72 / 72 / 68 / 71,目標 85 未達)**,收斂出「**Viewer-First 單舞台 + 召喚式抽屜**」方向;
過程中還挖出一個**真實 bug**(主 viewer iframe 每切張 remount)。User 裁決「都要做」=全範圍 →
PO 排序(風險優先)→ **architect 先用 spike 驗 5 個生死點命題(全綠)** → 完整設計 28 AC、切三片(M7a/b/c)→
PM 落 M7a 真實 E2E 測試。**目前進度:卡在 PG 階段(M7a 實作 + E2E 判綠未完成)。**

---

## 1. 為什麼用 `/loop`:這一輪和前六輪不一樣

| | M1–M6 | **M7** |
|---|---|---|
| 起點 | User 一句需求 / 「再做一輪」 | **User 用 `/loop` 開多代理討論** |
| 需求型態 | 功能清單明確 | **版面/體驗主觀,需反覆評分收斂** |
| 收斂方式 | PO 直接拆模組 | **`user` 角色子代理連續 5 輪打分逼近門檻** |
| 風險點 | 純邏輯模組,gate.py 客觀判綠 | **押在「未驗證的鍵盤橋」生死點上** |

關鍵動機:UI/UX 是**主觀**的,沒有 `gate.py` 那種客觀紅綠信號。`/loop` 的價值在於
**用「多個 user 視角代理 + 評分迴圈」當作主觀需求的代理收斂機制** —— 跑到評分穩定/收斂才停,
而不是一次拍板。這是 `/loop` 的 **dynamic mode(不給時間間隔、讓模型自我定步調)** 用法,
適合「討論到收斂為止」這種沒有固定節拍的任務。

---

## 2. 階段一:`/loop` 多代理討論(2026-06-24)

### 2.1 討論主題與收斂結果

- **主題**:`image-viewer-first + 可收疊` 的版面。
- **過程**:`user` 角色子代理連跑 **5 輪**,各輪評分 **74 / 72 / 72 / 68 / 71**,**始終未達 85 上限**
  (刻意設高門檻,逼出更尖銳的不滿)。
- **收斂方向**:「**Viewer-First 單舞台 + 召喚式抽屜**」
  - 主 viewer 最大化(~85% 畫面、由 JS 量視窗高動態給,高度 600 → 720)
  - 次要功能(比較 / 相似 / 聚類 / DZI / 漏檢 / 匯出)收進**單一**「🧰 工具台」`expander + st.tabs`
  - 篩選 / 資料源 / 排序收進可收合 `sidebar`
  - 判定 Rail 可收;頂部一條薄 Command Bar

### 2.2 討論挖出的「審圖員未滿意」之因

模擬審圖員(`user` 代理)不滿,理由有二:

1. **把標準拉到 workflow 大改**:鍵盤切張、verdict 熱鍵 1/2/3、linked-viewport 比較、跨圖 undo、
   縮圖虛擬化…… **遠超「只是收疊」的原始訴求** —— 但 User 後來裁決這些「都要做」。
2. **核心押在未驗證的鍵盤橋生死點**:整個鍵盤工作流的可行性沒被證明過。

### 2.3 討論意外挖到的真實 Bug 🐛

> 主 viewer `key=f"viewer_{ss.idx}"`(`app.py:350`)**每切一張,iframe 就 remount**
> → 焦點丟失 + 可能重置 zoom/pan。

這是後來 M7a 的核心修復標的(見 §4 的 M7a-AC2)。**討論本身就產出了可驗證的缺陷**,
不只是空談版面。

### 2.4 一個被閘門攔下的插曲:confused-deputy

討論用的 `user` 角色子代理,曾經 **把 `user` 寫進 `.unet/role`**(role-play 時誤觸 —— 它在「扮演 user」
就真去改了角色檔)。`role_guard` hook 擋下這次 PO 的誤寫並重置。
**這是一次 confused-deputy 被閘門攔下的實例**:子代理的「扮演」不該污染管線的真實狀態機。

---

## 3. 階段二:PO 裁決與排序(風險優先)

- **User 裁決**:「都要做」= **全範圍**(§2.2 第 1 點列的 workflow 大改全進場)。
- **PO 排序原則 = 風險優先**,沿用 M1 viewer「**先驗物理可行,再設計**」的慣例:

  1. **先 architect 做 spike 驗生死點**(spike 綠才准往下)
  2. 設計 → PM → PG
  3. 真實 E2E + 截圖 + **效能量測**
  4. 最後讓 `user` 角色代理**對「跑起來的成品」再評分**,評分過才結束 `/loop`

> 注意排序的紀律:**spike 不綠,後面全部不准開工**。把最大不確定性(鍵盤橋)提到最前面打掉。

---

## 4. 階段三:Architect Spike — 5 個生死點命題(全綠 + 對照組反證)

檔案:`spike/kbd_spike.py` + `spike/kbd_component/index.html` + `spike/kbd_probe.py` + `spike/kbd_p4_control.py`
(截圖佐證 `spike/kbd_spike_shot.png`)。用**真實 Streamlit 1.56 + 真實宣告式元件 + playwright** 實測。

| # | 命題 | 結果 | 對照組(反證) |
|---|------|------|----------------|
| 1 | 固定 `key="kv"`(不含 idx)→ iframe 跨 rerun **不 remount**(`__loadCount` 恆 ==1) | ✅ | idx-key 對照組:iframe **重生 2 次**(births 累加) |
| 2 | keydown → `setComponentValue` → app rerun → 切圖,**連按不吃首鍵** | ✅ P2_miss=0 | idx-key 對照組:**miss=3**(吃掉首鍵) |
| 3 | rerun 後 `osdEl.focus()` 自動回 viewer,**第二鍵仍生效** | ✅ activeEl=osd | — |
| 4 | **zoom/pan 跨切張保存**(切前存 zoom/center,新影像 open 後還原) | ✅ restore=1.866 | `?restore=off` 對照組:**重置回 fit 0.622** |
| 5 | 焦點守衛:`activeElement ∈ {INPUT,TEXTAREA}` 時打字**不誤觸熱鍵** | ✅ typed='drb123' 不切張 | — |

**結論**:鍵盤連切**物理可行、不需降級**。唯一鐵律 = **viewer 的 `key` 永不含 idx**。
spike 還順帶釘死一條後續設計必守的界線:**`maxZoomPixelRatio` 必須 = 24.0**,
否則預設 1.1 會把還原的 zoom **clamp 回 fit**,讓命題 4 失效。

> Spike 是 throwaway(非契約層),用完就丟,只為**買到「物理可行」這個確定性**,讓設計不用再把鍵盤橋當風險重議。

---

## 5. 階段四:Architect 設計 `20_viewer_workbench_redesign.md`

**Tier B GUI 大改**,**無 Python 單元 gate**(繪框/篩選/比較演算法一律複用既有 overlay / framecompare /
sidecar / tagging,不新造純邏輯)。**機器判綠 = 真實 playwright E2E 全綠 + 截圖實證 + 效能量測**三者皆過。

### 5.1 把「`user` 代理未滿足項」逐條映成 AC

設計 §1.2 有一張 12 列對應表,把討論裡審圖員的每個不滿,釘到具體 AC。摘要:

| 未滿足項 | 切片 / AC |
|---|---|
| verdict 一等熱鍵 1/2/3;r 循環 status、b bookmark(**別把流程狀態冒名成 verdict**) | M7b-AC2/AC3 |
| 鍵盤連切 ←/→、焦點不被 number_input 吃 | M7b-AC1/AC9 |
| 信心門檻常駐 footer + 細微調(step 0.01)、即時反映疊框 | M7a-AC5、M7b-AC8 |
| 切張自動存 + 改值入 undo 軌跡 | M7b-AC4/AC5 |
| **跨圖 undo**(跳回那張 + 還原值 + toast、多步) | M7b-AC6/AC7 |
| **linked-viewport 比較**(並排 + 閃爍、沿用主 viewer zoom/pan) | M7c-AC1/AC2 |
| **縮圖牆虛擬化**(只算可視窗 + 緩衝、改門檻不重建整牆) | M7c-AC3/AC4/AC5 |
| 收合狀態全域持久(跨圖不重置) | M7a-AC4 |
| 窄載體 RWD(nativeApp iframe) | M7c-AC6 |
| DZI 大圖自動瓦片(夠大自動,無感) | M7c-AC7/AC8 |
| HUD 語義界線(hover=8-bit 顯示值、click=真值)在新版面仍清楚 | M7a-AC6 |
| **判定單一真相**(Rail 與任何 popover 綁同一 session_state + 同一 undo 軌跡) | M7b-AC10 |

### 5.2 切三片(各自 E2E 綠才進下一片)

- **M7a — 版面 + viewer 基座(8 AC)**:收疊 / viewer 最大化 / 固定 key + zoom·pan 保存 / **修 remount bug** /
  footer 常駐信心 slider / P1 效能探針鋪底。
- **M7b — 鍵盤工作流(11 AC)**:←/→ nav / verdict 熱鍵 1/2/3 / r·b / 切張自動存 / **跨圖 undo** / 焦點守衛。
- **M7c — 進階(9 AC)**:linked-viewport 比較 / 縮圖牆虛擬化 / 窄載體 RWD / DZI 自動瓦片。

### 5.3 內建「效能量測機制」(把主觀『順不順』變可機器斷言)

UI 大改最容易 false-green。設計釘了三條**可被 Playwright 客觀讀取**的探針 + 量測法:

- **P1 server render 計時**:app 在每次 render 結尾寫隱藏探針 DOM
  `<div id='perf' data-render-ms data-reruns data-thumb-recalc data-tool-calls>`(主文件 DOM,跨 iframe 可讀)。
- **P2 元件端 `performance.now()`**:viewer 量 nav→下一張 open 完成的耗時,回灌 P1。
- **P3 重函式呼叫計數**:`ss.counters`,在 `_thumb_cached` / `_dzi_tiles` / `linked_compare` 實算分支 `+=1`。

三條量測法:
- **PerfA(切下一張 per-image 成本)**:連按 `→` 20 次,取 **P95 < 1200ms**(允許 PG 量實際後校準)。
- **PerfB(未召喚層 0 計算)**:工具台未展開時連切,`data-tool-calls` **恆為 0**(機器斷言計數器 ==0)。
- **PerfC(信心 slider 改值不重建整牆)**:改一格後 `data-thumb-recalc` 增量 **≤ 視窗大小**,而非 = total(上千張)。

### 5.4 誠實標註的物理界線(設計 §6,防 false-green)

- **autosave ≠ 絕對零遺失**:切張前 flush + 改值即時寫涵蓋連切;但「改值同一 run 內直接關閉/崩潰」不在保證內。
- **hover RGB = 8-bit 顯示值,非真值**(沿 M6):點擊才走 `imgio.value_at` 取 16-bit 真值;瓦片模式 hover 降級不取 RGB。
- **`j` 跨文件聚焦是務實降級**:iframe 不能跨文件 focus 主文件 number_input → `j` 落地為「捲到 + 高亮跳頁框」,仍需點。
- **DZI 自動瓦片為可降級項**:若量測到建金字塔 + 編碼成本使切張 P95 超門檻,**誠實降級**回 M5 手動開關(M7c-AC8 即驗「決策有被量測+記錄,不是默默跳過」)。

### 5.5 交代被取代/搬遷的 M6 AC(合法設計演進)

設計 §7 列了一張表:M6 的**行為全保留**(hover RGB、放大上限、縮圖疊框、HUD、可點縮圖、總開關同管兩處),
只是**位置/定位**改變(例:控制從 title 下方搬到 viewer-footer)。要求 PM 在新 E2E 以新定位重寫,
**不是破壞契約**。

---

## 6. 階段五:PM 落 M7a 真實 E2E(`test_m7a_e2e.py`)

只落 **M7a** 切片的 8 條 AC(M7b/M7c 不在此檔),全標 `@pytest.mark.e2e`。對應關係:

| 測試函式 | AC | 驗什麼 |
|---|---|---|
| `test_layout_skeleton_command_bar_viewer_footer` | M7a-AC1 | Command Bar(⟵/⟶ + 跳頁框 + 偵測N框 caption)、viewer canvas、footer 信心 slider/顯示框 checkbox **在 sidebar 外** |
| `test_fixed_key_viewer_no_remount_on_navigate` | M7a-AC2 | **修 remount**:切張 3 次後 `window.__loadCount === 1` 恆成立(沿用 spike 命題 1 手段) |
| `test_zoom_pan_preserved_across_navigation` | M7a-AC3 | 放大後 →再←,zoom/center 差 < 容差(沿用 spike 命題 4;maxZoomPixelRatio=24) |
| `test_collapse_state_persists_across_navigation` | M7a-AC4 | 收縮圖牆後切張 2 次仍維持收合(`ss.thumb_collapsed` 不重置) |
| `test_footer_conf_slider_resident_and_live` | M7a-AC5 | footer slider 常駐(不在 expander 內)+ 改門檻「顯示 k/總 框」k 即時變 |
| `test_hud_semantics_hover_rgb_is_display_value` | M7a-AC6 | 16-bit 圖 hover 後明示「顯示值/點擊取真值」語義 |
| `test_viewer_maximized_height` | M7a-AC7 | viewer 高度 > 660(顯著大於 M6 的 600,auto_height 生效) |
| `test_perf_probe_present_and_numeric` | M7a-AC8 | P1 探針 `data-render-ms` 等四個屬性皆可解析為數字 |

> PM 在檔頭誠實寫明:「PG 尚未完成,故本檔現在預期『紅』是正常的。本檔職責是把『使用者真的能用』釘成可機器斷言。」
> 這正是 TDD:**測試先紅,實作把它變綠**。

---

## 7. 目前狀態與下一步

### 7.1 切片進度

| 切片 | 狀態 |
|---|---|
| **M7a — 版面 + viewer 基座(8 AC)** | ✅ **機器判綠**(2026-06-25,orchestrator 親跑 E2E 8/8) |
| **M7b — 鍵盤工作流(11 AC + 1 推導)** | ✅ **機器判綠**(2026-06-25,PM→PG 一輪,E2E 12/12) |
| M7c — 進階(9 AC) | ⬜ 待「雙 iframe round-trip」小 spike → PM → PG;DZI 自動瓦片實作時真量測 |

### 7.2 M7a 判綠證據(2026-06-25)

orchestrator 親自重跑(不信子代理自述):

- **`test_m7a_e2e.py -m e2e` → 8 passed**:
  AC1 版面骨架(Command Bar + viewer + footer slider 在 sidebar 外)/ AC2 `__loadCount===1` 切張不 remount /
  AC3 zoom·pan 跨切張保存 / AC4 收合持久 / AC5 footer slider 即時反映 k / AC6 16-bit hover「顯示值/點擊取真值」語義 /
  AC7 viewer 高 >660(auto_height 生效)/ AC8 P1 探針 `data-*` 可解析為數字。
- **回歸**:單元 **811 passed**;viewer_ux E2E **13 passed / 1 skipped**(與 M6 一致);app_e2e **1 passed**(各檔單獨跑)。
- **誠實附記(交 PM,非 PG 改)**:`test_app_e2e` + `test_viewer_ux_e2e` **串在同一 pytest session** 跑時,
  `test_single_image_hover_shows_xy_and_rgb` 會紅 —— 根因是 `.cvr_state.json` / `Position` 位置記憶**跨測試檔在同一
  app_server session 持久**,前一檔導航到 idx7(wafer16,16-bit Gray、中心落圖外)污染了這個「不導航、用起始圖 hover」的測試。
  **各檔單獨跑皆綠**(per-module gate 即如此跑),屬 conftest 測試基建的跨檔狀態隔離議題(PM 擁有),**非 M7a 實作 bug**。
- **仍待人/工具觸發**:M7a 像素級 `[截圖實證]`(AC7 三欄比例「窄|寬|窄」等)交 `/ux-test` 或人工視覺驗收。

### 7.3 自然的下一個動作

進 **M7b**:architect 設計已備(在 `20_…redesign.md` §5),由 **PM 落 `test_m7b_e2e.py`**(←/→ nav、verdict 熱鍵 1/2/3、
r·b、切張自動存、跨圖 undo、焦點守衛),再 **PG 實作**(index.html 接 keydown + app nav 協定)到真實 E2E 綠;
之後 M7c(先補「雙 iframe round-trip」小 spike)。三切片各自 E2E 綠才進下一片。

---

## 8. 這一輪在方法論上的價值(為什麼值得記)

1. **`/loop` 當「主觀需求的收斂器」**:UI/UX 沒有客觀紅綠,用「多 user 視角代理 + 評分迴圈」逼近,
   比一次拍板更能挖出真實不滿(本輪挖出 2 條結構性不滿 + 1 個真 bug)。
2. **風險優先 + spike-first**:把最大不確定性(鍵盤橋)用 throwaway spike 提前打掉,**spike 不綠不准開工**。
3. **把主觀變可斷言**:UI 大改最怕 false-green —— 設計內建 P1/P2/P3 效能探針 + PerfA/B/C,
   讓「順不順、有沒有 0 計算、有沒有重建整牆」都變成 Playwright 能客觀讀的數字。
4. **誠實降級寫進契約**:autosave 不保證硬關零遺失、hover=顯示值、`j` 務實降級、DZI 可降級 —— 全部明文標註,不假裝。
5. **閘門擋下 confused-deputy**:`user` 代理 role-play 誤寫 `.unet/role`,`role_guard` 攔下並重置。
```
