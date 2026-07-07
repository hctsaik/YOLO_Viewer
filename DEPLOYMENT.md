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

**2026-07-08 已做的加固**:兩個元件的 JS 原本是 HTML 內嵌 `<script>`,已抽成**同源外部
`main.js`**(`<script src="main.js">`)。內嵌 script 會被「內容過濾 proxy 剝除」或「CSP
`script-src 'self'` 禁止執行」,那正是部分受限網路跳橫幅的根因;外部同源 script 則兩者皆放行
(與主畫面的外部 bundle 一樣穩)。已用 `verify/repro_component_banner.py` 對抗驗證:剝內嵌 /
CSP 兩情境**修前紅、修後綠**,且 viewer/thumbwall/app E2E 全綠、無退化。
**仍不可由程式修的**(環境問題,恆紅):整條 `/component/` 被擋(console 出 `fetch error`/
`net::ERR`)、或回應被拖過 60 秒——這兩種要靠下面的 localhost/proxy 例外/防毒白名單處置。

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
