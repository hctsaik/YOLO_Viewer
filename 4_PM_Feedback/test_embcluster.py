"""embcluster 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/17_embcluster.md(AC1..AC30 + §2/§3/§4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import embcluster`。此時實作尚未生成,import 不到屬正常(非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

純邏輯 Tier A 模組:對外部預先算好的 embedding 向量做餘弦相似搜尋與
確定性 k-means 分群(零 I/O、零 GUI、僅依賴 numpy)。
- cosine_similarity:dot(a,b)/(|a||b|);任一 norm==0 → 0.0(短路,先於除法);回內建 float。
- nearest:對每 candidate 算 cosine;依 (similarity 降序, name 升序) 排;回前 top_k。
- kmeans:確定性硬分群,初始中心=前 k 點、固定 iters 輪、平手取最小 cluster_id、
  空群中心不動;iters<1 視為跑 1 輪;回 {name: int cluster_id}。
- cluster_members:反轉 {name:cid} → {cid:[names 升序]};只列出現過的 cid。

期望值直接抄設計(可手算 / 釘死):cosine 精確值(1.0/0.0/-1.0)直接 `==`,
非整數值(1/√2)用 pytest.approx;kmeans 確切 dict 照釘值
(AC15 {a:0,b:0,c:1,d:1}、AC20 iters=0 同值)。不自行重算。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_embcluster.py -p no:cacheprovider --strict-markers -q
"""
import math

import pytest

import embcluster


# =====================================================================
# 共用合成夾具(設計 §5 釘死;原樣抄,不重排)
# 注意:ITEMS_2 前兩項是 a 與 c(兩個分離種子),其後才是 b、d。
# =====================================================================

# kmeans 分離點群:前 k 個 item 是 k 個分離種子,其餘各靠近一個種子。
# 兩群(k=2):前 k=2 項 = 兩個「分離種子」a=(0,0)、c=(10,10),使初始中心=真群心 → 1 輪即收斂
ITEMS_2 = [("a", [0.0, 0.0]), ("c", [10.0, 10.0]),
           ("b", [1.0, 1.0]), ("d", [11.0, 11.0])]   # 初始中心=a,c;a,b→群0、c,d→群1(AC15/AC20)
# 三群(k=3):前 3 item 為 (0,0)/(50,0)/(100,0) 三分離種子,後 3 各靠一個
ITEMS_3 = [("c0", [0.0, 0.0]), ("c1", [50.0, 0.0]), ("c2", [100.0, 0.0]),
           ("a",  [1.0, 1.0]), ("b",  [51.0, 1.0]),  ("d",  [99.0, 1.0])]
#   初始中心=c0/c1/c2;a 近 c0、b 近 c1、d 近 c2 → {c0:0,c1:1,c2:2,a:0,b:1,d:2}(AC16)
# 平手:種子 s0=(0,0)、s1=(10,0);mid=(5,0) 到兩者等距 → 取最小 cluster_id 0
ITEMS_TIE = [("s0", [0.0, 0.0]), ("s1", [10.0, 0.0]), ("mid", [5.0, 0.0])]  # AC18

# nearest 共用:Q=[1,0];CANDS 餘弦 x→1.0、w→1/√2、y→0.0、z→-1.0;降序 x,w,y,z
CANDS = [("x", [1, 0]), ("y", [0, 1]), ("z", [-1, 0]), ("w", [1, 1])]
# nearest 平手:apple/zebra 同相似 1.0 → name 升序;mango 相似 0.0 在後
TIE = [("zebra", [1, 0]), ("apple", [1, 0]), ("mango", [0, 1])]


# =====================================================================
# cosine_similarity — 確切浮點 / 零向量 / 對稱 / 尺度不變 / 型別
# =====================================================================

def test_ac1_cosine_identical_is_one():
    # AC1:相同向量 → 餘弦精確 1.0(可直接 ==)。
    assert embcluster.cosine_similarity([1, 0], [1, 0]) == 1.0


def test_ac2_cosine_orthogonal_is_zero():
    # AC2:正交 → 精確 0.0。
    assert embcluster.cosine_similarity([1, 0], [0, 1]) == 0.0


def test_ac3_cosine_opposite_is_minus_one():
    # AC3:反向 → 精確 -1.0。
    assert embcluster.cosine_similarity([1, 0], [-1, 0]) == -1.0


def test_ac4_cosine_45deg_approx():
    # AC4:45° → 1/√2 ≈ 0.7071067811865475(用 approx)。
    assert embcluster.cosine_similarity([1, 1], [1, 0]) == pytest.approx(1 / math.sqrt(2))


def test_ac5_cosine_general_and_parallel_scalar_multiple():
    # AC5:一般向量 [3,4] 自身 → 1.0;平行正純量倍 [1,2,2]~[2,4,4] → 1.0。
    assert embcluster.cosine_similarity([3, 4], [3, 4]) == 1.0
    assert embcluster.cosine_similarity([1, 2, 2], [2, 4, 4]) == pytest.approx(1.0)


def test_ac6_cosine_zero_vector_left_is_zero():
    # AC6:零向量(左)→ 精確 0.0(不除零、不回 nan)。
    assert embcluster.cosine_similarity([0, 0], [1, 2]) == 0.0


def test_ac7_cosine_zero_vector_right_and_both_zero():
    # AC7:零向量(右)→ 0.0;兩者皆零 → 0.0。
    assert embcluster.cosine_similarity([1, 2], [0, 0]) == 0.0
    assert embcluster.cosine_similarity([0, 0], [0, 0]) == 0.0


def test_ac8_cosine_returns_builtin_float():
    # AC8:回傳型別為 Python 內建 float(非 np.float64)(輔助斷言,與 AC1 確切值並存)。
    assert type(embcluster.cosine_similarity([1, 0], [1, 0])) is float


def test_ac9_cosine_symmetric():
    # AC9:對稱 —— cos(a,b) == cos(b,a)(確切相等)。
    assert embcluster.cosine_similarity([1, 2, 3], [4, 5, 6]) == \
        embcluster.cosine_similarity([4, 5, 6], [1, 2, 3])


def test_ac10_cosine_scale_invariant_metamorphic():
    # AC10:尺度不變(metamorphic)—— 正純量倍不改餘弦。
    assert embcluster.cosine_similarity([1, 1], [1, 0]) == \
        pytest.approx(embcluster.cosine_similarity([2, 2], [5, 0]))


# =====================================================================
# nearest — 確切排序(相似降序、name 升序)/ top_k 截斷 / 空 items / 邊界
# =====================================================================

def test_ac11_nearest_full_sorted_with_values():
    # AC11:充分 top_k 全排序 —— 順序與名字確切 [x,w,y,z],且相似度值釘死。
    res = embcluster.nearest([1, 0], CANDS, top_k=10)
    assert [n for n, _ in res] == ["x", "w", "y", "z"]
    assert len(res) == 4
    assert res[0][1] == pytest.approx(1.0)
    assert res[1][1] == pytest.approx(1 / math.sqrt(2))
    assert res[2][1] == pytest.approx(0.0)
    assert res[3][1] == pytest.approx(-1.0)


def test_ac12_nearest_top_k_truncation():
    # AC12:top_k 截斷 —— 只回前 2 高相似,確切順序 [x, w]。
    assert [n for n, _ in embcluster.nearest([1, 0], CANDS, top_k=2)] == ["x", "w"]


def test_ac13_nearest_tiebreak_name_ascending():
    # AC13:similarity 平手 → name 升序 —— apple/zebra 同相似 1.0("apple"<"zebra"),mango 在後。
    assert [n for n, _ in embcluster.nearest([1, 0], TIE, top_k=5)] == \
        ["apple", "zebra", "mango"]


def test_ac14_nearest_empty_items_and_top_k_boundaries():
    # AC14:空 items → [];top_k==0 → [];top_k 超量 → 回全部(4)。
    assert embcluster.nearest([1, 0], [], top_k=5) == []
    assert embcluster.nearest([1, 0], CANDS, top_k=0) == []
    assert len(embcluster.nearest([1, 0], CANDS, top_k=100)) == 4


# =====================================================================
# kmeans — 分離點群確切指派 / 確定性可重現 / 平手 / 單點 / k==n / iters 邊界
# =====================================================================

def test_ac15_kmeans_two_clusters_separated():
    # AC15:兩群分離點(主案例)—— 初始中心 a=(0,0)、c=(10,10);a,b→群0、c,d→群1(確切 dict)。
    assert embcluster.kmeans(ITEMS_2, k=2, iters=10) == \
        {"a": 0, "b": 0, "c": 1, "d": 1}


def test_ac16_kmeans_three_clusters_separated():
    # AC16:三群分離點 —— 前 3 種子各成群,a/b/d 各靠 c0/c1/c2(確切 dict)。
    assert embcluster.kmeans(ITEMS_3, k=3, iters=10) == \
        {"c0": 0, "c1": 1, "c2": 2, "a": 0, "b": 1, "d": 2}


def test_ac17_kmeans_deterministic_reproducible_metamorphic():
    # AC17:確定性可重現(metamorphic)—— 再跑一次逐 key/value identical;
    # 且已收斂 → 更多 iters(50)不改結果。
    assert embcluster.kmeans(ITEMS_3, 3, 10) == embcluster.kmeans(ITEMS_3, 3, 10)
    assert embcluster.kmeans(ITEMS_3, 3, 10) == embcluster.kmeans(ITEMS_3, 3, 50)


def test_ac18_kmeans_tie_takes_min_cluster_id():
    # AC18:平手取最小 cluster_id —— mid=(5,0) 到 s0/s1 等距 5 → 取最小 cid 0(確切)。
    assert embcluster.kmeans(ITEMS_TIE, k=2, iters=10) == \
        {"s0": 0, "s1": 1, "mid": 0}


def test_ac19_kmeans_single_point_and_k_equals_n():
    # AC19:單點(k=1)→ {only:0};k==n → 每點各成一群。
    assert embcluster.kmeans([("only", [3.0, 4.0])], k=1, iters=10) == {"only": 0}
    assert embcluster.kmeans([("p", [0.0, 0.0]), ("q", [9.0, 9.0])], k=2, iters=10) == \
        {"p": 0, "q": 1}


def test_ac20_kmeans_iters_zero_runs_one_round():
    # AC20:iters 邊界(至少跑一輪)—— iters=0 視為跑 1 輪,以初始中心做一次指派,
    # 結果同 AC15(確切、不拋錯、不回 None)。
    assert embcluster.kmeans(ITEMS_2, k=2, iters=0) == \
        {"a": 0, "b": 0, "c": 1, "d": 1}


def test_ac21_kmeans_values_are_builtin_int_in_range():
    # AC21:回傳 value 為 Python 內建 int 且全在 0..k-1(輔助斷言,與 AC16 確切值並存)。
    result = embcluster.kmeans(ITEMS_3, 3, 10)
    assert all(type(v) is int and 0 <= v < 3 for v in result.values())


# =====================================================================
# kmeans 錯誤路徑(釘死拋 ValueError)—— 各自獨立
# =====================================================================

def test_ac22_kmeans_k_le_0_raises():
    # AC22:k <= 0 拒(k=0 與 k=-1 各自獨立驗)。
    with pytest.raises(ValueError):
        embcluster.kmeans(ITEMS_2, k=0, iters=10)
    with pytest.raises(ValueError):
        embcluster.kmeans(ITEMS_2, k=-1, iters=10)


def test_ac23_kmeans_k_gt_n_raises():
    # AC23:k > len(items) 拒 —— 4 點要 5 群。
    with pytest.raises(ValueError):
        embcluster.kmeans(ITEMS_2, k=5, iters=10)


def test_ac24_kmeans_empty_items_raises():
    # AC24:空 items 拒。
    with pytest.raises(ValueError):
        embcluster.kmeans([], k=1, iters=10)


# =====================================================================
# nearest 錯誤路徑
# =====================================================================

def test_ac25_nearest_negative_top_k_raises():
    # AC25:top_k < 0 拒。
    with pytest.raises(ValueError):
        embcluster.nearest([1, 0], CANDS, top_k=-1)


# =====================================================================
# cluster_members — 反轉 / name 升序 / 空群不列 / 空 dict / 與 kmeans 串接
# =====================================================================

def test_ac26_cluster_members_invert_and_name_ascending():
    # AC26:反轉 + 各群 name 字典序升序(確切 dict)。
    assert embcluster.cluster_members(
        {"c0": 0, "c1": 1, "c2": 2, "a": 0, "b": 1, "d": 2}) == \
        {0: ["a", "c0"], 1: ["b", "c1"], 2: ["c2", "d"]}


def test_ac27_cluster_members_empty_dict():
    # AC27:空 dict → {}。
    assert embcluster.cluster_members({}) == {}


def test_ac28_cluster_members_chained_with_kmeans():
    # AC28:與 kmeans 串接 —— AC15 的指派 → 反轉聚群,name 升序(確切)。
    assert embcluster.cluster_members(embcluster.kmeans(ITEMS_2, 2, 10)) == \
        {0: ["a", "b"], 1: ["c", "d"]}


def test_ac29_cluster_members_empty_cluster_not_listed():
    # AC29:空群不列(釘死)—— ASG2 無 cluster_id 1 → 結果不含 key 1,只列出現過的 cid。
    ASG2 = {"x": 0, "y": 0, "z": 2}
    assert embcluster.cluster_members(ASG2) == {0: ["x", "y"], 2: ["z"]}


# =====================================================================
# 不 mutate 輸入
# =====================================================================

def test_ac30_no_mutate_inputs():
    # AC30:呼叫各函式後傳入物件內容與順序不變。
    vec = [1.0, 0.0]
    embcluster.cosine_similarity(vec, [0, 1])
    assert vec == [1.0, 0.0]

    before = [(n, list(v)) for n, v in ITEMS_2]
    embcluster.kmeans(ITEMS_2, 2, 10)
    assert [(n, list(v)) for n, v in ITEMS_2] == before

    asg = {"a": 0, "b": 1}
    embcluster.cluster_members(asg)
    assert asg == {"a": 0, "b": 1}


# =====================================================================
# 推導 / property 測試(設計未明列;由 §2/§3/§4 契約推導,即使同源也能逼出實作 bug)
# =====================================================================

def test_property_cosine_in_theoretical_range():
    # 推導(§2.2-3 值域):任意向量對,餘弦必落在 [-1.0, 1.0](浮點容差內);
    # 零向量短路回 0.0 亦在範圍內。比單點 AC 更強。
    pairs = [
        ([1, 0], [1, 0]), ([1, 0], [0, 1]), ([1, 0], [-1, 0]),
        ([1, 1], [1, 0]), ([3, 4], [4, 3]), ([0, 0], [1, 2]),
        ([1, 2, 3], [4, 5, 6]), ([-2, -3], [5, 7]), ([2, 2], [5, 0]),
    ]
    for a, b in pairs:
        s = embcluster.cosine_similarity(a, b)
        assert -1.0 - 1e-9 <= s <= 1.0 + 1e-9


def test_property_cosine_self_is_one_arbitrary_nonzero():
    # 推導(§2.2-3 同向):任意非零向量與自己 → 餘弦 == 1.0(approx);比 AC1/AC5 單點更強。
    for v in ([1, 0], [3, 4], [1, 2, 3], [-5, 2, 7], [0.5, 0.25, 0.125]):
        assert embcluster.cosine_similarity(v, v) == pytest.approx(1.0)


def test_property_cosine_symmetric_arbitrary():
    # 推導(§2.2-3 對稱):對任意向量對,cos(a,b) == cos(b,a)(確切相等);比 AC9 單點更強。
    pairs = [([1, 2, 3], [4, 5, 6]), ([1, 0], [1, 1]), ([3, 4], [0, 0]),
             ([-1, 2], [3, -4]), ([0, 0], [0, 0])]
    for a, b in pairs:
        assert embcluster.cosine_similarity(a, b) == embcluster.cosine_similarity(b, a)


def test_property_cosine_int_float_equivalence():
    # 推導(§2.1 / §4m):int 與 float 輸入經 float64 化後等價 → 結果完全相同。
    assert embcluster.cosine_similarity([3, 4], [3, 4]) == \
        embcluster.cosine_similarity([3.0, 4.0], [3.0, 4.0])
    assert embcluster.cosine_similarity([1, 2, 2], [2, 4, 4]) == \
        embcluster.cosine_similarity([1.0, 2.0, 2.0], [2.0, 4.0, 4.0])


def test_property_nearest_results_sorted_and_within_top_k():
    # 推導(§2.3 排序 + 截斷):回傳 similarity 必非遞增(降序),長度 <= top_k 且 <= len(items),
    # 同相似區段內 name 升序。比 AC11/AC12 單點更強。
    for tk in (0, 1, 2, 3, 10):
        res = embcluster.nearest([1, 0], CANDS, top_k=tk)
        sims = [s for _, s in res]
        assert sims == sorted(sims, reverse=True)
        assert len(res) <= tk
        assert len(res) <= len(CANDS)
        assert res == sorted(res, key=lambda t: (-t[1], t[0]))


def test_property_nearest_deterministic_repeatable():
    # 推導(§4l 純函式):同輸入同 top_k 恆回同結果(無隨機/時間/I/O)。
    r1 = embcluster.nearest([1, 0], CANDS, top_k=4)
    r2 = embcluster.nearest([1, 0], CANDS, top_k=4)
    assert [n for n, _ in r1] == [n for n, _ in r2]


def test_property_kmeans_deterministic_repeatable_arbitrary():
    # 推導(§2.4 確定性 / §4l):同 (items,k,iters) 多次呼叫必逐 key/value 相同。
    runs = [embcluster.kmeans(ITEMS_2, 2, 10) for _ in range(5)]
    for r in runs:
        assert r == runs[0]


def test_property_kmeans_assignment_partitions_all_names():
    # 推導(§2.4-4):每個 item name 都恰好得到一個 0..k-1 的 cluster_id,
    # 且 keys 集合 == names 集合(無遺漏、無多出)。比 AC15/AC16 更強。
    for items, k in ((ITEMS_2, 2), (ITEMS_3, 3), (ITEMS_TIE, 2)):
        result = embcluster.kmeans(items, k, 10)
        names = {n for n, _ in items}
        assert set(result.keys()) == names
        assert all(0 <= v < k for v in result.values())


def test_property_kmeans_cluster_members_roundtrip():
    # 推導(§2.5 串接不變量):cluster_members(kmeans(...)) 把每群成員聚在同一 cid;
    # 攤平所有群成員 == 全部 names(每個 name 恰出現一次)。
    asg = embcluster.kmeans(ITEMS_3, 3, 10)
    members = embcluster.cluster_members(asg)
    flat = sorted(n for names in members.values() for n in names)
    assert flat == sorted(n for n, _ in ITEMS_3)
    # 同一群成員的 cluster_id 在 asg 中相同
    for cid, names in members.items():
        assert all(asg[n] == cid for n in names)


def test_property_cluster_members_lists_sorted_ascending():
    # 推導(§2.5-3):任意 assignments,每個 cid 的成員 list 必為 name 升序。
    asg = {"zebra": 0, "apple": 0, "mango": 1, "banana": 1, "kiwi": 0}
    members = embcluster.cluster_members(asg)
    for names in members.values():
        assert names == sorted(names)
