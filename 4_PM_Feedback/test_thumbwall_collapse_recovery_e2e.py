"""縮圖牆收合/展開的真實 E2E 驗收(2026-07-04,User 回報「收合後再也展開不回來」+
「版面跑掉,文字變直排」,嚴重問題)。

背景:收合/排序/符合張數三個控制項原本跟縮圖格一起放在同一個 `left` 欄,而 `left` 欄寬
被 `_left_w=0.0001` 擠到近乎 0——連控制項本身都被擠壞(實測:收合後「展開縮圖」鈕
`bounding_box().width == 0`、`is_visible() == False`,真的卡死不是誤會)。
修法:控制項獨立放進一組**不隨收合狀態變窄**的欄(見 5_PG_Develop/app.py Stage 區塊)。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_thumbwall_collapse_recovery_e2e.py -m e2e -v
"""
import re

import pytest

APP_TITLE = "YOLO Image Viewer"


def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)


# ============================== 收合後「展開縮圖」鈕仍可點擊(防卡死)==============================
@pytest.mark.e2e
def test_expand_button_remains_clickable_after_collapse(page):
    _wait_app_ready(page)
    collapse_btn = page.get_by_text("收合縮圖", exact=False).first
    collapse_btn.wait_for(timeout=30000)
    collapse_btn.click()
    page.wait_for_timeout(1000)

    expand_btn = page.get_by_text("展開縮圖", exact=False).first
    expand_btn.wait_for(timeout=15000)
    box = expand_btn.bounding_box()
    assert box is not None and box["width"] > 20, (
        f"收合後「展開縮圖」鈕應仍有真實可點擊寬度(bug:曾被擠到 width=0、"
        f"is_visible=False,使用者永遠展開不回來);實得 {box}"
    )
    assert expand_btn.is_visible(), "收合後「展開縮圖」鈕應仍可見"

    # 實際點擊驗證真的能展開回去(不只是「看起來」可點)。
    expand_btn.click()
    page.wait_for_timeout(1000)
    assert page.get_by_text("收合縮圖", exact=False).count() > 0, \
        "點擊「展開縮圖」後應恢復展開狀態(按鈕文字變回「收合縮圖」)"


# ============================== 收合狀態下排序/符合張數不得版面錯亂 ==============================
@pytest.mark.e2e
def test_controls_not_corrupted_when_collapsed(page):
    _wait_app_ready(page)
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    collapse_btn = page.get_by_text("收合縮圖", exact=False).first
    collapse_btn.click()
    page.wait_for_timeout(1000)

    sort_sel = main.locator("[data-testid='stSelectbox']").filter(has_text="排序").first
    sort_sel.wait_for(timeout=15000)
    box = sort_sel.bounding_box()
    assert box is not None and box["width"] > 40, (
        f"收合狀態下「排序」下拉不應被擠到近乎 0 寬(版面錯亂/文字直排的成因);實得 {box}"
    )


# ============================== 排序選擇跨越收合/展開週期不遺失 ==============================
@pytest.mark.e2e
def test_sort_mode_survives_collapse_cycle(page):
    _wait_app_ready(page)
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    sort_sel = main.locator("[data-testid='stSelectbox']").filter(has_text="排序").first
    sort_sel.click()
    page.wait_for_timeout(300)
    page.get_by_role("option", name="信心(高→低)").click()
    page.wait_for_timeout(600)

    page.get_by_text("收合縮圖", exact=False).first.click()
    page.wait_for_timeout(800)
    page.get_by_text("展開縮圖", exact=False).first.click()
    page.wait_for_timeout(800)

    sort_sel2 = main.locator("[data-testid='stSelectbox']").filter(has_text="排序").first
    assert "信心" in sort_sel2.inner_text(), \
        f"收合再展開後排序選擇不應被重置為預設;實得 {sort_sel2.inner_text()!r}"
