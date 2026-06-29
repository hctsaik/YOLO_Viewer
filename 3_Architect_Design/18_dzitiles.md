# 18 — dzitiles(Tier B,M5)技術設計

> `/architect` 產物(module 粒度)。承 `ROADMAP.md`(M5、第 61 行;決策日誌 2026-06-23「po 釘契約」第 133–134 行:dzitiles 依 Deep Zoom 規格、level=`ceil(log2(maxWH))+1`、tile_size 預設 254 overlap 1)。
> 本檔只定義契約與驗收,**不含任何實作**。實作由 `/pg` 寫進 `5_PG_Develop/dzitiles.py`。

## 模組邊界 sanity check(開工前一句)

`dzitiles` 內聚一句話可講完(「把一張 RGB uint8 大圖切成 Deep Zoom(DZI)金字塔瓦片 + `.dzi` 描述,供 OpenSeadragon 只載可視區瓦片」)。
它是**純陣列 + PIL 縮放**的確定性轉換(核心純函式不開關檔案;寫檔在薄 `write_*` 包裝),
**無上游業務相依**(吃 `imgio.load()["array"]` 那種已就緒的 HxWx3 uint8 陣列,但不 import `imgio`),不依賴 GUI / Streamlit / 網路。
可獨立設計,並以「真實 PNG bytes 解回 PIL 驗尺寸/像素」+「DZI XML 字串逐字比對」做 Tier B 真實 round-trip 驗收。
**結論:範圍 OK,不退回 `/po`。**

> 與 viewer 的接線(OpenSeadragon 端如何吃 `.dzi` + tiles URL)屬 `app` / `viewer_component` 整合層的職責,**不在本模組契約內**;本模組只負責「產出符合 Deep Zoom 規格、OSD 能直接消費」的 descriptor 字串與瓦片 bytes/data_url。本模組存在的價值 = 解掉 ROADMAP 記載「目前送全解析度 data URL,大圖需改 DZI tiles」的最大技術風險(第 96 行)。

---

## 1. 目的 (Purpose)

把一張 `HxWx3 uint8` RGB 影像,依 **Deep Zoom Image(DZI)規格**生成影像金字塔:計算層數與各層尺寸、切出含 overlap 的瓦片(PIL 縮放 + numpy 裁切)、產出標準 `.dzi` XML descriptor,讓 OpenSeadragon 客戶端只下載可視區瓦片,而非整張全解析度 data URL。

## 2. 相依與限制

- 僅用:`numpy`、`Pillow(PIL)`、Python 標準庫(`io`、`base64`、`math`、`pathlib`、`os`)。
- **不可新增任何 pip 依賴。** **不得 import** `imgio` / `viewport` / `app` 等任何業務模組(可獨立平行驗收)。
- 核心純函式(`num_levels` / `level_dimensions` / `dzi_descriptor` / `tile` / `build_tiles`)**零檔案 I/O、零 GUI、零網路**;只做陣列/位元組/字串轉換,故可被純 pytest round-trip 驗收。
- **唯一允許碰檔案的是薄 write 包裝**(`write_dzi`,見 §3),其餘函式不得開關檔案。
- 進入點檔名:`5_PG_Develop/dzitiles.py`(conftest 已把 `5_PG_Develop` 置於 `sys.path` 最前;測試 `import dzitiles`)。模組內需 PIL/numpy 時正常 import。

### 2.1 縮放濾鏡(釘死,確定性的關鍵)

金字塔降採樣**一律使用 `PIL.Image.BOX`**(面積平均降採樣,即影像金字塔數學上正確的 area-average)。
**禁止**改用 `BILINEAR` / `LANCZOS` / `NEAREST`,因其輸出與 BOX 不同(已實測:4×4 區塊圖降到 2×2,BOX 給區塊平均、BILINEAR/LANCZOS 給帶權平滑值)。BOX 讓「每個 2×2 同色區塊 → 該色精確平均」可手算,AC 才能釘死像素值。最高層(`max_level`,scale=1)不縮放,瓦片為輸入的精確切片。

---

## 3. I/O 契約(逐字採用,簽名為硬契約,/pm 直接鎖)

```python
import numpy as np

def num_levels(width: int, height: int) -> int
# DZI 層數 = ceil(log2(max(width, height))) + 1。
#   特例:max(width,height) == 1 → 回 1(log2(1)=0,公式自然成立)。
#   level 0 永遠是 1x1;最高層 level == num_levels-1 永遠是原尺寸 (width,height)。

def level_dimensions(width: int, height: int, level: int) -> tuple
# 回 (levelW, levelH)。設 max_level = num_levels(width,height) - 1;scale = 2 ** (max_level - level);
#   levelW = ceil(width / scale);levelH = ceil(height / scale)。
#   level == max_level → (width, height);level == 0 → (1, 1)。
#   level < 0 或 level > max_level → ValueError。

def dzi_descriptor(width: int, height: int, tile_size: int = 254,
                   overlap: int = 1, fmt: str = "png") -> str
# 回標準 .dzi XML 字串(逐字,見 §3.1)。不換行、無多餘空白。

def tile(array: np.ndarray, level: int, col: int, row: int,
         tile_size: int = 254, overlap: int = 1) -> np.ndarray
# 把 array(HxWx3 uint8)縮到該 level 尺寸(PIL BOX),裁出 (col,row) 瓦片;回 HxWx3 uint8。
#   瓦片像素區間(Deep Zoom 規格,見 §3.2):
#     x0 = max(0, col*tile_size - overlap);  x1 = min(levelW, col*tile_size + tile_size + overlap)
#     y0 = max(0, row*tile_size - overlap);  y1 = min(levelH, row*tile_size + tile_size + overlap)
#     回 scaled[y0:y1, x0:x1]。
#   col/row 超出該 level 的格數範圍 → ValueError;level 超界 → ValueError。

def build_tiles(array: np.ndarray, tile_size: int = 254, overlap: int = 1,
                fmt: str = "png") -> dict
# 回完整金字塔(見 §3.3 結構)。tiles 值 = 該瓦片的 PNG bytes(fmt=="png")。

def to_png_bytes(rgb_uint8: np.ndarray) -> bytes
# 把 HxWx3 uint8 編成 PNG 檔位元組;回傳值以 PNG magic b"\x89PNG\r\n\x1a\n" 開頭。
#   非 uint8 / 形狀非 HxWx3 → ValueError。

def to_data_url(rgb_uint8: np.ndarray) -> str
# 回 "data:image/png;base64,<b64>";<b64> = base64(to_png_bytes(rgb_uint8))。

def write_dzi(out_dir, array: np.ndarray, name: str = "image",
              tile_size: int = 254, overlap: int = 1, fmt: str = "png") -> str
# 薄 write 包裝(唯一碰檔案者):呼叫 build_tiles,把
#   <out_dir>/<name>.dzi             ← descriptor 字串(UTF-8)
#   <out_dir>/<name>_files/<level>/<col>_<row>.<fmt>  ← 各瓦片 bytes
# 寫到磁碟(此即 OSD 標準 DZI 目錄佈局)。回傳 .dzi 檔的絕對路徑字串。
#   out_dir 不存在 → 自動建立(含 _files 子目錄樹)。
```

> **data_url vs png bytes 的決策**:`build_tiles` 的 `tiles` 值**固定為 PNG bytes**(非 data url),理由:(a) bytes 是最小、可被 PIL 直接 round-trip 驗收的中性表示;(b) viewer 接線層可自行決定包成 data url(`to_data_url`)或寫成檔案經 HTTP 供應(`write_dzi`),兩條路本模組都提供。`to_data_url(tile(...))` 即得單張瓦片的 data url。

### 3.1 `.dzi` XML(釘死,逐字)

`dzi_descriptor(W, H, tile_size, overlap, fmt)` **必須**回傳下列單行字串(屬性順序、引號、xmlns、無多餘空白皆為契約):

```
<?xml version="1.0" encoding="UTF-8"?><Image xmlns="http://schemas.microsoft.com/deepzoom/2008" Format="{fmt}" Overlap="{overlap}" TileSize="{tile_size}"><Size Height="{H}" Width="{W}"/></Image>
```

- 命名空間固定 `http://schemas.microsoft.com/deepzoom/2008`(OSD 認得的官方 Deep Zoom schema)。
- `<Image>` 屬性順序固定:`Format` → `Overlap` → `TileSize`。
- `<Size>` 屬性順序固定:`Height` → `Width`(本契約釘死此序;測試逐字比對)。
- 整串無換行符、無 tab、屬性間單一空白。

### 3.2 瓦片邊界與 overlap(Deep Zoom 規格,釘死)

對某 level(尺寸 `levelW × levelH`),瓦片格座標 `(col, row)`,`col ∈ [0, cols)`、`row ∈ [0, rows)`,其中
`cols = ceil(levelW / tile_size)`、`rows = ceil(levelH / tile_size)`。瓦片像素區間(半開區間,numpy 切片):

```
x0 = max(0,       col*tile_size - overlap)
x1 = min(levelW,  col*tile_size + tile_size + overlap)
y0 = max(0,       row*tile_size - overlap)
y1 = min(levelH,  row*tile_size + tile_size + overlap)
tile_pixels = scaled[y0:y1, x0:x1]   # 回 HxWx3 uint8
```

- overlap 語義:每片在**面向影像內部**的邊各多 `overlap` 像素;**碰到影像邊界的邊不外擴**(被 `max(0,..)` / `min(level..,..)` 夾住)。
- `overlap=0` → 瓦片彼此不重疊,寬高最大 = `tile_size`(邊界瓦片可能更小)。
- 角落瓦片只在 1~2 個方向有 overlap;中央瓦片四邊都有 overlap。

### 3.3 `build_tiles` 回傳結構(釘死)

```python
{
  "width":     W,            # int,== array.shape[1]
  "height":    H,            # int,== array.shape[0]
  "tile_size": tile_size,    # int
  "overlap":   overlap,      # int
  "max_level": num_levels(W,H) - 1,   # int
  "num_levels": num_levels(W,H),      # int
  "dzi":       <str>,        # == dzi_descriptor(W,H,tile_size,overlap,fmt)
  "tiles": {                 # dict[int level -> dict[str "{col}_{row}" -> bytes]]
      level: { f"{col}_{row}": <PNG bytes>, ... },
      ...                    # level 從 0 到 max_level 全部齊備
  }
}
```

- `tiles` 必含 **0 .. max_level 每一層**;每層含該層**全部** `cols × rows` 片,key 格式嚴格 `"{col}_{row}"`(col 在前、row 在後,底線分隔,無前導零)。
- 每片值 = `to_png_bytes(tile(array, level, col, row, tile_size, overlap))`(即真實可解碼 PNG)。
- 該 dict 之 key 集合 = `{f"{c}_{r}" for r in range(rows) for c in range(cols)}`,不多不少。

---

## 4. 資料流 (Data Flow)

```
 array (HxWx3 uint8, 全解析度) ──► build_tiles
        │
        ├─ num_levels(W,H) ─────────────► num_levels / max_level
        │
        └─ for level in 0..max_level:
               level_dimensions(W,H,level) ─► (levelW, levelH)
               PIL.Image.fromarray(array).resize((levelW,levelH), BOX) ─► scaled  (該層整圖)
               for row in 0..rows-1, col in 0..cols-1:
                   §3.2 邊界裁切 scaled[y0:y1, x0:x1] ─► tile_arr (含 overlap)
                   to_png_bytes(tile_arr) ─► PNG bytes ─► tiles[level]["{col}_{row}"]
        │
        └─ dzi_descriptor(W,H,..) ─► dict["dzi"]
                                    │
   單張瓦片需求:  tile(array,level,col,row,..) ─► HxWx3 uint8 ─┬─ to_png_bytes ─► bytes
                                                              └─ to_data_url ─► data:image/png;base64,..

   落磁碟(OSD HTTP 供圖):  write_dzi(out_dir, array, name) ─► <name>.dzi + <name>_files/<level>/<col>_<row>.png
```

要點:
- **每層只縮一次整圖**(`resize` 到 `(levelW,levelH)`),再對該層 scaled 切多片;不要每片各自縮放(效能 + 一致性)。
- 最高層 `level == max_level` 的 `(levelW,levelH) == (W,H)`,`resize` 為 no-op(尺寸相同),其瓦片是輸入的**精確切片**(像素零失真,AC 釘死靠這層)。
- 純函式不碰檔案;唯一寫檔在 `write_dzi`,佈局為 OSD 標準 `<name>.dzi` + `<name>_files/<level>/<col>_<row>.<fmt>`。

---

## 5. 邊界條件與錯誤處理

| 情境 | 行為 |
|------|------|
| `1×1` 影像 | `num_levels(1,1)==1`、`max_level==0`、`level_dimensions(1,1,0)==(1,1)`;`build_tiles` 回單層單片 |
| 非 2 次方尺寸(如 5×3) | 各層尺寸用 `ceil(width/scale)`(見 §3.2 表);末層回原尺寸;邊界瓦片較小 |
| `tile_size` 大於該層尺寸 | `cols==rows==1`,單一瓦片 = 整層(overlap 被邊界夾住,不外擴) |
| `overlap == 0` | 瓦片不重疊;§3.2 公式中 overlap 項為 0,`max(0,..)`/`min(..)` 退化為 `col*tile_size` / `(col+1)*tile_size`(末片夾到 levelW/levelH) |
| `level` 超界(`<0` 或 `>max_level`) | `level_dimensions` / `tile` 拋 `ValueError` |
| `tile` 的 `col`/`row` 超出該層格數 | `ValueError`(不靜默回空陣列) |
| `to_png_bytes` 收到非 uint8 / 非 HxWx3 | `ValueError`(避免靜默產壞 PNG) |
| `array` 非 HxWx3 uint8 RGB | 契約假設 RGB uint8;非此形狀行為未定義(Tier B 信任契約,但 `to_png_bytes` 仍守門) |
| `tile_size <= 0` 或 `overlap < 0` | `ValueError`(非法參數,明確失敗) |
| `width`/`height <= 0` | `ValueError` |

設計原則:**幾何/層級超界以 `ValueError` 明確失敗(不靜默回空或裁到 0);合法但極端(1×1、非 2 次方、tile 大於圖)以可預期值收斂。** 不 mutate 輸入 `array`(PIL 從 array 複製)。

---

## 6. Acceptance Criteria(可被 pytest 驗,帶具體期望值)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_dzitiles.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import dzitiles`)。
> 共用合成陣列(供下列 AC 引用):
> ```python
> import numpy as np
> # 4x4 灰階遞增,擴成 RGB(三通道相等):值 = row*4 + col
> _g = np.arange(16, dtype=np.uint8).reshape(4, 4)
> ARR4 = np.stack([_g, _g, _g], axis=-1)        # shape (4,4,3) uint8
> # 4x4 區塊純色圖(供 BOX 降採樣手算):每個 2x2 區塊同色
> BLK = np.zeros((4, 4, 3), np.uint8)
> BLK[0:2, 0:2] = (10, 10, 10); BLK[0:2, 2:4] = (20, 20, 20)
> BLK[2:4, 0:2] = (30, 30, 30); BLK[2:4, 2:4] = (40, 40, 40)
> ```

### A. `num_levels` — 層數公式(釘死)
- **AC1**:`dzitiles.num_levels(4, 4) == 3`(`ceil(log2 4)+1 = 2+1`)。
- **AC2**:`dzitiles.num_levels(1, 1) == 1`(1×1 特例)。
- **AC3**:`dzitiles.num_levels(5, 3) == 4`(`ceil(log2 5)+1 = 3+1`;非 2 次方、用 max 邊)。
- **AC4**:`dzitiles.num_levels(256, 100) == 9`(`ceil(log2 256)+1 = 8+1`)。
- **AC5**:`dzitiles.num_levels(257, 1) == 10`(`ceil(log2 257)+1 = 9+1`,剛過 2 次方)。

### B. `level_dimensions` — 各層尺寸(釘死)
> 對 `4×4`(`max_level == 2`):level0=(1,1)、level1=(2,2)、level2=(4,4)。
- **AC6**:`dzitiles.level_dimensions(4, 4, 0) == (1, 1)`。
- **AC7**:`dzitiles.level_dimensions(4, 4, 1) == (2, 2)`。
- **AC8**:`dzitiles.level_dimensions(4, 4, 2) == (4, 4)`(最高層 == 原尺寸)。
> 對 `5×3`(`max_level == 3`):level0=(1,1)、level1=(2,1)、level2=(3,2)、level3=(5,3)。
- **AC9**:`dzitiles.level_dimensions(5, 3, 1) == (2, 1)`(`ceil(5/4),ceil(3/4)`)。
- **AC10**:`dzitiles.level_dimensions(5, 3, 2) == (3, 2)`(`ceil(5/2),ceil(3/2)`)。
- **AC11**:`dzitiles.level_dimensions(5, 3, 3) == (5, 3)`(最高層原尺寸)。
- **AC12**:`level_dimensions(4, 4, 3)` 與 `level_dimensions(4, 4, -1)` 各觸發 `pytest.raises(ValueError)`(超界)。

### C. `dzi_descriptor` — XML 字串(逐字釘死)
- **AC13**:`dzitiles.dzi_descriptor(4, 4)`(預設 tile_size=254、overlap=1、fmt="png")**逐字等於**
  ```
  <?xml version="1.0" encoding="UTF-8"?><Image xmlns="http://schemas.microsoft.com/deepzoom/2008" Format="png" Overlap="1" TileSize="254"><Size Height="4" Width="4"/></Image>
  ```
  (以 `==` 整串比對,含 xmlns、屬性順序 `Format`→`Overlap`→`TileSize`、`Size` 為 `Height`→`Width`)。
- **AC14**:`dzitiles.dzi_descriptor(5, 3, tile_size=2, overlap=0, fmt="png")` **逐字等於**
  ```
  <?xml version="1.0" encoding="UTF-8"?><Image xmlns="http://schemas.microsoft.com/deepzoom/2008" Format="png" Overlap="0" TileSize="2"><Size Height="3" Width="5"/></Image>
  ```
- **AC15**:`dzi_descriptor(4,4)` 中 `"\n" not in` 結果 且 `"\t" not in` 結果(無換行/tab,單行)。

### D. `tile` — 最高層(scale=1,精確切片)overlap=0(釘死像素)
> `ARR4` 全解析度 4×4,`level=2`(max_level)、`tile_size=2`、`overlap=0`:cols=2、rows=2,每片 2×2 精確切片。
- **AC16**:`t = dzitiles.tile(ARR4, 2, 0, 0, tile_size=2, overlap=0)`;`t.dtype == np.uint8`、`t.shape == (2, 2, 3)`,且 `np.array_equal(t[..., 0], np.array([[0, 1], [4, 5]], np.uint8))`(瓦片 0_0 = 左上 2×2)。
- **AC17**:`dzitiles.tile(ARR4, 2, 1, 0, tile_size=2, overlap=0)[..., 0]` 等於 `np.array([[2, 3], [6, 7]], np.uint8)`(瓦片 1_0 = 右上;col=1）。
- **AC18**:`dzitiles.tile(ARR4, 2, 0, 1, tile_size=2, overlap=0)[..., 0]` 等於 `np.array([[8, 9], [12, 13]], np.uint8)`(瓦片 0_1 = 左下;row=1)。
- **AC19**:`dzitiles.tile(ARR4, 2, 1, 1, tile_size=2, overlap=0)[..., 0]` 等於 `np.array([[10, 11], [14, 15]], np.uint8)`(瓦片 1_1 = 右下)。

### E. `tile` — 最高層 overlap=1(釘死 overlap 像素)
> 同 `ARR4` level=2、tile_size=2、**overlap=1**:每片往內部方向各擴 1 像素,邊界邊不擴。
- **AC20**:`t = dzitiles.tile(ARR4, 2, 0, 0, tile_size=2, overlap=1)`;`t.shape == (3, 3, 3)`(左/上碰邊不擴,右/下各 +1 → 3×3),且 `np.array_equal(t[..., 0], np.array([[0, 1, 2], [4, 5, 6], [8, 9, 10]], np.uint8))`(對應 `ARR4[0:3, 0:3]`)。
- **AC21**:`dzitiles.tile(ARR4, 2, 1, 0, tile_size=2, overlap=1)[..., 0]` 等於 `np.array([[1, 2, 3], [5, 6, 7], [9, 10, 11]], np.uint8)`(對應 `ARR4[0:3, 1:4]`:左側內擴 +1、右側碰邊不擴 → 3×3)。
- **AC22**:`dzitiles.tile(ARR4, 2, 1, 1, tile_size=2, overlap=1)[..., 0]` 等於 `np.array([[5, 6, 7], [9, 10, 11], [13, 14, 15]], np.uint8)`(對應 `ARR4[1:4, 1:4]`:左+上內擴,右+下碰邊 → 3×3)。

### F. `tile` — BOX 降採樣層(level<max,純色區塊可手算)
> `BLK`(4×4,2×2 區塊純色:TL=10、TR=20、BL=30、BR=40),`level=1` 尺寸 (2,2),BOX 降採樣後每像素 = 對應 2×2 區塊的精確平均(同色 → 該色本身)。`tile_size=2`、`overlap=0`:整層單片 2×2。
- **AC23**:`t = dzitiles.tile(BLK, 1, 0, 0, tile_size=2, overlap=0)`;`t.shape == (2, 2, 3)`,且 `np.array_equal(t, np.array([[[10,10,10],[20,20,20]],[[30,30,30],[40,40,40]]], np.uint8))`(BOX 把每 2×2 純色區塊精確降成 1 像素)。
- **AC24**:`dzitiles.tile(BLK, 0, 0, 0, tile_size=2, overlap=0).shape == (1, 1, 3)`(level0 = 1×1,單片)。

### G. `tile` — 超界與 tile_size 大於圖
- **AC25**:`dzitiles.tile(ARR4, 2, 2, 0, tile_size=2, overlap=0)` 觸發 `pytest.raises(ValueError)`(level2 cols=2,col=2 超界)。
- **AC26**:`dzitiles.tile(ARR4, 3, 0, 0, tile_size=2, overlap=0)` 觸發 `pytest.raises(ValueError)`(level3 超界,max_level=2)。
- **AC27**:`t = dzitiles.tile(ARR4, 2, 0, 0, tile_size=254, overlap=1)`;`t.shape == (4, 4, 3)` 且 `np.array_equal(t[..., 0], _g)`(tile_size 大於圖 → 單片 = 整層;overlap 被邊界全夾住,不外擴)。

### H. `build_tiles` — 完整金字塔結構(釘死格數與內容)
> `dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")` 設為 `R`。
- **AC28**:`R["width"] == 4`、`R["height"] == 4`、`R["tile_size"] == 2`、`R["overlap"] == 0`、`R["max_level"] == 2`、`R["num_levels"] == 3`。
- **AC29**:`R["dzi"] == dzitiles.dzi_descriptor(4, 4, tile_size=2, overlap=0, fmt="png")`(descriptor 一致)。
- **AC30**:`set(R["tiles"].keys()) == {0, 1, 2}`(層 key 為 int,0..max_level 齊備)。
- **AC31**:各層格數釘死 — `len(R["tiles"][0]) == 1`(level0 1×1→1 片)、`len(R["tiles"][1]) == 1`(level1 2×2,ceil(2/2)²=1 片)、`len(R["tiles"][2]) == 4`(level2 4×4,ceil(4/2)²=4 片)。
- **AC32**:`set(R["tiles"][2].keys()) == {"0_0", "1_0", "0_1", "1_1"}`(key 格式 `"{col}_{row}"`,col 在前)。
- **AC33**:level2 瓦片是真實 PNG bytes — `R["tiles"][2]["0_0"][:8] == b"\x89PNG\r\n\x1a\n"` 且 `isinstance(R["tiles"][2]["0_0"], bytes)`。
- **AC34**(PNG 真能被解回且像素一致,Tier B 真實 round-trip):
  ```python
  import io; from PIL import Image
  png = R["tiles"][2]["0_0"]
  back = np.asarray(Image.open(io.BytesIO(png)))
  assert back.shape == (2, 2, 3)
  assert np.array_equal(back[..., 0], np.array([[0, 1], [4, 5]], np.uint8))
  ```
  (證明瓦片 PNG 經瀏覽器級解碼後尺寸與像素零失真,非只看 bytes 非空)。

### I. `build_tiles` — 非 2 次方 / tile_size 大於圖
- **AC35**:`R5 = dzitiles.build_tiles(np.zeros((3,5,3),np.uint8), tile_size=2, overlap=0)`;`R5["num_levels"] == 4`、`set(R5["tiles"].keys()) == {0,1,2,3}`。
- **AC36**:承 AC35,level3 尺寸 (5,3) → cols=ceil(5/2)=3、rows=ceil(3/2)=2 → `len(R5["tiles"][3]) == 6`,且 `set(R5["tiles"][3].keys()) == {"0_0","1_0","2_0","0_1","1_1","2_1"}`。
- **AC37**:`R1 = dzitiles.build_tiles(np.zeros((1,1,3),np.uint8))`;`R1["num_levels"] == 1`、`set(R1["tiles"].keys()) == {0}`、`len(R1["tiles"][0]) == 1`、`list(R1["tiles"][0].keys()) == ["0_0"]`(1×1 退化:單層單片)。
- **AC38**:`Rbig = dzitiles.build_tiles(ARR4, tile_size=254, overlap=1)`;每層格數皆 1(tile_size 遠大於各層)→ `len(Rbig["tiles"][2]) == 1` 且 `set(Rbig["tiles"][2].keys()) == {"0_0"}`。

### J. `to_png_bytes` / `to_data_url`(真實可解碼)
- **AC39**:`b = dzitiles.to_png_bytes(np.zeros((2,2,3),np.uint8))`;`isinstance(b, bytes)` 且 `b[:8] == b"\x89PNG\r\n\x1a\n"`。
- **AC40**:`dzitiles.to_png_bytes(np.zeros((2,2,3),np.uint16))` 觸發 `pytest.raises(ValueError)`(非 uint8 守門)。
- **AC41**:`u = dzitiles.to_data_url(np.zeros((2,2,3),np.uint8))`;`u.startswith("data:image/png;base64,")` 且
  ```python
  import base64, io; from PIL import Image
  payload = base64.b64decode(u.split(",", 1)[1])
  assert payload[:8] == b"\x89PNG\r\n\x1a\n"
  assert np.asarray(Image.open(io.BytesIO(payload))).shape == (2, 2, 3)
  ```
  (base64 解回 → PIL 解碼 → 尺寸一致,坐實瀏覽器可解碼)。

### K. 非法參數
- **AC42**:`dzitiles.dzi_descriptor(0, 4)` 與 `dzitiles.num_levels(0, 4)` 各觸發 `pytest.raises(ValueError)`(width<=0)。
- **AC43**:`dzitiles.tile(ARR4, 2, 0, 0, tile_size=0)` 與 `dzitiles.tile(ARR4, 2, 0, 0, overlap=-1)` 各觸發 `pytest.raises(ValueError)`(tile_size<=0 / overlap<0)。

### L. `write_dzi` — 薄 write 包裝(磁碟佈局,@pytest.mark.e2e)
> 此 AC 觸碰真實檔案系統(I/O),標 `@pytest.mark.e2e`,交 `/ux-test` 或人觸發,不進 PG 自主修綠迴圈(依 CLAUDE.md「GUI/整合/外部編解碼模組」分層)。核心金字塔正確性已由 AC16–AC38(純函式、純記憶體)坐實。
- **AC44**(@pytest.mark.e2e):`p = dzitiles.write_dzi(tmp_path, ARR4, name="img", tile_size=2, overlap=0)`,則
  - `pathlib.Path(p).name == "img.dzi"` 且該檔存在,內容 == `dzitiles.dzi_descriptor(4, 4, tile_size=2, overlap=0)`;
  - `(tmp_path / "img_files" / "2" / "0_0.png").exists()` 為真,且其 bytes 前 8 byte == PNG magic;
  - level2 目錄含 4 個 `.png`(`0_0 1_0 0_1 1_1`),level0/level1 目錄各含 1 個 `.png`(OSD 標準 `<name>_files/<level>/<col>_<row>.<fmt>` 佈局)。

---

## 7. 給 `/pm` 的提示(契約鎖點)

- **AC13/AC14 是逐字 XML 比對**,不可退化成「含某子字串」;OSD 對 DZI schema 與屬性敏感,整串釘死才能保證 viewer 認得。
- **AC16–AC22(最高層精確切片 + overlap 內擴)** 是 overlap 規格的核心,不可省;**AC23(BOX 降採樣手算)** 鎖住縮放濾鏡選擇,**不可**改用 BILINEAR/LANCZOS(數值會變)。
- **AC34/AC41** 是 Tier B「真實 round-trip」核心(PNG/data_url 經 PIL 解回像素一致),不可退化成「bytes 非空」。
- **AC30–AC38** 鎖死「每層瓦片格數 = ceil(levelW/tile_size) × ceil(levelH/tile_size)」與 key 格式 `"{col}_{row}"`;格數錯 = viewer 缺瓦片黑塊。
- 例外型別固定:幾何/層級/參數超界 → `ValueError`,用 `pytest.raises` 驗。
- `write_dzi`(AC44)標 `@pytest.mark.e2e`,`gate.py` 只跑單元;核心正確性靠純函式 AC,write 包裝只驗佈局。

## 8. 與其他模組的邊界(防越權)

- **不負責** 影像載入 / 解碼 / 色彩轉換 / window-level(那是 `imgio`:檔案 → 顯示 RGB)。本模組吃的是已就緒的 `HxWx3 uint8` RGB 陣列(由 `imgio.to_display_rgb` 之類產出),**不 import `imgio`**。
- **不負責** OpenSeadragon 端的 DZI 載入 / 瓦片請求 / 可視區計算(那是 `viewer_component` / `app` 整合層;本模組只產出 OSD 能直接消費的 descriptor + tiles)。
- **不負責** HTTP 供圖伺服器(`write_dzi` 只把標準 DZI 佈局落磁碟;由誰用 HTTP 供應是整合層 / nativeApp engine 的事,見 PRD `03` 第 24 行)。
- **不負責** 座標換算 / viewport 幾何(那是 `viewport`)、ROI / 標註 / 比較(`roi` / `overlay` / `framecompare`)。
- 本模組對外承諾:核心純函式、確定性(BOX 濾鏡 + 釘死公式)、無副作用、**不 mutate 輸入 `array`**、僅依賴 `numpy`/`PIL`/標準庫、**零 import 任何業務模組**(可獨立平行驗收);唯一檔案副作用集中在 `write_dzi`。

## 9. 未決 / 留給下游

- viewer 接線(OSD 如何吃 data_url tiles vs HTTP DZI 目錄)由 `app` / `viewer_component` 整合層在 M5 接;本模組已備兩條出口(`to_data_url` 單片 / `write_dzi` 落磁碟)。
- `fmt` 目前契約只承諾 `"png"`(無損、可 round-trip 驗);`"jpeg"` 等有損格式若 User 後續需要(省頻寬),回 `/po` 排程再擴 `to_png_bytes` / `build_tiles` 的編碼分支與對應 AC。
- 超大圖(GB 級)的串流式逐層落磁碟(不一次 build 全部到記憶體)屬效能優化,MVP 不承諾;現契約 `build_tiles` 一次回全金字塔 dict,適用 viewer 單圖載入規模。
