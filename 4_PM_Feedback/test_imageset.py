"""驗收測試:imageset(Tier B,M1b)

/pm 產物(回饋契約)。把 3_Architect_Design/03_imageset.md 的每條 AC + 邊界
轉成可執行 pytest。**只驗收,不含實作。**

規則對齊:
- 每條 AC 至少一個測試;邊界各自獨立測試;每個測試以 # ACn 標註。
- 真實讀寫:用 tmp_path 建假影像檔(寫任意 bytes,scan 不解碼內容)與狀態檔。
- 路徑斷言用 os.path.normcase 容忍 Windows 分隔字元差異。
- import 方式:`import imageset`(conftest 已把 5_PG_Develop 加進 sys.path)。
  實作尚未生成 → import 失敗屬正常(非「紅」)。

此外依規則加入「設計沒明列」的推導/property 測試(見檔尾 PROP-* 區段)。
"""
import json
import os

import pytest

import imageset


# ---------------------------------------------------------------------------
# 測試小工具
# ---------------------------------------------------------------------------
def _mkfile(folder, name, data=b"x", mtime=None):
    """在 folder 下建立檔案,寫入 data;可選設定 mtime(同時設 atime)。"""
    p = os.path.join(str(folder), name)
    with open(p, "wb") as f:
        f.write(data)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def _names(records):
    return [r["name"] for r in records]


def _indices(records):
    return [r["index"] for r in records]


# ===========================================================================
# scan
# ===========================================================================

# AC1 自然排序給 index:img1 < img2 < img10(非 ASCII 字典序)
def test_ac1_scan_natural_sort_index(tmp_path):
    # AC1
    for n in ("img1.png", "img2.png", "img10.png"):
        _mkfile(tmp_path, n)
    recs = imageset.scan(str(tmp_path))
    assert _names(recs) == ["img1.png", "img2.png", "img10.png"]
    assert _indices(recs) == [0, 1, 2]


# AC2 副檔名大小寫不敏感
def test_ac2_scan_extension_case_insensitive(tmp_path):
    # AC2
    for n in ("a.PNG", "b.Jpg", "c.TIFF"):
        _mkfile(tmp_path, n)
    recs = imageset.scan(str(tmp_path))
    assert len(recs) == 3
    assert {r["name"] for r in recs} == {"a.PNG", "b.Jpg", "c.TIFF"}


# AC3 過濾非影像 + 忽略子目錄(含子目錄內同名影像)
def test_ac3_scan_filters_nonimage_and_subdirs(tmp_path):
    # AC3
    _mkfile(tmp_path, "keep.png")
    _mkfile(tmp_path, "note.txt")
    sub = tmp_path / "sub"
    sub.mkdir()
    _mkfile(sub, "inner.png")
    recs = imageset.scan(str(tmp_path))
    assert _names(recs) == ["keep.png"]


# AC4 record 欄位齊全且型別正確
def test_ac4_scan_record_keys_and_types(tmp_path):
    # AC4
    _mkfile(tmp_path, "x.png")
    recs = imageset.scan(str(tmp_path))
    assert len(recs) == 1
    r = recs[0]
    assert set(r.keys()) == {"path", "name", "index", "mtime", "size"}
    assert isinstance(r["path"], str)
    assert isinstance(r["name"], str)
    assert isinstance(r["index"], int)
    assert isinstance(r["mtime"], float)
    assert isinstance(r["size"], int)
    # bool 是 int 的子類別 → 額外釘死 index 不可是 bool(設計語義為位置序號)
    assert not isinstance(r["index"], bool)


# AC5 size / mtime 為真實檔案值;path 為正規化絕對路徑
def test_ac5_scan_size_mtime_path_are_real(tmp_path):
    # AC5
    p = _mkfile(tmp_path, "x.png", data=b"abcde")
    os.utime(p, (1000.0, 1234.5))
    r = imageset.scan(str(tmp_path))[0]
    assert r["size"] == 5
    assert r["mtime"] == 1234.5
    expected = os.path.join(str(tmp_path), "x.png")
    assert os.path.normcase(r["path"]) == os.path.normcase(expected)


# AC6 資料夾不存在 → NotADirectoryError
def test_ac6_scan_missing_folder_raises(tmp_path):
    # AC6
    with pytest.raises(NotADirectoryError):
        imageset.scan(str(tmp_path / "no_such_dir"))


# AC7 目標是檔案(非目錄)→ NotADirectoryError
def test_ac7_scan_target_is_file_raises(tmp_path):
    # AC7
    f = _mkfile(tmp_path, "f.png")
    with pytest.raises(NotADirectoryError):
        imageset.scan(f)


# AC8 空資料夾 / 只含非影像 → 回傳 []
def test_ac8_scan_empty_returns_empty(tmp_path):
    # AC8
    empty = tmp_path / "empty"
    empty.mkdir()
    assert imageset.scan(str(empty)) == []


def test_ac8_scan_only_nonimage_returns_empty(tmp_path):
    # AC8
    _mkfile(tmp_path, "readme.md")
    assert imageset.scan(str(tmp_path)) == []


# AC9 .tif 與 .tiff 都收;完整副檔名比對(c.notpng 不因含 png 子字串入選)
def test_ac9_scan_full_extension_match(tmp_path):
    # AC9
    for n in ("a.tif", "b.tiff", "c.notpng"):
        _mkfile(tmp_path, n)
    recs = imageset.scan(str(tmp_path))
    assert {r["name"] for r in recs} == {"a.tif", "b.tiff"}


# ===========================================================================
# sort_records
# ===========================================================================

# AC10 key="time" 升冪 + 重編 index(mtime 順序 b < a < c)
def test_ac10_sort_by_time_ascending_reindex(tmp_path):
    # AC10
    _mkfile(tmp_path, "a.png", mtime=200.0)
    _mkfile(tmp_path, "b.png", mtime=100.0)
    _mkfile(tmp_path, "c.png", mtime=300.0)
    recs = imageset.scan(str(tmp_path))
    out = imageset.sort_records(recs, key="time")
    assert _names(out) == ["b.png", "a.png", "c.png"]
    assert _indices(out) == [0, 1, 2]


# AC11 key="size" 升冪
def test_ac11_sort_by_size_ascending(tmp_path):
    # AC11
    _mkfile(tmp_path, "big.png", data=b"0123456789")   # 10 bytes
    _mkfile(tmp_path, "small.png", data=b"01")          # 2 bytes
    _mkfile(tmp_path, "mid.png", data=b"01234")         # 5 bytes
    recs = imageset.scan(str(tmp_path))
    out = imageset.sort_records(recs, key="size")
    assert _names(out) == ["small.png", "mid.png", "big.png"]
    assert _indices(out) == [0, 1, 2]


# AC12 key="name" 自然排序(f1 < f2 < f10,非字典序)
def test_ac12_sort_by_name_natural(tmp_path):
    # AC12
    for n in ("f10.png", "f2.png", "f1.png"):
        _mkfile(tmp_path, n)
    recs = imageset.scan(str(tmp_path))
    out = imageset.sort_records(recs, key="name")
    assert _names(out) == ["f1.png", "f2.png", "f10.png"]


# AC13 tie-break deterministic:mtime 相同 → 以 name 自然序 tie-break
def test_ac13_sort_time_tiebreak_by_name(tmp_path):
    # AC13
    _mkfile(tmp_path, "z.png", mtime=500.0)
    _mkfile(tmp_path, "a.png", mtime=500.0)
    recs = imageset.scan(str(tmp_path))
    out = imageset.sort_records(recs, key="time")
    assert _names(out) == ["a.png", "z.png"]


# AC14 非法 key → ValueError
def test_ac14_sort_invalid_key_raises(tmp_path):
    # AC14
    _mkfile(tmp_path, "a.png")
    recs = imageset.scan(str(tmp_path))
    with pytest.raises(ValueError):
        imageset.sort_records(recs, key="bogus")


# AC15 回新 list 且不變更原物件(含其內 dict 的 index)
def test_ac15_sort_returns_new_list_immutable(tmp_path):
    # AC15
    _mkfile(tmp_path, "big.png", data=b"0123456789")
    _mkfile(tmp_path, "small.png", data=b"01")
    _mkfile(tmp_path, "mid.png", data=b"01234")
    original = imageset.scan(str(tmp_path))
    snapshot_names = [r["name"] for r in original]
    snapshot_idx = [r["index"] for r in original]
    out = imageset.sort_records(original, key="size")
    assert out is not original
    assert [r["name"] for r in original] == snapshot_names
    assert [r["index"] for r in original] == snapshot_idx


# AC16 空輸入 → 回傳 []
def test_ac16_sort_empty_input(tmp_path):
    # AC16
    assert imageset.sort_records([], key="name") == []


# ===========================================================================
# progress
# ===========================================================================

# AC17 1-based 格式
def test_ac17_progress_one_based():
    # AC17
    assert imageset.progress(0, 5) == "1 / 5"


# AC18 末尾
def test_ac18_progress_last():
    # AC18
    assert imageset.progress(4, 5) == "5 / 5"


# AC19 total <= 0 → ValueError(total==0 與負值皆是)
def test_ac19_progress_total_zero_raises():
    # AC19
    with pytest.raises(ValueError):
        imageset.progress(0, 0)


def test_ac19_progress_total_negative_raises():
    # AC19
    with pytest.raises(ValueError):
        imageset.progress(2, -1)


# ===========================================================================
# Position(真實讀寫 / round-trip / 持久化)
# ===========================================================================

# AC20 預設值:無紀錄回 default
def test_ac20_position_default(tmp_path):
    # AC20
    p = imageset.Position(str(tmp_path / "state.json"))
    assert p.get(str(tmp_path)) == 0
    assert p.get(str(tmp_path), default=7) == 7


# AC21 set → get round-trip(同一實例)
def test_ac21_position_set_get_roundtrip(tmp_path):
    # AC21
    p = imageset.Position(str(tmp_path / "state.json"))
    p.set(str(tmp_path), 3)
    assert p.get(str(tmp_path)) == 3


# AC22 立即持久化,跨實例(證明 set 已落地磁碟,非只在記憶體)
def test_ac22_position_persist_across_instances(tmp_path):
    # AC22
    state = str(tmp_path / "state.json")
    imageset.Position(state).set(str(tmp_path), 9)
    p2 = imageset.Position(state)
    assert p2.get(str(tmp_path)) == 9


# AC23 狀態檔內容為合法 JSON 且含寫入值 9
def test_ac23_position_state_file_is_valid_json(tmp_path):
    # AC23
    state = str(tmp_path / "state.json")
    imageset.Position(state).set(str(tmp_path), 9)
    with open(state, encoding="utf-8") as f:
        data = json.loads(f.read())
    assert 9 in [int(v) for v in data.values()]


# AC24 多資料夾互不干擾
def test_ac24_position_multiple_folders_independent(tmp_path):
    # AC24
    state = str(tmp_path / "state.json")
    dirA = tmp_path / "dirA"
    dirB = tmp_path / "dirB"
    dirA.mkdir()
    dirB.mkdir()
    p = imageset.Position(state)
    p.set(str(dirA), 1)
    p.set(str(dirB), 4)
    p2 = imageset.Position(state)
    assert p2.get(str(dirA)) == 1
    assert p2.get(str(dirB)) == 4


# AC25 路徑正規化一致(同一資料夾不同寫法對應同一筆)
def test_ac25_position_path_normalization(tmp_path):
    # AC25
    state = str(tmp_path / "state.json")
    p = imageset.Position(state)
    p.set(str(tmp_path), 2)
    # 寫法 1:尾端加分隔字元
    assert p.get(str(tmp_path) + os.sep) == 2
    # 寫法 2:含 sub/.. 的等價路徑
    assert p.get(os.path.join(str(tmp_path), "sub", "..")) == 2


# AC26 毀損狀態檔容錯:get 回 default 不丟例外;後續 set 乾淨覆寫
def test_ac26_position_corrupt_state_file_tolerated(tmp_path):
    # AC26
    state = str(tmp_path / "state.json")
    with open(state, "w", encoding="utf-8") as f:
        f.write("{ not valid json")
    p = imageset.Position(state)
    assert p.get(str(tmp_path)) == 0
    p.set(str(tmp_path), 5)
    assert imageset.Position(state).get(str(tmp_path)) == 5


# AC27 父目錄自動建立
def test_ac27_position_creates_parent_dirs(tmp_path):
    # AC27
    state = str(tmp_path / "nested" / "deep" / "state.json")
    imageset.Position(state).set(str(tmp_path), 1)
    assert os.path.exists(state) is True
    assert imageset.Position(state).get(str(tmp_path)) == 1


# ===========================================================================
# PROP-* 推導 / property 測試(設計沒明列,從契約推導)
# ===========================================================================

# PROP1 (sort_records 為置換 property):任何 key 的排序輸出,
# 其 name 多重集合 = 輸入的 name 多重集合(不漏不增不重)。設計只說「升冪/重編」,
# 未明列「元素集合守恆」,此為從「回傳新 list 重排」推導出的不變量。
def test_prop1_sort_is_permutation_preserving(tmp_path):
    # PROP1
    _mkfile(tmp_path, "f10.png", data=b"01", mtime=300.0)
    _mkfile(tmp_path, "f2.png", data=b"0123", mtime=100.0)
    _mkfile(tmp_path, "f1.png", data=b"012345", mtime=200.0)
    recs = imageset.scan(str(tmp_path))
    base = sorted(_names(recs))
    for key in ("name", "time", "size"):
        out = imageset.sort_records(recs, key=key)
        assert sorted(_names(out)) == base
        # 重編 index 必為 0..n-1 連續無洞
        assert _indices(out) == list(range(len(out)))


# PROP2 (scan 為 sort_records(key="name") 的不動點):設計說 scan 一律以 name
# 自然排序給 index,且 key="name" 與 scan 一致 → 對 scan 結果再做 name 排序,
# 順序與 index 應完全不變(冪等 / 不動點)。設計未把這條一致性明列為 AC。
def test_prop2_scan_is_fixed_point_of_name_sort(tmp_path):
    # PROP2
    for n in ("img1.png", "img2.png", "img10.png", "A.png", "a10.png", "a2.png"):
        _mkfile(tmp_path, n)
    recs = imageset.scan(str(tmp_path))
    out = imageset.sort_records(recs, key="name")
    assert _names(out) == _names(recs)
    assert _indices(out) == _indices(recs)


# PROP3 (progress 全域不變量):對任何合法 index 與 total>0,
# progress 回傳字串恆為 "(index+1) / total" 形狀(1-based 線性映射),
# 跨多組輸入掃描而非只有頭尾兩點(AC17/18 只驗端點)。
@pytest.mark.parametrize("index,total", [(0, 1), (3, 10), (9, 10), (1, 2), (50, 100)])
def test_prop3_progress_is_one_based_linear(index, total):
    # PROP3
    assert imageset.progress(index, total) == "{} / {}".format(index + 1, total)


# PROP4 (Position 路徑正規化等價類):用兩種等價寫法 set 同一資料夾,
# 第二次 set 應覆寫(而非新增)同一筆 → 狀態檔對該等價類只有一筆紀錄。
# 設計說 normalize 使不同寫法對應同一筆,但未明列「不會產生重複 key」。
def test_prop4_position_normalized_key_no_duplicates(tmp_path):
    # PROP4
    state = str(tmp_path / "state.json")
    sub = tmp_path / "sub"
    sub.mkdir()
    p = imageset.Position(state)
    p.set(str(tmp_path), 1)
    # 同一資料夾的等價寫法,改值
    p.set(str(tmp_path) + os.sep, 8)
    assert p.get(str(tmp_path)) == 8
    with open(state, encoding="utf-8") as f:
        data = json.loads(f.read())
    # 等價寫法只對應一筆 key,且其值為最新的 8
    assert list(data.values()).count(8) == 1
    assert 1 not in [int(v) for v in data.values()]
