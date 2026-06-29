"""embcluster:對外部預先算好的 embedding 向量做餘弦相似搜尋與確定性 k-means 分群。

設計來源:3_Architect_Design/17_embcluster.md(M5 / Tier A,純邏輯)。
純函式、無隨機、無檔案 I/O、無 GUI;唯一外部相依為 numpy。
不 import sklearn / scipy,也不 import 任何業務模組。

提供:
- cosine_similarity(a, b)        餘弦相似度;任一 norm==0 → 0.0(短路);回內建 float。
- nearest(query, items, top_k)   依 (similarity 降序, name 升序) 排,回前 top_k。
- kmeans(items, k, iters)        確定性硬分群:初始中心=前 k 點、固定 iters 輪、
                                 平手取最小 cluster_id、空群中心不動;iters<1 視為跑 1 輪。
- cluster_members(assignments)   反轉 {name:cid} → {cid:[names 升序]};只列出現過的 cid。
"""
import numpy as np


def _vec(v):
    # §3.1:轉成 1D float64 向量(list 與 ndarray 等價輸出;np.asarray 產生新陣列,不 mutate 輸入)。
    return np.asarray(v, dtype=np.float64)


def cosine_similarity(a, b) -> float:
    # §3.2 / §2.2:dot(a,b)/(|a||b|);任一 norm==0 → 0.0(先於除法,杜絕除零/nan)。回內建 float。
    a = _vec(a)
    b = _vec(b)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def nearest(query, items, top_k: int = 5) -> list:
    # §3.3 / §2.3:對每 candidate 算 cosine;依 (similarity 降序, name 升序) 排;回前 top_k。
    if top_k < 0:
        raise ValueError("top_k must be >= 0")
    scored = [(name, cosine_similarity(query, vec)) for name, vec in items]
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored[:top_k]


def kmeans(items, k: int, iters: int = 10) -> dict:
    # §3.4 / §2.4:確定性硬分群。邊界順序釘死:k<=0 → n==0 → k>n 皆 ValueError。
    n = len(items)
    if k <= 0:
        raise ValueError("k must be > 0")
    if n == 0:
        raise ValueError("items must be non-empty")
    if k > n:
        raise ValueError("k must be <= number of items")

    names = [it[0] for it in items]
    X = np.asarray([_vec(it[1]) for it in items], dtype=np.float64)  # (n, dim),列序=items 順序

    centers = X[:k].copy()  # 初始中心=前 k 點(確定性,無隨機)

    effective_iters = max(1, iters)  # §4-i:iters<1 視為跑 1 輪(保證 assign 不為 None)
    assign = None
    for _ in range(effective_iters):
        # 距離矩陣 D[i,j] = ||X[i] - centers[j]||(歐氏 L2)
        diff = X[:, None, :] - centers[None, :, :]
        D = np.linalg.norm(diff, axis=2)
        new_assign = np.argmin(D, axis=1)  # 平手取最小 cluster_id

        if assign is not None and np.array_equal(new_assign, assign):
            assign = new_assign
            break  # 收斂提早停
        assign = new_assign

        for j in range(k):
            mask = (assign == j)
            if mask.any():
                centers[j] = X[mask].mean(axis=0)  # 非空群更新;空群中心不動

    return {names[i]: int(assign[i]) for i in range(n)}


def cluster_members(assignments: dict) -> dict:
    # §3.5 / §2.5:反轉 {name:cid} → {cid:[names 升序]};只列出現過的 cid。
    out = {}
    for name, cid in assignments.items():
        out.setdefault(int(cid), []).append(name)
    for cid in out:
        out[cid].sort()
    return out
