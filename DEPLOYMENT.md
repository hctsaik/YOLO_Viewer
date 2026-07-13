# 部署指南(換機安裝 + 元件載入疑難排解)

## 安裝(新機器)

```bat
git clone <repo> CV_Viewer        REM 或解壓完整打包 zip(打包勿排除 *_component 內任何檔案)
cd CV_Viewer
pip install -r requirements.txt
run.bat                           REM 一鍵啟動;或 python -m streamlit run 5_PG_Develop\app.py --server.port 8501
```

### 完全離線安裝(目標機無外網,連 pypi 都到不了)

打包 zip 若含 `wheels/` 資料夾(在有網路的機器上用
`pip download -r requirements.txt -d wheels` 產生),目標機**不需外網**即可裝依賴:

```bat
cd CV_Viewer
pip install --no-index --find-links wheels -r requirements.txt
run.bat
```

前提:目標機的 **Python 主版本與位元數**須與產 wheels 的機器一致(wheels 檔名可查,
如 `cp314`+`win_amd64` = Python 3.14 / 64-bit Windows);且目標機已裝 Python 本體
(離線機請一併帶 python.org 的安裝檔)。前端資產(OpenSeadragon 等)本來就 vendored
在專案內,無需任何下載。

**鐵則:瀏覽器一律用 `http://localhost:8501` 開。** 不要用 Streamlit 印出的
Network URL(機器 IP)——Chromium/Edge 對 `localhost` 有「隱含 proxy 繞過」,
用 IP/主機名開則公司 proxy 會介入(見下)。

離線/內網機注意:本專案前端資產(OpenSeadragon 等)全部 vendored 在
`5_PG_Develop/viewer_component/`、`thumbwall_component/`,**不需要外網**。

## 疑難排解:「Your app is having trouble loading the viewer.cv_viewer component…」

這條橫幅 = Streamlit 前端「元件 **60 秒**內沒回報 `setComponentReady()`」的逾時訊息
(原始碼 `ComponentInstance.js`,`COMPONENT_READY_WARNING_TIME_MS = 60000`)。**與 CDN/外網無關。**

### 🛟 最快的解法:安全模式(不必動 proxy / 防毒 / 瀏覽器 / IT)

```bat
run_safe.bat            REM 等同 set CVR_SAFE_MODE=1 後啟動;進去後可在側欄「🛟 安全模式」關掉
```

viewer / thumbwall 是 Streamlit **自訂元件**:瀏覽器得另抓 `/component/` 資產、在 iframe 內執行腳本、
60 秒內回報 ready。**橫幅的兩大成因都卡在這條路上**,而且**元件端程式碼修不了**:

- **A 類**:內容過濾 proxy / 防火牆 / 防毒攔掉或拖慢 `/component/` 資產(iframe 的 HTML 根本抓不到)。
- **B 類**:端點防護 / 群組原則封鎖 iframe 內的腳本(抓得到但 ready 送不出)。

安全模式**完全不走那條路**:縮圖牆 → `st.image` + `st.button`;主 viewer → server 端 `overlay.draw`
燒框後 `st.image`;縮放平移 → server 端 `viewport.crop_rect` 裁切。瀏覽器只需要能顯示主頁
(已知是好的 —— 出橫幅時主頁本來就正常)。**A 類與 B 類同時被繞開。**

| | 一般模式 | 🛟 安全模式 |
|---|---|---|
| `/component/` 請求 | 4+ | **0** |
| 元件 iframe | 2 | **0** |
| 判片 / 切圖 / 標記 / 比較 / 匯出 | ✅ | ✅ |
| 偵測框 + 類別色 + cls·conf | ✅ | ✅(server 端燒進圖裡) |
| 縮放 / 平移 | 滑鼠滾輪拖曳 | 側欄滑桿(倍率 / 水平 / 垂直) |
| 拖曳框選 ROI、點擊取像素值、鍵盤熱鍵 | ✅ | ❌(已知取捨) |

紅→綠對抗驗證:`python verify/repro_safe_mode.py`(真 forward proxy 擋 `/component/` → 403,
Chromium 走 `--proxy-server` 且用機器 IP 開)。**S1 先證明同環境下關掉安全模式必紅**(橫幅出現、
4 個 `/component/` 請求),S2 開安全模式後 `/component/` 請求 0、元件 iframe 0、影像與縮圖真的算繪。

> 若你**有能力**改該機環境(proxy 例外 / 防毒白名單 / 換瀏覽器),下面的 A/B/C/D 分類處置能讓你
> 回到功能完整的一般模式;安全模式是「環境改不動、或人到不了現場」時的可用解。

**2026-07-08 已做的加固(誠實分級:哪些現場已證、哪些是建模推定)**:

- **現場已證、且對症的**:最能對上現場症狀「主頁正常、只有兩元件壞、用機器 IP 開」的是
  **#1 = proxy 在非 localhost 路徑上整條擋掉 `/component/` 資產**(真 forward proxy 重現 →
  console `source error 403` + 60s 橫幅)。**這種故障元件碼無法修**(iframe 的 HTML 本身抓不到)。
  對症作法:① `app.py` 啟動時偵測「用非 localhost 開」→ 主頁(不被擋)直接顯示指示,引導改用
  localhost / 加 proxy 例外;② 一律用 `http://localhost:8501` 開。
- **推定的根因之一、現場未直接證實**:內嵌 `<script>` 被「內容過濾 proxy 剝除」或「CSP
  `script-src 'self'` 禁止執行」(#3/#4)。**這是用我方寫的真 proxy『建模』出來的機制,現場沒有
  直接證據**(現場「index.html 沒 JavaScript」的報告也可能是看錯檔或搬運壞檔)。針對它的加固=把
  兩元件 JS 抽成**同源外部 `main.js`**(`<script src="main.js">`),內容過濾/CSP 皆放行外部 script。
  已用真 forward proxy 對抗驗證:剝內嵌情境**內嵌版紅、外部版綠且完整算繪**(`verify/repro_real_proxy.py`;
  另有較早的 page.route 版 `verify/repro_component_banner.py`)。此加固無害,但不宣稱它就是現場的病。
- **仍不可由程式修的**(環境問題):整條 `/component/` 被擋(console `source/fetch error`)、或回應被拖過
  60 秒——靠 localhost / proxy 例外 / 防毒白名單處置。
- **另一種現場已證的同症故障**:打包/搬運把 `main.js` 弄不見或改名(Gmail-safe 打包 `.js→.js.txt`)→
  main.js 404 → 同樣橫幅。`app.py` 啟動時會檢查兩個 `main.js` 是否存在,缺了就在主頁明講。

**第一步:跑 `diagnose.bat`**(開 `http://localhost:8502` 的診斷頁),照頁面判讀表處置。

| 診斷結果 | 原因 | 處置 |
|---|---|---|
| ⚠️ 用機器 IP 開 | proxy 不繞過 IP,內容過濾攔掉 `/component/` 資產 | **改用 `http://localhost:8501`**(最常見) |
| fetch/img ❌ | proxy / 防火牆 / 防毒攔截(情境 A) | proxy 例外加 `localhost;127.0.0.1`;專案資料夾加防毒白名單 |
| ✅ 但 >5000ms | 防毒即時掃描拖慢,主 app 60s 逾時(情境 A 變體) | 防毒白名單;重整主 app 一次 |
| 「內嵌腳本未執行」❌ | 瀏覽器/政策封鎖 iframe 內嵌 script(情境 B) | 換一般的新版 Chrome/Edge;或請 IT 放行 |
| ① 磁碟檢查 ❌ 缺檔 | 專案沒複製齊(打包排除了 `images/` 之類) | 重新 git clone / 完整複製 |

F12 Console 對照(給 IT 看):`Custom Component ... source error / fetch error` = 情境 A;
只有 `timeout error` = 情境 B。

## 已實測的重現與解法(2026-07-06,本機紅→綠驗證)

- 紅:內容過濾 proxy(擋 `/component/`)+ 瀏覽器用機器 IP 開 → 主頁正常、
  兩元件 60 秒後跳出與現場一字不差的橫幅。
- 綠 1:同一個壞 proxy,改用 `http://localhost` 開 → 全部正常(隱含繞過)。
- 綠 2:仍用 IP 開,瀏覽器 `--no-proxy-server` → 全部正常。
- 另排除:乾淨 clone 在 Streamlit 1.56.0 與 1.58.0、中文+空格路徑、LAN IP 直開(無 proxy)
  皆正常 → repo 本身無罪。

## 已知限制與殘料處置(2026-07-08 紅隊收尾,誠實記錄)

經三輪 multi-agent(找+修 → 驗證 → 紅隊)後,以下是**刻意不再修、留作已知限制**的項目及理由——
記在這裡避免下次有人誤以為是漏洞、或重複挖同一個坑:

| 殘料 | 處置 | 理由 |
|---|---|---|
| **從別台機器用 IP 連入**時,元件仍載不動 | **文件記錄,無程式解** | #1(proxy 擋 `/component/`)架構上元件碼不可修;「改用 localhost」對遠端使用者不適用,只能請 IT 把此位址加進 proxy/防毒例外。app 端提示已如實說明兩種情形。 |
| 非-localhost 提示**在「無 proxy 的健康遠端存取」也會顯示** | **降級即可、不做客戶端探測** | 已從紅色 `st.error` 降成**條件式 `st.info`**(「**若**下方載入失敗才是這原因;正常顯示請忽略」)。更精準的作法是客戶端 fetch 探測 `/component/` 才警告,但那要靠 srcdoc iframe 注入 JS、增加新表面/新風險;權衡後保留 host 判斷 + 非驚嚇文字。 |
| 舊版 Streamlit(無 `st.context.url`)時提示**靜默不顯示** | **靠版本 pin 緩解** | `requirements.txt` pin `streamlit>=1.56`,該版起 `st.context.url` 存在;guard 的 `try/except` fail-open(判為 localhost、不誤報也不崩)。 |
| 反向代理/非 8501 埠時,提示裡的 `localhost:PORT` 連結可能指錯埠 | **視為超出範圍** | 本工具設計為本機直開 `localhost:8501`;反向代理部署非支援模式。 |
| `127.0.0.2` 等 loopback、大小寫、`::ffff:127.0.0.1` 誤判 | **已修** | loopback 判定改用 `ipaddress.is_loopback`(涵蓋 `127.0.0.0/8`、`::1`、IPv4-mapped),非字面清單。 |
| 迴歸工具「無 LAN IP 時假綠」 | **已修 + 真測** | `verify/repro_real_proxy.py` 無 LAN IP 時印 `INCOMPLETE`、`exit 2`(不印 GREEN);用 `RRP_FORCE_NO_LAN=1` 已實跑確認(非僅讀碼)。 |
| `#3`(內容過濾剝內嵌 script / CSP)是不是現場的病 | **文件標為『建模推定、現場未證實』** | 只由我方真 proxy 建模重現,無現場證據;main.js 外部化是無害加固,不宣稱是現場根因。**真正確認需現場那台機器的一張 F12 Network/Console 截圖。** |
## 離網可靠模式（2026-07-11;預設已於 2026-07-13 翻回完整模式,見下）

安全模式:viewer 與 thumbwall 使用 Streamlit 原生元件算繪,完全不建立 `/component/` iframe,
因此不受公司 proxy、防毒、CSP 或端點防護攔截。

### ⚠️ 預設模式變更(2026-07-13,User 裁決)

一度把 `run.bat` 的預設設成安全模式(`CVR_SAFE_MODE=1`),但那讓**每一台正常機器**也吃降級體驗——
安全模式沒有 OpenSeadragon:**滾輪不縮放、不能拖曳平移、不能 Shift 框選 ROI、不能點擊取像素值**
(User 回報:「我現在滑鼠的滾輪不再放大縮小,而是做平移」——就是這個)。

**現在的預設 = 完整模式。** 對照表:

| 啟動方式 | `CVR_SAFE_MODE` | 得到什麼 |
|---------|----------------|---------|
| `run.bat`(雙擊) | `0` | **完整模式**:滾輪縮放 / 拖曳平移 / 框選 ROI / 點像素值 |
| `run_full.bat` | `0` | 同上(明示版) |
| `run_safe.bat` | `1` | 安全模式:純 server 端算繪,不走 iframe |
| 側欄「🛟 安全模式」開關 | — | 隨時互換,不必重啟 |

**受限網路那台機器 → 用 `run_safe.bat`。** 判斷方式不變:元件跳「trouble loading the component」
黃色橫幅 = 該機器擋掉了 `/component/`;先跑 `diagnose.bat` 判 A/B 類,瀏覽器一律開 `http://localhost:8501`。

## 🔥 DINO 語意差異比較的模型權重(2026-07-13)

比較模式的「🔥 DINO 語意差異」需要一個 DINOv2 權重(`.pth`)。**它永遠不會上網下載**:
架構原始碼已 vendored 在 `5_PG_Develop/dinov2_hub/`(1.1MB,進 repo);權重不進 repo(88MB)。

搬到新機器時,權重三選一(app 依此順序找,見 `dinodiff.resolve_model_path`):
1. app 內按 **📁**(比較模式 → 檢視方式選 DINO → 模型列右邊)開檔案總管挑 `.pth`;
2. 環境變數 `CVR_DINO_MODEL` = 權重完整路徑;
3. 丟進 `models/`(檔名如 `dinov2_vits14.pth`),或設 `CVR_MODELS_DIR` 指向共用模型夾
   (**Tauri 殼日後把它的模型資料夾設進這個變數即可接上**,不需改任何程式)。

找不到權重時 app 只顯示提示,**不崩、不連外網**。細節見 `models/README.md` 與 `3_Architect_Design/27_dinodiff.md`。
