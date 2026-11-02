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
- 標記修改後可按「保存判讀」寫入；若直接切圖或重新選擇資料夾，先自動保存目前影像的 sidecar。保存失敗時留在目前影像並保留修改，不能丟棄資料。
- 此切片不包含 ROI crop 匯出、ROI 標籤編輯或 YOLO／ROI 疊圖控制。

驗收須涵蓋 ROI source 座標與邊界、向量框顯示、sidecar 保存／讀回／移除及原圖唯讀。

## Review Undo

- Verdict、Review Status、Bookmark 的每次實際變更記錄舊值，最多保留最近 5 筆；Tag、Comment 與 ROI 不進此 Undo 歷程。
- 在 Viewer 按 `u` 撤銷最近一筆；若該修改屬於另一張影像，先切回該影像，再還原欄位並保存 sidecar。撤銷後顯示確認訊息。
- 歷程為目前資料夾工作階段所有；重新選擇資料夾時清除。空歷程按 `u` 不修改資料並提示「無可撤銷」。

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

## 舊版使用情境 → React 驗收矩陣

舊版 E2E 是行為來源；只有 React 瀏覽器驗收通過才算遷移。既有 Python 純邏輯模組的單元測試可保護共用 domain 行為，但不能替代 React UI 流程驗收。

| 使用情境 | 舊版驗收來源 | React 覆蓋 | 狀態與差距 |
|---|---|---|---|
| 開啟資料夾、自然排序、切圖、影像資訊與像素真值 | `test_app_e2e.py`、`test_viewer_ux_e2e.py` | `web/e2e/local-review.spec.ts` | 部分：排序、PNG/TIFF、metadata、pixel oracle、切圖與重開讀回已驗；OS 資料夾選擇器與真實磁碟存取仍由替身模擬。 |
| Viewer 縮放／平移、hover HUD、minimap、畫面狀態 | `test_m7a_e2e.py`、`test_viewer_ux_e2e.py` | `web/e2e/local-review.spec.ts` | 部分：縮放／平移後像素座標已驗；hover 座標與類別、縮放上限、minimap、導覽時檢視狀態尚未移植或驗收。 |
| Bookmark、Tag、Verdict、Comment、Review Status、快捷鍵、自動保存與 Undo | `test_m7b_e2e.py`、`test_widget_state_persistence_e2e.py` | `web/e2e/local-review.spec.ts` AC3–AC9 | 部分：標記欄位讀回、切圖／重選資料夾前自動保存、失敗保留修改、箭頭導覽、`1/2/3` verdict、`r` status、`b` bookmark 及輸入欄焦點保護已驗；Undo 的三欄位歷程、同值排除、五筆上限、保存失敗可重試、跨圖 LIFO、多步回復與空歷程已驗。一般編輯仍以手動保存或切圖／重選資料夾時自動保存，尚未做到每次編輯即時落盤。 |
| ROI 框選、顯示、移除與 sidecar 讀回 | `test_viewer_ux_e2e.py`、`5_PG_Develop/app.py` | `web/e2e/local-review.spec.ts` AC4 | 部分：正反向拖曳、overlay、移除、保存與讀回已驗；ROI crop 匯出和實際 OS 檔案權限尚未驗。 |
| 依信心／類別篩選偵測結果，並在切圖或收合後保留設定 | `test_conf_range_e2e.py`、`test_widget_state_persistence_e2e.py`、`test_thumbwall_collapse_recovery_e2e.py` | — | 待移植：React 尚無偵測篩選與設定持久化流程。 |
| 偵測框疊圖、縮圖偵測標記與物件聚焦 | `test_viewer_ux_e2e.py`、`test_focus_object_e2e.py` | — | 待移植：React 尚無 YOLO 結果載入、疊圖篩選與 focus 行為。 |
| 標記比較佇列、FIFO、疊合／並排／差異及清除 | `test_compare_e2e.py` | — | 待移植：React 尚無多圖比較流程。 |
| DINO 語意差異熱圖與模型缺漏提示 | `test_dinodiff_e2e.py` | — | 待移植：尚無本機模型呼叫與熱圖 UI 驗收。 |
| 影像工具箱調整、切圖重設且不改變偵測結果 | `test_cv_toolbox_e2e.py` | — | 待移植：React 尚無工具箱操作。 |
| 點位釘選、縮圖牆／側欄響應式版面與收合復原 | `test_pin_point_e2e.py`、`test_rwd_e2e.py`、`test_thumbwall_collapse_recovery_e2e.py` | — | 待移植：React 尚無 pin point、縮圖牆與舊版收合行為的等價驗收。 |
| Case Package、HTML 報告、相似影像及其他匯出／分析 | `test_casepkg.py`、`test_htmlreport.py`、`test_simhash.py`、`test_embcluster.py` | — | 待移植：Python domain 測試仍在，但 React 入口與端到端交付尚未驗。 |
| NativeApp 離線套件、公開 host API、ARM64 與真實本機檔案權限 | 本 PRD 產品邊界 | — | 宿主待驗：不能以瀏覽器替身或 Python API 測試宣稱通過。 |

每列維持來源測試檔名以供追溯；React 測試要覆蓋使用者可見結果、保存／重開效果及必要的錯誤情境。M10 完成前不得把「部分」或「待移植」列標成完成。
