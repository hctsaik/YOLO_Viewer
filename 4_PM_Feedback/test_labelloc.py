"""驗收測試:labelloc 模組(Tier B — 有檔案系統 I/O,但無 GUI、無跨模組契約;純單元判綠)。

對應設計 3_Architect_Design/22_labelloc.md §5 的 AC1~AC28,逐條落成可執行 pytest;
邊界(§4)以 tmp_path 自造目錄結構真實 I/O 驗收;另含若干「設計未明列」的推導 / property 測試
(見檔尾 H 段:precedence 唯一決定、resolve→label_path 往返一致、normcase 比對的雙向性…)。

跑法:
  cd C:/code/claude/CV_Viewer && python -m pytest 4_PM_Feedback/test_labelloc.py \
       -p no:cacheprovider --strict-markers -q
閘門:
  python verify/gate.py labelloc

此時實作尚未寫;import 不到 labelloc 屬正常(實作由 /pg 寫到 5_PG_Develop/labelloc.py)。
conftest 已把 5_PG_Develop 加進 sys.path,故測試直接 `import labelloc`。
設計 §5 硬約束:本測試**不得** import imageset / yolo(解耦驗收)。
.json 內容可為 "" 或 "[]"(本模組不讀內容,只看檔名存在)。
"""
import os
from pathlib import Path

import pytest

import labelloc


# ---------------------------------------------------------------------------
# 造檔小工具(供測試共用;不入契約,純測試輔助)
# ---------------------------------------------------------------------------
def _touch(p, content="[]"):
    """造一個 .json 檔(內容預設 "[]";本模組不讀內容,只看檔名存在)。"""
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(content, encoding="utf-8")
    return str(p)


# =====================================================================
# A. 主入口 resolve_label_dir — 核心判定(最具鑑別力)
# =====================================================================

def test_subdir_with_matching_json_returns_subdir(tmp_path):
    # AC1:labels/ 含對應 json → 回子夾
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(sub))


def test_no_subdir_samelevel_json_returns_samelevel(tmp_path):
    # AC2:無 labels/、同層含 json → 回同層
    _touch(tmp_path / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(tmp_path))


def test_empty_subdir_returns_samelevel(tmp_path):
    # AC3:labels/ 存在但空 → 回同層(空子夾不得吃掉同層)
    (tmp_path / "labels").mkdir()
    _touch(tmp_path / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(tmp_path))


def test_subdir_json_not_matching_stems_returns_samelevel(tmp_path):
    # AC4:labels/ 有 json 但 stem 不對應 → 回同層(避免別批標註誤套)
    _touch(tmp_path / "labels" / "other.json")
    _touch(tmp_path / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(tmp_path))


def test_folder_missing_returns_none_and_creates_nothing(tmp_path):
    # AC5:folder 不存在 → None,且不建立任何檔案/資料夾
    nope = tmp_path / "nope"
    got = labelloc.resolve_label_dir(str(nope), ["img1"])
    assert got is None
    assert os.path.exists(str(nope)) is False


def test_folder_is_file_returns_none(tmp_path):
    # AC6:folder 是檔案而非資料夾 → None
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
    assert labelloc.resolve_label_dir(str(f), ["img1"]) is None


def test_subdir_is_file_not_dir_returns_samelevel(tmp_path):
    # AC7:labels/ 是檔案不是目錄 → 回同層(isdir 為 False → 視為無子夾)
    (tmp_path / "labels").write_text("not a dir", encoding="utf-8")
    _touch(tmp_path / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(tmp_path))


def test_subdir_wins_over_samelevel(tmp_path):
    # AC8:子夾優先於同層:兩處皆有同 stem → 回子夾(釘死平手取捨;見 §3)
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    _touch(tmp_path / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(sub))


def test_subdir_wins_even_with_different_content(tmp_path):
    # AC9:子夾優先:內容不同也回子夾路徑(本模組不讀內容)
    sub = tmp_path / "labels"
    _touch(sub / "img1.json", content='[{"bbox":[1,1,1,1]}]')
    _touch(tmp_path / "img1.json", content="[]")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(sub))


def test_resolve_always_returns_absolute_path(tmp_path, monkeypatch):
    # AC10:回傳恆為絕對路徑(即使傳入相對 folder 亦然)
    # 對 AC1(子夾)與 AC2(同層)兩個情境各驗一次。
    # 用 monkeypatch chdir 到 tmp_path,再以相對路徑 "." 傳入。
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    monkeypatch.chdir(tmp_path)
    got_sub = labelloc.resolve_label_dir(".", ["img1"])  # AC1 形態,相對輸入
    assert os.path.isabs(got_sub) is True

    # AC2 形態(同層):另開一個乾淨子資料夾,只放同層 json
    plain = tmp_path / "plain"
    _touch(plain / "img2.json")
    got_same = labelloc.resolve_label_dir("plain", ["img2"])  # 相對輸入
    assert os.path.isabs(got_same) is True


def test_partial_match_still_adopts_subdir(tmp_path):
    # AC11:部分對應即採子夾(交集非空即「被證實」,至少 1 個對應即採)
    sub = tmp_path / "labels"
    _touch(sub / "img2.json")  # 只有 img2,缺 img1/img3
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1", "img2", "img3"])
    assert got == os.path.abspath(str(sub))


# =====================================================================
# B. 退化與空清單
# =====================================================================

def test_stems_none_degrades_any_json_adopts_subdir(tmp_path):
    # AC12:stems=None → 退化:labels/ 含任一 *.json 即採子夾(不要求對應特定 stem)
    sub = tmp_path / "labels"
    _touch(sub / "whatever.json")
    got = labelloc.resolve_label_dir(str(tmp_path), None)
    assert got == os.path.abspath(str(sub))


def test_stems_none_empty_subdir_returns_samelevel(tmp_path):
    # AC13:stems=None + labels/ 空 → 回同層
    (tmp_path / "labels").mkdir()
    got = labelloc.resolve_label_dir(str(tmp_path), None)
    assert got == os.path.abspath(str(tmp_path))


def test_empty_stems_list_does_not_adopt_subdir(tmp_path):
    # AC14:stems=[] 空清單 → 不採子夾 → 回同層(空清單視同無對應檔)
    _touch(tmp_path / "labels" / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), [])
    assert got == os.path.abspath(str(tmp_path))


# =====================================================================
# C. 跨平台大小寫(枚舉法 + normcase)
# =====================================================================

def test_subdir_case_variant_hits_and_returns_real_name(tmp_path):
    # AC15:子夾名大小寫變體(Labels 首字大寫)→ 命中並回真實名
    # 斷言用磁碟上實際建立的名組期望值,不寫死字面 "labels"。
    real_sub = tmp_path / "Labels"
    _touch(real_sub / "img1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"], subdir="labels")
    assert got == os.path.abspath(str(real_sub))


def test_ext_case_variant_treated_as_match(tmp_path):
    # AC16:ext 大小寫(.JSON)→ 視同對應
    sub = tmp_path / "labels"
    _touch(sub / "img1.JSON")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"], ext=".json")
    assert got == os.path.abspath(str(sub))


def test_stem_case_variant_treated_as_match(tmp_path):
    # AC17:stem 大小寫(IMG1.json vs stem img1)→ 視同對應
    sub = tmp_path / "labels"
    _touch(sub / "IMG1.json")
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(sub))


# =====================================================================
# D. has_labels helper 直驗
# =====================================================================

def test_has_labels_matching_stem_true(tmp_path):
    # AC18:has_labels:含對應 stem → True
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    assert labelloc.has_labels(str(sub), ["img1"]) is True


def test_has_labels_empty_dir_false(tmp_path):
    # AC19:has_labels:空目錄 → False
    sub = tmp_path / "labels"
    sub.mkdir()
    assert labelloc.has_labels(str(sub), ["img1"]) is False


def test_has_labels_json_not_matching_stem_false(tmp_path):
    # AC20:has_labels:有 json 但 stem 不對應 → False
    sub = tmp_path / "labels"
    _touch(sub / "other.json")
    assert labelloc.has_labels(str(sub), ["img1"]) is False


def test_has_labels_missing_dir_false_no_raise(tmp_path):
    # AC21:has_labels:不存在目錄 → False 不拋
    assert labelloc.has_labels(str(tmp_path / "nope"), ["img1"]) is False


def test_has_labels_stems_none_degrades(tmp_path):
    # AC22:has_labels:stems=None → 含任一 *.json 即 True;空目錄 → False
    sub = tmp_path / "labels"
    _touch(sub / "x.json")
    assert labelloc.has_labels(str(sub), None) is True

    empty = tmp_path / "labels_empty"
    empty.mkdir()
    assert labelloc.has_labels(str(empty), None) is False


# =====================================================================
# E. label_path 純字串(對齊既有 _pred_path,防 regression)
# =====================================================================

def test_label_path_pure_join():
    # AC23:label_path 純組合
    assert labelloc.label_path("/some/dir", "/imgs/wafer_001.png") == \
        os.path.join("/some/dir", "wafer_001.json")


def test_label_path_no_fs_touch_no_raise(tmp_path):
    # AC24:label_path 不碰 FS / 不檢存在;對不存在路徑仍回完整字串、不拋、不建檔
    missing_dir = str(tmp_path / "nope_dir")
    missing_img = str(tmp_path / "ghost" / "nope.png")
    got = labelloc.label_path(missing_dir, missing_img)
    assert got == os.path.join(missing_dir, "nope.json")
    assert os.path.exists(missing_dir) is False
    assert os.path.exists(os.path.dirname(missing_img)) is False
    assert os.path.exists(got) is False


def test_label_path_matches_pred_path_semantics():
    # AC25:label_path 對齊 app._pred_path 語義(防 integration regression)
    # _pred_path 等價於 str(Path(pred_folder) / f"{stem}.json"),其中 stem = Path(image_path).stem。
    # 不 import app(避免拖入 Streamlit 依賴),改在此重現 _pred_path 的純字串語義,並以 normpath 比對相等。
    cases = [
        ("/some/dir", "/imgs/wafer_001.png"),
        ("rel/dir", "a/b/c.jpg"),
        ("D:/x", "D:/y/z.tiff"),
        (".", "img1.png"),
    ]
    for pred_folder, image_path in cases:
        stem = Path(image_path).stem
        pred_path_equiv = str(Path(pred_folder) / f"{stem}.json")
        assert os.path.normpath(labelloc.label_path(pred_folder, image_path)) == \
            os.path.normpath(pred_path_equiv)


def test_label_path_unicode_stem():
    # AC26:label_path 接受 stem 取法一致(Unicode 安全)
    got = labelloc.label_path("/d", "/a/b/IMG_前綴.後綴.png")
    assert os.path.basename(got) == "IMG_前綴.後綴.json"
    assert os.path.basename(got) == Path("/a/b/IMG_前綴.後綴.png").stem + ".json"


# =====================================================================
# F. 容錯不拋(全程)
# =====================================================================

def test_resolve_never_raises(tmp_path):
    # AC27:resolve 永不拋。對各輸入皆回值(str 或 None)而非拋例外。
    uni = tmp_path / "資料夾_α"
    uni.mkdir()
    inputs = [
        str(tmp_path / "does_not_exist"),     # 不存在路徑
        str(uni),                             # 含 Unicode 的存在資料夾
        "",                                   # 空字串
    ]
    # 檔案路徑
    f = tmp_path / "afile.bin"
    f.write_bytes(b"x")
    inputs.append(str(f))

    for inp in inputs:
        got = labelloc.resolve_label_dir(inp, ["img1"])
        assert got is None or isinstance(got, str)


def test_label_path_never_raises():
    # AC28:label_path 永不拋。label_path("","")、label_path("/d","") 皆回字串。
    assert isinstance(labelloc.label_path("", ""), str)
    assert isinstance(labelloc.label_path("/d", ""), str)


# =====================================================================
# H. 推導 / property 測試(設計未明列,從契約推導的硬約束)
# =====================================================================

def test_precedence_uniquely_decides_when_both_locations_have_file(tmp_path):
    # 推導(§3 平手取捨「子夾優先」的唯一性):同 stem 在同層與子夾各放一份(內容刻意不同),
    # 規則必須「唯一決定」→ 回的目錄恰為子夾、且絕不是同層(兩者互斥,不得模稜)。
    sub = tmp_path / "labels"
    _touch(sub / "img1.json", content='[{"a":1}]')
    _touch(tmp_path / "img1.json", content='[{"b":2}]')
    got = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert got == os.path.abspath(str(sub))
    assert got != os.path.abspath(str(tmp_path))  # 唯一:不會是同層


def test_resolve_then_label_path_round_trip_points_to_existing_file(tmp_path):
    # 推導(往返一致 / round-trip):resolve 出的目錄餵進 label_path,組出的路徑
    # 必須真的指到磁碟上存在的標註檔(子夾情境)。釘死「定位 → 組路徑」鏈閉合。
    sub = tmp_path / "labels"
    real = _touch(sub / "img1.json")
    resolved = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    path = labelloc.label_path(resolved, "/anywhere/img1.png")
    assert os.path.isfile(path) is True
    assert os.path.normpath(path) == os.path.normpath(real)


def test_round_trip_samelevel_layout_points_to_existing_file(tmp_path):
    # 推導(往返一致;同層佈局 = sample_images 現況):無子夾、同層放 img1.json,
    # resolve→label_path 也必須指到那個真檔。
    real = _touch(tmp_path / "img1.json")
    resolved = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    path = labelloc.label_path(resolved, "/x/img1.png")
    assert os.path.isfile(path) is True
    assert os.path.normpath(path) == os.path.normpath(real)


def test_resolve_idempotent_on_fixed_disk_state(tmp_path):
    # 推導(純函式 / 確定性,§ 整合 (E) cache 安全依賴此性質):
    # 對固定磁碟狀態,重複呼叫 resolve 結果相同(子夾與同層兩種佈局各驗)。
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    a = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    b = labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    assert a == b == os.path.abspath(str(sub))

    plain = tmp_path / "plain"
    _touch(plain / "img2.json")
    c = labelloc.resolve_label_dir(str(plain), ["img2"])
    d = labelloc.resolve_label_dir(str(plain), ["img2"])
    assert c == d == os.path.abspath(str(plain))


def test_resolve_does_not_create_or_write_anything(tmp_path):
    # 推導(§2.2 純讀檔,不建檔不寫檔):呼叫 resolve 前後,資料夾內容(檔案集合)完全不變,
    # 且絕不冒出 labels/ 子夾或任何暫存檔。
    _touch(tmp_path / "img1.json")
    before = sorted(os.listdir(str(tmp_path)))
    labelloc.resolve_label_dir(str(tmp_path), ["img1"])
    after = sorted(os.listdir(str(tmp_path)))
    assert before == after


def test_resolve_normalizes_dotdot_to_clean_abspath(tmp_path):
    # 推導(§4.n folder 含 ..):含 ".." 的輸入須正規化成乾淨絕對路徑(無殘留 ".."),
    # 確保下游 _pred_path / _detections cache key 穩定。
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    messy = os.path.join(str(tmp_path), "sub", "..")  # 等價於 tmp_path
    (tmp_path / "sub").mkdir()
    got = labelloc.resolve_label_dir(messy, ["img1"])
    assert got == os.path.abspath(str(sub))
    assert ".." not in got


def test_has_labels_consistent_with_resolve_subdir_decision(tmp_path):
    # 推導(has_labels 是 resolve 採子夾的判定核心;兩者語義必須一致):
    # has_labels(子夾, stems) 為 True ⟺ resolve 採子夾;為 False ⟺ resolve 退同層。
    sub = tmp_path / "labels"
    _touch(sub / "img1.json")
    _touch(tmp_path / "img1.json")  # 同層也有,確保 fallback 有去處
    stems = ["img1"]
    if labelloc.has_labels(str(sub), stems):
        assert labelloc.resolve_label_dir(str(tmp_path), stems) == os.path.abspath(str(sub))
    else:
        assert labelloc.resolve_label_dir(str(tmp_path), stems) == os.path.abspath(str(tmp_path))

    # 反向:子夾存在但 stem 不對應 → has_labels False,resolve 退同層
    sub2_parent = tmp_path / "case2"
    sub2 = sub2_parent / "labels"
    _touch(sub2 / "other.json")
    _touch(sub2_parent / "img1.json")
    assert labelloc.has_labels(str(sub2), stems) is False
    assert labelloc.resolve_label_dir(str(sub2_parent), stems) == os.path.abspath(str(sub2_parent))


def test_empty_string_folder_returns_none(tmp_path):
    # 推導(§4.a 的延伸 + AC27):空字串 folder 不是有效資料夾 → None(os.path.isdir("") 為 False)。
    assert labelloc.resolve_label_dir("", ["img1"]) is None
