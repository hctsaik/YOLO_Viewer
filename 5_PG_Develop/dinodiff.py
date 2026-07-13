"""dinodiff — DINOv2 語意差異熱力圖(設計 3_Architect_Design/27_dinodiff.md)。

兩半(設計 §1):
  純邏輯核心 —— 只依賴 numpy,特徵 → 熱力圖 → Top-K 差異區 → 分數。單元 gate 全鎖這半。
  I/O 邊界   —— Dinov2PatchExtractor 載 .pth 跑 ViT。torch 是 **lazy import**(見下),
                 因為 import torch 要 ~2 秒,單元測試每次都吃這 2 秒不可接受(AC12 鎖住)。

為什麼不是像素差:像素差對亮度飄移/次像素位移全都有反應 → 整張發亮;DINOv2 的 patch token 編的是
語意/結構,對這些不敏感,只對「真的長得不一樣」有反應。熱力圖越紅 = 語意上越不一樣。
"""
from pathlib import Path

import numpy as np

_EPS = 1e-12

# DINOv2 的 patch 邊長(vits14 / vitb14 / vitl14 / vitg14 全是 14)。
PATCH = 14
# 預設輸入解析度:518 = 37 × 14 → 37×37 = 1369 個 patch token。
DEFAULT_RES = 518


# ============================== 純邏輯核心(只有 numpy)==============================
def grid_side(n_tokens):
    """patch token 數 → 方格邊長(1369 → 37)。

    非完全平方就 ValueError:這是呼叫端餵錯輸入尺寸的早期爆炸點。靜默 reshape 成怪形狀
    只會讓錯誤在下游變成一張看似合理、其實錯位的熱力圖 —— 那比崩潰難查得多。
    """
    n = int(n_tokens)
    g = int(round(n ** 0.5))
    if g * g != n or g <= 0:
        raise ValueError(f"patch token 數 {n} 不是完全平方,無法排成方格")
    return g


def cosine_distance_map(feat_a, feat_b):
    """逐 patch 的 cosine 距離圖 (g, g) float32,值域 [0, 2](相同=0 / 正交=1 / 反向=2)。

    per-token L2 normalize(不是整體):DINOv2 非 register 版有少數高範數 artifact token,
    整體正規化會讓它們主宰結果。
    """
    a = np.asarray(feat_a, dtype=np.float32)
    b = np.asarray(feat_b, dtype=np.float32)
    if a.ndim != 2 or b.ndim != 2:
        raise ValueError(f"特徵必須是 2 維 (N, D);實得 a={a.shape} b={b.shape}")
    if a.shape != b.shape:
        raise ValueError(f"兩張圖的特徵形狀必須相同;實得 a={a.shape} b={b.shape}")

    # +_EPS:零向量 token 不得產生 NaN —— 一個 NaN 會經 percentile/mean 污染整張熱力圖與分數。
    a = a / (np.linalg.norm(a, axis=1, keepdims=True) + _EPS)
    b = b / (np.linalg.norm(b, axis=1, keepdims=True) + _EPS)
    d = 1.0 - np.sum(a * b, axis=1)

    g = grid_side(a.shape[0])
    return d.reshape(g, g).astype(np.float32)


def normalize_heat(dmap, abs_floor=0.05, lo_pct=1.0, hi_pct=99.0):
    """拉伸到 [0,1] 供上色。★ 內含一道「不准說謊」的守衛(設計 §2.3)。

    percentile 拉伸本身是必要的(夾掉極端 artifact patch,否則整張被壓平),但它是**相對**的:
    兩張幾乎相同的圖,距離全落在 0.001~0.003,拉伸後最大值一樣變成 1.0 → 熱力圖照樣通紅,
    使用者會以為「差很多」。那是假紅。

    守衛:整張最大距離都還構不上 abs_floor → 直接回全零,不做任何相對拉伸。
    語義 = 「這兩張圖在語意上沒有值得一提的差異」。
    """
    d = np.asarray(dmap, dtype=np.float32)
    if float(d.max(initial=0.0)) < float(abs_floor):
        return np.zeros_like(d, dtype=np.float32)

    lo = float(np.percentile(d, lo_pct))
    hi = float(np.percentile(d, hi_pct))
    if hi - lo < _EPS:          # 差異存在但完全均勻(整張一起變)→ 沒有「哪一區」可指,不做假熱區
        return np.zeros_like(d, dtype=np.float32)
    return np.clip((d - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def upsample(heat, w, h):
    """(g,g) → (h,w) 雙線性放大。純 numpy,不依賴 cv2。

    誠實界線:真實解析度就是 g×g(37×37),放大後是塊狀漸層 —— 它回答「哪一區差很多」,
    不回答「哪一個像素差很多」。
    """
    src = np.asarray(heat, dtype=np.float32)
    gh, gw = src.shape
    w, h = int(w), int(h)
    if w <= 0 or h <= 0:
        raise ValueError(f"目標尺寸必須為正;實得 w={w} h={h}")

    ys = np.linspace(0.0, gh - 1, h, dtype=np.float32)
    xs = np.linspace(0.0, gw - 1, w, dtype=np.float32)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, gh - 1)
    x1 = np.minimum(x0 + 1, gw - 1)
    wy = (ys - y0)[:, None]
    wx = (xs - x0)[None, :]

    top = src[np.ix_(y0, x0)] * (1 - wx) + src[np.ix_(y0, x1)] * wx
    bot = src[np.ix_(y1, x0)] * (1 - wx) + src[np.ix_(y1, x1)] * wx
    return np.clip(top * (1 - wy) + bot * wy, 0.0, 1.0).astype(np.float32)


def _jet(t):
    """JET 色階(藍→青→綠→黃→紅),純 numpy;t ∈ [0,1] → (…, 3) float32 ∈ [0,255]。"""
    t = np.clip(np.asarray(t, dtype=np.float32), 0.0, 1.0)
    r = np.clip(1.5 - np.abs(4.0 * t - 3.0), 0.0, 1.0)
    g = np.clip(1.5 - np.abs(4.0 * t - 2.0), 0.0, 1.0)
    b = np.clip(1.5 - np.abs(4.0 * t - 1.0), 0.0, 1.0)
    return np.stack([r, g, b], axis=-1) * 255.0


def colorize_overlay(rgb, heat, alpha=0.5):
    """熱力圖疊上底圖。權重是 alpha*heat(不是固定 alpha)——

    這樣 heat=0 的冷區**逐像素等於原圖**,不會整張蒙一層藍霧;冷區要能看清原圖細節,
    否則「疊熱力圖」反而讓人看不到圖。
    """
    base = np.asarray(rgb)
    hm = np.asarray(heat, dtype=np.float32)
    if base.ndim != 3 or base.shape[2] != 3:
        raise ValueError(f"底圖必須是 (h, w, 3) RGB;實得 {base.shape}")
    if hm.shape != base.shape[:2]:
        raise ValueError(f"熱力圖尺寸需與底圖一致;實得 heat={hm.shape} rgb={base.shape[:2]}")

    wgt = (np.clip(float(alpha), 0.0, 1.0) * hm)[..., None]
    out = base.astype(np.float32) * (1.0 - wgt) + _jet(hm) * wgt
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def top_regions(heat, w, h, k=3, thr=0.5, min_cells=2):
    """把差異最大的幾塊框出來。回 [{"bbox": [x, y, w, h] 影像座標 int, "score": float}, ...]。

    在 grid 尺度(37×37 = 1369 格)上做 4-連通元件 —— 自己寫 BFS,不為了這點事引入 scipy。
    元件分數取該區 heat 的**最大值**而非面積:User 要的是「差異大」,不是「差異廣」。
    """
    hm = np.asarray(heat, dtype=np.float32)
    gh, gw = hm.shape
    w, h = int(w), int(h)
    hot = hm >= float(thr)
    seen = np.zeros_like(hot, dtype=bool)
    comps = []

    for r0 in range(gh):
        for c0 in range(gw):
            if not hot[r0, c0] or seen[r0, c0]:
                continue
            stack = [(r0, c0)]
            seen[r0, c0] = True
            cells = []
            while stack:
                r, c = stack.pop()
                cells.append((r, c))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < gh and 0 <= nc < gw and hot[nr, nc] and not seen[nr, nc]:
                        seen[nr, nc] = True
                        stack.append((nr, nc))
            if len(cells) < int(min_cells):
                continue                                   # 單格雜訊:不值得框
            rs = [c[0] for c in cells]
            cs = [c[1] for c in cells]
            comps.append({
                "score": float(max(hm[r, c] for r, c in cells)),
                "cell_box": (min(rs), max(rs), min(cs), max(cs)),
            })

    comps.sort(key=lambda c: c["score"], reverse=True)
    out = []
    for comp in comps[:int(k)]:
        rmin, rmax, cmin, cmax = comp["cell_box"]
        x0 = int(np.floor(cmin * w / gw))
        x1 = int(np.ceil((cmax + 1) * w / gw))
        y0 = int(np.floor(rmin * h / gh))
        y1 = int(np.ceil((rmax + 1) * h / gh))
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        out.append({"bbox": [x0, y0, max(1, x1 - x0), max(1, y1 - y0)],
                    "score": comp["score"]})
    return out


def diff_score(dmap):
    """整體語意差異分數 0~100。

    刻意用**原始** dmap 而非拉伸後的 heat:拉伸是 per-pair 相對的,拉伸後的 mean 沒有跨圖可比性
    (每一對都會被拉到 max=1),那樣的分數看起來有意義、其實不能比。
    """
    d = np.asarray(dmap, dtype=np.float32)
    return float(np.clip(float(np.mean(d)), 0.0, 1.0) * 100.0)


# ============================== 模型檔解析(純函式)==============================
def resolve_model_path(explicit, environ, search_dirs):
    """找 DINOv2 權重。**永不上網**(離線部署鐵則):找不到就回 None,由 app 提示使用者用 📁 選。

    優先序:explicit(📁 選的)→ CVR_DINO_MODEL → 掃 search_dirs 的 dinov2_*.pth → None。
    explicit 指到不存在的檔 → 不採用、繼續往下(路徑失效時自動退回可用來源,不是整個壞掉)。
    """
    if explicit:
        p = Path(str(explicit))
        if p.is_file():
            return p

    env_p = (environ or {}).get("CVR_DINO_MODEL")
    if env_p:
        p = Path(str(env_p))
        if p.is_file():
            return p

    for d in (search_dirs or []):
        d = Path(d)
        if not d.is_dir():
            continue
        hits = sorted(d.glob("dinov2_*.pth"))      # 排序 → 結果穩定、不隨檔案系統順序漂移
        if hits:
            return hits[0]
    return None


# ============================== I/O 邊界(torch;不進單元 gate)==============================
def arch_from_filename(pth_path):
    """由檔名推架構:dinov2_vits14*.pth → "dinov2_vits14"(D=384)、vitb14 → D=768…"""
    name = Path(pth_path).name.lower()
    for tag in ("vits14", "vitb14", "vitl14", "vitg14"):
        if tag in name:
            return f"dinov2_{tag}"
    raise ValueError(
        f"無法從檔名判斷 DINOv2 架構:{Path(pth_path).name}"
        "(檔名需含 vits14 / vitb14 / vitl14 / vitg14)")


class Dinov2PatchExtractor:
    """影像 → patch token 特徵 (N, D)。架構與權重**都從本機載入**,完全不碰網路。

    架構來自 vendored 的 5_PG_Develop/dinov2_hub/(facebookresearch/dinov2 原始碼,1.1MB),
    用 torch.hub.load(..., source="local") 建 —— source="local" 就是「不要去 GitHub」。
    這條路是從 LV/visuallatent/scripts/models.py 學來的(已在該專案實戰驗證)。
    """

    def __init__(self, pth_path, hub_dir, res=DEFAULT_RES):
        import torch                       # lazy:見模組 docstring / AC12

        if res % PATCH:
            raise ValueError(f"輸入解析度需為 {PATCH} 的倍數;實得 {res}")
        self.res = int(res)
        self._torch = torch

        model = torch.hub.load(str(hub_dir), arch_from_filename(pth_path),
                               source="local", pretrained=False)
        state = torch.load(str(pth_path), map_location="cpu")
        if isinstance(state, dict) and "model" in state:
            state = state["model"]
        model.load_state_dict(state, strict=False)
        model.eval()
        self.model = model

    def __call__(self, rgb):
        """(h, w, 3) uint8 RGB → (N, D) float32 patch token 特徵。"""
        from PIL import Image
        torch = self._torch

        im = Image.fromarray(np.asarray(rgb, dtype=np.uint8)).convert("RGB")
        im = im.resize((self.res, self.res), Image.BILINEAR)
        x = np.asarray(im, dtype=np.float32) / 255.0
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / \
            np.array([0.229, 0.224, 0.225], np.float32)          # ImageNet 正規化
        t = torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0)

        with torch.no_grad():
            feat = self.model.forward_features(t)["x_norm_patchtokens"]   # (1, N, D)
        return feat.squeeze(0).cpu().numpy().astype(np.float32)
