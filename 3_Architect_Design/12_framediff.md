# 設計:framediff(M4 / Tier A,純邏輯 numpy)

> `/architect` 模組設計。純陣列運算、零 I/O、零 GUI。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死 shape + 具體像素值/遮罩/bbox 清單/行為。
> 上游:`ROADMAP.md`(第 45 行,M4 模組分解;Tier A;相依「—」即無)、決策日誌 2026-06-23(framediff 可選複用已建的 `framecompare.difference`)。
> 職責一句:兩張同形 RGB uint8 影像 A、B 的「進階變化分析」——灰階化後門檻化得變化遮罩、連通變化區邊框、變化率、在 B 上高亮變化區。
> 邊界 sanity:此模組無 I/O、無跨模組契約、無 GUI,可獨立設計與驗收 → **不觸發反向閘門**。

---

## 開工前 sanity check(切分是否成立)

`framediff` 能獨立設計與驗收:輸入是「兩張 RGB uint8 numpy 陣列 A、B」,輸出是「遮罩陣列 / float 變化率 / bbox list / 高亮陣列」,全為無狀態純函式。

- 與 `framecompare` 的界線:`framecompare` 做**逐通道**的視覺比較(side-by-side / difference / blend / swipe / blink),`difference` 回的是 `(H,W,3)` 逐通道絕對差。`framediff` 做**像素層級的「變化/未變化」決策**(灰階化 → 門檻 → 二值遮罩 → 連通元件 → 統計/框/高亮),回的是 `(H,W)` 遮罩、float、bbox list。兩者正交:`framecompare` 是「給人看的合成圖」,`framediff` 是「給人判讀的變化量化與定位」。**不應合併**。
- 複用關係:`framediff` **可選**在內部複用 `framecompare.difference`(逐通道絕對差)再自行灰階化,但**設計不強制**;§2.5 釘死「以何種方式得到灰階差」的契約值,實作可用 framecompare 也可不用,只要產出與 §2.5 一致。本模組**嚴禁** import `yolo`/`sidecar`/`tagging`/`overlay` 等任何業務模組(沿用 M3 解耦慣例;`framecompare` 為同層純 numpy,複用與否皆不破壞解耦)。
- 與 `overlay` 的界線:`overlay` 畫的是「模型 Detection 的 bbox」(資料來自模型);`framediff.highlight` 畫的是「像素變化區的 bbox」(資料來自兩圖差)。資料來源不同、不 import、不重疊。

結論:切分成立,正常進行。

---

## 1. 目的 (Purpose)

提供一組純函式,把「兩張同形 RGB uint8 影像 A、B」的進階變化分析(灰階差門檻化遮罩、變化率、連通變化區 bbox、在 B 上高亮)固定成可預測、可逐像素斷言的陣列轉換,作為 app 變化偵測面板的共用底座。

---

## 2. I/O 契約 (逐字採用,不得更動簽名)

模組:`5_PG_Develop/framediff.py`(實作層,本檔不產出)。僅依賴 `numpy`(以下記為 `np`);**可選**複用同層 `framecompare`(見 §2.5),**嚴禁** import `yolo`/`sidecar`/`tagging`/`overlay`。

```python
import numpy as np

def change_mask(A: np.ndarray, B: np.ndarray, threshold: int = 30) -> np.ndarray:
    # 灰階化 A、B(§2.4 加權公式)→ 逐像素灰階絕對差 → diff > threshold 為「變化」。
    # 回 (H, W) 的 np.uint8 遮罩,值僅 {0, 1}(1=變化)。要求 A.shape == B.shape。
    ...

def change_ratio(A: np.ndarray, B: np.ndarray, threshold: int = 30) -> float:
    # 變化像素數 / 總像素數(總數 = H*W);回 Python float,值域 [0.0, 1.0]。要求 A.shape == B.shape。
    ...

def change_regions(A: np.ndarray, B: np.ndarray, threshold: int = 30,
                   min_area: int = 1, connectivity: int = 4) -> list:
    # 對 change_mask 做 4-連通元件標記(§3.3),每個元件回 [x, y, w, h](絕對像素,左上原點)。
    # 僅保留 area(元件像素數) >= min_area 者。回 list[list[int]],順序見 §3.3。要求 A.shape == B.shape。
    ...

def highlight(A: np.ndarray, B: np.ndarray, threshold: int = 30,
              color=(255, 0, 0), thickness: int = 1) -> np.ndarray:
    # 回 B 的 copy(輸入永不 mutate),在每個 change_regions(預設 min_area=1, connectivity=4) 的 bbox
    # 畫空心外框(§3.4 半開區間 + thickness 向框內加厚,與 overlay 語義一致)。
    # 回 (H, W, 3) uint8,shape 同 B。要求 A.shape == B.shape。
    ...
```

### 2.1 輸入資料形狀(契約值,釘死)
- A、B 皆為 `np.ndarray`,`ndim == 3`,最後一軸為 3(RGB),`dtype == np.uint8`,值域 `0..255`。
- 形狀記法:`A.shape == (H, W, 3)`。`H`=高(列數,row=y)、`W`=寬(欄數,col=x)。索引慣例 `array[row=y, col=x, channel]`(與 overlay/roi 一致)。
- 四個函式皆要求 `A.shape == B.shape`(完全相等);不符 → `raise ValueError`(§4a)。

### 2.2 dtype / 溢位規則(釘死,避免 uint8 wrap-around)
- **所有運算的中間值一律先升精度再轉回 uint8**,嚴禁直接對 uint8 做 `A - B`(會 wrap)。
- 灰階化(§2.4)與灰階差(§2.5)一律在 `int`/`float` 精度上算,最後門檻比較產生 `{0,1}` uint8 遮罩。

### 2.3 回傳型別(釘死)
- `change_mask` → `np.ndarray`,`dtype == np.uint8`,`shape == (H, W)`(**二維**,不含通道軸),值 ∈ `{0, 1}`。
- `change_ratio` → 內建 `float`(`isinstance(r, float) == True`;非 `np.float64`,以 `float(...)` 包一層),值域 `[0.0, 1.0]`。
- `change_regions` → `list`,元素為 `list[int]` 形如 `[x, y, w, h]`,四值皆 Python `int`,皆 `>= 0`,且 `w >= 1`、`h >= 1`(每個被保留的元件至少 1 像素,故 bbox 寬高至少 1)。
- `highlight` → `np.ndarray`,`dtype == np.uint8`,`shape == (H, W, 3)`。

### 2.4 灰階化公式(釘死,避免實作各自為政)
- 採 **ITU-R BT.601 luma 加權**,係數固定:`gray = 0.299*R + 0.587*G + 0.114*B`(R=channel0、G=channel1、B=channel2)。
- 計算在 `float64` 上做(`A.astype(np.float64)`),**不**在灰階階段取整(取整只在最終門檻比較前,見 §2.5)。
- 之所以選加權而非三通道平均:與業界(OpenCV `COLOR_RGB2GRAY`、PIL `L` 模式)一致,對人眼亮度更忠實;此為契約值,**禁止**改三通道算術平均(`(R+G+B)/3`),因其與本 AC 釘值不一致。

### 2.5 灰階差與門檻(釘死,二值化規則)
1. `gA = 0.299*A_R + 0.587*A_G + 0.114*A_B`(float64,§2.4);`gB` 同理。
2. `d = np.abs(gA - gB)`(float64 逐像素灰階絕對差,值域 `0.0..255.0`)。**不**先取整。
3. 二值化:`mask = (d > threshold)`。**用嚴格大於 `>`,不是 `>=`**(契約值;`d` 恰等於 `threshold` 視為「未變化」)。
4. `mask.astype(np.uint8)` → 值 ∈ `{0, 1}`。
- > 註:`d` 與 `threshold` 在 `float` 域比較;`threshold` 為 int(預設 30),比較時自動升 float。`change_ratio` 與 `change_regions` 內部皆以**同一個** `change_mask(A,B,threshold)` 為唯一變化定義(三者必然一致,不得各算各的)。

### 2.6 連通性與 min_area(釘死)
- `connectivity` 預設 **4**(上下左右四鄰;**不含**對角)。本版**只支援 `connectivity == 4`**;傳入非 4 之值 → `raise ValueError`(§4e)。(8-連通列為未來擴充,本輪不做,避免 AC 因對角歧義變脆。)
- `min_area` 為「元件像素數(該元件 mask==1 的像素總數,非 bbox 面積)」的**下限(含)**:保留 `area >= min_area` 者。預設 `min_area == 1`(保留所有非空元件)。`min_area <= 0` 等效於 `min_area == 1`(無元件 area 會 < 1,因最小元件即 1 像素);為明確起見契約規定 `min_area < 1` 一律當 `1` 處理,**不**拋例外。

### 2.7 highlight 繪製語義(釘死,與 overlay 對齊)
- 先算 `regions = change_regions(A, B, threshold, min_area=1, connectivity=4)`。
- `out = B.copy()`;對每個 `[x,y,w,h]` 畫**空心**外框(`thickness=1` 時僅最外圈一像素):
  - 半開區間:框覆蓋像素 `x <= col < x+w` 且 `y <= row < y+h`;外框四邊 = `row==y`(上)、`row==y+h-1`(下)、`col==x`(左)、`col==x+w-1`(右)。
  - `thickness` 向**框內**加厚:粗細 `t` 表外框內縮 `0..t-1` 圈皆塗色;`t >= min(w,h)` → 整框實心填滿;`t <= 0` → 不畫任何像素。
  - 座標夾界:bbox 必在影像內(由 change_regions 產生,天然 `0 <= x, x+w <= W`、`0 <= y, y+h <= H`),故無夾界需求;但實作仍以 overlay 同款夾界寫法防禦。
  - 顏色 = `color`(長度 3 序列,(R,G,B),0..255 int),寫成 `out[row, col, :] = color`。
- 回 `out`(新陣列,`out is not B`,`B` 逐像素不變)。

---

## 3. 資料流 (Data Flow)

### 3.1 `change_mask(A, B, threshold=30) -> np.ndarray`
1. `A.shape != B.shape` → `raise ValueError`。
2. `gA, gB ← 加權灰階(§2.4,float64)`。
3. `d = np.abs(gA - gB)`(float64,(H,W))。
4. `mask = (d > threshold).astype(np.uint8)`(§2.5,嚴格 `>`)。
5. 回 `mask`,shape `(H, W)`,值 ∈ `{0,1}`。
- **metamorphic**:`change_mask(A, A)` 全 0(`d≡0`,`0 > threshold` 恆 False,threshold>=0);`change_mask(A,B) == change_mask(B,A)`(`|gA-gB|==|gB-gA|`,逐元素相等)。

### 3.2 `change_ratio(A, B, threshold=30) -> float`
1. `A.shape != B.shape` → `raise ValueError`。
2. `m = change_mask(A, B, threshold)`(共用 §3.1 定義)。
3. 回 `float(int(m.sum()) / (H * W))`。`H*W` 恒 `>= 1`(契約假設非空影像)。
- 值域:`m.sum() ∈ [0, H*W]` → ratio ∈ `[0.0, 1.0]`。
- **metamorphic**:`change_ratio(A, A) == 0.0`(全 0 遮罩);`change_ratio(A,B) == change_ratio(B,A)`(對稱);**門檻單調**:`t1 <= t2` ⇒ `change_ratio(A,B,t1) >= change_ratio(A,B,t2)`(門檻越高、`d>t` 的像素越少,變化率單調不增)。

### 3.3 `change_regions(A, B, threshold=30, min_area=1, connectivity=4) -> list`
1. `A.shape != B.shape` → `raise ValueError`;`connectivity != 4` → `raise ValueError`。
2. `m = change_mask(A, B, threshold)`(共用 §3.1 定義,`(H,W)` uint8 {0,1})。
3. **連通元件標記(演算法釘死,確保可逐元件斷言)**:
   - **掃描順序**:雙重迴圈 `for y in range(H): for x in range(W):`(列優先,row 由上而下、col 由左而右)。
   - 對每個尚未標記且 `m[y,x] == 1` 的像素,以它為**種子**做 **iterative flood fill(顯式 stack/queue,4-鄰)**,收集整個連通元件。
   - **元件被「發現」的順序** = 種子像素在上述掃描順序中**首次被遇到**的順序(即元件依其「最上最左」像素的 raster 位置排序;等價於依 `(min_y_of_first_seed, x_of_first_seed)` 的掃描序,亦即依各元件第一個被掃到的像素位置遞增)。
   - 4-鄰定義:`(y-1,x),(y+1,x),(y,x-1),(y,x+1)`,須在影像內且 `m==1` 且未標記。
4. 對每個元件,計其 `area`(該元件像素數)與 bbox:
   - `min_x, max_x, min_y, max_y` 跨該元件所有像素;`bbox = [min_x, min_y, max_x - min_x + 1, max_y - min_y + 1]`(即 `[x, y, w, h]`,半開寬高,皆 Python int)。
5. **過濾**:僅保留 `area >= max(min_area, 1)` 者(§2.6;`min_area<1` 當 1)。
6. 依 §3.3-3 的「發現順序」回 `list[[x,y,w,h], ...]`。空遮罩 → 回 `[]`。
- > 釘死的小遮罩 → 確切 region 清單見 AC15(像素級可斷言)。
- **metamorphic**:`change_regions(A, A) == []`(全 0 遮罩無元件);`min_area` 單調:`min_area` 越大,保留的元件數越少(子集關係,過濾單調)。

### 3.4 `highlight(A, B, threshold=30, color=(255,0,0), thickness=1) -> np.ndarray`
1. `A.shape != B.shape` → `raise ValueError`。
2. `regions = change_regions(A, B, threshold, min_area=1, connectivity=4)`。
3. `out = B.copy()`;對每個 `[x,y,w,h]` 依 §2.7 畫空心外框(thickness 向內加厚、半開區間)。
4. 回 `out`,shape `(H,W,3)`,`out is not B`,`B` 不被 mutate。
- 端點:無變化(`A==B` 或門檻濾光)→ `regions==[]` → `out` 逐像素等於 `B`(只 copy 不畫)。

---

## 4. 邊界條件與錯誤處理

a. **形狀不符**:四個函式皆 `A.shape != B.shape` → `ValueError`(信任 dtype/ndim 契約,但形狀必檢,否則 broadcast 出無意義結果)。
b. **`A == B`(逐像素相等)**:`d≡0` → `change_mask` 全 0、`change_ratio == 0.0`、`change_regions == []`、`highlight` 回 `B.copy()`(逐像素等於 B)。
c. **threshold 邊界**:
   - `threshold` 為 int(預設 30);允許 `0`(此時任何 `d>0` 的像素皆算變化)與大值(`>= 255` ⇒ `d` 最大 255,`d>255` 恆 False ⇒ 全 0 遮罩、ratio 0.0、regions []);**不**對 threshold 上下限拋例外(任意非負 int 合法;負 threshold 亦不拋,`d>=0 > 負` 恆 True ⇒ 全 1 遮罩,語義自洽)。
   - **門檻單調性(metamorphic,§3.2)**:`change_ratio` 對 threshold 單調不增。
d. **`min_area` 邊界**:`min_area < 1` 當作 `1`(§2.6,不拋例外);`min_area` 大於任何元件 area ⇒ 回 `[]`。
e. **`connectivity` 邊界**:僅 `4` 合法;其他值(含 8)→ `ValueError`(本輪不支援 8-連通)。
f. **`thickness <= 0`(highlight)**:不畫任何框,`out` 逐像素等於 `B`(仍回新 copy,`out is not B`)。
g. **不 mutate 輸入**:四函式皆**不得**修改傳入的 A、B。`change_mask`/`change_ratio` 不寫輸入;`change_regions` 只讀 mask;`highlight` 以 `B.copy()` 起手。
h. **dtype/ndim 假設**:Tier A 純邏輯,信任契約假設 `(H,W,3) uint8`,不做額外 dtype 防禦(形狀相等檢查與 connectivity 檢查除外)。`color` 各分量假設 0..255 int。
i. **空間退化**:契約假設 `H>=1, W>=1`(非空影像);`change_ratio` 分母 `H*W>=1`,不會除零。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以合成小陣列釘死)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_framediff.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import framediff`)。
> 共用合成陣列(供下列 AC 引用):
> ```python
> import numpy as np
> # 2x2x3 純色:A 全 10、B 全 200(灰階差 = |10-200| = 190 > 30 → 全變化)
> A10  = np.full((2, 2, 3), 10,  dtype=np.uint8)
> B200 = np.full((2, 2, 3), 200, dtype=np.uint8)
> ```
> 灰階加權對純灰(R=G=B=v)像素:`0.299v+0.587v+0.114v = v`(係數和 == 1.0),故純色像素灰階 == 該值,差 == 兩值之差(下列 AC 多用純灰陣列以便心算)。

**dtype / 形狀基本契約**
- **AC1**:`framediff.change_mask(A10, B200).dtype == np.uint8` 且 `.shape == (2, 2)`(二維、無通道軸)。
- **AC2**:`framediff.change_mask(A10, B200)` 的值集合 ⊆ `{0, 1}` —— `set(np.unique(framediff.change_mask(A10, B200)).tolist()).issubset({0, 1}) == True`。
- **AC3**:`isinstance(framediff.change_ratio(A10, B200), float) == True`(回內建 float,非 np.float64)。
- **AC4**:`framediff.highlight(A10, B200).dtype == np.uint8` 且 `.shape == (2, 2, 3)`。

**change_mask — 門檻語義 / 嚴格大於 / 灰階加權 / 自差 / 對稱**
- **AC5**:全變化 —— `np.array_equal(framediff.change_mask(A10, B200), np.ones((2,2), np.uint8))`(灰階差 190 > 30,全 1)。
- **AC6**:自差全 0 —— `np.array_equal(framediff.change_mask(A10, A10), np.zeros((2,2), np.uint8))`(metamorphic 釘死)。
- **AC7**:對稱 —— `np.array_equal(framediff.change_mask(A10, B200), framediff.change_mask(B200, A10))`(`|gA-gB|==|gB-gA|`)。
- **AC8**:嚴格大於門檻(`>` 非 `>=`)—— 對 `P = np.full((1,1,3), 100, np.uint8)`、`Q = np.full((1,1,3), 130, np.uint8)`,灰階差恰 `30`;`change_mask(P, Q, threshold=30)[0,0] == 0`(`30 > 30` 為 False,未變化),但 `change_mask(P, Q, threshold=29)[0,0] == 1`(`30 > 29` 為 True)。
- **AC9**:灰階加權(非三通道平均)釘死 —— 對 `R0 = np.zeros((1,1,3), np.uint8)`(純黑,灰階 0)與 `G255 = np.array([[[0,255,0]]], np.uint8)`(純綠,灰階 `0.587*255 = 149.685`),`change_mask(R0, G255, threshold=100)[0,0] == 1`(差 ≈149.7 > 100)且 `change_mask(R0, G255, threshold=150)[0,0] == 0`(149.7 > 150 為 False)。若改用三通道平均(綠灰階 = 255/3 = 85)則 threshold=100 會得 0,故此 AC 可區辨灰階公式。
- **AC10**:閾值上界 —— `np.array_equal(change_mask(A10, B200, threshold=255), np.zeros((2,2), np.uint8))`(差 190,`190 > 255` 恆 False → 全 0)。

**change_ratio — 值域 / 自差 0 / 對稱 / 門檻單調 / 部分變化釘值**
- **AC11**:全變化 ratio == 1.0 —— `framediff.change_ratio(A10, B200) == 1.0`。
- **AC12**:自差 ratio == 0.0 —— `framediff.change_ratio(A10, A10) == 0.0`(metamorphic 釘死,內建 float 比較)。
- **AC13**:對稱 —— `framediff.change_ratio(A10, B200) == framediff.change_ratio(B200, A10)`。
- **AC14**:部分變化釘值 —— 設 `A = np.zeros((1,4,3), np.uint8)`(4 像素全 0)、`B = np.zeros((1,4,3), np.uint8)`;令 `B[0,0]=B[0,1]=(200,200,200)`(前 2 欄純灰 200、後 2 欄仍 0)。則 `change_ratio(A, B, threshold=30) == 0.5`(4 像素中 2 個變化,2/4)。
- **AC15(門檻單調,metamorphic)**:對任給上述 `A,B`(AC14),`change_ratio(A,B,10) >= change_ratio(A,B,100) >= change_ratio(A,B,255)`(門檻越高、變化率單調不增);具體 `change_ratio(A,B,10)==0.5`、`change_ratio(A,B,255)==0.0`。

**change_regions — 連通元件像素級釘死(核心)**
> 連通遮罩構造(以差值控制 mask):底圖 `A = np.zeros((4,5,3), np.uint8)`;`B = np.zeros((4,5,3), np.uint8)`,
> 然後把下列「變化像素」設成純灰 200(`B[y,x] = (200,200,200)`),其餘為 0,`threshold=30`。
> 變化遮罩(1=變化)固定為:
> ```
> col:  0 1 2 3 4
> row0: 1 1 0 0 1
> row1: 1 0 0 0 1
> row2: 0 0 1 0 0
> row3: 0 0 1 1 0
> ```
> 即 `B` 在座標(以 (y,x) 記)`(0,0),(0,1),(1,0),(0,4),(1,4),(2,2),(3,2),(3,3)` 設為 200。
> 4-連通下三個元件:① `{(0,0),(0,1),(1,0)}` ② `{(0,4),(1,4)}` ③ `{(2,2),(3,2),(3,3)}`。
> bbox `[x,y,w,h]`:① x∈[0,1] y∈[0,1] → `[0,0,2,2]`;② x=4 y∈[0,1] → `[4,0,1,2]`;③ x∈[2,3] y∈[2,3] → `[2,2,2,2]`。
> 發現順序(raster):①(種子(0,0))→②(種子(0,4))→③(種子(2,2))。
- **AC16(三元件、順序、bbox 全釘)**:對上述 `A,B`,`framediff.change_regions(A, B, threshold=30) == [[0,0,2,2],[4,0,1,2],[2,2,2,2]]`(順序與每個 bbox 逐值釘死)。
- **AC17(4-連通不含對角)**:對角相鄰不連通 —— `A = np.zeros((2,2,3), np.uint8)`、`B = np.zeros((2,2,3), np.uint8)`,`B[0,0]=B[1,1]=(200,200,200)`(只有對角兩像素變化)。`change_regions(A,B,threshold=30)` 回**兩個**元件(非一個):結果為 `[[0,0,1,1],[1,1,1,1]]`(發現順序 (0,0) 先於 (1,1);各為 1×1 框)。此 AC 可區辨 4-連通 vs 8-連通(8-連通會合成 1 個 `[0,0,2,2]`)。
- **AC18(min_area 過濾)**:沿用 AC16 的 `A,B`。元件像素數為 ①3、②2、③3。`change_regions(A,B,threshold=30,min_area=3) == [[0,0,2,2],[2,2,2,2]]`(濾掉 area=2 的元件②,保留 area>=3 的①③,保序)。
- **AC19(min_area 邊界含等於)**:`change_regions(A,B,threshold=30,min_area=2)` 仍含全部三元件 `[[0,0,2,2],[4,0,1,2],[2,2,2,2]]`(`area>=2` 三者皆滿足,`2>=2` 保留)。
- **AC20(自差無元件)**:`framediff.change_regions(A10, A10) == []`(全 0 遮罩,metamorphic)。
- **AC21(全變化單一元件)**:`framediff.change_regions(A10, B200, threshold=30) == [[0,0,2,2]]`(2×2 全變化 → 一個涵蓋全圖的 bbox)。
- **AC22(connectivity 非 4 拋例外)**:`framediff.change_regions(A10, B200, connectivity=8)` 觸發 `pytest.raises(ValueError)`(本輪僅支援 4-連通)。
- **AC23(回傳型別)**:AC16 結果中每個 bbox 的四個元素皆為 Python `int`(`all(isinstance(v, int) for r in regions for v in r) == True`),且每 `w>=1, h>=1`。

**highlight — 不 mutate / 畫框 / 無變化 / thickness / 形狀**
> 設 `A = np.zeros((4,5,3), np.uint8)`、`B` 同 AC16 構造(三變化元件),`color=(255,0,0)`、`thickness=1`。
- **AC24(回新陣列、不 mutate)**:`out = framediff.highlight(A, B, threshold=30)`;`out is not B` 且 `np.array_equal(B, <呼叫前的 B 副本>) == True`(B 逐像素不變)。
- **AC25(框邊像素被塗)**:沿用 AC24,元件③ bbox=[2,2,2,2](半開:左 col=2、右 col=3、上 row=2、下 row=3)。`out[2,2].tolist() == [255,0,0]`(左上角)且 `out[3,3].tolist() == [255,0,0]`(右下角)。
- **AC26(無變化 → 等於 B)**:`np.array_equal(framediff.highlight(A10, A10, threshold=30), A10) == True`(自差無框,只 copy;且回傳 `is not A10`)。
- **AC27(thickness<=0 不畫)**:`np.array_equal(framediff.highlight(A, B, threshold=30, color=(255,0,0), thickness=0), B) == True`(thickness 0 → 不畫任何框,逐像素等於 B)。
- **AC28(形狀/型別)**:`out.shape == (4,5,3)` 且 `out.dtype == np.uint8`。
- **AC29(color 生效)**:用 `color=(0,0,255)` 重畫,元件③左上 `framediff.highlight(A, B, threshold=30, color=(0,0,255))[2,2].tolist() == [0,0,255]`(顏色契約生效)。

**錯誤路徑 — 形狀不符四函式皆拋**
- **AC30**:`framediff.change_mask(np.zeros((2,2,3),np.uint8), np.zeros((2,3,3),np.uint8))` 觸發 `pytest.raises(ValueError)`。
- **AC31**:`framediff.change_ratio(np.zeros((2,2,3),np.uint8), np.zeros((3,2,3),np.uint8))` 觸發 `pytest.raises(ValueError)`。
- **AC32**:`framediff.change_regions(np.zeros((2,2,3),np.uint8), np.zeros((2,2,4),np.uint8))` 觸發 `pytest.raises(ValueError)`(末軸不符亦算 shape 不等)。
- **AC33**:`framediff.highlight(np.zeros((2,2,3),np.uint8), np.zeros((4,2,3),np.uint8))` 觸發 `pytest.raises(ValueError)`。

**跨函式一致性(三者共用同一變化定義)**
- **AC34**:`change_mask` 的 1 像素數 == `change_ratio * H * W` —— 對 AC14 的 `A,B`,`int(framediff.change_mask(A,B,30).sum()) == round(framediff.change_ratio(A,B,30) * 1 * 4) == 2`(遮罩與變化率由同一定義導出,彼此一致)。
- **AC35**:`change_regions` 涵蓋的變化像素數總和 == `change_mask.sum()` —— 對 AC16 的 `A,B`,三元件像素數 `3+2+3 == 8 == int(framediff.change_mask(A,B,30).sum())`(連通元件不漏不重)。

---

## 6. 與其他模組的邊界(防越權)
- **不負責** 影像載入 / 解碼 / 色彩轉換 / dtype 轉換(那是 `imgio`);本模組吃已就緒的 `(H,W,3)` uint8 RGB。
- **不負責** 兩圖的視覺合成(side-by-side/blend/swipe/blink)與逐通道絕對差(那是 `framecompare`);本模組做的是像素層級「變化/未變化」決策、變化率、連通變化區定位與高亮。**可選**複用 `framecompare.difference` 取逐通道差,但灰階化與門檻化為本模組契約(§2.4/§2.5)。
- **不負責** 模型 Detection 的 bbox 繪製(那是 `overlay`);`highlight` 畫的是「像素變化區」框,資料來源是兩圖差,不是模型。
- **不負責** 任何 GUI / Streamlit 元件 / 輪播計時 / 持久化 / I/O / 排序 / 篩選。
- 本模組對外承諾:純函式、無副作用、**輸入陣列不被 mutate**、僅依賴 `numpy`(可選同層 `framecompare`)、**零 import 任何業務模組(yolo/sidecar/tagging/overlay)**,可獨立平行驗收。
