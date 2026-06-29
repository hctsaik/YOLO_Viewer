# 設計:framecompare(M3 / Tier A,純邏輯 numpy)

> `/architect` 模組設計。純陣列運算、零 I/O、零 GUI、**不 import 任何業務模組**。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死 shape + 具體像素值/行為。
> 上游:`ROADMAP.md`(第 36 行,M3 模組分解;Tier A;相依「—」即無)。職責一句:兩張同形 RGB uint8 影像 A、B 的比較運算(side-by-side / difference / blend / swipe / blink)。
> 邊界 sanity:此模組無 I/O、無跨模組契約、無 GUI,可獨立設計與驗收 → 不需退回 `/po`。

---

## 1. 目的 (Purpose)

提供一組純函式,把「兩張同形 RGB uint8 影像 A、B」的五種視覺比較運算(水平併接、絕對差、α 混合、垂直擦除分割、閃爍序列)固定成可預測、可斷言的陣列轉換,作為 app 比較面板的共用底座。

---

## 2. I/O 契約 (逐字採用,不得更動簽名)

純邏輯、無 I/O。僅依賴 `numpy`(以下記為 `np`)。**不得 import** `imgio`/`sidecar`/`overlay` 等任何業務模組。

```python
import numpy as np

def side_by_side(A: np.ndarray, B: np.ndarray, gap: int = 0, gap_color=(0, 0, 0)) -> np.ndarray:
    # 水平併接 A | gap | B;輸出 shape = (H, wA + gap + wB, 3),dtype=uint8。要求 hA == hB。
    ...

def difference(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    # 逐像素絕對差 |A - B|,dtype=uint8;要求 A.shape == B.shape。
    ...

def blend(A: np.ndarray, B: np.ndarray, alpha: float) -> np.ndarray:
    # (1-alpha)*A + alpha*B,四捨五入後轉 uint8;要求 A.shape == B.shape、0.0 <= alpha <= 1.0。
    ...

def swipe(A: np.ndarray, B: np.ndarray, x: int) -> np.ndarray:
    # 左 x 欄取 A、其餘(欄 index >= x)取 B;要求 A.shape == B.shape、0 <= x <= W。
    ...

def blink_sequence(A: np.ndarray, B: np.ndarray) -> list:
    # 回 [A, B](供 app 輪播);要求 A.shape == B.shape。
    ...
```

### 2.1 輸入資料形狀(契約值,釘死)
- A、B 皆為 `np.ndarray`,`ndim == 3`,最後一軸為 3(RGB),`dtype == np.uint8`,值域 `0..255`。
- 形狀記法:`A.shape == (H, W, 3)`。`H`=高(列數)、`W`=寬(欄數)。
- `side_by_side` 之外的函式皆要求 `A.shape == B.shape`(完全相等)。
- `side_by_side` 只要求 `hA == hB`(高相等);寬可不同。

### 2.2 dtype / 溢位規則(釘死,避免 uint8 wrap-around)
- **所有運算的中間值一律先升精度再轉回 uint8**,嚴禁直接對 uint8 做 `A - B`(會 wrap)。
  - `difference`:以 `np.abs(A.astype(np.int16) - B.astype(np.int16)).astype(np.uint8)` 計算(差值 ∈ `0..255`,轉 uint8 不截斷)。
  - `blend`:以 `float` 計算 `(1-alpha)*A + alpha*B`,經**四捨五入**後 `.astype(np.uint8)`(見 §2.3 round 規則);結果值域 `0..255`,不需額外 clip(凸組合不會越界)。
- `side_by_side` / `swipe` / `blink_sequence` 僅做切片/併接/裝箱,值不變、dtype 維持 uint8。

### 2.3 round 規則(blend,釘死)
- 採用 **round-half-away-from-zero**(一般四捨五入,`.5` 進位)。實作以 `np.floor(value + 0.5)` 達成(value 非負,故等同 round-half-up)。
  - 例:`100.5 → 101`、`5.0 → 5`、`12.4 → 12`、`12.5 → 13`。
- 此規則為契約;**禁止**改用 `np.rint`/`np.round`(round-half-to-even,`12.5→12`、`13.5→14`),因其在 `.5` 處與本契約不一致。

### 2.4 gap_color 形狀(side_by_side)
- `gap_color` 為長度 3 的序列(tuple/list),元素 ∈ `0..255`,套用到 gap 區塊全部 H 列、全部 3 通道。

---

## 3. 資料流 (Data Flow)

### 3.1 `side_by_side(A, B, gap=0, gap_color=(0,0,0)) -> np.ndarray`
1. 取 `hA, wA = A.shape[:2]`、`hB, wB = B.shape[:2]`。
2. `hA != hB` → `raise ValueError`(高度不等不可併接)。
3. `gap < 0` → `raise ValueError`。
4. 配置輸出 `out = np.empty((hA, wA + gap + wB, 3), dtype=np.uint8)`。
5. `out[:, 0:wA] = A`;若 `gap > 0`,`out[:, wA:wA+gap] = gap_color`(broadcast 到 (H,gap,3));`out[:, wA+gap:] = B`。
6. 回 `out`。輸出寬精確為 `wA + gap + wB`。

### 3.2 `difference(A, B) -> np.ndarray`
1. `A.shape != B.shape` → `raise ValueError`。
2. 回 `np.abs(A.astype(np.int16) - B.astype(np.int16)).astype(np.uint8)`,shape 同輸入。
- **metamorphic**:`difference(A, A)` 全 0;`difference(A, B) == difference(B, A)`(`|A-B|==|B-A|`,逐元素相等)。

### 3.3 `blend(A, B, alpha) -> np.ndarray`
1. `A.shape != B.shape` → `raise ValueError`。
2. `alpha < 0.0 or alpha > 1.0` → `raise ValueError`。
3. `val = (1.0 - alpha) * A.astype(np.float64) + alpha * B.astype(np.float64)`。
4. 回 `np.floor(val + 0.5).astype(np.uint8)`(§2.3),shape 同輸入。
- 端點:`alpha == 0.0` → 逐元素等於 A;`alpha == 1.0` → 逐元素等於 B(浮點 `1.0*x` 對整數 x 精確,round 後還原)。

### 3.4 `swipe(A, B, x) -> np.ndarray`
1. `A.shape != B.shape` → `raise ValueError`。
2. 取 `W = A.shape[1]`;`x < 0 or x > W` → `raise ValueError`。
3. `out = B.copy()`;`out[:, 0:x] = A[:, 0:x]`;回 `out`。
- 語義:**欄 index `< x` 取 A,欄 index `>= x` 取 B**。`x == 0` → 全 B;`x == W` → 全 A。輸出 shape 同輸入,不 mutate A/B。

### 3.5 `blink_sequence(A, B) -> list`
1. `A.shape != B.shape` → `raise ValueError`。
2. 回 `[A, B]`(長度 2 的 list;元素為原陣列物件參照,不複製、不變更)。

---

## 4. 邊界條件與錯誤處理

a. **形狀不符**:
   - `side_by_side`:`hA != hB` → `ValueError`(寬不同合法)。
   - `difference` / `blend` / `swipe` / `blink_sequence`:`A.shape != B.shape` → `ValueError`。
b. **`gap` 邊界**:`gap == 0` → 無分隔欄,輸出寬 `wA + wB`;`gap < 0` → `ValueError`;`gap > 0` → 中間 `gap` 欄填 `gap_color`。
c. **`alpha` 邊界**:`alpha ∈ [0.0, 1.0]` 合法,端點含;超出 → `ValueError`。`alpha == 0.5` 走 §2.3 四捨五入。
d. **`x` 邊界**:`x ∈ [0, W]` 合法,`x == 0`(全 B)與 `x == W`(全 A)為合法端點;`x < 0` 或 `x > W` → `ValueError`。
e. **uint8 溢位**:嚴禁直接對 uint8 相減/相加;一律升精度(§2.2)。`difference` 差值天然 ∈ `0..255`;`blend` 凸組合天然 ∈ `0..255`,故皆無需額外 clip。
f. **不 mutate 輸入**:所有函式**不得**修改傳入的 A、B 內容。`swipe` 以 `B.copy()` 起手;`side_by_side`/`difference`/`blend` 配置新陣列;`blink_sequence` 雖回傳原參照(不複製)但自身不寫入。
g. **dtype 假設**:契約假設 A、B 為 uint8 RGB(§2.1);Tier A 純邏輯,信任契約,不對 dtype/ndim 做額外防禦(形狀相等檢查除外,因錯誤靜默會 broadcast 出無意義結果)。
h. **`blink_sequence` 不複製**:回傳 `[A, B]` 的元素即原物件(`out[0] is A`、`out[1] is B`),語義為「輪播這兩張」,不負責防呼叫端後續變更。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以合成小陣列釘死)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_framecompare.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import framecompare`)。
> 共用合成陣列(供下列 AC 引用):
> ```python
> import numpy as np
> # 2x2x3,純色:A 全 10、B 全 20
> A10 = np.full((2, 2, 3), 10, dtype=np.uint8)
> B20 = np.full((2, 2, 3), 20, dtype=np.uint8)
> ```

**dtype / 形狀基本契約**
- **AC1**:`framecompare.difference(A10, B20).dtype == np.uint8` 且 `.shape == (2, 2, 3)`(回 uint8、shape 不變)。
- **AC2**:`framecompare.blend(A10, B20, 0.5).dtype == np.uint8` 且 `.shape == (2, 2, 3)`。

**side_by_side — 寬度 / 內容 / gap / 錯誤**
- **AC3**:對 `A = np.zeros((2, 3, 3), np.uint8)`、`B = np.zeros((2, 4, 3), np.uint8)`,`side_by_side(A, B).shape == (2, 7, 3)`(輸出寬 = 3 + 0 + 4 = 7)。
- **AC4**:`side_by_side(A10, B20, gap=0).shape == (2, 4, 3)`,且 `out[:, 0:2]` 全為 10、`out[:, 2:4]` 全為 20(左 A 右 B,逐元素)。
- **AC5**:`side_by_side(A10, B20, gap=3, gap_color=(5, 6, 7)).shape == (2, 7, 3)`;其中 `out[:, 0:2]` 全 10、`out[:, 5:7]` 全 20,且中間 `out[:, 2:5]` 每個像素 == `[5, 6, 7]`(gap 欄填 gap_color)。
- **AC6**:高度不等時拋例外 — `side_by_side(np.zeros((2,2,3),np.uint8), np.zeros((3,2,3),np.uint8))` 觸發 `pytest.raises(ValueError)`。
- **AC7**:`gap` 為負時拋例外 — `side_by_side(A10, B20, gap=-1)` 觸發 `pytest.raises(ValueError)`。

**difference — 絕對差 / metamorphic 對稱 / 自差為 0 / 溢位**
- **AC8**:`np.array_equal(difference(A10, B20), np.full((2,2,3), 10, np.uint8))`(`|10-20| == 10`,逐元素)。
- **AC9**:`np.array_equal(difference(A10, A10), np.zeros((2,2,3), np.uint8))`(自差全 0,metamorphic 釘死)。
- **AC10**:`np.array_equal(difference(A10, B20), difference(B20, A10))`(對稱 `|A-B|==|B-A|`,釘死)。
- **AC11**:溢位安全 — 對 `P = np.full((1,1,3), 0, np.uint8)`、`Q = np.full((1,1,3), 255, np.uint8)`,`difference(P, Q)[0,0,0] == 255`(非 uint8 wrap 後的 1)。
- **AC12**:形狀不符拋例外 — `difference(np.zeros((2,2,3),np.uint8), np.zeros((2,3,3),np.uint8))` 觸發 `pytest.raises(ValueError)`。

**blend — 端點 / 0.5 平均 / round-half-up / clip 安全 / 錯誤**
- **AC13**:`np.array_equal(blend(A10, B20, 0.0), A10)`(`alpha=0` → 逐元素等於 A)。
- **AC14**:`np.array_equal(blend(A10, B20, 1.0), B20)`(`alpha=1` → 逐元素等於 B)。
- **AC15**:`blend(A10, B20, 0.5)[0,0,0] == 15` 且 `np.array_equal(blend(A10, B20, 0.5), np.full((2,2,3), 15, np.uint8))`(`(10+20)/2 = 15`,釘死具體像素值)。
- **AC16**:round-half-away-from-zero 釘死 — 對 `C = np.full((1,1,3), 100, np.uint8)`、`D = np.full((1,1,3), 101, np.uint8)`,`blend(C, D, 0.5)[0,0,0] == 101`(`100.5` 進位為 `101`,非 round-half-to-even 的 `100`)。
- **AC17**:`alpha` 超界拋例外 — `blend(A10, B20, 1.5)` 與 `blend(A10, B20, -0.1)` 各觸發 `pytest.raises(ValueError)`。
- **AC18**:形狀不符拋例外 — `blend(np.zeros((2,2,3),np.uint8), np.zeros((1,2,3),np.uint8), 0.5)` 觸發 `pytest.raises(ValueError)`。

**swipe — 欄邊界精確 / x=0 / x=W / 中間 / 不 mutate / 錯誤**
- **AC19**:對 `A = np.full((2,4,3), 10, np.uint8)`、`B = np.full((2,4,3), 20, np.uint8)`,`np.array_equal(swipe(A, B, 0), B)`(`x=0` → 全 B)。
- **AC20**:`np.array_equal(swipe(A, B, 4), A)`(`x=W=4` → 全 A)。
- **AC21**:`swipe(A, B, 1)` 結果中 `out[:, 0:1]` 全為 10(欄 0 取 A)、`out[:, 1:4]` 全為 20(欄 1..3 取 B);即「欄 index < x 取 A,其餘取 B」邊界釘死。
- **AC22**:不 mutate — 呼叫 `swipe(A, B, 2)` 後,`A` 仍全為 10、`B` 仍全為 20(以 `np.array_equal(A, np.full((2,4,3),10,np.uint8))` 與 B 同理驗證)。
- **AC23**:`x` 超界拋例外 — `swipe(A, B, -1)` 與 `swipe(A, B, 5)`(W=4,5>W)各觸發 `pytest.raises(ValueError)`。
- **AC24**:形狀不符拋例外 — `swipe(np.zeros((2,2,3),np.uint8), np.zeros((2,3,3),np.uint8), 1)` 觸發 `pytest.raises(ValueError)`。

**blink_sequence — 內容 / 順序 / 參照 / 錯誤**
- **AC25**:`seq = blink_sequence(A10, B20)`;`len(seq) == 2`、`np.array_equal(seq[0], A10)`、`np.array_equal(seq[1], B20)`(回 `[A, B]`,順序釘死)。
- **AC26**:`blink_sequence(A10, B20)[0] is A10` 且 `[1] is B20`(回傳原物件參照,不複製)。
- **AC27**:形狀不符拋例外 — `blink_sequence(np.zeros((2,2,3),np.uint8), np.zeros((3,2,3),np.uint8))` 觸發 `pytest.raises(ValueError)`。

---

## 6. 與其他模組的邊界(防越權)
- **不負責** 影像載入 / 解碼 / 色彩轉換(那是 `imgio`:檔案 → 顯示 RGB)。本模組吃的是已就緒的 uint8 RGB 陣列。
- **不負責** bbox / 偵測框疊加(那是 `overlay`:畫 Detection)。本模組的 "overlay" 比較模式由 app 用 `blend` 達成,不畫框。
- **不負責** 任何 GUI / 輪播計時 / Streamlit 元件(`blink_sequence` 只回 `[A, B]`,輪播節奏由 app 控)。
- **不負責** 持久化、I/O、排序、篩選。
- 本模組對外承諾:純函式、無副作用、**輸入陣列不被 mutate**(`blink_sequence` 回原參照但自身不寫入)、僅依賴 `numpy`、**零 import 任何業務模組**(可獨立平行驗收)。
