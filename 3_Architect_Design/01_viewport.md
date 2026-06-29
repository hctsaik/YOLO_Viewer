# 設計:`viewport`(Tier A,純幾何,零 I/O)

> `/architect` 產物。模組分解見 `2_PO_PRD/01` 第 3 節 M1;渲染策略背景見 `3_Architect_Design/00` 第 6 節
> 與 `2_PO_PRD/03`。本文件**只定義契約與可驗收的數值行為**,不含任何實作(.py)。
> 下游:`/pm` 把第 6 節 AC 落成 `4_PM_Feedback/test_viewport.py`;`/pg` 在 `5_PG_Develop/viewport.py` 實作到全綠。

---

## 1. 目的 (Purpose)
為「virtual viewport」提供全部縮放/平移/座標換算的**純幾何核心**:給定來源影像尺寸、zoom、來源座標中心與顯示尺寸,算出可視來源裁切矩形、display↔source 座標互換、以及縮圖上的視窗矩形——零 I/O、與影像位元深/檔案格式完全脫鉤。

---

## 2. 名詞與座標系約定 (Conventions) — 釘死語義,AC 由此推導

- **來源座標系 (source)**:像素座標,原點 `(0,0)` 在左上;x 向右、y 向下;有效範圍 `0 ≤ x ≤ src_w`、`0 ≤ y ≤ src_h`(右/下界為連續座標的開區間上限,矩形可貼齊到 `src_w`/`src_h`)。
- **顯示座標系 (display)**:送進前端的固定畫布像素,範圍 `[0, disp_w] × [0, disp_h]`。
- **zoom**:顯示像素 / 來源像素 的比值。`zoom = 2.0` ⇒ 1 來源像素佔 2 顯示像素(放大)。
- **可視來源寬高**:在某 zoom 下,整個顯示畫布對應的來源區域大小為
  `view_w = disp_w / zoom`、`view_h = disp_h / zoom`(浮點)。
- **rect 結構**:四元組 `(x0, y0, w, h)`,皆為 **int**;`(x0,y0)` 為可視來源矩形左上角(來源座標),`w,h` 為其寬高(來源像素)。本模組所有回傳 rect 的函式輸出**整數**且**clamp 在影像內**(`0 ≤ x0`、`x0+w ≤ src_w`、`y0 ≥ 0`、`y0+h ≤ src_h`)。
- **不依賴任何外部函式庫**:純 Python 算術(`int`/`float`/`min`/`max`/`round`/`math`)。numpy/PIL/cv2 皆**不得** import(此模組刻意保持零依賴,以利秒級單元測試)。

---

## 3. I/O 契約 (逐字採用,不得更動簽名)

```python
def fit_zoom(src_w, src_h, disp_w, disp_h) -> float:
    """整張圖 fit 進顯示框的 zoom = min(disp_w/src_w, disp_h/src_h)。"""

def clamp(v, lo, hi):
    """把 v 夾在 [lo, hi];回傳型別同 v(int 進 int 出、float 進 float 出)。"""

def crop_rect(src_w, src_h, zoom, cx, cy, disp_w, disp_h) -> tuple:
    """zoom 下、以來源座標 (cx,cy) 為中心的可視來源矩形 (x0,y0,w,h)。
    整數;clamp 在影像內;中心超界由內部 clamp 修正。"""

def display_to_source(dx, dy, rect, disp_w, disp_h) -> tuple:
    """顯示像素 (dx,dy) → 來源座標 (sx,sy)。rect 為 crop_rect 的輸出。"""

def minimap_rect(src_w, src_h, rect) -> tuple:
    """可視矩形 rect 在縮圖上的相對比例 (rx,ry,rw,rh),每個值 ∈ [0,1]。"""
```

- 型別:`src_w, src_h, disp_w, disp_h` 接受 int/float(內部以數值運算);`zoom, cx, cy, dx, dy` 為數值;`rect` 為 `(int,int,int,int)`。
- 回傳:`fit_zoom`→`float`;`clamp`→同輸入型別;`crop_rect`→`(int,int,int,int)`;`display_to_source`→`(float,float)`;`minimap_rect`→`(float,float,float,float)`。

---

## 4. 資料流 (Data Flow)

```
app(session_state: zoom, center=(cx,cy)) ─┐
                                          ├─ fit_zoom ── 初始 zoom(整張 fit)
src_w,src_h,disp_w,disp_h ────────────────┘
        │
        ▼
   crop_rect(...) ──► rect=(x0,y0,w,h)  ──► imageio.crop(源 ndarray[y0:y0+h, x0:x0+w]) → 降採樣到 disp ──► 前端畫布
        │                          │
        │                          └──► minimap_rect(src_w,src_h,rect) ──► 縮圖上畫紅框 (rx,ry,rw,rh)
        ▼
 使用者點擊 display(dx,dy)
        │
        ▼
 display_to_source(dx,dy,rect,disp_w,disp_h) ──► source(sx,sy) ──► imageio 取真值 / ROI 存檔 / 匯出
```

- 本模組是**無狀態純函式集**;zoom 與 center 由 `app` 存在 `st.session_state`,每幀傳入。
- `crop_rect` 與 `display_to_source` 構成往返閉環:對 display 上任一點先 `display_to_source` 取得 source 點,該點必落在 `crop_rect` 回傳矩形內(見 AC9)。
- `clamp` 為共用工具,供 `crop_rect` 內部與 `app` 約束 zoom/center 使用。

---

## 5. 邊界條件與錯誤處理 (Boundaries & Errors)

| 情境 | 行為 |
|------|------|
| `zoom <= 0` | `crop_rect` 拋 `ValueError` |
| `disp_w <= 0` 或 `disp_h <= 0` | `fit_zoom` / `crop_rect` / `display_to_source` 拋 `ValueError` |
| `src_w <= 0` 或 `src_h <= 0` | `fit_zoom` / `crop_rect` / `minimap_rect` 拋 `ValueError` |
| 中心 `(cx,cy)` 超出影像 | **不報錯**;`crop_rect` 內部把矩形平移夾回影像內(優先保持 `w,h`,平移左上角) |
| 可視來源大小 `view_w/view_h ≥ src_w/src_h`(zoom 太小,整圖都看得到) | `w,h` clamp 為 `src_w,src_h`,`x0=y0=0`(整張圖,不溢出) |
| `clamp` 的 `lo > hi` | 未定義輸入,不需特別處理(呼叫端保證 `lo ≤ hi`);不在 AC 範圍 |
| `minimap_rect` 收到合法 rect(已 clamp 在影像內) | 各比例必 ∈ [0,1] |

**整數化規則(釘死,讓 AC 可重現)**:
- `view_w = disp_w / zoom`、`view_h = disp_h / zoom`。
- 期望寬高 `w = clamp(round(view_w), 1, src_w)`、`h = clamp(round(view_h), 1, src_h)`(至少 1px;不超過影像)。
- 期望左上角(未夾)`x0 = round(cx - w/2)`、`y0 = round(cy - h/2)`。
- **平移夾回**(保寬高):`x0 = clamp(x0, 0, src_w - w)`、`y0 = clamp(y0, 0, src_h - h)`。
- 結果保證 `0 ≤ x0`、`x0 + w ≤ src_w`、`0 ≤ y0`、`y0 + h ≤ src_h`,且 `w,h ≥ 1`。
- `round` 採 Python 內建 `round`(banker's rounding);下方 AC 的數值已依此規則挑選為**無歧義**(非 .5 邊界),不受 rounding 模式影響。

---

## 6. Acceptance Criteria(條列、釘死數值、可被 pytest 驗)

> 約定:rect = `(x0,y0,w,h)`。除非標明,浮點比較用 `pytest.approx`(預設容差),整數用 `==`。
> 測試直接 `import viewport`(conftest 已把 `5_PG_Develop` 加進 sys.path)。

### fit_zoom
- **AC1**:`fit_zoom(1000, 500, 800, 800) == approx(0.8)`(受限於寬:`800/1000`)。
- **AC2**:`fit_zoom(500, 1000, 800, 800) == approx(0.8)`(受限於高:`800/1000`)。
- **AC3**:`fit_zoom(100, 100, 300, 300) == approx(3.0)`(小圖放大填滿)。
- **AC4**:`fit_zoom(2000, 1000, 1000, 1000) == approx(0.5)`(寬主導)。

### clamp
- **AC5**:`clamp(5, 0, 10) == 5`、`clamp(-3, 0, 10) == 0`、`clamp(99, 0, 10) == 10`。
- **AC6**:`clamp(2.5, 0.0, 1.0) == approx(1.0)` 且 `isinstance(clamp(2.5, 0.0, 1.0), float)`;`isinstance(clamp(5, 0, 10), int)`(型別保真:int 進 int 出,float 進 float 出)。

### crop_rect — 基本與置中
- **AC7**:整圖可見(zoom=1、disp≥src):`crop_rect(1000, 800, 1.0, 500, 400, 1000, 800) == (0, 0, 1000, 800)`。
- **AC8**:置中放大 zoom=2、disp=400×400 ⇒ view=200×200,中心 (500,400):
  `crop_rect(1000, 800, 2.0, 500, 400, 400, 400) == (400, 300, 200, 200)`。

### crop_rect — display↔source 往返閉環
- **AC9(往返一致)**:令 `rect = crop_rect(1000, 800, 2.0, 500, 400, 400, 400)`(= AC8 的 `(400,300,200,200)`),
  則 `display_to_source(0, 0, rect, 400, 400) == approx((400.0, 300.0))`(左上角對左上角)、
  `display_to_source(400, 400, rect, 400, 400) == approx((600.0, 500.0))`(右下角對 `x0+w, y0+h`)、
  `display_to_source(200, 200, rect, 400, 400) == approx((500.0, 400.0))`(畫布中心 = 來源中心 `(cx,cy)`)。

### crop_rect — 中心超界平移夾回(不報錯、保寬高)
- **AC10(左上越界)**:中心 (0,0)、zoom=2、disp=400×400 ⇒ 期望 200×200 但左上被夾:
  `crop_rect(1000, 800, 2.0, 0, 0, 400, 400) == (0, 0, 200, 200)`。
- **AC11(右下越界)**:中心 (1000,800)、同上:
  `crop_rect(1000, 800, 2.0, 1000, 800, 400, 400) == (800, 600, 200, 200)`(`x0=1000-200`,`y0=800-200`)。
- **AC12(不變式:永遠在影像內)**:對任意 `cx∈{-500,0,250,500,1500}`、`cy∈{-200,0,400,2000}`,
  令 `(x0,y0,w,h)=crop_rect(1000,800,2.0,cx,cy,400,400)`,則恆有
  `x0>=0 and y0>=0 and x0+w<=1000 and y0+h<=800 and w>=1 and h>=1`。

### crop_rect — zoom 太小時整圖且不溢出
- **AC13**:zoom=0.5(view=800×800 > src 寬 400)時 clamp 為整圖:
  `crop_rect(400, 600, 0.5, 200, 300, 400, 400) == (0, 0, 400, 600)`。

### crop_rect — 邊界錯誤
- **AC14**:`crop_rect(1000, 800, 0, 500, 400, 400, 400)` 拋 `ValueError`(zoom=0);
  `crop_rect(1000, 800, -1.0, 500, 400, 400, 400)` 拋 `ValueError`(zoom<0)。
- **AC15**:`crop_rect(1000, 800, 2.0, 500, 400, 0, 400)` 拋 `ValueError`(disp_w=0);
  `crop_rect(0, 800, 2.0, 500, 400, 400, 400)` 拋 `ValueError`(src_w=0)。

### fit_zoom / minimap_rect — 邊界錯誤
- **AC16**:`fit_zoom(0, 800, 400, 400)` 拋 `ValueError`;`fit_zoom(1000, 800, 0, 400)` 拋 `ValueError`。
- **AC17**:`minimap_rect(0, 800, (0,0,10,10))` 拋 `ValueError`(src_w=0);`minimap_rect(1000, 0, (0,0,10,10))` 拋 `ValueError`(src_h=0)。

### display_to_source — 線性映射與邊界錯誤
- **AC18(線性內插)**:`rect=(400,300,200,200)`,`display_to_source(100, 50, rect, 400, 400) == approx((450.0, 325.0))`
  (`sx = 400 + 100/400*200 = 450`、`sy = 300 + 50/400*200 = 325`)。
- **AC19**:`display_to_source(10, 10, (0,0,100,100), 0, 100)` 拋 `ValueError`(disp_w=0,避免除零)。

### minimap_rect — 相對比例 ∈ [0,1]
- **AC20**:`minimap_rect(1000, 800, (400, 300, 200, 200)) == approx((0.4, 0.375, 0.2, 0.25))`
  (`rx=400/1000, ry=300/800, rw=200/1000, rh=200/800`)。
- **AC21**:整圖矩形 → 全幅比例:`minimap_rect(1000, 800, (0, 0, 1000, 800)) == approx((0.0, 0.0, 1.0, 1.0))`。
- **AC22(不變式:比例皆在 [0,1])**:對 AC20 的回傳 `(rx,ry,rw,rh)`,恆有
  `0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0 and 0.0 <= rw <= 1.0 and 0.0 <= rh <= 1.0`
  且 `rx+rw <= 1.0 and ry+rh <= 1.0`(視窗不超出縮圖)。

### 整合不變式(跨函式,坐實 virtual viewport)
- **AC23(crop→minimap 一致)**:令 `rect=crop_rect(1000,800,2.0,500,400,400,400)`,
  `minimap_rect(1000,800,rect) == approx((0.4, 0.375, 0.2, 0.25))`(= AC20,確認 crop 的輸出餵給 minimap 自洽)。
- **AC24(fit→crop 看到整張)**:令 `z=fit_zoom(1000,800,400,400)`(=0.4),
  `crop_rect(1000,800,z,500,400,400,400) == (0,0,1000,800)`(以 fit zoom 裁切恰好涵蓋整張圖、不溢出)。

---

## 7. 給 `/pm` 的測試指引
- 測試檔:`4_PM_Feedback/test_viewport.py`;`import viewport`。
- 執行:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_viewport.py -p no:cacheprovider --strict-markers -q`。
- 錯誤路徑用 `pytest.raises(ValueError)`;浮點用 `pytest.approx`;rect 整數用 `==`。
- AC12 / AC22 為**不變式型**(對一組輸入掃描斷言),其餘為釘死數值;無 e2e(本模組純幾何,不需瀏覽器/App)。

## 8. 非目標 (Non-Goals)
- 不做影像讀取、解碼、window/level、降採樣(屬 `imageio`)。
- 不持有 zoom/center 狀態(屬 `app` 的 session_state)。
- 不處理 ROI 框語義或 crop 匯出(屬 `roi`)。
- 不產生前端 JS / OpenSeadragon 互動(屬 `viewer_component`)。
