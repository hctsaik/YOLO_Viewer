# PRD 增補 03:viewer 架構定案(獨立原型 + OpenSeadragon 宣告式元件)

> `/po`+`/architect` 聯合決策增補。承增補 02 與 `3_Architect_Design/00`,並依對 nativeApp 架構的實地勘查。

## 背景(對 nativeApp 的勘查結論)
真正載體 nativeApp = Electron → React portal →(iframe)→ 每工具一個 Streamlit 子程序;
另有常駐 **FastAPI engine sidecar**(本地 HTTP)、**postMessage 協議**(Streamlit→portal)、
`chooseFile→/selected-paths→env` 檔案橋接。renderer 是沙盒(`contextIsolation:true / nodeIntegration:false`),
**不能直接讀本機檔**;大圖正解是「engine 用 HTTP 供圖/tiles,viewer client-side 縮放」。

## 決定
1. **先做獨立 Streamlit 原型**(不直接進 nativeApp),驗證 viewer 概念後再移植。
2. **viewer = OpenSeadragon,經 Streamlit 宣告式元件嵌入**(client-side 滾輪縮放/平移/鍵盤/hover/ROI)。

## 關鍵技術更正(影響「事件回傳」的生死點)
- `st.components.v1.html()` / `iframe()` 是**單向**的,**無法把值回傳 Python**。
- 要回傳 ROI/點擊/view → 用 **`components.declare_component(path=...)` + 手寫 static `index.html`**
  (實作元件協定:`componentReady`/接收 `render` args/`setFrameHeight`/`setComponentValue`)。
  **不需要 React/npm build**;OpenSeadragon 由 CDN 載入。
- (移植到 nativeApp 時可改用既有 `postMessage → React portal` 路徑,二擇一。)

## 影像供應(分階段,先簡後繁)
- **spike / 早期**:Python 產生/讀圖 → base64 data URL 當 OSD simple-image source(證明機制,免 static server)。
- **獨立原型大圖**:小型本地 static server 供圖(或 DZI tiles);**移植 nativeApp 時改由 engine HTTP 端點供應**。
- 16-bit:server 端先 window/level → 8-bit 顯示;**原始 16-bit 真值**用「點擊 → 回 Python 查值」(viewport 換算座標),
  hover 連續真值列為後續(需把資料送進元件)。

## 對 M1a 模組的影響
- `viewer_component`(Tier B):= 一個 **static 宣告式元件(OpenSeadragon + 元件協定 index.html)** + Python 包裝函式;
  client-side 滾輪縮放/平移/鍵盤/ROI;`setComponentValue` 回傳 `{view, click(x,y), roi}`。
- `viewport`(Tier A,不變):解讀元件回傳的 view/點 → source 座標與裁切矩形(供取真值、ROI 存檔、匯出)。
- `imageio`(Tier B):讀 8/16-bit/TIFF/大圖 → 8-bit 顯示影像(window/level)+ 保留原始陣列供查值;供圖給元件。

## 生死點 spike(先做,放 `spike/`,非契約層)
證明:**獨立 Streamlit 裡,OpenSeadragon 能滾輪縮放,且點擊/ROI 座標能 `setComponentValue` 回到 Python。**
過 → 放行設計 M1a;不過 → 反向閘門,改評估(side HTTP channel / 移植 nativeApp 用 portal / 換 host)。
