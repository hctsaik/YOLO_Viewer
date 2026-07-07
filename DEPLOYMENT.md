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
