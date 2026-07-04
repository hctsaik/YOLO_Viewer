"""窄視窗 RWD 的真實 E2E 驗收(2026-07-04,User 回報「這個圖並不是完整的,應該要做好 RWD」)。

背景:M7c 設計(20_viewer_workbench_redesign.md §3.11)規劃過 RWD 斷點但從未實作。實測(用真實
1254×1254 無標註影像資料集)發現:Streamlit sidebar 用 inline style 固定 `width:300px`,與 viewport
寬度無關,窄窗下佔掉不成比例的空間、把縮圖牆/主 viewer 一起擠小。修法為純 CSS media query
(`!important` 蓋掉 inline style,見 app.py RWD 區塊),不涉 Python/JS round-trip。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_rwd_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
"""
import pytest

APP_TITLE = "YOLO Image Viewer"


def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)


@pytest.mark.e2e
def test_sidebar_narrows_at_narrow_viewport(page):
    _wait_app_ready(page)
    sidebar = page.locator("[data-testid='stSidebar']").first

    page.set_viewport_size({"width": 1920, "height": 1080})
    page.wait_for_timeout(300)
    w_wide = sidebar.bounding_box()["width"]
    assert w_wide >= 280, f"寬視窗(1920px)下 sidebar 應維持 Streamlit 預設寬度,實得 {w_wide}"

    page.set_viewport_size({"width": 1000, "height": 800})
    page.wait_for_timeout(300)
    w_medium = sidebar.bounding_box()["width"]
    assert w_medium <= 230, (
        f"視窗縮到 1000px(≤1100px 斷點)後 sidebar 應收窄(設計 220px),"
        f"不應仍固定佔 300px 不成比例的空間;實得 {w_medium}"
    )

    page.set_viewport_size({"width": 700, "height": 800})
    page.wait_for_timeout(300)
    w_narrow = sidebar.bounding_box()["width"]
    assert w_narrow <= 230, (
        f"視窗縮到 700px(≤760px 斷點)後 sidebar 應更窄(設計 160px,此寬度以下 Streamlit "
        f"原生行為也可能介入把它收得更窄);實得 {w_narrow}"
    )
    assert w_narrow <= w_medium, (
        f"視窗越窄,sidebar 應越窄或至少不變寬(單調不遞增);"
        f"1000px→{w_medium}, 700px→{w_narrow}"
    )
