# PRD 增補 02:滾輪縮放定為 Must → 改採 client-side 自訂元件

> `/po` 決策增補(承 `3_Architect_Design/00_feasibility...` 的反向閘門)。不重寫 01,只記這次轉向。

## 決策(PO 裁定)
**「滑鼠滾輪以游標為中心連續縮放」是 MVP 必須(Must)。** 因此 **不採方案 A(伺服器端虛擬視窗)**,
改採 **方案 B/C:client-side 互動的自訂雙向 Streamlit 元件**(縮放引擎可內嵌 OpenSeadragon,或自繪 canvas)。

## 連帶影響(一好一壞,誠實列)
- ✅ **三項降級全部收回**:改 client-side 後,滾輪縮放、hover 顯示座標、鍵盤操作都回到 **Must**
  (00 文件第 7 節的 AC 1/2/3 不再降級)。
- ⚠️ **新增 JS/Node 前端 build**:元件用 React + Streamlit Component API,專案多一個前端子專案與
  build/維護成本;這違反「純 Python」的預設假設,但使用者已明確接受滾輪縮放的代價。
- ⚠️ **M1 變大、最大風險轉移**:新的頭號風險 = 「這個雙向元件能不能做出滾輪縮放 + 把事件
  (點擊座標/值、ROI 框、鍵)傳回 Python」。**動全套 M1 前要先 spike 證明。**

## 仍要釐清的(hover 取值的真相,不要過度樂觀)
瀏覽器只顯示 8-bit。元件端 hover 能即時顯示「顯示用 8-bit 值」很容易;但要顯示**原始 16-bit 真值**,
需讓元件**持有像素資料**(連同影像送進去、在 JS 查值),否則 hover 每次回 Python 查值會卡(rerun 模型)。
→ 列為架構師開放問題。

## M1 重新拆解(取代 01 的 M1)
- **M1a — Viewer 元件可行性 + 核心(新頭號風險,先 spike)**
  - `viewer_component`(Tier B,JS 子專案):載入影像 → 客戶端滾輪縮放/平移/鍵盤;
    透過 `Streamlit.setComponentValue` 回傳 `{view(zoom/center)、click(x,y)、roi boxes、key}`。
- **M1b — 影像管線 + 串接**
  - `imageio`(B):讀 8/16-bit/TIFF/大圖 → 給元件的顯示影像(server 端 window/level→8-bit)+ 保留原始陣列供查真值。
  - `imageset`(B):資料夾→清單、排序、進度、記住位置。
  - `viewport`(A,**角色縮小但保留**):解讀元件回傳的 view/點 → **source 座標與裁切矩形**
    (供取真值、ROI 存檔、case 匯出);live 互動改在元件端,故不再負責 live 渲染。
  - `app`(B):縮圖牆 + 嵌入 viewer_component + 上一/下一/跳號 + 記住位置。

## 新的架構師開放問題(取代/補充 00)
1. **元件技術選型**:OpenSeadragon(deep-zoom,需 tiles)vs 單張影像 client-side zoom(3000² 單張在
   瀏覽器端縮放可行,>~8000² 才需 tiles pipeline)vs 自繪 canvas。定 MVP 用哪個 + 需不需要 tiles。
2. **16-bit**:window/level 在 server 端先做成 8-bit 送元件(簡單,live 調整需重送)vs 送 16-bit 由 JS/WebGL
   處理(可 live 調 + hover 真值,較重)。定 MVP 策略。
3. **事件回傳與持久化**:ROI/verdict/點擊事件如何回 Python 並寫進 sidecar(節流避免每次滑動都 rerun)。
4. **元件的測試/閘門**:JS 元件怎麼納入驗收——元件自身 JS 測試 + 整體 `@pytest.mark.e2e`(playwright 真實滾輪縮放);
   `.unet/gate.json` 可為該模組設 JS 測試命令。

## Appetite
M1 因元件而變大,**先只放行 M1a 的 spike**(證明滾輪縮放 + 事件回傳),通過再排 M1b。
若 spike 顯示成本過高或元件做不出來 → 反向閘門回此處,重新考慮(降級回方案 A,或重新評估「Streamlit 是否適合
這種前端重互動」這個更上游的問題)。
