# 需求:讀更多標註格式(不只 YOLO),不用先轉檔

## User 原話
> 「你看,這個裡面有接受很多種格式 `C:\code\claude\LV\visuallatent`」
> (AskUserQuestion 確認範圍)→「全部五種都加」

## 想要什麼
目前 YOLO Image Viewer 打開一個資料夾時,只認得 **YOLO `.txt`** 和一種 **`.json`**。
但實際拿到的資料常常不是這兩種——可能是別的工具(Roboflow、LabelMe、CVAT、
SageMaker Ground Truth…)輸出的標註。現在遇到這些就看不到框,得先自己寫轉檔腳本。

希望**選一個資料夾就直接把框畫出來**,不管標註是哪一種常見格式:
- YOLO `.txt`(現有,但要更穩)
- COCO JSON
- Pascal VOC XML
- LabelMe JSON
- NDJSON / JSONL(一行一圖)

我的另一個專案 `C:\code\claude\LV\visuallatent` 裡面已經有一套會自動判斷、能吃這五種
格式的實作(`scripts/label_formats.py` + `interaction.py`),直接拿過來用就好,不要重寫。

## 我不在乎的(交給你判斷)
- 不用做格式轉換/匯出(那是另一回事,已有匯出功能)。
- 不用支援 segmentation / OBB 的「多邊形」本身——但如果標註檔裡混了這種行,
  **不要把它誤讀成一個亂框**,寧可跳過。
- 選哪個當「優先」順序你決定,只要同一張圖不會同時畫出重複來源的框。
