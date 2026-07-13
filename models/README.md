# models/ — 模型權重放這裡

比較模式的「🔥 DINO 語意差異」需要一個 **DINOv2 權重檔**。權重**不進 git**(`dinov2_vits14.pth` 有 88MB),
所以換機部署時要自己把檔案放好。三種方式,app 依序尋找:

1. **app 裡用 📁 選**(比較模式 → 檢視方式選 DINO → 模型列右邊的 📁)——開原生檔案總管挑 `.pth`。
2. **環境變數 `CVR_DINO_MODEL`** = 權重檔完整路徑。
3. **丟進這個資料夾**(檔名要能被 `dinov2_*.pth` 比對到,例如 `dinov2_vits14.pth`),app 會自動掃到。
   也可以設 `CVR_MODELS_DIR` 指向別的資料夾(例如 Tauri 殼的共用模型夾),它會**優先於**本資料夾。

**永遠不會上網下載。** 找不到權重時 app 只會提示你去選檔,不會嘗試連 HuggingFace / GitHub
(離線部署鐵則;架構原始碼已 vendored 在 `5_PG_Develop/dinov2_hub/`,那 1.1MB 是程式碼、有進 repo)。

## 支援的權重

| 檔名需含 | 架構 | 特徵維度 | 大小 |
|---------|------|---------|------|
| `vits14` | `dinov2_vits14` | 384 | 88 MB |
| `vitb14` | `dinov2_vitb14` | 768 | 346 MB |
| `vitl14` | `dinov2_vitl14` | 1024 | 1.1 GB |
| `vitg14` | `dinov2_vitg14` | 1536 | 4.5 GB |

官方權重(facebookresearch/dinov2)。**建議 `vits14`** —— CPU 上兩張圖約 2 秒,足夠;
更大的模型在 CPU 上會慢到不好用,而差異熱力圖的解析度一樣是 37×37,不會因此變細。
