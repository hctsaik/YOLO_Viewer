# 設計:imgadjust(Tier A,純邏輯)

> `/architect` 模組設計。純邏輯、零 I/O、零 GUI(`cv2` 為條件式相依,見 §4)。本文件是給 `/pm` 抓取的契約來源。
> 上游:`1_user_needs/06_cv_toolbox.md`。**這是純顯示層工具**——輸出只餵去畫面,不寫回 sidecar、不影響
> 偵測/判定/匯出;呼叫端(app)決定何時套用、套用順序(見 §3.4)。

---

## 1. 目的 (Purpose)

提供一組常見 CV 顯示調整的純函式(亮度/對比、gamma、直方圖均衡化、反色、對比度極限拉伸、二值化、
Canny 邊緣偵測),供 app 端「CV 工具箱」(平常收合)呼叫,幫助使用者在看圖當下臨時改善顯示效果。

---

## 2. I/O 契約(逐字採用,不得更動簽名)

純邏輯、不 mutate 輸入、不做 I/O、不寫檔。輸入輸出皆為 `uint8` RGB ndarray,shape `(H, W, 3)`。

```python
def brightness_contrast(img: np.ndarray, brightness: float = 0.0, contrast: float = 1.0) -> np.ndarray: ...
def gamma(img: np.ndarray, g: float = 1.0) -> np.ndarray: ...
def invert(img: np.ndarray) -> np.ndarray: ...
def stretch_contrast(img: np.ndarray) -> np.ndarray: ...
def equalize_histogram(img: np.ndarray) -> np.ndarray: ...
def threshold(img: np.ndarray, thresh: float = 128.0) -> np.ndarray: ...
def canny_edges(img: np.ndarray, low: float = 100.0, high: float = 200.0) -> np.ndarray: ...

HAS_CV2: bool  # 模組載入時偵測 cv2 是否可匯入;equalize_histogram/canny_edges 依此容錯降級(見 §4)
```

- 所有函式回傳**新陣列**(輸入 `img` 不被 mutate);輸出恆為 `(H, W, 3)` `uint8`,不論輸入是否已是灰階打三通道。
- 除 `canny_edges`(需真正邊緣偵測)外,所有函式**不依賴 cv2 才能運作**;僅 `equalize_histogram`/`canny_edges` 需要 cv2,缺 cv2 時容錯降級(見 §4b)。

---

## 3. 資料流 (Data Flow)

### 3.1 `brightness_contrast(img, brightness, contrast)`
`out = clip(round((img - 128) * contrast + 128 + brightness), 0, 255)`(逐 pixel、逐 channel)。
- 以 `128`(非 127.5)為對比支點,確保支點本身是乾淨整數、便於驗算(§5)。
- `brightness`:加法位移,常用範圍 `[-100, 100]`,無範圍限制(超界值一律 clip)。
- `contrast`:乘法係數,`1.0`=無變化,常用範圍 `[0.0, 3.0]`,無範圍限制。
- 四捨五入用 `np.round`(非截斷),避免「先乘除、卡在 .5」時的行為對呼叫端不直覺。

### 3.2 `gamma(img, g)`
標準 gamma correction:`out = round(255 * (img/255) ** (1/g))`。
- `g <= 0` 視為 `0.01`(避免除以 0 / 負次方,§4a)。
- `g == 1.0` 為單位映射(`table[i] == i` for all `i`,見 AC7)。
- `g > 1` 整體變亮(暗部提升較多);`g < 1` 整體變暗——此為標準 gamma 語義,非「數值越大越暗」的反向定義,呼叫端 UI 標籤需自行說明清楚(不在本模組職責)。

### 3.3 `invert(img)`
`out = 255 - img`(逐 pixel、逐 channel;`uint8` 減法在 numpy 會 wraparound,故先轉 `int16` 運算再轉回,避免非預期環繞)。

### 3.4 `stretch_contrast(img)`(對比度極限拉伸,min-max stretch)
逐 channel 各自拉伸:`out[:,:,c] = (img[:,:,c] - min_c) / (max_c - min_c) * 255`。
- `max_c == min_c`(該 channel 全同一值,如全黑/全白/單色圖)→ 該 channel **原樣輸出**(不除以 0,§4c)。

### 3.5 `equalize_histogram(img)`
轉 `YCrCb`,只對 `Y`(亮度)通道做直方圖均衡化(`cv2.equalizeHist`),轉回 `RGB`——**不對 R/G/B 三通道各自獨立均衡**(那會破壞色彩平衡、產生不自然的色偏,§4b 說明理由)。缺 cv2 時降級為「原樣回傳」(§4b)。

### 3.6 `threshold(img, thresh)`(二值化)
轉灰階(BT.601 加權:`0.299R + 0.587G + 0.114B`,對齊既有 `framediff` 模組同慣例),`> thresh → 255`、`<= thresh → 0`,結果複製到三通道回傳(維持 `(H,W,3)` 輸出形狀一致)。

### 3.7 `canny_edges(img, low, high)`
轉灰階(`cv2.cvtColor` BGR 慣例差異見 §4d)→ `cv2.Canny(gray, low, high)` → 白邊黑底單通道複製到三通道。缺 cv2 時降級為「原樣回傳」(§4b)。

### 3.8 呼叫端套用順序(app 職責,非本模組契約,供 PM/PG 參考)
使用者可能同時開啟多種調整(如亮度對比 + gamma);`threshold`/`canny_edges` 屬「終端替換」型(輸出取代原圖內容,不適合再疊加其他調色)。**建議固定管線順序**:`stretch_contrast → gamma → brightness_contrast → equalize_histogram → invert → threshold → canny_edges`(各自可獨立開關;`threshold`/`canny_edges` 若開啟,建議 app 端視為「終點」,忽略其後步驟——本模組不做互斥檢查,由 app 決定)。

---

## 4. 邊界條件與錯誤處理

a. **`gamma(img, g<=0)`**:視為 `g=0.01`,不拋例外、不除以 0。
b. **cv2 不可用**(`HAS_CV2=False`,環境未安裝):`equalize_histogram`/`canny_edges` 皆**原樣回傳輸入的複製品**(不崩潰、不假裝有效果);呼叫端(app)應在 UI 提示「此功能需要 opencv-python,目前不可用」而非靜默失效誤導使用者(app 職責,非本模組契約)。
c. **`stretch_contrast` 遇到單一值 channel**(`max==min`,如全黑圖):該 channel 原樣輸出,不除以 0、不拋例外。
d. **色彩空間**:本模組全程以 **RGB** 為輸入輸出慣例(對齊 `overlay.py`/`imgio.py` 既有慣例);`cv2` 函式預設吃 BGR,呼叫 `cv2.cvtColor`/`cv2.equalizeHist`/`cv2.Canny` 前後需要正確的 RGB↔BGR 轉換或等價處理,確保「輸入 RGB、輸出 RGB」對外契約不因借用 cv2 而破功(PG 實作與測試需驗證顏色通道順序正確,非只驗證數值形狀)。
e. **輸入非 `(H,W,3)` uint8**:契約假設呼叫端(app)只餵 `imgio.to_display_rgb` 產出的標準 RGB 陣列;Tier A 信任呼叫端,不做防禦性型別檢查(同 `overlay.py` 慣例)。
f. **灰階圖(RGB 三通道值相同)**:所有函式對此類輸入行為與一般彩色圖一致(無特殊分支),`equalize_histogram`/`stretch_contrast` 在三通道值相同時,YCrCb 的色度通道不受影響、三通道視覺上仍呈灰階(不會意外染色)。

---

## 5. Acceptance Criteria(可被 pytest 驗)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_imgadjust.py -p no:cacheprovider --strict-markers -q`。

**brightness_contrast**
- **AC1**:`brightness_contrast(img, 0.0, 1.0)` 對任意輸入為**單位映射**(輸出逐 pixel 等於輸入)。
- **AC2**(純亮度):`img` 全部像素為 `100`,`brightness_contrast(img, 50.0, 1.0)` → 全部像素 `150`。
- **AC3**(亮度封頂):`img` 全部像素為 `220`,`brightness_contrast(img, 50.0, 1.0)` → 全部像素 `255`(220+50=270 clip)。
- **AC4**(純對比,支點 128):`img` 全部像素為 `138`,`brightness_contrast(img, 0.0, 2.0)` → `(138-128)*2+128=148`,全部像素 `148`。
- **AC5**(對比 + 亮度封底):`img` 全部像素為 `108`,`brightness_contrast(img, 0.0, 2.0)` → `(108-128)*2+128=88`,全部像素 `88`(未觸底,驗證公式);另補一組觸底:`img` 全像素 `10`,同參數 → `(10-128)*2+128=-108` → clip `0`。
- **AC6**:輸出 dtype 為 `uint8`;輸入陣列本身不被 mutate(呼叫前後 `img` 內容相等)。

**gamma**
- **AC7**(單位映射):`gamma(img, 1.0)` 對任意輸入為單位映射(逐 pixel 等於輸入,含邊界 `0`/`255`)。
- **AC8**(端點不變):任意 `g>0`,像素值 `0` → `0`、像素值 `255` → `255`。
- **AC9**(`g<=0` 容錯):`gamma(img, -1.0)` 與 `gamma(img, 0.01)` 結果相同(視為同一 clamp 值),不拋例外。
- **AC10**(單調性):`g=2.0` 的 LUT(`gamma` 對 `0..255` 逐值)為單調不遞減。

**invert**
- **AC11**:`invert(img)` 對像素值 `0/128/255` 分別回 `255/127/0`。
- **AC12**(對合性,involution):`invert(invert(img))` 逐 pixel 等於原圖(浮點/整數運算不引入誤差)。

**stretch_contrast**
- **AC13**:單一 channel 輸入值域 `[50, 200]`(該 channel min=50,max=200)→ 拉伸後 min→`0`、max→`255`。
- **AC14**(除以 0 防護):輸入某 channel 全部同一值(如全部 `128`)→ 該 channel 原樣輸出(仍為 `128`,不拋例外、不變 `nan`)。

**equalize_histogram**
- **AC15**(cv2 可用時):輸出形狀/dtype 與輸入一致(`(H,W,3)` `uint8`);對全灰階輸入(R=G=B)不引入色偏(輸出仍 R=G=B)。
- **AC16**(cv2 不可用時,以 monkeypatch 模擬):回傳輸入的**複製品**(值相等、但非同一物件參考,防止呼叫端意外 mutate 到 cache 住的原圖)。

**threshold**
- **AC17**:像素灰階值(BT.601 加權)`> thresh` 者三通道皆為 `255`,`<= thresh` 者三通道皆為 `0`。
- **AC18**:輸出只含 `{0, 255}` 兩種值(無中間值)。

**canny_edges**
- **AC19**(cv2 可用時):輸出形狀 `(H,W,3)` `uint8`,且三通道相等(灰階邊緣圖複製而非誤用色彩)。
- **AC20**(cv2 不可用時,monkeypatch 模擬):回傳輸入的複製品(同 AC16 語義)。
- **AC21**(全平坦輸入無邊緣):輸入為單一顏色的純色圖 → 輸出全 `0`(無邊緣可偵測)。

**通用**
- **AC22**(不 mutate):所有函式呼叫前後,輸入陣列內容不變(`np.array_equal(before, after)`)。
- **AC23**(輸出型別/形狀不變性):所有函式對任意合法輸入,輸出 `dtype==uint8` 且 `shape==輸入shape`。

---

## 6. 與其他模組的邊界(防越權)

- **不負責**套用順序/UI/開關邏輯——那是 app(PG)的事;本模組只提供純函式。
- **不負責**寫入 sidecar、匯出檔案;純顯示層,呼叫端不得把調整後的結果誤存為判定依據。
- **不重複**`overlay.py`/`framediff.py` 的既有邏輯(灰階加權公式對齊 `framediff` 慣例,但不 import 它,維持 Tier A 解耦慣例)。
- 對外承諾:純函式、無副作用、輸入不被 mutate、僅依賴 numpy(+ 條件式 cv2);`equalize_histogram`/`canny_edges` 缺 cv2 時優雅降級,不拋例外。
