"""simhash 模組實作(PG / U-Net 上採樣)。

依 3_Architect_Design/14_simhash.md 契約生成。影像感知雜湊(perceptual hash):
average-hash / difference-hash 整數、Hamming 距離、相似圖搜尋。

純邏輯、零檔案 I/O、零 GUI;僅依賴 numpy 與 PIL.Image(僅記憶體灰階化與縮放,
絕不開關檔案)。不 import 任何業務模組。

語義釘死(§2):
- 灰階化:2D 原樣;3D RGB 用 PIL "L"(§2.2)。
- 縮放:NEAREST,PIL resize 參數為 (width, height)(§2.3)。
- 打包:C-order flatten + MSB-first,左上=最高位(§2.4)。
- ahash bit = (pixel > mean) 嚴格大於;dhash bit = (left > right)(§2.5)。
- hamming = bin(h1 ^ h2).count("1")(§2.6)。
- find_similar 排序鍵 (distance 升序, name 升序)(§2.7)。
"""
import numpy as np
from PIL import Image


def _to_grey(array: np.ndarray) -> np.ndarray:
    """轉成單通道 uint8 灰階(§3.1)。

    - 2D(ndim==2):視為灰階,原樣回傳(uint8)。
    - 3D 且最後軸==3(RGB):用 PIL "L" 轉換。
    - 其他形狀:raise ValueError(§4a)。
    """
    if array.ndim == 2:
        return array
    if array.ndim == 3 and array.shape[2] == 3:
        return np.asarray(Image.fromarray(array, "RGB").convert("L"), dtype=np.uint8)
    raise ValueError(
        f"unsupported array shape {array.shape!r}: expected 2D grey (H,W) "
        f"or 3D RGB (H,W,3)"
    )


def _pack_bits(bits: np.ndarray) -> int:
    """把 2D 布林矩陣以 C-order(row-major)flatten + MSB-first 打包成 int(§2.4)。

    第一個(左上)布林是最高位,最後一個(右下)是最低位。
    """
    value = 0
    for b in bits.flatten():
        value = (value << 1) | int(bool(b))
    return value


def ahash(array: np.ndarray, hash_size: int = 8) -> int:
    """average hash:灰階化 → NEAREST 縮放到 hash_size×hash_size →
    bit = (pixel > mean) → MSB-first 打包成整數(§3.2)。
    """
    if hash_size < 1:
        raise ValueError(f"hash_size must be >= 1, got {hash_size}")
    grey = _to_grey(array)
    img = Image.fromarray(grey, "L").resize(
        (hash_size, hash_size), Image.Resampling.NEAREST
    )
    small = np.asarray(img, dtype=np.uint8)
    mean = float(small.mean())
    bits = small > mean
    return _pack_bits(bits)


def dhash(array: np.ndarray, hash_size: int = 8) -> int:
    """difference hash:灰階化 → NEAREST 縮放到 (hash_size+1)×hash_size →
    bit = (left > right) 水平梯度 → MSB-first 打包成整數(§3.3)。
    """
    if hash_size < 1:
        raise ValueError(f"hash_size must be >= 1, got {hash_size}")
    grey = _to_grey(array)
    img = Image.fromarray(grey, "L").resize(
        (hash_size + 1, hash_size), Image.Resampling.NEAREST
    )
    small = np.asarray(img, dtype=np.uint8)
    bits = small[:, :-1] > small[:, 1:]
    return _pack_bits(bits)


def hamming(h1: int, h2: int) -> int:
    """兩 hash 整數的 Hamming 距離:XOR 後的 popcount(§3.4)。"""
    return bin(h1 ^ h2).count("1")


def find_similar(query: np.ndarray,
                 candidates: list,
                 max_distance: int = 10,
                 hasher: str = "ahash",
                 hash_size: int = 8) -> list:
    """在 candidates 中找出與 query 的 hamming <= max_distance 者,
    依 (distance 升序, name 升序) 排好回傳 list[(name, distance)](§3.5)。

    candidates = list[(name: str, array: np.ndarray)];可為空 list。
    hasher ∈ {"ahash", "dhash"}。
    hash_size 必須一致地套用到 query 與所有 candidate(否則距離無意義,§2.7)。
    """
    if hasher not in ("ahash", "dhash"):
        raise ValueError(f"hasher must be 'ahash' or 'dhash', got {hasher!r}")
    if max_distance < 0:
        raise ValueError(f"max_distance must be >= 0, got {max_distance}")
    fn = ahash if hasher == "ahash" else dhash
    qh = fn(query, hash_size)
    results = []
    for name, arr in candidates:
        d = hamming(qh, fn(arr, hash_size))
        if d <= max_distance:
            results.append((name, d))
    results.sort(key=lambda t: (t[1], t[0]))
    return results
