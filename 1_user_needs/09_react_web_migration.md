# React Web 遷移需求

## 背景

使用者決定停止支援 Streamlit，將既有 Streamlit App 改寫為 React Web，並由本機原生服務提供檔案與模型能力。CV Review Workbench 的人工判讀、影像檢視與 sidecar 資料必須延續既有契約。

## 需求

1. React Web 是受支援的使用介面；一般啟動流程不啟動 Streamlit。
2. Python 保留影像解碼、像素取值、DZI、YOLO 結果解析及既有純邏輯模組；React 呼叫本機 HTTP 契約，不直接依賴 Streamlit session state。
3. 保留現有 UI 使用者可見功能，逐項映射到 React 驗收案例；功能未移植前不得宣稱完整遷移。
4. 影像原檔不可被覆寫。標記、ROI、狀態與判讀沿用 `.cvr.json` sidecar 格式。
5. 本機離線執行為基準。前端資產 vendored 並由本機服務提供；不使用 CDN。
6. 本機檔案存取必須由使用者明確授權；不得接受任意網頁提供的路徑或依賴 NativeApp 私有 import。
7. 先驗 React 瀏覽器中的一張影像完整流程，再擴充比較、疊圖、排序、工具箱及桌面接入。

## 首個垂直流程

使用者授權影像資料夾、以自然排序瀏覽影像、開啟影像並縮放／平移、檢視影像尺寸與位元深度、修改標記及保存 sidecar；重新開啟資料夾後讀回標記，且原始影像位元組不變。

## 完成判準

既有使用者功能全部有 React 驗收對照，單張影像流程通過 Python API、React UI、真實瀏覽器與重開讀回驗證。NativeApp 發布、ARM64 Python／模型相容性另需在實際宿主驗證，不能以 mock host 取代。
