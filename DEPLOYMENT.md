# 部署指南(換機安裝 + 元件載入疑難排解)

## 安裝(新機器)

```bat
git clone <repo> CV_Viewer        REM 或解壓完整打包 zip(打包勿排除 *_component 內任何檔案)
cd CV_Viewer
pip install -r requirements.txt
run.bat                           REM 一鍵啟動;或 python -m streamlit run 5_PG_Develop\app.py --server.port 8501
```

**鐵則:瀏覽器一律用 `http://localhost:8501` 開。** 不要用 Streamlit 印出的
Network URL(機器 IP)——Chromium/Edge 對 `localhost` 有「隱含 proxy 繞過」,
用 IP/主機名開則公司 proxy 會介入(見下)。

離線/內網機注意:本專案前端資產(OpenSeadragon 等)全部 vendored 在
`5_PG_Develop/viewer_component/`、`thumbwall_component/`,**不需要外網**。

## 疑難排解:「Your app is having trouble loading the viewer.cv_viewer component…」

這條橫幅 = Streamlit 前端「元件 **60 秒**內沒回報 `setComponentReady()`」的逾時訊息
(原始碼 `ComponentInstance.js`,timeout 60000ms)。**與 CDN/外網無關。**

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
