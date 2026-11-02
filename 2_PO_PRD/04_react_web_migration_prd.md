# PRD 增補 04：React Web 遷移

> 產品決策：承接既有 CV Review Workbench 功能，依使用者指示把受支援 UI 轉為 React Web。這是 UI／啟動架構遷移，不表示原功能矩陣已完成移植。

## 目標

- 在 Windows 本機以 React Web 開啟影像資料夾與 Review Workbench。
- Python 本機服務沿用 `imgio`、`imageset`、`viewport`、`sidecar`、`tagging`、`roi`、`yolo`、`overlay`、`dzitiles` 等既有行為。
- 保留人工標記格式、原始影像唯讀與離線部署能力。
- 以 React 驗收矩陣追蹤所有現有使用者可見流程，逐步停止 Streamlit runtime 支援。

## 第一階段範圍

完成最小可用的單機流程：啟動 React／Python 本機服務、授權資料夾、顯示自然排序清單、開啟影像、zoom／pan、顯示圖像資訊及原始像素值、讀寫 sidecar、關閉服務後重開並讀回。先支援既有 `imgio` 已承諾的 PNG／JPEG／TIFF 範圍；BMP 等輸入依既有 imageset／decoder 契約逐項納入。

此階段建立介面、影像存取及 sidecar 生命週期。除下方 ROI 標註切片明確涵蓋的操作外，不宣稱 ROI crop、YOLO overlay、全部標籤工具、排序、案例匯出、聚類、差異分析或桌面 host parity 已完成。這些功能依現有 PRD 與測試逐項遷移。

## ROI 標註切片

- 在主 viewer 以 Shift+拖曳新增 ROI，拖曳範圍轉成原圖像素座標 `(x, y, w, h)` 並夾在影像邊界內。
- 沿用 `.cvr.json` 的 `rois` 陣列與既有項目欄位 `bbox`、`label`、`verdict`、`comment`；顯示已保存 ROI，允許移除。
- 新增 ROI 後標記 sidecar 為待保存；使用既有「保存判讀」動作寫入。切圖前維持既有未保存變更提示。
- 此切片不包含 ROI crop 匯出、ROI 標籤編輯或 YOLO／ROI 疊圖控制。

驗收須涵蓋 ROI source 座標與邊界、向量框顯示、sidecar 保存／讀回／移除及原圖唯讀。

## 產品邊界

- 瀏覽器選取資料夾的權限由使用者授予，瀏覽器模式不收任意絕對路徑。
- Sidecar 仍與影像同目錄、同檔名主幹，使用既有 `.cvr.json` 欄位及合法列舉；寫入不得改原圖。
- 服務預設只綁 loopback；API 寫入需同源及短效本機工作階段驗證。
- NativeApp adapter 只依已發布的公開 host API 實作。未驗證的 OS picker／ARM64／model bridge 保持明確未完成。
- React 與 Python 可獨立開發；一般使用者的發佈套件不要求 Node 或 Streamlit。

## 驗收順序

1. React bundle、Python service 與本機配對／同源 API。
2. 授權資料夾、影像清單、解碼預覽、viewport 與像素查詢。
3. Sidecar load/save、重開讀回及來源檔雜湊不變。
4. 舊版功能矩陣逐列遷移，包含真實瀏覽器畫面驗證。
5. 離線套件與發布版 NativeApp host、架構及資源容量驗收。
