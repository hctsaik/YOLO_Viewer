"""dinodiff 驗收測試(純邏輯核心;設計 3_Architect_Design/27_dinodiff.md §6)。

刻意**不觸碰真實 88MB 權重**:單元 gate 要秒回,且模型載入屬 I/O 邊界(設計 §1 表格)。
真實模型鏈路由 test_dinodiff_e2e.py 以 @pytest.mark.e2e 實證。
"""
import os
import subprocess
import sys

import numpy as np
import pytest

import dinodiff

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- helpers:合成特徵(不需要模型) ----------
def _feats(g, d=8, seed=0):
    """(g*g, d) 隨機特徵。"""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((g * g, d)).astype(np.float32)


# ================= AC1 grid_side =================
def test_ac1_grid_side_of_dinov2_vits14_518px():
    assert dinodiff.grid_side(1369) == 37          # 518/14 = 37


def test_ac1_grid_side_rejects_non_square_token_count():
    with pytest.raises(ValueError):
        dinodiff.grid_side(1370)


# ================= AC2 cosine_distance_map =================
def test_ac2_identical_features_give_zero_distance():
    f = _feats(4)
    dmap = dinodiff.cosine_distance_map(f, f)
    assert dmap.shape == (4, 4)
    assert np.allclose(dmap, 0.0, atol=1e-5)


def test_ac2_orthogonal_features_give_distance_one():
    a = np.tile(np.array([1.0, 0.0], dtype=np.float32), (9, 1))
    b = np.tile(np.array([0.0, 1.0], dtype=np.float32), (9, 1))
    dmap = dinodiff.cosine_distance_map(a, b)
    assert dmap.shape == (3, 3)
    assert np.allclose(dmap, 1.0, atol=1e-5)


def test_ac2_opposite_features_give_distance_two():
    a = np.tile(np.array([1.0, 0.0], dtype=np.float32), (9, 1))
    dmap = dinodiff.cosine_distance_map(a, -a)
    assert np.allclose(dmap, 2.0, atol=1e-5)


# ================= AC3 形狀/NaN 防線 =================
@pytest.mark.parametrize("a_shape,b_shape", [
    ((9, 8), (16, 8)),      # N 不等
    ((9, 8), (9, 4)),       # D 不等
])
def test_ac3_mismatched_shapes_raise(a_shape, b_shape):
    with pytest.raises(ValueError):
        dinodiff.cosine_distance_map(np.zeros(a_shape, np.float32),
                                     np.zeros(b_shape, np.float32))


def test_ac3_non_2d_input_raises():
    with pytest.raises(ValueError):
        dinodiff.cosine_distance_map(np.zeros((9,), np.float32), np.zeros((9,), np.float32))


def test_ac3_zero_vectors_do_not_produce_nan():
    z = np.zeros((9, 8), np.float32)
    dmap = dinodiff.cosine_distance_map(z, z)
    assert not np.isnan(dmap).any()


# ================= AC4 normalize_heat =================
def test_ac4_normalize_heat_stretches_into_unit_range():
    dmap = np.linspace(0.0, 1.2, 16, dtype=np.float32).reshape(4, 4)
    heat = dinodiff.normalize_heat(dmap)
    assert heat.shape == (4, 4)
    assert heat.min() >= 0.0 and heat.max() <= 1.0
    assert heat.max() == pytest.approx(1.0)
    # 單調性:原本最大的那格,拉伸後仍是最大的那格
    assert np.unravel_index(np.argmax(heat), heat.shape) == \
           np.unravel_index(np.argmax(dmap), dmap.shape)


# ================= AC5 ★ 反自欺:幾乎相同的兩張圖不得被相對拉伸成通紅 =================
def test_ac5_near_identical_images_stay_cold_instead_of_being_stretched_red():
    # 距離全都遠低於 abs_floor(0.05)—— 相對拉伸會讓最大值變 1.0(假紅),契約要求回全零。
    dmap = np.array([[0.001, 0.002], [0.003, 0.004]], dtype=np.float32)
    heat = dinodiff.normalize_heat(dmap, abs_floor=0.05)
    assert np.count_nonzero(heat) == 0, "幾乎相同的兩張圖被拉伸成有熱區 = 對使用者說謊"


def test_ac5_real_difference_above_floor_still_stretches():
    dmap = np.array([[0.001, 0.002], [0.003, 0.60]], dtype=np.float32)
    heat = dinodiff.normalize_heat(dmap, abs_floor=0.05)
    assert heat.max() == pytest.approx(1.0)


# ================= AC6 upsample =================
def test_ac6_upsample_to_image_size_keeps_unit_range():
    heat = np.array([[0.0, 1.0], [0.5, 0.25]], dtype=np.float32)
    up = dinodiff.upsample(heat, 40, 30)
    assert up.shape == (30, 40)
    assert up.min() >= 0.0 and up.max() <= 1.0


# ================= AC7 colorize_overlay =================
def test_ac7_alpha_zero_returns_the_original_image_pixel_for_pixel():
    rgb = (np.arange(12 * 10 * 3, dtype=np.uint8) % 251).reshape(12, 10, 3)
    heat = np.ones((12, 10), dtype=np.float32)
    out = dinodiff.colorize_overlay(rgb, heat, alpha=0.0)
    assert out.shape == (12, 10, 3) and out.dtype == np.uint8
    assert np.array_equal(out, rgb)


def test_ac7_cold_region_is_left_untouched():
    rgb = np.full((8, 8, 3), 120, dtype=np.uint8)
    heat = np.zeros((8, 8), dtype=np.float32)
    heat[0:2, 0:2] = 1.0                       # 只有左上角是熱區
    out = dinodiff.colorize_overlay(rgb, heat, alpha=0.6)
    assert np.array_equal(out[4:, 4:], rgb[4:, 4:]), "冷區被蒙色 → 看不清原圖"
    assert not np.array_equal(out[0:2, 0:2], rgb[0:2, 0:2]), "熱區沒有上色"


# ================= AC8 / AC9 top_regions =================
def test_ac8_single_hot_blob_yields_one_box_that_contains_it():
    heat = np.zeros((10, 10), dtype=np.float32)
    heat[6:9, 2:5] = 0.9                       # grid row 6..8, col 2..4
    regions = dinodiff.top_regions(heat, w=100, h=100, k=3, thr=0.5, min_cells=2)
    assert len(regions) == 1
    x, y, bw, bh = regions[0]["bbox"]
    # grid(10x10) → image(100x100):每格 10px。熱區 = x 20..50, y 60..90
    assert x <= 20 and y <= 60 and x + bw >= 50 and y + bh >= 90


def test_ac8_k_limits_the_number_of_returned_regions():
    heat = np.zeros((12, 12), dtype=np.float32)
    for i, c in enumerate((0, 4, 8)):          # 三塊互不相連的熱區
        heat[c:c + 2, c:c + 2] = 0.6 + 0.1 * i
    regions = dinodiff.top_regions(heat, w=120, h=120, k=2, thr=0.5, min_cells=2)
    assert len(regions) == 2
    assert regions[0]["score"] >= regions[1]["score"], "未依分數由大到小排序"


def test_ac8_all_zero_heat_yields_no_boxes():
    assert dinodiff.top_regions(np.zeros((10, 10), np.float32), w=50, h=50) == []


def test_ac8_noise_smaller_than_min_cells_is_dropped():
    heat = np.zeros((10, 10), dtype=np.float32)
    heat[3, 3] = 0.99                          # 只有 1 格 → 雜訊
    assert dinodiff.top_regions(heat, w=100, h=100, thr=0.5, min_cells=2) == []


def test_ac9_boxes_are_integer_image_coords_inside_bounds():
    heat = np.zeros((10, 10), dtype=np.float32)
    heat[8:10, 8:10] = 0.8                     # 貼著右下角
    regions = dinodiff.top_regions(heat, w=64, h=48, k=3, thr=0.5, min_cells=2)
    assert len(regions) == 1
    x, y, bw, bh = regions[0]["bbox"]
    assert all(isinstance(v, int) for v in (x, y, bw, bh))
    assert bw >= 1 and bh >= 1
    assert 0 <= x and 0 <= y and x + bw <= 64 and y + bh <= 48, "框超出影像邊界"


# ================= AC10 diff_score =================
def test_ac10_identical_features_score_zero():
    f = _feats(6)
    assert dinodiff.diff_score(dinodiff.cosine_distance_map(f, f)) == pytest.approx(0.0, abs=1e-3)


def test_ac10_score_is_monotone_in_difference_and_bounded():
    small = np.full((4, 4), 0.05, dtype=np.float32)
    big = np.full((4, 4), 0.60, dtype=np.float32)
    s_small, s_big = dinodiff.diff_score(small), dinodiff.diff_score(big)
    assert 0.0 <= s_small < s_big <= 100.0


# ================= AC11 resolve_model_path =================
def test_ac11_explicit_path_wins(tmp_path):
    p = tmp_path / "dinov2_vits14.pth"
    p.write_bytes(b"x")
    env_p = tmp_path / "other.pth"
    env_p.write_bytes(b"x")
    got = dinodiff.resolve_model_path(str(p), {"CVR_DINO_MODEL": str(env_p)}, [])
    assert got is not None and os.path.samefile(str(got), str(p))


def test_ac11_missing_explicit_falls_through_to_env(tmp_path):
    env_p = tmp_path / "dinov2_vits14.pth"
    env_p.write_bytes(b"x")
    got = dinodiff.resolve_model_path(str(tmp_path / "nope.pth"),
                                      {"CVR_DINO_MODEL": str(env_p)}, [])
    assert got is not None and os.path.samefile(str(got), str(env_p))


def test_ac11_falls_back_to_scanning_search_dirs(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    (d / "yolov8n.pt").write_bytes(b"x")          # 非 DINO,不該被選中
    (d / "dinov2_vits14.pth").write_bytes(b"x")
    got = dinodiff.resolve_model_path(None, {}, [d])
    assert got is not None and got.name == "dinov2_vits14.pth"


def test_ac11_returns_none_when_nothing_found(tmp_path):
    assert dinodiff.resolve_model_path(None, {}, [tmp_path]) is None


# ================= AC12 ★ 純邏輯核心不得把 torch 拖進來 =================
def test_ac12_importing_dinodiff_does_not_import_torch():
    code = ("import sys; sys.path.insert(0, r'%s'); import dinodiff; "
            "print('torch' in sys.modules)" % os.path.join(ROOT, "5_PG_Develop"))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=ROOT, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", "import dinodiff 把 torch 拉進來了(單元測試會慢 2 秒/次)"
