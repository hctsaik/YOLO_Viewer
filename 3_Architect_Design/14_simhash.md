# 設計:simhash(M4 / Tier A,純邏輯 numpy + PIL)

> `/architect` 模組設計。影像感知雜湊(perceptual hash),供近重複 / 相似圖搜尋。純運算、**零檔案 I/O、零 GUI**;用 PIL 縮放 + numpy 運算。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死「確切 hash 整數 / hamming 距離 / 排序」,**禁止代理式 AC**(不准「非空 / 是 int / 有差異」)。
> 上游:`ROADMAP.md`(第 47 行,M4 模組分解;Tier A;相依「—」即無)。職責一句:給一張影像陣列算出 average-hash / difference-hash 整數,並提供 Hamming 距離與相似圖搜尋。
> 邊界 sanity:此模組無 I/O、無跨模組契約、無 GUI,可獨立設計與驗收 → 不需退回 `/po`。

---

## 1. 目的 (Purpose)

把一張影像壓成固定長度的「感知雜湊整數」(average hash / difference hash),使「外觀近似」反映為「Hamming 距離小」,提供 `find_similar` 在候選集中找出近重複 / 相似圖;全程純函式、可被精確斷言(以可手算的合成小陣列釘死確切 hash 整數)。

---

## 2. I/O 契約 (逐字採用,不得更動簽名)

純邏輯。僅依賴 `numpy`(記為 `np`)與 `PIL.Image`(僅用於灰階化與縮放,**不做任何檔案開關**)。**不得 import** `imgio`/`framecompare`/`sidecar` 等任何業務模組。

```python
import numpy as np
from PIL import Image

def ahash(array: np.ndarray, hash_size: int = 8) -> int:
    # average hash:灰階化 → 縮放到 hash_size×hash_size → bit = (pixel > mean) → 打包成整數。
    ...

def dhash(array: np.ndarray, hash_size: int = 8) -> int:
    # difference hash:灰階化 → 縮放到 (hash_size+1)×hash_size → bit = (left > right) 水平梯度 → 打包成整數。
    ...

def hamming(h1: int, h2: int) -> int:
    # 兩 hash 整數的 Hamming 距離:bin(h1 ^ h2).count("1")。
    ...

def find_similar(query: np.ndarray,
                 candidates: list,
                 max_distance: int = 10,
                 hasher: str = "ahash",
                 hash_size: int = 8) -> list:
    # candidates = list[(name: str, array: np.ndarray)];
    # 用 hasher(預設 ahash)在 hash_size(預設 8)下算 query 與每個 candidate 的 hash 與 hamming;
    # 回 <= max_distance 者,依 (distance 升序, name 升序) 排好的 list[(name, distance)]。
    # hash_size 必須一致地套用到 query 與所有 candidate(否則距離無意義)。
    ...
```

### 2.1 輸入資料形狀(契約值,釘死)

- `array`(以及 `find_similar` 的 `query` 與各 candidate array)為 `np.ndarray`,`dtype == np.uint8`,值域 `0..255`。
- **接受兩種形狀**(釘死):
  - RGB:`ndim == 3` 且 `shape == (H, W, 3)`。
  - 灰階:`ndim == 2` 且 `shape == (H, W)`。
- `H >= 1`、`W >= 1`。
- `hash_size` 為正整數,`hash_size >= 1`(典型 8)。
- `find_similar` 的 `candidates` 為 `list`,每個元素為 `(name, array)`;`name` 為 `str`,`array` 同上形狀規則。`candidates` 可為空 list。
- `hasher ∈ {"ahash", "dhash"}`。

### 2.2 灰階化規則(釘死,**這是 hash 可重現的關鍵**)

把輸入轉成單通道 uint8 灰階,規則固定為:

- **若輸入已是 2D(`ndim == 2`)**:直接視為灰階,**不做任何轉換**(值原樣使用)。
- **若輸入是 3D RGB(`shape == (H, W, 3)`)**:用 PIL 的 `"L"` 轉換,即
  `Image.fromarray(array, mode="RGB").convert("L")`。
  PIL `"L"` 的公式(釘死,供 PM 推導期望值):
  `L = round(0.299*R + 0.587*G + 0.114*B)`,其中 PIL 內部以整數係數
  `L8 = (R*299 + G*587 + B*114) // 1000`(實際 ITU-R 601-2 luma,對純色三通道相等時 `R==G==B==v` → `L == v`,因 `(299+587+114)=1000`,`v*1000//1000 == v`)。
  - **契約推論(供 AC)**:任何 `R==G==B==v` 的純色 RGB 像素,灰階後恰為 `v`(無誤差)。本模組 AC 全部採用此種「三通道相等」的 RGB 或直接用 2D 灰階,**避免 luma 係數捨入造成脆弱斷言**。

### 2.3 縮放規則(釘死)

- 灰階化後得到 2D PIL `"L"` 影像,用 **`Image.resize((target_w, target_h), resample=Image.Resampling.NEAREST)`** 縮放(NEAREST = 最近鄰,**釘死**;不得用 BILINEAR/LANCZOS,因其會插值,使手算 hash 不可行)。
  - `ahash` 目標尺寸:`(target_w, target_h) = (hash_size, hash_size)`。
  - `dhash` 目標尺寸:`(target_w, target_h) = (hash_size + 1, hash_size)`(寬比高多 1,供水平梯度)。
  - 注意 PIL `resize` 的參數是 `(width, height)`,而 numpy shape 是 `(height, width)`,**順序相反**,實作須留意。
- **當輸入尺寸已等於目標尺寸時,NEAREST resize 為 identity(值不變)**。本模組 AC **一律餵入已等於目標尺寸的陣列**(如 `ahash` 餵 `hash_size×hash_size`、`dhash` 餵 `hash_size×(hash_size+1)`),使 resize 不改值、hash 可純手算。
- resize 後轉回 numpy:`np.asarray(resized, dtype=np.uint8)`,得到 `ahash` 的 `(hash_size, hash_size)` 或 `dhash` 的 `(hash_size, hash_size+1)` uint8 灰階矩陣。

### 2.4 位元順序與打包規則(釘死,**hash 整數的唯一定義**)

得到布林矩陣 `bits`(2D,row-major)後:

1. **以 C order(row-major)`.flatten()` 攤平**:即 `bits.flatten()`,先掃第 0 列由左到右,再第 1 列…(numpy 預設 C order)。
2. **MSB-first**:攤平後的第 `i` 個布林(`i` 從 0 起)對應位權 `2**(N-1-i)`,其中 `N = len(flat)`。等價於把布林序列當成二進位字串(第一個 bit 是最高位)轉成整數。
   - 實作等價式(釘死語義,實作可任選等價寫法):
     ```
     value = 0
     for b in bits.flatten():
         value = (value << 1) | int(bool(b))
     return value
     ```
   - 即「第一個(左上)像素是最高位,最後一個(右下 / dhash 右下對)像素是最低位」。
3. 回傳 Python `int`(任意精度;`hash_size=8` → 64 bit;`hash_size=16` → 256 bit,Python int 天然支援)。

### 2.5 bit 判定準則(釘死,**含 `>` 與均勻邊界**)

- **ahash**:`mean = float(grey.mean())`(對 `(hash_size, hash_size)` uint8 矩陣取算術平均,float64);
  `bit[r,c] = (grey[r,c] > mean)`(**嚴格大於**,`>`,釘死;`== mean` → 0/False)。
  - **均勻影像推論(供 AC)**:當所有像素相等(`grey` 全為同值 `v`)時,`mean == v`,每個像素 `v > v` 為 False → **整張 hash 全 0,即整數 `0`**(釘死)。
- **dhash**:對 `(hash_size, hash_size+1)` 矩陣,逐列比較水平相鄰:
  `bit[r,c] = (grey[r,c] > grey[r,c+1])`,`c ∈ 0..hash_size-1`,`r ∈ 0..hash_size-1`,得 `(hash_size, hash_size)` 布林矩陣。(**left > right** 為 1,釘死;`left == right` → 0。)
  - **均勻影像推論(供 AC)**:全相等時每個相鄰對 `v > v` 為 False → **dhash 全 0,即整數 `0`**(釘死)。

### 2.6 hamming(釘死)

- `hamming(h1, h2) = bin(h1 ^ h2).count("1")`(兩整數 XOR 後的 popcount)。
- 推論:`hamming(h, h) == 0`(任何整數與自己距離 0,釘死);`hamming` 對稱(`hamming(a,b)==hamming(b,a)`)。

### 2.7 find_similar 排序與篩選(釘死)

1. 算 `qh = hasher_fn(query, hash_size)`(`hasher == "ahash"` 用 `ahash`,`"dhash"` 用 `dhash`;`hash_size` 由參數傳入,預設 8)。
2. 對每個 `(name, arr)` in `candidates`:算 `d = hamming(qh, hasher_fn(arr, hash_size))`(query 與 candidate 用**同一** hash_size)。
3. **篩選**:只保留 `d <= max_distance` 者。
4. **排序鍵**:`(d, name)` —— **先 distance 升序,平手再 name 字典序(`str` 預設 `<`)升序**(釘死;穩定且全序)。
5. 回 `list[(name, d)]`(篩選後、排好序);空候選或無人達標 → `[]`。

---

## 3. 資料流 (Data Flow)

### 3.1 `_to_grey(array) -> np.ndarray`(內部,語義釘死;名稱可自定)
1. `array.ndim == 2` → 回 `array`(視為灰階,uint8,原樣)。
2. `array.ndim == 3 and array.shape[2] == 3` → `np.asarray(Image.fromarray(array, "RGB").convert("L"), dtype=np.uint8)`,回 `(H, W)` uint8。
3. 其他形狀 → `raise ValueError`(見 §4)。

### 3.2 `ahash(array, hash_size=8) -> int`
1. `hash_size < 1` → `raise ValueError`。
2. `grey = _to_grey(array)`(§3.1)。
3. `img = Image.fromarray(grey, "L").resize((hash_size, hash_size), Image.Resampling.NEAREST)`;`small = np.asarray(img, dtype=np.uint8)`(shape `(hash_size, hash_size)`)。
4. `mean = float(small.mean())`;`bits = small > mean`(布林 `(hash_size, hash_size)`)。
5. 依 §2.4 打包 `bits.flatten()` → `int`,回。

### 3.3 `dhash(array, hash_size=8) -> int`
1. `hash_size < 1` → `raise ValueError`。
2. `grey = _to_grey(array)`。
3. `img = Image.fromarray(grey, "L").resize((hash_size + 1, hash_size), Image.Resampling.NEAREST)`;`small = np.asarray(img, dtype=np.uint8)`(shape `(hash_size, hash_size+1)`)。
4. `bits = small[:, :-1] > small[:, 1:]`(布林 `(hash_size, hash_size)`;每列左>右)。
5. 依 §2.4 打包 `bits.flatten()` → `int`,回。

### 3.4 `hamming(h1, h2) -> int`
1. 回 `bin(h1 ^ h2).count("1")`。

### 3.5 `find_similar(query, candidates, max_distance=10, hasher="ahash", hash_size=8) -> list`
1. `hasher not in {"ahash","dhash"}` → `raise ValueError`。
2. `max_distance < 0` → `raise ValueError`。
3. `fn = ahash if hasher == "ahash" else dhash`;`qh = fn(query, hash_size)`。
4. `results = []`;對每個 `(name, arr)`:`d = hamming(qh, fn(arr, hash_size))`;若 `d <= max_distance` → `results.append((name, d))`。
5. `results.sort(key=lambda t: (t[1], t[0]))`(distance 升序、name 升序;§2.7)。
6. 回 `results`(`candidates == []` → `[]`)。

- **metamorphic / 不變性(供 AC,§5)**:
  - 同一陣列兩次 hash 相同 → `hamming(ahash(X), ahash(X)) == 0`、`hamming(dhash(X), dhash(X)) == 0`。
  - **2× 上採樣不變性**:把 `X`(已是 `hash_size×hash_size`)用 NEAREST 放大 2× 成 `2hash_size×2hash_size` 的 `X2`,因 NEAREST 縮回原尺寸還原 → `ahash(X2) == ahash(X)`(距離 0)。

---

## 4. 邊界條件與錯誤處理

a. **不支援的形狀**:`array.ndim` 非 2、且非「3D 且最後軸=3」→ `raise ValueError`(例:`(H,W,4)` RGBA、`(H,W,1)`、`ndim==1` 皆拒)。Tier A 純邏輯,僅守此一條形狀防禦(因錯誤靜默會讓 PIL/numpy 拋難解的下游錯)。
b. **`hash_size` 邊界**:`hash_size >= 1` 合法;`hash_size < 1`(0 或負)→ `raise ValueError`。`hash_size == 1`:`ahash` 為 1×1(單像素 `> mean` 恆 False → hash `0`);`dhash` 為 `1×2`(單一左右對)。
c. **均勻 / 全同值影像**:所有像素相等 → `ahash` 與 `dhash` 皆回整數 `0`(§2.5 釘死);這是合法且確定的行為,非錯誤。
d. **`find_similar` 空候選**:`candidates == []` → 回 `[]`(不拋錯)。
e. **`max_distance == 0`**:只回「hash 與 query 完全相同(hamming 0)」者;距離 >0 一律剔除。
f. **`max_distance < 0`**:`raise ValueError`(負距離無意義)。
g. **`hasher` 非法值**:`hasher ∉ {"ahash","dhash"}` → `raise ValueError`。
h. **不 mutate 輸入**:所有函式不得修改傳入的 `array` / `query` / candidate arrays / `candidates` list 內容(灰階/縮放都產生新物件;排序在內部新 list 上做,不動傳入 list)。
i. **dtype 假設**:契約假設輸入 uint8(§2.1);Tier A 信任契約,不對 dtype 額外防禦(形狀防禦除外,見 a)。
j. **hash 穩定性**:`ahash`/`dhash` 為純函式,**同輸入同參數恆回同整數**(無隨機、無時間、無 I/O)。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以可手算的合成小陣列釘死確切整數)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_simhash.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import simhash`)。
>
> **AC 釘值推導說明(給 PM 對照,確保期望值可手算)**:
> - 所有 AC 餵入的陣列**尺寸恰等於 hash 目標尺寸**,故 NEAREST resize 為 identity,hash 完全由餵入值決定。
> - RGB 一律用「三通道相等」純色(§2.2 → 灰階 = 該值),或直接餵 2D 灰階,避免 luma 捨入。
> - 位元打包:row-major flatten + MSB-first(§2.4);把布林矩陣讀成二進位字串(左上→右下)即為整數的二進位表示。
>
> 共用合成陣列(供下列 AC 引用):
> ```python
> import numpy as np
> # --- ahash 用,hash_size=2,直接餵 2x2 灰階(resize 為 identity) ---
> # 棋盤:[[10, 90],[90, 10]],mean = (10+90+90+10)/4 = 50。
> #   bit = (v > 50):10>50=F, 90>50=T, 90>50=T, 10>50=F → flatten [F,T,T,F]
> #   MSB-first: 0b0110 = 6。
> G_CHECKER = np.array([[10, 90], [90, 10]], dtype=np.uint8)   # ahash(., 2) == 6
> # 左暗右亮:[[10, 90],[10, 90]],mean=50 → bit [F,T,F,T] = 0b0101 = 5。
> G_LR = np.array([[10, 90], [10, 90]], dtype=np.uint8)        # ahash(., 2) == 5
> # 全均勻:[[50,50],[50,50]],mean=50,皆 50>50=F → 0。
> G_FLAT = np.full((2, 2), 50, dtype=np.uint8)                 # ahash(., 2) == 0
> # --- dhash 用,hash_size=2,直接餵 2x3 灰階(resize 為 identity) ---
> # [[10,90,10],[90,10,90]]:列0 對 (10>90=F,90>10=T)→[F,T];列1 (90>10=T,10>90=F)→[T,F]
> #   flatten [F,T,T,F] MSB-first = 0b0110 = 6。
> D_A = np.array([[10, 90, 10], [90, 10, 90]], dtype=np.uint8) # dhash(., 2) == 6
> # 全均勻 2x3 → dhash 0。
> D_FLAT = np.full((2, 3), 50, dtype=np.uint8)                 # dhash(., 2) == 0
> ```

**ahash — 確切整數釘死 / `>` 準則 / 均勻邊界 / RGB↔灰階一致 / hash_size**
- **AC1**:`simhash.ahash(G_CHECKER, hash_size=2) == 6`(棋盤,mean=50,bits `[F,T,T,F]` MSB-first = `0b0110` = 6;**確切整數**)。
- **AC2**:`simhash.ahash(G_LR, hash_size=2) == 5`(左暗右亮,bits `[F,T,F,T]` = `0b0101` = 5)。
- **AC3**:`simhash.ahash(G_FLAT, hash_size=2) == 0`(全均勻 → 所有 `v > mean` 皆 False,`>` 準則 + 均勻邊界釘死為整數 0)。
- **AC4**:回傳型別為 Python `int` 且非負 —— `isinstance(simhash.ahash(G_CHECKER, 2), int) and simhash.ahash(G_CHECKER, 2) >= 0`(輔助斷言,非代理:與 AC1 的確切值並存)。
- **AC5**:RGB↔灰階一致 —— 令 `RGB_CHECKER = np.stack([G_CHECKER]*3, axis=-1)`(三通道相等,shape `(2,2,3)`),則 `simhash.ahash(RGB_CHECKER, 2) == simhash.ahash(G_CHECKER, 2) == 6`(§2.2 三通道相等 → 灰階還原)。
- **AC6**:`hash_size=8` 全均勻 —— `simhash.ahash(np.full((8,8), 123, np.uint8), hash_size=8) == 0`(64 位全 0)。
- **AC7**:位元範圍 —— `simhash.ahash(np.full((8,8,3), 0, np.uint8), 8) == 0`;且對「左半全 0、右半全 255」的 `8×8`(`g=np.zeros((8,8),np.uint8); g[:,4:]=255`,mean=127.5,左<mean=0、右>mean=1,每列 bits `00001111`=0x0F)→ `ahash(g,8) == int("0000111100001111"*4, 2)`,即 `0x0F0F0F0F0F0F0F0F == 1085102592571150095`(每列 `0b00001111`=15,8 列串接 MSB-first;**確切 64-bit 整數**)。

**dhash — 確切整數釘死 / left>right 準則 / 均勻邊界 / 尺寸**
- **AC8**:`simhash.dhash(D_A, hash_size=2) == 6`(2×3,水平梯度 bits `[F,T,T,F]` = `0b0110` = 6;**確切整數**)。
- **AC9**:`simhash.dhash(D_FLAT, hash_size=2) == 0`(全均勻 → 每個 `left > right` 皆 False,均勻邊界釘死為 0)。
- **AC10**:left>right 準則釘死(餵 `hash_size=8` 的目標尺寸 `(8,9)`,resize 為 identity)—— 令 `row = [0,255,0,255,0,255,0,255,0]`、`g = np.tile(np.array(row, dtype=np.uint8), (8, 1))`(shape `(8,9)`,8 列皆同)。每列相鄰對 (0>255=F,255>0=T,0>255=F,…) 交替 → 每列 bits `[F,T,F,T,F,T,F,T]` = `0b01010101`;8 列 row-major flatten + MSB-first 串接 → `0x5555555555555555` → `simhash.dhash(g, hash_size=8) == 6148914691236517205`(**確切 64-bit 整數**;`int("0101010101010101"*4, 2)` 亦等於此)。
- **AC11**:RGB↔灰階一致 —— `RGB_D = np.stack([D_A]*3, axis=-1)`(shape `(2,3,3)`),`simhash.dhash(RGB_D, 2) == simhash.dhash(D_A, 2) == 6`。

**hamming — 確切距離 / 自距 0 / 對稱**
- **AC12**:`simhash.hamming(0b1011, 0b0110) == 3`(`1011 ^ 0110 = 1101`,popcount=3;**確切**)。
- **AC13**:`simhash.hamming(255, 255) == 0` 且 `simhash.hamming(0, 0) == 0`(自距 0,釘死)。
- **AC14**:`simhash.hamming(6, 5) == simhash.hamming(5, 6)` 且其值 `== 2`(`6=110,5=101`,XOR=`011`,popcount=2;對稱 + 確切值)。
- **AC15**:`simhash.hamming(0, 255) == 8`(`0b00000000 ^ 0b11111111 = 11111111`,8 個 1;確切)。

**identity / metamorphic 不變性(同陣列 / 2× 上採樣)**
- **AC16**:同陣列 hash 一致 —— `simhash.hamming(simhash.ahash(G_CHECKER,2), simhash.ahash(G_CHECKER,2)) == 0`,且 `simhash.hamming(simhash.dhash(D_A,2), simhash.dhash(D_A,2)) == 0`。
- **AC17**:**2× 上採樣不變性(metamorphic)** —— `X2 = np.repeat(np.repeat(G_CHECKER, 2, axis=0), 2, axis=1)`(把 `2×2` 最近鄰放大成 `4×4`),則 `simhash.ahash(X2, hash_size=2) == simhash.ahash(G_CHECKER, hash_size=2) == 6`(NEAREST 縮回 identity → 距離 0)。

**find_similar — 篩選 / 排序(距離升序、name 升序)/ max_distance=0 / 空候選 / 不變性**
> 共用:`query = G_CHECKER`(ahash=6);候選用直接餵的 2×2 灰階,各自 ahash 可手算。
> ```python
> # G_CHECKER ahash=6(0b0110)。設計三個候選:
> #   "same"  = G_CHECKER             → ahash 6 → hamming(6,6)=0
> #   "lr"    = G_LR                  → ahash 5(0b0101)→ hamming(6,5)= XOR 0b0011 →2
> #   "flat"  = G_FLAT               → ahash 0(0b0000)→ hamming(6,0)= popcount(0b0110)=2
> cands = [("lr", G_LR), ("flat", G_FLAT), ("same", G_CHECKER)]
> ```
> 註:下列 `find_similar` AC 一律傳 `hash_size=2`(與 2×2/2×3 候選尺寸一致,使 resize 為 identity、hamming 可手算);若省略 `hash_size` 則用預設 8、會把 2×2 上採樣到 8×8 致距離改變(那是 §2.7 的合法行為,但非本批 AC 釘值情境)。
- **AC18**:全收(`max_distance=10`)排序 —— `simhash.find_similar(G_CHECKER, cands, max_distance=10, hasher="ahash", hash_size=2) == [("same", 0), ("flat", 2), ("lr", 2)]`(距離升序:0 在前;距離平手(flat、lr 皆 2)再以 **name 升序** `"flat" < "lr"`;**確切 list、含順序**)。
- **AC19**:`max_distance=0` 只回完全相同 —— `simhash.find_similar(G_CHECKER, cands, max_distance=0, hasher="ahash", hash_size=2) == [("same", 0)]`(距離 >0 全剔除;確切)。
- **AC20**:`max_distance=1` 邊界 —— `simhash.find_similar(G_CHECKER, cands, max_distance=1, hasher="ahash", hash_size=2) == [("same", 0)]`(距離 2 的 flat/lr 因 `2 <= 1` 為 False 被剔;只剩 0)。
- **AC21**:空候選 —— `simhash.find_similar(G_CHECKER, [], max_distance=10, hash_size=2) == []`(回空 list)。
- **AC22**:name 升序平手解析(純距離平手案例)—— 對 `cands2 = [("zebra", G_FLAT), ("apple", G_LR)]`(兩者對 query 距離皆 2),`simhash.find_similar(G_CHECKER, cands2, max_distance=5, hasher="ahash", hash_size=2) == [("apple", 2), ("zebra", 2)]`(同距離 → name 字典序 `"apple" < "zebra"`)。
- **AC23**:`hasher="dhash"` 路徑可用 —— `query2 = D_A`(dhash=6);`cands3 = [("d_same", D_A), ("d_flat", D_FLAT)]`(D_FLAT dhash=0 → hamming(6,0)=2);`simhash.find_similar(D_A, cands3, max_distance=10, hasher="dhash", hash_size=2) == [("d_same", 0), ("d_flat", 2)]`(走 dhash 分支、排序確切)。

**錯誤路徑(釘死拋 ValueError)**
- **AC24**:不支援形狀 —— `simhash.ahash(np.zeros((4,4,4), np.uint8))` 觸發 `pytest.raises(ValueError)`(RGBA 4 通道拒)。
- **AC25**:`ndim==1` 拒 —— `simhash.ahash(np.zeros((16,), np.uint8))` 觸發 `pytest.raises(ValueError)`。
- **AC26**:`hash_size < 1` 拒 —— `simhash.ahash(G_CHECKER, hash_size=0)` 觸發 `pytest.raises(ValueError)`。
- **AC27**:`hasher` 非法 —— `simhash.find_similar(G_CHECKER, [], hasher="phash")` 觸發 `pytest.raises(ValueError)`。
- **AC28**:`max_distance < 0` 拒 —— `simhash.find_similar(G_CHECKER, cands, max_distance=-1, hash_size=2)` 觸發 `pytest.raises(ValueError)`(max_distance 檢查先於雜湊,故 hash_size 不影響)。

**不 mutate 輸入**
- **AC29**:呼叫 `simhash.ahash` / `simhash.dhash` / `simhash.find_similar` 後,傳入的 `G_CHECKER` 內容不變 —— `np.array_equal(G_CHECKER, np.array([[10,90],[90,10]], np.uint8))` 仍為 True;且 `cands` list 物件本身內容/順序不被改動(`cands[0] == ("lr", ...)` 仍成立,即函式回新 list 不就地排序傳入 list)。

---

## 6. 與其他模組的邊界(防越權)

- **不負責** 影像載入 / 解碼 / 檔案讀取(那是 `imgio`:檔案 → 顯示 RGB)。本模組吃的是**已就緒的記憶體陣列**(uint8 灰階或 RGB),PIL 只用於灰階化與縮放,**絕不開關檔案**。
- **不負責** 兩圖的視覺比較運算(side-by-side/difference/blend/swipe;那是 `framecompare`)。本模組只產出「雜湊整數 / 距離 / 相似清單」,不產出可顯示影像。
- **不負責** 任何 GUI / 排序 UI / 縮圖牆 / Streamlit 元件;`find_similar` 只回 `list[(name, distance)]`,呈現由 app 控。
- **不負責** 持久化 / 索引建置 / 快取;每次呼叫即時計算。
- **不負責** tagging / verdict / 偵測框語義(與 `tagging`/`yolo`/`overlay` 無關;**零 import 任何業務模組**)。
- 本模組對外承諾:純函式、無檔案副作用、**輸入陣列不被 mutate**、僅依賴 `numpy` + `PIL.Image`(僅記憶體操作)、**零 import 任何業務模組**(可獨立平行驗收)。
```
