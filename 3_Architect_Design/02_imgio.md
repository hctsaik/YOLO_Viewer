# 02 — imageio(Tier B,M1b)技術設計

> `/architect` 產物(module 粒度)。承 PRD `2_PO_PRD/01`、增補 `03`、可行性 `3_Architect_Design/00`。
> 本檔只定義契約與驗收,**不含任何實作**。實作由 `/pg` 寫進 `5_PG_Develop/imageio.py`。

## 模組邊界 sanity check(開工前一句)
`imageio` 內聚一句話可講完(「把 8/16-bit、TIFF、大圖讀成可顯示 RGB 陣列 + 原始 pixel 取值 + 尺寸/位元深」),
無上游相依、不依賴 GUI,純讀寫 + 陣列轉換,**可獨立設計、可用 round-trip 真實讀寫驗收**。
不需與 `imageset`(資料夾清單/排序)或 `viewport`(純幾何座標換算)合併,亦無須再拆——
它們各自內聚、契約耦合少且不成環。**結論:範圍 OK,不退回 `/po`。**

---

## 1. 目的 (Purpose)
把磁碟上的 8/16-bit 灰階與 RGB 影像(`.png/.jpg/.tif/.tiff`)讀成「保留原始真值的 numpy 陣列 + 尺寸/位元深/通道數」,
並提供 window/level 顯示映射、原始取值、安全裁切、縮圖,以及把顯示影像編成 PNG bytes / data URL 給前端 viewer 元件。

## 2. 相依與限制
- 僅用:`numpy`、`Pillow(PIL)`、`tifffile`(讀 TIFF)、`cv2`(可選,非必要)、Python 標準庫(`io`、`base64`、`pathlib`)。
- **不可新增任何 pip 依賴。**
- 模組層級**零 GUI、零 Streamlit、零網路**;只做檔案讀寫與陣列/位元組轉換,故可被純 pytest round-trip 驗收。
- 進入點檔名:`5_PG_Develop/imageio.py`(測試 `import imageio` 取本模組——conftest 已把 `5_PG_Develop` 置於 `sys.path` 最前,遮蔽同名第三方套件;PG 模組內若需 PIL/標準庫請正常 import,勿命名衝突)。

---

## 3. I/O 契約(逐字採用,簽名為硬契約,/pm 直接鎖)

```python
def load(path) -> dict
# 回傳 {"array": np.ndarray, "width": int, "height": int, "bit_depth": int, "channels": int}
#   array: 灰階 = HxW uint8 或 uint16;RGB = HxWx3 uint8
#   width = array.shape[1];height = array.shape[0]
#   bit_depth ∈ {8, 16};channels ∈ {1, 3}
# 支援副檔名:.png .jpg .jpeg .tif .tiff(大小寫不敏感)
# 支援:8-bit 灰階、16-bit 灰階、8-bit RGB(三者皆 round-trip)
# 路徑不存在 → FileNotFoundError
# 存在但非影像/無法解碼 → ValueError

def to_display_rgb(array, lo=None, hi=None) -> np.ndarray   # 回 HxWx3 uint8
# window/level 顯示映射:
#   lo/hi 為 None 時用 array 的 min/max 自動 normalize 到 0..255
#   給定 lo/hi 時做線性 window:value<=lo → 0,value>=hi → 255,中間線性內插後 round 取整 clip 到 0..255
#   灰階(HxW)→ 複製成 3 通道(R=G=B)
#   已是 HxWx3 uint8 RGB → 原樣回傳(忽略 lo/hi)

def value_at(array, x, y) -> int | tuple
# 取「原始真值」(不是顯示值):
#   灰階 → int(8-bit 0..255;16-bit 0..65535)
#   RGB  → (r, g, b) 三個 int 的 tuple
#   x 為欄(column,對應 width),y 為列(row,對應 height)
#   超出邊界(x<0 或 y<0 或 x>=width 或 y>=height)→ IndexError

def crop(array, x, y, w, h) -> np.ndarray
# 安全裁切:回傳 array[y:y+h, x:x+w] 的對應區域,但所有座標先 clamp 進 [0, width]/[0, height]
#   不丟例外;完全在界外或 w<=0/h<=0 → 回傳 shape 第 0/1 維為 0 的空陣列(dtype/通道維與輸入一致)
#   保持 dtype 與通道結構(灰階回 2D、RGB 回 3D)

def to_png_bytes(rgb_uint8) -> bytes
# 把 HxWx3 uint8(或 HxW uint8 灰階)編成 PNG 檔位元組;回傳值以 PNG magic b"\x89PNG\r\n\x1a\n" 開頭

def to_data_url(rgb_uint8) -> str
# 回 "data:image/png;base64,<b64>";<b64> 為 to_png_bytes(rgb_uint8) 的 base64;可被瀏覽器 <img src> 直接解碼

def thumbnail(array, max_px=256) -> np.ndarray   # 回 HxWx3 uint8
# 先 to_display_rgb(array)(auto window/level)→ 等比例縮放使「長邊 <= max_px」
#   長邊 <= max_px 時不放大(只縮不放)
#   回 HxWx3 uint8;縮放後長邊精確 == max_px(當原長邊 > max_px)或 == 原長邊(當 <= max_px)
```

### 資料結構:`load` 回傳值
| key | 型別 | 不變量 |
|-----|------|--------|
| `array` | `np.ndarray` | 灰階 `ndim==2` dtype∈{uint8,uint16};RGB `ndim==3 且 shape[2]==3` dtype==uint8 |
| `width` | `int` | `== array.shape[1]` |
| `height` | `int` | `== array.shape[0]` |
| `bit_depth` | `int` | uint8→`8`;uint16→`16` |
| `channels` | `int` | 灰階→`1`;RGB→`3` |

---

## 4. 資料流 (Data Flow)

```
            ┌─ .png/.jpg ─► PIL.Image.open ─► np.asarray ─┐
 path ──────┤                                             ├─► 正規化形狀/dtype ─► load() dict
            └─ .tif/.tiff ─► tifffile.imread ────────────┘        (HxW uint8/16 或 HxWx3 uint8)
                                                                          │
   load()["array"] (原始真值,全解析度) ──────────────────────────────────┤
                                                                          │
   ├─ value_at(array,x,y) ───────────────► 原始 int / (r,g,b)            (查值,真值)
   ├─ crop(array,x,y,w,h) ──────────────► 原始 dtype 子陣列              (ROI/裁切,真值)
   └─ to_display_rgb(array,lo,hi) ──────► HxWx3 uint8 (8-bit 顯示)
            │                                   │
            ├─ to_png_bytes ─► PNG bytes ─► to_data_url ─► data:image/png;base64  (供 OSD/前端)
            └─ thumbnail(array,max_px) ─► HxWx3 uint8 (長邊<=max_px)               (縮圖牆)
```

要點:
- **真值路線**(`value_at`/`crop` 直接吃 `load` 的原始 `array`)與**顯示路線**(`to_display_rgb`→PNG/data_url/thumbnail 走 8-bit)分離;16-bit 真值永不因顯示映射而失真(呼應增補 03「server 端 window/level 顯示、原始真值點擊查」)。
- 顯示映射統一在 `to_display_rgb`;`thumbnail` 內部複用它,確保縮圖與主畫面同一套 normalize 規則。
- 16-bit → 8-bit 預設策略 = **auto min/max normalize**(PRD 開放問題 3 由本設計定案為 MVP 預設;手動 window/level 由 `lo/hi` 提供)。

---

## 5. 邊界條件與錯誤處理

| 情境 | 行為 |
|------|------|
| 路徑不存在 | `FileNotFoundError` |
| 檔案存在但非影像(如文字檔)/ 解碼失敗 | `ValueError` |
| 不支援副檔名 | `ValueError`(歸入「非影像」) |
| 16-bit RGB / RGBA / 浮點 / 調色盤等 | 不在 MVP 契約承諾內;允許 `ValueError`(範圍外輸入,不靜默誤判)。RGBA 若能安全去 alpha 可轉 RGB,否則 `ValueError`。 |
| `to_display_rgb` 全均勻影像(max==min) | 不可除以零;auto 模式回傳全 0 的 HxWx3 uint8(不丟例外) |
| `to_display_rgb` 給 `lo==hi` | 視為階梯:`value<lo`→0,`value>=lo`→255(不除零、不丟例外) |
| `to_display_rgb` 給 `lo>hi` | 範圍外輸入 → `ValueError` |
| `value_at` 座標超界 | `IndexError`(契約硬性) |
| `value_at` 座標為 float | 允許接受可轉 int 的值;非整數語意由呼叫端負責(契約以 int 座標定義) |
| `crop` 座標/寬高超界或為負 | **不丟例外**,clamp 進界內;完全界外或 w<=0/h<=0 → 空陣列(第 0/1 維為 0,dtype/通道維保持) |
| `thumbnail` 長邊 <= max_px | 只縮不放,維持原尺寸 |
| `thumbnail` 任一邊為 0 之退化輸入 | 允許 `ValueError`(範圍外) |
| `to_png_bytes`/`to_data_url` 收到非 uint8 / 形狀不符 | `ValueError`(避免靜默產生壞 PNG) |

設計原則:**查值/裁切(真值路線)以例外或安全 clamp 明確界定;顯示/編碼路線對「合法但極端」輸入(均勻、過小)以可預期值收斂,對「非法」輸入(lo>hi、非 uint8、非影像)以 `ValueError`/`FileNotFoundError`/`IndexError` 明確失敗,不靜默吞錯。**

---

## 6. Acceptance Criteria(可被 pytest 驗,帶具體期望值)

> 約定:測試以 numpy 合成資料 + `tmp_path` 寫出實體 `.png` / 16-bit `.tif` 再讀回驗證(真實檔案 round-trip,非只驗物件存在)。
> 寫檔工具:8-bit PNG/RGB 用 `PIL.Image`;16-bit 灰階 TIFF 用 `tifffile.imwrite`。

### A. `load` — 真實讀寫 round-trip
- **AC1**(8-bit 灰階 PNG round-trip):合成 `g8 = np.array([[0,128,255],[10,20,30]], np.uint8)`,以 PIL 存成 `tmp_path/g8.png` 後 `load`,結果 `d["bit_depth"]==8`、`d["channels"]==1`、`d["width"]==3`、`d["height"]==2`、`d["array"].dtype==np.uint8`、`d["array"].ndim==2` 且 `np.array_equal(d["array"], g8)`。
- **AC2**(16-bit 灰階 TIFF round-trip):合成 `g16 = np.array([[0,1000,65535],[40000,256,257]], np.uint16)`,`tifffile.imwrite(tmp_path/g16.tif, g16)` 後 `load`,結果 `d["bit_depth"]==16`、`d["channels"]==1`、`d["array"].dtype==np.uint16` 且 `np.array_equal(d["array"], g16)`(16-bit 真值不得被截成 8-bit)。
- **AC3**(8-bit RGB PNG round-trip):合成 `rgb = np.zeros((2,2,3),np.uint8); rgb[0,0]=[10,20,30]; rgb[1,1]=[200,100,50]`,存 PNG 後 `load`,結果 `d["channels"]==3`、`d["bit_depth"]==8`、`d["array"].shape==(2,2,3)` 且 `np.array_equal(d["array"], rgb)`。
- **AC4**(`.tiff` 副檔名亦可、大小寫不敏感):同 AC1 之 `g8` 存成 `tmp_path/G8.TIFF`(用 tifffile),`load` 成功且 `np.array_equal(d["array"], g8)`、`d["bit_depth"]==8`。
- **AC5**(不存在路徑):`load(tmp_path/"nope.png")` 拋 `FileNotFoundError`(用 `pytest.raises`)。
- **AC6**(非影像檔):`(tmp_path/"x.png").write_bytes(b"not an image")` 後 `load` 拋 `ValueError`。
- **AC7**(width/height 對齊 shape):對任一上面讀回的 `d`,`d["width"]==d["array"].shape[1]` 且 `d["height"]==d["array"].shape[0]`。

### B. `to_display_rgb` — window/level
- **AC8**(auto normalize 端點):`arr = np.array([[0,255]],np.uint8)`,`to_display_rgb(arr)` 之 dtype==uint8、shape==(1,2,3),且 `[...,0]` 在 `(0,0)`==0、`(0,1)`==255(min→0、max→255)。
- **AC9**(16-bit auto normalize):`arr = np.array([[100, 100, 4140]],np.uint16)`(min=100,max=4140),`out=to_display_rgb(arr)`,則 `out[0,0]==(0,0,0)`、`out[0,2]==(255,255,255)`、`out[0,1]==(0,0,0)`(值==min→0);形狀 (1,3,3) dtype uint8。
- **AC10**(手動 window/level 線性中點):`arr = np.array([[0,50,100]],np.uint16)`,`out=to_display_rgb(arr, lo=0, hi=100)`,則 `out[0,0,0]==0`、`out[0,2,0]==255`、`out[0,1,0]==128`(50/100*255=127.5,round→128)。
- **AC11**(window 截斷):`arr=np.array([[10,40,90]],np.uint16)`,`out=to_display_rgb(arr, lo=40, hi=80)`,則 `out[0,0,0]==0`(10<=lo)、`out[0,2,0]==255`(90>=hi)、`out[0,1,0]==0`(40==lo→0)。
- **AC12**(灰階→3 通道相等):承 AC8,`np.array_equal(out[...,0], out[...,1])` 且 `np.array_equal(out[...,1], out[...,2])`。
- **AC13**(RGB uint8 原樣):`rgb=np.array([[[10,20,30],[200,100,50]]],np.uint8)`,`to_display_rgb(rgb)` 與 `rgb` `np.array_equal`(忽略 lo/hi 不變更內容)。
- **AC14**(均勻影像不除零):`arr=np.full((2,2),7,np.uint8)`,`to_display_rgb(arr)` 不丟例外,回 shape (2,2,3) uint8 全 0。
- **AC15**(非法 lo>hi):`to_display_rgb(np.zeros((1,1),np.uint8), lo=200, hi=10)` 拋 `ValueError`。

### C. `value_at` — 原始真值
- **AC16**(灰階回 int 真值):`arr=np.array([[5,9],[12,40000]],np.uint16)`,`value_at(arr,0,0)==5`、`value_at(arr,1,0)==9`、`value_at(arr,1,1)==40000`(x=col、y=row),且回傳型別為 `int`(`isinstance(...,int)`,非 numpy scalar 亦可——以 `int(...)==` 驗值)。
- **AC17**(RGB 回 tuple):`rgb=np.zeros((2,2,3),np.uint8); rgb[1,0]=[7,8,9]`,`value_at(rgb,0,1)==(7,8,9)`(x=0,y=1 → row1,col0),回傳為長度 3 的 tuple。
- **AC18**(超界 IndexError):承 AC16(2x2),`value_at(arr,2,0)`、`value_at(arr,0,2)`、`value_at(arr,-1,0)` 皆拋 `IndexError`。

### D. `crop` — 安全 clamp 裁切
- **AC19**(界內精確):`arr=np.arange(16,dtype=np.uint8).reshape(4,4)`,`crop(arr,1,1,2,2)` 與 `arr[1:3,1:3]` `np.array_equal`(即 `[[5,6],[9,10]]`)。
- **AC20**(超界 clamp 不丟例外):同 `arr`,`crop(arr,2,2,10,10)` 回 shape `(2,2)`(clamp 到右下角 `arr[2:4,2:4]`)且 `np.array_equal` 該子陣列。
- **AC21**(完全界外回空陣列):`crop(arr,100,100,5,5)` 回傳 `np.ndarray`,`size==0` 且 `dtype==np.uint8`,不丟例外。
- **AC22**(負座標 clamp):`crop(arr,-5,-5,7,7)` 等同 `arr[0:2,0:2]`,`np.array_equal` 且 shape `(2,2)`。
- **AC23**(RGB 保留通道維):`rgb=np.zeros((4,4,3),np.uint8)`,`crop(rgb,0,0,2,2).shape==(2,2,3)`。

### E. `to_png_bytes` / `to_data_url` — 真實可解碼(round-trip)
- **AC24**(PNG magic):`b=to_png_bytes(np.zeros((3,3,3),np.uint8))`,`isinstance(b,bytes)` 且 `b[:8]==b"\x89PNG\r\n\x1a\n"`。
- **AC25**(PNG 真能被解回且像素一致):`rgb=np.zeros((2,2,3),np.uint8); rgb[0,0]=[10,20,30]; rgb[1,1]=[200,100,50]`;`png=to_png_bytes(rgb)`;用 `PIL.Image.open(io.BytesIO(png))` 解回 → `np.array_equal(np.asarray(img), rgb)`(證明瀏覽器級 PNG 解碼後像素不失真,非只看 bytes 非空)。
- **AC26**(data_url 前綴):`u=to_data_url(np.zeros((2,2,3),np.uint8))`,`u.startswith("data:image/png;base64,")` 且 `isinstance(u,str)`。
- **AC27**(data_url payload 解 base64 後等於 PNG 且可重新解碼):承 AC25 之 `rgb`,`u=to_data_url(rgb)`,`payload=base64.b64decode(u.split(",",1)[1])`;`payload[:8]==b"\x89PNG\r\n\x1a\n"` 且 `np.array_equal(np.asarray(PIL.Image.open(io.BytesIO(payload))), rgb)`。
- **AC28**(非 uint8 報錯):`to_png_bytes(np.zeros((2,2,3),np.uint16))` 拋 `ValueError`。

### F. `thumbnail` — 長邊縮放
- **AC29**(縮小:長邊精確 == max_px):`arr=np.zeros((100,400),np.uint16)`,`t=thumbnail(arr,max_px=200)`,`t.dtype==np.uint8`、`t.ndim==3 且 t.shape[2]==3`、`max(t.shape[0],t.shape[1])==200`、且短邊 `t.shape[0]==50`(等比例 100*200/400)。
- **AC30**(不放大):`arr=np.zeros((30,40,3),np.uint8)`,`thumbnail(arr,max_px=256).shape==(30,40,3)`(長邊 40<=256,維持原尺寸)。
- **AC31**(預設 max_px=256 生效):`arr=np.zeros((512,1024),np.uint8)`,`thumbnail(arr)` 之 `max(shape[:2])==256` 且短邊 `==128`。

---

## 7. 給 `/pm` 的提示(契約鎖點)
- AC1/AC2/AC3/AC25/AC27 是「**真實讀寫 / round-trip**」核心,**不可**退化成只驗「回傳非空 / 物件存在」。
- 16-bit 不失真(AC2、AC9、AC16)是本模組存在價值,必須有專屬斷言。
- 例外型別固定:不存在→`FileNotFoundError`、非影像/範圍外→`ValueError`、座標超界→`IndexError`,用 `pytest.raises` 驗。
- 本模組 **無 E2E 需求**(零 GUI/網路);單元 round-trip 即構成 Tier B 的真實 I/O 驗收。`to_data_url` 的瀏覽器可解碼性已由 AC27「base64 解回 → PIL 解碼 → 像素一致」在單元層坐實。
- 測試置於 `4_PM_Feedback/test_imageio.py`;跑:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_imageio.py -p no:cacheprovider --strict-markers -q`。

## 8. 未決 / 留給下游
- RGBA / 16-bit RGB / 浮點 / 調色盤影像:MVP 範圍外(允許 `ValueError`);若 User 後續需要,回 `/po` 排程再擴 `load` 契約。
- 連續 hover 真值(把整張 16-bit 送進前端元件)屬 Phase 2(見增補 03);本模組僅負責「點擊查值」所需的 `value_at` 真值能力。
