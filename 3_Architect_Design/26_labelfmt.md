# 26 · labelfmt — 多格式標註自動偵測(COCO / VOC / LabelMe / NDJSON)

> 需求:`1_user_needs/08_multi_format_annotations.md`;PO 裁決見 ROADMAP「M8」決策日誌。
> 來源:port 自使用者另一專案 `C:\code\claude\LV\visuallatent\scripts\label_formats.py`(純 stdlib + PIL、已測),
> 加一層 adapter 轉成 CV_Viewer 既有 `Detection` 形狀。**YOLO `.txt`/`.json` 仍走既有 `yolo.load`**,不由本模組處理。

## 1. 角色與邊界(Tier A)
- **純邏輯**:僅依賴 Python 標準庫 + PIL(讀影像標頭補尺寸);**永不拋例外**;不寫任何檔、不 mutate 輸入。
- 不 import 任何業務模組(overlay/yolo/sidecar…);輸出即 CV_Viewer 跨模組共用的
  `Detection = {"bbox":[x,y,w,h] 絕對像素 int(左上原點), "cls":str, "conf":float(0~1)}`。
- 與 `cocoio` 職責分離:cocoio = 匯入/匯出(round-trip);labelfmt = **讀取為顯示的自動偵測**。
  COCO 解析小幅重複可接受(不動 cocoio 契約)。

## 2. 對外契約(API)
```
load_for_image(image_path, img_w, img_h) -> list[Detection] | None
folder_has_annotations(folder, probe=25) -> bool
```
- `load_for_image`:依序試 **COCO → VOC → LabelMe → NDJSON**,任一「來源」命中即回該圖的 `list[Detection]`。
  - 回 `None` = 找不到任何(非 YOLO-txt)標註**來源** → 呼叫端應退回 `yolo.load`(.json/.txt)。
  - 回 `[]` = 有來源但**該影像**無框(語義同 YOLO「檔在但空」)。
  - `img_w`/`img_h`:目前顯示影像的實際寬高(正整數);把各格式的正規化框換算成絕對像素用。
- `folder_has_annotations`:資料夾是否帶任一支援格式(供 sidebar caption 顯示「偵測到 COCO/VOC…」)。

### 2.1 內部正規化 rows → Detection 的 adapter(唯一新增邏輯)
各解析器沿用 LV 的中間形狀 `row = (cid|None, cx, cy, w, h, score, name|None)`(cx,cy,w,h ∈ 0~1)。
`_row_to_det(row, W, H)`:
- `bbox = [int((cx - w/2)*W), int((cy - h/2)*H), int(w*W), int(h*H)]`(int 向 0 截斷,對齊 yolo.load §4.e)
- `cls = name if name else (f"class_{cid}" if cid is not None else "")`
- `conf = score if score is not None else 1.0`(超界夾到 0~1)

## 3. 各格式偵測與解析(port 自 LV,行為逐條保留)

### 3.1 COCO JSON
- 檔名候選(影像 `parent` 或 `parent.parent`,涵蓋平鋪與 `images/` 佈局):
  `_annotations.coco.json`(Roboflow)、`annotations.json`、`coco.json`。
- `categories` 建 id→name(容**非連號 id**);每筆 annotation 用 `images[image_id].width/height` 把
  絕對 `bbox=[x,y,w,h]` 正規化;`score` 存在則帶入(→ conf),否則 None(→ 1.0)。缺尺寸/w≤0/h≤0 跳過。

### 3.2 Pascal VOC XML
- 位置:同名 `.xml`、或 `Annotations/`、`annotations/`(本層或上一層,涵蓋經典 VOC 的 `JPEGImages/` 佈局)。
- `<size>` 取 W/H,缺就開影像讀標頭補;每 `<object>` 讀 `name` + `bndbox(xmin,ymin,xmax,ymax)` → 正規化 xywh。
- 名稱制(無數字 id,`cid=None`;類名即 `name`)。

### 3.3 LabelMe JSON
- 同名 `.json` 且頂層有 `shapes` list 才算 LabelMe(否則回 None,讓呼叫端試別的來源——**與 YOLO 的 .json 不衝突**)。
- `rectangle` 用兩角;`polygon` 等多點取外接框;`imageWidth`/`imageHeight` 為尺寸。

### 3.4 NDJSON / JSONL(一行一圖)
- 資料夾根層(本層或上一層)的 `*.ndjson`/`*.jsonl`,**內容抽樣驗證**(前 50 行至少一行同時有影像鍵 +
  「含 dict 的框清單」)才採;排除 `manifest.jsonl`(本 app 資料契約檔,非標註)。
- 影像鍵別名:`image`/`image_path`/`file_name`/`filename`/`source-ref`/`path`;框清單鍵:`boxes`/`annotations`/`objects`/`bboxes`;
  每框 label 別名:`label`/`class`/`name`/`category`(或 `class_id` → `class_<id>`)。
- **4 種 bbox 慣例**:`bbox=[x,y,w,h]`(像素)、`xmin/ymin/xmax/ymax`、`left/top/width/height`(SageMaker 風)、
  `cx/cy/w/h`(0~1);像素形需行內 `width/height`(或 `image_size:[{width,height}]`)。

## 4. Acceptance Criteria(對應 `4_PM_Feedback/test_labelfmt.py`;數值逐項釘死)

> 慣例:合成資料建在 tmp_path,真實寫讀驗證(比照 casepkg/cocoio)。所有格式的框都用同一組
> 換算驗:框絕對 `[8,6,16,12]` @ 影像 64×48 → 正規化 (cx,cy,w,h)=(0.25,0.25,0.25,0.25) → adapter 回絕對 `[8,6,16,12]`。

- **AC1(adapter)** `_row_to_det((7, 0.25,0.25,0.25,0.25, 0.9, "cat"), 64, 48)` → `{"bbox":[8,6,16,12],"cls":"cat","conf":0.9}`。
- **AC2(adapter 無名/無分數)** `_row_to_det((None,0.5,0.5,0.5,0.5,None,None), 100,100)` → `bbox=[25,25,50,50]`,`cls=""`,`conf=1.0`。
- **AC3(adapter cid 補名)** `_row_to_det((3,0.5,0.5,0.2,0.2,None,None),50,50)` → `cls="class_3"`。
- **AC4(COCO 平鋪)** Roboflow 佈局(影像在根 + `_annotations.coco.json`,類名 id=7 cat / id=9 dog,**非連號**):
  a.jpg 兩框(cat/dog)、b.jpg 一框(dog)、c.jpg 無標註 →
  `load_for_image(a.jpg,64,48)` 有 2 筆、`cls` 取自 categories 名(非 id);`load_for_image(c.jpg,...)` 回 `[]`(有來源無框)。
- **AC5(COCO images/ 佈局)** 影像在 `images/`、COCO 在上一層 → 同樣抓得到。
- **AC6(COCO score→conf)** annotation 帶 `score=0.8` → 該 Detection `conf=0.8`;無 score → `conf=1.0`。
- **AC7(VOC 同名 XML)** `x.xml`(`<size>64×48`、object name=cat、bndbox 0,0→16,12)→ `cls="cat"`、`bbox=[0,0,16,12]`。
- **AC8(VOC 無 size 讀影像)** XML 缺 `<size>` → 開真實影像(64×48)補尺寸,框仍正確。
- **AC9(VOC Annotations/ 佈局)** 影像在 `JPEGImages/`、XML 在上一層 `Annotations/` → 抓得到。
- **AC10(LabelMe rectangle)** 同名 `.json` 有 `shapes`(rectangle 兩角 [8,6],[24,18],label=cat,imageWidth/Height=64/48)
  → `cls="cat"`、`bbox=[8,6,16,12]`。
- **AC11(LabelMe polygon 取外接框)** polygon 多點 → 外接框正確。
- **AC12(LabelMe 非 LabelMe .json 不誤判)** 一個沒有 `shapes` 的 `.json`(如 YOLO 風 dict)→ `parse_labelme_boxes` 回 None
  (不吞掉、讓呼叫端往下試/退回 yolo)。
- **AC13(NDJSON bbox 像素)** 一行 `{image:"a.jpg", width:64,height:48, boxes:[{bbox:[8,6,16,12],label:"cat"}]}` → `bbox=[8,6,16,12]`。
- **AC14(NDJSON 四種 bbox)** 同一測試分別驗 `xmin/ymin/xmax/ymax`、`left/top/width/height`、`cx/cy/w/h(0-1)` 三種其餘慣例各得正確框。
- **AC15(NDJSON 排除 manifest)** 根層 `manifest.jsonl`(只有 path/sha)→ 不被當標註來源(`load_for_image` 對該圖回 None 或走別的來源)。
- **AC16(NDJSON label 別名 + class_id)** `class`/`category` 別名可讀;`{class_id:2}` 無 label → `cls="class_2"`。
- **AC17(優先序 COCO 先於其餘)** 同資料夾同時有 COCO 與 LabelMe 同名檔 → 採 COCO(統一入口順序 COCO→VOC→LabelMe→NDJSON)。
- **AC18(無來源回 None)** 資料夾只有 YOLO `.txt`(無 COCO/VOC/LabelMe/NDJSON)→ `load_for_image` 回 `None`(呼叫端退回 yolo)。
- **AC19(永不拋)** 壞 JSON / 壞 XML / 缺尺寸 / 空檔 → 回 `[]` 或 `None`,**不拋例外**(參數化幾種壞輸入)。
- **AC20(不 mutate、純讀)** 呼叫 `load_for_image` 前後,合成的標註檔內容位元不變(讀不寫)。
- **AC21(folder_has_annotations)** COCO/VOC/LabelMe/NDJSON 任一存在 → True;只有 YOLO txt 或空夾 → False。

## 5. 與 07_yolo.md 的關聯(seg/OBB 守衛,契約演進)
見 `07_yolo.md` §「2026-07-05 演進」:`_load_yolo_txt` 對 **≥7 欄**的行一律跳過(segmentation/OBB 多邊形,
前 4 座標會被誤讀成 cx cy w h)。偵測框只認 5 欄(GT)或 6 欄(pred+conf)。此守衛使 labelfmt 與 yolo 一致地
「寧可跳過、不畫亂框」(對齊 User『混了 seg 行不要誤讀成亂框』)。

## 6. app 整合(5_PG_Develop/app.py,不在本模組內)
`_detections` 先試 `labelfmt.load_for_image(image_path, w, h)`;非 None 就用它,None 才 `yolo.load(...)`。
sidebar caption 用 `labelfmt.folder_has_annotations` 標示偵測到的格式來源。**下游 overlay/縮圖/信心過濾零改**
(輸出仍是 Detection)。

## 7. 誠實界線
- COCO 的 `images.width/height` 若與實際影像不符,adapter 以 **app 的 img_w/img_h** 換算 → 極少數會有縮放近似(同 yolo.load xywhn 慣例)。
- segmentation/OBB 的多邊形形狀本身不畫(User 明列不需要);只保證不誤讀成亂框。
- 與 cocoio 的 COCO 解析小幅重複(職責不同,見 §1)。
