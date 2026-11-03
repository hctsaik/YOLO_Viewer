# CV_Viewer 移入「nativeApp Tauri 架構」——第三方程式碼查證與架構判斷

> 這份文件是針對 [TAURI_NATIVEAPP_HANDOFF.md](TAURI_NATIVEAPP_HANDOFF.md) 的回覆。
> 內容**不是推論,是實際讀了 `nativeApp` 與 `CV_Viewer` 原始碼後的查證結果**,每一條都附檔案/行號。
> 目的：讓下一位 AI 在**已知現況事實**的基礎上評估,而不是從零臆測。
>
> 待答的核心問題（原文）：**「如果我用 nativeApp 這個架構,能解決 `/component/` 被 proxy/CSP/EDR 攔截的問題嗎？」**

---

## 一、先給結論

**光是把 CV_Viewer 搬進 nativeApp,不會根治那個故障；它與你要消滅的故障屬於同一類（loopback HTTP + Streamlit Custom Component）。**

- nativeApp 本質上就是 handoff 文件裡的**方案 A**：Tauri 殼 + 每個工具一個 `streamlit run` 起在 `http://127.0.0.1:<port>`,再用 `<iframe>` 載入。
- CV_Viewer **其實已經被搬進 nativeApp 了**（= `module_006`）,而且 viewer / thumbwall **原封不動仍用 `st.components.v1.declare_component(path=...)`**,也就是仍然掛在 `/component/` 下、以巢狀 iframe 載入。
- 因此你要消滅的 `/component/` iframe + `componentReady` timeout 故障面,在 module_006 裡**完全沒有被移除**。

它**可能**在某些機器上「剛好會動」（見第四節）,但那正是原文明講「不要宣稱包進 Tauri 就沒事」的情況——移除了部分觸發器,沒有移除故障那一整類。

---

## 二、查證證據（含檔案/行號）

環境：
- `C:\code\claude\nativeApp`（Tauri 平台，內部代號 CIM / cim-light）
- `C:\code\claude\CV_Viewer`（獨立版 CV Viewer，即 handoff 文件描述的現況系統）

### 2.1 nativeApp 如何渲染工具 → loopback HTTP + iframe（= 方案 A）

- `sidecar/python-engine/engine.py:983` — `streamlit_command_for_script(...)`：工具是以 `streamlit run` 子程序啟動。
- `engine.py:1450`、`1403-1404`、`1491` — 工具 URL 是 `http://127.0.0.1:{port}`；渲染模式 `mode="iframe"`（`engine.py:243,1392,1441`）。
- `apps/portal-react/src/main.jsx:309,313,348` — portal 前端用 `<iframe src={url}>` 載入該 127.0.0.1 頁面。
- `apps/portal-react/src/main.jsx:125-126` — 註解明講「iframe 使用 localhost 同源」,並注入 MutationObserver 攔截 Streamlit 錯誤對話框。
- `apps/host-tauri/src-tauri/tauri.conf.json` — 只有 `"withGlobalTauri": true`；**沒有**為工具內容註冊任何 `asset:` / 自訂 protocol。工具內容不是從 app bundle 經自訂 protocol 載入,而是走 loopback HTTP。

> 結論：nativeApp 的**整個工具模型**都建立在「WebView2 → 127.0.0.1 Streamlit iframe」。換殼（外部瀏覽器 → WebView2）有,換傳輸層（loopback HTTP → 原生 asset/IPC）**沒有**。

### 2.2 CV_Viewer 已在 nativeApp 內 = `module_006`,且仍用 Custom Component（= /component/ 故障面還在）

路徑：`sidecar/python-engine/plugins/cim-modules/modules/module_006/`

- `viewer.py:13,16`
  ```python
  import streamlit.components.v1 as components
  _component = components.declare_component("cv_viewer", path=str(_DIR))
  ```
- `thumbwall.py:20,23`
  ```python
  import streamlit.components.v1 as components
  _component = components.declare_component("cv_thumbwall", path=str(_DIR))
  ```
- 靜態資產仍在,由 Streamlit 掛在 `/component/` 下：
  - `viewer_component/index.html`、`viewer_component/openseadragon.min.js`、`viewer_component/images/`
  - `thumbwall_component/index.html`
- `thumbwall_component/index.html:37,39` — 用 `window.parent.postMessage(... isStreamlitMessage ...)` + `streamlit:setComponentValue` 把值送回。這證明它用的是 **Streamlit 雙向 Custom Component 協定**（不是單向的 `components.html`）。
- `plugin.yaml:8` — 描述明載「移植自獨立 app CV_Viewer」,功能含 OpenSeadragon 縮放/平移/點擊取像素、縮圖牆、雙 model 比對等。

> 結論：進了 Tauri 殼後,實際結構是——
> ```
> WebView2 → portal(React) → iframe(127.0.0.1 Streamlit 頁) → 巢狀 iframe(/component/…)   ← 故障點原封不動在這
> ```

---

## 三、為什麼不算根治（對照 handoff 的驗收條件）

- **驗收 #8**：「企業 proxy 封鎖 localhost HTTP 時,**架構若不使用 loopback HTTP**,完整功能仍正常。」
  → nativeApp 先天過不了：它每個工具都靠 127.0.0.1 iframe。若 GPO 強制連 loopback 都走 proxy,**不只 `/component/`,連 Streamlit 主頁 iframe 都載不起來**。
- **驗收 #2（WebView2 離網 runtime）/ #3（CSP）/ EDR 端點檢查**：這些介入點在 WebView2 裡同樣存在,只是觸發機率不同,不因「在 Tauri 裡」而消失。
- **驗收「全程沒有 /component/ 請求」**：module_006 現況直接違反——它就是靠 `/component/` 提供 viewer/thumbwall 資產。

---

## 四、什麼情況下「搬進去剛好會變好」（誠實揭露,不宜當保證）

WebView2 通常對 loopback（127.0.0.1）**繞過**系統 proxy,而且不再經過受管的外部瀏覽器那條 proxy 鏈。所以若你的故障成因**恰好是**「外部瀏覽器被公司 proxy 攔 localhost」,那換到 WebView2 內就可能不再觸發。

但這**移除的是觸發器,不是故障類別**。在以下任一情況它仍會失敗：
- GPO/防火牆強制對 127.0.0.1 也套 proxy。
- EDR/端點防護對 WebView2 程序流量做檢查或注入。
- Streamlit component 因任何原因（資產路徑、時序、CSP header）而 `componentReady` 逾時（~60s）。

---

## 五、真正根治要動的地方（= handoff 方案 B 的精神）

核心動作只有一個：**拿掉 `declare_component`**。但這裡有個**硬限制**必須先知道,否則會走冤枉路：

- `st.components.v1.html(inline_html)`（srcdoc 內嵌）**能**避開 `/component/`,**但它是單向的**——無法把 ROI 座標、點擊像素值、縮圖選取送回 Python。
- CV_Viewer 的必留功能（ROI 回存、點擊取像素、縮圖選取、比較標記）**需要雙向**。`declare_component` 之所以還在用,正是因為它能雙向（`setComponentValue`）。
- **所以不能只是把 `declare_component` 換成 `components.html` 就了事。**

要同時「拿掉 /component/」又「保留雙向」,唯一乾淨解是把 viewer / thumbwall 變成**原生前端**（在 Tauri/portal 層,bundle 內、經 `asset:`/自訂 protocol 載入,不走 loopback）+ **Python sidecar 走 IPC 回傳事件**——這就是方案 B,也是唯一能滿足驗收 #8 的路。

在 nativeApp 這個既有架構下,方案 B 具體會落在：
- 把 viewer/thumbwall 從 Streamlit component 移進 `apps/portal-react`（或獨立的 Tauri 前端），OpenSeadragon 資產隨 bundle 走 asset/自訂 protocol。
- 資料（切圖、16-bit 解碼、標註、比對）由既有 Python CV 模組處理,以 Tauri IPC / sidecar 事件與前端往返（避免大圖用巨大 base64 JSON,改用檔案 / binary / custom protocol）。
- **注意**：nativeApp 目前的工具模型是「Streamlit 為中心」,並沒有現成的「原生前端工具」路徑（見 2.1）。所以在 nativeApp 內做方案 B,等於要**擴充平台的工具模型**,不是「把模組丟進去」那種等級的工作量。

---

## 六、一個能立刻分辨成因的實測（建議先做,用結果定案）

在**目標離網機**上：拔掉網路 + 把系統 proxy 設成一個無效位址,啟動 nativeApp 開 module_006,觀察：

| 觀察到的現象 | 代表的成因 | 該走的路 |
|---|---|---|
| 連工具主頁 iframe 都載不出來 | loopback（127.0.0.1）被 proxy 攔 → 方案 A 整類不可行 | 必須方案 B（原生前端 + IPC） |
| 主頁出來,但縮圖牆/viewer 卡在 componentReady ~60s | `/component/` 故障面沒被移除 | 拿掉 `declare_component`（方案 B） |
| 兩者都正常 | 成因是「外部瀏覽器 proxy 鏈」 | 換到 WebView2 內就足夠;方案 A 可接受 |

---

## 七、給下一位 AI 的待答問題（在上面事實基礎上）

1. 在 **nativeApp 既有架構**下實作方案 B（原生前端 + IPC 取代 `/component/`）,最小改動路徑為何？是擴充 portal-react 的工具模型,還是另立一個「原生工具」類別？
2. 雙向事件（ROI / 點擊像素 / viewport / 縮圖選取）用 Tauri IPC 時,request/event schema 與程序生命週期（ready / shutdown / crash recovery）建議怎麼定？
3. 大圖與大量縮圖的高效傳輸：在「不走 loopback HTTP」前提下,asset protocol / 自訂 protocol / binary IPC / 暫存檔,哪個對數百張影像的啟動與切圖延遲最好？
4. 若短期仍要留在 Streamlit component：有沒有**保留雙向**又能避開 `/component/` 被攔的折衷（例如把資產改由 srcdoc 內嵌 + 自建 postMessage 回傳橋接,而非 `declare_component(path=)`）？可行性與風險？
5. 分階段遷移：先只把 viewer+thumbwall 原生化、其餘 Streamlit 控制保留,是否有乾淨的可回退切點？

---

### 附：關鍵事實一句話總結

> nativeApp = Tauri 殼 + 127.0.0.1 Streamlit iframe（方案 A）；CV_Viewer 已是其 `module_006` 且 viewer/thumbwall 仍用 `declare_component`(`/component/`)。所以「搬進這個架構」= 換殼不換傳輸層,`/component/` 與 loopback-HTTP 故障面都還在;真正根治需拿掉 `declare_component`,走原生前端 + Python sidecar IPC（方案 B）。
