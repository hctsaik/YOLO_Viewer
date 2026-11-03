# NativeApp 原生 CV Viewer POC 實作請求

## 前置文件

請先完整閱讀：

1. `C:\code\claude\CV_Viewer\TAURI_NATIVEAPP_HANDOFF.md`
2. `C:\code\claude\CV_Viewer\NATIVEAPP_ARCH_REVIEW.md`

我們已確認目前 `module_006` 仍是：

```text
Tauri WebView2
→ portal-react
→ 127.0.0.1 Streamlit iframe
→ /component/ viewer/thumbwall iframe
```

因此，這一階段不是再包裝 Streamlit，也不是調整 Custom Component timeout，而是驗證 NativeApp
能否支援真正的「原生前端工具」。

## 本階段目標

請在 NativeApp 建立一個最小但可執行的原生 CV Viewer POC，證明以下路徑成立：

```text
Tauri bundled frontend
→ bundled OpenSeadragon
→ NativeApp IPC/session bridge
→ Python engine/CV modules
```

POC 必須完全不使用：

- `streamlit run`
- `st.components.v1.declare_component`
- `/component/`
- Streamlit component iframe
- CDN 或任何公網資產

## 先做設計審查，再實作

請先提交一份短設計，回答以下問題；設計確認後才實作：

1. NativeApp 應新增哪一種工具模式，例如 `mode="native"`，以及它如何與現有 `mode="iframe"`
   共存。
2. 原生工具如何註冊、啟動、取得工具 ID、case/session ID 及關閉通知。
3. portal React 是否直接承載 viewer，或載入另一個 bundled route／bundle。
4. 前端如何呼叫 Python engine；請優先使用既有 NativeApp 通訊能力，不要先新增 loopback HTTP。
5. Python session 狀態放在哪裡，避免原生 viewer 與既有 Streamlit `st.session_state` 各自持有真相。
6. 本機影像如何安全、高效地交給 WebView2；不得將大圖反覆包成巨大 base64 JSON。
7. Windows 完全離網、無管理員權限、中文與空格路徑下的資產與 sidecar 路徑策略。

## POC 功能範圍

只需要完成一條最小垂直切片：

1. 從既有 `sample_images` 或使用者選定資料夾載入一張影像。
2. Python 解碼影像；需至少支援目前 PNG，並說明 16-bit TIFF 的後續接法。
3. Tauri bundled frontend 顯示影像。
4. OpenSeadragon 支援滾輪縮放與拖曳平移。
5. 點擊影像後，把原始影像座標送到 Python。
6. Python 讀取真實像素值並回傳前端顯示。
7. Shift + 拖曳建立 ROI，把 `[x, y, width, height]` 送到 Python。
8. Python 暫存或寫入測試 sidecar，再把已確認 ROI 回傳並疊加顯示。
9. 關閉工具後，session、listener、worker 與 Python 工作全部正確釋放。

本階段暫時不要求完整縮圖牆、篩選、比較模式與全部 Streamlit 控制，但 API 不應阻礙後續加入。

## 建議事件契約

可調整命名，但請維持版本化、request ID 與明確錯誤格式：

```json
{
  "version": 1,
  "requestId": "uuid",
  "toolSessionId": "uuid",
  "type": "viewer.openImage",
  "payload": {
    "path": "C:\\data\\sample.tif"
  }
}
```

```json
{
  "version": 1,
  "requestId": "uuid",
  "toolSessionId": "uuid",
  "type": "viewer.pixel.read",
  "payload": {
    "imageId": "uuid",
    "x": 123,
    "y": 456
  }
}
```

```json
{
  "version": 1,
  "requestId": "uuid",
  "toolSessionId": "uuid",
  "type": "viewer.roi.create",
  "payload": {
    "imageId": "uuid",
    "bbox": [100, 120, 240, 180]
  }
}
```

錯誤至少要包含：

```json
{
  "requestId": "uuid",
  "ok": false,
  "error": {
    "code": "IMAGE_DECODE_FAILED",
    "message": "User-facing summary",
    "detail": "Diagnostic detail"
  }
}
```

## 安全與效能要求

- 所有 HTML、JavaScript、CSS、OpenSeadragon、圖示與字型必須 bundled。
- 不允許 `unsafe-eval`；若需要 `unsafe-inline`，必須說明原因並提出移除計畫。
- 前端不得直接獲得任意 filesystem 權限；路徑需經 Python／Tauri allowlist 或 token 化。
- IPC 必須綁定 `toolSessionId`，避免不同工具或視窗交叉讀取資料。
- 影像傳輸需評估 custom protocol、受控暫存檔、binary channel 或 texture；請用量測選擇。
- 不把任意本機絕對路徑直接暴露為可被 WebView 任意讀取的 URL。
- 載入新影像時應取消或丟棄舊 request，避免快速切圖後舊結果覆蓋新畫面。

## 必做驗證

POC 不以「畫面看得到」作為完成標準，必須自動化或以可重現腳本證明：

1. 系統完全離網時可啟動。
2. 系統 proxy 設為無效位址時仍可完整操作。
3. Network log 中沒有 `/component/`。
4. 沒有 Streamlit iframe，也沒有 `streamlit run` 子程序。
5. 沒有任何外部 HTTP/HTTPS、CDN、telemetry 或執行期下載。
6. 縮放、平移、點擊座標、像素回傳及 ROI 往返成功。
7. ROI 座標以原始影像座標保存，不受 viewport zoom/pan 影響。
8. 快速連續切換至少 20 次，不會顯示過期結果。
9. 關閉 POC 後沒有殘留 Python、port listener 或 worker。
10. 中文及空格路徑可以載入影像。

請附上測試命令、結果與必要的 Network／process 證據。

## 回退與隔離要求

- 不要直接破壞既有 `module_006`。
- POC 應使用獨立 feature flag、tool ID 或 route。
- 現有 `mode="iframe"` 工具必須維持可用。
- 原生工具框架若尚未成熟，移除 POC 不應影響其他工具。
- 不要先重寫現有 Python CV 演算法；優先透過 adapter 沿用。

## 本階段交付物

請交付：

1. 架構決策與資料流圖。
2. 修改檔案清單。
3. 原生工具註冊／manifest 格式。
4. TypeScript 與 Python 的 IPC schema／型別。
5. 可執行 POC。
6. 自動化測試與離網驗證結果。
7. 已知風險、未完成項目與下一階段估算。

## 完成定義

只有在 POC 同時保留 viewer 雙向互動，且完全沒有 Streamlit `/component/`、Streamlit iframe
與外部網路依賴時，才算證明方案 B 可行。

如果 NativeApp 現有架構無法在不新增 loopback HTTP 的情況下讓 portal 與 Python engine 通訊，
請先停在設計階段，清楚列出缺少的平台能力與最小平台擴充，不要退回「用 Tauri 包住 Streamlit」作為完成方案。
