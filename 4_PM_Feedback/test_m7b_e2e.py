"""M7b 切片的真實 E2E 驗收(Viewer-First 鍵盤工作流 — ←/→ nav / verdict 熱鍵 1·2·3 /
r·b 循環狀態·書籤 / 切張自動存 / 跨圖 undo(可撤 N 筆 + toast)/ 焦點守衛 / PerfA)。

對應設計 `3_Architect_Design/20_viewer_workbench_redesign.md` §5 的 M7b-AC1…AC11。
只落本切片(M7b)的 AC;M7a(版面/固定 key/zoom·pan)與 M7c(比較/虛擬化/RWD/DZI)不在此檔。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_m7b_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
conftest 的 app_server 會自動起 streamlit run 5_PG_Develop/app.py;page fixture 已開好瀏覽器。

TDD 提醒:M7b 的實作(index.html document keydown→nav 事件協定、viewer.py nav_keys=True 接線、
app.py nav 事件 dispatch + 改值即時存 + 跨圖 undo_stack + footer「可撤 N 筆」+ [−]/[+] 細調鈕 +
P1 探針回寫 data-verdict/data-status/data-bookmarked/data-conf)PG 尚未完成,故本檔現在預期『紅』是正常的。

────────────────────────────────────────────────────────────────────────────
本檔釘死的『可機器斷言觀測面』(PM 定義契約,PG 必須暴露;設計 §5 P1 已預期 data-verdict):
  - 主文件 P1 探針 `#perf`(沿用 M7a 的 `[data-render-ms]`)『額外』回寫『目前顯示圖』的判定狀態:
      data-verdict     ∈ {"unset","true_defect","false_alarm","reflection"}  (= tagging.VERDICTS)
      data-status      ∈ {"none","need_review","done"}
      data-bookmarked  ∈ {"0","1"}
      data-conf-lo     = 目前信心門檻下界(float 字串,供 AC8 step 量測;契約演進見
                         3_Architect_Design/20_viewer_workbench_redesign.md §7 2026-07-04,取代單值 data-conf)
      data-conf-hi     = 目前信心門檻上界(float 字串;AC-conf* 在 test_conf_range_e2e.py)
  - footer 常駐文字含「可撤 N 筆」(N = undo_stack 深度;設計 §3.6 / AC5 / AC7)。
  - 跨圖 undo 觸發 `st.toast`,文字含「撤銷」(設計 §3.6 / AC6)。
  - 鍵盤事件落在 viewer 元件 iframe 的 document keydown(設計 §2.1 nav_keys / §3.4 鍵位表);
    本檔以 `vf.locator('#osd').press(key)` 對該 iframe 內元素派發真實鍵盤事件(冒泡到 document)。
────────────────────────────────────────────────────────────────────────────
"""
import re
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_images"

APP_TITLE = "YOLO Image Viewer"
TOTAL = 8  # sample_images 內 8 張(5 lot42 png + 3 wafer16 tif)

VERDICTS = ("unset", "true_defect", "false_alarm", "reflection")  # = tagging.VERDICTS
STATUSES = ("none", "need_review", "done")


# ============================== sidecar 隔離(PM 擁有測試基建)==============================
@pytest.fixture(autouse=True)
def _sidecar_sandbox():
    """M7b 測試會經 app 寫 sidecar(verdict/status/bookmark)到 sample_images 旁的
    `<stem>.cvr.json`(sidecar.sidecar_path 規約)。每個測試前快照、測試後還原 ——
    保證測試**冪等**且不永久污染樣本資料。屬 PM 擁有的測試基建(PG 唯讀)。"""
    before = {}
    try:
        for p in SAMPLE.glob("*.cvr.json"):
            before[p.name] = p.read_bytes()
    except Exception:
        pass
    yield
    # 還原:刪掉測試新建的、覆寫回被改動的
    try:
        for p in list(SAMPLE.glob("*.cvr.json")):
            if p.name not in before:
                p.unlink()
        for name, data in before.items():
            (SAMPLE / name).write_bytes(data)
    except Exception:
        pass


# ============================== 共用定位 helper(沿用 test_m7a_e2e.py 範式)==============================
def _wait_app_ready(page):
    # 版面演進(跨輪):頂列資訊徽章整條移除 → 不再有可見『N / 8』;改以 P1 探針 [data-render-ms]
    # (主文件 DOM,設計 §5 P1 機器讀面)當 ready;再加等『下一張』鈕 hydrate(查鈕不撲空)。
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name=re.compile(r"下一張")).first.wait_for(timeout=60000)


def _find_viewer_frame(page, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in page.frames:
            try:
                if f.locator("canvas").count() > 0:
                    return f
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def _wait_viewer_open(vf, timeout=30000):
    vf.wait_for_function(
        "() => window.viewer && window.viewer.viewport "
        "&& window.viewer.isOpen && window.viewer.isOpen()",
        timeout=timeout)


def _progress_index(page):
    """讀目前進度序號 N(頂列資訊徽章移除後改讀 P1 探針 data-idx;設計 §5 P1 機器讀面);失敗回 None。"""
    v = page.locator("[data-render-ms]").first.get_attribute("data-idx")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _wait_progress(page, n, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _progress_index(page) == n:
            return True
        page.wait_for_timeout(250)
    return False


def _jump_to(page, n):
    """用 Command Bar 跳頁 number_input 跳到第 n 張,等進度穩定。"""
    sp = page.get_by_role("spinbutton").first
    sp.fill(str(n))
    sp.press("Enter")
    _wait_progress(page, n)


def _probe(page):
    el = page.locator("[data-render-ms]").first
    el.wait_for(state="attached", timeout=30000)
    return el


def _probe_attr(page, attr):
    return _probe(page).get_attribute(attr)


def _verdict(page):
    return _probe_attr(page, "data-verdict")


def _status(page):
    return _probe_attr(page, "data-status")


def _bookmarked(page):
    return _probe_attr(page, "data-bookmarked")


def _conf_lo(page):
    """信心門檻下界(契約演進 2026-07-04:單值 data-conf → 雙界 data-conf-lo/hi)。"""
    v = _probe_attr(page, "data-conf-lo")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _undo_count(page):
    """可撤筆數 N(『可撤 N 筆』caption 已移除 → 改讀 P1 探針 data-undo-n;設計 §5 P1 機器讀面);找不到回 None。"""
    v = page.locator("[data-render-ms]").first.get_attribute("data-undo-n")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _press_viewer(page, vf, key):
    """對 viewer iframe 內 #osd 派真實鍵盤事件(冒泡到 document keydown;.press 會先 focus #osd,
    模擬『焦點在 viewer 上』的鍵盤工作流)。"""
    vf.locator("#osd").press(key)


def _wait_attr(page, getter, expected, timeout=15):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = getter(page)
        if last == expected:
            return True
        page.wait_for_timeout(250)
    return False


def _setup_viewer(page):
    """共用前置:app ready + 跳到第 1 張(已知有框的 lot42_frame_000)+ viewer open。"""
    _wait_app_ready(page)
    _jump_to(page, 1)
    vf = _find_viewer_frame(page)
    assert vf is not None, "主 viewer canvas frame 未出現"
    _wait_viewer_open(vf)
    return vf


# ============================== M7b-AC1 — ←/→ 鍵盤連切(不吃首鍵 + 焦點回 viewer)==============================
@pytest.mark.e2e
def test_arrow_keys_navigate(page):
    # AC1:viewer focus 後對 viewer frame keydown ArrowRight ×2,進度變 3/總(連按不吃首鍵);
    #      ArrowLeft 回 2/總。沿用 spike 命題2(不吃首鍵)+ 命題3(rerun 後焦點回 viewer)。
    vf = _setup_viewer(page)
    assert _progress_index(page) == 1, "前置應在第 1 張"

    _press_viewer(page, vf, "ArrowRight")
    assert _wait_progress(page, 2), "ArrowRight 後應到第 2 張(鍵盤 nav 未生效?nav_keys 未接)"
    # 焦點回 viewer(open handler 應 osdEl.focus();spike 命題3)— rerun 後 activeElement 仍是 #osd
    _wait_viewer_open(vf)
    active = vf.evaluate("() => document.activeElement && document.activeElement.id")
    assert active == "osd", f"切張 rerun 後焦點應回 viewer(#osd),實得 activeElement.id={active!r}(spike 命題3)"

    _press_viewer(page, vf, "ArrowRight")
    assert _wait_progress(page, 3), "連按第二次 ArrowRight 應到第 3 張(不吃首鍵;spike 命題2)"

    _press_viewer(page, vf, "ArrowLeft")
    assert _wait_progress(page, 2), "ArrowLeft 後應回第 2 張"


# ============================== M7b-AC2 — verdict 熱鍵 1/2/3(不冒名成 status/bookmark)==============================
@pytest.mark.e2e
def test_verdict_hotkeys(page):
    # AC2:按 1→verdict="true_defect"、2→"false_alarm"、3→"reflection"(讀 P1 探針 data-verdict);
    #      且 status/bookmarked 不被這些鍵改動(防把流程狀態冒名成 verdict;User-role 第1點)。
    vf = _setup_viewer(page)
    assert _verdict(page) == "unset", "前置:第 1 張 verdict 應為 unset(sidecar 隔離後)"
    st0, bk0 = _status(page), _bookmarked(page)

    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect"), "按 1 應設 verdict=true_defect"
    _press_viewer(page, vf, "2")
    assert _wait_attr(page, _verdict, "false_alarm"), "按 2 應設 verdict=false_alarm"
    _press_viewer(page, vf, "3")
    assert _wait_attr(page, _verdict, "reflection"), "按 3 應設 verdict=reflection"

    # 防冒名:1/2/3 只改 verdict,不動 review_status / bookmarked
    assert _status(page) == st0, f"verdict 熱鍵不應改 review_status({st0!r}→{_status(page)!r})"
    assert _bookmarked(page) == bk0, f"verdict 熱鍵不應改 bookmarked({bk0!r}→{_bookmarked(page)!r})"


# ============================== M7b-AC3 — r 循環 status / b toggle bookmark ==============================
@pytest.mark.e2e
def test_status_cycle_and_bookmark_toggle(page):
    # AC3:按 r → review_status 循環 none→need_review→done(→none);按 b → bookmarked toggle。
    #      r/b 是獨立鍵,不寫 verdict(讀 P1 探針 data-status / data-bookmarked)。
    vf = _setup_viewer(page)
    assert _status(page) == "none", "前置:status 應為 none"
    vd0 = _verdict(page)

    _press_viewer(page, vf, "r")
    assert _wait_attr(page, _status, "need_review"), "按 r:none→need_review"
    _press_viewer(page, vf, "r")
    assert _wait_attr(page, _status, "done"), "按 r:need_review→done"
    _press_viewer(page, vf, "r")
    assert _wait_attr(page, _status, "none"), "按 r:done→none(循環)"
    assert _verdict(page) == vd0, "r 不應改 verdict(獨立鍵)"

    bk0 = _bookmarked(page)
    _press_viewer(page, vf, "b")
    assert _wait_attr(page, _bookmarked, "0" if bk0 == "1" else "1"), "按 b 應 toggle bookmarked"
    _press_viewer(page, vf, "b")
    assert _wait_attr(page, _bookmarked, bk0), "再按 b 應 toggle 回原值"


# ============================== M7b-AC4 — 切張自動存(不按儲存,切走再回值仍在)==============================
@pytest.mark.e2e
def test_autosave_on_navigate(page):
    # AC4:在 A 圖按 1(verdict=true_defect),不按「💾儲存」,按 →切到 B 再 ←回 A,
    #      A 的 verdict 仍是 true_defect(改值即時/切張前 flush 寫入 sidecar;設計 §3.5)。
    vf = _setup_viewer(page)  # A = 第 1 張
    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect"), "A 按 1 應 verdict=true_defect"

    _press_viewer(page, vf, "ArrowRight")
    assert _wait_progress(page, 2), "應切到 B(第 2 張)"
    _wait_viewer_open(vf)
    _press_viewer(page, vf, "ArrowLeft")
    assert _wait_progress(page, 1), "應切回 A(第 1 張)"

    assert _wait_attr(page, _verdict, "true_defect"), \
        "切走再回 A,verdict 應仍是 true_defect(切張自動存,未按儲存)"


# ============================== M7b-AC5 — 改值入 undo 軌跡(可撤 N 筆遞增)==============================
@pytest.mark.e2e
def test_changes_push_undo_stack(page):
    # AC5:按 1 後 footer「可撤 N 筆」之 N +1;再按 2(同圖)N 再 +1(每次改值入 undo)。
    vf = _setup_viewer(page)
    n0 = _undo_count(page)
    assert n0 is not None, "footer 應有『可撤 N 筆』(設計 §3.6)"

    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect")
    assert _wait_attr(page, _undo_count, n0 + 1), f"按 1 後『可撤』應 {n0}→{n0 + 1}"

    _press_viewer(page, vf, "2")
    assert _wait_attr(page, _verdict, "false_alarm")
    assert _wait_attr(page, _undo_count, n0 + 2), f"再按 2 後『可撤』應 {n0 + 1}→{n0 + 2}"


# ============================== M7b-AC6 — 跨圖 undo(跳回那張 + 還原值 + toast)==============================
@pytest.mark.e2e
def test_cross_image_undo(page):
    # AC6:A 按 1(verdict true_defect,舊值 unset)→ →切到 B → 按 u:
    #      跳回 A(進度回 A 序號)+ A verdict 還原為 unset + 出現 toast(含「撤銷」)。撤銷會跳轉。
    vf = _setup_viewer(page)  # A = 第 1 張
    assert _verdict(page) == "unset", "A 前置 verdict=unset"
    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect")

    _press_viewer(page, vf, "ArrowRight")
    assert _wait_progress(page, 2), "切到 B(第 2 張)"
    _wait_viewer_open(vf)

    _press_viewer(page, vf, "u")
    # 跳回 A
    assert _wait_progress(page, 1), "按 u 應跳回 A(第 1 張)— 撤銷會跳轉(設計 §3.6)"
    # A verdict 還原
    assert _wait_attr(page, _verdict, "unset"), "按 u 應把 A 的 verdict 還原為 unset"
    # toast(含「撤銷」)— Streamlit toast 短暫出現
    try:
        page.get_by_text(re.compile("撤銷")).first.wait_for(timeout=8000)
        toast_ok = True
    except Exception:
        toast_ok = False
    assert toast_ok, "跨圖 undo 應出現含『撤銷』的 toast(設計 §3.6 / AC6)"


# ============================== M7b-AC7 — 多步 undo(遞減到 0 + 第 N+1 次 no-op)==============================
@pytest.mark.e2e
def test_multi_step_undo(page):
    # AC7:在三張不同圖各改一次(1@img1 → 2@img2 → 3@img3),連按 u ×3 每次跳回對應圖 + 還原,
    #      footer「可撤 N 筆」遞減到 0;第 4 次 u no-op(N=0、toast 含「無可撤銷」)。
    vf = _setup_viewer(page)
    base = _undo_count(page)

    _jump_to(page, 1)
    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect")
    _jump_to(page, 2)
    _wait_viewer_open(vf)
    _press_viewer(page, vf, "2")
    assert _wait_attr(page, _verdict, "false_alarm")
    _jump_to(page, 3)
    _wait_viewer_open(vf)
    _press_viewer(page, vf, "3")
    assert _wait_attr(page, _verdict, "reflection")
    assert _wait_attr(page, _undo_count, base + 3), "三次改值後『可撤』應 = base+3"

    # u#1 → 跳回 img3、還原 unset
    _press_viewer(page, vf, "u")
    assert _wait_progress(page, 3), "u#1 跳回第 3 張"
    assert _wait_attr(page, _verdict, "unset"), "u#1 還原第 3 張 verdict"
    assert _wait_attr(page, _undo_count, base + 2)
    # u#2 → 跳回 img2
    _press_viewer(page, vf, "u")
    assert _wait_progress(page, 2), "u#2 跳回第 2 張"
    assert _wait_attr(page, _verdict, "unset"), "u#2 還原第 2 張 verdict"
    assert _wait_attr(page, _undo_count, base + 1)
    # u#3 → 跳回 img1
    _press_viewer(page, vf, "u")
    assert _wait_progress(page, 1), "u#3 跳回第 1 張"
    assert _wait_attr(page, _verdict, "unset"), "u#3 還原第 1 張 verdict"
    assert _wait_attr(page, _undo_count, base), "三次 undo 後『可撤』應回到 base"

    # u#4 → no-op(空 stack):count 不變 + toast 含「無可撤銷」
    _press_viewer(page, vf, "u")
    page.wait_for_timeout(800)
    assert _undo_count(page) == base, "空 stack 再按 u 應 no-op(『可撤』不變)"
    try:
        page.get_by_text(re.compile("無可撤銷")).first.wait_for(timeout=6000)
        empty_toast = True
    except Exception:
        empty_toast = False
    assert empty_toast, "空 stack 按 u 應 toast『無可撤銷』(設計 §3.6 / §4d)"


# ============================== M7b-AC8 — 信心細微調(slider step 0.01 即時;[−]/[+] 鈕已移除)==============================
@pytest.mark.e2e
def test_conf_fine_tuning(page):
    # AC8(契約演進,User 回饋:移除信心門檻旁 [−]/[+] 鈕):只驗 footer slider step=0.01
    #     (對 slider 按一次 ArrowRight → data-conf-lo +0.01),改門檻即時反映(承接 M7a-AC5)。
    # 契約再演進(2026-07-04):slider 由單值改雙界 range slider(2 個 thumb);
    # 本測試只動下界 thumb(get_by_role("slider").first),AC-conf1..7(雙界/triage 完整覆蓋)在 test_conf_range_e2e.py。
    _wait_app_ready(page)
    _jump_to(page, 1)  # 有框圖,k 才有意義
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first

    c0 = _conf_lo(page)
    assert c0 is not None, "P1 探針應回寫 data-conf-lo(目前信心門檻下界)"

    # step=0.01:對 footer slider 下界 thumb 按一次 ArrowRight → 下界 +0.01(容差 0.005)
    slider = main.get_by_role("slider").first
    slider.wait_for(timeout=30000)
    slider.click()
    slider.press("ArrowRight")
    page.wait_for_timeout(800)
    c1 = _conf_lo(page)
    assert c1 is not None and abs((c1 - c0) - 0.01) < 0.005, \
        f"slider 單步 ArrowRight 應使下界 +0.01(step=0.01):{c0}→{c1}"

    # [−]/[+] 細調鈕已移除(User 回饋)→ 斷言它們不存在(信心微調僅留 slider)。
    plus = page.get_by_role("button", name=re.compile(r"^\s*[＋+]\s*$|\+0?\.05"))
    minus = page.get_by_role("button", name=re.compile(r"^\s*[－\-]\s*$|\-0?\.05"))
    assert plus.count() == 0 and minus.count() == 0, "信心門檻 [−]/[+] 細調鈕應已移除(User 回饋)"


# ============================== M7b-AC9 — 焦點守衛(焦點在輸入框時熱鍵不誤觸 verdict)==============================
@pytest.mark.e2e
def test_focus_guard_input_eats_keys(page):
    # AC9:點 Command Bar 跳頁 number_input 取得焦點後按 1,verdict 不變(鍵進輸入框/不誤觸熱鍵);
    #      點開 viewer 後同鍵才生效。沿用 spike 命題5 + §6『主文件輸入框天然不把鍵傳進元件 iframe』。
    vf = _setup_viewer(page)
    assert _verdict(page) == "unset", "前置 verdict=unset"

    # 焦點放到 Command Bar 跳頁框(主文件輸入框),按 1 → verdict 不該變
    sp = page.get_by_role("spinbutton").first
    sp.click()
    page.keyboard.press("1")
    page.wait_for_timeout(1000)
    assert _verdict(page) == "unset", \
        "焦點在輸入框時按 1 不應誤觸 verdict 熱鍵(焦點守衛 / 跨文件隔離;AC9)"

    # 焦點回 viewer 後同鍵才生效
    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect"), "焦點回 viewer 後按 1 才設 verdict"


# ============================== M7b-AC10 — 判定單一真相(熱鍵設值 → P1 探針反映;不依賴任何已移除的 widget)==============================
@pytest.mark.e2e
def test_verdict_single_source_of_truth(page):
    # AC10:熱鍵設 verdict 後,單一真相 = sidecar + P1 探針 data-verdict;再按熱鍵仍能改。
    # ★ 契約演進(User 回饋,跨輪):右側判定 Rail 早已移除;本輪頂列 verdict 徽章亦整條移除
    #   (資訊徽章「N/total · 判定 · 偵測N框 · 檔名」拿掉)→ 畫面不再有 verdict 文字。
    #   verdict 的單一真相落在 sidecar + P1 探針 data-verdict(設計 §5 P1 機器讀面);
    #   驗法:熱鍵 1 → 探針 data-verdict=true_defect;熱鍵 2 仍能改成 false_alarm
    #   (寫入只走 sidecar/探針,不依賴任何已移除的 Rail widget / 頂列徽章)。
    vf = _setup_viewer(page)
    _press_viewer(page, vf, "1")
    assert _wait_attr(page, _verdict, "true_defect"), \
        "熱鍵 1 後 P1 探針 data-verdict 應為 true_defect(單一真相)"
    _press_viewer(page, vf, "2")
    assert _wait_attr(page, _verdict, "false_alarm"), \
        "再按熱鍵 2 仍應改 verdict=false_alarm(寫入只走 sidecar/探針,不依賴 Rail/徽章;皆已移除)"


# ============================== M7b-AC11 — 連切 per-image 成本(PerfA,P95 < 門檻)==============================
@pytest.mark.e2e
def test_perf_per_image_nav_cost(page):
    # AC11 [效能量測] PerfA:連按 → 20 次,每次讀 P1 data-render-ms,取 P95 < 門檻(初值 1200ms,
    #      允許 PG 量實際值後 architect 校準)。驗『鍵盤連切不卡頓』的可感知體驗。
    vf = _setup_viewer(page)
    samples = []
    cur = _progress_index(page)
    for _ in range(20):
        _press_viewer(page, vf, "ArrowRight")
        nxt = min(TOTAL, (cur or 1) + 1)
        _wait_progress(page, nxt)
        cur = _progress_index(page)
        ms = _probe_attr(page, "data-render-ms")
        try:
            samples.append(float(ms))
        except (TypeError, ValueError):
            pass
        if cur == TOTAL:  # 到末張夾界,折返避免一直 no-op
            _press_viewer(page, vf, "ArrowLeft")
            _wait_progress(page, TOTAL - 1)
            cur = _progress_index(page)

    assert len(samples) >= 10, f"PerfA 應收集到足夠 render 計時樣本,實得 {len(samples)}"
    samples.sort()
    p95 = samples[min(len(samples) - 1, int(round(0.95 * (len(samples) - 1))))]
    assert p95 < 1200.0, (
        f"連切 per-image render P95={p95:.0f}ms 應 < 1200ms(設計 PerfA 初值;"
        "超標 → PG 量實際後交 architect 校準門檻,非就地放寬)")


# ============================== 推導測試(PM 自加,非逐字抄 AC)——undo 是 verdict 的『真逆元』==============================
@pytest.mark.e2e
def test_undo_is_inverse_metamorphic(page):
    # 不變量(metamorphic):對任一串 verdict 改值,做『等量 undo』後,每張被動過的圖 verdict
    # 必回到原始 baseline,且『可撤 N 筆』回到起始值。即 change∘undo = identity(verdict 狀態)。
    # 這條設計沒明列,用來逼出『undo 還原成 new 而非 old』『undo 不跳轉/跳錯圖』『count 不對稱』等實作 bug。
    vf = _setup_viewer(page)
    base_count = _undo_count(page)

    # baseline:三張圖目前 verdict(sidecar 隔離後應皆 unset)
    baseline = {}
    for n in (1, 2, 3):
        _jump_to(page, n)
        _wait_viewer_open(vf)
        baseline[n] = _verdict(page)

    # 施加 3 次改值(每張一次,值各異)
    seq = {1: ("1", "true_defect"), 2: ("2", "false_alarm"), 3: ("3", "reflection")}
    for n, (key, expect) in seq.items():
        _jump_to(page, n)
        _wait_viewer_open(vf)
        _press_viewer(page, vf, key)
        assert _wait_attr(page, _verdict, expect), f"第 {n} 張按 {key} 應 verdict={expect}"
    assert _wait_attr(page, _undo_count, base_count + 3), "三次改值後 count=base+3"

    # 等量 undo ×3
    for _ in range(3):
        _press_viewer(page, vf, "u")
        page.wait_for_timeout(600)

    # 不變量:count 回到 base;每張 verdict 回 baseline
    assert _wait_attr(page, _undo_count, base_count), "等量 undo 後『可撤』應回到起始值(對稱)"
    for n in (1, 2, 3):
        _jump_to(page, n)
        _wait_viewer_open(vf)
        assert _verdict(page) == baseline[n], (
            f"change∘undo 應為 identity:第 {n} 張 verdict 應回 baseline {baseline[n]!r},"
            f"實得 {_verdict(page)!r}(undo 還原成 old 而非 new?)")
