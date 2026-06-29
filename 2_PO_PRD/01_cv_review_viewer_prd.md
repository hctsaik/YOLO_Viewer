# PRD:CV Review Workbench(v1)

> `/po` 階段產物(草案,待人審)。決定「做什麼 / 為什麼 / 什麼順序」,不做技術設計。
> 對應 `1_user_needs/01_cv_review_viewer.md`。

## 1. 目標與成功指標 (Goals & Success Metrics)
把大量影像快速轉成「可判斷、可追蹤、可回訓的工程證據」,讓工程師不必在多個工具間切換。
- **找得快**:開資料夾 → 3 秒內看到縮圖牆;可鍵盤上一/下一/跳號;自動回到上次位置;顯示 `N / M`。
- **看得準**:滾輪定點縮放;游標處即時顯示 `(x,y)` 與 RGB/Gray 值;支援 8/16-bit、TIFF、大圖。
- **記得住**:每張圖的 Bookmark/Tag/Verdict/Comment/ROI 都不破壞原圖、可搜尋、可匯出。
- **可回流**:能匯出「模型結果 + 人工判定」的案例清單(CSV/JSON)。

## 2. 範圍 (MoSCoW)
**Must(v1 MVP,= User 文件第 6 節 8 項)**
- 資料夾瀏覽 + 縮圖牆;順暢 Zoom/Pan/MiniMap/Pixel 值;Bookmark/Tag/Comment/Status;
  ROI 框選 + Crop 匯出;前後影像比較 + Blink;YOLO bbox/conf overlay;快捷鍵;匯出 CSV+JSON。

**Should(v1 若有餘力)**
- 依多條件排序(time/conf/class/reviewed/tagged);簡單 Review Queue;confidence threshold slider。

**Could(Phase 2,先不做)**
- Frame Difference 進階、DINO/SAM overlay、相似圖搜尋、embedding cluster、多模型四格比較、
  自動 Missed-Detection Queue、FiftyOne/LabelMe/COCO 匯入匯出、Case Package(folder/HTML/PDF)。

**Won't(v1 明確不做)**
- 完整 Labeling 平台、多人協作/帳號權限、雲端。

## 3. 模組分解 (Module Breakdown) — feature→module 收斂
> Tier A=純邏輯(無 I/O/GUI,測試不省、設計可極簡);Tier B=有 I/O/GUI(完整五層 + 真實 E2E)。
> 每個 module 都通過拆解三問(內聚一句話講完 / 契約耦合少且不成環 / 可獨立驗收)。

### M1 — 瀏覽 + 專業放大(最痛點)  appetite:≤4 模組
| module | Tier | 一句話職責 | 相依 |
|--------|------|-----------|------|
| `imageio`  | B | 把 8/16-bit、TIFF、大圖讀成「可顯示 RGB 陣列 + 原始 pixel 取值能力 + 尺寸/位元深」 | — |
| `imageset` | B | 把一個資料夾變成「可排序(time/name)、可定位、記得進度 N/M、記得上次位置」的影像清單 | — |
| `viewport` | A | 所有縮放/平移/以游標為中心的座標換算、image↔canvas、pixel 取值座標、minimap 視窗矩形(純幾何) | — |
| `app`(增量) | B | Streamlit:縮圖牆 + 主畫布(zoom/pan/minimap/pixel)+ 上一/下一/跳號 + 快捷鍵 + 記住位置 | 上列全部 |

### M2 — 標記與追蹤  appetite:≤3 模組(+app 增量)
| module | Tier | 一句話職責 | 相依 |
|--------|------|-----------|------|
| `sidecar` | B | 每張圖的 sidecar JSON 讀寫(status/tags/verdict/comment/rois),**不改原圖** | — |
| `roi`     | A | ROI 框幾何、一圖多 ROI、crop 計算、ROI↔影像座標(純邏輯) | — |
| `tagging` | A | 三層標記模型(Bookmark/Verdict/Action)+ 內建標籤清單 + 篩選/搜尋 predicate | — |
| `app`(增量) | B | 標記面板(Bookmark/Tag/Comment/Status)、ROI 框選 + Crop 匯出、可搜尋 | M1 + 上列 |

### M3 — 模型疊圖 + 前後比較 + 排序 + 匯出  appetite:≤4 模組(+app;進行時可再拆 M3a/M3b)
| module | Tier | 一句話職責 | 相依 |
|--------|------|-----------|------|
| `yolo`        | B | 載入每張圖的 YOLO 偵測結果(JSON,容錯) | — |
| `overlay`     | A | 在影像上畫 bbox/class/conf,可依 confidence threshold / class 篩選(純邏輯) | yolo(資料) |
| `framecompare`| A | 前後兩張圖:side-by-side / overlay / blink / swipe / difference(純計算) | — |
| `filtersort`  | A | 智慧排序(time/conf/class/reviewed/tagged)+ Review Queue 規則(純邏輯) | tagging/yolo(資料) |
| `casepkg`     | B | 把選定案例匯出 CSV + JSON case list(含模型結果 + 人工判定) | sidecar/yolo |
| `app`(增量)   | B | overlay 控制、前後比較模式、排序/Queue、匯出 UI | 全部 |

## 4. 使用者驗收 (User-facing Acceptance,銜接 User 文件)
- 指向一個含影像的資料夾 → 看到縮圖牆 + 主畫布,底部 filmstrip 可上一/下一(鍵盤可操作)。
- 主畫布滾輪縮放、平移;游標處顯示座標與 RGB/Gray;minimap 顯示目前視窗。
- 對一張圖加 Bookmark/Tag/Verdict/Comment、框一個 ROI 存 crop → 重開工具後資料還在、可搜尋。
- 載入 YOLO 結果 → 可開關 bbox/conf;前後兩張可 blink/side-by-side/difference。
- 匯出 → 得到含「影像、判定、標籤、(若有)模型結果」的 CSV + JSON。

## 5. 給架構師的開放問題 (Open Questions for Architect) — **需技術判斷,影響契約**
1. **大圖 / 互動縮放可行性(最大風險)**:3000×3000、16-bit、TIFF 在 Streamlit 要順暢 zoom/pan,
   `st.image` 會整張送且 downscale。可行路線(tiling / image pyramid / 自訂前端元件 / canvas)請架構師
   評估,並界定 M1 `viewport`/`app` 對「以游標為中心縮放」這條 AC 的可達成程度。
2. **游標座標 / pixel 值即時顯示 + 滾輪 + 鍵盤**:Streamlit 原生事件有限。決定 MVP 用自訂元件
   (如 image-coordinates / drawable-canvas)還是可接受折衷(slider 縮放 + 點擊取座標 + 按鈕導覽),
   並標明對上述 AC 的影響(這會回頭調整本 PRD 的措辭)。
3. **16-bit 顯示映射**:window/level vs 自動 normalize,MVP 預設哪個。
4. **sidecar 放置**:與原圖同目錄 `<name>.json` vs 集中索引檔;多 ROI 結構與座標系。
5. **YOLO 結果格式 / 座標系**:per-image JSON?COCO?xyxy 還是正規化 xywhn?

## 6. Appetite 與停止準則
- 一次只放行一個里程碑;每個里程碑 ≤ 上表模組數,達上限即停輪,溢出進「候選」。
- **豁免**:修「不可用 / false-green」可不受 appetite 限制修到真能用;只有「新增能力」受限。
- 若開放問題 1/2 評估後發現 Streamlit 無法達成核心互動 → 退回本 PRD 取捨(降級 AC 或換呈現策略)。
