"""比較模式 = 雙 model 覆蓋比對 的真實 E2E 驗收(對應設計 24_modeldiff.md + 23_compare.md §8)。

User 第三輪裁決(取代舊 image-vs-image diff/混合):A/B = 兩個 model 對【同一包影像】的結果;
信心/類別/分歧 filter 對【整個影像集】做 triage(濾掉整張圖);IoU 框級配對;
主視圖 = 覆蓋率儀表板 + 分歧 triage 佇列(橫向縮圖條)+ 下鑽雙色疊框(A 藍 / B 橘);
『B 缺檔(打錯路徑/沒輸出)』與『有檔但 0 框』分成 missing_b / both_empty(防假冒覆蓋差異)。

機器讀:沿設計 §5 P1 探針(主文件 DOM)新增 data-cmp-queue-n / only-a / only-b / missing-b / delta-imgs,
用穩定數字斷言而非脆弱像素。E2E fixture:sample_images/model_b/(較弱 model B,只逮 frame_000 1 框、漏 frame_001)。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_compare_e2e.py -m e2e -v
比較預設 OFF → 既有 M7a/M7b/viewer_ux/app_e2e 回歸不受影響。
"""
import os
import re
import time

import pytest

APP_TITLE = "YOLO Image Viewer"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_B = os.path.join(ROOT, "sample_images", "model_b")  # 較弱 model B 的標註夾


def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name=re.compile(r"下一張")).first.wait_for(timeout=60000)


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


def _thumbwall_frames(page, timeout=30):
    """比較佇列的橫向縮圖條 iframe(非主文件、無 canvas、img≥1)。"""
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        last = [f for f in page.frames if f is not page.main_frame
                and _safe(f, "canvas") == 0 and _safe(f, "img") >= 1]
        if last:
            return last
        page.wait_for_timeout(500)
    return last


def _safe(frame, sel):
    try:
        return frame.locator(sel).count()
    except Exception:
        return 0


def _probe_int(page, attr):
    v = page.locator("[data-render-ms]").first.get_attribute(attr)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _toggle_compare(page):
    # st.toggle 渲染在 stCheckbox testid 下;點文字 label 不會切換,需點 stCheckbox 控制本體。
    page.locator('[data-testid="stCheckbox"]').filter(has_text="比較模式").first.click()
    page.wait_for_timeout(500)


def _set_model_b(page, path):
    tb = page.locator('[data-testid="stTextInput"]').filter(has_text="第二個 model").locator("input")
    tb.fill(path)
    tb.press("Enter")
    page.wait_for_timeout(900)


def _enter_model_compare(page):
    """設 model B + 開比較模式,等覆蓋率儀表板出現。"""
    _set_model_b(page, MODEL_B)
    _toggle_compare(page)
    page.get_by_text(re.compile("覆蓋率彙總")).first.wait_for(timeout=30000)


# ============================== AC1 — 進入/離開雙 model 比較 ==============================
@pytest.mark.e2e
def test_enter_exit_model_compare(page):
    _wait_app_ready(page)
    assert _find_viewer_frame(page) is not None, "比較 OFF 時應有單一 viewer canvas"
    _enter_model_compare(page)
    assert page.get_by_text(re.compile("覆蓋率彙總")).count() > 0, "比較模式應有『覆蓋率彙總』儀表板"
    _toggle_compare(page)
    page.wait_for_timeout(800)
    assert page.get_by_text(re.compile("覆蓋率彙總")).count() == 0, "取消比較後儀表板應消失"
    assert _find_viewer_frame(page) is not None, "取消比較後單一 viewer canvas 應回來"


# ============================== AC2 — 覆蓋率儀表板(弱 model 逮的更少)==============================
@pytest.mark.e2e
def test_coverage_dashboard_shows_b_caught_less(page):
    _wait_app_ready(page)
    _enter_model_compare(page)
    # 儀表板量化『B 比 A 少』
    assert page.get_by_text(re.compile(r"B 比 A 少")).count() > 0, "儀表板應量化『B 比 A 少 N 張/框』"
    # model B(只逮 frame_000)覆蓋比 A 少 → delta_imgs >= 1
    di = _probe_int(page, "data-cmp-delta-imgs")
    assert di is not None and di >= 1, f"A 覆蓋的張數應多於 B(delta_imgs>=1),實得 {di}"


# ============================== AC3 — 分歧 triage 佇列 + 下鑽雙色疊框 ==============================
@pytest.mark.e2e
def test_triage_queue_and_drill_dual_overlay(page):
    _wait_app_ready(page)
    _enter_model_compare(page)
    # 佇列橫向縮圖條(至少一張符合 disagree:frame_000 = a_only)
    walls = _thumbwall_frames(page)
    assert walls and walls[0].locator("img").count() >= 1, "分歧 triage 佇列應有縮圖條(≥1 張)"
    # 下鑽 caption:配對/只A(frame_000 a_only:配對 1 · 只A 2)
    body = page.locator("body").inner_text()
    assert "配對" in body and "只A" in body, f"下鑽應顯示配對/只A 計數,實得片段:{body[:300]!r}"


# ============================== AC4 — dataset triage:filter 濾整個影像集 ==============================
@pytest.mark.e2e
def test_dataset_triage_filters_whole_set(page):
    _wait_app_ready(page)
    _enter_model_compare(page)
    # 預設『有分歧』:符合張數 < 全部(triage 把不感興趣的圖整張濾掉)
    n_disagree = _probe_int(page, "data-cmp-queue-n")
    assert n_disagree is not None and n_disagree >= 1, f"預設分歧佇列應 >=1,實得 {n_disagree}"
    # 切『看哪種差異』→『全部』:佇列張數應增加(納入 agree/missing 等)
    sb = page.locator('[data-testid="stSelectbox"]').filter(has_text="看哪種差異")
    sb.click()
    page.get_by_role("option", name=re.compile("全部")).first.click()
    page.wait_for_timeout(900)
    n_all = _probe_int(page, "data-cmp-queue-n")
    assert n_all is not None and n_all > n_disagree, \
        f"切『全部』後佇列張數應 > 分歧張數(triage 是對整個影像集),disagree={n_disagree} all={n_all}"


# ============================== AC5 — 缺檔 vs 0 框 區分(防假冒覆蓋差異)==============================
@pytest.mark.e2e
def test_missing_distinct_from_empty(page):
    _wait_app_ready(page)
    _enter_model_compare(page)
    # model_b 沒有 frame_001.json(與『有檔但 0 框』不同)→ B 缺檔數 >= 1
    mb = _probe_int(page, "data-cmp-missing-b")
    assert mb is not None and mb >= 1, f"B 缺檔(missing_b)應 >=1(frame_001 無 B 標註),實得 {mb}"
    assert page.get_by_text(re.compile(r"B 缺檔")).count() > 0, "儀表板應顯示『B 缺檔 N 張』"


# ============================== AC6 — 控制齊全(信心雙界/類別/分歧)==============================
@pytest.mark.e2e
def test_controls_present(page):
    # ★ 契約演進(User 回饋 C):『IoU 配對門檻』滑桿已移除(固定 0.5)→ 不再斷言它存在。
    _wait_app_ready(page)
    _enter_model_compare(page)
    assert page.get_by_text(re.compile(r"信心範圍")).count() > 0, "缺信心範圍(雙界)slider"
    assert page.get_by_text(re.compile(r"Object 類別")).count() > 0, "缺 Object 類別多選"
    assert page.get_by_text(re.compile(r"看哪種差異")).count() > 0, "缺『看哪種差異』分歧篩選"
    assert page.get_by_text(re.compile(r"IoU 配對門檻")).count() == 0, "『IoU 配對門檻』滑桿應已移除(User C)"


# ============================== AC7 — 向後相容(預設 OFF 不破壞既有版面)==============================
@pytest.mark.e2e
def test_backward_compatible_default_off(page):
    _wait_app_ready(page)
    assert page.get_by_role("button", name=re.compile(r"上一張")).count() > 0, "預設應有『上一張』鈕"
    assert page.get_by_role("button", name=re.compile(r"下一張")).count() > 0, "預設應有『下一張』鈕"
    assert _find_viewer_frame(page) is not None, "預設(比較 OFF)應有單一 viewer canvas"
    assert page.get_by_text(re.compile("覆蓋率彙總")).count() == 0, "預設未開比較,不應出現儀表板"


# ============================== AC8 — 未指定 model B 時的引導(不崩)==============================
@pytest.mark.e2e
def test_compare_without_model_b_prompts(page):
    _wait_app_ready(page)
    _toggle_compare(page)  # 開比較但未填 model B
    page.wait_for_timeout(600)
    assert page.get_by_text(re.compile(r"第二個 model 結果資料夾")).count() > 0, \
        "未指定 model B 時應提示填入第二個 model 資料夾(不崩、不顯示假儀表板)"
    assert page.get_by_text(re.compile("覆蓋率彙總")).count() == 0, "未填 model B 不應出現儀表板"
