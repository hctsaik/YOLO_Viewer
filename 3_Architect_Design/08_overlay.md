# 設計:overlay(M3 / Tier A,純邏輯 numpy)

> `/architect` 模組設計。純邏輯、零 I/O、零 GUI。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死數值/行為。
> 上游:`2_PO_PRD/01` §3 M3(第 52 行 `overlay`)、`ROADMAP.md`(第 35 行 + 第 40~43 行「M3 共用契約」)。
> 相依:**只依「資料形狀」`Detection` dict**,**嚴禁 import yolo / sidecar / tagging**(解耦、可獨立平行驗收;測試一律以 dict 模擬)。
> 下游:`/pm` 依本檔 AC 落成 `4_PM_Feedback/test_overlay.py`;`/pg` 依 I/O 契約實作 `5_PG_Develop/overlay.py`。

---

## 開工前 sanity check(切分是否成立)

`overlay` 能獨立設計與驗收:它是一組**無狀態純函式**,輸入是「RGB uint8 numpy 陣列 + `list[Detection]`(dict)」,輸出是「新的 numpy 陣列 / 篩選後的 list」。職責一句話:**在影像上畫 bbox(+可選 class/conf 標籤),並依 conf 門檻 / class 篩選**。

- 與 `yolo` 的界線:`yolo` 是唯一「**產生** `Detection` 形狀」者(讀 JSON、容錯);`overlay` 是「**消費**」者,只依資料形狀、不 import。兩者不重疊、不成環,**不應合併**。
- 與 `roi` 的界線:`roi` 做使用者手繪 ROI 框的幾何/裁切;`overlay` 做模型偵測結果的繪製/篩選。資料來源不同(人 vs 模型)、用途不同(裁切 vs 視覺化),**不需合併**。
- 與 `framecompare` 的界線:`framecompare` 做兩張圖的合成/差異;`overlay` 只在單張圖上疊框。彼此正交。

結論:切分成立,正常進行,**不觸發反向閘門**。

---

## 1. 目的 (Purpose)

在 RGB uint8 影像陣列上,依 conf 門檻 / class 篩選後畫出每個 `Detection` 的 bbox(可選 class/conf 文字標籤),回傳**新陣列**(輸入不被 mutate),作為 app 模型疊圖層與匯出縮圖的共用繪製底座。

---

## 2. I/O 契約 (逐字採用,不得更動簽名)

模組:`5_PG_Develop/overlay.py`(實作層,本檔不產出)。僅依賴 `numpy` 與 Python 標準庫。**嚴禁 import yolo/sidecar/tagging。**

### 2.1 共用資料形狀(PO 釘死,逐字採用)

```python
# 一筆偵測(dict;本模組只讀下列三鍵)
Detection = {
    "bbox": [x, y, w, h],   # 絕對像素,左上原點;x 向右、y 向下;數值為 int 或 float(內部一律 int() 截斷取整)
    "cls":  str,            # 類別字串
    "conf": float,          # 0~1 信心值
}
```

> 本模組**只讀** `Detection` 的 `bbox` / `cls` / `conf` 三鍵;不寫、不持久化。`cls`/`conf` 在 `draw` 不畫標籤時可缺(見 §4)。`filter_detections` 需讀 `conf`(缺 → 視同 `0.0`,見 §4c)與 `cls`(缺 → 視同 `None`,見 §4d)。

### 2.2 影像陣列契約

- **array**:`numpy.ndarray`,**dtype `uint8`**,形狀 `(H, W, 3)`(RGB,通道順序 R,G,B)。索引慣例 `array[row=y, col=x, channel]`(與 `roi` 一致)。
- **color**:長度 3 的序列 `(R, G, B)`,各元素 `int` 0~255。
- 本模組不負責 dtype/通道數轉換(那是 `imgio`);契約假設呼叫端已給 `(H,W,3) uint8`。

### 2.3 函式簽名(逐字採用,不得更動)

```python
# class → 顏色 的內建對照(契約值,釘死;見 §2.4)
CLASS_COLORS: dict[str, tuple]      # {cls_name: (R,G,B)}
DEFAULT_COLOR: tuple = (255, 0, 0)  # 未在 CLASS_COLORS 命中、且未顯式給 color 時的回退色(紅)

def filter_detections(dets, conf_threshold=0.0, classes=None) -> list:
    # 保留 conf >= conf_threshold 且 (classes is None 或 cls in classes) 者
    # 保序、不 mutate;回新 list,元素為原 dict 物件的參照(淺層,不複製 dict)
    ...

def color_for(det, color=None) -> tuple:
    # 決定一筆 det 的繪製顏色:color 顯式給 → 用之;否則 CLASS_COLORS.get(det["cls"], DEFAULT_COLOR)
    ...

def draw(array, dets, color=None, thickness=1, conf_threshold=0.0,
         classes=None, draw_label=False) -> np.ndarray:
    # 回新陣列(輸入不被 mutate)。先 filter_detections(dets, conf_threshold, classes),
    # 再對每個通過者畫 bbox(座標夾到影像邊界);draw_label=True 時另畫 class/conf 文字(策略見 §3.4)。
    ...
```

### 2.4 模組常數(契約值,釘死)

- `DEFAULT_COLOR == (255, 0, 0)`(R,G,B 紅)。
- `CLASS_COLORS` 至少含下列三筆固定對映(供 AC 釘值;未列之 cls 一律回退 `DEFAULT_COLOR`):

  | `cls` | 顏色 (R,G,B) |
  |-------|--------------|
  | `"defect"`  | `(255, 0, 0)`   |
  | `"scratch"` | `(0, 255, 0)`   |
  | `"dent"`    | `(0, 0, 255)`   |

> 顏色策略:`draw` 的 `color` 參數**顯式給定時對所有框生效**(覆蓋 class 對照);`color=None`(預設)時每框依 `color_for` 用 `CLASS_COLORS`(命中)或 `DEFAULT_COLOR`(未命中)。

---

## 3. 資料流 (Data Flow)

### 3.1 `filter_detections(dets, conf_threshold=0.0, classes=None) -> list`
逐筆判定,**AND** 合併,**保序**輸出:
1. conf 條件:`float(det.get("conf", 0.0)) >= conf_threshold`。
2. class 條件:`classes is None`(不篩)**或** `det.get("cls", None) in classes`。
兩條件皆成立才保留。回**新 list**(不修改 `dets` 本身,亦不複製其中的 dict)。`conf_threshold == 0.0` 且 `classes is None` → 全保留(保序)。

### 3.2 `color_for(det, color=None) -> tuple`
- `color is not None` → 直接回 `tuple(color)`。
- 否則 → 回 `CLASS_COLORS.get(det.get("cls"), DEFAULT_COLOR)`(命中用對照色,未命中或無 `cls` 用 `DEFAULT_COLOR`)。

### 3.3 `draw(...) -> np.ndarray`(核心,釘死繪製語義)
1. `out = array.copy()`(輸入永不 mutate;後續只寫 `out`)。
2. `kept = filter_detections(dets, conf_threshold, classes)`。
3. 對 `kept` 中每筆 `det`(**依輸入順序**,後畫者覆蓋先畫者的重疊像素):
   a. 取整:`x, y, w, h = int(det["bbox"][0]), int(det["bbox"][1]), int(det["bbox"][2]), int(det["bbox"][3])`。
   b. **半開區間**:框覆蓋像素為 `x <= col < x+w` 且 `y <= row < y+h`(與 `roi` 半開語義一致)。框的四條外框邊界線定義為:
      - 上邊:`row == y`、左邊:`col == x`、下邊:`row == y+h-1`、右邊:`col == x+w-1`(皆在框的最外圈像素上)。
   c. **夾界**:把要寫的像素索引夾到 `0 <= row < H`、`0 <= col < W`;**超出影像的部分不寫、不拋例外**(只畫可見部分)。
   d. `thickness` 為邊框粗細(向**框內**加厚):粗細 `t` 表示外框內縮 `0..t-1` 圈皆塗色(`t >= min(w,h)` 時整框實心填滿;`t <= 0` → 不畫任何像素)。
   e. 顏色 = `color_for(det, color)`,寫成 `out[row, col, :] = color`。
4. 若 `draw_label`,對每筆 `det` 額外畫文字標籤(策略見 §3.4)。
5. 回 `out`。

> **不變量**:`draw` 回傳 `out is not array`(新物件),`out.shape == array.shape`、`out.dtype == array.dtype == uint8`;`array`(輸入)逐像素不變。

### 3.4 標籤策略(`draw_label=True`)
- 標籤文字 = `f"{det.get('cls','')} {float(det.get('conf',0.0)):.2f}"`(class 與兩位小數 conf;`cls` 缺 → 空字串)。
- 標籤以該框顏色,畫在框**上緣外側**(`row` 從 `y-LABEL_H` 起;`LABEL_H` 由實作定的小常數)起的矩形帶或字形像素;**超出影像邊界的部分一律夾掉、不拋例外**。
- 文字字形/精確像素**不列為釘值 AC**(避免脆弱);標籤的可驗收性僅以「不影響 `draw_label=False` 時的 bbox 像素」「`draw_label=True` 不拋例外、回傳形狀/型別不變」「空 dets 仍逐像素等於輸入」三點約束(見 AC)。

---

## 4. 邊界條件與錯誤處理

a. **空 dets(`[]`)**:`filter_detections([], ...) == []`;`draw(array, [], ...)` 回**逐像素等於輸入**的新陣列(且 `out is not array`)。
b. **全被濾掉**(`conf_threshold` 高到無人通過,或 `classes` 不含任何 det 的 cls):`draw` 輸出**逐像素等於輸入**(只 copy 不畫)。
c. **`conf` 缺鍵**:`filter_detections` 與 `draw` 內視同 `0.0`(`det.get("conf", 0.0)`);`conf_threshold=0.0`(預設)時仍通過(`0.0 >= 0.0`)。
d. **`cls` 缺鍵**:`classes is None` 時不受影響;`classes` 有給時 `det.get("cls", None) in classes`(缺 cls → `None`,除非 `None in classes` 否則不通過);`color_for` 缺 cls → `DEFAULT_COLOR`。
e. **bbox 超出影像邊界 / 部分在外 / 負座標**:依 §3.3c 夾界,**只畫可見部分、不拋例外**;完全在影像外的框 → 不寫任何像素(等同未畫)。
f. **bbox 寬或高為 0 或負**(`w <= 0` 或 `h <= 0`):視為無可見框,**不畫、不拋例外**(半開區間下覆蓋像素為空集)。
g. **`thickness <= 0`**:該框不畫任何像素(不拋例外)。
h. **不 mutate 不變式**:`filter_detections` 不改 `dets`(list 與其中 dict);`draw` 不改 `array`(以呼叫前後 `np.array_equal` / deepcopy 驗證)。
i. **dtype/形狀**:契約假設 `(H,W,3) uint8`;本模組不做型別防禦(Tier A 純邏輯,信任契約)。`color` 各分量假設 0~255 int。
j. **顏色覆蓋**:多框重疊時,**後畫者(list 中較後者)覆蓋先畫者**重疊像素(§3.3 step 3 順序)。

---

## 5. Acceptance Criteria(可被 pytest 驗;測試以 numpy 陣列 + dict 模擬)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_overlay.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import overlay`)。
> 像素級 AC 統一用「全黑畫布」`img = np.zeros((10, 10, 3), dtype=np.uint8)`,框與顏色全部釘死,半開區間 + 邊框定義見 §3.3b。

**常數契約**
- **AC1**:`overlay.DEFAULT_COLOR == (255, 0, 0)`。
- **AC2**:`overlay.CLASS_COLORS["defect"] == (255,0,0)` 且 `overlay.CLASS_COLORS["scratch"] == (0,255,0)` 且 `overlay.CLASS_COLORS["dent"] == (0,0,255)`。

**color_for**
- **AC3**:`overlay.color_for({"cls":"scratch"}) == (0,255,0)`(命中對照)。
- **AC4**:`overlay.color_for({"cls":"unknown_xyz"}) == (255,0,0)`(未命中 → DEFAULT_COLOR)。
- **AC5**:`overlay.color_for({"cls":"scratch"}, color=(7,8,9)) == (7,8,9)`(顯式 color 覆蓋對照)。
- **AC6**:`overlay.color_for({}) == (255,0,0)`(無 cls → DEFAULT_COLOR,不拋例外)。

**filter_detections — conf / class / 保序 / 不 mutate**
- **AC7**:`overlay.filter_detections([{"cls":"a","conf":0.9},{"cls":"b","conf":0.3}], conf_threshold=0.5) == [{"cls":"a","conf":0.9}]`(過濾低 conf;`0.3 < 0.5` 被除、`0.9 >= 0.5` 保留)。
- **AC8**:邊界相等保留 —— `len(overlay.filter_detections([{"cls":"a","conf":0.5}], conf_threshold=0.5)) == 1`(`0.5 >= 0.5`)。
- **AC9**:`overlay.filter_detections([{"cls":"a","conf":0.9},{"cls":"b","conf":0.9}], classes=["a"]) == [{"cls":"a","conf":0.9}]`(class 篩選)。
- **AC10**:`classes=None`(預設)+ `conf_threshold=0.0`(預設)→ `len(overlay.filter_detections([{"cls":"a","conf":0.0},{"cls":"b","conf":1.0}])) == 2`(全保留;`0.0>=0.0`)。
- **AC11**:保序 —— 對 `d=[{"cls":"a","conf":0.9},{"cls":"b","conf":0.8},{"cls":"c","conf":0.95}]`,`[x["cls"] for x in overlay.filter_detections(d, conf_threshold=0.85)] == ["a","c"]`(保留原相對順序)。
- **AC12**:conf 缺鍵視同 0.0 —— `overlay.filter_detections([{"cls":"a"}], conf_threshold=0.0) == [{"cls":"a"}]` 且 `overlay.filter_detections([{"cls":"a"}], conf_threshold=0.1) == []`。
- **AC13**:不 mutate —— 呼叫 `filter_detections(d, conf_threshold=0.5)` 後,原 `d`(list 與其中 dict)以 deepcopy 比對不變,且回傳值 `is not d`(新 list 物件)。

**draw — 像素級交叉驗證(全黑 10×10,釘死座標與顏色)**
> 設 `img = np.zeros((10,10,3), np.uint8)`。畫一個 `bbox=[2,3,4,5]`(x=2,y=3,w=4,h=5)、`thickness=1`、`color=(255,0,0)` 的框。
> 由 §3.3b:左邊 col=2、右邊 col=2+4-1=5、上邊 row=3、下邊 row=3+5-1=7。框外圈像素如下釘死。
- **AC14**(上邊角):`out[3,2].tolist() == [255,0,0]`(左上角,row=3,col=2 在框上)。
- **AC15**(右下角):`out[7,5].tolist() == [255,0,0]`(右下角,row=7,col=5 在框上)。
- **AC16**(邊上中段):`out[3,4].tolist() == [255,0,0]`(上邊 row=3 上一點 col=4 在框上)且 `out[5,2].tolist() == [255,0,0]`(左邊 col=2 上一點 row=5 在框上)。
- **AC17**(框內部空心):`thickness=1` 時 `out[5,4].tolist() == [0,0,0]`(框內部 row=5,col=4 未被塗,空心邊框)。
- **AC18**(框外仍黑):`out[0,0].tolist() == [0,0,0]` 且 `out[9,9].tolist() == [0,0,0]` 且 `out[2,2].tolist() == [0,0,0]`(框上緣外一列 row=2 仍黑)。
- **AC19**(輸入未被 mutate):上述 `draw` 後 `img` 仍為全 0(`np.array_equal(img, np.zeros((10,10,3), np.uint8))`),且回傳 `out is not img`。
- **AC20**(回傳形狀/型別):`out.shape == (10,10,3)` 且 `out.dtype == np.uint8`。

**draw — class→顏色(color=None 時用對照)**
- **AC21**:在全黑 10×10 上 `draw(img, [{"bbox":[2,3,4,5],"cls":"scratch","conf":1.0}])`(不給 color)→ `out[3,2].tolist() == [0,255,0]`(綠,scratch 命中對照)。
- **AC22**:`draw(img, [{"bbox":[2,3,4,5],"cls":"unknown","conf":1.0}])` → `out[3,2].tolist() == [255,0,0]`(未命中 → DEFAULT_COLOR 紅)。
- **AC23**:顯式 `color=(0,0,255)` 對所有框生效覆蓋對照 —— `draw(img, [{"bbox":[2,3,4,5],"cls":"scratch","conf":1.0}], color=(0,0,255))` → `out[3,2].tolist() == [0,0,255]`。

**draw — thickness**
- **AC24**(實心填滿):`thickness` 夠大(如 `thickness=10`)時 `draw(img, [{"bbox":[2,3,4,5],...}], color=(255,0,0), thickness=10)` 使框內部也被塗 —— `out[5,4].tolist() == [255,0,0]`(對照 AC17 的空心)。
- **AC25**(thickness<=0 不畫):`draw(img, [{"bbox":[2,3,4,5],...}], color=(255,0,0), thickness=0)` 逐像素等於輸入(`np.array_equal(out, img)`)。

**draw — 篩選貫穿(conf / class 與 filter_detections 一致)**
- **AC26**:`draw(img, [{"bbox":[2,3,4,5],"cls":"a","conf":0.2}], color=(255,0,0), conf_threshold=0.5)` → `np.array_equal(out, img)`(被 conf 濾掉 → 不畫,逐像素等於輸入)。
- **AC27**:`draw(img, [{"bbox":[2,3,4,5],"cls":"a","conf":1.0}], color=(255,0,0), classes=["b"])` → `np.array_equal(out, img)`(被 class 濾掉 → 不畫)。

**draw — 可推導不變量(metamorphic;給 /pm 的提示落成的 AC)**
- **AC28**(空 dets 逐像素等於輸入):任給非全黑輸入 `base = np.arange(10*10*3, dtype=np.uint8).reshape(10,10,3)`,`np.array_equal(overlay.draw(base, []), base) == True`(且回傳 `is not base`)。
- **AC29**(全濾掉逐像素等於輸入):`np.array_equal(overlay.draw(base, [{"bbox":[1,1,3,3],"cls":"a","conf":0.1}], conf_threshold=0.9), base) == True`(門檻濾光 → 不動)。
- **AC30**(bbox 超界只畫可見部分、不拋例外):`draw(img, [{"bbox":[8,8,5,5],"cls":"a","conf":1.0}], color=(255,0,0))` **不拋例外**,且 `out[8,8].tolist() == [255,0,0]`(框左上角在界內被畫),`out[9,9].tolist()` 為合法 uint8(界內最後一格,不越界存取)。
- **AC31**(完全在影像外不畫不拋):`draw(img, [{"bbox":[100,100,5,5],"cls":"a","conf":1.0}], color=(255,0,0))` 不拋例外且 `np.array_equal(out, img) == True`。
- **AC32**(負座標夾界):`draw(img, [{"bbox":[-3,-3,5,5],"cls":"a","conf":1.0}], color=(255,0,0))` 不拋例外;框可見部分(右下角區域)被畫且界外負索引不被寫(`out` 中所有被改像素 row/col 皆 `>=0`;以「輸入為全黑、改動處皆等於 color」驗證無環繞寫入)。
- **AC33**(w/h 非正不畫):`draw(img, [{"bbox":[2,3,0,5],"cls":"a","conf":1.0}], color=(255,0,0))`(w=0)與 `draw(img, [{"bbox":[2,3,4,0],...}])`(h=0)皆 `np.array_equal(out, img) == True`(無可見框)。

**draw — 重疊覆蓋(順序語義)**
- **AC34**:兩框重疊時後畫者覆蓋 —— `draw(img, [{"bbox":[2,2,4,4],"cls":"a","conf":1.0},{"bbox":[2,2,4,4],"cls":"a","conf":1.0}], color=None)`,第二框與第一框同位但本 AC 以「先紅後綠」驗證:`draw(img, [{"bbox":[2,2,4,4],"cls":"defect","conf":1.0},{"bbox":[2,2,4,4],"cls":"scratch","conf":1.0}])` → `out[2,2].tolist() == [0,255,0]`(scratch 綠,後畫覆蓋 defect 紅)。

**draw_label — 不破壞 bbox 像素、不拋例外**
- **AC35**:`draw(img, [{"bbox":[2,3,4,5],"cls":"defect","conf":0.87}], draw_label=True)` **不拋例外**,回傳 `out.shape == (10,10,3)` 且 `out.dtype == np.uint8`;且框邊像素 `out[3,2].tolist() == [255,0,0]`(畫標籤不影響 bbox 邊像素值)。
- **AC36**:`draw_label=True` 對**空 dets** 仍逐像素等於輸入 —— `np.array_equal(overlay.draw(base, [], draw_label=True), base) == True`。

---

## 6. 與其他模組的邊界(防越權)
- **不負責**讀檔 / 解析 YOLO 輸出(那是 `yolo`:JSON→`list[Detection]`,容錯);本模組**不 import yolo**,只吃 dict。
- **不負責**陣列 dtype / 通道 / bit 深度轉換(那是 `imgio`);本模組假設輸入已是 `(H,W,3) uint8`。
- **不負責**使用者手繪 ROI 幾何 / 裁切(那是 `roi`);本模組只繪製模型偵測框。
- **不負責**雙圖合成 / 差異(那是 `framecompare`)。
- 本模組對外承諾:純函式、無副作用、**輸入陣列與輸入 dets 皆不被 mutate**、僅依賴 `numpy` 與標準庫、**不 import 任何專案內其他模組**。
