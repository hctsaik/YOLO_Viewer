"""htmlreport 模組驗收測試(PM 回饋契約)。

來源:3_Architect_Design/16_htmlreport.md(AC1..AC38 + §3 I/O 契約 + §5 邊界)。
本檔只寫測試,不含任何實作。conftest 已把 5_PG_Develop 加進 sys.path,
故直接 `import htmlreport`。此時實作尚未生成,import 不到屬正常(test-first,非紅);
一旦模組存在,各測試應在實作正確前為紅、正確後轉綠。

執行:
  cd C:/code/claude/CV_Viewer && \
  python -m pytest 4_PM_Feedback/test_htmlreport.py -p no:cacheprovider --strict-markers -q

逸出契約(§3.2):等價 html.escape(str(text), quote=True)
  &  → &amp;   <  → &lt;   >  → &gt;   "  → &quot;   '  → &#x27;
其餘字元(含中文、逗號、分號、空白、數字)一律原樣保留。
"""
import copy
import html
import re

import pytest

import htmlreport


# =====================================================================
# 共用測試夾具(設計 §6 釘死 IT1/IT2/ITX)。
# 每個取用夾具的測試自取一份「全新」深拷貝,避免測試間因 mutate 互相污染。
# =====================================================================

def _IT1():
    return {
        "name": "a.png", "path": "/img/a.png",
        "sidecar": {
            "review_status": "done", "verdict": "true_defect",
            "tags": ["True Defect", "Need Review"],
            "bookmarked": True, "rois": [{"bbox": [1, 2, 3, 4]}],
            "comment": "刮傷,邊緣",
        },
        "detections": [
            {"bbox": [10, 20, 30, 40], "cls": "scratch", "conf": 0.9},
            {"bbox": [50, 60, 10, 10], "cls": "dent", "conf": 0.5},
            {"bbox": [0, 0, 5, 5], "cls": "scratch", "conf": 0.7},
        ],
    }


def _IT2():
    # 全缺鍵:sidecar 為空 dict、detections 為空
    return {"name": "b.png", "path": "/img/b.png", "sidecar": {}, "detections": []}


def _ITX():
    # 對抗用:name/tags/comment 帶 XSS 與特殊字元
    return {
        "name": "<script>alert(1)</script>", "path": "/img/x.png",
        "sidecar": {
            "verdict": "unset", "review_status": "none",
            "tags": ["a<b>", "c&d"],
            "comment": 'He said "hi" & <b>bye</b>',
        },
        "detections": [{"bbox": [0, 0, 1, 1], "cls": "scratch", "conf": 0.8765}],
    }


# =====================================================================
# A. escape(逸出行為,釘死;§3.2)
# =====================================================================

def test_ac1_escape_script_angle_brackets():
    # AC1:escape("<script>") == "&lt;script&gt;"
    assert htmlreport.escape("<script>") == "&lt;script&gt;"


def test_ac2_escape_ampersand():
    # AC2:escape("a & b") == "a &amp; b"(& → &amp;)
    assert htmlreport.escape("a & b") == "a &amp; b"


def test_ac3_escape_double_quote():
    # AC3:escape('say "hi"') == "say &quot;hi&quot;"(雙引號 → &quot;)
    assert htmlreport.escape('say "hi"') == "say &quot;hi&quot;"


def test_ac4_escape_single_quote():
    # AC4:escape("it's") == "it&#x27;s"(單引號 → &#x27;,確切字串,非 &#39;/&apos;)
    assert htmlreport.escape("it's") == "it&#x27;s"


def test_ac5_escape_mixed_all_five():
    # AC5:五種字元同時、順序正確、& 不二次逸出
    assert htmlreport.escape("a<b>c&d\"e'f") == "a&lt;b&gt;c&amp;d&quot;e&#x27;f"


def test_ac6_escape_chinese_and_comma_verbatim():
    # AC6:非五種字元一律不動(中文與逗號原樣)
    assert htmlreport.escape("刮傷,邊緣") == "刮傷,邊緣"


def test_ac7_escape_non_string_str_first():
    # AC7:非字串先 str()
    assert htmlreport.escape(3) == "3"
    assert htmlreport.escape(True) == "True"
    assert htmlreport.escape(None) == "None"
    assert htmlreport.escape(0.9) == "0.9"


def test_ac8_escape_already_entity_still_escaped():
    # AC8:已是 entity 的 & 仍被逸出(無智慧偵測):"&amp;" → "&amp;amp;"
    assert htmlreport.escape("&amp;") == "&amp;amp;"


def test_ac9_escape_no_dangerous_raw_form():
    # AC9:逸出後不含危險原形
    out = htmlreport.escape("<script>x</script>")
    assert "<script>" not in out
    assert "</script>" not in out
    assert out == "&lt;script&gt;x&lt;/script&gt;"


# =====================================================================
# B. build_html 骨架與自含性(釘死;§3.3)
# =====================================================================

def test_ac10_doctype_and_html_close():
    # AC10:以 <!DOCTYPE html> 開頭、以 </html> 結尾(允許結尾單一換行)
    h = htmlreport.build_html([_IT1(), _IT2()])
    assert h.startswith("<!DOCTYPE html>")
    assert h.rstrip("\n").endswith("</html>")


def test_ac11_skeleton_substrings_present():
    # AC11:必含骨架子字串皆 in h
    h = htmlreport.build_html([_IT1()])
    for frag in (
        '<html lang="zh-Hant">', '<meta charset="utf-8">',
        "<head>", "</head>", "<body>", "</body>",
        "<style>", "</style>", "<table>", "</table>",
    ):
        assert frag in h, frag


def test_ac12_self_contained_no_external_resources():
    # AC12:自含,無外部資源(含逸出後不應出現 <script 原形)
    h = htmlreport.build_html([_IT1(), _IT2(), _ITX()])
    for forbidden in ("<link", "href=", "<script", "src=", "http://", "https://"):
        assert forbidden not in h, forbidden


def test_ac13_head_before_body_summary_before_table():
    # AC13:head 先於 body,摘要(總案數)先於 table
    h = htmlreport.build_html([_IT1()])
    assert h.index("<head>") < h.index("<body>")
    assert h.index("總案數") < h.index("<table>")


# =====================================================================
# C. 標題(出現在 <title> 與 <h1>,逸出;§3.3)
# =====================================================================

def test_ac14_default_title():
    # AC14:預設標題出現在 <title> 與 <h1>
    h = htmlreport.build_html([_IT1()])
    assert "<title>CV Review Report</title>" in h
    assert "<h1>CV Review Report</h1>" in h


def test_ac15_custom_title():
    # AC15:自訂中文標題出現在 <title> 與 <h1>
    h = htmlreport.build_html([_IT1()], title="我的報告")
    assert "<title>我的報告</title>" in h
    assert "<h1>我的報告</h1>" in h


def test_ac16_title_escaped():
    # AC16:標題經逸出(<title>/<h1> 內無原始 <b>)
    h = htmlreport.build_html([], title='X<b>&"')
    assert '<title>X&lt;b&gt;&amp;&quot;</title>' in h
    assert '<h1>X&lt;b&gt;&amp;&quot;</h1>' in h


# =====================================================================
# D. 摘要列(總案數 / 已審數,釘死計數;§3.5)
# =====================================================================

def test_ac17_summary_it1_it2():
    # AC17:IT1(verdict≠unset 且 status=done → 已審)、IT2(全缺鍵 → 未審)
    h = htmlreport.build_html([_IT1(), _IT2()])
    assert "總案數:2" in h
    assert "已審數:1" in h


def test_ac18_summary_empty_items():
    # AC18:空 items → 總案數:0、已審數:0
    h = htmlreport.build_html([])
    assert "總案數:0" in h
    assert "已審數:0" in h


def test_ac19_reviewed_by_verdict_only():
    # AC19:已審判定僅 verdict≠unset(即使 status=none)
    it = {"name": "v", "sidecar": {"verdict": "false_alarm", "review_status": "none"},
          "detections": []}
    h = htmlreport.build_html([it])
    assert "已審數:1" in h


def test_ac20_reviewed_by_status_done_only():
    # AC20:已審判定僅 status=done(即使 verdict=unset)
    it = {"name": "s", "sidecar": {"verdict": "unset", "review_status": "done"},
          "detections": []}
    h = htmlreport.build_html([it])
    assert "已審數:1" in h


def test_ac21_not_reviewed():
    # AC21:verdict=unset 且 status=none → 未審
    it = {"name": "n", "sidecar": {"verdict": "unset", "review_status": "none"},
          "detections": []}
    h = htmlreport.build_html([it])
    assert "已審數:0" in h
    assert "總案數:1" in h


# =====================================================================
# E. 表格結構與列數(釘死;§3.4 / §5)
# =====================================================================

def test_ac22_header_seven_th_exact():
    # AC22:表頭 7 個 <th>,文字精確、順序固定
    h = htmlreport.build_html([_IT1()])
    assert re.findall(r"<th>(.*?)</th>", h) == [
        "Name", "Verdict", "Tags", "Status", "Detections", "Max Conf", "Comment",
    ]


@pytest.mark.parametrize("items_factory, expected_tr", [
    (lambda: [_IT1(), _IT2()], 3),
    (lambda: [_IT1()], 2),
    (lambda: [], 1),
    (lambda: [_IT1(), _IT2(), _ITX()], 4),
])
def test_ac23_data_row_count_is_1_plus_len(items_factory, expected_tr):
    # AC23:<tr> 數 == 1(表頭) + len(items)
    h = htmlreport.build_html(items_factory())
    assert len(re.findall(r"<tr>", h)) == expected_tr


def test_ac24_tr_open_close_paired():
    # AC24:<tr> 與 </tr> 成對且各為 3(表頭 + 2 資料列)
    h = htmlreport.build_html([_IT1(), _IT2()])
    assert h.count("<tr>") == h.count("</tr>") == 3


def test_ac25_seven_td_per_data_row():
    # AC25:每資料列 7 個 <td>
    assert htmlreport.build_html([_IT1()]).count("<td>") == 7
    assert htmlreport.build_html([_IT1(), _IT2()]).count("<td>") == 14


def test_ac26_empty_items_header_only_and_message():
    # AC26:空 items 只有表頭列、無資料 <td>,並含「沒有可顯示的案例」
    h = htmlreport.build_html([])
    assert h.count("<tr>") == 1
    assert h.count("<td>") == 0
    assert "沒有可顯示的案例" in h


# =====================================================================
# F. 資料列逐 cell 值(釘死,含逸出與格式;§3.4)
# =====================================================================

def test_ac27_it1_seven_cells_exact():
    # AC27:IT1 七個 cell 確切(tags 以 "; " 串接、n_det=3、max_conf=f"{0.9:.3f}"、中文 comment 原樣)
    h = htmlreport.build_html([_IT1()])
    assert re.findall(r"<td>(.*?)</td>", h) == [
        "a.png", "true_defect", "True Defect; Need Review", "done",
        "3", "0.900", "刮傷,邊緣",
    ]


def test_ac28_it2_all_missing_cells_exact():
    # AC28:IT2 全缺鍵 cell 確切(verdict→unset、tags→空、status→none、n_det=0、max_conf→0.000、comment→空)
    h = htmlreport.build_html([_IT2()])
    assert re.findall(r"<td>(.*?)</td>", h) == [
        "b.png", "unset", "", "none", "0", "0.000", "",
    ]


def test_ac29_max_conf_three_decimal_format():
    # AC29:max_conf 呈現為固定三位小數(四捨五入)
    it_05 = {"name": "c", "sidecar": {},
             "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.5}]}
    assert re.findall(r"<td>(.*?)</td>", htmlreport.build_html([it_05]))[5] == "0.500"
    # IT1 最大 conf = 0.9 → "0.900"
    assert re.findall(r"<td>(.*?)</td>", htmlreport.build_html([_IT1()]))[5] == "0.900"
    # conf 為 int 1 → "1.000"
    it_int = {"name": "i", "sidecar": {},
              "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 1}]}
    assert re.findall(r"<td>(.*?)</td>", htmlreport.build_html([it_int]))[5] == "1.000"
    # conf 0.8765 → 四捨五入至 3 位 → "0.877"
    it_round = {"name": "r", "sidecar": {},
                "detections": [{"bbox": [0, 0, 1, 1], "cls": "x", "conf": 0.8765}]}
    assert re.findall(r"<td>(.*?)</td>", htmlreport.build_html([it_round]))[5] == "0.877"


def test_ac30_xss_special_chars_escaped_into_cells():
    # AC30:XSS / 特殊字元逸出進 cell;危險標籤成文字、內容仍可見
    h = htmlreport.build_html([_ITX()])
    cells = re.findall(r"<td>(.*?)</td>", h)
    assert cells[0] == "&lt;script&gt;alert(1)&lt;/script&gt;"        # name 逸出
    assert cells[2] == "a&lt;b&gt;; c&amp;d"                          # tags "a<b>","c&d" → "; " 串接後逸出
    assert cells[6] == "He said &quot;hi&quot; &amp; &lt;b&gt;bye&lt;/b&gt;"  # comment 逸出
    assert "<script>" not in h
    assert "alert(1)" in cells[0]


def test_ac31_multi_item_row_order_aligns_items():
    # AC31:多 item 各列首 cell 原序對齊 items
    h = htmlreport.build_html([_IT1(), _IT2()])
    names = re.findall(r"<tr>.*?<td>(.*?)</td>", h, re.S)
    assert names == ["a.png", "b.png"]


# =====================================================================
# G. 不 mutate 輸入(§5)
# =====================================================================

def test_ac32_build_html_does_not_mutate_input():
    # AC32:build_html 不就地改 items / sidecar / detections / tags
    items = [_IT1(), _IT2(), _ITX()]
    snap = copy.deepcopy(items)
    htmlreport.build_html(items)
    assert items == snap


# =====================================================================
# H. write_report(Tier B,tmp_path 真實寫讀,逐字;§3.6)
# =====================================================================

def test_ac33_write_report_returns_path_and_file_exists(tmp_path):
    # AC33:回傳路徑 == str(out_path) 且檔存在
    import os
    p = tmp_path / "r.html"
    ret = htmlreport.write_report(p, [_IT1(), _IT2()])
    assert ret == str(p)
    assert os.path.exists(ret) is True


def test_ac34_disk_content_equals_build_html(tmp_path):
    # AC34:寫入內容 == build_html,讀回逐字相等
    p = tmp_path / "r.html"
    ret = htmlreport.write_report(p, [_IT1(), _IT2()], title="我的報告")
    with open(ret, "r", encoding="utf-8") as f:
        disk = f.read()
    assert disk == htmlreport.build_html([_IT1(), _IT2()], title="我的報告")


def test_ac35_utf8_lossless_and_escape_correct(tmp_path):
    # AC35:UTF-8 中文無損 + 逸出正確
    p = tmp_path / "r.html"
    ret = htmlreport.write_report(p, [_IT1(), _IT2()], title="我的報告")
    with open(ret, "r", encoding="utf-8") as f:
        disk = f.read()
    assert "刮傷,邊緣" in disk
    assert "<title>我的報告</title>" in disk
    # 另寫一份 ITX,驗逸出後讀回無原始 <script>
    p2 = tmp_path / "x.html"
    ret2 = htmlreport.write_report(p2, [_ITX()])
    with open(ret2, "r", encoding="utf-8") as f:
        disk2 = f.read()
    assert "&lt;script&gt;" in disk2
    assert "<script>" not in disk2


def test_ac36_out_path_accepts_str(tmp_path):
    # AC36:out_path 接受 str
    p = str(tmp_path / "s.html")
    ret = htmlreport.write_report(p, [_IT1()])
    assert ret == p
    with open(ret, "r", encoding="utf-8") as f:
        assert f.read() == htmlreport.build_html([_IT1()])


def test_ac37_empty_items_writes_legal_html(tmp_path):
    # AC37:空 items 仍寫合法 HTML 骨架 + 無資料訊息 + 摘要 0
    p = tmp_path / "empty.html"
    ret = htmlreport.write_report(p, [])
    with open(ret, "r", encoding="utf-8") as f:
        disk = f.read()
    assert disk.startswith("<!DOCTYPE html>")
    assert "沒有可顯示的案例" in disk
    assert "總案數:0" in disk


def test_ac38_overwrite_semantics(tmp_path):
    # AC38:同 out_path 重複呼叫,後者完全覆寫前者(非附加)
    p = tmp_path / "ow.html"
    htmlreport.write_report(p, [_IT1(), _IT2()])
    htmlreport.write_report(p, [_IT2()])
    with open(p, "r", encoding="utf-8") as f:
        disk = f.read()
    assert len(re.findall(r"<tr>", disk)) == 2   # 1 表頭 + 1 資料列
    assert "a.png" not in disk
    assert "b.png" in disk


# =====================================================================
# 推導 / property / metamorphic 測試(設計未明列;由契約推導,
# 即使與設計同源也能逼出實作 bug)
# =====================================================================

def test_invariant_escape_equiv_html_escape_quote_true():
    # 推導(§3.2 鐵則):escape 對任意 str 等價 html.escape(s, quote=True)。
    # 用一批含全部五種字元 + 中文 + 邊界的樣本逐字比對,把契約變硬斷言。
    samples = [
        "<script>", "a & b", 'say "hi"', "it's", "a<b>c&d\"e'f",
        "刮傷,邊緣", "&amp;", "", "純文字 no special", "<a href=\"x\">'&</a>",
        "Tom & Jerry <co>", '混<>&"\'合',
    ]
    for s in samples:
        assert htmlreport.escape(s) == html.escape(s, quote=True), repr(s)


def test_invariant_escape_output_has_no_raw_dangerous_chars():
    # 推導:逸出後字串不得含任何裸 < > 或裸 " ' ;& 僅能以合法 entity 形式出現(&xxx;)。
    for s in ["<script>alert('x')</script>", 'a"b<c>d&e', "<<>>&&\"\"''"]:
        out = htmlreport.escape(s)
        assert "<" not in out
        assert ">" not in out
        assert '"' not in out
        assert "'" not in out
        # 每個 & 後必接合法 entity(amp;/lt;/gt;/quot;/#x27;)
        for amp_tail in re.findall(r"&(.{0,5})", out):
            assert amp_tail.startswith(("amp;", "lt;", "gt;", "quot;", "#x27;")), out


def test_invariant_data_td_count_equals_seven_times_len():
    # 推導(§3.4):總資料 <td> 數 == 7 * len(items)(每案恰 7 cell),對多種長度成立。
    for items in ([_IT1()], [_IT1(), _IT2()], [_IT1(), _IT2(), _ITX()]):
        h = htmlreport.build_html(items)
        assert h.count("<td>") == 7 * len(items)
        assert h.count("<td>") == h.count("</td>")


def test_invariant_summary_reviewed_le_total():
    # 推導(§3.5):已審數 R ∈ [0, N],且 reviewed 邏輯為 (verdict!=unset) or (status==done)。
    # 用混合 items 驗 R 計數與獨立重算一致。
    items = [_IT1(), _IT2(), _ITX(),
             {"name": "rv", "sidecar": {"verdict": "x", "review_status": "none"}, "detections": []},
             {"name": "rs", "sidecar": {"verdict": "unset", "review_status": "done"}, "detections": []}]
    n = len(items)
    r = sum(1 for it in items
            if it.get("sidecar", {}).get("verdict", "unset") != "unset"
            or it.get("sidecar", {}).get("review_status", "none") == "done")
    h = htmlreport.build_html(items)
    assert f"總案數:{n}" in h
    assert f"已審數:{r}" in h
    assert 0 <= r <= n


def test_invariant_write_report_does_not_mutate_input(tmp_path):
    # 推導(§5 跨 I/O 不變式):write_report 寫檔後不得 mutate 輸入 items。
    items = [_IT1(), _IT2(), _ITX()]
    snap = copy.deepcopy(items)
    htmlreport.write_report(tmp_path / "m.html", items)
    assert items == snap


def test_invariant_build_html_no_crlf_for_roundtrip():
    # 推導(§3.6 註):為使 write_report round-trip 逐字成立,build_html 輸出不得含 \r\n。
    h = htmlreport.build_html([_IT1(), _IT2(), _ITX()], title="混<>合")
    assert "\r\n" not in h
    assert "\r" not in h
