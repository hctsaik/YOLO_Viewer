# CIM 平台三元件架構與部署流程 — 完整分析(問題 / 過程 / 結果)

> **這份文件是什麼**:對 `CV_Viewer`、`nativeApp`、`native_Provision` 三個 repo 的完整架構盤點、
> 問題分析、目標分工與部署流程設計。所有現況描述都經過**實際讀碼查證**(附 file:line),
> 不是臆測。目的:讓下一位 AI(或工程師)不必重新考古,直接在正確的事實基礎上開發。
>
> **文件鏈**(建議閱讀順序):
> 1. [TAURI_NATIVEAPP_HANDOFF.md](TAURI_NATIVEAPP_HANDOFF.md) — 原始問題:Streamlit `/component/` 被攔
> 2. [NATIVEAPP_ARCH_REVIEW.md](NATIVEAPP_ARCH_REVIEW.md) — 查證:搬進 nativeApp 不等於根治
> 3. [NATIVEAPP_NATIVE_TOOL_POC_DESIGN.md](NATIVEAPP_NATIVE_TOOL_POC_DESIGN.md) — 原生工具 POC 設計審查
> 4. **本文件** — 三元件總體分工與部署 pipeline(含最新約束:**沒有無 WDAC 建置機**)
>
> 撰寫日期:2026-07-11。本機環境:Windows 11、WDAC 強制模式、Python 3.11、Node v24。

---

## 第一部分:現況盤點(每一條都有程式碼依據)

### 1.1 三個 repo 各是什麼

| Repo | 路徑 | 角色(現況) |
|---|---|---|
| **nativeApp** | `C:\code\claude\nativeApp` | CIM 平台:Tauri 殼 + React portal + Python engine + 工具(plugins) |
| **CV_Viewer** | `C:\code\claude\CV_Viewer` | 獨立 Streamlit CV 檢視器(`5_PG_Develop/app.py`);其功能已被移植成 nativeApp 的 `module_006` |
| **native_Provision** | `C:\code\claude\native_Provision` | 離線補給包產生器:掃 `plugin.yaml requires:` → 下載 wheel → 離線機一鍵套用 |

### 1.2 nativeApp 的內部構造

```text
nativeApp\
├─ apps\host-tauri\
│  ├─ prebuilt\cim-light.exe        ← 預建 Tauri 殼(本機 WDAC 擋 cargo,只能跑既有 exe)
│  └─ src-tauri\src\
│     ├─ lib.rs                     ← 視窗/生命週期;前端用 WebviewUrl::App 載入(tauri://,非 loopback)
│     ├─ bridge.rs                  ← ~16 個固定 #[tauri::command],以 host 端 ureq 轉發到 engine
│     └─ sidecar.rs                 ← 找空埠 → spawn engine → 等 health → 崩潰監看
├─ apps\portal-react\               ← React portal;vite build 產 dist(Tauri 載靜態 dist)
├─ sidecar\python-engine\
│  ├─ engine.py                     ← FastAPI 控制伺服器(127.0.0.1:<port>);每個工具 spawn `streamlit run`
│  ├─ core\                         ← deppack / tool_deps / wheel_store(離線安裝、fail-closed 驗章)
│  └─ plugins\cim-modules\          ← git submodule(nativeApp_modules.git)
│     └─ modules\module_006\        ← 移植版 CV_Viewer(viewer.py / thumbwall.py / cvviewer_app.py)
├─ runtime\(python311 可攜)         ← scripts\win\build-runtime.bat 產生
└─ start.bat / start-dev-tauri.bat  ← 啟動入口
```

關鍵證據:
- 工具渲染 = Streamlit + loopback iframe:`engine.py:983`(spawn `streamlit run`)、`engine.py:1450`(`http://127.0.0.1:{port}`)、`portal-react/src/main.jsx:348`(`<iframe src=…>`)。
- portal↔engine 通訊**雙軌並存**:
  - IPC 軌:`invoke` → `bridge.rs:46-104` 固定指令 → Rust `ureq` 打 engine(WebView 不發 HTTP)。
  - HTTP 軌:portal 直接 `fetch(config.sidecarControlUrl + …)`(`main.jsx:581,789,887,962`,WebView 發 loopback HTTP)。
- 前端本體由 `WebviewUrl::App("index.html")` 載入(`lib.rs:47`)= bundled dist,經 tauri:// 協定,不走 loopback。
- CSP 目前 **未設**(`tauri.conf.json:13` `"csp": null`)。
- 生命週期已處理孤兒程序:關窗攔截 → graceful stop sidecar(`lib.rs:77-89`)。
- `cim-modules` 是 **git submodule**(`.gitmodules` → `nativeApp_modules.git`)。

### 1.3 CV_Viewer 與 module_006 的關係(雙份真相)

- `module_006` 的 `plugin.yaml:8` 明載「移植自獨立 app CV_Viewer」。
- viewer / thumbwall 在 module_006 內**仍用 Streamlit Custom Component**:
  - `viewer.py:16` → `components.declare_component("cv_viewer", path=…)`
  - `thumbwall.py:23` → `components.declare_component("cv_thumbwall", path=…)`
  - 靜態資產 `viewer_component/`(含 vendored `openseadragon.min.js`)、`thumbwall_component/` 由 Streamlit 掛在 **`/component/`** 下,以巢狀 iframe 載入 —— **這正是 handoff 文件要消滅的故障面,原封不動存在**。
- 也就是說:CV_Viewer 的功能現在有**兩份**——獨立 repo 一份、cim-modules submodule 內一份(module_006)。

### 1.4 native_Provision 的現有能力(已 E2E 驗證)

| 能力 | 說明 | 狀態 |
|---|---|---|
| 掃描 | 掃 `plugin.yaml` 的 `requires:`,鎖定 win_amd64/py3.11/cp311 | ✅ |
| 產包 | `pip download` → `packs/<tool>/wheels` + 逐檔 SHA-256 `deppack.json` | ✅ |
| 大相依隔離 | >100MB wheel 進 `big-deps\`,跨工具去重 | ✅ |
| 離線可裝自檢 | 產包後立刻 `--no-index` 重解依賴圖,在連網機就證明離線裝得起來 | ✅ |
| 增量 | requires 指紋/目標標籤/sha256 任一變才重建 | ✅ |
| **source-packages** | Module 原始碼獨立打包(`source/` + `source-manifest.json`),與 wheel 分離、可只更新原始碼 | ✅ 產出 |
| apply.py | 離線機:只搬 wheel 到 deppack-cache(stdlib-only、原子換位、sha256 驗證) | ✅ |
| warmup.py | 離線機:借平台 `core.tool_deps` 先離線裝進 per-tool venv(避開殼 30s 逾時) | ✅ |
| run-platform.bat | 一鍵 apply→warmup→啟動平台(portable/dev 雙模式,GUI 可選、隨包產出) | ✅(2026-07-11 加入) |
| GUI | 掃描→勾選→打包→實機 Tauri 驗證,與 CLI 同一核心 | ✅ |
| E2E | `e2e/gui_flow_e2e.py`:真實 GUI 後端 + 真 Tauri 殼 + 死位址 pip index,app/module 兩分支全 PASS | ✅ |

**已知缺口(查證過,不是猜測)**:`apply.py` **只處理 wheels(packs/big-deps),不套用 source-packages**
(`apply.py` 全文無 source-packages 邏輯)。原始碼更新要進離線機 engine 的 plugins 樹,目前是**手動複製**。

---

## 第二部分:問題分析

### P1(根本問題)工具渲染的故障面在平台,不在打包

執行時鏈路(現況):

```text
WebView2(tauri:// 載 portal)
  → <iframe src="http://127.0.0.1:<port>">      ← Streamlit 工具頁(loopback HTTP,故障面 1)
      → 巢狀 iframe /component/…                 ← declare_component 資產(故障面 2:被 proxy/CSP/EDR 攔,~60s 逾時)
```

- 故障面 2 就是 handoff 文件的原始問題;搬進 nativeApp **沒有**移除它(module_006 仍用 declare_component)。
- 故障面 1(loopback iframe)是 nativeApp 工具模型的地基;若目標機把 127.0.0.1 也強制走 proxy,整個 iframe 模式失效。
- **打包器(native_Provision)治不了這兩個**:它們是「執行時請求路徑」問題,不是「檔案沒到位」問題。
  打包解決「缺檔」,解決不了「請求被攔」。

### P2 分工邊界模糊:CV_Viewer 雙份真相

- 獨立 CV_Viewer repo 與 module_006(cim-modules submodule)各持一份 viewer 程式碼。
- 修 bug 要改兩處;行為漂移無人守護;「誰是部署真相」沒有定論。

### P3 部署 pipeline 有斷點

離線機需要三個資料夾(`runtime\`、平台專案、`provision\`),現況:
- runtime 與平台專案靠**人工 XCOPY**,沒有工具負責組裝與驗證整包。
- source-packages 產得出來,但**離線機端沒有自動套用步驟**(P1.4 缺口)——「只改原始碼」的更新流最後一哩是手動的。
- `--deppack-cache` 路徑要人查表(portable/dev 不同),曾是最容易出錯的一步(run-platform.bat 已緩解)。

### P4 平台殼被凍結:WDAC + 沒有建置機

- 本機 WDAC 強制模式擋未簽章新 exe(含 cargo build script)→ **不能在本機改 Rust 殼**(`start-dev-tauri.bat:8-11`)。
- **使用者已確認:目前沒有無 WDAC 的建置機。** → 一切需要重編 `cim-light.exe` 的方案(新 Tauri command、custom protocol、CSP 設定變更)全部**暫時不可行**。
- 連 portal 前端 dist 的重建都存疑:`portal-react` 用 **vite build**(依賴 esbuild 原生 exe,未簽章);
  `start-dev-tauri.bat:46` 暗示 dist 是「在可用 esbuild 的機器」建的。**本機能否 `npm run build` 未驗證**——
  這是 Phase 1 開工前第一個要實測的事(fallback:esbuild-wasm / 在任何一台無 WDAC 的普通電腦建 dist,dist 是純靜態檔,帶回即可)。

### P5 通訊雙軌混用 + CSP 未設

- portal 同時用 IPC(invoke)與 loopback fetch;新功能沒有明確規範該走哪軌。
- `csp: null`:所有收緊都得改 `tauri.conf.json` → 也要重編殼 → 受 P4 限制。

---

## 第三部分:分析過程(如何查證的)

方法:不接受任何「應該是」,每個結論都讀碼取證。關鍵查證步驟與發現:

| # | 查證問題 | 方法 | 發現 |
|---|---|---|---|
| 1 | nativeApp 怎麼渲染工具? | 讀 `engine.py`、`main.jsx` | Streamlit subprocess + 127.0.0.1 iframe(方案 A) |
| 2 | CV_Viewer 在 nativeApp 裡是什麼形態? | 找 viewer/thumbwall 檔案 | module_006,**仍用 declare_component**(/component/ 還在) |
| 3 | portal↔engine 有沒有非 loopback 通道? | 讀 `bridge.rs`、`lib.rs` | 有:invoke→Rust ureq(host 端);但指令固定、無通用直通;portal 缺指令時退回 fetch |
| 4 | 前端本體怎麼載入? | `lib.rs:47` | `WebviewUrl::App` = tauri:// bundled,非 loopback |
| 5 | 殼能不能改? | `start-dev-tauri.bat`、prebuilt README | WDAC 擋 cargo;**使用者確認無建置機** → 殼凍結 |
| 6 | apply.py 套不套 source-packages? | grep apply.py | 只搬 wheels;原始碼套用是缺口 |
| 7 | module_006 的源頭? | `.gitmodules` | cim-modules 是 submodule(nativeApp_modules.git) |
| 8 | 打包→離線→跑起來整鏈可行? | 跑 `e2e/gui_flow_e2e.py` | app-lv + module_001 全 PASS(死位址 pip index 證明離線) |

裁決結論(先前文件已詳述):
- 「搬進 nativeApp」= 換殼不換傳輸層,**不算根治**(NATIVEAPP_ARCH_REVIEW.md)。
- 「原生工具(方案 B)」在 nativeApp 架構上**可行**,但完整版需要一次 Rust 擴充(NATIVEAPP_NATIVE_TOOL_POC_DESIGN.md)——
  而 P4 的新事實(無建置機)迫使它分期。

---

## 第四部分:結果一 — 三元件的目標分工

### 4.1 一句話定位

```text
CV_Viewer        = 內容(Content):工具的前端互動 + Python CV 演算法 —— 「工具長什麼樣、會算什麼」
nativeApp        = 平台(Platform):渲染契約、生命週期、通訊、相依安裝 —— 「工具怎麼跑起來、怎麼畫出來」
native_Provision = 部署(Deployment):把以上兩者可驗證地送進離線機 —— 「東西怎麼完整送到、裝得起來」
```

**分工鐵律:內容不碰埠與殼;平台不含任何工具的業務邏輯;部署不碰渲染。**
先前的混淆(「用 native_Provision 包 CV_Viewer 是不是就解決了」)正是把「部署」誤當「渲染」——
打包把檔案送到,攔截發生在執行時的請求路徑上,兩者互不替代。

### 4.2 各自的職責與交付物

**CV_Viewer(內容供應方)**
- 擁有:viewer 前端(OpenSeadragon、ROI、縮圖牆的 JS/HTML)、Python CV 模組(解碼、16-bit、標註、比對)。
- 交付物:**一個符合平台 plugin contract 的 module 資料夾**,經 `cim-modules` submodule 進版。
- 不擁有:執行殼、埠、iframe/protocol 決策、安裝方式。
- **單一真相決議(建議)**:`cim-modules` 的 module 為**部署真相**;獨立 CV_Viewer repo 轉為
  開發沙盒/上游來源(或逐步退役)。新的原生版 viewer 應以**新 module id**(如 `cv_viewer_native`)
  進 cim-modules,與 module_006 並存(可回退)。

**nativeApp(平台)**
- 擁有:Tauri 殼、portal(渲染契約:今 `mode="iframe"`,未來加 `mode="native"`)、engine(session、
  工具生命週期、deppack fail-closed 安裝)、plugin contract 本身。
- 對上(工具)的介面:`plugin.yaml`(id/version/enabled/requires/mode/entry)+ 未來的 native 工具契約
  (route + IPC schema,見 POC 設計文件第 3 節)。
- 對下(部署)的介面:`requires:` 宣告、`CIM_DEPPACK_CACHE`/`CIM_TOOL_VENVS_DIR` 語意、
  `core.tool_deps` 的離線安裝與驗章。

**native_Provision(部署工具鏈)**
- 擁有:掃描、目標鎖定(win_amd64/cp311)、wheel 下載與自檢、big-deps、manifest/verify、
  apply/warmup、launcher(run-platform.bat)、GUI 與 E2E 驗證。
- **未來要補的兩個能力**(見 4.3):`source-apply` 與 `assemble`。
- 永遠不做:改變工具的渲染方式、執行語意。

### 4.3 native_Provision 的兩個擴充(部署 pipeline 補洞)

1. **source-apply(優先)**:離線機端把 `source-packages/<id>/source/` 套進
   `engine\sidecar\python-engine\plugins\…\<id>\`,做法沿 apply.py 既有紀律:
   逐檔 sha256 驗證(對 `source-manifest.json`)→ 暫存組裝 → 原子換位 → 失敗不留半套。
   這補上「只改原始碼」更新流的最後一哩(現為手動複製)。建議做成 `apply.py --with-sources`
   或獨立 `apply_sources.py`(維持 apply.py stdlib-only 的自足性)。
2. **assemble(整包組裝)**:在連網機把四件事組成**單一可搬資料夾**(標準 APP_ROOT 佈局):
   `runtime\`(既有 build-runtime 產物)+ `engine\`(平台工作副本,含 prebuilt exe 與 portal dist)
   + `provision\`(本工具產物)+ 頂層 `start.bat`。離線機從「三個來源自己拼」變成「複製一個資料夾」。
   GUI 加一顆「組成離線整包」按鈕即可(純檔案複製 + manifest,不碰渲染)。

---

## 第五部分:結果二 — 目標部署流程(單一 pipeline)

### 5.1 連網機(建置/發布人員)

```text
[一次性]   scripts\win\build-runtime.bat            → runtime\python311(Python 升版才重做)
[每次更新] git pull / submodule update              → nativeApp(含 cim-modules 內容更新)
[每次更新] native_Provision GUI:
            1. 掃描 Module → 勾選
            2. 開始打包    → source-packages + packs + big-deps + manifests
                             + apply.py/warmup.py + run-platform.bat(自動烤入模式與專案路徑)
            3. (建議擴充) 組成離線整包 → APP_ROOT\{runtime, engine, provision, start.bat}
            4. (可選) GUI「實際套用與 Tauri 驗證」→ 出貨前在隔離資料夾實跑一次
```

### 5.2 離線機(工廠端使用者)

```text
1. 複製 APP_ROOT(單一資料夾;big-deps 可分開搬,缺了只會明確跳過該工具,不會壞)
2. 雙擊 provision\run-platform.bat
     [check]  可先自測:只驗路徑與計畫,不寫入
     [實跑]   apply(搬 wheel,秒級)→ (擴充後)source-apply → warmup(首次數十秒,之後指紋秒過)
              → 啟動平台 → 選工具 → Start
```

### 5.3 三種更新流(增量語意)

| 變更 | 連網機 | 離線機 | 現況 |
|---|---|---|---|
| 只改 module 原始碼 | GUI 重打包(source-package 增量,wheel 全沿用) | 搬 source-packages → **source-apply** | ⚠ 最後一哩手動(擴充 1 補) |
| 改 `requires:` | GUI 重打包(該工具 pack 重建,其餘秒過) | 搬 provision → run-platform.bat(apply+warmup) | ✅ 已可用 |
| 改平台(engine/portal dist) | git 更新 + 重出 engine 資料夾 | 覆蓋 `engine\` | ✅ 檔案級,可用 |
| 改 Rust 殼 | **需無 WDAC 建置機(目前沒有)** | 換 `cim-light.exe` | ❌ 凍結(P4) |

---

## 第六部分:結果三 — 分階段演進(對齊「無建置機」的現實)

### Phase 0(現況;已 E2E 驗證可用)
- 工具 = Streamlit + iframe;module_006 帶著 `/component/` 故障面。
- 部署 = provision 打包 + run-platform.bat 一鍵。
- **適用**:目標機的攔截成因是「外部瀏覽器 proxy 鏈」時,WebView2 內通常已可用;先實測再說。

### Phase 1(免 Rust 重編;現有 cim-light.exe 直接跑)— **移除 /component/ 與 Streamlit**
- engine(Python):加 `mode="native"` 工具型態 + `/native/*` session 端點 + CV adapter(沿用演算法)。
- portal(JS):加 `#/native/<toolId>` route,OpenSeadragon vendored 進 bundle;viewer 互動全在 tauri:// 前端。
- 傳輸:暫走既有 `fetch(sidecarControlUrl)`(WebView loopback HTTP)+ 既有 invoke 指令。
- 新工具 id `cv_viewer_native` 進 cim-modules;module_006 不動,feature flag 可回退。
- **效果**:handoff 的原始故障(`/component/` ~60s 逾時)被消除;殘留故障面 = WebView 的 loopback fetch。
- **開工前必驗**:本機 `npm --prefix apps\portal-react run build` 是否被 WDAC 擋(vite→esbuild 原生 exe)。
  被擋的 fallback:在任何一台**普通無 WDAC 電腦**(不需 Rust 工具鏈)建 dist 帶回——dist 是純靜態檔。

### Phase 2(需無 WDAC 建置機;**目前沒有 → 凍結,列觸發條件**)— 連 WebView loopback 都移除
- Rust:通用 `engine_call` 指令(invoke→ureq)+ `cimimg://` 二進位影像 protocol + CSP 收緊。
- 觸發條件(任一成立才啟動):
  (a) 取得任何一台可跑 cargo 的 Windows(同事機/暫借/雲端 VM 皆可,編完帶 exe 回來);
  (b) 實測證明目標機把 127.0.0.1 也強制走 proxy(Phase 1 的 fetch 軌失效);
  (c) 資安要求收緊 CSP / 禁 WebView 發任何 HTTP。
- Phase 1 的 IPC schema 設計已對齊 Phase 2(同一套 request/event 格式,只換傳輸層),屆時前端改動極小。

### 判斷實驗(隨時可做,5 分鐘)
在目標離線機:拔網路 + 系統 proxy 設無效位址 → 開 nativeApp 的任一 iframe 工具:
- 主頁 iframe 都載不出 → loopback 被攔 → Phase 2 是必要的(開始找建置機)。
- 主頁可載、`/component/` 逾時 → Phase 1 就是正解。
- 全部正常 → Phase 0 暫時夠用,Phase 1 仍建議做(消除已知地雷)。

---

## 第七部分:給下一位 AI 的開發指引

### 7.1 關鍵約束(違反任何一條 = 方向錯誤)
1. **本機不能 cargo build**(WDAC),且**目前沒有替代建置機** → 不要提出任何「先改 bridge.rs/lib.rs/tauri.conf.json 再說」的短期方案。
2. 平台鎖 **Python 3.11 / win_amd64 / cp311**;離線機無編譯器 → 相依必須有 wheel。
3. **不動 module_006**(Streamlit 版保留可回退);原生版用新 module id + feature flag。
4. 不要退回「Tauri 包 Streamlit」當作 `/component/` 的解;也不要只把 `declare_component` 換 `components.html`(單向,會失去 ROI/像素回傳)。
5. `apply.py` 必須維持 stdlib-only 自足(SPEC D8);source-apply 若做,遵守同樣的 sha256+原子換位紀律。
6. 大圖不要反覆 base64 JSON;Phase 1 可用 loopback binary 端點,Phase 2 換 `cimimg://`。

### 7.2 建議的開發順序(Phase 1)
1. 實測 portal dist 能否本機重建(vite/esbuild vs WDAC);不行就安排外機建 dist 的流程。
2. engine:`mode="native"` 分支 + `/native/session` + `viewer.openImage / pixel.read / roi.create`(schema 見 POC 設計文件第 3 節,含 requestId 防過期結果)。
3. CV adapter:從 module_006 / CV_Viewer 抽純函式(解碼、像素、ROI sidecar 寫入),不重寫演算法。
4. portal:native route + vendored OpenSeadragon + IPC/fetch 客戶端。
5. cim-modules:新增 `cv_viewer_native` module(plugin.yaml `mode: native`)。
6. native_Provision:確認新 module 能被掃描/打包(它有 requires 就產 pack,沒有就只有 source-package);(可並行)實作 source-apply 與 assemble。
7. 驗收矩陣(全自動化,參考 POC 請求文件「必做驗證」10 條):離網啟動、無效 proxy、network log 無 `/component/`、無 `streamlit run` 子程序、縮放/平移/像素/ROI 往返、連切 20 張無過期結果、關閉無殘留、中文/空格路徑。

### 7.3 檔案地圖(要動的地方)

| 層 | 位置 | Phase |
|---|---|---|
| engine native session | `nativeApp\sidecar\python-engine\engine.py` + 新 `core/native_session.py` | 1 |
| CV adapter | `cim-modules\modules\cv_viewer_native\`(新) | 1 |
| portal native route | `nativeApp\apps\portal-react\src\`(新 route + viewer 元件) | 1 |
| OSD 資產 | `portal-react`(vendored,自 CV_Viewer `viewer_component/openseadragon.min.js`) | 1 |
| source-apply / assemble | `native_Provision\src\provision_builder\` + `apply.py` 族 | 1(並行) |
| `engine_call` + `cimimg://` + CSP | `nativeApp\apps\host-tauri\src-tauri\`(bridge.rs/lib.rs/tauri.conf.json) | **2(凍結中)** |

### 7.4 未決問題(需要人拍板,不要替使用者決定)
1. CV_Viewer 獨立 repo 的最終定位:開發沙盒?退役?還是反向成為 cim-modules 的上游?
2. Phase 1 的影像傳輸選型(loopback binary vs base64 IPC)以量測定案——在目標機量,不在開發機量。
3. assemble 整包的 `engine\` 內容要不要瘦身(排除 .git、tests、node_modules 等)與授權/簽章議題。
4. 建置機的取得管道(哪怕一次性):決定 Phase 2 的啟動時間。

---

## 附錄 A:證據索引

| 事實 | 位置 |
|---|---|
| 工具 = streamlit subprocess | `nativeApp\sidecar\python-engine\engine.py:983` |
| 工具 URL = 127.0.0.1 | `engine.py:1403-1404,1450,1491`;mode 欄位 `engine.py:243,1392,1441` |
| portal 用 iframe 渲染工具 | `nativeApp\apps\portal-react\src\main.jsx:309,313,348` |
| portal 直接 fetch loopback | `main.jsx:581,789,887,962` |
| Rust 固定指令 + ureq 轉發 | `nativeApp\apps\host-tauri\src-tauri\src\bridge.rs:25-38,46-104`;註冊 `lib.rs:22-39` |
| 前端 tauri:// 載入 | `lib.rs:47`(`WebviewUrl::App`) |
| CSP 未設 | `apps\host-tauri\src-tauri\tauri.conf.json:13` |
| 關窗 graceful stop sidecar | `lib.rs:77-89` |
| WDAC 擋 cargo | `nativeApp\start-dev-tauri.bat:8-11,29-39` |
| portal 用 vite build(esbuild 原生 exe) | `apps\portal-react\package.json:7-14`;dist 需預建 `start-dev-tauri.bat:44-48` |
| module_006 用 declare_component | `plugins\cim-modules\modules\module_006\viewer.py:16`、`thumbwall.py:23` |
| cim-modules 是 submodule | `nativeApp\.gitmodules` |
| apply.py 不套 source-packages | `native_Provision\apply.py`(僅 packs/big-deps 邏輯) |
| provision 打包/離線語意 | `native_Provision\SPEC.md`、`docs\OFFLINE_DEPLOY.md` |
| 打包 E2E 全綠 | `native_Provision\e2e\gui_flow_e2e.py`(2026-07-11 實跑 PASS×2) |

## 附錄 B:一頁摘要(給趕時間的人)

> 三個 repo 的正確分工是 **內容(CV_Viewer)/ 平台(nativeApp)/ 部署(native_Provision)**。
> 目前的 `/component/` 故障住在**平台的渲染方式**(Streamlit + loopback iframe + declare_component),
> 所以打包器包得再好也治不了它——要改的是 nativeApp,加 `mode="native"` 的原生工具路徑。
> 因為本機 WDAC 且**沒有建置機**,Rust 殼凍結:先做 **Phase 1**(純 Python+JS,移除 Streamlit/`/component/`,
> 現有 exe 直接跑),把 IPC schema 設計成 Phase 2(`engine_call`+`cimimg://`,拿到建置機再做)可無痛接軌。
> 部署側,native_Provision 已能一鍵(run-platform.bat),再補 **source-apply**(原始碼自動套用)與
> **assemble**(組單一 APP_ROOT 整包),離線機就是「複製一個資料夾 + 雙擊一個 bat」。
