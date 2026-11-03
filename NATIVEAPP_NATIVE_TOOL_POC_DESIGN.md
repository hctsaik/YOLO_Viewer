# NativeApp 原生 CV Viewer POC — 設計審查（實作前）

> 回應 [NATIVEAPP_NATIVE_TOOL_POC_REQUEST.md](NATIVEAPP_NATIVE_TOOL_POC_REQUEST.md)，前置文件
> [TAURI_NATIVEAPP_HANDOFF.md](TAURI_NATIVEAPP_HANDOFF.md)、[NATIVEAPP_ARCH_REVIEW.md](NATIVEAPP_ARCH_REVIEW.md)。
>
> 依請求規定「**先設計審查、回答閘門問題,設計確認後才實作**」。本文不含實作,只做決策與風險。
> 所有架構結論都讀過 `C:\code\claude\nativeApp` 原始碼,附檔案/行號。

---

## 0. 先回答那個決定成敗的閘門問題

> 請求第 179-180 行：**「若 NativeApp 現有架構無法在不新增 loopback HTTP 的情況下讓 portal 與
> Python engine 通訊,請先停在設計階段,列出缺少的平台能力與最小平台擴充。」**

**裁決:portal↔engine 可以在「WebView 不發 loopback HTTP」的前提下通訊——這條路已經存在,但目前沒有 viewer 需要的指令,必須做一次性的最小平台擴充（要重編 Rust 殼）。**

依據（程式碼）：

1. engine 是跑在 `127.0.0.1:<control_port>` 的 **FastAPI/uvicorn 控制伺服器**
   （`sidecar/python-engine/engine.py:24,1826`；Rust 於 `src-tauri/src/sidecar.rs` 找空埠→spawn→等 health）。
2. Rust 殼 `bridge.rs` 用 **Tauri command（IPC）** 把特定端點**轉發**到 engine，走的是 **Rust 端的 `ureq` loopback**，
   不是 WebView 的網路堆疊：
   - `bridge.rs:25-38` `get_json/post_json/delete_json` → `http://127.0.0.1:{port}`
   - `bridge.rs:46-104` 一組 `#[tauri::command]`（`list_tools`/`start_tool`/`stop_tool`…），
     於 `lib.rs:22-39` `invoke_handler` 註冊。
3. 前端由 **`WebviewUrl::App("index.html")`（`lib.rs:47`）** 載入——即 **Tauri app protocol（bundled `portal-react/dist`）,非 loopback**。

> 意義：native viewer 的前端可以用 `invoke(command)`（IPC）呼叫 Rust，Rust 再以 host 端 loopback 打 engine。
> **WebView2 全程不對 127.0.0.1 發 HTTP**，於是 handoff 最在意的「proxy / EDR 攔截 WebView 的 loopback 請求」這條觸發器被移除。

**但有三個必須誠實標明的邊界：**

- **(A) 目前沒有 viewer 指令、也沒有通用直通。** `bridge.rs` 的指令是**固定清單**（`lib.rs:22-39`），
  沒有 `viewer.openImage / pixel.read / roi.create`，也沒有 `engine_call(path,body)` 這種通用 passthrough。
  portal 對「沒有專屬指令」的端點目前是退回 **`fetch(config.sidecarControlUrl + …)`**（WebView loopback HTTP，
  `portal-react/src/main.jsx:581,789,887,962`）。**POC 若走 fetch 那條,就直接違反完成定義。** 因此必須新增指令。
- **(B) 新增指令 = 重編 `cim-light.exe`,而本機 WDAC 擋 cargo。**
  （`start-dev-tauri.bat:8-11,34`、`apps/host-tauri/prebuilt/README.md`：本機 WDAC 強制模式擋未簽章新 exe，
  殼要在**沒有 WDAC 的機器**編好帶回。）→ 程式碼可以在這裡寫,**但可跑的 POC 殼必須在別台機器編**。
- **(C) engine 本身仍是 loopback HTTP 伺服器（FastAPI）。** 我們移除的是「**WebView** 的 loopback 依賴」,
  不是「整台機器完全沒有 loopback」。Rust→engine 的 `ureq` 連線是 host 本地、不經 WinINet/WebView proxy。
  若要連 host 端 loopback 都不要（改 stdin/stdout 或 named pipe），那是遠大於 POC 的工程,本階段**不做**,但在風險列明。

> 結論:**不退回「Tauri 包 Streamlit」。** 走 native 是可行的,代價是一次性平台擴充 + 一次異地重編。

---

## 1. 建議架構與資料流

```text
Tauri WebView2（tauri:// app protocol，bundled）
├─ portal-react（既有）
│   └─ 新增 route: #/native/<toolId>  ← 原生 viewer 掛載點（同一 bundle，OpenSeadragon vendored）
│         │  invoke("engine_call", {session, method, payload})        ← 請求/回應（IPC，非 HTTP）
│         │  listen("native://<session>")                              ← 非同步事件（Tauri event）
│         ▼
├─ Rust 殼（bridge.rs 擴充）
│   ├─ #[command] engine_call(session,method,payload) → ureq → engine （host loopback）
│   └─ register_uri_scheme_protocol("cimimg") → 影像 bytes（避免 base64 JSON）
│         ▼
Python engine（FastAPI，既有）
└─ 新增 native session 端點（/native/session、/native/call）
      └─ adapter → 既有 CV 模組（解碼 / 像素 / ROI；沿用,不重寫）
```

**核心決策:不做「每個 viewer 動作一個 Rust 指令」,而是加一個通用 `engine_call`。** 一次重編殼之後,
未來所有 native 工具都在 **JS + Python** 迭代,不用再碰 Rust。這把「WDAC 異地重編」壓成**一次性成本**。

---

## 2. 對請求 7 個設計問題的回答（逐條，有依據）

**Q1 新增哪種工具模式、如何與 `mode="iframe"` 共存？**
engine 的 tool 描述已有 `mode` 欄位（`engine.py:243` `mode: str = "iframe"`，另見 `1392,1441`）。
新增 `mode="native"`：`/tools/{id}/start` 對 native 工具**不 spawn streamlit**，改回傳一個 `session_id` 與
前端 route（`#/native/<toolId>`）。portal `main.jsx` 依 `mode` 決定渲染 `<iframe>`（現況）或掛載 native route。
既有 iframe 工具零改動、可回退（見第 6 節隔離）。

**Q2 原生工具的註冊/啟動/ID/關閉？**
沿用既有 `plugin.yaml` 機制,加 `mode: native` 與進入點欄位。啟動走 `start_tool`（已存在,`bridge.rs:51`）,
engine 建立 `NativeSession(session_id, tool_id, case_id)` 並回傳。關閉走既有 `stop_tool`（`bridge.rs:61`）+
視窗關閉 graceful stop（`lib.rs:77-89` 已攔 `CloseRequested` → `sidecar::stop`，不留孤兒 Python）。

**Q3 portal 直接承載 viewer,還是另一個 bundle？**
**同一 portal bundle 內新增 route**（最小改動、共用既有 `invoke` shim `window.cimHost`，
`lib.rs:13` 注入 `cimhost-shim.js`）。OpenSeadragon 用 vendored 檔（CV_Viewer 既有 `openseadragon.min.js`）
放進 `portal-react` 資產,隨 `frontendDist`（`tauri.conf.json:7`）打包,經 tauri:// 載入,不走 CDN、不走 loopback。

**Q4 前端如何呼叫 Python（優先既有能力，不先加 loopback HTTP）？**
用 **Tauri `invoke("engine_call", …)`**（新增的通用指令）→ Rust `ureq` → engine。**這就是既有能力的延伸**
（`bridge.rs` 全部指令都是這個形狀）,不是新 loopback：WebView 端是 IPC。非同步/進度用 **Tauri event**
（`app.emit`，`lib.rs:62` 已在用 `sidecar-ready`）。**明確禁止** POC 走 `fetch(sidecarControlUrl)`。

**Q5 session 狀態放哪，避免與 Streamlit `st.session_state` 兩份真相？**
engine 已是選取路徑等狀態的單一真相（`SelectedPathStore`/`ToolProcessManager`，`engine.py:880,2202-2209,2430`）。
native session 狀態**一律放 engine 端 `NativeSession`**,前端只持 UI 短暫狀態（zoom/pan）。native 工具**完全不碰
`st.session_state`**（它不跑 Streamlit）,所以兩份真相的問題在 native 路徑上自然消失。

**Q6 本機影像如何安全高效交給 WebView（不得反覆巨大 base64 JSON）？**
新增 **custom protocol `cimimg://<session>/<imageId>?...`**（`register_uri_scheme_protocol`，需 Rust）。
OpenSeadragon 的 tile / 整圖以 **binary** 由該 protocol 提供,Rust 向 engine 取 bytes。
`imageId` 為 engine 發的**不透明 token**,前端拿不到絕對路徑（滿足「不暴露任意本機路徑」）。
16-bit TIFF 由 engine 解碼→8-bit 顯示位圖後才出 bytes（原始像素值走 `pixel.read` 另回）。
**選型用量測**：POC 先做「binary custom protocol」vs「base64 IPC」兩者延遲對比,寫進驗證報告。

**Q7 離網 / 無管理員 / 中文與空格路徑的資產與 sidecar 策略？**
- 前端資產：全 bundled（tauri://），無公網。CSP 待收緊（見第 5 節；目前 `tauri.conf.json:13` `csp: null`）。
- sidecar 打包：engine 以凍結 exe 或可攜 runtime 執行（`sidecar.rs:113-125`：`.py`→用 `CIM_ENGINE_PYTHON`,
  否則直接跑 exe）。**目標機免裝 Python / 免 PyPI 由既有 `native_Provision` 補給包 + 可攜 runtime 解決**
  （見該專案 `docs/OFFLINE_DEPLOY.md`）。
- 中文/空格路徑：影像路徑不進 URL 明碼（用 `imageId` token），engine 以 `Path` 處理;沿用平台既有可攜佈局。

---

## 3. IPC schema（TypeScript ⇄ Python，對齊請求建議並標明傳輸層）

傳輸層＝ Tauri `invoke`（請求/回應）+ Tauri `event`（非同步）。**不是 HTTP。** 版本化 + requestId + toolSessionId。

```ts
// 前端 → Rust → engine（invoke 回傳 EngineResult）
type EngineCall = {
  version: 1; requestId: string; toolSessionId: string;
  type: "viewer.openImage" | "viewer.pixel.read" | "viewer.roi.create";
  payload: unknown;
};
type EngineResult =
  | { requestId: string; ok: true; payload: unknown }
  | { requestId: string; ok: false; error: { code: string; message: string; detail?: string } };
```

```jsonc
// viewer.openImage → { imageId, width, height, tileSource }  // tileSource 指向 cimimg://…（binary）
// viewer.pixel.read {imageId,x,y} → { value: number[] , raw16?: number[] }   // x,y 為原始影像座標
// viewer.roi.create {imageId,bbox:[x,y,w,h]} → { roiId, bbox }               // bbox 原始座標,寫入 sidecar
```

錯誤格式採請求第 113-125 行原樣（`code/message/detail`）。**快速切圖**：前端對每次 openImage 帶新 requestId,
engine/前端丟棄過期 requestId 的回應（滿足驗證 #8「連切 20 次不顯示過期結果」）。

---

## 4. 生命週期（啟動 / ready / shutdown / crash）

- **啟動**：sidecar 先起、ready 後才建視窗（`lib.rs:40-74`）→ portal 載入即有真實 port。
- **native session ready**：`start_tool`（native）回 `session_id` + route;前端掛載 viewer。
- **shutdown**：關窗 → `CloseRequested` 攔截 → `sidecar::stop` graceful（`lib.rs:77-89`）→ 無孤兒 Python。
  native session 額外釋放：關 route 時 `invoke("engine_call",{type:"viewer.session.close"})`。
- **crash recovery**：sidecar 已掛崩潰監看（`sidecar.rs:105`）;engine 崩潰→前端 `engine_call` 收到錯誤→提示重試/`restart_sidecar`（`bridge.rs:134`）。

---

## 5. CSP / capabilities / filesystem / sidecar 權限

- **CSP 目前是 `null`（`tauri.conf.json:13`）= 沒設。** POC 應**收緊**成明確白名單：
  `default-src 'self'`; `img-src 'self' cimimg:`; `connect-src 'self' ipc:`; `script-src 'self'`;
  `style-src 'self' 'unsafe-inline'`（OSD 需要少量 inline style;請求允許但要說明與移除計畫）。**禁 `unsafe-eval`。**
- **capabilities**：只授 `dialog`（已用,`lib.rs:20`）與新增指令;**不授前端任意 fs**。檔案選取走既有
  `choose_file`（`bridge.rs:146`,原生對話框→engine `/selected-paths`）。
- **filesystem scope**：前端永遠拿 `imageId` token,不拿絕對路徑;實體讀檔只在 engine（Python allowlist）。
- **session 綁定**：`engine_call` 與 `cimimg://` 都帶 `toolSessionId`,engine 驗證後才回,避免跨工具/跨視窗互讀（請求第 132 行）。

---

## 6. 隔離與回退（滿足請求第 154-160 行）

- native 工具用**獨立 `mode="native"` + 獨立 tool_id/route + feature flag**;既有 `mode="iframe"` 工具零改動。
- `module_006`（現況 Streamlit viewer）**不動**;POC 是另一個 tool_id（例如 `module_006_native` / `cv_viewer_native`）。
- 若 native 框架不成熟：移除新增指令的註冊 + route,平台回到純 iframe,其他工具不受影響。
- **不重寫 CV 演算法**:engine 端以 adapter 包既有解碼/像素/ROI 邏輯。

---

## 7. 修改/新增檔案清單與粗估

| 層 | 檔案 | 動作 | 需重編殼? | 粗估 |
|---|---|---|---|---|
| Rust | `src-tauri/src/bridge.rs` | 加 `engine_call` 通用指令 + `cimimg` protocol handler | ✅ WDAC 異地 | 0.5–1d |
| Rust | `src-tauri/src/lib.rs` | 註冊指令 + `register_uri_scheme_protocol` | ✅ | 0.25d |
| Rust | `tauri.conf.json` | 收緊 CSP、加 protocol/capabilities | ✅ | 0.25d |
| 前端 | `apps/portal-react/src/`（新增 native viewer route + OSD 掛載 + IPC 客戶端） | 新增 | ❌（JS 熱迭代） | 2–3d |
| 前端 | vendored `openseadragon.min.js` 等資產 | 複製進 bundle | ❌ | 0.25d |
| Python | `engine.py` + 新 `native session` 端點 | 加 `mode=native` 分支 + `/native/*` | ❌ | 1–2d |
| Python | CV adapter（沿用既有解碼/像素/ROI） | 新增薄層 | ❌ | 1–2d |
| 測試 | 離網/proxy/network-log/process 驗證腳本 | 新增 | ❌ | 1–2d |

> **關鍵路徑是 Rust 那 3 個檔案的一次性重編**（WDAC 異地）。之後全部在 JS+Python 迭代。

---

## 8. 已知風險 / 未決 / 下一步

1. **WDAC 重編閘門（最高風險）**：本機無法產生含新指令的 `cim-light.exe`。
   需要一台無 WDAC 的機器跑 `scripts\win\build-shell.bat` 產 exe 帶回。**這是進入實作前必須先確認的資源。**
2. **engine 仍是 loopback FastAPI**（邊界 C）。滿足「WebView 不依賴 loopback」但非「全機無 loopback」。
   若客戶環境連 host 端 loopback 都受管,才需要把 engine 傳輸改 stdin/stdout / named pipe（大改,另立階段）。
3. **影像傳輸選型**：custom protocol vs base64 IPC 需實測延遲後定案（Q6）。
4. **CSP 收緊**可能與 OSD 的 inline style/worker 衝突,需在 POC 內驗證白名單可用。
5. **16-bit TIFF**:POC 先過 PNG 全鏈路,TIFF 只驗「engine 解碼→8-bit 顯示 + 原始像素值回傳」的接法。

**建議的下一步（實作前確認點）**：
- (a) 確認能取得無 WDAC 的建置機（否則卡在無法產出可跑 POC 殼）。
- (b) 確認「一次性通用 `engine_call` + `cimimg` protocol」這個最小擴充方向是否採用。
- 兩點確認後,才進實作;實作順序建議：Rust 擴充（異地編一次）→ engine `/native/*` + adapter → 前端 route → 離網驗證矩陣。

---

## 9. 完成定義對照（請求第 174-180 行）

| 要求 | 本設計是否滿足 | 說明 |
|---|---|---|
| 保留 viewer 雙向互動 | ✅ | `engine_call`（IPC）雙向 + event |
| 完全無 Streamlit `/component/` | ✅ | native route,無 Streamlit、無 declare_component |
| 無 Streamlit iframe / `streamlit run` | ✅ | `mode=native` 不 spawn streamlit |
| 無外部網路依賴 | ✅ | 全 bundled + tauri:// + cimimg:// |
| portal↔engine 不新增 loopback HTTP | ✅（WebView 端） | invoke→Rust→host loopback;WebView 不發 HTTP。**engine 內部 loopback 仍在(邊界 C)** |
| 不退回「Tauri 包 Streamlit」 | ✅ | 明確走 native + 列出最小平台擴充與 WDAC 閘門 |
