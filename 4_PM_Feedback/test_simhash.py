"""simhash 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/14_simhash.md(AC1..AC29 + §2/§3/§4 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import simhash`。此時實作尚未生成,import 不到屬正常(非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

純邏輯 Tier A 模組:影像感知雜湊(perceptual hash)。
- ahash:灰階化 → 縮放(NEAREST)到 hash_size×hash_size → bit=(pixel>mean) → MSB-first 打包。
- dhash:灰階化 → 縮放到 (hash_size+1)×hash_size → bit=(left>right) → MSB-first 打包。
- hamming:bin(h1 ^ h2).count("1")。
- find_similar:回 <= max_distance 的 (name, distance),依 (distance 升序, name 升序)。

測試以設計 §5 釘死的可手算合成陣列(G_CHECKER/G_LR/G_FLAT/D_A/D_FLAT)與確切 hash 整數斷言:
ahash(G_CHECKER,2)==6、ahash(G_LR,2)==5、ahash(全 0 8x8)==0、AC7 64-bit==1085102592571150095、
dhash(D_A,2)==6、dhash AC10(8x9)==6148914691236517205(0x5555555555555555)、
find_similar AC18==[("same",0),("flat",2),("lr",2)]。
find_similar AC18/19/20/21/22/23/28 一律傳 hash_size=2(與 2x2/2x3 候選尺寸一致,resize 為 identity)。
期望值直接抄設計(可手算),不自行重算。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_simhash.py -p no:cacheprovider --strict-markers -q
"""
import numpy as np
import pytest

import simhash


# =====================================================================
# 共用合成陣列(設計 §5 釘死,確切 hash 可手算)
# =====================================================================

def _G_CHECKER():
    # 2x2 灰階棋盤:[[10,90],[90,10]],mean=50。
    # bit=(v>50): F,T,T,F → MSB-first 0b0110 = 6。ahash(., 2) == 6。
    return np.array([[10, 90], [90, 10]], dtype=np.uint8)


def _G_LR():
    # 2x2 左暗右亮:[[10,90],[10,90]],mean=50。
    # bit: F,T,F,T → 0b0101 = 5。ahash(., 2) == 5。
    return np.array([[10, 90], [10, 90]], dtype=np.uint8)


def _G_FLAT():
    # 2x2 全均勻 50:mean=50,皆 50>50=F → 0。ahash(., 2) == 0。
    return np.full((2, 2), 50, dtype=np.uint8)


def _D_A():
    # 2x3 灰階:[[10,90,10],[90,10,90]]。
    # 列0 對 (10>90=F,90>10=T)→[F,T];列1 (90>10=T,10>90=F)→[T,F]
    # flatten [F,T,T,F] MSB-first = 0b0110 = 6。dhash(., 2) == 6。
    return np.array([[10, 90, 10], [90, 10, 90]], dtype=np.uint8)


def _D_FLAT():
    # 2x3 全均勻 50 → dhash 0。
    return np.full((2, 3), 50, dtype=np.uint8)


# =====================================================================
# ahash — 確切整數 / `>` 準則 / 均勻邊界 / RGB↔灰階一致 / hash_size
# =====================================================================

def test_ac1_ahash_checker_exact():
    # AC1:棋盤,mean=50,bits [F,T,T,F] MSB-first = 0b0110 = 6(確切整數)。
    assert simhash.ahash(_G_CHECKER(), hash_size=2) == 6


def test_ac2_ahash_left_right_exact():
    # AC2:左暗右亮,bits [F,T,F,T] = 0b0101 = 5(確切整數)。
    assert simhash.ahash(_G_LR(), hash_size=2) == 5


def test_ac3_ahash_flat_is_zero():
    # AC3:全均勻 → 所有 v>mean 皆 False(嚴格 `>` + 均勻邊界)→ 整數 0。
    assert simhash.ahash(_G_FLAT(), hash_size=2) == 0


def test_ac4_ahash_returns_nonneg_int():
    # AC4:回傳型別為 Python int 且非負(輔助斷言,與 AC1 確切值並存,非代理)。
    h = simhash.ahash(_G_CHECKER(), 2)
    assert isinstance(h, int)
    assert h >= 0


def test_ac5_ahash_rgb_matches_grey():
    # AC5:RGB↔灰階一致 —— 三通道相等純色 (2,2,3),灰階還原 → ahash 與灰階版相等 == 6。
    rgb_checker = np.stack([_G_CHECKER()] * 3, axis=-1)
    assert rgb_checker.shape == (2, 2, 3)
    assert simhash.ahash(rgb_checker, 2) == simhash.ahash(_G_CHECKER(), 2) == 6


def test_ac6_ahash_hash_size_8_flat_is_zero():
    # AC6:hash_size=8 全均勻 123 → 64 位全 0。
    assert simhash.ahash(np.full((8, 8), 123, np.uint8), hash_size=8) == 0


def test_ac7_ahash_bit_range_exact_64bit():
    # AC7:位元範圍 —— 全 0 RGB(8x8x3)→ 0;
    # 左半全 0、右半全 255 的 8x8(mean=127.5,左<mean=0、右>mean=1,每列 0b00001111=0x0F)
    # → 8 列串接 MSB-first = 0x0F0F0F0F0F0F0F0F == 1085102592571150095(確切 64-bit)。
    assert simhash.ahash(np.full((8, 8, 3), 0, np.uint8), 8) == 0
    g = np.zeros((8, 8), np.uint8)
    g[:, 4:] = 255
    assert simhash.ahash(g, 8) == int("0000111100001111" * 4, 2)
    assert simhash.ahash(g, 8) == 0x0F0F0F0F0F0F0F0F
    assert simhash.ahash(g, 8) == 1085102592571150095


# =====================================================================
# dhash — 確切整數 / left>right 準則 / 均勻邊界 / RGB↔灰階一致
# =====================================================================

def test_ac8_dhash_checker_exact():
    # AC8:2x3 水平梯度 bits [F,T,T,F] = 0b0110 = 6(確切整數)。
    assert simhash.dhash(_D_A(), hash_size=2) == 6


def test_ac9_dhash_flat_is_zero():
    # AC9:全均勻 → 每個 left>right 皆 False(均勻邊界)→ 0。
    assert simhash.dhash(_D_FLAT(), hash_size=2) == 0


def test_ac10_dhash_left_gt_right_exact():
    # AC10:left>right 準則釘死 —— (8,9) g 每列 [0,255,0,255,...],hash_size=8(目標尺寸,
    # resize 為 identity)。每列相鄰對 (0>255=F,255>0=T,...) 交替 → 每列 bits
    # [F,T,F,T,F,T,F,T] = 0b01010101;8 列 row-major flatten + MSB-first 串接 →
    # 0x5555555555555555 == 6148914691236517205(確切 64-bit;int("0101010101010101"*4,2) 亦等於此)。
    row = [0, 255, 0, 255, 0, 255, 0, 255, 0]
    g = np.tile(np.array(row, dtype=np.uint8), (8, 1))
    assert g.shape == (8, 9)
    assert simhash.dhash(g, hash_size=8) == 6148914691236517205
    assert simhash.dhash(g, hash_size=8) == 0x5555555555555555
    assert simhash.dhash(g, hash_size=8) == int("0101010101010101" * 4, 2)


def test_ac11_dhash_rgb_matches_grey():
    # AC11:RGB↔灰階一致 —— 三通道相等 (2,3,3) → dhash 與灰階版相等 == 6。
    rgb_d = np.stack([_D_A()] * 3, axis=-1)
    assert rgb_d.shape == (2, 3, 3)
    assert simhash.dhash(rgb_d, 2) == simhash.dhash(_D_A(), 2) == 6


# =====================================================================
# hamming — 確切距離 / 自距 0 / 對稱
# =====================================================================

def test_ac12_hamming_exact():
    # AC12:1011 ^ 0110 = 1101,popcount=3(確切)。
    assert simhash.hamming(0b1011, 0b0110) == 3


def test_ac13_hamming_self_is_zero():
    # AC13:自距 0(任何整數與自己距離 0)。
    assert simhash.hamming(255, 255) == 0
    assert simhash.hamming(0, 0) == 0


def test_ac14_hamming_symmetric_and_exact():
    # AC14:對稱 + 確切值 —— 6=110,5=101,XOR=011,popcount=2。
    assert simhash.hamming(6, 5) == simhash.hamming(5, 6)
    assert simhash.hamming(6, 5) == 2


def test_ac15_hamming_zero_vs_full():
    # AC15:0b00000000 ^ 0b11111111 = 11111111,8 個 1(確切)。
    assert simhash.hamming(0, 255) == 8


# =====================================================================
# identity / metamorphic 不變性(同陣列 / 2× 上採樣)
# =====================================================================

def test_ac16_same_array_hash_identical():
    # AC16:同陣列 hash 一致 → hamming 自距 0(ahash 與 dhash 各驗)。
    assert simhash.hamming(
        simhash.ahash(_G_CHECKER(), 2), simhash.ahash(_G_CHECKER(), 2)) == 0
    assert simhash.hamming(
        simhash.dhash(_D_A(), 2), simhash.dhash(_D_A(), 2)) == 0


def test_ac17_upsample_2x_invariance_metamorphic():
    # AC17:2× 上採樣不變性(metamorphic)—— 把 2x2 最近鄰放大成 4x4,
    # NEAREST 縮回 identity → ahash(X2,2) == ahash(G_CHECKER,2) == 6(距離 0)。
    g = _G_CHECKER()
    x2 = np.repeat(np.repeat(g, 2, axis=0), 2, axis=1)
    assert x2.shape == (4, 4)
    assert simhash.ahash(x2, hash_size=2) == simhash.ahash(g, hash_size=2) == 6


# =====================================================================
# find_similar — 篩選 / 排序(距離升序、name 升序)/ 邊界 / 空候選
# =====================================================================

def _cands():
    # query = G_CHECKER(ahash=6,0b0110)。
    #   "lr"   = G_LR    → ahash 5(0b0101) → hamming(6,5)= XOR 0b0011 → 2
    #   "flat" = G_FLAT  → ahash 0(0b0000) → hamming(6,0)= popcount(0b0110) → 2
    #   "same" = G_CHECKER → ahash 6 → hamming(6,6) → 0
    return [("lr", _G_LR()), ("flat", _G_FLAT()), ("same", _G_CHECKER())]


def test_ac18_find_similar_full_sorted():
    # AC18:max_distance=10 全收 —— 距離升序 0 在前;平手(flat、lr 皆 2)再以 name 升序
    # "flat" < "lr" → [("same",0),("flat",2),("lr",2)](確切 list 含順序)。
    assert simhash.find_similar(
        _G_CHECKER(), _cands(), max_distance=10, hasher="ahash",
        hash_size=2) == [
        ("same", 0), ("flat", 2), ("lr", 2)]


def test_ac19_find_similar_max_distance_0():
    # AC19:max_distance=0 只回完全相同(hamming 0)→ [("same",0)];距離 >0 全剔。
    assert simhash.find_similar(
        _G_CHECKER(), _cands(), max_distance=0, hasher="ahash",
        hash_size=2) == [("same", 0)]


def test_ac20_find_similar_max_distance_1_boundary():
    # AC20:max_distance=1 邊界 —— 距離 2 的 flat/lr 因 2<=1 為 False 被剔,只剩 0。
    assert simhash.find_similar(
        _G_CHECKER(), _cands(), max_distance=1, hasher="ahash",
        hash_size=2) == [("same", 0)]


def test_ac21_find_similar_empty_candidates():
    # AC21:空候選 → 回空 list。
    assert simhash.find_similar(
        _G_CHECKER(), [], max_distance=10, hash_size=2) == []


def test_ac22_find_similar_name_tiebreak_ascending():
    # AC22:純距離平手 → name 字典序 "apple" < "zebra"。
    cands2 = [("zebra", _G_FLAT()), ("apple", _G_LR())]
    assert simhash.find_similar(
        _G_CHECKER(), cands2, max_distance=5, hasher="ahash",
        hash_size=2) == [
        ("apple", 2), ("zebra", 2)]


def test_ac23_find_similar_dhash_branch():
    # AC23:hasher="dhash" 路徑 —— query=D_A(dhash=6);D_FLAT dhash=0 → hamming(6,0)=2。
    cands3 = [("d_same", _D_A()), ("d_flat", _D_FLAT())]
    assert simhash.find_similar(
        _D_A(), cands3, max_distance=10, hasher="dhash",
        hash_size=2) == [
        ("d_same", 0), ("d_flat", 2)]


# =====================================================================
# 錯誤路徑(釘死拋 ValueError)—— 5 條,各自獨立
# =====================================================================

def test_ac24_ahash_rgba_shape_raises():
    # AC24:不支援形狀 —— RGBA 4 通道 (4,4,4) 拒。
    with pytest.raises(ValueError):
        simhash.ahash(np.zeros((4, 4, 4), np.uint8))


def test_ac25_ahash_ndim1_raises():
    # AC25:ndim==1 拒。
    with pytest.raises(ValueError):
        simhash.ahash(np.zeros((16,), np.uint8))


def test_ac26_ahash_hash_size_lt1_raises():
    # AC26:hash_size < 1(此處 0)拒。
    with pytest.raises(ValueError):
        simhash.ahash(_G_CHECKER(), hash_size=0)


def test_ac27_find_similar_bad_hasher_raises():
    # AC27:hasher 非法值("phash")拒。
    with pytest.raises(ValueError):
        simhash.find_similar(_G_CHECKER(), [], hasher="phash")


def test_ac28_find_similar_negative_max_distance_raises():
    # AC28:max_distance < 0 拒(max_distance 檢查先於雜湊,hash_size 不影響)。
    with pytest.raises(ValueError):
        simhash.find_similar(
            _G_CHECKER(), _cands(), max_distance=-1, hash_size=2)


# =====================================================================
# 不 mutate 輸入
# =====================================================================

def test_ac29_no_mutate_inputs():
    # AC29:呼叫 ahash/dhash/find_similar 後,傳入的 array 內容不變;
    # 且 cands list 本身內容/順序不被改動(回新 list,不就地排序傳入 list)。
    g = _G_CHECKER()
    simhash.ahash(g, 2)
    assert np.array_equal(g, np.array([[10, 90], [90, 10]], np.uint8))

    d = _D_A()
    simhash.dhash(d, 2)
    assert np.array_equal(d, np.array([[10, 90, 10], [90, 10, 90]], np.uint8))

    cands = _cands()
    query = _G_CHECKER()
    simhash.find_similar(query, cands, max_distance=10, hasher="ahash")
    assert np.array_equal(query, np.array([[10, 90], [90, 10]], np.uint8))
    # 傳入 list 順序/元素 name 未被就地排序更動(原序仍是 lr, flat, same)
    assert [name for name, _ in cands] == ["lr", "flat", "same"]
    assert np.array_equal(cands[0][1], np.array([[10, 90], [10, 90]], np.uint8))


# =====================================================================
# 推導 / property 測試(設計未明列;由 §2/§3/§4 契約推導)
# =====================================================================

def test_property_ahash_flat_zero_any_value_and_size():
    # 推導(§2.5 + §4c 均勻邊界):任意均勻值、任意 hash_size,ahash 恆為 0(嚴格 `>`,
    # 全等 → mean==v → v>v 皆 False)。比 AC3/AC6 單點更強。
    for v in (0, 1, 50, 123, 200, 255):
        for hs in (1, 2, 3, 8):
            assert simhash.ahash(np.full((hs, hs), v, np.uint8), hash_size=hs) == 0


def test_property_dhash_flat_zero_any_value_and_size():
    # 推導(§2.5 + §4c 均勻邊界):任意均勻值、任意 hash_size,dhash 恆為 0
    # (每個 left>right 皆 False)。比 AC9 單點更強。
    for v in (0, 1, 50, 123, 200, 255):
        for hs in (1, 2, 3, 8):
            assert simhash.dhash(
                np.full((hs, hs + 1), v, np.uint8), hash_size=hs) == 0


def test_property_hamming_symmetric_and_self_zero_arbitrary():
    # 推導(§2.6):對任意整數對,hamming 對稱且自距 0,涵蓋多組值(比 AC13/AC14 單點更強)。
    pairs = [(0, 0), (255, 0), (6, 5), (1085102592571150095, 0),
             (123456789, 987654321), (1, 2)]
    for a, b in pairs:
        assert simhash.hamming(a, b) == simhash.hamming(b, a)
        assert simhash.hamming(a, a) == 0
        assert simhash.hamming(b, b) == 0


def test_property_ahash_pure_function_repeatable():
    # 推導(§4j 純函式):同輸入同參數恆回同整數(無隨機/時間/I/O)。
    g = _G_CHECKER()
    vals = {simhash.ahash(g, 2) for _ in range(5)}
    assert vals == {6}
    d = _D_A()
    dvals = {simhash.dhash(d, 2) for _ in range(5)}
    assert dvals == {6}


def test_property_ahash_rgb_grey_consistency_arbitrary_pure_color():
    # 推導(§2.2):任意「三通道相等」純色 RGB,灰階後恰為該值 → ahash(RGB)==ahash(灰階)。
    # 比 AC5 單一棋盤更強:對多種純色棋盤驗證一致。
    rng = np.random.default_rng(0)
    for _ in range(4):
        a, b = int(rng.integers(0, 128)), int(rng.integers(128, 256))
        grey = np.array([[a, b], [b, a]], dtype=np.uint8)
        rgb = np.stack([grey] * 3, axis=-1)
        assert simhash.ahash(rgb, 2) == simhash.ahash(grey, 2)


def test_property_find_similar_distance_monotone_sorted():
    # 推導(§2.7 排序):回傳結果的 distance 必為非遞減(全序排序鍵 (d, name) 的必要條件)。
    res = simhash.find_similar(
        _G_CHECKER(), _cands(), max_distance=10, hasher="ahash")
    dists = [d for _, d in res]
    assert dists == sorted(dists)
    # 同距離區段內 name 必為升序
    assert res == sorted(res, key=lambda t: (t[1], t[0]))


def test_property_find_similar_filter_excludes_above_threshold():
    # 推導(§2.7 篩選):回傳每個 distance 必 <= max_distance(無漏放超界者)。
    for md in (0, 1, 2, 5, 10):
        res = simhash.find_similar(
            _G_CHECKER(), _cands(), max_distance=md, hasher="ahash")
        for _, d in res:
            assert d <= md
