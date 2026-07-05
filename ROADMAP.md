# ROADMAP(由 PO 維護)— CV Review Workbench

> 狀態圖例:⬜ 待設計 · 📝 設計中 · 🧪 驗收定義中 · 🔨 開發中 · ✅ 完成
> 提醒:狀態是人的判斷,不可由「檔案存在」自動標 ✅。模組表/測試數請定期用
> `python verify/unet_status.py` 核對是否漂移。

## 里程碑
- **M1a — Viewer 元件核心**:✅ 完成
  (`viewer_component`:OpenSeadragon 宣告式元件,滾輪縮放/平移/hover 座標/點擊取值/Shift+拖 ROI;
   spike + app 整合,playwright 真實瀏覽器驗收通過)
- **M1b — 影像管線 + 串接**:✅ 完成
  (imgio/imageset/viewport 全綠 + `app.py` 串接:縮圖牆 + 嵌入 viewer + 上一/下一/跳號 + 記住位置;app 可跑、冒煙通過)
- **M2 — 標記與追蹤**:✅ 完成
  (sidecar/roi/tagging 全綠 + 已接進 app:Bookmark/Tag/Verdict/Comment/Status + Shift 拖框 ROI + 篩選搜尋;
   收尾已補:ROI crop 一鍵下載、進階搜尋(Comment 文字 + 標籤 any/all + 偵測類別篩選))
- **M3 — 模型疊圖 + 前後比較 + 排序 + 匯出**:✅ 完成(本輪一次做完)
  (yolo / overlay / framecompare / filtersort / casepkg 五模組單元全綠 + 已接進 app:模型疊框(class 顏色/conf 門檻/類別)、
   前後比較(並排/差異/混合/擦除/閃爍)、智慧排序 + Review Queue、Case Package CSV+JSON 匯出;
   playwright 真實 E2E 通過、截圖確認疊框可見)
  **appetite(本輪)= 全 5 模組 + app 整合 + M2 收尾**(User 指示「一口氣做完全部」,PO 覆寫 PRD 原 ≤4 限制)。
- **M4 — 智慧分析(Phase 2 第一刀)**:✅ 完成(本輪一次做完)
  (framediff / missedq / simhash 三 Tier A 純邏輯模組單元全綠 + 已接進 app:前後比較加「變化偵測」模式(變化率/變化區紅框)、
   Missed-Detection Queue(漏檢/誤報/低信心/未審有框 + 理由 + 可跳轉)、找相似圖(感知雜湊 Hamming);
   playwright E2E 通過、截圖確認 Queue 顯示「2 張需再看」且縮圖 ✓ 恢復語義)
  含一個反向閘門(simhash find_similar 漏 hash_size,PG 攔下)+ 一個 bugfix(sidecar verdict 預設 ""→"unset" 對齊 tagging)。
  **appetite(本輪)= 3 模組 + app 整合**。從 Phase 2 池挑相依輕/高綜效者;刻意緩做重 ML 與 viewer 架構項。
- **M5 — 互通 + 進階表示**:✅ 完成(本輪一次做完)
  (cocoio / htmlreport / embcluster / dzitiles 四模組單元全綠 + 已接進 app:匯出加 COCO/LabelMe + HTML 報告、
   embcluster 聚類/相似面板、**大圖 DZI 瓦片模式**(OSD 自訂 tile source 分層渲染 + write_dzi 落磁碟);
   viewer 元件重構成 buildViewer 支援瓦片(向後相容,官方 E2E 仍綠);截圖實證 DZI 第二 viewer 渲染 37 片金字塔)
  含一個反向閘門(dzitiles 自相矛盾 meta-test,PG 攔下)+ 整合修一個 NameError(app 漏 import json)。
  **appetite = 4 模組 + 整合**。涵蓋 Phase 2 的 COCO/LabelMe 互通、HTML Case Package、embedding cluster、大圖 DZI tiles。
- **M6 — viewer/縮圖 UX 回饋輪**:✅ 完成(本輪一次做完)
  (User 實跑後 7 點 UX 回饋:主 viewer〔1.點圖不觸發原生選圖 2.最大放大上限 maxZoomPixelRatio=24 3.hover 即時 x,y+RGB
   〔client offscreen-canvas 零 round-trip、顯示 8-bit;16-bit 真值仍靠點擊伺服器查〕 4.多列 HUD=檔名+序號·尺寸·位元深·通道·zoom%·游標下框 class·conf〕;
   縮圖牆〔5.整張縮圖可點→載入主 viewer(新 thumbwall 宣告式元件取代看不懂的索引鈕「N」) 6.縮圖疊 YOLO 框〕;頂部〔7.YOLO 框總開關同管縮圖+主圖〕。
   機器判綠:viewer_ux E2E **13 passed/1 skipped**(AC6 瓦片誠實 skip)+ app E2E 回歸綠 + 811 單元仍綠;截圖實證縮圖疊框、hover RGB=(15,18,28)、放大封頂 4279%。
   含 2 個反向閘門〔pg→pm:AC10 dispatch 座標 bug、AC16 hydration timing,orchestrator 親驗皆測試 bug、PG 拒改實作〕+ helper 收緊排除 main_frame + app 還原延遲載入 + conftest 殺子程序防 orphan。)
- **Phase 2(剩餘候選,未排程,誠實標註重依賴)**:
  - **DINO/SAM live 推論 + overlay**:需 `transformers` + 數 GB 權重下載 → 不在單終端機原型內跑;`embcluster` 已備好
    消費「外部預算好的 embedding 向量」的純邏輯底座(離線算 embedding、線上分群/搜尋)。
  - **PDF 報告**:需 reportlab/weasyprint(本機未裝)→ htmlreport 先出 HTML(瀏覽器可印 PDF);PDF 列候選。
  - 多模型版本比較、FiftyOne 整合、相似圖 embedding 索引建置。

## 模組進度
> 由 `python verify/unet_status.py` 核對:已建模組單元測試共 **915 passed**(2026-07-04,含新增 imgadjust 28;
> 本表 M1-M5 各模組測試數為當初落地時的計數,之後新增模組〔labelloc/modeldiff/pairset/imgadjust 等〕
> 見下方對應決策日誌,尚未逐一補回本表列——已知漂移,非本輪範圍)。
> M1-M2:viewport59/imgio39/imageset37/roi103/tagging41/sidecar40;M3:yolo40/overlay43/framecompare39/filtersort31/casepkg35;
> M4:framediff48/missedq34/simhash36;M5:cocoio50/htmlreport47/embcluster40/dzitiles50(含 1 e2e)。
| Module | Tier | 狀態 | 設計 | 驗收 | 實作 | 相依 | 里程碑 | 備註 |
|--------|------|------|------|------|------|------|--------|------|
| viewport    | A | ✅ | ✅ | ✅ | ✅ | — | M1b | 縮放/座標/裁切/minimap 純幾何(59 測試) |
| imgio       | B | ✅ | ✅ | ✅ | ✅ | — | M1b | 8/16-bit/TIFF→顯示RGB+真值+thumbnail+dataURL(39) |
| imageset    | B | ✅ | ✅ | ✅ | ✅ | — | M1b | 資料夾→清單/自然排序/進度/Position 記憶(37) |
| viewer_component | B | ✅ | 設計於 2_PO_PRD/03 | e2e | ✅ | imgio | M1a | OSD 宣告式元件(無 build):滾輪/平移/hover/點擊/Shift拖ROI;spike+playwright 驗 |
| sidecar     | B | ✅ | ✅ | ✅ | ✅ | — | M2 | sidecar JSON 讀寫(原子寫、不改原圖,40) |
| roi         | A | ✅ | ✅ | ✅ | ✅ | — | M2 | ROI 幾何 + crop(103) |
| tagging     | A | ✅ | ✅ | ✅ | ✅ | — | M2 | 三層標記 + 內建標籤 + 篩選 predicate(41) |
| app         | B | ✅ | — | e2e | ✅ | 上列全部 | M1→M3 | Streamlit UI 串接 M1+M2+M3;playwright E2E(載入/1-8/viewer/下一張)通過 + 截圖驗疊框 |
| yolo        | B | ✅ | ✅ | ✅ | ✅ | — | M3 | 載入 YOLO 結果(容錯,多 schema/座標系)→ 標準 Detection(40) |
| overlay     | A | ✅ | ✅ | ✅ | ✅ | Detection 形狀 | M3 | 畫 bbox/class/conf + threshold/class 篩選(numpy,不 import yolo,43) |
| framecompare| A | ✅ | ✅ | ✅ | ✅ | — | M3 | side-by-side/difference/blend/swipe/blink(純 numpy,39) |
| filtersort  | A | ✅ | ✅ | ✅ | ✅ | (tagging 語義) | M3 | 智慧排序 6 鍵 + Review Queue(吃 dict,不 import,31) |
| casepkg     | B | ✅ | ✅ | ✅ | ✅ | Detection 形狀 | M3 | case package CSV+JSON(吃 dict,tmp_path 真實寫讀驗,35) |
| framediff   | A | ✅ | ✅ | ✅ | ✅ | — | M4 | 進階幀差:4-連通變化區框 + 變化率 + BT.601 灰階高亮(48) |
| missedq     | A | ✅ | ✅ | ✅ | ✅ | (tagging 語義) | M4 | Missed-Detection Queue:漏檢/誤報/低信心/未審 + 理由 + priority(34) |
| simhash     | A | ✅ | ✅ | ✅ | ✅ | — | M4 | 相似圖:a/d-hash + Hamming + find_similar(numpy+PIL,36) |
| cocoio      | B | ✅ | ✅ | ✅ | ✅ | Detection 形狀 | M5 | COCO + LabelMe 雙向匯入匯出(round-trip,tmp_path 真實寫讀,50) |
| htmlreport  | B | ✅ | ✅ | ✅ | ✅ | Detection/sidecar 形狀 | M5 | 自含 HTML Case Package 報告(html.escape 防破版,47) |
| embcluster  | A | ✅ | ✅ | ✅ | ✅ | — | M5 | 餘弦相似 + 確定性 k-means(吃預算好向量;app 用 8×8 特徵示範,40) |
| dzitiles    | B | ✅ | ✅ | ✅ | ✅ | — | M5 | DZI 金字塔瓦片 + OSD 自訂 tile source 接線 + write_dzi(50,含 1 e2e) |
| imgadjust   | A | ✅ | ✅ | ✅ | ✅ | — | 2026-07-04(🧰CV工具箱) | 顯示層調整:亮度/對比/gamma/直方圖均衡化/反色/拉伸/二值化/Canny(純 numpy+條件式 cv2,28) |

> **M3 共用契約(PO 釘死,所有 module 依「資料形狀」而非互相 import,故全程可平行)**:
> `Detection = {"bbox":[x,y,w,h](絕對像素,左上原點), "cls":str, "conf":float(0~1)}`。
> yolo 是唯一「產生」此形狀者(load JSON→list[Detection],容錯);overlay/filtersort/casepkg 是「消費」者,
> 測試一律用 dict 模擬,**不得 import yolo/sidecar/tagging 的實作**(解耦、可獨立驗收)。

## 技術假設
Python + pytest + Streamlit。Streamlit 進入點 `5_PG_Develop/app.py`。閘門 `python verify/gate.py <module>`。

## 待架構師先回的高風險開放問題(見 2_PO_PRD/01)
1. 大圖 / 16-bit / TIFF 在 Streamlit 的順暢 zoom/pan 可行性(最大風險,可能改 viewport/app 契約)。
2. 游標座標 / pixel 值 / 滾輪 / 鍵盤:用自訂元件還是折衷;影響「以游標為中心縮放」AC。

## 決策日誌(append-only)
> 每次反向閘門退回、模組增刪、需求被砍,追加一行:日期 / 從哪層退到哪層(或 決策) / 一句為什麼。
- 2026-06-21 (init) 建立 U-Net v2.1 框架(含機器強制閘門)。
- 2026-06-21 (po) 把 User MVP 8 項收斂成 12 模組、分 M1/M2/M3 三個有界回合;Phase 2 全列為候選。
- 2026-06-21 (po) 標記兩個高風險開放問題給 architect 先評(Streamlit 大圖互動縮放 / 事件支援),
  其結論可能回頭降級 M1 的縮放 AC。
- 2026-06-21 (architect→po 反向閘門) spike 實測:st.image 整張 3000² = 952ms/8.8MB 不可用;
  「伺服器端只切可視區+降採樣」= 68ms/629KB。建議方案 A;但需 PO 裁決滾輪縮放是否必須。見 3_Architect_Design/00。
- 2026-06-22 (po 裁決) 滾輪縮放定為 Must → 不採方案 A,改 client-side 元件。見 2_PO_PRD/02。
- 2026-06-22 (勘查 nativeApp) 載體 = Electron→React portal→iframe Streamlit + FastAPI engine + postMessage 協議;
  renderer 沙盒不能直接讀檔,大圖靠 engine HTTP 供應。
- 2026-06-22 (po 定案) 先做獨立 Streamlit 原型;viewer = OpenSeadragon 經「宣告式元件(declare_component+static index.html,無 React build)」;
  關鍵更正:components.v1.html 單向、無法回傳值。見 2_PO_PRD/03。下一步:先做生死點 spike。
- 2026-06-22 (spike PASS,playwright 實測) `spike/viewer_spike.py` + `spike/osd_component/`:獨立 Streamlit 裡
  OpenSeadragon 滾輪縮放成立(zoom 1.17×、client-side 不 rerun),點擊影像座標 (600,450)+zoom 經 setComponentValue
  回到 Python。→ **viewer 架構端到端驗證通過,M1a 解除封鎖、可放行設計。**
- 2026-06-22 (build) 用 workflow 走完 6 個純邏輯模組(viewport/imgio/imageset/roi/tagging/sidecar)的
  設計→驗收測試→實作,**319 單元測試全綠**;imageio 改名 imgio(避免遮蔽 PyPI 套件)。
- 2026-06-22 (integrate) 手做 viewer_component(OSD 宣告式元件)+ `app.py` 串接 M1+M2;
  playwright 冒煙:app 載入、1/8、viewer canvas、下一張→2/8 通過。**M1 完成、M2 核心完成、可實跑。**
- 2026-06-22 (待辦) M3(yolo/overlay/framecompare/filtersort/casepkg)尚未開發;app 的 ROI crop 存檔、
  進階搜尋 UI、大圖 tiles(目前送全解析度 data URL,大圖需改 DZI tiles)待補。
- 2026-06-22 (po appetite 覆寫) User 指示「所有功能一口氣用 U-Net 做完、不再逐項確認」→ 本輪 appetite
  覆寫為「全 5 個 M3 模組 + app 整合 + M2 收尾(ROI crop 存檔、進階搜尋)」。大圖 DZI tiles 仍列候選(Phase 2)。
- 2026-06-22 (po 釘契約) 釘死跨模組共用 `Detection={"bbox":[x,y,w,h]絕對像素,"cls":str,"conf":float}`;
  M3 消費端(overlay/filtersort/casepkg)只依此資料形狀、不 import 上游實作 → 5 模組設計/驗收/實作全程可平行。
- 2026-06-22 (po 啟動 M3 build) 切 architect→pm→pg 三階段、同階段平行、階段間以 .unet/role 切換 + gate snapshot 把關。
- 2026-06-22 (architect 5 設計) yolo/overlay/framecompare/filtersort/casepkg 設計完成,AC 全釘死數值(yolo35/overlay36/
  framecompare27/filtersort26/casepkg30);人審修 filtersort AC18 一處錯值(c/b 順序,應 conf 降序 b<c)。
- 2026-06-22 (pm 5 驗收) 188 條測試,每模組含 ≥1 metamorphic/property 推導測試;casepkg 自驗 ASCII 逗號 codepoint。
- 2026-06-22 (pg 5 實作) gate.py 各自客觀 GREEN;orchestrator 親自重跑 5 gate 複驗(40+43+39+31+35),契約未竄改;
  unet_status:15 模組三層對齊、508 收集無漂移。**無反向閘門觸發**。
- 2026-06-22 (integrate) app.py 接入 M3:模型疊框(overlay.draw 燒 class 顏色、conf 門檻/類別)、前後比較(framecompare
  五模式)、智慧排序+Review Queue(filtersort)、Case Package 匯出(casepkg);M2 收尾 ROI crop 下載 + 進階搜尋。
  真實資料管線冒煙 + playwright E2E 通過,截圖確認三框(綠 scratch/藍 dent/紅 edge)正確疊出。**M2、M3 完成。**
- 2026-06-22 (備註) sample_images 內附 2 份示範偵測 JSON(lot42_frame_000/001)供 overlay 開箱即見;大圖 DZI tiles 仍 Phase 2 候選。
- 2026-06-23 (po 啟動 M4) User 指示「再一輪」→ PO 從 Phase 2 池挑 framediff/missedq/simhash(均 Tier A 純邏輯、相依輕、
  與現有 yolo/overlay/framecompare/tagging 高綜效、可全程平行)。appetite=3 模組 + app 整合。
  **緩做**:DINO/SAM/embedding(重 ML 依賴、安裝風險)、大圖 DZI tiles(動 viewer 架構,值得獨立一輪)——理由=fixed-appetite 控風險。
- 2026-06-23 (po 解耦原則) 三模組吃 dict/array、彼此不互 import;framediff 可選複用已建的 framecompare、missedq 自帶
  reviewed 等價邏輯不 import tagging(沿用 M3 解耦慣例)→ 設計/驗收/實作全程平行。
- 2026-06-23 (/pg →(設計矛盾)→ /architect 反向閘門) simhash PG 停手回報、未動契約:`find_similar` 簽名漏 `hash_size`
  參數(內部固定 hash_size=8)但 AC18/22/23 餵 2×2 圖、期望值按 hash_size=2 手算 → 上採樣後 hamming 不符;且 AC10 餵
  (1,9) 配 hash_size=8 違反設計「餵目標尺寸陣列」前提(dhash 目標 (8,9))。orchestrator 核驗屬實 → architect 修設計
  (find_similar 加 hash_size 參數、AC10 改餵 (8,9) 期望 0x5555555555555555、AC18-23 傳 hash_size=2),PM 同步改測試。
  **價值印證:PG 拒絕為過綠改契約,真實設計 bug 被閘門攔下而非鎖成 false-green。**
- 2026-06-23 (/pg 整合 →(發現 sidecar/tagging 預設值不一致)→ /po 裁決 → 修 sidecar) M4 整合時發現:`sidecar.default()`
  image-level `verdict=""`,但 tagging/filtersort/missedq 的「未審」哨兵是 `"unset"`(VERDICTS[0]),致全新 sidecar 被
  誤判已審(縮圖 ✓ 恆亮、missedq 不標未審)。PO 裁決:image-level verdict 預設對齊 `"unset"`(同 tagging 哨兵 + sidecar
  自己的 ROI-level 預設;casepkg 早 workaround 成 unset)→ architect/pm/pg 同步修 sidecar(AC2/test/default())。bugfix,
  appetite 豁免。修後 ✓ 標記恢復語義、missedq 對「有框未審」正確標記。
- 2026-06-23 (integrate M4) app.py 接入:前後比較加「變化偵測」模式(framediff.highlight + 變化率/變化區)、
  Missed-Detection Queue 全寬面板(missedq,可點名跳轉)、找相似圖 expander(simhash.find_similar)。真實資料管線冒煙 +
  playwright E2E 通過,截圖確認 Queue 顯示「2 張需再看一眼」、縮圖 ✓ 恢復語義、疊框正確。**M4 完成、625 單元全綠。**
- 2026-06-23 (po 啟動 M5) User 指示「全部做完」→ PO 從 Phase 2 池挑 cocoio/htmlreport/embcluster/dzitiles(均可在
  單終端機負責任交付)。**範圍裁決**:DINO/SAM live 推論(transformers 缺 + GB 權重)與 PDF 庫(reportlab 缺)依方法論
  「原型不塞重依賴」原則排除;改交付 embcluster(吃外部 embedding 的純邏輯底座)+ htmlreport(HTML,瀏覽器可印 PDF)。
  探測:torch✓ transformers✗ reportlab✗ sklearn✓ cv2✓(embcluster 仍走純 numpy 確定性實作以利釘死 AC,不依賴 sklearn 隨機性)。
- 2026-06-23 (po 釘契約) cocoio 用 COCO 原生 xywh(與我們 Detection bbox 同序)、cls↔category_id 映射釘死;dzitiles 依 Deep Zoom
  規格(level=ceil(log2(maxWH))+1、tile_size 預設 254 overlap 1);embcluster k-means 用確定性初始(前 k 點)+ 固定迭代;
  四模組吃 dict/array、彼此不互 import → 全程平行。
- 2026-06-23 (architect 人審修 bug) 前段人審逐輪手算 k-means,抓到 embcluster ITEMS_2 夾具排序錯(前兩項同群,致 AC20 iters=0
  期望值與演算法不符)→ 改前兩項為分離種子 a/c,使初始中心=真群心、1 輪收斂,AC15/20/28 一致。dzitiles DZI 數學逐項驗算無誤。
- 2026-06-23 (/pg →(測試自相矛盾)→ /pm 反向閘門) dzitiles PG 停手:PM 自寫的反作弊 meta-test 掃自身原始碼禁
  `pytest.mark.skip/xfail`,但那些字串就寫在它自己的註解/tuple 裡 → 恆失敗(與實作無關)。49 個實質測試全過。PM 修:用字串
  拼接構造 needle 避免 self-match。**PG 拒改測試、停手交接,自相矛盾的測試被攔下而非被硬改。**
- 2026-06-23 (pg 誠實回報) htmlreport 設計 §3.4 片段 `f"{x:.3f}"` 與 AC29 期望 0.8765→"0.877" 互斥(IEEE754 給 "0.876")。
  PG 未改測試/設計、未硬編碼,改用 `Decimal(str(x))` round-half-up 滿足全部釘死 AC(對其它值與 .3f 一致)→ 綠。設計片段待修為 round-half-up 描述。
- 2026-06-23 (integrate M5) app.py 接入:匯出加 COCO/LabelMe(cocoio)+ HTML 報告(htmlreport)+ COCO/LabelMe 匯入回填;
  embcluster 聚類/相似面板(8×8 灰階特徵當 placeholder 向量,k-means 把 wafer TIF 與 lot42 PNG 乾淨分兩群);
  viewer 元件重構成 buildViewer(tileSources) 支援 DZI 瓦片 + 大圖瓦片模式(osd_viewer tiles=…)+ write_dzi 落磁碟。
  整合冒煙抓到並修一個 NameError(app.py 漏 `import json`)。官方 E2E 仍綠;截圖實證 DZI 第二 viewer 用自訂 tile source
  渲染 1200×900→12 層 37 片金字塔。**M5 完成、811 單元全綠、18 模組三層對齊。大圖 DZI tiles(最大技術風險)落地。**
- 2026-06-23 (里程碑) M1–M5 全數完成;Phase 2 剩餘僅「重依賴」項(DINO/SAM live 推論、PDF 庫、FiftyOne)——
  依方法論「單終端機原型不塞重依賴」刻意留外部,embcluster/htmlreport 已備好消費端與 HTML(可印 PDF)出口。
- 2026-06-23 (po 啟動 M6 — viewer/縮圖 UX 回饋輪) User 實跑 app 後提 UX 回饋,逐輪釐清(2× AskUserQuestion + 截圖)鎖定 7 點:
  主 viewer〔1.點圖不觸發原生選圖/拖曳 2.最大放大上限 3.hover 即時 x,y+RGB(client 端 offscreen canvas 取樣、零 round-trip、
  顯示 8-bit 值;16-bit/灰階「真值」仍靠點擊走伺服器 imgio.value_at) 4.HUD 推薦組合=檔名+序號 / 尺寸·位元深·通道 / zoom% /
  hover(x,y)+RGB / 游標下偵測框 class·conf〕;縮圖牆〔5.整張縮圖可點→載進主 viewer(現況:只有索引鈕「N」可導覽、縮圖圖片不可點,
  且「N」對 User 無意義) 6.縮圖畫 YOLO 框〕;頂部〔7.YOLO 框總開關(管縮圖+主圖),由 sidebar 提到最上面〕。
  Tier B GUI,done=既有 app E2E 仍綠 AND 新 viewer_ux E2E 綠 + 截圖實證(沿 viewer/app「手做+playwright」防 false-green 慣例);
  index.html/app.py 無 Python 單元 gate,以真實 playwright E2E 為機器判綠。階段角色閘門:architect→pm→pg 以 .unet/role 切換把關。
- 2026-06-23 (architect 19_viewer_ux) 18 條 AC,每條標 [E2E可斷言]/[截圖實證];誠實標 hover=8-bit 顯示值 vs 點擊=真值界線、瓦片模式 hover 降級不取 RGB;新增 thumbwall 宣告式元件(零第三方依賴,取代被否決的索引鈕)。orchestrator 親自核設計通過。
- 2026-06-23 (pm test_viewer_ux_e2e) 14 條 @e2e,只落 [E2E可斷言]+視覺項代理;AC6 瓦片誠實 skip(環境難穩定構造)、純截圖 AC3/5/14 不假裝斷言。
- 2026-06-23 (pg 實作) 5 處變更(viewer.py 新 meta/dets/max_zoom;index.html 暴露 window.viewer+maxZoomPixelRatio+禁原生選圖+offscreen-canvas 零 round-trip hover RGB+多列 HUD;app.py 控制上移/縮圖疊框/thumbwall 串接;新 thumbwall 元件)。orchestrator 親跑 E2E:11 passed/2 failed/1 skipped。
- 2026-06-23 (/pg →(2 個測試 bug)→ /pm 反向閘門) PG 停手回報、未動實作:① AC10 `test_hover_inside_known_box` 把「canvas 頁面座標原點」加到「frame 局部像素」再 dispatch,viewer 在中欄時游標落框外(orchestrator 親驗:HUD 顯示 (x=1642,y=1712) 但圖僅 1200×900,且 HUD meta 列全對=反證實作正確);② AC16 `test_top_controls_exist` 在 hydration 前就數 checkbox(AC15/AC17/AC18 已證該 checkbox 存在可用=反證實作正確)。**PG 拒絕為過綠改實作=閘門正常運作**;orchestrator 裁決屬測試 bug→退 PM 修。另:`_find_thumbwall_frame` helper 過寬(會選到主 frame 外洩的 st.image),PG 為此改了 app(framecompare/simhash 延遲載入)→ 裁決:收緊 helper(排除 main_frame)+ 還原 app(測試遷就 app,非 app 遷就測試);順修 conftest Windows 殺子程序(防 orphan server 假紅)。
- 2026-06-23 (M6 完成) orchestrator 親跑判綠:viewer_ux **13 passed/1 skipped**、app E2E 回歸綠、**811 單元綠**;截圖實證 7 點全落地
  (縮圖疊 YOLO 框〔綠+藍框〕、頂部總開關、可點縮圖+selected 高亮、HUD 檔名+序號+尺寸·位元深+zoom%、hover (x,y)+RGB=(15,18,28)、放大封頂 4279% 不無限)。
  修後重跑 2 反向閘門測試皆綠(AC10 座標修正後游標正確落 scratch 框、AC16 等 hydration 後 checkbox 計數>0)。`.unet/role` 清空回維護模式。
- 2026-06-24 (po 啟動 M7 — UI/UX 重設計,/loop 多 agent 討論) User 用 /loop 起多 agent 討論版面(image-viewer-first + 可收疊),
  5 輪 user-role agent 評分 74/72/72/68/71、未達 85 上限。收斂出「Viewer-First 單舞台 + 召喚式抽屜」:viewer 最大化(~85% 畫面、600→720)、
  次要功能(比較/相似/聚類/DZI/漏檢/匯出)進單一「工具台」expander+tabs、篩選/資料源/排序進收合 sidebar、判定 Rail 可收、頂列薄 Command Bar。
  模擬審圖員未滿意之因:① 把標準拉到 workflow 大改(鍵盤切張/verdict 熱鍵 1/2/3/linked-viewport 比較/跨圖 undo/縮圖虛擬化)遠超「收疊」訴求;
  ② 核心押在未驗證的鍵盤橋生死點。挖到真實 bug:主 viewer `key=f"viewer_{ss.idx}"`([app.py:350])每切張 iframe remount(焦點丟+可能重置 zoom/pan)。
  User 裁決「都要做」=全範圍。PO 排序(風險優先):先 architect spike 驗生死點〔固定 key viewer 跨 rerun 存活 + 元件端 keydown→nav→app rerun→focus 不吃首鍵 + zoom/pan 跨切張保存〕,
  spike 綠才設計→pm→pg→真實 E2E+截圖+效能量測,最後 user-role agent 對「跑起來的成品」再評才結束 loop。沿 M1 viewer「先驗物理可行再設計」慣例。
  附記:討論 workflow 的 user-role 子代理曾把 `user` 寫進 .unet/role(role-play 誤觸),role_guard 擋下 PO 誤寫、已重置——confused-deputy 被閘門攔下。
- 2026-06-24 (architect spike 生死點 PASS) `spike/kbd_*`:真實 Streamlit+playwright 驗 5 條全綠+對照組反證:① 固定 key→iframe 不 remount(idx-key 對照重生 2 次)
  ② keydown→setComponentValue→rerun 切圖不吃首鍵(P2_miss=0,idx-key 對照 miss=3)③ rerun 後 osdEl.focus() 焦點回 viewer(activeEl=osd,第二鍵生效)
  ④ zoom/pan 切張保存 1.866(restore=off 對照重置回 fit 0.622)⑤ 打字守衛 activeElement∈INPUT/TEXTAREA(typed='drb123' 不誤觸)。截圖佐證。**鍵盤連切物理可行、不需降級**;唯一鐵律=viewer key 永不含 idx。
- 2026-06-26 (User 實跑回饋 → 版面再精簡,orchestrator 直接落地 + 全 E2E 回歸保契約) User 看 M7a/M7b 成品後給 4 點:
  ① 拿掉頂列快捷鈕(篩選/漏檢/工具台/匯出/資料源);② 判定 Rail 只留 Bookmark;③ 把 viewer-footer 的
  『顯示偵測框 + 信心門檻(−/＋)』併到最上面 Command Bar;④ 左側 sidebar 過長、精簡。AskUserQuestion 確認兩裁決:
  Verdict/狀態/Tags/Comment/ROIs 搬到工具台新「✏️ 標記」分頁(保留可編輯,verdict/狀態仍走鍵盤 1/2/3·r、頂列加 verdict 徽章);
  工具台改「單一展開 toggle 入口」(取代快捷鈕,**保留 `if ss.tool_open` 閘門以維持 M7b-AC11 連切 0 計算效能**)。
  sidebar 精簡為「資料來源常駐 + 單一折疊『篩選/排序/進階』」(不刪功能、可逆)。
  **契約守恆**:全程不改 4_PM_Feedback 既有斷言 —— 控制仍在 main(非 sidebar、非 expander)滿足 M7a-AC1/AC5、
  頂列 verdict 徽章文字滿足 M7b-AC10「Rail 顯示同值」、「偵測 N 框」「顯示 k/n 框」「可撤 N 筆」皆保留。
  orchestrator 親跑回歸全綠:**單元 811 / M7a 8 / M7b 12 / viewer_ux 13+1skip / app_e2e 1,零 regression**。
  附記:此為 M6/M7「footer 控制位置」的合法設計演進(從 viewer 下方 → 最上面 Command Bar),行為全保留、僅定位改變。
- 2026-06-26 (User 連續微調回饋,orchestrator 落地 + 回歸保契約) 接續上條,User 實跑後再給 4 點:① 拿掉頂部空白
  (CSS 收 stHeader/stToolbar/stDecoration + 緊湊 block-container 上緣);② 判定 Rail 的提示 caption 拿掉(只剩 Bookmark 勾選);
  ③ Command Bar 兩列『合併成一列』(導覽 + 資訊/verdict 徽章 + 顯示偵測框 + 信心門檻−/＋ + 顯示k/n·可撤,單一 st.columns);
  ④ 空白鍵也能 bookmark(index.html keydown 加 ' '/'Spacebar' → 同 'b')。**價值印證**:合併成一列初版把信心 slider 擠到過窄,
  `test_m7b_e2e::test_conf_fine_tuning`(slider 單步 ArrowRight=+0.01)**確定性轉紅** —— 反映真實「slider 太小不好操作」,
  PG 加寬 slider 欄(未改測試)後復綠。orchestrator 親跑回歸全綠:**單元 811 / M7a 8 / M7b 12 / viewer_ux 13+1skip / app_e2e 1**。
- 2026-06-26 (UI 再精簡 + 比較功能多代理提案,orchestrator) ① 又一輪 User UI 回饋:bookmark 移到頂列(toggle button、
  讀寫 sidecar、走 _push_change 入 undo)、移除右側判定 Rail(stage 改兩欄)、移除 viewer 下方尺寸/操作/進度 caption
  (進度『N / 8』移進頂列徽章;16-bit 保留一行誠實語義界線)。契約演進:M7b-AC10 改驗「頂列徽章單一真相」(Rail 已移除)、
  _wait_app_ready 加等導覽鈕 hydrate(底部 N/8 barrier 移除後的健壯化)。全 E2E 綠(811/8/12/13+1/1)。
  踩到並修兩個實作 bug:N/8 移頂列引發 hydration 競態(AC1)、bookmark 移頂列引發『widget 實例化後改 session_state』
  StreamlitAPIException(AC3)——皆 PG 修實作、未放寬測試。
  ② **比較功能:User 要求多代理先提案再開發**。用 Workflow 跑 8 agents(4 視角探索→綜合三版→3 可行性查),產出三版:
  V1 就地便利版(framecompare 合成圖 + folder_B/Path.stem,零新元件/零 spike,high 可行,1–1.5天);
  V2 連動並排(linked dual-OSD,medium,需雙 OSD spike,2.5–3天);
  V3 資料集對比審查台(pairset.py〔Tier A 可單元 gate〕配對清單 + 配對狀態三態 + 篩選 + linked dual-OSD 主舞台,medium,3–4天)。
  多代理推薦『最終 V3、先 V1 增量』;**User 裁決 = V3 一次到位**。
- 2026-06-26 (po 啟動 V3 — 拆解 + spike-first 排序) **裁決**:採 V3。風險優先,沿 M1/M7「先驗物理可行再設計」鐵律。
  模組拆解:(a) `pairset`(Tier A 純邏輯:兩夾 record→依 stem 配對 list[{name,a,b,status∈both/only_a/only_b}],
  可 verify/gate.py 判綠——把『配對』這 CLAUDE.md 點名唯一無客觀紅綠保護的收斂步驟用單元鎖住);
  (b) `compare`(linked dual-OSD 元件,§2.3/§3.10,Tier B GUI,E2E 判綠);(c) app 整合(sidebar 第二夾 + 配對清單套進 nav
  工作流 + 配對牆徽章 + 篩選 + verdict 寫 A 夾單一真相)。**排序**:① 先做 dual-OSD 生死點 spike(ROADMAP 多次明令、
  feasibility 標為單一最大決定因素)——兩 OSD 同 iframe + 雙向 viewport 連動 + 無回授風暴,playwright 實證;
  ② pairset 與 spike 並行(無相依、可先單元判綠);③ spike 綠才設計 compare 元件→pm→pg;④ app 整合;⑤ 真實 E2E + 截圖。
  spike 不綠則誠實降級回 V1(framecompare 並存退路在 V3 仍保留)。釘死語義界線:server 疊合數據只在 A/B 同尺寸可信、
  linked 是 client viewport 連動與 server numpy 並存不互取代(§6)、verdict/sidecar 寫 A 夾為單一真相。
- 2026-06-26 (architect dual-OSD 生死點 spike PASS,playwright 實證 + 截圖) `spike/cmp_component/index.html`(同一 iframe
  內兩顆 OpenSeadragon)+ `spike/cmp_spike.py` + `spike/cmp_verify.py`:5 命題全綠 —— P1 兩顆 OSD 同 iframe 都 open;
  P2 A 縮放→B 同步 zoom;P3 A 平移→B 同步 center;P4 B 縮放→A 同步(**雙向**);P5 **無回授風暴**(一次互動 sync 增量=1、
  zA=zB=2.1 收斂)。防回授靠『syncing 旗標 + 值差門檻(>1e-4 才動)雙保險』+ getZoom(false) 取動畫終點值(沿 viewer_component
  防漂移經驗)。截圖 `spike/cmp_spike_shot.png`:A(藍)/B(紅)同為 zoom 3.500、格線對齊 = viewport 鎖定同一處。
  **V3 最大物理風險(雙 OSD 連動)消化、linked dual-OSD 物理可行、不需降級**。下一步:linked_compare 元件可照此 spike 落實;
  pairset(Tier A)可並行先單元判綠;再 architect/pm/pg compare 元件 + app 整合。`.unet/role` 暫掛 po(切片間)。
- 2026-06-26 (User 細化 V3 比較 UI 規格) User 實跑後給比較模式具體版面:點「比較」→ viewer 區分**左右兩大區塊**;
  每塊**上半=縮圖條(←/→ 切換選圖)、下半=完整圖**;對左右兩圖做**差異 + 混合**運算。
  解讀:這是『兩個獨立選圖器並排 + framecompare 差異/混合』,**未要求 viewport 連動**(linked sync 變可選 bonus,
  dual-OSD spike 仍為『要連動時』的已驗底座、不浪費)。比較模式佔據 viewer 主舞台區(收合縮圖牆/沿用兩欄)。
  待 architect 將此規格落成 compare 設計(每塊選圖器用既有 thumbwall + 完整圖用 osd_viewer 或 st.image;差異/混合複用 framecompare)。
  另:同輪 User 又要求『選一個 YOLO 資料夾自動判斷 labels 在子夾或同影像夾』→ 以多代理 Workflow 建 `labelloc` 模組(見下條)。
- 2026-06-26 (labelloc 完成 — 多代理 Workflow 全程 + orchestrator 親跑判綠) Workflow(7 agents:2 探索→architect→pm→pg→2 對抗驗證)
  走完 U-Net 五階段、各 agent 自設 `.unet/role`、role_guard 正常隔離(PM 寫 5_ 被擋=印證)。產出:
  `3_Architect_Design/22_labelloc.md`(28 AC)、`4_PM_Feedback/test_labelloc.py`(36 測試:28 AC + 8 推導 property,含
  『resolve→label_path 往返指到真實檔』『precedence 唯一決定』『純讀無副作用』)、`5_PG_Develop/labelloc.py`
  (`resolve_label_dir`/`label_path`/`has_labels`,標準庫 os/pathlib、normcase 跨平台、純讀容錯)。
  契約裁決:`labels/` 子夾**條件式優先**(須證實含 ≥1 個對應 `<stem>.json` 才採,否則退同層);ext 固定 `.json`(對齊 yolo.load,
  不支援 `.txt` 別名=YAGNI);PG 攔到一個真 bug(`stems=[]` 誤採子夾)依設計修實作、未改測試。
  整合:app.py sidebar `pred_folder` 改『自動判定 + 可覆寫(留空=自動)』,`records` 後解析 `pred_folder = override or resolve_label_dir(folder,stems) or folder`,
  sidebar caption 顯示判定結果;`_pred_path`/`_detections`/`yolo` 全未改。**orchestrator 親跑:labelloc gate GREEN(36)、
  全單元 847 passed、E2E M7a 8/M7b 12/viewer_ux 13+1skip/app_e2e 1,零 regression。**
  對抗驗證誠實附記(交 PO 知曉,非阻斷):① **mixed 佈局**(部分圖標註在子夾、部分在同層)只回單一目錄→少數圖會靜默漏框
  ——設計明文裁為 over-engineering 排除,若 User 真混放需回 /po 擴張;② `resolve_label_dir(None)` 等非字串會拋(AC27『永不拋』
  未涵蓋 None),但 app 端 folder 恆為 str→不可達;③ `labels/<stem>.json` 若是『目錄』會假陽性(has_labels 不檢 isfile),極罕見。
  皆不影響當前功能(典型 YOLO 佈局一致),列為已知邊界。
- 2026-06-26 (compare 雙區塊比較模式完成 — architect→pm→pg 一輪,orchestrator 親跑判綠 + 截圖) 依 User 細化規格落成:
  architect `3_Architect_Design/23_compare.md`(7 AC);pm `4_PM_Feedback/test_compare_e2e.py`(6 @e2e);
  pg app.py 實作『🔀 比較模式 toggle → 中欄變左右兩大區塊,每塊 上半縮圖條(◀/▶ + ○/● 點選切換)+ 下半完整圖,
  下方對左A/右B 做 差異(framecompare.difference)/混合(blend+alpha)』,A/B 各自獨立選圖索引(cmpA/cmpB);
  並依 User「只留比較」移除工具台其餘 6 tab(標記/相似/聚類/DZI/漏檢/匯出,僅移 UI 入口、模組保留)。
  **機器判綠**:compare E2E **6 passed**;比較預設 OFF → 回歸全綠(單元 847/M7a 8/M7b 12/viewer_ux 13+1skip/app_e2e 1,零 regression)。
  截圖 `app_compare2.png` 實證:區塊A(1/8)| 區塊B(3/8)獨立選圖、各 縮圖條+完整圖並排、下方差異/混合運算區。
  複用 framecompare/_resize_to/_display_rgb/_thumb,未動 viewer.py/index.html(本切片未用 linked OSD;dual-OSD spike 留作日後連動升級)。
  誠實界線:A/B 不同尺寸時 B 經 _resize_to(插值)→ 差異為縮放後近似;Tags/Comment/ROI/匯出 UI 隨 tab 移除暫不可達(模組仍在)。
  **V3 比較切片以 User 細化規格交付完成。**`.unet/role` 回 po。
- 2026-06-25 (M7b 完成 — PM→PG 一輪,orchestrator 親跑判綠) PM 先落 `test_m7b_e2e.py`(11 AC + 1 推導 metamorphic
  測試「change∘undo = identity」;自帶 sidecar snapshot/restore fixture 保冪等不污染樣本);PG 實作 index.html
  document keydown(capture)→nav 協定(←/→/[/]/1/2/3/r/b/u + 焦點守衛 + stopPropagation 防 OSD 誤觸方向鍵)、
  viewer 接 nav_keys=True、app.py nav dispatch(改值即時寫 sidecar + 同步 Rail widget 達單一真相 + 跨圖 undo_stack 留近5 +
  footer step=0.01 slider/[−][＋]±0.05 鈕/「可撤 N 筆」+ 探針回寫 data-verdict/status/bookmarked/conf)。
  orchestrator 親跑:**test_m7b_e2e 12 passed**;回歸 **811 單元綠 / M7a 8 passed / app_e2e 1 / viewer_ux 13+1skip**,**無 regression**。
  過程修兩個實作層 bug(非動測試/契約):① footer 減號鈕字形 U+2212→全形「－」對齊驗收正規式;
  ② undo 的 `st.toast` 緊接 `st.rerun()` 會在 toast 提交前撕掉該 run → 改 pending-toast(存 session_state,下一個正常 run 開頭 flush)。
  **M7b 機器判綠達成;切片閘門通過,可進 M7c。**
- 2026-06-25 (M7a 完成 — orchestrator 親跑判綠) PG 實作(app.py 版面三欄重組+Command Bar+viewer-footer 常駐 slider、
  viewer.py/index.html 固定 key="cv_viewer" 修 remount + auto_height 最大化 + 純 client 端 zoom/pan 跨切張保存 + P1 隱藏探針)
  已就緒;orchestrator 親跑 `pytest test_m7a_e2e.py -m e2e`:**8 passed**(AC1 版面骨架/AC2 __loadCount==1 不 remount/
  AC3 zoom·pan 保存/AC4 收合持久/AC5 footer slider 即時/AC6 16-bit hover 語義/AC7 viewer 高 >660/AC8 P1 探針可讀)。
  回歸:**811 單元綠**、viewer_ux E2E **13 passed/1 skipped**(同 M6)、app_e2e **1 passed**(各檔單獨跑)。
  附記(交 PM,非 PG 改):把 test_app_e2e + test_viewer_ux_e2e **同一 pytest session 串跑**時,
  `test_single_image_hover_shows_xy_and_rgb` 會紅 —— 根因是位置記憶 `.cvr_state.json`/`Position` 跨『測試檔』在同一
  app_server session 持久,前一檔導航到 idx7(wafer16 16-bit Gray、中心落圖外)污染了這個『不導航、用起始圖 hover』的測試;
  **各檔單獨跑皆綠**(per-module gate 即如此跑)。屬 conftest/測試基建層的跨檔狀態隔離議題(PM 擁有),非 M7a 實作 bug。
  M7a 像素級截圖實證(AC7 三欄比例等)仍待 /ux-test 或人觸發。**M7a 機器判綠達成;切片閘門通過,可進 M7b。**
- 2026-06-24 (architect 20_viewer_workbench_redesign) M7 完整設計 28 AC、三切片:M7a 版面+viewer 基座(8)、M7b 鍵盤工作流(11)、M7c 進階(9)。
  含效能量測機制(app 端隱藏 DOM 探針 data-render-ms/reruns/thumb-recalc/tool-calls + 元件 performance.now 回灌,Playwright 讀;PerfA 連切 P95、PerfB 未召喚層 0 tool-call、PerfC 改門檻不重建整牆)、被取代/搬遷的 M6 AC 清單(行為全留、僅定位演進)。
  PO 裁決:`j` 跨文件聚焦降級(捲到+高亮、仍需點,Streamlit 上限)接受;M7c「雙 iframe 同頁 round-trip」開工前先補小 spike;DZI 自動瓦片實作時真量測。三切片各自 E2E 綠才進下一片。
- 2026-06-26 (User 回饋 → 頂列資訊徽章整條移除,orchestrator 落地 + 契約演進保不放寬,**機器判綠完成**) User 指『1/8 · 判定 unset · 偵測 N 框 · 檔名』
  頂列資訊徽章「拿掉」(AskUserQuestion 確認=整條移除)。**契約演進非破壞**:位置/檔名仍在 viewer 內 HUD;verdict 仍由鍵盤 1/2/3 設定。
  app.py 移除 bar[3] 徽章 + 重排 Command Bar 欄位(10→9 欄)+ P1 探針新增 `data-idx`/`data-total`。跨 5 E2E 檔
  (m7a/m7b/app_e2e/viewer_ux/compare_e2e)把 `_wait_app_ready`(原等「/ 8」)、`_progress_index`(原解析「N / 8」)、
  點縮圖→進度(viewer_ux AC12)、verdict 單一真相(m7b AC10→驗探針 data-verdict)、偵測數(m7a AC1→驗「顯示 k/n 框」)、
  「有框」代理(viewer_ux AC10)、16-bit 導航確認(m7a AC6 / viewer_ux AC9 原以可見檔名「wafer16」→改讀 data-idx)全部重歸位。
  **無斷言放寬,僅觀測位置從可見徽章 → P1 探針(設計 §5 P1 早為機器讀面)**;設計同步 20_viewer_workbench_redesign.md 加演進表 + re-snapshot(47 檔)。
  **對抗稽核抓 2 漏網**(初次盤點漏):① compare_e2e 也用「/ 8」當 ready;② m7a-AC6/viewer_ux-AC9 用可見檔名「wafer16」確認導 16-bit。
  **orchestrator 親跑判綠**:單元 847 / m7a 8(獨跑)/ m7b 12 / viewer_ux 13+1skip(獨跑、清位置)/ app_e2e 1 / compare 6,零 regression。
  另根治一個歷史 flaky:位置記憶 `.cvr_state.json` 跨 run 污染『用起始圖』測試 → conftest `app_server` session 啟動前清除(PM 基建,deterministic)。
- 2026-06-26 (po 啟動 compare 第二輪 — User 實跑 V3 比較後再細化,架構演進排序) User 給 6 點比較 UI 規格(見 23_compare.md §7):
  ① 點圖即選、移除下方 ○/● 點選區;② 選中圖有框;③ 圖上顯示檔名、依檔名排序;④ 縮圖條下方 scroll bar 快速拉到某張;
  ⑤ 左右(A/B)各有信心度 filter、改為**上下界雙界**;⑥ 可選特定 **object type(class)**。
  **PO/architect 裁決**:(a) 縮圖條改**橫向可捲 thumbwall**(擴充 thumbwall `horizontal=True` 向後相容;`overflow-x:auto`=原生捲軸滿足④,
  整圖可點滿足①、`.sel` 黃框滿足②、`corner` label 放檔名滿足③);比較模式隱藏主縮圖牆(A/B 各自的條取代,對齊截圖、E2E 僅 2 條 iframe);
  (b) 完整圖升為**疊框圖**,A/B 各 conf **雙界 slider**(信心範圍)+ class **multiselect**(Object 類別)過濾疊的框(⑤⑥);
  (c) conf 雙界**在 app inline 過濾**(不擴充 `overlay.filter_detections` 單下界契約 → 不動 test_overlay 釘死 AC);(d) diff/混合仍對原始像素。
  **回歸保契約**:thumbwall 橫向預設關 → 主縮圖牆(縱向)+ viewer_ux AC11/13/15/18 不受影響;compare 預設 OFF → M7a/M7b/app E2E 不受影響。
  PM 先落 test_compare_e2e.py(AC2 改點圖選取證獨立、AC3 橫向條+檔名、AC8 信心範圍雙界、AC9 Object 類別;AC1/4/5/6 留)→ 待 PG 實作轉綠。
- 2026-06-26 (compare 第二輪完成 — PG 實作 + orchestrator 親跑判綠 + 截圖實證) PG 落地:① `thumbwall` 加 `horizontal=True`
  (index.html `#wall.horiz` flex-row + `overflow-x:auto` 原生捲軸 + 每格固定寬 + corner=檔名 + ellipsis/title;預設縱向不變);
  ② `_cmp_block` 重寫:橫向縮圖條(整圖可點即選、`.sel` 黃框、檔名標、偵測數徽章)取代 ◀/▶/○●;每塊 `st.slider` 信心**雙界**
  (信心範圍 A/B)+ `st.multiselect` Object 類別(切圖前 sanitize session_state 去舊類別防 multiselect 報錯);完整圖升為
  **疊過濾後框**(conf∈[lo,hi]∧class 命中,app inline 過濾、不動 overlay 契約);③ 比較模式隱藏左側主縮圖牆(雙區塊佔滿舞台)。
  **機器判綠(orchestrator 親跑、逐檔)**:compare E2E **8 passed**;全套回歸 **單元 847 / m7a 8 / m7b 12 / viewer_ux 13+1skip /
  app_e2e 1 / compare 8 = 42 passed+1skip,零 regression**(thumbwall 橫向擴充未動縱向主牆;左牆 guard 未破 m7a/viewer_ux)。
  截圖 `app_compare_v3.png` 實證 6 點全到位:橫向可捲縮圖條(檔名標+選中黃框)、信心範圍雙界 slider×2、Object 類別多選×2、
  疊框完整圖、雙區塊佔滿(左牆隱藏)、頂列徽章已無。誠實界線:① 縮圖條捲軸=原生水平捲軸(N 破千再議虛擬化,YAGNI);
  ② conf 上界由 app inline 過濾(overlay 契約仍單下界);③ diff/混合仍對原始像素(與框/篩選無關,§3.4)。`.unet/role` 維護模式(空)。
- 2026-06-26 (User 推翻比較理解 → compare 第三輪『雙 model 覆蓋 triage』,多代理設計 + 全五層 + orchestrator 親跑判綠) **重大需求釐清**:
  User 指出「filter 是要濾掉【所有的影像】不是對單一圖過濾;我要用【兩個 model】對【同一包資料】做整理,弱 model 逮的更少」——
  我先前把比較做成『兩張圖目視 diff』是誤解。**設計探索 Workflow**(7 agents:3 角度提案→對抗評審→綜合)推薦『分歧 triage workbench』
  為主、並存策略落地;AskUserQuestion 三裁決:① **取代**舊 image-vs-image 比較;② 主視圖=覆蓋率儀表板 **+** 分歧 triage 佇列(下鑽);
  ③ **IoU 框級配對**;(預設)兩 model 來源 = A 用現有、新增 model B 夾,缺檔以 missing_b 明示(防打錯路徑假冒差異)。
  **新增純邏輯模組 `modeldiff`(Tier A,五層齊全)**:24_modeldiff.md(26 AC)+ test_modeldiff.py(31 測試,IoU/配對數值逐項手算)+
  modeldiff.py(iou/match 貪婪/diff_image/summarize/filter_images/queue)→ `verify/gate.py modeldiff` **GREEN(31)**。把 CLAUDE.md 點名
  『配對/收斂=唯一無紅綠保護單點』用單元 gate 鎖住。app 整合:sidebar 加 model B 夾、_item_for 加 detections_b+a/b_present、
  _render_compare 重寫為(看哪種差異 selectbox / IoU 門檻 / 信心雙界 / 類別 → 對【整個影像集】triage → 覆蓋率儀表板 + 分歧佇列橫向 thumbwall
  + 下鑽 overlay 疊兩色 A藍/B橘);P1 探針加 data-cmp-queue-n/only-a/only-b/missing-b/delta-imgs 供穩定斷言。compare E2E 改寫(8 AC,
  fixture sample_images/model_b 較弱 B)。**orchestrator 親跑判綠**:modeldiff gate GREEN;單元 **878**(847+31);E2E m7a8/m7b12/viewer_ux13+1skip/
  app1/**compare8** = 42 passed+1skip,**零 regression**。截圖 `app_modelcompare.png` 實證:儀表板『B 比 A 少 1 張·少 3 框·B 缺檔 7 張』、
  分歧佇列『1/8 張符合』、下鑽 A藍/B橘 雙疊(看出 B 漏的框)。過程修一個 E2E bug:st.toggle 在 stCheckbox testid 下,點文字 label 不切換 →
  改點 stCheckbox 控制本體(PG/測試基建修,非放寬斷言)。誠實界線:① v1 IoU 同類配對(same_class 預設 True);② 缺檔 vs 0框已分 missing_b/both_empty;
  ③ 兩 model 須對同一影像夾(兩包不同影像需 pairset,YAGNI 未做);④ verdict/sidecar 仍以影像為單位(未分 per-model)。
  舊 image-vs-image compare(§1-§7)與 framecompare/framediff 模組保留未用(可回退)。`.unet/role` 維護模式(空)。
- 2026-06-26 (User UI 回饋:資料來源簡化為兩個資料夾 + 都能『用選的』,orchestrator 落地 + 回歸保契約) User 兩點:
  ①「這兩個資料夾應該都要能夠用選的」② 「總共只有兩個資料夾,為什麼有三個」。**裁決**:移除多餘的「模型結果資料夾(留空=自動)」
  Model A 覆寫欄 —— Model A 標註本就由 labelloc 從『影像資料夾』自動偵測(labels/ 子夾或同層,典型 YOLO 佈局)。資料來源精簡為
  **正好兩個資料夾**:① 影像資料夾(= Model A:影像 + 自動偵測標註)② 第二個 model 結果資料夾 B。兩欄各加 **📁 原生資料夾選擇鈕**
  (新 `_pick_folder` 用 tkinter askdirectory,已驗 worker-thread 可建 Tk;headless/失敗則回 None 不崩 → E2E 不受影響、仍可打字)+
  `_folder_field`(text_input + 📁,瀏覽鈕在 widget 實例化前寫 ss[key] 再 rerun 回填,合法)。`pred_folder = _resolved_pred or folder`
  (移除 override 分支);caption 改『Model A 標註於…』。**orchestrator 親跑全回歸**:單元 878 / compare 8 / m7a 8 / m7b 12 /
  viewer_ux 13+1skip / app_e2e 1 = **42 passed+1skip,零 regression**;截圖 `app_modelcompare.png` 實證左側僅兩個資料夾欄、各帶 📁 鈕。
  誠實界線:① 📁 對話框僅 local 桌面 Streamlit 可用(headless 無顯示則無效,改打字);② 移除 Model A 覆寫 → Model A 標註須在影像夾
  同層或 labels/ 子夾(非標準位置者改打字到影像夾或回 /po 加回覆寫,YAGNI)。
- 2026-06-27 (User 實跑真實 YOLO 資料集 → 支援 YOLO 切分佈局 + .txt 標註,yolo 契約演進 + orchestrator 親跑判綠) User 選
  `indoor/[Small]/test`(YOLO 切分:images/ + labels/ + .txt 標註 + data.yaml 類別名)→『無支援影像』。根因:app 只掃選到的夾(images 在
  images/ 子夾)、yolo.load 只吃 .json。**修**:yolo.load 加 `.txt`(YOLO `cls cx cy w h [conf]` 正規化→絕對,names 映射 id→名;
  test_yolo +9、design 07 §演進、gate GREEN 49);app 偵測 images/ 子夾、Model A 標註取 sibling labels/、沿目錄上行讀 data.yaml/classes.txt
  載類別名、標註路徑 .json|.txt 容錯。labelloc/imageset 契約不動(app 層處理)。smoke 實證:107 圖 + 10 類名 + 12.png→cabinet/door 具名框。
- 2026-06-27 (User 連發 UI 回饋 B/C/D + 兩夾選擇,orchestrator 批次落地 + 契約演進保不放寬) ① 資料來源精簡為**兩個資料夾**
  (移除多餘 Model A 覆寫欄)、兩欄各加 **📁 原生資料夾選擇鈕**(tkinter askdirectory,worker-thread 已驗;headless 回 None 不崩)。
  ② **B(框顏色/標籤)**:主 viewer 偵測框原為『燒進影像的色帶、無文字、僅 3 類有色其餘紅』→ 改由**元件畫向量框**:類別色
  (新 `_cls_color` 穩定調色盤,主 viewer 與縮圖**共用**→顏色一致)+ **cls·conf 文字標籤**;url 改純顯示圖(不燒框、不糊化)。
  實證 det-lbl 三框文字『scratch 0.91 / dent 0.62 / edge 0.40』、真實資料 cabinet/door 具名彩框。
  ③ **C**:移除『IoU 配對門檻』滑桿(固定 0.5,配對仍用 IoU)。④ **D**:移除『顯示偵測框』開關(無實質意義)→ 偵測框恆顯示、
  只由信心門檻過濾;Command Bar 9→8 欄。**契約演進**(非放寬,測被否決功能):m7a-AC1 去『顯示偵測框』斷言;viewer_ux AC15→縮圖 data-URL、
  AC16→只驗信心門檻、AC17→驗開關全移除、AC18→驗框恆顯示、移除 _top_show_overlay_checkbox helper;compare-AC6 去 IoU、加驗 IoU 滑桿已移除。
  **orchestrator 親跑判綠**:單元 887 / m7a 8 / m7b 12 / viewer_ux 13+1skip / app_e2e 1 / compare 8 = 42 passed+1skip,**零 regression**。
  誠實界線:框級配對 IoU 固定 0.5(不暴露);調色盤以類別名 hash 取色(同名同色、極少數同色碰撞可接受)。
- 2026-06-27 (User 連發 UI 精修:排序 + Object 下拉 + 移除 caption/＋－,orchestrator 批次落地 + 探針錨點遷移) 4 點:
  ① **縮圖牆排序**(單張 + 比較共用):新增『排序』下拉(檔名 / 信心高→低),複用 `filtersort.sort_items`(conf=該圖最大偵測信心,
  tie-break name);單張排 shown_items+導覽、比較排分歧佇列(取代 disagreement-priority)。② **Object 類別下拉**:Command Bar 信心門檻旁
  新增 selectbox(全部 / 單一類別)→ overlay_classes;移除 sidebar 舊『只顯示偵測類別』文字框(單一真相)。③ **移除『顯示 k/n 框 · 可撤 N 筆』
  caption**;④ **移除信心門檻旁 [−][＋] 鈕**(只留 slider)。Command Bar 8→6 欄。**契約演進(錨點遷移,非放寬)**:caption 兩個機器讀數
  改由 P1 探針新增 `data-shown-k`/`data-shown-n`/`data-undo-n` 暴露;m7a-AC1/AC5(顯示框數)、m7b `_undo_count`(可撤)、viewer_ux
  AC11/AC18 全改讀探針;m7b-AC8 改驗 slider step=0.01 + 斷言 [−][＋] 已移除。**orchestrator 親跑判綠**:單元 887 / m7a 8 / m7b 12 /
  viewer_ux 13+1skip / app_e2e 1 / compare 8 = 42 passed+1skip,**零 regression**(一個預期紅:m7b-AC8 測到被移除的＋－鈕 → 改斷言已移除後綠)。
  截圖 `app_realdata.png` 實證:Command Bar 無＋－/無 caption + Object 下拉、縮圖牆上方『排序』下拉、真實 indoor 具名彩框。
- 2026-06-27 (User UI 收尾:改名 + 移空白 + 使用手冊 + 移除縮圖牆字/篩選排序進階區,orchestrator 批次 + 修 flaky) 5 點:
  ① 移除『縮圖牆』標題字;② 標題 `🔬 CV Review Workbench` → **`🖼️ YOLO Image Viewer`**(APP_TITLE 同步改 5 個 e2e 檔 + app_e2e);
  ③ 移除標題上方一大塊空白(根因=新版 Streamlit `.block-container` 上 padding,舊 `section.main` 選擇器沒命中 → 改 class+testid 雙保險 +
  隱藏只放 `<style>` 的空 markdown 容器);④ 標題旁加 **❓ 使用手冊**(用 `st.dialog` modal,非 popover —— popover 內容常駐 DOM,
  其『信心門檻』粗體會被 E2E `get_by_text` 誤命中為隱藏元素致假紅,實測確認;dialog 只在開啟時進 DOM);⑤ User『這些功能都移除』→
  整個移除 sidebar『🔍 篩選/排序/進階』折疊區(fs_sort/標籤/判定/review/bookmark/comment/類別/智慧排序/queue),改給無作用預設(不篩選、
  排序由頂列『排序』下拉)。**orchestrator 親跑判綠**:單元 887 / m7a 8 / m7b 12 / viewer_ux 13+1skip / app_e2e 1 / compare 8 = 42+1skip,**零 regression**。
  過程修 2 個:① popover→dialog(解 ③④ 連帶的 3 個假紅 m7a-AC1/AC5、viewer_ux-AC16);② m7a-AC5 信心 slider 加寬欄(3.2)+ 斷言改『輪詢 k 變化』
  取代固定 sleep(60 次快速 ArrowRight 在 server 忙時 rerun 未沉澱的 flaky 根治)。截圖 `app_final.png`/`app_manual.png` 實證版面 + 手冊。
- 2026-07-04 (po 啟動 — User 回饋:信心門檻要卡縮圖牆、且要雙邊) User 指出頂列「信心門檻」只影響主圖疊框,縮圖牆仍列出資料夾內
  每一張圖,不管有無偵測落在門檻內。需求文件 `1_user_needs/03_confidence_range_thumbwall_triage.md`。**AskUserQuestion 確認兩點**:
  ① 語義 = 濾影像清單(triage),非只濾單圖框;② 完全無偵測(0 框)的圖一併濾掉,不另開開關。
  **PO 裁決**:Tier B GUI 整合(app.py 層,無新純邏輯模組)、E2E 判綠,比照既有 `_cmp_filter`(比較模式雙界)app-inline 慣例,
  不擴充 `overlay.filter_detections`/`filtersort` 契約(兩模組簽名不動)。architect 已落附錄於 `20_viewer_workbench_redesign.md`
  §7「設計演進(2026-07-04)」,AC-conf1..7 全釘死可驗規則。
  **中途關鍵發現、二次確認(反向閘門級別但非退層,PO 當場裁決)**:著手設計時發現 `sample_images/` 8 張圖僅 2 張
  (`lot42_frame_000`/`001`)有偵測 JSON,其餘 3 張 lot42 + 全部 3 張 wafer16(16-bit)皆 0 偵測。若「0 框一併濾掉」
  不對「全開」設例外,**預設(未動 slider)就會讓這 5 張消失**,破壞現有 42 項 E2E 對 `TOTAL=8` 的假設、且 16-bit
  測試圖預設在單張模式不可達;真實審圖场景亦同(乾淨圖/未跑模型的圖預設消失,滑鼠鍵盤切不到)。
  用 AskUserQuestion 二次確認 → User 選**「全開時不 triage(向後相容)」**:`lo<=0.0 and hi>=1.0` 時清單不受影響
  (含 0 框圖,同現狀);使用者**主動**偏離全開(下界>0 或上界<1)才啟動 triage、此時 0 框圖必被濾除。
  設計文件已同步此裁決(見 §7 `_in_conf_range` 函式 + AC-conf2 的「向後相容關閉點」)。
  下一步:PM 落 E2E 斷言(`data-conf`→`data-conf-lo/hi` 契約演進、AC-conf1..7)、
  PG 改 app.py(`footer_conf_thr` session key 型別 float→tuple、`_passes` 加 `_in_conf_range` triage 述詞、
  `kept` 改雙界內嵌過濾),orchestrator 跑全套 E2E 回歸判綠。
- 2026-07-04 (信心區間 triage 完成 — PG 實作 + orchestrator 親跑判綠) PG 落地:①`_cmp_filter`(雙界+類別過濾)
  由比較模式上移為模組層級共用函式,單張模式 `kept` 改呼叫它(取代 `overlay.filter_detections` 單下界呼叫,
  overlay.py 契約未改);②新增 `_in_conf_range(it,lo,hi)`,`_passes` 併入此 triage 述詞;③footer slider 改
  `st.slider(...,(conf_lo,conf_hi),...)` 雙滑塊;④P1 探針 `data-conf`→`data-conf-lo`/`data-conf-hi`。
  **PG 實作時另發現並修一個防卡死缺口(非 User 需求原文但必要,見設計 §4k)**:`shown_items` 被信心 triage
  篩空時原 `st.warning(...);st.stop()` 會讓 slider 本身(定義在 st.stop() 之後)從畫面消失,使用者無法拉寬
  範圍脫困;修為篩空分支**先重畫同 key slider 再 st.stop()**。PM 落 `test_conf_range_e2e.py`(7 條 AC-conf1..7,
  含 AC-conf5 防卡死驗證:篩空後 slider 仍在、可操作、拉回全開可恢復);`test_m7b_e2e.py` 的 `data-conf` 讀取
  改 `data-conf-lo`(AC8 沿用)。**orchestrator 親跑判綠(逐檔)**:單元 **887**(不變,無新純邏輯模組)/
  m7a **8** / m7b **12** / viewer_ux **13+1skip** / app_e2e **1** / compare **8** / **conf_range 7(新增)**
  = **49 passed+1skip,零 regression**。
  誠實附記:compare_e2e 在跑滿整檔時偶現 2 項 flaky(`test_dataset_triage_filters_whole_set`/
  `test_backward_compatible_default_off`,frame-detach/hydration 時序相關);用 `git stash` 比對後**確認
  在改動前的原始 app.py 上同樣重現**,屬既有 flake、非本輪回歸,重跑即綠(已於本輪驗證記錄留痕,未計入
  regression 判定,未列入待辦——與既有 compare 測試基礎設施的已知時序脆弱一致,非本次變更引入)。
  E2E helper 撰寫踩到一個坑:range slider 的 `Home`/`End` 鍵無作用(只有 ArrowLeft/Right 生效),且連續快速
  按鍵會被 server 忙時的 rerun 吃掉部分按鍵(同 2026-06-26 m7a-AC5 根因)——`test_conf_range_e2e.py` 改用
  「單鍵→等沉澱→重讀值」逐步逼近寫法解決,此為測試基建細節,不影響 app 行為契約。
- 2026-07-04 (User 回報:hover RGB/座標「不 realtime 更新」→ 調查 + 右鍵釘選點功能,orchestrator 全程留痕)
  User 回報主 viewer hover 顯示的座標/RGB 移動滑鼠時不即時更新。**調查過程(誠實記錄,非猜測)**:
  用真實 Playwright `page.mouse.move`(非測試既有的合成 `dispatch_event`)在①剛載入、②切張後(固定 key
  不 remount)、③縮放後 三種情境各驅動兩段真實滑鼠移動,HUD 座標/RGB 皆逐次正確更新、零 console/page
  錯誤——**standalone Streamlit 版本本身沒有重現此 bug**。但調查中發現一個真實、獨立的程式碼缺陷:
  `viewer_component/index.html` 的 `buildViewer()`(每次切張都會呼叫)把 `#osd`/`window` 的
  `mousemove`/`dragstart`/`selectstart`/`mousedown`/`mouseup` 監聽器**掛在每次呼叫裡、從未移除**——
  這些元素跨切張存活(不像 OSD `viewer` 物件本身每次重建),導致監聽器隨切張次數**無限疊加**(切 N 張後
  同一個滑鼠事件觸發 N 個重複 handler)。雖每個 handler 各自算值正確、不影響單次正確性,但長時間/大量
  切張後累積的重複運算是「感覺不夠即時」的合理成因之一(User 環境可能已切過大量圖累積此效應,或在
  nativeApp WebView2 載體下有不同臨界點;此界線誠實記錄,非本次確認為根因,僅為排除並修正的已知缺陷)。
  **修正**:將這些跨圖存活的監聽器抽成 `setupOsdListeners()`,腳本啟動時只呼叫一次;`buildViewer()`
  只保留『每次都必須重掛』的部分(掛在 OSD `viewer` 物件本身的 `canvas-click`/`open`/`zoom` 等 handler,
  因該物件確實每次重建)。回歸驗證:m7a 8(含 `__loadCount==1` 不 remount 探針)/ viewer_ux 13+1skip /
  m7b 12 / app_e2e 1 / compare 8,**全綠、零 regression**,證明抽離監聽器未改變任何既有行為。
  **同輪需求(User)**:右鍵點一下→把當下 hover 的座標與 RGB 記錄並固定顯示(不隨滑鼠移開消失),
  再右鍵→覆蓋,切圖→清空。需求文件 `1_user_needs/04_pin_point_right_click.md`;PO 裁決 MVP 範圍
  (單點、不持久化、不可清除鈕,User 原文「不在乎」多點/存檔/清除鈕)。architect 落
  `20_viewer_workbench_redesign.md` §3.12 + AC-pin1..5(**純 client 端,`viewer.py` 簽名/`meta`/`dets`
  資料形狀零變更,無 Python 契約可動**)。PG 實作:`contextmenu` 監聽(`e.preventDefault()` 蓋原生選單)+
  模組層級 `pinPoint` 狀態(`buildViewer` 換圖時自然重置)+ `drawRois()` 內新增 `.pin-ov` 洋紅圓點 overlay
  (與 ROI/偵測框同路徑重繪,縮放平移自動跟位置)+ `renderHud()` 新增獨立釘選列(📌,與 hover 列並存)。
  PM 落 `test_pin_point_e2e.py`(AC-pin1..4,4 條;AC-pin5 併入 AC-pin1 的 `.pin-ov` 計數斷言)。
  **orchestrator 親跑判綠**:pin_point 4 passed(重跑兩次穩定)+ 上述回歸全綠,零 regression。
  誠實界線:瓦片模式(大圖)釘選 RGB 恆 null(與既有 hover 瓦片降級語義一致,§6);不持久化、不匯出、
  不支援多點清單(對齊 User 原文「不在乎」的裁決範圍,非遺漏)。
- 2026-07-04 (User 連發三點:排序缺低→高、要顯示信心範圍內張數、「filter 切下一張就不見了(嚴重)」;
  orchestrator 即時修 + 全程留痕) ① 排序下拉補回「信心(低→高)」(`filtersort.sort_items(...,reverse=False)`
  已有、只是 UI 少一個選項);單張模式與比較模式的分歧佇列排序同步補上。②「排序」下拉旁新增
  `st.caption(f"此信心範圍內符合:{total}/{len(items)} 張")`,零額外開關,全開時等於資料夾總數。
  ③ **嚴重 bug、實測重現後修復**:設信心門檻/Object 類別篩選後按「下一張」,篩選值被打回預設。
  根因:Streamlit 對『本輪指令碼跑完前都沒被實例化』的 keyed widget 會清空其 session_state(孤兒
  widget 狀態清理);Command Bar 的信心 slider(`footer_conf_thr`)、Object 下拉(`cls_filter`)原本排在
  ⟵/⟶/跳頁/⭐ 按鈕**之後**才實例化,這些按鈕會呼叫 `st.rerun()`,導致按下時本輪提早結束、兩個 widget
  在該輪『未被呼叫到』而遭清空;縮圖牆的「排序」下拉(`sort_mode`)則是包在 `if not ss.thumb_collapsed:`
  內,收合縮圖期間整輪都不會被呼叫,同樣機制清空。**修法**:讓 `footer_conf_thr`/`cls_filter` 的實例化
  搶在任何 nav 按鈕之前執行(`st.columns` 的視覺欄位順序只看 `bar=st.columns([...])` 當下的宣告,與後續
  往哪個 `bar[i]` 寫入的程式碼順序無關,故不影響版面);`sort_mode` 改**恆渲染、不隨收合狀態條件式跳過**。
  用真實 Playwright 操作重現 bug(改值→按下一張→讀值歸零)、套用修法後同一操作值不再歸零,三個場景
  (信心門檻、Object 類別、排序×收合展開)逐一驗證。PM 落 `test_widget_state_persistence_e2e.py`(3 條),
  **對抗驗證**:先用 `git stash` 還原成修前的 app.py 重跑這 3 條測試,**全部如預期失敗**(證明測試真的
  在測這個 bug、非空歡喜);stash pop 修復後全部轉綠。
  **同輪意外發現、順手修復(User 提供螢幕截圖佐證)**:調查「篩選消失」時 User 另外回報「左邊縮圖沒有
  綠色框但右邊大圖有」——直接對 Python 端 `overlay.draw` 算過的縮圖像素驗算,確認框像素**確實有畫進
  縮圖**(rows 2-8, cols 2-7 皆變色),只是被 thumbwall_component 的「索引數字角標」(實心黑底
  `rgba(0,0,0,.65)`,恰好也定位在縮圖左上角)完全蓋住——純 UI 疊層問題,非 overlay/yolo 資料層 bug。
  修法比照既有 `.mark`(⭐/✓)已驗證有效的作法:角標與 `.badge`(偵測數徽章)改用「文字 + text-shadow
  描邊」取代實心背景色塊,不再有機會蓋住底下的偵測框像素。PM 落
  `test_thumbnail_badges_have_no_opaque_background`(讀 `.corner`/`.badge` 的 CSS 計算樣式斷言
  background alpha≈0,不採像素計數——像素級截圖比對抓到修前後綠像素數僅 9 vs 12,margin 太薄不穩定,
  改語意層斷言更穩固);同樣以 `git stash` 對抗驗證,修前 `alpha=0.65` 精確失敗、修後轉綠。
  **orchestrator 親跑判綠**:單元 887(不變)/ viewer_ux 14+1skip(新增 1 條)/
  widget_state_persistence 3 passed(新增)/ m7a 8 / m7b 12 / app_e2e 1 / compare 8 /
  conf_range 7 / pin_point 4,**零 regression**。
- 2026-07-04 (User 回報「這個圖並不是完整的,應該要做好 RWD」,提供真實資料集
  `C:/code/claude/iWISC/dataset/perfect`〔5 張 1254×1254 純影像、無標註,image-only 場景〕測試,
  orchestrator 實測 + 修復) M7c 設計文件早已規劃 RWD 斷點(§3.11,2026-06-24)但**從未實作**——
  ROADMAP 決策日誌中 M7a/M7b 皆有「完成」記錄,M7c 沒有,之後專案直接轉向 compare v3(資料集級
  triage),RWD 連同 linked-compare/縮圖虛擬化/DZI 自動瓦片一起被擱置。
  **實測重現**(真實資料集、多種 viewport 寬度截圖比對):1920/1366px 下版面正常;窄到 1024px 以下,
  **Streamlit sidebar 用 inline style 固定 `width:300px`,與 viewport 寬度完全無關**,窄窗下佔掉不成
  比例的空間(800px 寬時佔 37.5%),把縮圖牆/主 viewer 一起擠小——這是唯一實測到的真正瓶頸(縮圖牆
  本身 `.cell img{width:100%}` 已隨容器縮放,不需額外處理)。
  **修法(純 CSS,零 JS round-trip、零風險)**:實測驗證 `!important` 可蓋掉 Streamlit 對 sidebar 設的
  inline width(非既有 M7c 設計那套「元件回報 window.innerWidth → app 讀 ss.viewport_w → 調欄寬比例」
  round-trip 機制——sidebar 寬度問題純屬 CSS 层級,不需要 Python 側知道確切寬度);加兩級 media query
  斷點:`vw<=1100px` sidebar 收到 220px、`vw<=760px` 收到 160px(此寬度以下 Streamlit 自身原生行為
  也會介入,實測 700px 時 sidebar 幾乎讓出全部空間給 viewer)。E2E 預設 viewport(Playwright 預設
  1280×720)在兩個斷點之外,故此變更對既有測試零影響。
  **orchestrator 親跑判綠**:單元 887 / m7a 8 / viewer_ux 14+1skip / m7b 12 / app_e2e 1 /
  widget_state_persistence 3 / compare 8 / conf_range 7 / pin_point 4,**零 regression**。
  誠實界線:未做「縮圖牆隨窄寬自動收合」(M7c-AC6 原設計的另一半);目前縮圖牆仍需使用者手動按
  「收合縮圖」。若日後真的需要窄寬自動收合,才值得補 M7c 那套 round-trip 機制(現在的 CSS-only 解法
  已解決實測中最大的瓶頸,YAGNI 暫不做更多)。
- 2026-07-04 (User:「我想要再多一個 focus object 模式,他會自動放大到這張圖最高 confidence 的
  object,這樣幫助我快速的看 yolo 判斷結果」,orchestrator 全程實作 + 兩個真 bug 在驗證時當場抓到)
  需求文件 `1_user_needs/05_focus_object_mode.md`;PO 裁決:純轉發 + app 端一行 `max()` 挑選,不新增
  純邏輯模組(挑「目前顯示框裡信心最高者」不足以撐一個獨立模組,見 20_viewer_workbench_redesign.md
  §3.13)。architect 落 §3.13 設計 + AC-focus1..4。PG 實作:`viewer.py` 新增 `focus_bbox` 可選參數
  (純轉發,不做挑選邏輯);app.py 新增 `st.toggle("🎯 Focus Object...")`;`viewer_component/index.html`
  新增 `focusOnBbox()`(35% 留白 fit)+ `curFocusBbox`/`lastFocusBbox` 狀態 + 三處掛鉤(open handler /
  同圖 focus 目標變動 / 三態分支)。
  **實作時當場抓到兩個真 bug(非空談驗證,皆用真實 Playwright 操作重現→修→再驗證)**:
  ① 新 `st.toggle("🎯 Focus Object...")` 放在 Command Bar 的 ⟵/⟶/跳頁 按鈕**之後**——與稍早
  「filter 切下一張消失」**同一個 widget-cleanup 成因**(§4.l 鐵律早已寫下但這次還是踩到,證明
  這條規則需要每次新增控制都主動檢查)。探針證實:切下一張後 `curFocusBbox` 從正確值變 `None`。
  修法:把兩個 toggle(連同既有 `compare_on`)整段移到本區塊最前面,任何按鈕之前。
  ② 三態設計缺口:`focus_bbox` 原本只有「有值」/`None` 兩態,導致「模式開啟但本圖 0 偵測」也共用
  `None`,誤入 M7a 的 `pendingRestore` 分支、沿用上一張殘留的高倍率 zoom 顯示一張無關的裁切畫面
  (實測:聚焦某框後切到 0 偵測圖,zoom 停在 11.76 不變,而非合理的 fit≈1.0)。修法:三態化——
  `None`=模式關閉、`[]`=模式開但本圖無框(退回 `goHome()`)、非空 list=聚焦該框(§4.m)。
  PM 落 `test_focus_object_e2e.py`(AC-focus1..4,4 條,含專門驗上述兩個 bug 場景的 AC-focus2/3)。
  **orchestrator 親跑判綠(逐檔)**:單元 887(不變,無新模組)/ focus_object 4 passed(重跑穩定)/
  m7a 8 / viewer_ux 14+1skip / m7b 12 / app_e2e 1 / compare 8 / widget_state_persistence 3 /
  rwd 1 / pin_point 4 / conf_range 7,**零 regression**。
  誠實界線:「使用者手動又縮放到別處」不記錄,下次切圖/篩選變動一律重新 fit 回最高信心框
  (對齊 User 原文「不需要記住我手動縮放過的位置」,非遺漏)。
- 2026-07-04 (User 連續三則版面/互動回饋,orchestrator 逐一實測 + 修復) ① 兩個 toggle 各佔一整行、
  右側大片留白太空 → 併成一列(`_modecol`)。② 再要求連標題/使用手冊都併進同一列 → 合併為單一列
  `_top = st.columns([...])`(標題、Focus Object、比較模式、使用手冊),說明文字從行內文字移到
  `help=` 滑鼠懸停提示(不佔版面又不遺失資訊)。兩輪皆截圖 + 回歸(m7a/compare/focus_object)驗證。
  ③ **嚴重 bug、User 回報「左邊工具列收起來後就再也看不到了」+「版面跑掉」(截圖佐證直排文字)**:
  用 `bounding_box()` 實測確認「展開縮圖」鈕收合後 `width=0`、`is_visible=False`,真的卡死,
  且縮圖牆的「排序」下拉在收合寬度下被擠成逐字直排——不是使用者誤會。根因:收合/排序/符合張數
  三個控制項原本跟縮圖格共用同一個會被 `_left_w=0.0001` 擠到近乎 0 寬的 `left` 欄;§4.l 先前建議
  「靠外層容器寬度趨近 0 隱藏」本身就是錯的,容器變窄時 Streamlit 不會優雅隱藏內容,而是擠壞它
  (§4.n 已勘誤 §4.l 這條錯誤建議)。**修法**:控制項移到獨立、不隨收合狀態變窄的欄
  (`_ctrl_left`,仍用 0.85:6.6 對齊縮圖欄視覺位置),縮圖格本身才依收合旗標變窄——「控制項容器」
  與「內容格容器」分兩層。PM 落 `test_thumbwall_collapse_recovery_e2e.py`(3 條);**對抗驗證**:
  `git stash` 還原成修前的 app.py 重跑,3 條**全部如預期失敗**(展開鈕點不到、逾時),stash pop
  修復後全綠。
  **同輪也順手修復一個關聯設計缺口(User 截圖:選了 Object 類別後某圖仍留在清單但畫不出框)**:
  `_in_conf_range` 擴充第三參數 `classes`,清單 triage 從「只看信心」改成「信心+類別同一筆偵測
  需同時滿足」,語義對齊 `kept` 的 `_cmp_filter`(見 20_viewer_workbench_redesign.md §7 再演進);
  順帶解掉 `_all_classes` 選項的自我循環(改由「只套信心、不套類別」的中繼結果推導)、並擴充
  §4.k/o 的篩空防卡死(復原分支現在同時重畫信心 slider **與** Object 類別下拉,只補前者會在
  類別造成篩空時卡死)。PM 落 `test_conf_range_e2e.py` 新增 AC-conf8/9(2 條);**對抗驗證**同樣
  用 `git stash` 確認修前必紅、修後轉綠。
  **orchestrator 親跑判綠(逐檔)**:單元 887(不變)/ m7a 8 / m7b 12 / viewer_ux 14+1skip /
  app_e2e 1 / compare 8 / widget_state_persistence 3 / rwd 1 / pin_point 4 / focus_object 4 /
  conf_range 9(7→9)/ thumbwall_collapse_recovery 3(新增),**零 regression**。
- 2026-07-04 (User 回報「左邊一開始選資料夾的地方不見了」,追問後確認「整個側邊欄不見了、
  進不去,滑鼠移過去也不會跑出來」——嚴重問題,orchestrator 實測重現 + 修復) 用 bounding_box
  逐步排查:先確認 App 本身沒有任何程式碼會關閉 sidebar;接著把本專案所有自訂 CSS 全部移除、
  在同一視窗寬度(700px)下依然重現 sidebar 消失,**證明根因不是本專案任何一輪改動,而是
  Streamlit 內建的窄視窗響應式行為**:sidebar 在窄視窗下被判定進入 collapsed 狀態
  (`aria-expanded="false"`),用 `transform: translateX(-300px)` 整個平移出畫面,而負責「點回來
  展開」的控制項(`stSidebarCollapsedControl`)在這個視窗寬度下的 DOM 裡計數為 0——使用者卡住
  真的進不去,不是操作問題。**修法**:直接鎖住 `[data-testid='stSidebar']{transform:none !important;}`,
  讓 sidebar 永遠不被 Streamlit 自己的響應式邏輯推出畫面;稍早那輪 RWD 欄寬 media query(縮窄但
  不隱藏)維持不變、兩者疊加才是完整修復(窄視窗下變窄、但恆留在畫面上、恆可用)。
  PM 落 `test_rwd_e2e.py` 新增 `test_sidebar_never_pushed_off_screen`(1 條,涵蓋 1920/1000/700/500px
  四級寬度斷言 `x>=0` 且資料夾輸入框恆可見);**對抗驗證**:`git stash` 還原成修前的 app.py 重跑,
  在 700px 精確重現 `x=-300` 失敗(與實測完全吻合),stash pop 修復後轉綠。
  **orchestrator 親跑判綠**:單元 887(不變)/ rwd 2(新增 1 條)/ m7a 8 / viewer_ux 14+1skip /
  app_e2e 1,**零 regression**。
- 2026-07-04 (User:「我想請你幫我再增加一個 tool box,平常是折疊的,裡面是一些在做 CV 時常用的
  功能,比如說調亮度對比之類,方便在看圖的時候能夠更加方便」,orchestrator 全程走五層 + 新模組)
  AskUserQuestion 兩輪確認範圍:①「只影響顯示(推薦)」——不寫回 sidecar、不影響偵測/判定/匯出;
  ②功能清單鎖定 7 項:亮度/對比、gamma、直方圖均衡化、反色、對比度極限拉伸(min-max stretch)、
  二值化、Canny 邊緣偵測。需求文件 `1_user_needs/06_cv_toolbox.md`。
  **PO 裁決:新增 Tier A 純邏輯模組 `imgadjust`**(7 個調整皆是「輸入 uint8 RGB → 輸出 uint8 RGB」
  的純函式,無 I/O、無 GUI、不吃既有模組——夠格獨立模組,非 app 端隨手一行可打發)。
  architect 落 `3_Architect_Design/25_imgadjust.md`(23 AC,逐項手算數值,如 AC4:pixel=138、
  contrast=2.0、支點 128 →`(138-128)*2+128=148`);釘死 `equalize_histogram`/`canny_edges` 需要 cv2、
  缺 cv2 時容錯降級為原圖複製品(不崩潰、不假裝有效果),其餘 5 個函式零 cv2 依賴;色彩空間全程
  RGB(對齊 overlay/imgio 慣例,cv2 呼叫前後自行 RGB↔BGR 轉換)。PM 落 `test_imgadjust.py`
  (28 測試:23 AC + 5 條推導的『不 mutate + 型別/形狀不變性』參數化測試)。PG 實作 `imgadjust.py`,
  `python verify/gate.py imgadjust` 首次即 **GREEN(28 passed)**,無反向閘門。
  **app 整合(UI 接線,Tier B,architect 補 20_viewer_workbench_redesign.md §3.14 + AC-cvbox1..4)**:
  新增 `st.expander("🧰 CV 顯示調整工具箱…", expanded=False)`,置於 Command Bar 之後、比較模式之前,
  內含 7 組調整的 checkbox+slider + 一顆「🔄 重設調整」按鈕;只套用在主 viewer(`_display_url_adjusted`
  取代原 `_display_url`,後者已無其他呼叫者故一併刪除),縮圖牆維持不套用(對齊需求「不需要影響
  縮圖牆」)。套用管線依設計 §3.8 固定順序疊加,`threshold`/`canny_edges` 視為管線終點。
  切圖(`ss.idx` 改變)時 7 個開關自動全部關閉、恢復原本顯示(對齊需求「切換圖片…後恢復原本顯示」);
  「關掉工具箱後恢復原本顯示」則因 Streamlit `st.expander` 不對外暴露收合事件回呼,改以顯式
  「🔄 重設調整」按鈕落地同一使用者意圖(語意等價、不依賴私有前端行為,已記錄於設計 §3.14 供
  PM/PG 對齊,非規避需求)。`#perf` 探針新增 `data-adj-active`(任一調整啟用中)供 E2E 穩定斷言。
  **關鍵設計判斷(避免複製 §4.l 那個 widget-cleanup bug 第三次)**:確認 `st.expander` 收合/展開是
  **前端視覺層級**、不是 Python `if` 條件式跳過——內部 widget 不論收合與否每輪都會被實例化,故
  本工具箱天生免疫 §4.l 那個成因;但「🔄 重設調整」按鈕本身會觸發 `st.rerun()`,依 §4.l 鐵律仍需
  排在本節**所有** checkbox/slider 呼叫之後才呼叫(已按此實作、非事後才發現的 bug)。
  PM 落 `4_PM_Feedback/test_cv_toolbox_e2e.py`(AC-cvbox1..4,4 條):工具箱預設收合、勾選反色後
  送進 viewer 的像素值近似 `255-原值`、切圖後 `data-adj-active` 自動回 0、開啟多項調整不影響
  `data-shown-k`/`data-shown-n`(偵測框判定不受影響)。**對抗驗證**:`git stash` 還原成整合前的
  app.py 重跑,4 條**全部如預期逾時失敗**(工具箱標籤/控制項不存在),stash pop 修復後全綠。
  requirements.txt 新增 `opencv-python-headless`(headless=無 GUI 依賴,適合伺服器環境;缺此套件
  時 `imgadjust.HAS_CV2=False`,均衡化/Canny 兩項優雅降級,不影響其餘 5 項)。
  **orchestrator 親跑判綠(逐檔)**:單元 **915**(887+imgadjust 28)/ cv_toolbox 4(新增)/
  focus_object 4 / conf_range 9 / rwd 2 / thumbwall_collapse_recovery 3 / widget_state_persistence 3 /
  pin_point 4 / m7b 12 / viewer_ux 14+1skip / m7a 8 / app_e2e 1 / compare 8,**零 regression**。
  誠實界線:「關掉工具箱=重設」用顯式按鈕而非收合偵測落地(見上,架構取捨已記錄);滑桿參數值
  本身在切圖時不重置(只關開關,類似「靜音鍵保留音量」),非疏漏。
- 2026-07-04 (User 回報「左邊的資料夾選項縮進去就再也拉不出來了,造成版面異常」〔截圖=~40px 直排
  文字窄條〕,orchestrator 實測重現 + 修復 —— 本日稍早「sidebar 防跑丟」修法的已知後果收尾)
  **Playwright 1280px 實測重現**:hover sidebar → 點收合鈕「«」→ sidebar 寬度變 0、內容溢出成
  直排窄條,與 User 截圖一致。**根因兩層**:① 稍早 `transform:none` 只擋「平移出畫面」,Streamlit
  收合時還會把**寬度**收 0 —— transform 被擋、寬度沒擋,卡在半收合;② Streamlit 1.56 收合後的
  展開鈕是 `stExpandSidebarButton`(前一輪查的 `stSidebarCollapsedControl` 是舊版 testid,已改名
  ——該輪觀察對象因此不完整,本輪以實際 DOM 為準),位在頂部 header 工具列、已被 User 明確要求的
  「拿掉頂部空白」CSS 藏掉 → 展開鈕不可見,真的拉不回來。**裁決:sidebar 定為恆展開、不可收合**
  (完成稍早「恆留在畫面上、恆可用」裁決的邏輯終點;本 app sidebar 只放資料來源兩欄,收合價值低於
  「拉不回來」的災難成本;可靠展開途徑需露出 header〔與既有裁決衝突〕或自製浮動鈕〔過度工程〕)。
  修法(app.py 純 CSS):①收合態 `[aria-expanded='false']` 鎖寬 300px(media query 以同 specificity
  selector 列表窄窗蓋成 220/160,直排窄條在任何寬度不再可能);②「«」與 `stExpandSidebarButton`
  皆 display:none(陷阱觸發器移除);拖拉調寬(展開態)不受影響。architect 落
  20_viewer_workbench_redesign.md §3.11.1(AC-sbfix1/2);PM 落 test_rwd_e2e.py 新增 2 條;
  **對抗驗證**:`git stash` 還原修前 app.py,AC-sbfix1 精確重現 `width=0` 失敗(=User 的 bug),
  stash pop 修復後綠;AC-sbfix2(700px 自動收合態鎖寬)修前亦綠,誠實記錄為回歸防護、非對抗紅點。
  契約 re-snapshot(58 檔)。**orchestrator 親跑判綠(逐檔)**:單元 915(不變)/ rwd 4(2→4)/
  m7a 8 / m7b 12 / viewer_ux 14+1skip / app_e2e 1 / compare 8 / conf_range 9 / pin_point 4 /
  focus_object 4 / widget_state_persistence 3 / thumbwall_collapse_recovery 3 / cv_toolbox 4,
  **零 regression**。誠實界線:sidebar 收合功能整個移除(非修好收合),若 User 想要「可收合且
  可靠拉回」需自製浮動展開鈕、另開一輪。
- 2026-07-05 (User 回報「現在收合鈕移除了⋯⋯版面就會一直被佔用,難道沒有辦法解決這個問題、只能
  靠移除收合鈕嗎?」——orchestrator 承認前一輪是繞過問題、非真正解法,重新根因分析 + 修復)
  User 一針見血指出前一輪「移除收合鈕」犧牲了「收合以騰出畫面空間」這個正當需求,只是把
  「拉不回來」的症狀壓下去。**重新根因分析**:展開鈕 `stExpandSidebarButton` 之所以不可見不可點,
  真正兇手是 `[data-testid='stToolbar']{display:none !important;}`(拿掉頂部空白 CSS)——
  展開鈕是 `stToolbar` 的**子元素**,父層 `display:none` 連同子元素一起吃掉,與「header 高度收
  到 0」無關(header 有 `overflow:visible`,子元素本可見)。**修法**:改成只隱藏 `stToolbar`
  裡不需要的子元素(狀態列/部署鈕/主選單),保留展開鈕、`position:fixed` 定位讓它脫離收到 0 高的
  header。**修完仍點不到**——第二個根因:展開鈕的祖先 `stToolbar`/`stHeader` 各自
  `position:relative/absolute` 且 `z-index:999990`,建立獨立堆疊環境;sidebar 本身
  `z-index:999991` 更高,子元素(展開鈕)無論自己設多高的 z-index 都只在祖先的堆疊環境內比較,
  永遠贏不了 sidebar(Playwright 實測:點擊被 `stSidebarContent` 攔截)。**修法**:祖先
  (`stHeader`/`stToolbar`)一起把 z-index 拉到 1000000(蓋過 sidebar 的 999991),展開鈕才真正
  疊在最上層可點。收合鈕「«」與展開鈕都**恢復顯示**,移除前一輪「恆展開鎖寬 300px」的規則——
  收合/展開恢復成 Streamlit 原生行為(真的騰出空間、真的點得回來)。**唯一保留**:窄視窗
  (≤1100/760px)仍維持「強制展開、鎖寬」,這是 07-04 第一輪那個更嚴重 bug(自動收合 + 完全找
  不到任何展開路徑)的專屬防護,不受今天改動影響。
  **意外的深度調查插曲(誠實記錄,非產品 bug)**:Playwright `page.screenshot()`(含 headless
  與 headed 模式)在收合後持續顯示「殘影」——sidebar 區域仍畫出完整 300px 內容,即使
  `getBoundingClientRect()`、`elementFromPoint()` 皆已確認 DOM/hit-testing 100% 正確收合
  (main 內容/iframe 確實補滿空間、可正確互動)。逐步排除:非多個 stSidebar 節點重複、非 CSS
  transition 動畫殘留、非 window.resize 事件未觸發、非缺少真實 Streamlit rerun。最終用
  **PowerShell `System.Drawing.Graphics.CopyFromScreen` 做作業系統層級截圖**(等同真人肉眼所見,
  非經 CDP screenshot API)實證:真實視窗顯示**完全正確**的收合後版面(sidebar 消失、viewer 補滿
  空間),證實「殘影」是 Playwright/CDP screenshot API 在此環境對 iframe-based 自訂元件
  (viewer_component/thumbwall_component)resize 後的合成/截圖快取假象,不影響真實使用者、也
  不影響既有語意層 E2E 斷言(本專案慣例本就不用像素截圖比對,見 2026-07-04「改語意層斷言更
  穩固」的既有裁決)。**記錄此發現供未來測試作者參考**:若日後要對這類 iframe-resize-after-
  collapse 場景寫新 E2E,應信任 `bounding_box()`/`elementFromPoint` 等 DOM 斷言,不要用
  `page.screenshot()` 像素比對驗證此特定互動(已知在此環境會有假陰性)。
  architect 補 20_viewer_workbench_redesign.md §3.11.1 演進註記;PM 改寫 `test_rwd_e2e.py`
  的 AC-sbfix1(舊:斷言收合鈕已隱藏 + 恆展開;新:斷言收合鈕可見可點→點擊後真的收窄 <50px→
  展開鈕可見可點→點擊後恢復 ≥280px)。**對抗驗證**:`git stash` 還原成 07-04 第二輪(收合鈕
  隱藏)的 app.py 重跑新測試,精確重現「收合鈕不可見」失敗(=User 今天的抱怨),stash pop
  修復後轉綠。契約 re-snapshot。**orchestrator 親跑判綠(逐檔)**:單元 915(不變)/ rwd 4
  (改寫後仍 4 條)/ m7a 8 / m7b 12 / viewer_ux 14+1skip / app_e2e 1 / compare 8 / conf_range 9 /
  pin_point 4 / focus_object 4 / widget_state_persistence 3 / thumbwall_collapse_recovery 3 /
  cv_toolbox 4,**零 regression**。
  誠實界線:窄視窗(≤1100/760px)仍不能手動收合(維持鎖寬保護),僅寬視窗恢復收合彈性——
  這是刻意的取捨,非遺漏(見上文「唯一保留」)。
- 2026-07-05 (po 啟動 compare 第四輪 — User:「把原本的資料夾疊圖功能改成是,我在縮圖牆裡面
  標註兩張影像來做疊圖就好(不再需要兩個資料夾)」,取代第三輪 modeldiff 雙 model 覆蓋 triage)
  需求文件 `1_user_needs/07_two_image_mark_overlay_compare.md`。**AskUserQuestion 兩項確認**:
  ①疊圖內容 = 像素疊合(並排/差異/混合)與偵測框疊合(A 藍/B 橘)**兩者都要,可切換**;
  ②現有雙 model 覆蓋率儀表板/分歧佇列**整個移除**,改成新的兩圖疊圖模式。
  **PO 裁決**:`modeldiff.py`/`test_modeldiff.py` 本體保留不刪(31 測試仍計入單元總數、
  `verify/gate.py modeldiff` 仍可判綠)——比照 framecompare/framediff 的既有慣例,只是
  app.py 不再呼叫、未來可回退;真正的新工作是「縮圖牆標記機制」(thumbwall 元件擴充)+
  「疊圖比較視圖」(直接重用已測試的 framecompare 五函式 + overlay.draw,零新純邏輯模組)。
  architect 落 `23_compare.md` §9(取代 §8):
  - **thumbwall 擴充**:`thumbwall_component/index.html` 每格新增第 4 角標 `.cmpmark`(左下角,
    其餘三角已用:corner=左上索引/mark=右上⭐✓/badge=右下偵測數);未標記顯示淡色「○」提示、
    標記後顯示①(藍)/②(橘);點擊用 `stopPropagation()` 隔開,不誤觸整格既有的選取/導覽
    click。`thumbwall.py` 新增 `markable` 參數,回傳值依 markable 分岐(向後相容:
    markable=False 時回傳同舊版 `int|None`;True 時回傳 `{"type":"select"|"mark","index"}`)。
  - **app.py**:移除 sidebar「第二個 model 資料夾 B」欄位、`_item_for` 的
    `detections_b`/`a_present`/`b_present`(連帶唯一呼叫者 `_label_exists` 一併刪除)、
    `_CMP_STATUS`/`_CMP_MODES`、`import modeldiff`;新增 `ss.cmp_marks`(list[str] 存 name,
    最多 2 個、FIFO 踢最舊)+ `_toggle_cmp_mark`;`_render_compare` 全面重寫:標記<2 張時
    提示、標記滿 2 張後可切「像素疊合」(重用 `framecompare.side_by_side/difference/blend`,
    尺寸不同時用既有 `_resize_to` 縮放 B 對齊 A)或「偵測框疊合」(base=`framecompare.blend`
    半透明疊 A/B 各自偵測框,B 框座標依縮放比例換算);主縮圖牆不再因 `compare_on` 隱藏
    (否則進了比較模式就沒地方改標記)。P1 探針 5 個舊 `data-cmp-*` 換成 2 個新的:
    `data-cmp-marks-n`(0/1/2,不論 compare_on 皆回寫)、`data-cmp-view-mode`(pixel/box)。
  - PM 全面改寫 `test_compare_e2e.py`(AC1-AC8:提示狀態/FIFO/視圖切換/像素三模式/
    標記不誤觸導覽/清除標記/向後相容/標記圖示存在)。
  **意外挖到一個真實的既有 bug(非本輪引入,今天才被揭露)**:`thumbwall.py` 的點擊去重計數器
  `thumbwall._last_n` 是**模組層級 Python 全域字典**,不是 per-session——同一 pytest session
  內多個測試各自開新分頁(= 新 Streamlit session)但共用同一伺服器行程,前一個測試累積的點擊
  次數會讓下一個測試「新分頁的第一次點擊」被誤判成舊事件而略過(新分頁 JS 端 `evtN` 從 0 重新
  計數,若全域 `last` 已被前面測試推高,新分頁前幾次點擊的 n 都追不上、被吃掉)。這個缺陷之前
  沒被抓到是因為之前每個檔案通常只有一個測試函式會點同一顆縮圖牆,本輪 8 個測試都重複點同一顆
  `key="thumbwall"` 才第一次把它引出來。**根本修復**(非測試繞道):去重計數器改存進
  `st.session_state`(每個 session 各自獨立),不再用 Python 模組全域狀態。
  **對抗驗證**:`git stash` 還原 app.py/thumbwall.py/thumbwall_component/index.html,8 條新測試
  皆如預期失敗(`.cmpmark` 不存在、`data-cmp-marks-n` 探針不存在、「第二個 model」欄位仍在),
  stash pop 修復後 8 條全綠。契約 re-snapshot。
  **orchestrator 親跑判綠(逐檔)**:單元 915(不變,modeldiff 31 測試仍在、僅 app 不呼叫)/
  compare 8(全面改寫)/ m7a 8 / m7b 12 / viewer_ux 14+1skip / app_e2e 1 / conf_range 9 /
  pin_point 4 / focus_object 4 / widget_state_persistence 3 / thumbwall_collapse_recovery 3 /
  rwd 4 / cv_toolbox 4,**零 regression**。
  誠實界線:像素疊合的並排/差異/混合對「兩張本質不同的照片」在數學上仍然合法但視覺意義因場景
  而異(如同 §8 舊版已有的界線);偵測框疊合的 base canvas 用 50/50 blend(非任一原圖純色),
  純粹作為讓兩張圖都隱約可見的背景,非精確合成;B 的框座標縮放假設 A/B 兩張影像描述同一種
  拍攝視角比例,若兩張影像長寬比差異極大,縮放後框位置的參考價值會降低(未做拉伸失真警示,
  YAGNI,User 未提出此需求)。
- 2026-07-05 (User 版面回饋:「看一下 GUI layout 有沒有可以調整更好的部份」→ 提建議後 User
  裁決「按照你的建議進行調整,不用再問我」,orchestrator 自主落地 + 全程留痕)先提 7 點建議
  (排序列浪費空間、sidebar 利用率低、標題列可合併、導覽鈕/跳頁無提示、信心 slider 過寬、
  比較模式入口不易發現、收合鈕歸屬),再依 User 授權挑「高價值 × 低契約風險」的落地:
  **A(主要,收回垂直空間)**:排序下拉 / 「此信心範圍內符合 N/M 張」/ 收合鈕 原本在窄的左欄裡
  『垂直堆疊三列』、右側大片全空,改成『單一橫向工具列』(排序 | 收合鈕 | 符合張數 caption)——
  收回約兩列高度、主圖上移。仍是獨立於下方會收合的 stage 欄的一列(不隨 `_left_w` 收合變窄),
  故 thumbwall_collapse_recovery 契約(收合後排序寬>40、收合鈕寬>20)照樣成立;實測 bounding_box
  排序 w=180 / 收合鈕 w=168,遠超門檻。§4.l 順序保持:sort_mode selectbox 在收合鈕(會 rerun)
  之前實例化,不會被收合的 rerun 判成孤兒 widget。
  **D(可發現性)**:比較模式 toggle 標籤在已標記時顯示「🔀 比較模式 · 已標記 N/2」——進比較模式前
  就看得到標記進度(仍含『比較模式』子字串,compare E2E 的 filter(has_text) 不受影響)。
  **E(提示)**:頂列跳頁 number_input 加 `help="跳到第幾張(輸入頁碼)"` tooltip(原本 label
  collapsed、無懸停提示)。
  **刻意緩做(交 User 知曉,非遺漏)**:①**B sidebar 縮寬**——會與剛落地的「sidebar 恆展開 + 可
  拖拉調寬」修法(2026-07-05 §側邊欄可收合)衝突:強制縮寬需 `!important` 蓋掉 Streamlit inline
  width,會連帶讓拖拉調寬失效;為保護剛修好的行為,本輪不動 sidebar 寬度(300px 主要浪費在垂直
  空白而非水平,縮 40px 對 viewer 邊際效益低,不值得為此破壞拖拉)。②**C 標題列與 Command Bar
  合併**——兩列各自已是單列且不浪費;硬併成一列會塞 10+ 個控制項(標題/2 toggle/手冊/上一張/
  下一張/跳頁/⭐/信心 slider/類別)過度擁擠,且信心 slider 需要足夠寬度(鍵盤微調可靠性,見
  2026-06-26 歷史坑),擠壓風險 > 省一列的收益。③導覽鈕維持文字(「上一張/下一張」為多個 E2E
  的 button name 錨點,改純圖示會破契約)。
  **契約守恆**:全程未改任何 4_PM_Feedback 既有斷言;信心 slider 留在頂列 Command Bar(main、
  非 sidebar、非 expander,滿足 m7a-AC1/AC5、viewer_ux-AC16)、排序仍在 main 且恆渲染、
  收合鈕仍有「收合縮圖/展開縮圖」文字且收合後不被擠壞。
  **orchestrator 親跑判綠(逐檔)**:單元 915(不變)/ thumbwall_collapse_recovery 3 /
  widget_state_persistence 3 / m7a 8 / m7b 12 / viewer_ux 14+1skip / app_e2e 1 / compare 8 /
  conf_range 9 / pin_point 4 / focus_object 4 / cv_toolbox 4 / rwd 4,**零 regression**。
  截圖實證:排序/收合/符合張數同列橫排、主圖較改前上移約兩列;比較模式 toggle 顯示「已標記 1/2」。
- 2026-07-05 (User「起 Multi agent 逐項確認,都有完成了嗎」→ 用 Workflow 派 7 個代理各自獨立
  讀現行程式碼稽核 7 項建議的實作狀態,再依授權補做安全的缺口)**多代理稽核結論(誠實)**:
  第一輪只 #6 完整完成、#1/#4 部分完成、#2/#3/#5/#7 未做。據此第二輪補做兩項高價值且可驗證者:
  **#2(sidebar 利用率,User 明列『最划算』之一)**:把 🧰 CV 顯示調整工具箱從主舞台『搬進 sidebar』
  (User 原話「工具箱在 sidebar 也符合看圖時順手調」)。用 `st.sidebar.expander(...)`——渲染在
  sidebar 但『程式碼仍在原位執行』(ss.idx 已於上方定案、§4.l 執行順序不變;避免移到 sidebar
  區塊 466 行時 ss.idx〔652 才定案〕尚未就緒的順序陷阱)。效果:主舞台少一整列全寬 expander、
  主圖再上移;原本只有一個資料夾欄、空盪的 sidebar 被填滿。並把工具箱內部由 2/3 欄並排改為
  **單欄垂直堆疊**——實測窄 sidebar 下多欄會使 checkbox 標籤互相重疊,單欄是窄容器的自然版面。
  **#5(信心 slider 過寬)**:Command Bar 的信心 slider 欄權重 3.2→2.6(~46%→~40% 列寬),
  類別欄 1.35→1.5 平衡;**刻意保守**(不砍到 User 建議的 ~1/3≈2.0),留足鍵盤 ArrowRight 微調寬度
  以免重蹈 2026-06-26『slider 太窄單步不可靠』的歷史 flaky。
  **仍刻意不做(交 User 裁決,附硬理由)**:#3 標題列/Command Bar 合併(擠 10+ 控制 + slider 需寬度);
  #7『收合鈕改成縮圖牆頂端的 ◂/▸ 圖示』——**這條若照字面做會主動重新引入 2026-07-04 修過的
  『收合後寬度=0、展開鈕點不到』陷阱**:縮圖牆欄收合時 `_left_w≈0.0001`,任何放進該欄的控制項
  都會被擠成 0 寬;收合鈕正是為此才刻意放在『不隨收合變窄的獨立列』。故字面版有害,維持現狀
  並向 User 說明。#4 導覽鈕維持文字(button name 為多個 E2E 錨點)。
  **契約守恆**:信心 slider 仍在 main Command Bar(非 sidebar、非 expander),工具箱移入 sidebar
  不影響 m7a-AC5/viewer_ux-AC16 對『信心門檻不在 sidebar/expander』的斷言(工具箱標籤是
  亮度/對比/Gamma…,非『信心門檻』);cv_toolbox_e2e 以 get_by_text(位置無關)命中,不受搬移影響。
  **orchestrator 親跑判綠(逐檔,各檔獨立 session 避免跨檔位置記憶污染)**:cv_toolbox 4 / m7a 8 /
  viewer_ux 14+1skip(單跑;三檔同 session 跑時 viewer_ux 的『用起始圖 hover』測試被 m7a 導航到
  idx6 wafer16 污染 → 已知 2026-06-25 跨檔 flake,非本輪回歸)/ 其餘全套逐檔綠、單元 915 不變。
  截圖實證:工具箱在 sidebar 單欄堆疊、標籤不重疊;主舞台已無工具箱列、主圖再上移;信心 slider 變窄。
- 2026-07-05 (po 啟動 M8 — User 指向 `LV/visuallatent` 的多格式標註載入、裁決「全部五種都加」)
  需求 `1_user_needs/08_multi_format_annotations.md`。現況:CV_Viewer 只吃 YOLO `.txt` + 一種 `.json`
  (bbox/xyxy/xywhn);COCO/LabelMe 只在 `cocoio` 匯入匯出路徑、不在主偵測讀取流。LV 的
  `scripts/label_formats.py`(純 stdlib + PIL,已測)自動偵測 5 種:YOLO txt / COCO JSON / Pascal VOC
  XML / LabelMe JSON / NDJSON。User 要複用該實作、不重寫。
  **PO 裁決 / 契約**:
  ① **新增 Tier A 純邏輯模組 `labelfmt`**(port LV `label_formats.py`,依賴僅 stdlib + PIL,同 CV_Viewer
     既有約束)——負責 COCO / VOC / LabelMe / NDJSON 的**自動偵測 + 解析**,並用 app 影像尺寸把 LV 的
     正規化 rows `(cid|None, cx, cy, w, h, score, name|None)` **轉成 CV_Viewer 既有 `Detection` 形狀**
     (`{"bbox":[x,y,w,h]絕對像素 int, "cls":str, "conf":float}`)——不新增資料形狀、下游 overlay/縮圖零改。
  ② **`yolo.py` txt 解析加 seg/OBB 守衛**(契約演進 07_yolo.md):≥7 欄的行視為 segmentation/OBB
     多邊形,一律**跳過**(現況會把前 4 個座標誤讀成 cx cy w h = silent-wrong);偵測框只認 5 欄(GT)
     或 6 欄(pred + conf)。這是 LV `parse_yolo_boxes` 早就有的防呆,補進 CV_Viewer。
  ③ **優先序(app 整合層,不在模組內耦合)**:同一張圖依序試 COCO → VOC → LabelMe → NDJSON
     (labelfmt 統一入口),**任一來源命中就用它**;皆無來源才退回既有 `yolo.load`(.json / .txt)。
     保證同圖不會疊出重複來源的框(User 明列)。
  ④ **cocoio 保留不動**:cocoio = 匯入/匯出(round-trip),labelfmt = 讀取為顯示(auto-detect);
     兩者職責不同、COCO 解析小幅重複可接受(誠實界線,不強行合併以免動 cocoio 契約)。
  排序:architect(26_labelfmt.md + 07 演進)→ pm(test_labelfmt.py + test_yolo seg 新測試)→
  snapshot → pg(labelfmt.py + yolo.py 守衛)→ gate GREEN → app 整合 → E2E 回歸 + 真實多格式 smoke。
- 2026-07-05 (M8 完成 — orchestrator 走完 U-Net 五階段 + 親跑判綠 + 真實 COCO 截圖實證) 依 PO 裁決
  落地多格式標註支援(port 自 LV/visuallatent):
  **architect** `3_Architect_Design/26_labelfmt.md`(21 AC,COCO/VOC/LabelMe/NDJSON 逐項釘死數值,
  canonical box `[8,6,16,12]@64×48` 對五格式同解)+ `07_yolo.md` seg/OBB 守衛演進註記;
  **pm** `4_PM_Feedback/test_labelfmt.py`(23 測試:AC1-21 + adapter/純讀不 mutate/永不拋)+
  `test_yolo.py` 加 3 條 seg/OBB 守衛測試(seg 跳過、OBB 跳過、5/6 欄仍收);
  **pg** `5_PG_Develop/labelfmt.py`(port LV 四解析器 + `_row_to_det` adapter → Detection + 統一入口
  `load_for_image`/`folder_has_annotations`,純 stdlib + PIL、永不拋)+ `yolo.py` `_load_yolo_txt`
  加 `len(parts)>=7` 守衛。**客觀判綠**:`gate.py labelfmt` **GREEN(23)**、`gate.py yolo` **GREEN(52)**,
  契約未竄改(snapshot 於 pm 完成後、pg 動工前重打,pg 只動 5_)。
  **app 整合**:`import labelfmt`;`_detections` 改『先試 `labelfmt.load_for_image`(多格式自動偵測),
  回 None 才退回 `yolo.load`(.json/.txt)』——兩路徑輸出都是 Detection,下游 overlay/縮圖/信心過濾零改;
  sidebar caption 用 `folder_has_annotations` 標示偵測到的格式(優先於 YOLO)。
  **整合 smoke(6 路徑全過)**:COCO(widget 0.77)/ VOC(screw)/ LabelMe(crack)/ NDJSON(SageMaker
  left,top,w,h → dent)各正確畫框;YOLO .txt(混入 seg 行被守衛跳過 → 只留偵測框)+ YOLO .json fallback 皆正常。
  **真實 app Tier B 驗證(截圖 `coco_live.png`)**:live app 指向 COCO 資料夾 → 主 viewer 畫出
  『scratch 0.94』(綠,category_id=3)+『contamination 0.61』(洋紅,category_id=8),類名取自 COCO
  categories、信心取自 score;sidebar 顯示『標註格式:COCO / VOC / LabelMe / NDJSON 自動偵測(優先於 YOLO)』。
  **orchestrator 親跑判綠(逐檔)**:單元 **941**(915 + labelfmt 23 + yolo seg 3)/ app_e2e 1 / m7a 8 /
  viewer_ux 14+1skip / conf_range 9 / m7b 12 / focus_object 4 / pin_point 4 / widget_state 3 /
  thumbwall_collapse 3 / cv_toolbox 4 / rwd 4 / **compare 8(單跑)**,**零 regression**。
  誠實附記:批次跑時 compare_e2e 曾出現 1 failed/7 errors —— 根因是 orchestrator 同時在 live app(8501)
  驅動 COCO 截圖、寫到 repo root 的共享 `.cvr_state.json`,恰在 compare_e2e(8765)session setup 時被
  clobber(基礎設施跨進程共享檔的已知時序脆弱,非本輪程式碼回歸);compare_e2e 單獨重跑 8/8 綠確認。
  誠實界線(交 User):① labelfmt 與 cocoio 的 COCO 解析小幅重複(職責不同:讀取顯示 vs 匯入匯出,
  不強行合併);② segmentation/OBB 的多邊形形狀本身不畫(User 明列不需要),只保證不誤讀成亂框;
  ③ COCO images.width/height 與實際影像不符時以 app 影像尺寸換算(極少數縮放近似,同 yolo xywhn 慣例)。
  `.unet/role` 已清空回維護模式。
