# 架構：React Web 與本機 Python 服務

> 對應 `2_PO_PRD/04_react_web_migration_prd.md`。此文件定義第一個 React migration slice 的公開邊界，不改寫既有影像與標記模組契約。

## 元件

1. `web/` 使用 React、TypeScript 與 Vite。React 管理影像選取、工作列、狀態編輯及 OpenSeadragon viewer；資料與判讀狀態不依賴 Streamlit session state。
2. Python 本機 HTTP service 只綁 loopback，負責影像 bytes 解碼、metadata、像素真值、ROI TIFF crop、DZI／tiles 與既有純邏輯 adapter。API 僅收上傳 bytes 與 opaque image handle，不收可任意讀取的主機路徑。
3. Browser filesystem adapter 使用使用者明確授權的 File System Access directory handle，讀取影像與相鄰 `.cvr.json`，並只寫 sidecar。若宿主不提供公開 picker／filesystem API，React 顯示不支援狀態，不探測 Electron／Tauri 私有 API。
4. Web production build 由 Python service 同源提供。Node／Vite 僅供建置與開發；OpenSeadragon 與其他前端依賴須鎖版並離線打包。

## 影像生命週期

- 資料夾授權後只列舊版支援的影像副檔名，按 `imageset._natural_key` 排序，UI 不自行使用 lexical sort。
- 開啟影像時，瀏覽器傳原始 bytes 給本機 service。service 使用 `imgio.load`、`imgio.to_display_rgb` 建顯示用 PNG，回傳不含路徑的 opaque handle、尺寸、bit depth 與 channels。
- 點擊影像時，React 將 viewport 點轉為原圖座標，呼叫像素 API；service 以 `imgio.value_at` 讀原始 8／16-bit 真值。Hover 顯示值遵循既有 8-bit 顯示層語義。
- Sidecar 先用既有 default／合法列舉與形狀驗證；瀏覽器以授權的同目錄 file handle 原子替換 `.cvr.json`。不回寫原始影像 bytes。使用者切圖或改選資料夾時先保存目前影像的 dirty sidecar；寫入失敗就留在目前影像並保留 dirty 狀態，不能以放棄變更提示繞過。
- DZI 達門檻時使用既有 `dzitiles` 產出 tiles，以短效 opaque handle 讀取；暫存資料需有大小與生命週期上限。

## ROI 標註切片

- Shift+`pointerdown` 在 OSD viewer 上攔截平移手勢並顯示 rubber-band；`pointermove` 更新草稿，`pointerup` 將兩角點透過 `viewport.pointFromPixel` 與 `viewportToImageCoordinates` 轉成 source 座標。OSD viewer 使用 Pointer Events，因此 ROI 手勢也以 Pointer Events 處理；`pointercancel` 會清除草稿並恢復平移。
- 先正規化反向拖曳，再將矩形夾入目前影像寬高；寬高不足 3 像素不新增。持久化形狀沿用 `sidecar.add_roi`：`{bbox:[x,y,w,h], label:"", verdict:"unset", comment:""}`。
- React 畫布以 OSD image-space overlay 顯示已載入 ROI；右側清單顯示數量與座標，移除操作標記 sidecar 為 dirty。新／刪 ROI 由既有「保存判讀」一次寫回，不直接寫原圖。
- OSD overlay 更新時只替換 ROI overlay 元素，不清除其他 overlay 類型；卸載影像時移除舊元素。
- 每個 ROI 可經過 session 保護的 `/api/images/{handle}/roi-crop?x=&y=&w=&h=` 匯出。Service 以 `roi.clamp_box` 夾界、以 `roi.crop` 裁原始陣列，再用 `tifffile` 輸出 `<image-stem>_roiN.tif`；TIFF 保留來源的 uint8／uint16 與灰階／RGB 像素值，不改寫原圖，也不接受本機路徑。
- ROI crop 驗收：API 讀回 TIFF 後比對 16-bit dtype、crop shape 與每個像素真值；無 session、零尺寸或完全越界的 ROI 必須拒絕。Chromium 驗 UI 可下載非空 TIFF 並使用影像主幹與 ROI 序號命名。

## Viewer 快捷鍵切片

- Viewer 聚焦時，`ArrowLeft`／`ArrowRight` 切換前後影像；`1`／`2`／`3` 分別設為 `true_defect`／`false_alarm`／`reflection`，`r` 循環 review status，`b` 切換 bookmark。
- 快捷鍵呼叫與面板控制相同的 sidecar 更新路徑；切圖沿用 AC5 自動保存及失敗停留行為。
- 當焦點位於 input、select、textarea、button 或 contenteditable 時，快捷鍵不觸發影像導覽或標記修改，保留原生輸入行為。

## Review Undo 切片

- `verdict`、`review_status`、`bookmarked` 欄位改變且新舊值不同時，將 `{imageName, field, oldValue}` 推入 LIFO stack，最多留 5 筆；Tag、Comment 與 ROI 不入此 stack。
- Viewer 按 `u` 時先定位 stack 尾端影像；若目前不是該圖，沿用 AC5 自動保存後切回。讀取目前 sidecar、只還原該欄位、保存後才移除 stack entry，並顯示「已撤銷」訊息。
- 寫入失敗保留目前欄位與 stack entry，允許重試。stack 空時不改資料並顯示「無可撤銷」。選擇新資料夾清除舊 stack，避免歷程指向另一個資料集。

## Viewer hover HUD 切片

- Viewer 指標移動時，以 OSD viewport 轉換為原圖整數座標 `(x, y)`；座標在原圖範圍內時，從目前顯示 PNG 的 offscreen canvas 讀取 8-bit RGB。這是快速顯示值，不取代點擊 `/pixel` API 取得的原始真值。
- HUD 顯示 `x=`、`y=`、`RGB=(r, g, b)` 與相對於 fit-to-image 的整數縮放百分比。移出有效影像或目前影像沒有可讀取樣本時，不顯示 RGB；指標離開 viewer 時清除舊座標與 RGB；不發送 hover API 請求。
- HUD 固定說明「hover RGB 為顯示值；點擊讀取原始真值」。16-bit 灰階影像也顯示 Python service 已轉成 8-bit RGB 的顯示值；點擊仍回傳原始 uint16 值。

驗收錨點：

- **AC10 hover 座標與 RGB**：在已知 8-bit sample image 中央移動指標，HUD 座標和 RGB 必須符合 source pixel oracle；移動指標後座標更新，點擊同一點仍由原始 pixel API 回傳真值。
- **AC11 zoom 與語義**：初始 fit 顯示 `100%`；放大後百分比上升。HUD 同時明示 hover 是顯示值、點擊取得原始真值。

## Viewer minimap navigator 切片

- 影像開啟時保持 OpenSeadragon navigator 可見，並顯示目前 viewport 範圍。
- 使用者點 navigator 時移動同一影像的主 viewport；不切圖、不改 sidecar 或原始影像。

驗收錨點：

- **AC12 navigator 導覽**：Chromium 確認 navigator 可見；先放大，再點 navigator 的另一區域，點主圖相同 viewport 中心後，來源 pixel 座標／值須改變。
- **AC13 縮放上限**：Chromium 連續按放大直到 HUD 百分比停止上升，再按一次仍維持相同百分比；React toolbar 在每次 `viewport.zoomBy` 後套用 OpenSeadragon viewport constraints，遵守 `maxZoomPixelRatio: 24`。
- **AC14 切圖保留檢視**：切換影像前保存 viewport bounds，新影像載入後以同 bounds 還原；Chromium 驗下一張再上一張後，同一畫面中心讀回相同來源 pixel，HUD zoom 與切換前相差不超過 5%。重新選資料夾仍以 fit-to-image 開始。
- **AC15 ROI TIFF 匯出**：點 ROI 清單的 TIFF 動作後，瀏覽器下載 `<image-stem>_roiN.tif`；API／測試驗 uint16 灰階與 uint8 RGB crop 的 dtype 及像素逐值保留，並拒絕未授權、零尺寸與完全越界請求。

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
- **AC5 導覽自動保存**：變更標記後不按保存而切圖，回到原圖時讀回變更；若 sidecar 寫入失敗，仍停留原圖且變更保留，修復寫入後可再次切圖並讀回。
- **AC6 Viewer 快捷鍵**：Viewer 聚焦時驗前後導覽、三種 verdict、review status 循環與 bookmark 切換；輸入欄位聚焦時按同一組鍵不得改變影像或標記。
- **AC7 Undo 計數**：對 verdict/status/bookmark 做實際變更時 Undo 筆數增加，最多保留最近 5 筆；撤銷後筆數遞減，重複設定相同值不新增 entry。
- **AC8 跨圖 Undo**：在 A 圖修改欄位、切到 B 後按 `u`，跳回 A、只還原最近欄位、保存 sidecar 並顯示「已撤銷」。
- **AC9 多步與空歷程**：跨多張圖連續修改後逐筆撤銷並回復各舊值；撤完再按 `u` 不修改 sidecar，顯示「無可撤銷」。
