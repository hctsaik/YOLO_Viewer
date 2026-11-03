# CV Viewer 移入 Tauri NativeApp：架構評估請求

## 我要確認的問題

我有一套 Python + Streamlit 的離線 CV Viewer。現在 viewer 與 thumbwall 使用 Streamlit
Custom Component；在部分離網或企業管控環境中，主頁可以正常開啟，但瀏覽器載入
`/component/` iframe 時會被 proxy、防毒、CSP 或端點防護攔截，約 60 秒後出現：

> Your app is having trouble loading the viewer.cv_viewer component.

我想把系統放進 Tauri NativeApp。請評估：怎樣的整合方式才能真正移除這個故障面，並保留完整互動功能？

請不要只回答「包進 Tauri 就不會有問題」。Tauri WebView 仍可能受 proxy、CSP、資產路徑、
localhost server 與 iframe 設計影響。請根據下面的現況提出具體架構、風險及驗證方法。

## 現有系統

- 作業系統：Windows，部分目標機完全離網，且可能有企業 proxy、GPO、防毒及端點防護。
- 後端：Python。
- UI：Streamlit。
- 主程式：`5_PG_Develop/app.py`。
- Viewer：OpenSeadragon 4.1.0，已 vendored，不使用 CDN。
- 自訂元件：
  - `5_PG_Develop/viewer_component/`
  - `5_PG_Develop/thumbwall_component/`
- 圖像處理、標註、篩選、比較等邏輯已拆成 Python 模組，希望繼續沿用。
- 現有安全模式完全不使用 Custom Component，所以離網可靠，但會失去部分高互動功能。

## 必須保留的功能

1. OpenSeadragon 滾輪縮放。
2. 滑鼠拖曳平移。
3. Shift／滑鼠拖曳框選 ROI，並把座標送回 Python 儲存。
4. 點擊影像取得原始像素座標與像素值。
5. 鍵盤快捷鍵與上一張／下一張導覽。
6. 偵測框、ROI、標籤及 confidence overlay。
7. 可互動縮圖牆、選圖與兩張影像比較標記。
8. 16-bit TIFF 等影像由 Python 解碼、處理及轉換顯示。
9. 完全離網運作，不使用 CDN、遠端字型、線上 API 或執行期套件下載。
10. 數百張影像時仍需維持可接受的啟動與切圖速度。

## 期望消除的故障面

新架構不應再依賴：

- Streamlit Custom Component。
- Streamlit 的 `/component/` URL。
- Streamlit component iframe 與 `componentReady` timeout。
- 瀏覽器透過公司 proxy 存取 localhost 元件資產。
- 外部 CDN 或任何公網資源。

## 請比較的 Tauri 整合方案

請至少比較以下三種方案，並推薦一種：

### 方案 A：只用 Tauri WebView 包住目前 Streamlit localhost 頁面

- Tauri 啟動 Python/Streamlit sidecar，再讓 WebView 開 `http://127.0.0.1:<port>`。
- 請判斷這是否仍保留 `/component/` iframe、proxy、CSP 與 endpoint injection 的風險。
- 如果只是換殼但沒有移除 Streamlit Custom Component，請明確說明它為何不算根治。

### 方案 B：Tauri 前端直接承載 Viewer，Python 作為 sidecar

- Viewer、縮圖牆與 OpenSeadragon 資產全部打包進 Tauri frontend bundle。
- UI 不透過 Streamlit component iframe。
- 前端與 Python 間可使用 Tauri commands、plugin shell sidecar、stdin/stdout、local IPC，或受控的
  loopback API。
- 請建議最可靠的 IPC 選擇、資料格式、事件契約、程序生命週期及錯誤處理方式。
- 大圖與大量縮圖不要反覆用巨大 base64 JSON 傳輸；請設計檔案、binary、custom protocol 或其他方案。

### 方案 C：Tauri 前端 + Rust 核心，逐步取代 Python

- 請評估是否有必要，以及相對於方案 B 的成本、效益與風險。
- Python 現有 CV 模組若可沿用，優先避免一次全部重寫。

## 特別需要回答的問題

1. Tauri 的 `asset:`／自訂 protocol 是否能讓 HTML、JS、CSS、OpenSeadragon 與圖示完全從 App
   bundle 載入，不經系統 proxy？
2. Windows WebView2 在完全離網環境是否仍需要預先安裝 WebView2 Runtime？應採 Evergreen 還是
   Fixed Version Runtime？安裝包如何處理？
3. Tauri CSP 應如何設定，才能允許本地影像／canvas／worker，同時不使用危險的廣泛放行？
4. 若顯示本機任意路徑影像，應使用 Tauri asset protocol、convertFileSrc、自訂 protocol，還是由
   Python 提供 binary？各自的安全邊界是什麼？
5. Python sidecar 如何打包，使目標機不必另外安裝 Python 或從 PyPI 下載依賴？
6. sidecar port 如何避免衝突？若使用 loopback HTTP，怎樣避免 proxy、未授權本機程序存取及
   固定 port 問題？是否應改用 stdin/stdout 或 named pipe？
7. 如何安全傳送 ROI、點擊座標、viewport state、篩選條件與縮圖選取事件？
8. 如何確保主視窗關閉、崩潰或升級時，Python sidecar 不會殘留？
9. 如何在沒有管理員權限、沒有網路、中文及空格安裝路徑下安裝與執行？
10. 現有 Streamlit UI 應一次遷移，還是先把 viewer／thumbwall 移到 Tauri，再逐步遷移其他控制？

## 希望採用的方向

目前傾向方案 B：

```text
Tauri WebView
├─ bundled HTML/CSS/TypeScript
├─ bundled OpenSeadragon
├─ viewer / ROI / keyboard / thumbwall interactions
└─ Tauri IPC
       ↕
Python sidecar
├─ image decoding and 16-bit handling
├─ detection/annotation/sidecar files
├─ filtering/comparison/export
└─ existing CV processing modules
```

請確認這是否能真正移除 Streamlit `/component/` 的問題。如果仍有 proxy、WebView2、CSP 或企業
端點防護可能介入的地方，請逐項列出，不要宣稱絕對不會發生。

## 請輸出的內容

請提供：

1. 推薦架構與不推薦方案的理由。
2. Tauri、前端與 Python sidecar 的目錄規劃。
3. IPC request/event schema 範例。
4. Python sidecar 啟動、ready、shutdown 與 crash recovery 流程。
5. 圖像與縮圖的高效傳輸方案。
6. CSP、capabilities、filesystem scope 與 sidecar 權限設定建議。
7. Windows 完全離網打包與 WebView2 Runtime 策略。
8. 分階段遷移計畫，包含可回退節點。
9. 自動化測試及企業離網環境驗收矩陣。
10. 需要修改或新增的檔案清單與預估工作量。

## 驗收條件

遷移完成後至少需要證明：

- 拔除網路並設定無效系統 proxy，App 仍能啟動及使用完整 viewer。
- 全程沒有 `/component/` 請求或 Streamlit component iframe。
- 沒有任何外部 HTTP/HTTPS、CDN、字型或 telemetry 請求。
- ROI、點擊像素、縮放、平移、鍵盤及縮圖牆全部可用。
- App 關閉後沒有 Python、WebView 或 localhost listener 殘留。
- 中文／空格路徑、標準使用者權限及乾淨離網 Windows 機器可用。
- 安裝包包含所有必要 runtime，或明確檢查並提示缺少的 WebView2 Runtime。
- 企業 proxy 封鎖 localhost HTTP 時，如果架構不使用 loopback HTTP，完整功能仍正常。

請先做架構審查與風險說明，再提出實作步驟；不要直接假設「Tauri 包裝 Streamlit」就是根治。
