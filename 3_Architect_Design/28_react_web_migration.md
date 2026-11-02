# 架構：React Web 與本機 Python 服務

> 對應 `2_PO_PRD/04_react_web_migration_prd.md`。此文件定義第一個 React migration slice 的公開邊界，不改寫既有影像與標記模組契約。

## 元件

1. `web/` 使用 React、TypeScript 與 Vite。React 管理影像選取、工作列、狀態編輯及 OpenSeadragon viewer；資料與判讀狀態不依賴 Streamlit session state。
2. Python 本機 HTTP service 只綁 loopback，負責影像 bytes 解碼、metadata、像素真值、DZI／tiles 與既有純邏輯 adapter。API 僅收上傳 bytes 與 opaque image handle，不收可任意讀取的主機路徑。
3. Browser filesystem adapter 使用使用者明確授權的 File System Access directory handle，讀取影像與相鄰 `.cvr.json`，並只寫 sidecar。若宿主不提供公開 picker／filesystem API，React 顯示不支援狀態，不探測 Electron／Tauri 私有 API。
4. Web production build 由 Python service 同源提供。Node／Vite 僅供建置與開發；OpenSeadragon 與其他前端依賴須鎖版並離線打包。

## 影像生命週期

- 資料夾授權後只列舊版支援的影像副檔名，按 `imageset._natural_key` 排序，UI 不自行使用 lexical sort。
- 開啟影像時，瀏覽器傳原始 bytes 給本機 service。service 使用 `imgio.load`、`imgio.to_display_rgb` 建顯示用 PNG，回傳不含路徑的 opaque handle、尺寸、bit depth 與 channels。
- 點擊影像時，React 將 viewport 點轉為原圖座標，呼叫像素 API；service 以 `imgio.value_at` 讀原始 8／16-bit 真值。Hover 顯示值遵循既有 8-bit 顯示層語義。
- Sidecar 先用既有 default／合法列舉與形狀驗證；瀏覽器以授權的同目錄 file handle 原子替換 `.cvr.json`。不回寫原始影像 bytes。
- DZI 達門檻時使用既有 `dzitiles` 產出 tiles，以短效 opaque handle 讀取；暫存資料需有大小與生命週期上限。

## ROI 標註切片

- Shift+`pointerdown` 在 OSD viewer 上攔截平移手勢並顯示 rubber-band；`pointermove` 更新草稿，`pointerup` 將兩角點透過 `viewport.pointFromPixel` 與 `viewportToImageCoordinates` 轉成 source 座標。OSD viewer 使用 Pointer Events，因此 ROI 手勢也以 Pointer Events 處理；`pointercancel` 會清除草稿並恢復平移。
- 先正規化反向拖曳，再將矩形夾入目前影像寬高；寬高不足 3 像素不新增。持久化形狀沿用 `sidecar.add_roi`：`{bbox:[x,y,w,h], label:"", verdict:"unset", comment:""}`。
- React 畫布以 OSD image-space overlay 顯示已載入 ROI；右側清單顯示數量與座標，移除操作標記 sidecar 為 dirty。新／刪 ROI 由既有「保存判讀」一次寫回，不直接寫原圖。
- OSD overlay 更新時只替換 ROI overlay 元素，不清除其他 overlay 類型；卸載影像時移除舊元素。
- ROI crop 匯出不在此切片；後續需從已授權目錄與原始 dtype 定義 crop file writer 契約。

## 安全與錯誤

- service host 僅接受 loopback；API 驗證 Host 與一次性配對建立的 session。寫入及配對路由必須帶允許的 Origin；同源 GET 可能省略 Origin，但仍必須帶 opaque session header，任何提供但不允許的 Origin 都拒絕。
- 每次上傳限制 byte size、允許的副檔名及解碼尺寸；錯誤回傳有限錯誤碼，不回傳本機完整路徑、stack trace 或上傳內容。
- folder handle 僅在前端授權範圍使用。URL、檔名和 sidecar 目標都以該 handle 的相對子項解析，不接受 `..` 或任意磁碟路徑。
- 服務重啟後恢復已保存的 sidecar；影像 decode cache 與 DZI 暫存可重建，不能作為判讀資料唯一保存位置。

## 驗證契約

PM 驗收必須覆蓋健康檢查、未授權來源拒絕、支援／不支援格式、自然排序、8／16-bit metadata 與 pixel oracle、 sidecar round-trip、原圖 SHA-256 不變、服務 restart 後 readback，以及 Chromium 真實資料夾授權與 viewer zoom/pan。GUI 需實際截圖／檢視；DOM 存在不能取代畫面驗證。

首個垂直流程的瀏覽器錨點：

- **AC1 自然排序**：資料夾列舉順序刻意先回傳 `frame_10` 再回傳 `frame_2`，畫面仍須先列 `frame_2`。
- **AC2 viewport 與像素真值**：8-bit RGB 與 16-bit TIFF 初始點擊都符合來源影像 pixel oracle；縮放後平移，再點同一畫面座標，回傳的來源影像座標必須改變且仍在界內。
- **AC3 原圖唯讀與保存**：原圖 file handle 不提供 writable，E2E 只記錄 `.cvr.json` 寫入；切圖及頁面重新載入後都讀回保存值。
- **AC4 ROI sidecar**：Shift+drag 正規化並夾界後新增 `{bbox,label,verdict,comment}`；向量框與清單同步顯示；保存／重新載入讀回相同 bbox，移除後再保存則不再出現。
