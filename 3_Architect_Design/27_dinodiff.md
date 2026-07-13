# 27 · dinodiff — DINOv2 語意差異熱力圖(比較模式第三種檢視)

> 需求:User(2026-07-13)「這個比較模式,能夠多一個 DINO 的比較,如果差異很大的部份就會是熱力圖較大的差異」。
> PO 裁決見 ROADMAP「M9」決策日誌。呈現方式 User 選定:**熱力圖疊在 A 上 + 自動框出 Top-K 差異區**。
> 模型來源 User 裁決:權重放「Tauri 殼的模型資料夾」,app 端提供 **📁 選模型檔**(file explorer),
> **不得**首次使用時上網下載(離線部署鐵則)。

## 0. 為什麼不是「像素差異」(這個模組存在的理由)

現有 `framecompare.difference` 是逐像素相減:對亮度飄移、次像素位移、感測雜訊全都有反應 → 整張圖都在發亮,
真正「長得不一樣的東西」反而被淹沒。DINOv2 是自監督 ViT,patch token 編的是**語意/結構**而非亮度:
同一塊背景在兩張圖亮度差 10% 時 cosine 距離幾乎為 0,但「多了一顆缺陷 / 圖案變形」會讓該 patch 距離明顯拉高。
**熱力圖越紅 = 語意上越不一樣**,正是 User 要的東西。

## 1. 角色與邊界(Tier B)

模組**刻意切成兩半**,理由是「單元 gate 不該碰 88MB 模型」(血淚來自 LV/visuallatent:
`4_PM_Feedback/al_batch.md` — 測試一律注入 fake extractor,真模型只在 E2E smoke 驗):

| 半邊 | 內容 | 依賴 | 進單元 gate? |
|------|------|------|-------------|
| **純邏輯核心**(本檔 §2) | 特徵 → 熱力圖 → Top-K 框 → 分數 | **只有 numpy**(不 import torch / cv2) | ✅ 全部 |
| **I/O 邊界**(本檔 §5) | 載 `.pth`、跑 ViT 前向、解析模型檔路徑 | torch + vendored `dinov2_hub/` | ❌ 只在 `@pytest.mark.e2e` |

- 純邏輯核心 **永不拋例外以外的副作用**:不讀寫檔、不 mutate 輸入、不 import 業務模組。
- `import dinodiff` **不得**觸發 `import torch`(torch 進 process 要 ~2s;單元測試要秒回)→ torch 只在
  `Dinov2PatchExtractor.__init__` 內 lazy import。這是 **AC12** 鎖住的。

## 2. 對外契約(純邏輯 API)

```
grid_side(n_tokens: int) -> int
cosine_distance_map(feat_a: np.ndarray, feat_b: np.ndarray) -> np.ndarray   # (g, g) float32
normalize_heat(dmap: np.ndarray, abs_floor: float = 0.05,
               lo_pct: float = 1.0, hi_pct: float = 99.0) -> np.ndarray     # (g, g) float32 ∈ [0,1]
upsample(heat: np.ndarray, w: int, h: int) -> np.ndarray                    # (h, w) float32 ∈ [0,1]
colorize_overlay(rgb: np.ndarray, heat: np.ndarray, alpha: float = 0.5) -> np.ndarray  # (h,w,3) uint8
top_regions(heat: np.ndarray, w: int, h: int, k: int = 3,
            thr: float = 0.5, min_cells: int = 2) -> list[dict]
diff_score(dmap: np.ndarray) -> float                                        # 0.0 ~ 100.0
```

### 2.1 `grid_side` — token 數 → 方格邊長
DINOv2 patch=14;輸入 518×518 → 37×37 = **1369** 個 patch token。`grid_side(1369) == 37`。
`n_tokens` 非完全平方 → `ValueError`(呼叫端餵錯尺寸的早期爆炸點,不要靜默 reshape 成怪形狀)。

### 2.2 `cosine_distance_map` — 逐 patch 語意距離(本模組的心臟)
- 輸入:`feat_a`、`feat_b` 皆 `(N, D)` float(N=patch 數、D=特徵維度,vits14 → D=384)。
- 步驟:**per-token L2 normalize**(非整體)→ 逐 token 內積 → `d = 1 - cos`。
- 值域 `[0, 2]`:相同=0、正交=1、反向=2。輸出 reshape 成 `(g, g)`。
- 形狀不合(N 不等、D 不等、非 2 維)→ `ValueError`。
- 零向量 token:L2 normalize 前加 `eps=1e-12`,不得產生 NaN(NaN 會一路污染到熱力圖)。

### 2.3 `normalize_heat` — 拉伸到 [0,1](★ 這裡有一個會說謊的陷阱)
percentile 拉伸(`lo_pct`/`hi_pct` 夾掉極端 patch,避免單一 artifact token 把整張壓平)。

**但相對拉伸有個致命的自欺**:兩張**幾乎相同**的圖,距離全落在 0.001~0.003,相對拉伸後
最大值一樣會變成 1.0 → 熱力圖照樣燒得通紅,使用者以為「差很多」。**這是假紅、不可接受。**

守衛:`dmap.max() < abs_floor`(預設 0.05)→ **直接回全零**,不做任何相對拉伸。
語義 = 「這兩張圖在語意上沒有值得一提的差異」。**AC5 專門鎖這條**;E2E 用「同一張圖 vs 自己」實證。

### 2.4 `upsample` — 37×37 → 影像尺寸
雙線性放大到 `(h, w)`,值域仍夾在 `[0,1]`。**誠實界線**:熱力圖的真實解析度就是 37×37,
放大後是塊狀漸層,**不是像素級精確**;它回答「哪一區差很多」,不回答「哪一個像素差很多」。

### 2.5 `colorize_overlay` — 熱力圖疊上 A
- 純 numpy 實作的 JET 式色階(藍→青→綠→黃→紅);**不依賴 cv2**(保持核心零選用依賴)。
- 疊加:`out = rgb*(1 - alpha*heat) + color(heat)*(alpha*heat)`
  → **heat=0 的區域完全等於原圖**(不是整張蒙一層藍霧;冷區要能看清原圖細節)。
- `alpha=0` → 輸出逐像素等於輸入 `rgb`(AC7)。

### 2.6 `top_regions` — 自動框出差異最大的幾塊
- 在 **grid 尺度**(37×37)上做 `heat >= thr` 二值化 → 4-連通元件(37×37 才 1369 格,自己寫 BFS,
  **不引入 scipy**)。
- 每個元件的分數 = 該元件內 heat 的**最大值**(不是面積:User 要的是「差異大」,不是「差異廣」)。
- 小於 `min_cells` 格的元件視為雜訊丟棄;依分數排序取前 `k` 個。
- 回 `[{"bbox": [x, y, w, h], "score": float}, ...]`,**bbox 已換算成影像座標**(int、w/h ≥ 1)。
- `heat` 全零 → 回 `[]`(接 §2.3 的守衛:沒差異就不該框任何東西)。

### 2.7 `diff_score` — 整體差異分數(給 caption 一個數字)
`score = 100 * clip(mean(dmap), 0, 1)`。**用原始 `dmap`,不用拉伸後的 heat**——拉伸後的 mean 沒有跨圖可比性。
同圖 vs 自己 → ≈0;實測 sample_images 兩張不同圖 → ≈6.5。單調:差異越大分數越高。

## 3. 呼叫端管線(app 層,不屬本模組契約)

```
A, B(B 已 resize 對齊 A)
  → 各自 resize 到 518×518 → extractor → (1369, 384)
  → cosine_distance_map → dmap (37,37)
  → diff_score(dmap)                      → caption 數字
  → normalize_heat(dmap)                  → heat (37,37) ∈ [0,1]
  → upsample(heat, A.w, A.h)              → heat_full
  → colorize_overlay(A, heat_full, alpha) → 疊圖
  → top_regions(heat, A.w, A.h, k)        → overlay.draw 白框 + score 標籤
```
- 特徵抽取以 `@st.cache_data` 依 **(檔案路徑, mtime, 模型路徑)** 快取 → 調 alpha/k/thr 滑桿**不重跑模型**。
- 「疊合方式」下拉在 DINO 檢視下**不適用**(它只對 pixel 檢視有意義),改顯示 alpha / Top-K / 門檻。

## 4. 模型檔解析(純函式,可單元測)

```
resolve_model_path(explicit: str | None, environ: Mapping, search_dirs: Sequence[Path]) -> Path | None
```
優先序(第一個命中即回,**永不上網**):
1. `explicit`(User 用 📁 選的路徑;檔案不存在 → **不採用**,繼續往下)
2. `environ["CVR_DINO_MODEL"]`(單一檔案路徑)
3. 依序掃 `search_dirs`,取檔名 glob `dinov2_*.pth` 的**第一個**(排序後,結果穩定)
4. 都沒有 → `None` → app 顯示「請用 📁 選擇 DINOv2 權重(.pth)」,**不報錯、不下載**

`search_dirs` 由 app 提供,順序:`$CVR_MODELS_DIR` → `<repo>/models/`。
(Tauri 殼日後把它的模型資料夾設進 `CVR_MODELS_DIR` 即可接上,不需要改本模組。)

## 5. I/O 邊界(不進單元 gate)

```
class Dinov2PatchExtractor:
    def __init__(self, pth_path: Path, hub_dir: Path, res: int = 518) -> None
    def __call__(self, rgb: np.ndarray) -> np.ndarray   # (N, D) float32
```
- 架構:`torch.hub.load(hub_dir, arch, source="local", pretrained=False)` — **vendored**
  `5_PG_Develop/dinov2_hub/`(1.1MB,facebookresearch/dinov2 原始碼,port 自
  `LV/visuallatent/scripts/dinov2_hub`)。`source="local"` = 不碰 GitHub。
- `arch` 由**檔名**推斷:`dinov2_vits14*` → `dinov2_vits14`(D=384);`dinov2_vitb14*` → `dinov2_vitb14`(D=768)。
- 權重:`torch.load(pth, map_location="cpu")`;若是 `{"model": ...}` 包一層則取出;`load_state_dict(strict=False)`。
  (實測官方 `dinov2_vits14.pth`:missing=0 / unexpected=0。)
- 前向:`forward_features(x)["x_norm_patchtokens"]` → `(1, N, D)` → squeeze 成 `(N, D)` numpy。
- 前處理:resize 到 `res×res`(需為 14 的倍數;518=37×14)+ ImageNet mean/std 正規化。
- 實測成本:CPU、vits14、兩張圖約 **2 秒**(含 warmup)→ 必須靠 §3 的快取,不然每動一次滑桿就卡 2 秒。

## 5.1 P1 探針(GUI E2E 的機器讀數;沿用 `#perf` 隱藏 div 慣例)

新增三個屬性(只在 `compare_on` 且已標記 2 張時有值,否則空字串;同 `data-cmp-view-mode` 語義):

| 屬性 | 值 | 意義 |
|------|-----|------|
| `data-dino-score` | `"0.0"`~`"100.0"` \| `""` | `diff_score` 結果(整體語意差異) |
| `data-dino-regions` | `"0"`~`"k"` \| `""` | `top_regions` 實際回傳的框數 |
| `data-dino-model` | `"1"` / `"0"` | 權重是否已解析到(0 = 顯示「請選模型」提示,**不是錯誤**) |

`data-cmp-view-mode` 的值域從 `pixel|box` **擴充**為 `pixel|box|dino`(既有測試斷言 `pixel`/`box` 不受影響)。

## 6. 驗收標準(AC)

**純邏輯(單元 gate `python verify/gate.py dinodiff`)**
- **AC1** `grid_side(1369)==37`;`grid_side(1370)` → `ValueError`。
- **AC2** `cosine_distance_map`:相同特徵 → 全 0;正交 → 全 1;反向 → 全 2;輸出 shape `(g,g)`。
- **AC3** 形狀不合(N 不等 / D 不等 / 非 2 維)→ `ValueError`;零向量不產生 NaN。
- **AC4** `normalize_heat`:輸出 ∈ [0,1] 且最大值 == 1.0(有真實差異時)。
- **AC5** ★ **反自欺**:`dmap` 全部 < `abs_floor` → 回**全零**(不做相對拉伸)。
- **AC6** `upsample(heat, w, h).shape == (h, w)`,值域仍 ∈ [0,1]。
- **AC7** `colorize_overlay`:輸出 `(h,w,3) uint8`;`alpha=0` → 逐像素等於原圖;`heat=0` 區域等於原圖。
- **AC8** `top_regions`:單一合成熱區 → 回 1 框且**框住**該區;`k` 限制回傳數;heat 全零 → `[]`。
- **AC9** `top_regions` 回的 bbox 是**影像座標**、int、w/h ≥ 1、不超出影像邊界。
- **AC10** `diff_score`:相同特徵 → 0.0;差異越大分數越高;值域 0~100。
- **AC11** `resolve_model_path` 四段優先序(explicit → env → 掃夾 → None);explicit 指到不存在的檔 → 跳過不採用。
- **AC12** ★ `import dinodiff` **不得** import torch(`sys.modules` 不出現 `torch`)。

**真實 E2E(`4_PM_Feedback/test_dinodiff_e2e.py`,`@pytest.mark.e2e`;無權重則 skip)**
- **AC-E1** 真實 `.pth` + 兩張 sample 圖 → `dmap` shape `(37,37)`、`diff_score > 1`、熱力圖非全零。
- **AC-E2** ★ **同一張圖 vs 自己** → `diff_score ≈ 0`(< 1)、`normalize_heat` 全零、`top_regions == []`。
  (這條是 §2.3 陷阱的真實實證:沒有它,「假紅」會一路混進產品。)
- **AC-E3** app 比較模式選「🔥 DINO 語意差異」→ 畫面出現熱力圖影像 + Top-K 框 + 分數 caption(GUI E2E)。

## 7. 已知限制(誠實聲明)

- 熱力圖真實解析度 37×37,**不是像素級**;它指路,不做像素級判定。
- DINOv2 在自然影像上訓練;**晶圓/工業灰階圖是 domain shift**,對「結構性差異」仍有效,
  但對「極細微的低對比缺陷」可能不如專用模型敏感。這是特徵抽取器的限制,不是本模組的 bug。
- A/B 尺寸不同時,B 已由 app 先 resize 對齊 A;兩張都會再被壓到 518×518 → **長寬比失真**對
  cosine 距離的影響兩張一致,可接受(要精確就得走 tiling,超出本輪 appetite)。
