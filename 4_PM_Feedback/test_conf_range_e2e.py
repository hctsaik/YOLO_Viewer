"""信心門檻雙界 + 縮圖牆 triage 的真實 E2E 驗收(單張檢視模式)。

對應設計 `3_Architect_Design/20_viewer_workbench_redesign.md` §7
「設計演進(2026-07-04,User 回饋:信心門檻要卡縮圖牆、且要雙邊)」的 AC-conf1..7。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_conf_range_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
conftest 的 app_server 會自動起 streamlit run 5_PG_Develop/app.py;page fixture 已開好瀏覽器。

樣本集 conf 分布(git-tracked、非 make_samples.py 產生,見設計文件逐字釘死):
  lot42_frame_000: conf = {0.91(scratch), 0.62(dent), 0.40(edge)}
  lot42_frame_001: conf = {0.77(scratch)}
  其餘 6 張(lot42_frame_002/003/004、wafer16_000/001/002): 0 偵測
  TOTAL_ALL = 8(資料夾總圖數)

TDD 提醒:本檔對應的實作(footer_conf_thr 由 float 改 tuple、_passes 加 _in_conf_range triage、
kept 改雙界內嵌過濾、P1 探針 data-conf 拆成 data-conf-lo/hi)PG 尚未完成,故本檔現在預期『紅』是正常的。
"""
import time

import pytest

APP_TITLE = "YOLO Image Viewer"
TOTAL_ALL = 8


# ============================== 共用定位 helper(沿用既有 M7 系列範式)==============================
def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name="下一張 ⟶").first.wait_for(timeout=60000)


def _probe(page):
    el = page.locator("[data-render-ms]").first
    el.wait_for(state="attached", timeout=30000)
    return el


def _probe_attr(page, attr):
    return _probe(page).get_attribute(attr)


def _total(page):
    v = _probe_attr(page, "data-total")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _shown_k(page):
    v = _probe_attr(page, "data-shown-k")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _shown_n(page):
    v = _probe_attr(page, "data-shown-n")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _conf_lo(page):
    v = _probe_attr(page, "data-conf-lo")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _conf_hi(page):
    v = _probe_attr(page, "data-conf-hi")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _conf_thumbs(page):
    """Command Bar 信心門檻的 slider thumb(main、非 sidebar)。"""
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    return main.get_by_role("slider")


def _aria_val(thumb):
    v = thumb.get_attribute("aria-valuenow")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _step_thumb_to(thumb, target, deadline_s=150):
    """把單一 thumb 逼近到 target(step=0.01)。逐鍵『按一下→等一輪 rerun 沉澱→重讀當下值』,
    不連按(實測連按會被 server 忙時的 rerun 吃掉部分按鍵,同 ROADMAP 2026-06-26 m7a-AC5
    『60 次快速 ArrowRight』flaky 根因;本 helper 需要落在精確數值〔AC-conf* 釘死的 conf 邊界〕,
    不能像該處只驗『方向有變』,故改逐步收斂、每步等沉澱,寧可慢一點也要準。"""
    thumb.click()
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        cur = _aria_val(thumb)
        if cur is not None and abs(cur - target) < 0.005:
            return
        if cur is None:
            thumb.click()
            time.sleep(0.3)
            continue
        thumb.press("ArrowRight" if target > cur else "ArrowLeft")
        time.sleep(0.6)  # 等這一鍵的 rerun 沉澱,再讀值/按下一鍵(避免連按被吃掉)。
    raise AssertionError(f"slider 逼近逾時:目標={target},卡在={_aria_val(thumb)}")


def _set_conf_range(page, lo, hi):
    """把信心門檻 range slider 設到 (lo, hi)(step=0.01)。

    不用 Home/End(實測此元件的兩個鍵無作用,只有 ArrowLeft/Right 生效 —— 本 helper 撰寫時
    先用 Home/End 踩到這個坑:第一次呼叫因起始值恰好等於一端而巧合通過,第二次呼叫〔把範圍
    從窄區間拉回全開〕才暴露 Home 其實不動)。**先做「拉寬」方向(lo 下降 / hi 上升,任何時候
    都安全)、才做「拉窄」方向(lo 上升 / hi 下降)**,避免中途因 lo>hi 被 range slider 互卡。"""
    thumbs = _conf_thumbs(page)
    lo_thumb, hi_thumb = thumbs.first, thumbs.nth(1)
    cur_lo, cur_hi = _aria_val(lo_thumb), _aria_val(hi_thumb)
    assert cur_lo is not None and cur_hi is not None, "讀不到 slider 當前 aria-valuenow"

    if lo < cur_lo:
        _step_thumb_to(lo_thumb, lo)
        cur_lo = lo
    if hi > cur_hi:
        _step_thumb_to(hi_thumb, hi)
        cur_hi = hi
    if lo > cur_lo:
        _step_thumb_to(lo_thumb, lo)
    if hi < cur_hi:
        _step_thumb_to(hi_thumb, hi)


# ============================== AC-conf1 — range slider(2 個 thumb)==============================
@pytest.mark.e2e
def test_conf_slider_is_range_with_two_thumbs(page):
    _wait_app_ready(page)
    assert _conf_thumbs(page).count() == 2, \
        "信心門檻應為雙滑塊 range slider(2 個 role=slider thumb),而非單一滑塊"


# ============================== AC-conf2 — 全開時不 triage(向後相容關閉點)==============================
@pytest.mark.e2e
def test_full_open_range_does_not_triage(page):
    _wait_app_ready(page)
    # 預設即全開 (0.00, 1.00);不主動設定,驗證『開箱』狀態就等於現狀(不 triage)。
    assert _conf_lo(page) == 0.0 and _conf_hi(page) == 1.0, \
        "footer_conf_thr 預設應為全開 (0.0, 1.0)"
    assert _total(page) == TOTAL_ALL, \
        f"全開時 data-total 應等於資料夾總圖數 {TOTAL_ALL}(含 0 偵測圖,向後相容、不得回歸)"


# ============================== AC-conf3 — 下界隔離:排除 conf 較低的有框圖 + 全部 0 框圖 ==============================
@pytest.mark.e2e
def test_lower_bound_triages_list(page):
    _wait_app_ready(page)
    _set_conf_range(page, 0.80, 1.00)
    assert _total(page) == 1, (
        "lo=0.80,hi=1.00:僅 lot42_frame_000(conf 0.91)滿足;"
        "lot42_frame_001(0.77<0.80)與全部 0 偵測圖應被排除"
    )


# ============================== AC-conf4 — 上界隔離:與 AC-conf3 排除不同的圖,證明非巧合 ==============================
@pytest.mark.e2e
def test_upper_bound_triages_list(page):
    _wait_app_ready(page)
    _set_conf_range(page, 0.65, 0.80)
    assert _total(page) == 1, (
        "lo=0.65,hi=0.80:僅 lot42_frame_001(conf 0.77)滿足;"
        "lot42_frame_000 的 0.40/0.62/0.91 皆落在此區間外,應被排除"
    )


# ============================== AC-conf5 — 篩空邊界:警告 + slider 仍可操作脫困(防卡死)==============================
@pytest.mark.e2e
def test_empty_range_warns_and_slider_recoverable(page):
    _wait_app_ready(page)
    _set_conf_range(page, 0.95, 1.00)  # 高於樣本集最大 conf 0.91 → 篩空
    page.get_by_text("沒有符合篩選條件的影像").first.wait_for(timeout=15000)

    # 防卡死(設計 §4k):slider 仍在畫面上、仍可操作 —— 拉回全開應能脫困、清單恢復非空。
    assert _conf_thumbs(page).count() == 2, \
        "清單篩空後信心 slider 不應從畫面消失(否則使用者無法拉寬回去,卡死)"
    _set_conf_range(page, 0.0, 1.0)
    assert _total(page) == TOTAL_ALL, "拉回全開後應恢復 data-total == 8(使用者可自行脫困)"


# ============================== AC-conf6 — P1 探針型別(data-conf-lo/hi 皆可解析為 float)==============================
@pytest.mark.e2e
def test_conf_probe_types(page):
    _wait_app_ready(page)
    assert _conf_lo(page) is not None and _conf_hi(page) is not None, \
        "P1 探針應同時回寫 data-conf-lo 與 data-conf-hi"
    _set_conf_range(page, 0.30, 0.90)
    assert abs(_conf_lo(page) - 0.30) < 0.005 and abs(_conf_hi(page) - 0.90) < 0.005, \
        "調整 slider 後 data-conf-lo/hi 應反映新設定值"


# ============================== AC-conf7 — 主圖疊框雙界(與清單 triage 各自獨立驗證)==============================
@pytest.mark.e2e
def test_main_view_overlay_upper_bound(page):
    _wait_app_ready(page)
    # lo=0.00,hi=0.50:僅 lot42_frame_000 的 0.40 落在區間內 → 清單只剩它一張(index 0 = 第1張)。
    _set_conf_range(page, 0.00, 0.50)
    assert _total(page) == 1, "lo=0,hi=0.50:清單應只剩 lot42_frame_000(唯一含 conf<=0.50 偵測的圖)"
    assert _shown_n(page) == 3, "lot42_frame_000 總偵測數應為 3(0.40/0.62/0.91)"
    assert _shown_k(page) == 1, (
        "上界 0.50 應濾掉 0.62 與 0.91,只留 0.40 → data-shown-k == 1"
        "(證明 kept 的雙界對主圖疊框生效,與清單層級 triage 是兩個獨立機制)"
    )
