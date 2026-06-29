# 設計:embcluster(M5 / Tier A,純邏輯 numpy)

> `/architect` 模組設計。對**外部預先算好的 embedding 向量**(來自 DINO/SAM/CLIP 等,**本模組不產生**)做餘弦相似搜尋與**確定性** k-means 分群,供「相似圖 / 聚類檢視」。純 numpy、**零檔案 I/O、零 GUI、零 import 業務模組**;**不依賴 sklearn**(自寫確定性實作以利釘死 AC)。本文件是給 `/pm` 抓取的契約來源,AC 全部釘死「確切相似度浮點 / 確切排序 / 確切 `{name:cluster_id}` 指派」,**禁止代理式 AC**(不准「非空 / 是 list / 是 dict / 有分群」)。
>
> 上游:`ROADMAP.md`(第 60 行,M5 模組分解;Tier A;相依「—」即無)。職責一句:給一組已就緒的 embedding 向量,提供餘弦相似度、最近鄰搜尋,與一個**確定性(無隨機)**的 k-means 分群。
>
> **邊界 sanity 自評**:此模組無 I/O、無跨模組契約、無 GUI、不 import 任何業務模組,可獨立設計與驗收 → **不需退回 `/po`**。與 `simhash`(感知雜湊相似圖)精神類似但**正交**:simhash 吃影像陣列算 hash/Hamming;embcluster 吃**抽象向量**算餘弦/歐氏,兩者不重疊、不該合併。

---

## 1. 目的 (Purpose)

把「外部離線算好的高維 embedding 向量」變成可用的相似度與分群信號:`cosine_similarity` 量化兩向量方向相似、`nearest` 在候選集中找最相似的前 top_k、`kmeans` 做**完全確定性、可重現**的硬分群;全程純函式、無隨機、無 I/O,可被精確斷言(以可手算的合成小向量 / 分得很開的 2D 點釘死確切數值與指派)。

---

## 2. I/O 契約 (逐字採用,不得更動簽名)

純邏輯。**僅依賴 `numpy`(記為 `np`)**。**不得 import** `sklearn`、`scipy`,也**不得 import** `imgio`/`simhash`/`framecompare`/`yolo` 等任何業務模組。**不得使用任何隨機來源**(`random`、`np.random`、時間、雜湊種子皆禁)。

```python
import numpy as np

def cosine_similarity(a, b) -> float:
    # 餘弦相似度 = dot(a,b) / (|a| * |b|)。
    # 零向量處理:任一 norm == 0 → 回 0.0(不除零)。回 Python 內建 float。
    ...

def nearest(query, items, top_k: int = 5) -> list:
    # items = list[(name: str, vector)];對每個 candidate 算 cosine_similarity(query, vector);
    # 依 (similarity 降序, name 升序) 排序;回前 top_k 的 list[(name, similarity)]。
    ...

def kmeans(items, k: int, iters: int = 10) -> dict:
    # items = list[(name: str, vector)];確定性硬分群。
    # 回 {name: cluster_id(int, 0..k-1)}。演算法見 §2.4(確定性,釘死)。
    ...

def cluster_members(assignments: dict) -> dict:
    # assignments = {name: cluster_id};反轉成 {cluster_id: [names 升序]}。
    # 只列出實際出現的 cluster_id(由 assignments 推得);各群 names 以 str 字典序升序。
    ...
```

### 2.1 輸入資料形狀(契約值,釘死)

- **向量**(`a` / `b` / `query` / 每個 item 的第二元素)為「1D 數值序列」:`list[float|int]` **或** `np.ndarray`(`ndim == 1`)。本模組內部一律以 `np.asarray(v, dtype=np.float64)` 轉成 float64 1D 後運算(故 `int` 與 `float` 輸入等價)。
- **item** = `(name: str, vector)` 的 tuple;`name` 為 `str`。
- `items`(`nearest` / `kmeans` 的)為 `list[(name, vector)]`。
- `assignments`(`cluster_members` 的)為 `dict[str, int]`(name → cluster_id)。
- **維度一致性**:同一次呼叫內,所有參與運算的向量應同維度(`cosine_similarity` 的 `a`、`b` 同維;`nearest` 的 `query` 與所有 candidate 同維;`kmeans` 的所有 item 同維)。Tier A 信任契約,**不對維度不一致做主動防禦**(維度不符時 numpy 廣播會自然拋 `ValueError`,屬下游錯,非本模組契約點;**不列為 AC**)。
- `top_k` 為 `int`;`k`、`iters` 為 `int`。

### 2.2 `cosine_similarity(a, b) -> float`(釘死)

設 `a, b` 轉為 float64 1D:`na = ||a||`、`nb = ||b||`(歐氏 L2 範數,`np.linalg.norm`)。

1. **零向量短路(釘死,先於除法)**:若 `na == 0.0` **或** `nb == 0.0` → 回 **`0.0`**(Python float;**不執行除法**,杜絕 `nan`/`inf`/除零警告)。
2. 否則回 `float(np.dot(a, b) / (na * nb))`(內建 `float`,非 `np.float64`)。
3. **值域與釘死推論**(供 AC,均可手算):
   - **相同方向 / 同向**:`cosine_similarity(v, v) == 1.0`;`cosine_similarity([3,4],[3,4]) == 1.0`;平行(正純量倍)`cosine_similarity([1,2,2],[2,4,4]) == 1.0`。
   - **正交**:`cosine_similarity([1,0],[0,1]) == 0.0`。
   - **反向**:`cosine_similarity([1,0],[-1,0]) == -1.0`。
   - **45°**:`cosine_similarity([1,1],[1,0]) == 1/√2 ≈ 0.7071067811865475`(以 `pytest.approx` 或 `math.isclose` 比對,容差見 §5)。
   - **對稱**:`cosine_similarity(a,b) == cosine_similarity(b,a)`。
   - 理論值域 `[-1.0, 1.0]`(浮點誤差內)。

### 2.3 `nearest(query, items, top_k=5) -> list`(釘死)

1. `top_k < 0` → `raise ValueError`(負數無意義;見 §4)。
2. 對每個 `(name, vec)` in `items`:`s = cosine_similarity(query, vec)`,收集 `(name, s)`。
3. **排序鍵**:`(-s, name)` —— 即 **similarity 降序**(高相似在前),**平手再 name 字典序(`str` 預設 `<`)升序**(釘死;全序、穩定可重現)。
4. **截斷**:回排序後的**前 `top_k` 個**(`results[:top_k]`)。`top_k == 0` → 回 `[]`;`top_k >= len(items)` → 回全部(已排序)。
5. 回 `list[(name, similarity)]`,`similarity` 為 §2.2 的內建 `float`。`items == []` → 回 `[]`(不拋錯)。

### 2.4 `kmeans(items, k, iters=10) -> dict`(**確定性演算法,釘死,杜絕隨機**)

設 `n = len(items)`,`names = [item[0] ...]`(保序),`X = np.asarray([vec ...], dtype=np.float64)`(shape `(n, dim)`,**列序 = items 給定順序**)。

**邊界先檢**(順序釘死,見 §4):
- `k <= 0` → `raise ValueError`。
- `n == 0`(空 items) → `raise ValueError`(無點可分)。
- `k > n` → `raise ValueError`(群數多於點數,無法非空初始化)。

**演算法(步驟釘死)**:

1. **初始中心(確定性)**:`centers = X[:k].copy()` —— 取**前 `k` 個 item 的向量**作為初始中心 `c_0..c_{k-1}`(`c_j = X[j]`)。**無隨機、無 k-means++、無資料順序洗牌**。中心順序即 cluster_id 順序(`c_j` 對應 `cluster_id == j`)。
2. **固定迭代 `iters` 次**(或提早收斂即停):每一輪做「指派 → 更新」:
   - **指派(assign)**:對每個點 `X[i]`,算到各中心的**歐氏距離(L2)** `d_ij = ||X[i] - c_j||`;指派到**距離最小**的中心。**平手規則(釘死)**:多個中心距離相等(在浮點容差下相等)時,取**最小的 cluster_id**(即 `np.argmin` 於 `j` 軸,回最小索引)。得 `assign[i] ∈ 0..k-1`。
   - **收斂提早停(釘死)**:若本輪 `assign` 與**上一輪完全相同**(`np.array_equal`),則指派已穩定 → **立即停止**(不再更新中心,直接用此 `assign`)。這保證確定性且避免無謂迭代。
   - **更新(update)**:對每個 cluster `j`,令 `members_j = {i : assign[i] == j}`;
     - 若 `members_j` **非空**:`c_j = X[members_j].mean(axis=0)`(該群成員向量的算術平均,逐維)。
     - 若 `members_j` **為空(空群)**:**`c_j` 保持不變**(維持上一輪中心;**不重新挑點、不丟棄該群**)——釘死「空群中心保持不變」。
3. 跑滿 `iters` 輪或提早收斂後,以**最後一次的 `assign`** 產生結果。
4. 回 `{names[i]: int(assign[i]) for i in range(n)}`(value 為 Python 內建 `int`,範圍 `0..k-1`)。

**確定性保證(供 AC)**:函式無隨機來源、無時間依賴;**相同 `(items, k, iters)` 必回完全相同 dict**(逐 key 逐 value 相等)。再跑一次結果 identical。

**手算釘死範例(分得很開的 2D 點)**:見 §5 的 AC15–AC19,皆可由上述步驟手推(初始中心 = 前 k 點 → 一輪指派即收斂)。

### 2.5 `cluster_members(assignments) -> dict`(釘死)

1. 反轉 `assignments`(`{name: cid}`)為 `{cid: [names]}`:對每個 `(name, cid)`,把 `name` 收進 `cid` 的 list。
2. **只列出實際出現的 `cid`**(由 `assignments.values()` 決定;**不**自動補空群的 `cid`)。
3. 每個 `cid` 的 list 以 **`name` 字典序升序排序**(釘死)。
4. 回 `dict[int, list[str]]`。`assignments == {}` → 回 `{}`。
- **與 kmeans 串接推論(供 AC)**:`cluster_members(kmeans(items, k))` 給出每群成員;但**若 kmeans 產生空群,該 cid 不會出現在 cluster_members 結果中**(因 §2.5-2 只列出現過的 cid)。

---

## 3. 資料流 (Data Flow)

### 3.1 `_vec(v) -> np.ndarray`(內部 helper,語義釘死;名稱可自定)
1. `np.asarray(v, dtype=np.float64)` → 1D float64 向量(`list` 與 `ndarray` 等價輸出)。

### 3.2 `cosine_similarity(a, b) -> float`
1. `a = _vec(a)`、`b = _vec(b)`。
2. `na = float(np.linalg.norm(a))`、`nb = float(np.linalg.norm(b))`。
3. `if na == 0.0 or nb == 0.0: return 0.0`(§2.2-1,先於除法)。
4. 回 `float(np.dot(a, b) / (na * nb))`。

### 3.3 `nearest(query, items, top_k=5) -> list`
1. `top_k < 0` → `raise ValueError`(§4)。
2. `q = query`(交由 `cosine_similarity` 內部 `_vec`)。
3. `scored = [(name, cosine_similarity(q, vec)) for name, vec in items]`。
4. `scored.sort(key=lambda t: (-t[1], t[0]))`(similarity 降序、name 升序;§2.3)。
5. 回 `scored[:top_k]`(`items == []` → `[]`;`top_k == 0` → `[]`)。

### 3.4 `kmeans(items, k, iters=10) -> dict`
1. `n = len(items)`;邊界:`k <= 0` → ValueError;`n == 0` → ValueError;`k > n` → ValueError(§2.4 / §4,順序釘死)。
2. `names = [it[0] for it in items]`;`X = np.asarray([_vec(it[1]) for it in items], dtype=np.float64)`(shape `(n, dim)`)。
3. `centers = X[:k].copy()`(初始中心 = 前 k 點;§2.4-1)。
4. `assign = None`;迴圈 `for _ in range(iters)`:
   - 算距離矩陣 `D`(`(n, k)`,`D[i,j] = ||X[i] - centers[j]||`)。
   - `new_assign = np.argmin(D, axis=1)`(平手取最小 cluster_id;§2.4-2)。
   - `if assign is not None and np.array_equal(new_assign, assign): assign = new_assign; break`(收斂提早停)。
   - `assign = new_assign`。
   - 對每個 `j ∈ 0..k-1`:`mask = (assign == j)`;`if mask.any(): centers[j] = X[mask].mean(axis=0)`(非空群更新;空群中心不動;§2.4-2)。
5. 回 `{names[i]: int(assign[i]) for i in range(n)}`(§2.4-4)。

### 3.5 `cluster_members(assignments) -> dict`
1. `out = {}`;對 `(name, cid) in assignments.items()`:`out.setdefault(int(cid), []).append(name)`。
2. 對每個 `cid in out`:`out[cid].sort()`(name 字典序升序;§2.5-3)。
3. 回 `out`(`assignments == {}` → `{}`)。

- **metamorphic / 不變性(供 AC,§5)**:
  - **尺度不變(cosine)**:`cosine_similarity(a, b) == cosine_similarity(2*a, b) == cosine_similarity(a, 5*b)`(正純量倍不改方向;在浮點容差內)。
  - **確定性可重現(kmeans)**:`kmeans(items, k, iters) == kmeans(items, k, iters)`(逐 key/value 相等),且與 `iters` 加大後相同(已收斂則更多迭代不改結果)。
  - **kmeans 與 cluster_members 串接**:同一群的成員,其 cluster_id 在 `kmeans` 結果中相同;`cluster_members` 把它們聚在同一 cid 下、name 升序。

---

## 4. 邊界條件與錯誤處理

a. **零向量(cosine)**:`a` 或 `b` 的 L2 範數為 0 → 回 `0.0`(§2.2-1;**不除零、不拋錯、不回 nan**)。兩者皆為零向量亦回 `0.0`。
b. **`nearest` 空 items**:`items == []` → 回 `[]`(不拋錯)。
c. **`nearest` `top_k` 邊界**:`top_k == 0` → `[]`;`top_k >= len(items)` → 回全部(已排序);`top_k < 0` → `raise ValueError`(負數無意義)。
d. **`kmeans` `k <= 0`**:`raise ValueError`(群數須為正)。
e. **`kmeans` 空 items**(`n == 0`):`raise ValueError`(無點可分)。
f. **`kmeans` `k > len(items)`**:`raise ValueError`(群數多於點數,前 k 點無法取足)。**邊界檢查順序(釘死)**:先 `k <= 0`,再 `n == 0`,再 `k > n`(故 `k<=0` 優先於其他;`k=3, n=0` 因 `n==0` 先觸發亦拋 ValueError,殊途同歸)。
g. **`kmeans` 單點 / `k == n`**:`n == 1, k == 1` → 唯一點自成 cluster 0(`{name: 0}`);`k == n` → 每點各成一群(初始中心 = 全部點,一輪指派每點落回自身群,`{name_i: i}`,平手規則下穩定)。
h. **`kmeans` 空群**:迭代中某群無成員 → 該群中心保持不變(§2.4-2);最終該 cluster_id 可能無任何 name 指派到它(合法,非錯誤)。`cluster_members` 不會列出該空 cid(§2.5-2)。
i. **`kmeans` `iters <= 0`**:迴圈 `range(iters)` 不執行 → `assign` 仍為 `None` → 取結果時為未定義。**釘死防禦**:`iters` 預設 10;契約假設 `iters >= 1`。為避免 `assign is None`,實作須保證**至少跑一輪**——**規定 `iters < 1` 時視為跑 1 輪**(即 `effective_iters = max(1, iters)`),使 `kmeans(items, k, iters=0)` 仍回「以初始中心做一次指派」的確定結果(釘死於 AC20)。
j. **`cluster_members` 空 dict**:`{}` → `{}`。
k. **不 mutate 輸入**:所有函式**不得修改**傳入的向量(`a`/`b`/`query`/各 vector)、`items` list、`assignments` dict 內容或順序(`_vec` 以 `np.asarray` 產生新陣列;`centers = X[:k].copy()` 用 copy;排序在內部新 list 上做;`cluster_members` 產生新 dict)。
l. **純函式 / 無隨機**:四函式皆無隨機、無時間、無 I/O,**同輸入同參數恆回同結果**(這是 kmeans 確定性的根本)。
m. **dtype 假設**:契約假設向量為數值序列(`int`/`float`);內部一律 `float64` 化,故 `int` 與 `float` 輸入結果一致。Tier A 信任契約,不對非數值元素額外防禦。

---

## 5. Acceptance Criteria(可被 pytest 驗;以可手算的合成小向量 / 分得很開的 2D 點釘死確切值)

> 測試入口:`cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_embcluster.py -p no:cacheprovider --strict-markers -q`(conftest 已把 `5_PG_Develop` 加進 sys.path,直接 `import embcluster`)。
>
> **AC 釘值推導說明(給 PM 對照,確保期望值可手算)**:
> - cosine 用單位 / 簡單向量(`[1,0]`/`[0,1]`/`[1,1]`/`[3,4]`),浮點相等用 `pytest.approx(...)` 或 `math.isclose(..., abs_tol=1e-9)`;**整數值(1.0/0.0/-1.0)可直接 `==`**(這些是精確可表示的浮點)。
> - kmeans 用**分得很開的 2D 點**,且**把前 k 個 item 排成 k 個分離種子**,使「初始中心 = 前 k 點」恰為三個真實群心 → 一輪指派即收斂、結果與直覺一致且唯一。
> - 平手(tie)案例專門構造「點到兩中心等距」以驗「取最小 cluster_id」。
>
> 共用合成資料(供下列 AC 引用):
> ```python
> import numpy as np, math
> # --- kmeans 分離點群:前 k 個 item 是 k 個分離種子,其餘各靠近一個種子 ---
> # 兩群(k=2):前 k=2 項 = 兩個「分離種子」a=(0,0)、c=(10,10),使初始中心=真群心 → 1 輪即收斂
> ITEMS_2 = [("a", [0.0, 0.0]), ("c", [10.0, 10.0]),
>            ("b", [1.0, 1.0]), ("d", [11.0, 11.0])]   # 初始中心=a,c;a,b→群0、c,d→群1(見 AC15/AC20)
> # 三群(k=3):前 3 item 為 (0,0)/(50,0)/(100,0) 三分離種子,後 3 各靠一個
> ITEMS_3 = [("c0", [0.0, 0.0]), ("c1", [50.0, 0.0]), ("c2", [100.0, 0.0]),
>            ("a",  [1.0, 1.0]), ("b",  [51.0, 1.0]),  ("d",  [99.0, 1.0])]
> #   初始中心=c0/c1/c2;a 近 c0、b 近 c1、d 近 c2 → {c0:0,c1:1,c2:2,a:0,b:1,d:2}(AC16)
> # 平手:種子 s0=(0,0)、s1=(10,0);mid=(5,0) 到兩者等距 → 取最小 cluster_id 0
> ITEMS_TIE = [("s0", [0.0, 0.0]), ("s1", [10.0, 0.0]), ("mid", [5.0, 0.0])]  # AC18
> ```

**cosine_similarity — 確切浮點 / 零向量 / 對稱 / 尺度不變 / 型別**
- **AC1**:相同向量 → `embcluster.cosine_similarity([1, 0], [1, 0]) == 1.0`(精確 `1.0`,可直接 `==`)。
- **AC2**:正交 → `embcluster.cosine_similarity([1, 0], [0, 1]) == 0.0`(精確 `0.0`)。
- **AC3**:反向 → `embcluster.cosine_similarity([1, 0], [-1, 0]) == -1.0`(精確 `-1.0`)。
- **AC4**:45° → `embcluster.cosine_similarity([1, 1], [1, 0]) == pytest.approx(1/math.sqrt(2))`(≈ `0.7071067811865475`;以 approx 比對)。
- **AC5**:一般向量 → `embcluster.cosine_similarity([3, 4], [3, 4]) == 1.0`,且 `embcluster.cosine_similarity([1, 2, 2], [2, 4, 4]) == pytest.approx(1.0)`(平行正純量倍 → 1.0)。
- **AC6**:**零向量(左)** → `embcluster.cosine_similarity([0, 0], [1, 2]) == 0.0`(精確,**不除零、不回 nan**)。
- **AC7**:**零向量(右)** → `embcluster.cosine_similarity([1, 2], [0, 0]) == 0.0`;**兩者皆零** → `embcluster.cosine_similarity([0, 0], [0, 0]) == 0.0`。
- **AC8**:回傳型別為 Python 內建 `float`(非 `np.float64`)—— `type(embcluster.cosine_similarity([1, 0], [1, 0])) is float`(輔助斷言,與 AC1 確切值並存,非代理)。
- **AC9**:對稱 —— `embcluster.cosine_similarity([1, 2, 3], [4, 5, 6]) == embcluster.cosine_similarity([4, 5, 6], [1, 2, 3])`(確切相等)。
- **AC10**:**尺度不變(metamorphic)** —— `embcluster.cosine_similarity([1, 1], [1, 0]) == pytest.approx(embcluster.cosine_similarity([2, 2], [5, 0]))`(正純量倍不改餘弦)。

**nearest — 確切排序(相似降序、name 升序)/ top_k 截斷 / 空 items / 邊界**
> 共用:`Q = [1, 0]`;`CANDS = [("x", [1, 0]), ("y", [0, 1]), ("z", [-1, 0]), ("w", [1, 1])]`。
> 餘弦:x→1.0、w→1/√2≈0.7071、y→0.0、z→-1.0。降序 = x, w, y, z。
- **AC11**:全排序 + 充分 top_k —— `embcluster.nearest([1, 0], CANDS, top_k=10)` 回 4 元素,**順序與名字確切** `[("x", ...), ("w", ...), ("y", ...), ("z", ...)]`,且相似度值:第 0 個 `== pytest.approx(1.0)`、第 1 個 `== pytest.approx(1/math.sqrt(2))`、第 2 個 `== pytest.approx(0.0)`、第 3 個 `== pytest.approx(-1.0)`。
- **AC12**:**top_k 截斷** —— `[n for n, _ in embcluster.nearest([1, 0], CANDS, top_k=2)] == ["x", "w"]`(只回前 2 高相似;確切順序)。
- **AC13**:**similarity 平手 → name 升序** —— 對 `TIE = [("zebra", [1, 0]), ("apple", [1, 0]), ("mango", [0, 1])]`,`[n for n, _ in embcluster.nearest([1, 0], TIE, top_k=5)] == ["apple", "zebra", "mango"]`(apple/zebra 同相似 1.0 → name 升序 `"apple" < "zebra"`;mango 相似 0.0 在後)。
- **AC14**:**空 items / top_k 邊界** —— `embcluster.nearest([1, 0], [], top_k=5) == []`;且 `embcluster.nearest([1, 0], CANDS, top_k=0) == []`(top_k=0 回空);且 `len(embcluster.nearest([1, 0], CANDS, top_k=100)) == 4`(top_k 超量回全部)。

**kmeans — 分離點群確切指派 / 確定性可重現 / 平手 / 單點 / k==n / iters 邊界**
- **AC15**:**兩群分離點(主案例)** —— `embcluster.kmeans(ITEMS_2, k=2, iters=10) == {"a": 0, "b": 0, "c": 1, "d": 1}`(初始中心 a=(0,0)、c=(10,10);a,b 落群 0、c,d 落群 1;**確切 dict**)。
- **AC16**:**三群分離點** —— `embcluster.kmeans(ITEMS_3, k=3, iters=10) == {"c0": 0, "c1": 1, "c2": 2, "a": 0, "b": 1, "d": 2}`(前 3 種子各成群,a/b/d 各靠 c0/c1/c2;**確切 dict**)。
- **AC17**:**確定性可重現(metamorphic)** —— `embcluster.kmeans(ITEMS_3, 3, 10) == embcluster.kmeans(ITEMS_3, 3, 10)`(再跑一次逐 key/value identical);且 `embcluster.kmeans(ITEMS_3, 3, 10) == embcluster.kmeans(ITEMS_3, 3, 50)`(已收斂 → 更多 iters 不改結果)。
- **AC18**:**平手取最小 cluster_id** —— `embcluster.kmeans(ITEMS_TIE, k=2, iters=10) == {"s0": 0, "s1": 1, "mid": 0}`(初始中心 s0=(0,0)、s1=(10,0);mid=(5,0) 到兩中心等距 5 → 平手取**最小** cluster_id 0;更新後 c0=(2.5,0)、c1=(10,0),再指派穩定;**確切**)。
- **AC19**:**單點 / k==n** —— `embcluster.kmeans([("only", [3.0, 4.0])], k=1, iters=10) == {"only": 0}`;且 `embcluster.kmeans([("p", [0.0, 0.0]), ("q", [9.0, 9.0])], k=2, iters=10) == {"p": 0, "q": 1}`(k==n,每點自成一群)。
- **AC20**:**iters 邊界(至少跑一輪)** —— `embcluster.kmeans(ITEMS_2, k=2, iters=0) == {"a": 0, "b": 0, "c": 1, "d": 1}`(§4-i:`iters<1` 視為跑 1 輪 → 以初始中心 a=(0,0)、c=(10,10) 做一次指派,a,b 近 (0,0) 落 0、c,d 近 (10,10) 落 1;確切、不拋錯、不回 None)。
- **AC21**:回傳 value 為 Python 內建 `int` 且全在 `0..k-1` —— 對 `embcluster.kmeans(ITEMS_3, 3, 10)`,`all(type(v) is int and 0 <= v < 3 for v in result.values())`(輔助斷言,與 AC16 確切值並存)。

**kmeans 錯誤路徑(釘死拋 ValueError)**
- **AC22**:`k <= 0` 拒 —— `embcluster.kmeans(ITEMS_2, k=0, iters=10)` 觸發 `pytest.raises(ValueError)`;`embcluster.kmeans(ITEMS_2, k=-1, iters=10)` 亦觸發。
- **AC23**:`k > len(items)` 拒 —— `embcluster.kmeans(ITEMS_2, k=5, iters=10)` 觸發 `pytest.raises(ValueError)`(4 點要 5 群)。
- **AC24**:空 items 拒 —— `embcluster.kmeans([], k=1, iters=10)` 觸發 `pytest.raises(ValueError)`。

**nearest 錯誤路徑**
- **AC25**:`top_k < 0` 拒 —— `embcluster.nearest([1, 0], CANDS, top_k=-1)` 觸發 `pytest.raises(ValueError)`。

**cluster_members — 反轉 / name 升序 / 空群不列 / 空 dict / 與 kmeans 串接**
- **AC26**:反轉 + name 升序 —— `embcluster.cluster_members({"c0": 0, "c1": 1, "c2": 2, "a": 0, "b": 1, "d": 2}) == {0: ["a", "c0"], 1: ["b", "c1"], 2: ["c2", "d"]}`(各群 name 字典序升序;**確切 dict**)。
- **AC27**:空 dict —— `embcluster.cluster_members({}) == {}`。
- **AC28**:與 kmeans 串接 —— `embcluster.cluster_members(embcluster.kmeans(ITEMS_2, 2, 10)) == {0: ["a", "b"], 1: ["c", "d"]}`(AC15 的指派 → 反轉聚群,name 升序;**確切**)。
- **AC29**:**空群不列(釘死)** —— 對 `ASG = {"s0": 0, "s1": 1, "e": 2}`(cluster_id 1 仍有 s1;此測 cid 連續且皆有成員的反例不足以驗空群,改用)`ASG2 = {"x": 0, "y": 0, "z": 2}`(無 cluster_id 1)→ `embcluster.cluster_members(ASG2) == {0: ["x", "y"], 2: ["z"]}`(結果**不含 key 1**;只列出現過的 cid)。

**不 mutate 輸入**
- **AC30**:呼叫各函式後傳入物件不變 —— 令 `vec = [1.0, 0.0]`,呼叫 `embcluster.cosine_similarity(vec, [0, 1])` 後 `vec == [1.0, 0.0]`(內容不變);令 `items = list(ITEMS_2)` 的淺拷貝、`before = [(n, list(v)) for n, v in ITEMS_2]`,呼叫 `embcluster.kmeans(ITEMS_2, 2, 10)` 後 `ITEMS_2` 的每個向量內容與順序不變(`[(n, list(v)) for n, v in ITEMS_2] == before`);令 `asg = {"a": 0, "b": 1}`,呼叫 `embcluster.cluster_members(asg)` 後 `asg == {"a": 0, "b": 1}`(原 dict 不被改)。

---

## 6. 與其他模組的邊界(防越權)

- **不負責產生 embedding 向量**:DINO/SAM/CLIP 等模型推論、權重下載、影像→向量的特徵抽取**全部在本模組之外**(離線預算)。本模組吃的是**已就緒的數值向量**(`list`/`ndarray`),對來源完全不可知。
- **不負責影像 / 檔案**:**零檔案 I/O、零 PIL、零影像解碼**(與 `imgio`/`simhash` 不同;simhash 吃影像陣列算 hash,本模組吃抽象向量算餘弦/歐氏)。不開關任何檔案、不讀寫 sidecar、不持久化 / 不建索引 / 不快取;每次呼叫即時計算。
- **不依賴 sklearn / scipy**:k-means 為**自寫確定性實作**(初始中心 = 前 k 點、固定迭代、平手取最小 cluster_id、空群中心不動),刻意避開 sklearn 的隨機初始化以利釘死 AC。
- **不負責 GUI / 視覺化**:`nearest` 回 `list[(name, similarity)]`、`kmeans` 回 `{name: cluster_id}`、`cluster_members` 回 `{cid: [names]}`;縮圖牆 / 聚類檢視 / 排序呈現由 app(Streamlit)控,本模組不產出任何可顯示影像或 UI 元件。
- **不 import 任何業務模組**:**零 import** `imgio`/`simhash`/`framecompare`/`yolo`/`overlay`/`sidecar`/`tagging` 等;唯一外部相依為 `numpy`。
- 本模組對外承諾:純函式、無檔案副作用、**無隨機**、**輸入向量 / items / assignments 不被 mutate**、僅依賴 `numpy`、**零 import 任何業務模組**(可獨立平行驗收)。
```