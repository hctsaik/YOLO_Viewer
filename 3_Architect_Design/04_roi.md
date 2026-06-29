# 技術設計:`roi` — ROI 框幾何(Tier A,純邏輯)

> `/architect` 階段產物。對應 PRD `2_PO_PRD/01` §3 M2 的 `roi` 模組、`ROADMAP.md`「roi / A / M2」。
> 模組粒度。**只含純幾何(numpy),零 I/O、零 GUI、無跨模組契約。**
> 下游:`/pm` 依本檔 Acceptance Criteria 落成 `4_PM_Feedback/test_roi.py`;`/pg` 依 I/O 契約實作 `5_PG_Develop/roi.py`。

---

## 開工前 sanity check(切分是否成立)

`roi` 能獨立設計與驗收:它是一組**無狀態純函式**,輸入/輸出都是整數 tuple 與 numpy 陣列,
不依賴 `imageio`、`viewport`、`sidecar`。職責一句話可講完:「ROI 框的正規化、夾界、裁切與座標換算」。

- 與 `viewport` 的界線:`viewport` 負責 display↔source 座標換算(縮放/平移幾何);`roi` 只在
  **已是 source 座標** 的前提下做框運算。兩者不重疊、不成環,**不應合併**。
- 與 `sidecar` 的界線:`sidecar` 負責「一圖多 ROI 的 JSON 讀寫(不改原圖)」;ROI 的序列化由 sidecar
  持有,`roi` 只提供幾何原語。**不需在此再拆**。

結論:切分成立,正常進行,**不觸發反向閘門**。

---

## 1. 目的 (Purpose)

提供 ROI 矩形框的純幾何原語:正規化、夾到影像邊界、裁切像素、面積、點命中測試、與 xyxy 互轉;
所有運算以整數 `(x, y, w, h)` 為唯一框格式,座標系為**影像 source 像素座標**(原點左上、x 向右、y 向下)。

---

## 2. I/O 契約 (I/O Contract)

模組:`5_PG_Develop/roi.py`(實作層,本檔不產出)。僅依賴 `numpy` 與 Python 標準庫。

### 2.1 型別與資料結構

- **Box**:長度 4 的 tuple `(x, y, w, h)`,四個元素皆為 Python `int`。
  - `(x, y)` = 左上角;`w` = 寬(向右);`h` = 高(向下)。
  - 採**半開區間**語義:框覆蓋的像素為 `x <= px < x+w` 且 `y <= py < y+h`。
  - **不變量(normalize/clamp/from_xyxy 的輸出保證)**:`w >= 0`、`h >= 0`、四元素為 `int`。
- **array**:`numpy.ndarray`,形狀 `(H, W)`(灰階)或 `(H, W, C)`(多通道);索引慣例 `array[row=y, col=x]`。

### 2.2 函式簽名(逐字採用,不得更動)

純幾何(numpy)。box 一律 (x,y,w,h) 整數。

```python
def normalize(x, y, w, h) -> (x, y, w, h):   # w/h 轉正、整數
    ...

def clamp_box(box, img_w, img_h) -> (x, y, w, h):
    ...

def crop(array, box) -> np.ndarray:
    ...

def area(box) -> int:
    ...

def contains(box, x, y) -> bool:
    ...

def to_xyxy(box) -> (x1, y1, x2, y2):
    ...

def from_xyxy(x1, y1, x2, y2) -> box:
    ...
```

### 2.3 各函式語義(精確定義)

| 函式 | 輸入 | 輸出 | 語義 |
|------|------|------|------|
| `normalize(x,y,w,h)` | 四個數值(可為負、可為 float) | `(x,y,w,h)` int,`w>=0,h>=0` | 把可能反向(負寬/負高)的框轉成左上角原點 + 正寬高的標準框,並轉 int。 |
| `clamp_box(box, img_w, img_h)` | 一個 box、影像寬高 int | `(x,y,w,h)` int,落在 `[0,img_w]×[0,img_h]` 內 | 先 normalize,再把框夾到影像範圍;完全在界外 → 退化為 `w` 或 `h` = 0(空交集)。 |
| `crop(array, box)` | ndarray、box | ndarray(原陣列的 slice/view) | 回 `array[y:y+h, x:x+w]`;空框 → 對應軸長度為 0 的陣列。 |
| `area(box)` | box | int | `w * h`;空框 → `0`。 |
| `contains(box, x, y)` | box、查詢點 int | bool | 半開區間命中:`x_box <= x < x_box+w and y_box <= y < y_box+h`。 |
| `to_xyxy(box)` | box | `(x1,y1,x2,y2)` int | `(x, y, x+w, y+h)`;`x2/y2` 為**排除端點**(exclusive)。 |
| `from_xyxy(x1,y1,x2,y2)` | 兩角點 | `(x,y,w,h)` int | 由兩角點建框,內部走 normalize,允許 x2<x1 / y2<y1。 |

### 2.4 數值轉換規則(釘死,消除歧義)

- **int 轉換**:一律使用 Python `int()`(向 0 截斷)。例:`int(2.9)==2`、`int(-2.9)==-2`。
  - `normalize`/`from_xyxy`:**先**對端點/寬高做幾何(取絕對值、相加),再 `int()`,確保輸出皆 int。
  - `clamp_box`:輸入若非 int,先 normalize(含 int 化)再夾界。
- **normalize 的反向處理**:
  - 若 `w < 0`:`x ← x + w`(左上角左移)、`w ← -w`。
  - 若 `h < 0`:`y ← y + h`(左上角上移)、`h ← -h`。
- **clamp_box 夾界算法**(用 xyxy 夾,避免先夾 x 再算 w 的偏差):
  1. `(x,y,w,h) = normalize(box)`
  2. `x1,y1,x2,y2 = x, y, x+w, y+h`
  3. `x1 = min(max(x1, 0), img_w)`;`x2 = min(max(x2, 0), img_w)`
  4. `y1 = min(max(y1, 0), img_h)`;`y2 = min(max(y2, 0), img_h)`
  5. 回 `(x1, y1, x2 - x1, y2 - y1)`(`x2>=x1`、`y2>=y1` 必成立,故 w,h >= 0)。

---

## 3. 資料流 (Data Flow)

```
使用者在 viewer 拖出兩角點 (display 座標)
        │  (由 viewport 換成 source 座標 — 不在本模組)
        ▼
from_xyxy(x1,y1,x2,y2)  ──► 標準 box (x,y,w,h)            ← 建框,容許任意拖曳方向
        │
        ▼
clamp_box(box, img_w, img_h) ──► 夾到影像內的 box          ← 不超界
        │                            │
        │                            ├─► area(box) ──► int   (空交集→0,UI 可判定無效框)
        │                            ├─► contains(box, x, y) ──► bool  (點是否落在 ROI 內)
        │                            └─► to_xyxy(box) ──► xyxy  (匯出 / 與外部格式互轉)
        ▼
crop(source_array, box) ──► np.ndarray 子陣列              ← 供 ROI crop 匯出 / 預覽
```

- 框格式在模組內外**全程為 `(x,y,w,h)` 整數**;`to_xyxy`/`from_xyxy` 僅為與兩角點/外部格式的轉接點。
- `crop` 不複製資料語義不被本契約要求(回 view 或 copy 皆可),但**形狀必須**為 `(h, w)` 或 `(h, w, C)`。
- 純函式、無狀態、無副作用:不修改輸入陣列、不寫檔、不依賴全域狀態。

---

## 4. 邊界條件與錯誤處理 (Edge Cases & Error Handling)

| 情境 | 規則 | 預期結果 |
|------|------|----------|
| 負寬 / 負高 | `normalize` 轉正並移動左上角 | `normalize(10,20,-4,-6)==(6,14,4,6)` |
| float 輸入 | `int()` 截斷(向 0) | `normalize(0.0,0.0,5.9,5.9)==(0,0,5,5)` |
| 框部分超界 | `clamp_box` 夾右下與左上 | 見 AC6 |
| 框完全在界外 | `clamp_box` 退化為空交集(w 或 h = 0) | `area==0` |
| 零寬 / 零高框 | 視為空框,合法、不報錯 | `area==0`;`crop` 回 0 大小陣列 |
| 空交集 crop | 對應軸 slice 長度 0 | `crop(a, (5,5,0,0)).shape == (0,0)`(灰階);多通道保留 C 軸 |
| 點在框邊界 | 半開:含左/上界、排除右/下界 | 見 AC8 |
| `img_w`/`img_h` = 0 | 合法;整個影像為空 | clamp 後 `area==0` |

錯誤處理原則(Tier A,純邏輯):
- **不**自行吞錯;不接受非數值型別的防禦性轉換(契約假設呼叫端傳數值/合法 ndarray)。
- 不對「點命中」以外的情況丟自訂例外;非法型別由 Python 原生例外冒出即可(契約不要求自訂錯誤訊息)。
- 無外部服務 / 無非同步 / 無瀏覽器解碼 → GUI/整合/外部編解碼/非同步 AC 強制清單**不適用**本模組。

---

## 5. Acceptance Criteria(可被 pytest 驗,帶具體期望值)

> 全部為釘死數值 / 行為斷言。`/pm` 落成 `4_PM_Feedback/test_roi.py`,每條測試註記對應 `# ACn`。
> 測試直接 `import roi`(conftest 已把 `5_PG_Develop` 加入 `sys.path`)。

### normalize

- **AC1**(寬高已正,僅轉 int 型別):
  `roi.normalize(45, 105, 30, 150) == (45, 105, 30, 150)`,且回傳 tuple 四元素皆為 `int` 型別
  (`all(isinstance(v, int) for v in roi.normalize(45, 105, 30, 150))` 為 `True`)。
- **AC2**(負寬 + 負高 → 轉正並移動原點):
  `roi.normalize(10, 20, -4, -6) == (6, 14, 4, 6)`。
- **AC3**(單軸負寬;float 截斷向 0):
  `roi.normalize(0.0, 0.0, -5.9, 5.9) == (-5, 0, 5, 5)`
  (x = int(0 + (-5.9)) 經反向處理:先 0+(-5.9)=-5.9→ -5;w=int(5.9)=5;h=int(5.9)=5)。
  並補一條純截斷:`roi.normalize(2.9, 2.9, 5.9, 5.9) == (2, 2, 5, 5)`。

### area

- **AC4**(一般面積):`roi.area((45, 105, 30, 150)) == 4500`。
- **AC5**(空框面積為 0):`roi.area((45, 105, 0, 150)) == 0` 且 `roi.area((45, 105, 30, 0)) == 0`。

### clamp_box

- **AC6**(右下超界,夾到影像內):
  `roi.clamp_box((90, 90, 50, 50), 100, 100) == (90, 90, 10, 10)`。
- **AC7a**(完全在界外 → 空交集 w=0):
  `roi.clamp_box((200, 10, 30, 30), 100, 100) == (100, 10, 0, 30)`,且 `roi.area(...) == 0`。
- **AC7b**(左上負座標被夾;同時驗證先 normalize):
  `roi.clamp_box((-10, -10, 50, 50), 100, 100) == (0, 0, 40, 40)`。
- **AC7c**(負寬框先 normalize 再夾):
  `roi.clamp_box((50, 50, -100, -100), 100, 100) == (0, 0, 50, 50)`
  (normalize→(-50,-50,100,100),夾後左上補到 0、右下保 50)。

### contains(半開區間)

- **AC8a**(框內點為 True):`roi.contains((10, 10, 20, 20), 15, 15) is True`。
- **AC8b**(含左/上界):`roi.contains((10, 10, 20, 20), 10, 10) is True`。
- **AC8c**(排除右/下界):`roi.contains((10, 10, 20, 20), 30, 30) is False`
  且 `roi.contains((10, 10, 20, 20), 29, 29) is True`。
- **AC8d**(界外點為 False):`roi.contains((10, 10, 20, 20), 9, 15) is False`。
- **AC8e**(空框永不命中):`roi.contains((10, 10, 0, 0), 10, 10) is False`。

### to_xyxy / from_xyxy

- **AC9**(to_xyxy 為 x+w, y+h,右下端點 exclusive):
  `roi.to_xyxy((45, 105, 30, 150)) == (45, 105, 75, 255)`。
- **AC10**(from_xyxy 正常兩角點):
  `roi.from_xyxy(45, 105, 75, 255) == (45, 105, 30, 150)`。
- **AC11**(from_xyxy 容許反向角點 → 走 normalize):
  `roi.from_xyxy(75, 255, 45, 105) == (45, 105, 30, 150)`。
- **AC12**(round-trip 恆等):對 `b = (45, 105, 30, 150)`,
  `roi.from_xyxy(*roi.to_xyxy(b)) == b`。

### crop

- **AC13**(灰階一般裁切;形狀與內容):
  令 `a = np.arange(100, dtype=np.uint8).reshape(10, 10)`,
  `roi.crop(a, (2, 3, 4, 5)).shape == (5, 4)`(注意:shape 為 (h, w)),
  且 `roi.crop(a, (2, 3, 4, 5))[0, 0] == a[3, 2]`(== 32),
  且 `np.array_equal(roi.crop(a, (2, 3, 4, 5)), a[3:8, 2:6])` 為 `True`。
- **AC14**(多通道保留通道軸):
  令 `a = np.zeros((10, 10, 3), dtype=np.uint8)`,
  `roi.crop(a, (1, 1, 4, 6)).shape == (6, 4, 3)`。
- **AC15**(空框 → 0 大小陣列,灰階):
  令 `a = np.zeros((10, 10), dtype=np.uint8)`,
  `roi.crop(a, (5, 5, 0, 0)).shape == (0, 0)` 且 `roi.crop(a, (5, 5, 0, 0)).size == 0`。
- **AC16**(空交集 box 經 clamp 後 crop → 0 大小;多通道保留 C):
  令 `a = np.zeros((10, 10, 3), dtype=np.uint8)`,`b = roi.clamp_box((200, 5, 4, 4), 10, 10)`,
  則 `roi.area(b) == 0` 且 `roi.crop(a, b).size == 0`,`roi.crop(a, b).shape[2] == 3`。
- **AC17**(crop 不修改輸入陣列):
  令 `a = np.arange(100, dtype=np.uint8).reshape(10, 10)`,`a0 = a.copy()`,
  呼叫 `roi.crop(a, (2, 3, 4, 5))` 後 `np.array_equal(a, a0)` 為 `True`。

### 整合(管線串接)

- **AC18**(from_xyxy → clamp → area → crop 串接一致):
  令 `a = np.arange(100, dtype=np.uint8).reshape(10, 10)`,
  `b = roi.clamp_box(roi.from_xyxy(8, 8, 14, 14), 10, 10)`,
  則 `b == (8, 8, 2, 2)`、`roi.area(b) == 4`、`roi.crop(a, b).shape == (2, 2)`。

---

## 6. 給 `/pm` 與 `/pg` 的備註

- 共 **7 個函式**:`normalize` / `clamp_box` / `crop` / `area` / `contains` / `to_xyxy` / `from_xyxy`。
- 共 **18 條 AC**(AC1–AC18;AC3、AC7、AC8 含子項,合計約 28 個獨立斷言點)。
- Tier A:`gate.py` 只跑單元(`4_PM_Feedback/test_roi.py`),**無 E2E**。
- 測試指令(逐字):
  `cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_roi.py -p no:cacheprovider --strict-markers -q`
- 不可新增任何 pip 依賴;僅用 `numpy` + 標準庫。
- 完成本檔後**停下等人審查**,審查通過才放行 `/pm`。
