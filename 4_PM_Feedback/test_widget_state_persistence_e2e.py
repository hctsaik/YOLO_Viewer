"""Command Bar / 縮圖牆控制在導覽/收合互動後不遺失狀態的真實 E2E 驗收。

背景(User 回報「filter 切下一張就不見了」,2026-07-04,嚴重問題):Streamlit 對『本輪指令碼
執行完畢前都沒被實例化』的 keyed widget 會清掉其 session_state(孤兒 widget 狀態清理)。
Command Bar 的信心門檻 slider(`footer_conf_thr`)、Object 類別下拉(`cls_filter`)原本排在
⟵/⟶/跳頁/⭐ 按鈕**之後**才實例化;縮圖牆的「排序」下拉(`sort_mode`)原本包在
`if not ss.thumb_collapsed:` 內,收合期間整輪都不會被呼叫。這些按鈕/收合動作都會呼叫
`st.rerun()`,導致上述 widget 在按鈕觸發的那一輪『來不及被實例化』就結束 → 下一輪其值被清空、
打回預設(信心門檻回全開、Object 類別回「全部」、排序回「檔名」)。

修法(見 5_PG_Develop/app.py Command Bar / 縮圖牆區塊註解):讓 `footer_conf_thr`/`cls_filter`
在任何可能呼叫 `st.rerun()` 的按鈕**之前**實例化;讓 `sort_mode` **恆渲染、不隨收合狀態條件式跳過**。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_widget_state_persistence_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
"""
import re
import time

import pytest

APP_TITLE = "YOLO Image Viewer"


def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name=re.compile(r"下一張")).first.wait_for(timeout=60000)


def _probe_attr(page, attr):
    el = page.locator("[data-render-ms]").first
    el.wait_for(state="attached", timeout=30000)
    return el.get_attribute(attr)


def _conf_thumbs(page):
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    return main.get_by_role("slider")


def _aria_val(thumb):
    v = thumb.get_attribute("aria-valuenow")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _step_thumb_to(thumb, target, deadline_s=90):
    """單鍵逼近(不連按,避免 server 忙時 rerun 吃鍵;同 test_conf_range_e2e.py 慣例)。"""
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
        time.sleep(0.6)
    raise AssertionError(f"slider 逼近逾時:目標={target},卡在={_aria_val(thumb)}")


# ============================== 信心門檻:切下一張後不重置 ==============================
@pytest.mark.e2e
def test_confidence_range_survives_next_image_click(page):
    _wait_app_ready(page)
    lo_thumb = _conf_thumbs(page).first
    _step_thumb_to(lo_thumb, 0.20)
    assert abs(float(_probe_attr(page, "data-conf-lo")) - 0.20) < 0.01, \
        "設定下界後應立即反映 0.20"

    page.get_by_role("button", name=re.compile(r"下一張")).first.click()
    page.wait_for_timeout(900)
    conf_after = float(_probe_attr(page, "data-conf-lo"))
    assert abs(conf_after - 0.20) < 0.01, (
        f"切下一張後信心門檻下界不應被重置(bug:Streamlit 對『本輪未實例化』的 keyed widget "
        f"會清空其 session_state,若 slider 排在 nav 按鈕之後就會被打回全開 0.0);"
        f"實得 {conf_after}"
    )


# ============================== Object 類別下拉:切下一張後不重置 ==============================
@pytest.mark.e2e
def test_class_filter_survives_next_image_click(page):
    _wait_app_ready(page)
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    jump = page.get_by_role("spinbutton").first
    jump.fill("1")
    jump.press("Enter")
    page.wait_for_timeout(600)

    cls_sel = main.locator("[data-testid='stSelectbox']").filter(has_text="Object").first
    cls_sel.click()
    page.wait_for_timeout(300)
    page.get_by_role("option", name="dent").click()
    page.wait_for_timeout(600)
    assert "dent" in cls_sel.inner_text(), "選取 dent 後下拉應顯示 dent"

    page.get_by_role("button", name=re.compile(r"下一張")).first.click()
    page.wait_for_timeout(900)
    cls_after = cls_sel.inner_text()
    assert "dent" in cls_after, (
        f"切下一張後 Object 類別篩選不應被重置(同一 widget-cleanup 成因);實得下拉顯示:{cls_after!r}"
    )


# ============================== 排序下拉:收合/展開縮圖牆後不重置 ==============================
@pytest.mark.e2e
def test_sort_mode_survives_thumbnail_collapse_toggle(page):
    _wait_app_ready(page)
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    sort_sel = main.locator("[data-testid='stSelectbox']").filter(has_text="排序").first
    sort_sel.click()
    page.wait_for_timeout(300)
    page.get_by_role("option", name="信心(高→低)").click()
    page.wait_for_timeout(600)
    assert "信心" in sort_sel.inner_text(), "選取排序後下拉應顯示信心(高→低)"

    page.get_by_role("button", name=re.compile(r"收合縮圖")).first.click()
    page.wait_for_timeout(800)
    page.get_by_role("button", name=re.compile(r"展開縮圖")).first.click()
    page.wait_for_timeout(800)

    sort_after = main.locator("[data-testid='stSelectbox']").filter(has_text="排序").first.inner_text()
    assert "信心" in sort_after, (
        f"收合再展開縮圖牆後排序選擇不應被重置(sort_mode 原本包在 `if not ss.thumb_collapsed:` "
        f"內,收合期間整輪不被實例化 → 同一 widget-cleanup 成因被清空);實得:{sort_after!r}"
    )
