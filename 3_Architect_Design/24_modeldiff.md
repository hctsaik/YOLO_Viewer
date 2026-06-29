# 設計:modeldiff — 兩 model 在同一影像集上的覆蓋差異(IoU 框級配對)

> `/architect`。**Tier A 純邏輯模組**(無 I/O、無 GUI、不 import 其他實作),`python verify/gate.py modeldiff` 可客觀判綠。
> 上游:User 2026-06-26 第三輪比較需求 —— 「用兩個 model 對【同一包資料】做整理,filter 濾掉整個影像集(不是濾單圖的框),
> 弱 model 逮的更少要能表達」;裁決:**IoU 框級配對**(matched/only-A/only-B per box)、主視圖=覆蓋率儀表板 + 分歧 triage 佇列、
> 取代既有 image-vs-image 比較。本模組把 CLAUDE.md 點名「配對/收斂是唯一無客觀紅綠保護單點」用單元 gate 鎖住。

## 1. 角色與邊界
- **吃資料形狀、不 import 實作**:只吃 `Detection = {"bbox":[x,y,w,h]絕對像素左上原點, "cls":str, "conf":float(0~1)}`(沿 M3 共用契約)。
  **不** import `yolo`/`overlay`/`sidecar`(解耦,可獨立判綠);conf 雙界過濾自己 inline 做(不依賴 overlay 單下界契約)。
- **純函式**:零 I/O、不 mutate 輸入、同輸入同輸出(可釘死 AC)。
- 「label 檔是否存在(model 有沒有跑這張)」屬 app/yolo 層的判斷 → 由 app 以 `a_present`/`b_present` 旗標傳入;
  本模組據以把「**檔缺失(打錯路徑/model 沒輸出)**」與「**有檔但 0 框(真覆蓋差異)**」分成不同 status(防假覆蓋差異)。

## 2. API(對外契約)

```python
iou(box_a, box_b) -> float
    # [x,y,w,h] 兩框的 IoU;union<=0(退化框)→ 0.0;對稱。

match(dets_a, dets_b, iou_thr=0.5, same_class=True) -> {"matched":[(i,j,iou)], "only_a":[i...], "only_b":[j...]}
    # 貪婪框級配對:候選對 = {(i,j) : iou(a_i,b_j) >= iou_thr 且 (not same_class 或 a_i.cls==b_j.cls)}
    # 依 (iou 降冪, i 升冪, j 升冪) 排序,逐對指派(每個 a/b 至多配一次)→ 確定性。
    # matched=配成功對(含 iou);only_a/only_b=未配到的 A/B 索引(升冪)。

diff_image(dets_a, dets_b, iou_thr=0.5, conf_range=(0.0,1.0), classes=None,
           same_class=True, a_present=True, b_present=True) -> dict
    # 1) 先過濾兩邊:保留 conf_range[0] <= conf <= conf_range[1] 且 (classes is None 或 cls in classes) 的框。
    # 2) match(過濾後 A, 過濾後 B, iou_thr, same_class)。
    # 3) 回 {n_a, n_b, matched, only_a, only_b, status, a_present, b_present}
    #    (n_a/n_b=過濾後框數;matched/only_a/only_b 皆為『數量 int』)。
    # status 判定(優先序):
    #   not a_present and not b_present -> "missing_both"
    #   not b_present                   -> "missing_b"     (B model 此圖無輸出;非真 0 框)
    #   not a_present                   -> "missing_a"
    #   n_a==0 and n_b==0               -> "both_empty"    (此 conf/類別下兩邊皆無框)
    #   only_a==0 and only_b==0         -> "agree"         (全部配對成功)
    #   only_a>0  and only_b==0         -> "a_only"        (A 多逮、B 漏)
    #   only_b>0  and only_a==0         -> "b_only"        (B 多逮、A 漏)
    #   else (only_a>0 and only_b>0)    -> "disagree"

summarize(records) -> dict
    # records = list[dict],每筆至少含 n_a,n_b,matched,only_a,only_b,status(diff_image 輸出 + app 加的 name)。
    # 回 {total_a, total_b, imgs_a, imgs_b, total_matched, total_only_a, total_only_b,
    #     delta_boxes(=total_a-total_b), delta_imgs(=imgs_a-imgs_b),
    #     n_missing_a, n_missing_b}  (imgs_a=計 n_a>0 的張數;弱 model 覆蓋少 → total_b/imgs_b 小、delta>0)

filter_images(records, mode) -> list
    # 依 status 對『整個影像集 records』做 triage,回符合的子集(順序保持)。mode:
    #   "all"     -> 全部
    #   "disagree"-> status in {a_only, b_only, disagree}
    #   "a_only"  -> status == "a_only"
    #   "b_only"  -> status == "b_only"
    #   "agree"   -> status == "agree"
    #   "missing" -> status in {missing_a, missing_b, missing_both}

queue(records) -> list
    # 分歧/缺檔優先的排序(records 須含 name 供 tie-break)。
    # key = (rank(status), -(only_a+only_b), name);rank: missing_*=0, disagree=1, a_only=2, b_only=3, agree=4, both_empty=5。
```

## 3. Acceptance Criteria(對應 4_PM_Feedback/test_modeldiff.py;數值已逐項手算釘死)

- **AC1** iou 完全重疊:`iou([0,0,10,10],[0,0,10,10]) == 1.0`。
- **AC2** iou 半重疊:`iou([0,0,10,10],[5,0,10,10]) == 1/3`(inter=50, union=150)。
- **AC3** iou 無重疊:`iou([0,0,10,10],[10,0,10,10]) == 0.0`。
- **AC4** iou 內含:`iou([0,0,10,10],[2,2,6,6]) == 0.36`(inter=36, union=100)。
- **AC5** iou 退化框(w 或 h=0):union<=0 → `0.0`,不除零。
- **AC6** iou 對稱(property):任意兩框 `iou(a,b)==iou(b,a)`。
- **AC7** match 兩相同清單 → 全 matched、only_a/only_b 皆空。
- **AC8** match 門檻邊界:`iou([0,0,10,10],[1,1,10,10])=81/119≈0.6807`;`iou_thr=0.5` → 配對成功;`iou_thr=0.7` → 不配(only_a=only_b=1)。
- **AC9** match same_class=True:同位置不同類別 → **不配**(only_a=[0], only_b=[0])。
- **AC10** match same_class=False:同位置不同類別 → 配對成功(matched 1)。
- **AC11** match 貪婪多框:A=[(0,0,10,10),(20,20,10,10)] B=[(1,1,10,10),(100,100,10,10)](同類)→ matched=1、only_a=[1]、only_b=[1]。
- **AC12** match 確定性/搶配:A=[(0,0,10,10)] B=[(0,0,10,10),(1,1,10,10)] → a0 配 IoU 最高的 b0(1.0),only_b=[1](最高 IoU 先贏,確定性)。
- **AC13** diff_image conf 雙界過濾:conf 在 [lo,hi] 外的框配對前先丟。
- **AC14** diff_image 類別過濾:只算 classes 內的框。
- **AC15** diff_image status `a_only`(A 多一框未配、B 無多)。
- **AC16** diff_image status `b_only`。
- **AC17** diff_image status `disagree`(兩邊各有未配)。
- **AC18** diff_image status `agree`(全配對)。
- **AC19** diff_image status `both_empty`(過濾後兩邊 0 框)。
- **AC20** diff_image `a_present=False` → status `missing_a`(與 both_empty 區分)。
- **AC21** diff_image `b_present=False` → status `missing_b`。
- **AC22** summarize 彙總:total_a/total_b/imgs_a/imgs_b/total_only_a/total_only_b/delta_boxes/delta_imgs/n_missing_b 數值正確。
- **AC23** filter_images:`a_only` 只回 a_only;`disagree` 回 {a_only,b_only,disagree};`missing` 回 missing_*;`all` 全回。
- **AC24** queue 排序:missing/disagree 在前、agree/both_empty 在後,同 rank 依 (未配數降冪, name 升冪)。
- **AC25** 純度(property):呼叫後輸入 list/dict 不被 mutate。
- **AC26** 計數一致(metamorphic property):任意輸入 `matched + only_a == n_a` 且 `matched + only_b == n_b`。

## 4. 邊界
- 空輸入:`match([],[])` → 全空;`diff_image([],[])` → both_empty。
- iou_thr=0:任何有重疊(inter>0)即可配;iou_thr=1:僅完全重疊配。
- conf_range 預設 (0,1) = 不濾;classes=None = 全類別。
- 退化框(w/h=0)不崩(iou=0)。
- same_class 預設 True(物件類別感知比較:scratch 只配 scratch);app 可關。

## 5. 與其他模組邊界(防越權)
- 不 import yolo/overlay/sidecar/任何 app 內函式;只吃 Detection dict 形狀。
- 不碰 conftest/verify/.unet/fixtures。app 整合層(讀兩 model 夾、a_present/b_present 判斷、疊色、佇列 UI)在 23_compare.md §8 描述、由 app(pg)落實,不在本模組。
