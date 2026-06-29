"""framecompare:兩張同形 RGB uint8 影像的五種視覺比較運算(純邏輯,僅依賴 numpy)。

實作對齊設計 3_Architect_Design/09_framecompare.md:
- side_by_side:水平併接 A | gap | B(高相等即可,寬可不同)。
- difference:逐像素絕對差,升 int16 計算避免 uint8 wrap-around。
- blend:(1-alpha)*A + alpha*B,float64 計算後以 round-half-away-from-zero
  (np.floor(val + 0.5))轉 uint8。
- swipe:欄 index < x 取 A,>= x 取 B(以 B.copy() 起手,不 mutate 輸入)。
- blink_sequence:回 [A, B] 原物件參照(不複製)。

純函式、無副作用、不 mutate 輸入、零 import 任何業務模組。
"""
import numpy as np


def side_by_side(A: np.ndarray, B: np.ndarray, gap: int = 0,
                 gap_color=(0, 0, 0)) -> np.ndarray:
    """水平併接 A | gap | B;輸出 (hA, wA + gap + wB, 3) uint8。要求 hA == hB。"""
    hA, wA = A.shape[:2]
    hB, wB = B.shape[:2]
    if hA != hB:
        raise ValueError(
            "side_by_side requires equal heights: hA=%d, hB=%d" % (hA, hB))
    if gap < 0:
        raise ValueError("gap must be >= 0, got %d" % gap)

    out = np.empty((hA, wA + gap + wB, 3), dtype=np.uint8)
    out[:, 0:wA] = A
    if gap > 0:
        out[:, wA:wA + gap] = gap_color
    out[:, wA + gap:] = B
    return out


def difference(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """逐像素絕對差 |A - B|,升 int16 計算後轉 uint8。要求 A.shape == B.shape。"""
    if A.shape != B.shape:
        raise ValueError(
            "difference requires equal shapes: %s vs %s" % (A.shape, B.shape))
    return np.abs(A.astype(np.int16) - B.astype(np.int16)).astype(np.uint8)


def blend(A: np.ndarray, B: np.ndarray, alpha: float) -> np.ndarray:
    """(1-alpha)*A + alpha*B,round-half-away-from-zero 後轉 uint8。

    要求 A.shape == B.shape、0.0 <= alpha <= 1.0。
    """
    if A.shape != B.shape:
        raise ValueError(
            "blend requires equal shapes: %s vs %s" % (A.shape, B.shape))
    if alpha < 0.0 or alpha > 1.0:
        raise ValueError("alpha must be in [0.0, 1.0], got %r" % alpha)
    val = (1.0 - alpha) * A.astype(np.float64) + alpha * B.astype(np.float64)
    return np.floor(val + 0.5).astype(np.uint8)


def swipe(A: np.ndarray, B: np.ndarray, x: int) -> np.ndarray:
    """欄 index < x 取 A、其餘取 B。要求 A.shape == B.shape、0 <= x <= W。不 mutate 輸入。"""
    if A.shape != B.shape:
        raise ValueError(
            "swipe requires equal shapes: %s vs %s" % (A.shape, B.shape))
    W = A.shape[1]
    if x < 0 or x > W:
        raise ValueError("x must be in [0, %d], got %d" % (W, x))
    out = B.copy()
    out[:, 0:x] = A[:, 0:x]
    return out


def blink_sequence(A: np.ndarray, B: np.ndarray) -> list:
    """回 [A, B](原物件參照,不複製)。要求 A.shape == B.shape。"""
    if A.shape != B.shape:
        raise ValueError(
            "blink_sequence requires equal shapes: %s vs %s" % (A.shape, B.shape))
    return [A, B]
