# 可行性評估:Streamlit 大圖 / 16-bit / TIFF 的互動檢視(PRD 開放問題 1+2)

> `/architect` 風險評估(非模組設計)。結論會**反向閘門回 PO 調整幾條 AC**(見最後一節)。
> 附微型 spike 實測數字為據。

## 1. 目的
回答 PRD 開放問題 1、2:Streamlit 能不能順暢地對 3000×3000 / 16-bit / TIFF 做 zoom/pan、
滾輪定點縮放、即時 pixel 值、鍵盤操作?若不能完全做到,MVP 該採什麼策略、哪幾條 AC 要調。

## 2. Streamlit 的硬限制(誠實列出)
- **rerun 模型**:每次 widget 互動會把整個 script 從頭重跑;狀態要存在 `st.session_state`。
- **`st.image` 會把「整張」影像送到瀏覽器**。實測 3000² 16-bit→PNG:**952 ms / 8.8 MB / 每次互動**(不可用)。
- **核心 Streamlit 沒有滑鼠滾輪 / 滑鼠移動 / 鍵盤事件**。
  - 取座標:需元件(如 `streamlit-image-coordinates`,給**點擊**座標,非 hover)。
  - 鍵盤:核心不支援全域快捷鍵;需自訂元件,或退而用畫面按鈕。

## 3. 候選方案
| 方案 | 做法 | 優 | 缺 |
|------|------|----|----|
| **A. 伺服器端 virtual viewport(MVP 推薦)** | Python 持有全解析度陣列;zoom/pan/center 存 session_state;**每次只把「可視區裁切 + 降採樣到固定顯示尺寸(~1000px)」**用 `st.image` 顯示;座標用 `streamlit-image-coordinates`(點擊),縮放用按鈕/滑桿/點擊定點,ROI 用兩點或 `streamlit-drawable-canvas` | 純 Streamlit + 1 個現成元件,**無自訂 JS build**;每次互動 **68 ms / 629 KB**,與源圖大小脫鉤;`viewport` 維持純幾何、好測 | 縮放是「點擊定點 + 按鈕」,**非連續滑鼠滾輪**;座標/值是**點擊**顯示,非 hover 連續 |
| B. 內嵌 client-side deep-zoom(OpenSeadragon via `components.html` + tiles) | 影像切成 image pyramid tiles,瀏覽器端真‧滑鼠滾輪縮放/平移 | 縮放體驗最好、客戶端流暢 | 要先把每張圖切 tiles;**把 ROI/座標/判定傳回 Python 需雙向自訂元件**(build 成本) |
| C. 全自訂 React 雙向元件 | 自己寫元件,滾輪縮放 + 事件回傳全包 | 最高擬真 | build/維護成本最高,非 MVP |
| D. `st.image(整張)` | 直接丟全圖 | 最簡單 | 實測 952ms/8.8MB,**否決** |

## 4. Spike 實測(本機,3000×3000 16-bit gray)
| 策略 | 每次互動 | 傳輸量 |
|------|---------|--------|
| 整張 PNG(= st.image full / 方案 D) | 952 ms | 8 804 KB |
| **可視區裁切 + 降採樣(方案 A)** | **68 ms** | **629 KB** |
| 縮圖(contact sheet 每格,需快取) | 124 ms | 13 KB |
> A 對 D:時間 0.07×、傳輸 0.071×。**虛擬視窗讓互動成本與源圖尺寸脫鉤**;NEAREST 降採樣保留 pixel 邊界(可看 pixel)。

## 5. 推薦:MVP 採方案 A(伺服器端 virtual viewport)
理由:用純 Streamlit + 一個現成元件就打中真正的 jobs(看 pixel / 座標 / 值、ROI 放大、大圖不卡),
不必自訂 JS;且把渲染策略與 `viewport` 純幾何模組解耦——**滾輪要不要、之後要不要升級到方案 B,
都不必動 viewport**。保留日後換 B 的路。

## 6. 對 M1 模組契約的影響
- **`viewport`(Tier A,不變且更被坐實)**:給定 `(src_w, src_h, zoom, center_xy, disp_w, disp_h)` →
  回 `可視源裁切矩形`、`display↔source 座標轉換`、`點擊 display 點 → source (x,y)`、`minimap 視窗矩形`。
  純幾何、零 I/O,正是 virtual viewport 需要的核心;高度可測。
- **`imageio`(Tier B)**:需提供 `load→(全解析度 ndarray, dtype/bit深, size)`、
  `to_display_8bit(arr, window/level|auto)`、以及「便宜地裁切源矩形」(numpy slice)。
  16-bit→8-bit 用 window/level 或 auto-normalize(預設見開放問題 3)。
- **`app`(Tier B)**:渲染採 virtual viewport 迴圈;事件層用 `streamlit-image-coordinates`(點擊取座標)
  + 按鈕/滑桿/快捷鍵元件(縮放與導覽)。新增相依:`streamlit-image-coordinates`(+ 可能 `streamlit-drawable-canvas`)。

## 7. 反向閘門:建議 PO 調整這幾條 AC(因 Streamlit 限制)
1. ~~「滾輪以游標為中心連續縮放」~~ → **「點擊定點縮放 + Fit/100/200/400/800 縮放鈕/快捷鍵(以點擊點為中心)」**。
   真‧滑鼠滾輪縮放列入 **Phase 2(方案 B)**。
2. ~~「游標處**即時(hover)**顯示 (x,y) 與 RGB/Gray」~~ → **「**點擊**顯示該點 (x,y) 與值」**(hover 連續顯示需自訂元件,Phase 2)。
3. 「全程鍵盤操作」 → **「上一/下一/標記等主導覽用按鈕 + 盡量提供鍵盤元件」**(完整全域快捷鍵視元件可行性,可能部分入 Phase 2)。
4. 「開資料夾 3 秒內看到縮圖牆」 → 維持,但**註明縮圖需快取**(首次建縮圖有成本,之後即時)。

其餘 MVP AC(ROI 框選+crop、上一/下一、blink/側邊/差分比較、YOLO overlay、CSV/JSON 匯出)在方案 A 下無虞。

## 8. 待 PO 裁決
- 接受上述 AC 調整(採方案 A)→ 即可放行設計 M1 `viewport` / `imageio` / `app`。
- 若「真‧滑鼠滾輪縮放」是 MVP 必須 → 改採方案 B/C,成本與時程上升(需 tiles pipeline + 雙向元件),
  請 PO 重排 appetite。
