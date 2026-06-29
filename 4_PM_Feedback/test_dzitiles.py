"""dzitiles 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/18_dzitiles.md(AC1..AC44 + §3/§3.1/§3.2/§3.3/§5 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import dzitiles`。此時實作尚未生成,import/collection 不到屬正常(test-first);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

Tier B 模組:把 HxWx3 uint8 RGB 大圖切成 Deep Zoom(DZI)金字塔瓦片 + .dzi 描述。
核心純函式(num_levels / level_dimensions / dzi_descriptor / tile / build_tiles /
to_png_bytes / to_data_url)零檔案 I/O,以 numpy 像素級 + PIL round-trip 釘死(AC1–AC43)。
唯一碰檔案的 write_dzi(AC44)標 @pytest.mark.e2e,gate 只跑單元,write 佈局交人/ux-test 觸發。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_dzitiles.py -p no:cacheprovider --strict-markers -q
"""
import base64
import io
import pathlib

import numpy as np
import pytest
from PIL import Image

import dzitiles


# =====================================================================
# 共用合成陣列(設計 §6 原樣建立,逐字採用)
# =====================================================================

# 4x4 灰階遞增,擴成 RGB(三通道相等):值 = row*4 + col
_g = np.arange(16, dtype=np.uint8).reshape(4, 4)
ARR4 = np.stack([_g, _g, _g], axis=-1)        # shape (4,4,3) uint8


def _BLK():
    # 4x4 區塊純色圖(供 BOX 降採樣手算):每個 2x2 區塊同色
    # TL=10、TR=20、BL=30、BR=40。回新陣列以免測試間互相污染。
    blk = np.zeros((4, 4, 3), np.uint8)
    blk[0:2, 0:2] = (10, 10, 10)
    blk[0:2, 2:4] = (20, 20, 20)
    blk[2:4, 0:2] = (30, 30, 30)
    blk[2:4, 2:4] = (40, 40, 40)
    return blk


BLK = _BLK()


# =====================================================================
# A. num_levels — 層數公式(釘死)
# =====================================================================

def test_ac1_num_levels_4x4():
    # AC1:num_levels(4,4) == 3(ceil(log2 4)+1 = 2+1)
    assert dzitiles.num_levels(4, 4) == 3


def test_ac2_num_levels_1x1():
    # AC2:num_levels(1,1) == 1(1x1 特例,log2(1)=0)
    assert dzitiles.num_levels(1, 1) == 1


def test_ac3_num_levels_5x3():
    # AC3:num_levels(5,3) == 4(ceil(log2 5)+1 = 3+1;非 2 次方、用 max 邊)
    assert dzitiles.num_levels(5, 3) == 4


def test_ac4_num_levels_256x100():
    # AC4:num_levels(256,100) == 9(ceil(log2 256)+1 = 8+1)
    assert dzitiles.num_levels(256, 100) == 9


def test_ac5_num_levels_257x1():
    # AC5:num_levels(257,1) == 10(ceil(log2 257)+1 = 9+1,剛過 2 次方)
    assert dzitiles.num_levels(257, 1) == 10


# =====================================================================
# B. level_dimensions — 各層尺寸(釘死)
# =====================================================================

def test_ac6_level_dimensions_4x4_level0():
    # AC6:level_dimensions(4,4,0) == (1,1)
    assert dzitiles.level_dimensions(4, 4, 0) == (1, 1)


def test_ac7_level_dimensions_4x4_level1():
    # AC7:level_dimensions(4,4,1) == (2,2)
    assert dzitiles.level_dimensions(4, 4, 1) == (2, 2)


def test_ac8_level_dimensions_4x4_level2():
    # AC8:level_dimensions(4,4,2) == (4,4)(最高層 == 原尺寸)
    assert dzitiles.level_dimensions(4, 4, 2) == (4, 4)


def test_ac9_level_dimensions_5x3_level1():
    # AC9:level_dimensions(5,3,1) == (2,1)(ceil(5/4),ceil(3/4))
    assert dzitiles.level_dimensions(5, 3, 1) == (2, 1)


def test_ac10_level_dimensions_5x3_level2():
    # AC10:level_dimensions(5,3,2) == (3,2)(ceil(5/2),ceil(3/2))
    assert dzitiles.level_dimensions(5, 3, 2) == (3, 2)


def test_ac11_level_dimensions_5x3_level3():
    # AC11:level_dimensions(5,3,3) == (5,3)(最高層原尺寸)
    assert dzitiles.level_dimensions(5, 3, 3) == (5, 3)


def test_ac12_level_dimensions_out_of_range_raises():
    # AC12:level 超界(>max_level 與 <0)各觸發 ValueError(邊界各自獨立)
    with pytest.raises(ValueError):
        dzitiles.level_dimensions(4, 4, 3)
    with pytest.raises(ValueError):
        dzitiles.level_dimensions(4, 4, -1)


# =====================================================================
# C. dzi_descriptor — XML 字串(逐字釘死)
# =====================================================================

def test_ac13_dzi_descriptor_defaults_verbatim():
    # AC13:預設 tile_size=254、overlap=1、fmt="png" 的 .dzi XML 逐字等於設計字串
    # (含 xmlns、屬性順序 Format→Overlap→TileSize、Size 為 Height→Width;整串 == 比對)
    expected = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        'Format="png" Overlap="1" TileSize="254">'
        '<Size Height="4" Width="4"/></Image>'
    )
    assert dzitiles.dzi_descriptor(4, 4) == expected


def test_ac14_dzi_descriptor_custom_verbatim():
    # AC14:tile_size=2、overlap=0、fmt="png"、5x3 的 .dzi XML 逐字等於設計字串
    expected = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        'Format="png" Overlap="0" TileSize="2">'
        '<Size Height="3" Width="5"/></Image>'
    )
    assert dzitiles.dzi_descriptor(5, 3, tile_size=2, overlap=0, fmt="png") == expected


def test_ac15_dzi_descriptor_single_line():
    # AC15:結果無換行/tab(單行字串)
    out = dzitiles.dzi_descriptor(4, 4)
    assert "\n" not in out
    assert "\t" not in out


# =====================================================================
# D. tile — 最高層(scale=1,精確切片)overlap=0(釘死像素)
# =====================================================================

def test_ac16_tile_top_left_overlap0():
    # AC16:tile(ARR4,2,0,0,ts=2,ov=0) → 左上 2x2 精確切片;dtype/shape/像素釘死
    t = dzitiles.tile(ARR4, 2, 0, 0, tile_size=2, overlap=0)
    assert t.dtype == np.uint8
    assert t.shape == (2, 2, 3)
    assert np.array_equal(t[..., 0], np.array([[0, 1], [4, 5]], np.uint8))


def test_ac17_tile_top_right_overlap0():
    # AC17:tile 1_0(col=1)= 右上 2x2 = [[2,3],[6,7]]
    out = dzitiles.tile(ARR4, 2, 1, 0, tile_size=2, overlap=0)[..., 0]
    assert np.array_equal(out, np.array([[2, 3], [6, 7]], np.uint8))


def test_ac18_tile_bottom_left_overlap0():
    # AC18:tile 0_1(row=1)= 左下 2x2 = [[8,9],[12,13]]
    out = dzitiles.tile(ARR4, 2, 0, 1, tile_size=2, overlap=0)[..., 0]
    assert np.array_equal(out, np.array([[8, 9], [12, 13]], np.uint8))


def test_ac19_tile_bottom_right_overlap0():
    # AC19:tile 1_1 = 右下 2x2 = [[10,11],[14,15]]
    out = dzitiles.tile(ARR4, 2, 1, 1, tile_size=2, overlap=0)[..., 0]
    assert np.array_equal(out, np.array([[10, 11], [14, 15]], np.uint8))


# =====================================================================
# E. tile — 最高層 overlap=1(釘死 overlap 像素,內擴/碰邊不擴)
# =====================================================================

def test_ac20_tile_overlap1_corner_top_left():
    # AC20:tile 0_0,ov=1 → 左/上碰邊不擴、右/下各 +1 → 3x3 = ARR4[0:3,0:3]
    t = dzitiles.tile(ARR4, 2, 0, 0, tile_size=2, overlap=1)
    assert t.shape == (3, 3, 3)
    assert np.array_equal(
        t[..., 0], np.array([[0, 1, 2], [4, 5, 6], [8, 9, 10]], np.uint8))


def test_ac21_tile_overlap1_top_right():
    # AC21:tile 1_0,ov=1 → 左內擴 +1、右碰邊不擴 → 3x3 = ARR4[0:3,1:4]
    out = dzitiles.tile(ARR4, 2, 1, 0, tile_size=2, overlap=1)[..., 0]
    assert np.array_equal(
        out, np.array([[1, 2, 3], [5, 6, 7], [9, 10, 11]], np.uint8))


def test_ac22_tile_overlap1_bottom_right():
    # AC22:tile 1_1,ov=1 → 左+上內擴、右+下碰邊 → 3x3 = ARR4[1:4,1:4]
    out = dzitiles.tile(ARR4, 2, 1, 1, tile_size=2, overlap=1)[..., 0]
    assert np.array_equal(
        out, np.array([[5, 6, 7], [9, 10, 11], [13, 14, 15]], np.uint8))


# =====================================================================
# F. tile — BOX 降採樣層(level<max,純色區塊可手算)
# =====================================================================

def test_ac23_tile_box_downsample_level1():
    # AC23:BLK level1 (2,2) BOX 降採樣後每像素 = 對應 2x2 純色區塊精確平均(同色→該色)
    #   鎖死縮放濾鏡 = PIL.Image.BOX(BILINEAR/LANCZOS 數值會變)
    t = dzitiles.tile(BLK, 1, 0, 0, tile_size=2, overlap=0)
    assert t.shape == (2, 2, 3)
    assert np.array_equal(
        t,
        np.array([[[10, 10, 10], [20, 20, 20]],
                  [[30, 30, 30], [40, 40, 40]]], np.uint8))


def test_ac24_tile_level0_is_1x1():
    # AC24:BLK level0 = 1x1 單片
    assert dzitiles.tile(BLK, 0, 0, 0, tile_size=2, overlap=0).shape == (1, 1, 3)


# =====================================================================
# G. tile — 超界與 tile_size 大於圖
# =====================================================================

def test_ac25_tile_col_out_of_range_raises():
    # AC25:level2 cols=2,col=2 超界 → ValueError(不靜默回空陣列)
    with pytest.raises(ValueError):
        dzitiles.tile(ARR4, 2, 2, 0, tile_size=2, overlap=0)


def test_ac26_tile_level_out_of_range_raises():
    # AC26:level3 超界(max_level=2)→ ValueError
    with pytest.raises(ValueError):
        dzitiles.tile(ARR4, 3, 0, 0, tile_size=2, overlap=0)


def test_ac27_tile_size_larger_than_image():
    # AC27:tile_size 遠大於圖 → 單片 = 整層;overlap 被邊界全夾住不外擴 → 4x4
    t = dzitiles.tile(ARR4, 2, 0, 0, tile_size=254, overlap=1)
    assert t.shape == (4, 4, 3)
    assert np.array_equal(t[..., 0], _g)


# =====================================================================
# H. build_tiles — 完整金字塔結構(釘死格數與內容)
# =====================================================================

def test_ac28_build_tiles_metadata():
    # AC28:build_tiles(ARR4,ts=2,ov=0) 的 metadata 欄位釘死
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    assert R["width"] == 4
    assert R["height"] == 4
    assert R["tile_size"] == 2
    assert R["overlap"] == 0
    assert R["max_level"] == 2
    assert R["num_levels"] == 3


def test_ac29_build_tiles_dzi_consistent():
    # AC29:R["dzi"] == dzi_descriptor(4,4,ts=2,ov=0,fmt="png")(descriptor 一致)
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    assert R["dzi"] == dzitiles.dzi_descriptor(4, 4, tile_size=2, overlap=0, fmt="png")


def test_ac30_build_tiles_level_keys_are_ints():
    # AC30:tiles 層 key 為 int,0..max_level 齊備
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    assert set(R["tiles"].keys()) == {0, 1, 2}


def test_ac31_build_tiles_tile_counts_per_level():
    # AC31:各層格數釘死 — level0=1、level1=1、level2=4 片
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    assert len(R["tiles"][0]) == 1
    assert len(R["tiles"][1]) == 1
    assert len(R["tiles"][2]) == 4


def test_ac32_build_tiles_level2_key_format():
    # AC32:level2 key 格式 "{col}_{row}"(col 在前、row 在後)
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    assert set(R["tiles"][2].keys()) == {"0_0", "1_0", "0_1", "1_1"}


def test_ac33_build_tiles_value_is_png_bytes():
    # AC33:level2 瓦片值是真實 PNG bytes(magic 開頭、型別 bytes)
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    assert isinstance(R["tiles"][2]["0_0"], bytes)
    assert R["tiles"][2]["0_0"][:8] == b"\x89PNG\r\n\x1a\n"


def test_ac34_build_tiles_png_roundtrip_pixels():
    # AC34:PNG 經 PIL(瀏覽器級解碼)解回,尺寸與像素零失真(Tier B 真實 round-trip)
    R = dzitiles.build_tiles(ARR4, tile_size=2, overlap=0, fmt="png")
    png = R["tiles"][2]["0_0"]
    back = np.asarray(Image.open(io.BytesIO(png)))
    assert back.shape == (2, 2, 3)
    assert np.array_equal(back[..., 0], np.array([[0, 1], [4, 5]], np.uint8))


# =====================================================================
# I. build_tiles — 非 2 次方 / tile_size 大於圖
# =====================================================================

def test_ac35_build_tiles_non_power_of_two_levels():
    # AC35:3x5 圖 → num_levels==4、層 key {0,1,2,3}
    R5 = dzitiles.build_tiles(np.zeros((3, 5, 3), np.uint8), tile_size=2, overlap=0)
    assert R5["num_levels"] == 4
    assert set(R5["tiles"].keys()) == {0, 1, 2, 3}


def test_ac36_build_tiles_non_power_of_two_top_level_grid():
    # AC36:承 AC35,level3 尺寸 (5,3) → cols=3、rows=2 → 6 片,key 集合釘死
    R5 = dzitiles.build_tiles(np.zeros((3, 5, 3), np.uint8), tile_size=2, overlap=0)
    assert len(R5["tiles"][3]) == 6
    assert set(R5["tiles"][3].keys()) == {
        "0_0", "1_0", "2_0", "0_1", "1_1", "2_1"}


def test_ac37_build_tiles_1x1_degenerate():
    # AC37:1x1 退化 → 單層單片,key == ["0_0"]
    R1 = dzitiles.build_tiles(np.zeros((1, 1, 3), np.uint8))
    assert R1["num_levels"] == 1
    assert set(R1["tiles"].keys()) == {0}
    assert len(R1["tiles"][0]) == 1
    assert list(R1["tiles"][0].keys()) == ["0_0"]


def test_ac38_build_tiles_tile_size_larger_than_all_levels():
    # AC38:tile_size 遠大於各層 → 每層格數皆 1,level2 key == {"0_0"}
    Rbig = dzitiles.build_tiles(ARR4, tile_size=254, overlap=1)
    assert len(Rbig["tiles"][2]) == 1
    assert set(Rbig["tiles"][2].keys()) == {"0_0"}


# =====================================================================
# J. to_png_bytes / to_data_url(真實可解碼)
# =====================================================================

def test_ac39_to_png_bytes_magic():
    # AC39:to_png_bytes 回 bytes,以 PNG magic 開頭
    b = dzitiles.to_png_bytes(np.zeros((2, 2, 3), np.uint8))
    assert isinstance(b, bytes)
    assert b[:8] == b"\x89PNG\r\n\x1a\n"


def test_ac40_to_png_bytes_non_uint8_raises():
    # AC40:非 uint8 → ValueError(守門,避免靜默產壞 PNG)
    with pytest.raises(ValueError):
        dzitiles.to_png_bytes(np.zeros((2, 2, 3), np.uint16))


def test_ac41_to_data_url_decodable():
    # AC41:to_data_url 以 "data:image/png;base64," 開頭,base64 解回 → PIL 解碼 → 尺寸一致
    u = dzitiles.to_data_url(np.zeros((2, 2, 3), np.uint8))
    assert u.startswith("data:image/png;base64,")
    payload = base64.b64decode(u.split(",", 1)[1])
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert np.asarray(Image.open(io.BytesIO(payload))).shape == (2, 2, 3)


# =====================================================================
# K. 非法參數(邊界各自獨立)
# =====================================================================

def test_ac42_width_le_zero_raises():
    # AC42:width<=0 → ValueError(dzi_descriptor 與 num_levels 各驗)
    with pytest.raises(ValueError):
        dzitiles.dzi_descriptor(0, 4)
    with pytest.raises(ValueError):
        dzitiles.num_levels(0, 4)


def test_ac43_tile_illegal_params_raise():
    # AC43:tile_size<=0 與 overlap<0 各觸發 ValueError(各自獨立)
    with pytest.raises(ValueError):
        dzitiles.tile(ARR4, 2, 0, 0, tile_size=0)
    with pytest.raises(ValueError):
        dzitiles.tile(ARR4, 2, 0, 0, overlap=-1)


# =====================================================================
# L. write_dzi — 薄 write 包裝(磁碟佈局,真實檔案系統 → @pytest.mark.e2e)
# =====================================================================

@pytest.mark.e2e
def test_ac44_write_dzi_disk_layout(tmp_path):
    # AC44(@e2e):write_dzi 落 OSD 標準 DZI 佈局到真實磁碟
    #   - <name>.dzi 存在且內容 == dzi_descriptor;回傳路徑 .name == "img.dzi"
    #   - <name>_files/<level>/<col>_<row>.png 存在,PNG magic 開頭
    #   - level2 含 4 個 .png,level0/level1 各 1 個(<name>_files/<level>/<col>_<row>.<fmt>)
    p = dzitiles.write_dzi(tmp_path, ARR4, name="img", tile_size=2, overlap=0)

    # .dzi 檔名與內容
    assert pathlib.Path(p).name == "img.dzi"
    dzi_path = pathlib.Path(p)
    assert dzi_path.exists()
    assert dzi_path.read_text(encoding="utf-8") == dzitiles.dzi_descriptor(
        4, 4, tile_size=2, overlap=0)

    # 一片瓦片存在且為真實 PNG
    tile_png = tmp_path / "img_files" / "2" / "0_0.png"
    assert tile_png.exists()
    assert tile_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    # 各層 .png 數量(OSD 標準佈局)
    lvl2 = sorted(q.name for q in (tmp_path / "img_files" / "2").glob("*.png"))
    assert lvl2 == ["0_0.png", "0_1.png", "1_0.png", "1_1.png"]
    assert len(list((tmp_path / "img_files" / "0").glob("*.png"))) == 1
    assert len(list((tmp_path / "img_files" / "1").glob("*.png"))) == 1


# =====================================================================
# 推導 / property 測試(設計未明列;由 §3.2/§5 契約推導,metamorphic 施壓)
# =====================================================================

def test_property_num_levels_top_level_is_original_size():
    # 推導(§3 契約:最高層 level==num_levels-1 永遠是原尺寸):
    #   對多組尺寸驗 level_dimensions(W,H,max_level)==(W,H)、level0==(1,1)。
    for w, h in [(4, 4), (5, 3), (1, 1), (256, 100), (257, 1), (7, 11)]:
        ml = dzitiles.num_levels(w, h) - 1
        assert dzitiles.level_dimensions(w, h, ml) == (w, h)
        assert dzitiles.level_dimensions(w, h, 0) == (1, 1)


def test_property_build_tiles_does_not_mutate_input():
    # 推導(§8 對外承諾「不 mutate 輸入 array」):build_tiles 後 ARR4 內容不變。
    before = ARR4.copy()
    dzitiles.build_tiles(ARR4, tile_size=2, overlap=0)
    assert np.array_equal(ARR4, before)


def test_property_tile_does_not_mutate_input():
    # 推導(§5「不 mutate 輸入 array」+ PIL 從 array 複製):tile 後 BLK 內容不變。
    before = BLK.copy()
    dzitiles.tile(BLK, 1, 0, 0, tile_size=2, overlap=0)
    assert np.array_equal(BLK, before)


def test_property_build_tiles_keys_match_grid_formula():
    # 推導(§3.3「key 集合 = {f"{c}_{r}"} 不多不少」):對每層,實際 key 集合 ==
    #   由 level_dimensions + ceil(levelW/ts)×ceil(levelH/ts) 算出的應有 key 集合。
    import math
    ts = 2
    R = dzitiles.build_tiles(ARR4, tile_size=ts, overlap=0)
    for level in R["tiles"]:
        lw, lh = dzitiles.level_dimensions(4, 4, level)
        cols = math.ceil(lw / ts)
        rows = math.ceil(lh / ts)
        expected = {f"{c}_{r}" for r in range(rows) for c in range(cols)}
        assert set(R["tiles"][level].keys()) == expected


def test_property_top_level_tiles_lossless_roundtrip():
    # 推導(§4「最高層精確切片、像素零失真」+ AC34 強化):build_tiles 後拼回
    #   level2 全部瓦片(overlap=0,不重疊),經 PNG round-trip 應精確還原 ARR4。
    ts = 2
    R = dzitiles.build_tiles(ARR4, tile_size=ts, overlap=0)
    recon = np.zeros((4, 4, 3), np.uint8)
    for key, png in R["tiles"][2].items():
        col, row = (int(s) for s in key.split("_"))
        patch = np.asarray(Image.open(io.BytesIO(png)))
        recon[row * ts:row * ts + patch.shape[0],
              col * ts:col * ts + patch.shape[1]] = patch
    assert np.array_equal(recon, ARR4)


def test_property_no_banned_xfail_skip_in_this_file():
    # 反向稽查(PM 鐵則:不得用放水樣式充綠):本測試檔自身,除唯一合法的
    #   @pytest.mark.e2e(AC44 觸真實檔案系統)外,不得出現停用標記/跳過/放寬。
    #   needle 以字串拼接構造,使本稽查器的字面 token 不出現在自身原始碼,避免 self-match。
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    _m = "pytest" + ".mark."
    _c = "pytest" + "."
    banned = [_m + "skip", _m + "xfail", _c + "skip(", _c + "xfail("]
    for needle in banned:
        assert needle not in src, f"禁用放水樣式出現:{needle}"
