"""比較模式 = 兩圖疊圖比較 的真實 E2E 驗收(對應設計 23_compare.md §9,第四輪取代)。

User 第四輪裁決(取代第三輪的雙 model 覆蓋 triage):不再需要第二個資料夾,改成在主縮圖牆
每張縮圖左下角標記兩張影像(①藍/②橘,最多同時 2 張,FIFO 踢掉最舊)。標記滿 2 張後開啟
「🔀 比較模式」,可切換「像素疊合」(並排/差異/混合,重用 framecompare)或「偵測框疊合」
(各自的偵測框疊在一起,A 藍/B 橘)。

機器讀:沿設計 §5 P1 探針(主文件 DOM)新增 data-cmp-marks-n(0/1/2,不論 compare_on 皆回寫)、
data-cmp-view-mode(pixel/box,僅 compare_on 且已標記 2 張時有值)。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_compare_e2e.py -m e2e -v
比較預設 0 標記 + OFF → 既有 M7a/M7b/viewer_ux/app_e2e 回歸不受影響。
"""
import re
import time

import pytest

APP_TITLE = "YOLO Image Viewer"


def _wait_app_ready(page):
    # conftest 的 page fixture 未指定 viewport(預設 1280x720);縮圖牆縱向排列 8 張縮圖,
    # 較窄的預設高度下第 2/3 張的 .cmpmark 落在需要捲動才可見的範圍,點擊不穩定(實測重現)。
    # 加大 viewport 讓整排縮圖(至少前幾張)不需捲動即可見可點,同 test_rwd_e2e.py 慣例
    # (各檔自行呼叫 set_viewport_size,不動 conftest 的預設)。
    page.set_viewport_size({"width": 1400, "height": 1000})
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name=re.compile(r"下一張")).first.wait_for(timeout=60000)
    page.wait_for_timeout(1500)


def _find_viewer_frame(page, timeout=30):
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


def _find_thumbwall_frame(page, min_imgs=2, timeout=30):
    """回傳含『多張 img、且無 canvas』的 iframe(縮圖牆);找不到回 None。
    同 test_viewer_ux_e2e.py 慣例:排除主文件,避免誤選其他 st.image。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in page.frames:
            try:
                if (f is not page.main_frame and f.locator("canvas").count() == 0
                        and f.locator("img").count() >= min_imgs):
                    return f
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def _probe_int(page, attr):
    v = page.locator("[data-render-ms]").first.get_attribute(attr)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _probe_str(page, attr):
    return page.locator("[data-render-ms]").first.get_attribute(attr)


def _toggle_compare(page):
    # st.toggle 渲染在 stCheckbox testid 下;點文字 label 不會切換,需點 stCheckbox 控制本體。
    # 一次點擊觸發兩輪 rerun(component 值變動的自動 rerun + _toggle_cmp_mark 的顯式 rerun),
    # 需比單純 widget 點擊更寬裕的等待時間才會穩定。
    page.locator('[data-testid="stCheckbox"]').filter(has_text="比較模式").first.click()
    page.wait_for_timeout(1200)


def _mark_cell(tf, index):
    """點第 index 張縮圖左下角的疊圖比較標記圖示(.cmpmark),不是整張縮圖(避免誤觸導覽)。"""
    tf.locator(".cmpmark").nth(index).click()


def _mark_two_images(page, tf, i=0, j=1):
    """標記兩張影像(index i、j),等 marks-n 變 2。每次標記觸發兩輪 rerun(見 _toggle_compare
    註解),需給足夠等待時間才會穩定反映在 P1 探針。"""
    _mark_cell(tf, i)
    page.wait_for_timeout(1200)
    _mark_cell(tf, j)
    page.wait_for_timeout(1200)


# ============================== AC1 — 標記 <2 張時的提示 ==============================
@pytest.mark.e2e
def test_compare_prompts_when_less_than_two_marked(page):
    _wait_app_ready(page)
    assert _probe_int(page, "data-cmp-marks-n") == 0, "初始應無任何標記"

    tf = _find_thumbwall_frame(page)
    assert tf is not None, "縮圖牆 iframe 未出現"
    _mark_cell(tf, 0)
    page.wait_for_timeout(1200)
    assert _probe_int(page, "data-cmp-marks-n") == 1, "標記 1 張後 marks-n 應為 1"

    _toggle_compare(page)
    assert page.get_by_text(re.compile(r"請在左側縮圖牆")).count() > 0, \
        "標記未滿 2 張時,開比較模式應提示『請在左側縮圖牆…』,不崩、不顯示假疊圖"
    assert page.get_by_text(re.compile(r"1/2")).count() > 0, "提示應反映目前已標記數(1/2)"


# ============================== AC2 — 標記兩張 + FIFO ==============================
@pytest.mark.e2e
def test_mark_two_images_and_fifo_replace(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page)
    assert tf is not None

    _mark_two_images(page, tf, 0, 1)
    assert _probe_int(page, "data-cmp-marks-n") == 2, "標記兩張後 marks-n 應為 2"

    # 再標記第 3 張 → FIFO 踢掉最舊一張,marks-n 仍為 2(不會變 3)
    _mark_cell(tf, 2)
    page.wait_for_timeout(1200)
    assert _probe_int(page, "data-cmp-marks-n") == 2, \
        "標記第 3 張後應 FIFO 踢掉最舊一張,marks-n 仍應為 2(不會累積成 3)"


# ============================== AC3 — 疊圖比較視圖(像素/偵測框可切換)==============================
@pytest.mark.e2e
def test_overlay_view_switches_pixel_and_box(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page)
    assert tf is not None
    _mark_two_images(page, tf, 0, 1)
    assert _probe_int(page, "data-cmp-marks-n") == 2

    _toggle_compare(page)
    page.wait_for_timeout(1200)
    assert _probe_str(page, "data-cmp-view-mode") == "pixel", "標記滿 2 張後預設應為像素疊合(pixel)"
    assert page.get_by_text(re.compile(r"檢視方式")).count() > 0, "應有『檢視方式』下拉"
    assert page.get_by_text(re.compile(r"疊合方式")).count() > 0, "像素疊合下應有『疊合方式』下拉"

    sb = page.locator('[data-testid="stSelectbox"]').filter(has_text="檢視方式")
    sb.click()
    page.wait_for_timeout(200)
    page.get_by_role("option", name=re.compile("偵測框疊合")).first.click()
    page.wait_for_timeout(1200)
    assert _probe_str(page, "data-cmp-view-mode") == "box", "切到偵測框疊合後 view-mode 應變 box"
    assert page.get_by_text(re.compile(r"信心範圍")).count() > 0, "偵測框疊合下應沿用信心範圍雙界"
    assert page.get_by_text(re.compile(r"Object 類別")).count() > 0, "偵測框疊合下應沿用 Object 類別"


# ============================== AC4 — 像素疊合三種疊合方式皆可正常顯示 ==============================
@pytest.mark.e2e
def test_pixel_modes_side_diff_blend(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page)
    assert tf is not None
    _mark_two_images(page, tf, 0, 1)
    _toggle_compare(page)
    page.wait_for_timeout(1200)

    pm = page.locator('[data-testid="stSelectbox"]').filter(has_text="疊合方式")
    assert pm.count() > 0, "像素疊合下應有『疊合方式』下拉"

    for label in ("並排", "差異", "混合"):
        pm.click()
        page.wait_for_timeout(200)
        page.get_by_role("option", name=re.compile(label)).first.click()
        page.wait_for_timeout(1200)
        # 不 raise、不顯示例外 traceback 文字(st.image 正常渲染)
        assert page.get_by_text(re.compile("Traceback")).count() == 0, \
            f"疊合方式『{label}』不應崩潰(頁面出現 Traceback)"

    # 混合模式應多一顆 alpha slider
    assert page.get_by_text(re.compile(r"混合比例")).count() > 0, "混合模式下應有『混合比例』slider"


# ============================== AC5 — 標記動作不影響單張導覽(stopPropagation)==============================
@pytest.mark.e2e
def test_mark_click_does_not_trigger_navigation(page):
    _wait_app_ready(page)
    idx_before = _probe_int(page, "data-idx")
    tf = _find_thumbwall_frame(page)
    assert tf is not None

    _mark_cell(tf, 2)  # 點第 3 張的標記圖示(非目前顯示的第 1 張)
    page.wait_for_timeout(1200)
    idx_after = _probe_int(page, "data-idx")
    assert idx_after == idx_before, (
        f"點縮圖左下角『標記』圖示不應觸發整格的選取/導覽(data-idx 不應改變);"
        f"實得 before={idx_before} after={idx_after}"
    )
    assert _probe_int(page, "data-cmp-marks-n") == 1, "標記應確實生效(marks-n=1)"


# ============================== AC6 — 清除標記 ==============================
@pytest.mark.e2e
def test_clear_marks_button(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page)
    assert tf is not None
    _mark_two_images(page, tf, 0, 1)
    _toggle_compare(page)
    page.wait_for_timeout(1200)

    btn = page.get_by_role("button", name=re.compile("清除標記"))
    assert btn.count() > 0, "疊圖比較視圖應有『清除標記』鈕"
    btn.first.click()
    page.wait_for_timeout(1200)
    assert _probe_int(page, "data-cmp-marks-n") == 0, "點清除標記後 marks-n 應回 0"
    assert page.get_by_text(re.compile(r"請在左側縮圖牆")).count() > 0, \
        "清除標記後應回到『請標記兩張影像』提示狀態"


# ============================== AC7 — 向後相容(預設 0 標記 + OFF 不破壞既有版面)==============================
@pytest.mark.e2e
def test_backward_compatible_default_state(page):
    _wait_app_ready(page)
    assert page.get_by_role("button", name=re.compile(r"上一張")).count() > 0, "預設應有『上一張』鈕"
    assert page.get_by_role("button", name=re.compile(r"下一張")).count() > 0, "預設應有『下一張』鈕"
    assert _find_viewer_frame(page) is not None, "預設(比較 OFF)應有單一 viewer canvas"
    assert _probe_int(page, "data-cmp-marks-n") == 0, "預設不應有任何標記"
    assert page.get_by_text(re.compile(r"第二個 model")).count() == 0, \
        "舊版『第二個 model 資料夾』欄位應已移除(改成標記式比較,不再需要第二個資料夾)"


# ============================== AC8 — 標記圖示存在且可辨識 ==============================
@pytest.mark.e2e
def test_cmpmark_icons_present_on_thumbwall(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page, min_imgs=2)
    assert tf is not None, "縮圖牆 iframe 未出現"
    n_imgs = tf.locator("img").count()
    n_marks = tf.locator(".cmpmark").count()
    assert n_marks == n_imgs, (
        f"每張縮圖都應有一個疊圖比較標記圖示(.cmpmark),數量應與縮圖數一致;"
        f"實得 imgs={n_imgs} marks={n_marks}"
    )
