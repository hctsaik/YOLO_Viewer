"""Focus Object 模式的真實 E2E 驗收(2026-07-04)。

對應設計 `3_Architect_Design/20_viewer_workbench_redesign.md` §3.13 / §5「Focus Object 模式」
的 AC-focus1..4。

樣本集 conf 分布(git-tracked,同 test_conf_range_e2e.py 已釘死的分布):
  lot42_frame_000: 最高信心框 conf=0.91, bbox=[180,135,360,315]
  lot42_frame_001: 唯一框 conf=0.77, bbox=[20,20,60,60]
  lot42_frame_002/003/004、wafer16_000/001/002: 0 偵測

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_focus_object_e2e.py -m e2e -v
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


def _jump_to(page, n):
    jump = page.get_by_role("spinbutton").first
    jump.fill(str(n))
    jump.press("Enter")
    page.wait_for_timeout(800)


def _wait_viewer_open(vf, timeout=30000):
    vf.wait_for_function(
        "() => window.viewer && window.viewer.viewport "
        "&& window.viewer.isOpen && window.viewer.isOpen()",
        timeout=timeout)


def _toggle_focus(page):
    page.get_by_text("Focus Object", exact=False).first.click()
    page.wait_for_timeout(1000)


def _visible_image_rect(vf):
    """讀目前 viewport 可視範圍,換算回影像座標(x0,y0,x1,y1)。"""
    b = vf.evaluate("() => { const r = window.viewer.viewport.getBounds(true);"
                    " return {x:r.x, y:r.y, w:r.width, h:r.height}; }")
    tl = vf.evaluate(
        "(b) => { const p = window.viewer.viewport.viewportToImageCoordinates("
        "new OpenSeadragon.Point(b.x, b.y)); return {x:p.x, y:p.y}; }", b)
    br = vf.evaluate(
        "(b) => { const p = window.viewer.viewport.viewportToImageCoordinates("
        "new OpenSeadragon.Point(b.x+b.w, b.y+b.h)); return {x:p.x, y:p.y}; }", b)
    return tl["x"], tl["y"], br["x"], br["y"]


def _zoom(vf):
    return vf.evaluate("() => window.viewer.viewport.getZoom(true)")


# ============================== AC-focus1 — 開啟後聚焦到最高信心框 ==============================
@pytest.mark.e2e
def test_focus_zooms_to_highest_confidence_box(page):
    _wait_app_ready(page)
    _jump_to(page, 1)  # lot42_frame_000: 最高信心框 conf=0.91 bbox=[180,135,360,315]
    vf = _find_viewer_frame(page)
    assert vf is not None
    _wait_viewer_open(vf)
    z0 = _zoom(vf)
    assert abs(z0 - 1.0) < 0.05, f"開啟 Focus 前應是 fit 狀態(zoom≈1.0),實得 {z0}"

    _toggle_focus(page)
    z1 = _zoom(vf)
    assert z1 > z0 + 0.3, f"開啟 Focus Object 後應明顯放大,實得開前 {z0} 開後 {z1}"

    x0, y0, x1, y1 = _visible_image_rect(vf)
    bx, by, bw, bh = 180, 135, 360, 315
    assert x0 <= bx + 5 and y0 <= by + 5 and x1 >= bx + bw - 5 and y1 >= by + bh - 5, (
        f"可視範圍應包住最高信心框 [180,135,360,315](容差 5px),"
        f"實得可視範圍 ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})"
    )


# ============================== AC-focus2 — 切下一張自動重新聚焦(非停留舊視角)==============================
@pytest.mark.e2e
def test_focus_refocuses_on_next_image(page):
    _wait_app_ready(page)
    _jump_to(page, 1)
    vf = _find_viewer_frame(page)
    _wait_viewer_open(vf)
    _toggle_focus(page)
    page.wait_for_timeout(500)

    page.get_by_role("button", name=re.compile(r"下一張")).first.click()
    page.wait_for_timeout(1500)
    vf2 = _find_viewer_frame(page)
    _wait_viewer_open(vf2)
    page.wait_for_timeout(500)

    x0, y0, x1, y1 = _visible_image_rect(vf2)
    bx, by, bw, bh = 20, 20, 60, 60  # lot42_frame_001 唯一框
    assert x0 <= bx + 5 and y0 <= by + 5 and x1 >= bx + bw - 5 and y1 >= by + bh - 5, (
        f"切到下一張(唯一框 [20,20,60,60])後應自動重新聚焦到新框,而非停留在上一張的視角;"
        f"實得可視範圍 ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})"
    )


# ============================== AC-focus3 — 0 偵測圖退回 fit,不殘留前一張 zoom ==============================
@pytest.mark.e2e
def test_focus_falls_back_to_fit_on_zero_detection_image(page):
    _wait_app_ready(page)
    _jump_to(page, 1)
    vf = _find_viewer_frame(page)
    _wait_viewer_open(vf)
    _toggle_focus(page)
    page.wait_for_timeout(500)
    z_focused = _zoom(vf)
    assert z_focused > 1.3, f"聚焦後 zoom 應明顯 >1(fit),實得 {z_focused}"

    _jump_to(page, 3)  # lot42_frame_002:0 偵測
    vf2 = _find_viewer_frame(page)
    _wait_viewer_open(vf2)
    page.wait_for_timeout(500)
    z_empty = _zoom(vf2)
    assert abs(z_empty - 1.0) < 0.05, (
        f"0 偵測圖應退回 fit(zoom≈1.0),不應殘留前一張聚焦的高倍率 {z_focused};實得 {z_empty}"
    )


# ============================== AC-focus4 — 關閉後行為與功能上線前相同(向後相容)==============================
@pytest.mark.e2e
def test_focus_off_preserves_existing_zoom_pan_behavior(page):
    _wait_app_ready(page)
    _jump_to(page, 1)
    vf = _find_viewer_frame(page)
    _wait_viewer_open(vf)

    # 手動縮放(不開 Focus Object)
    canvas = vf.locator("canvas").first
    box = canvas.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, -600)
    page.wait_for_timeout(500)
    z_manual = _zoom(vf)
    assert z_manual > 1.0, "手動滾輪縮放應生效"

    # 切下一張再切回來:Focus Object 關閉時,M7a 既有的 zoom/pan 保存行為應不受影響
    page.get_by_role("button", name=re.compile(r"下一張")).first.click()
    page.wait_for_timeout(1200)
    page.get_by_role("button", name=re.compile(r"上一張")).first.click()
    page.wait_for_timeout(1200)
    vf2 = _find_viewer_frame(page)
    _wait_viewer_open(vf2)
    z_back = _zoom(vf2)
    assert abs(z_back - z_manual) < 0.1, (
        f"Focus Object 關閉時,既有 M7a 跨切張 zoom 保存行為不應被本功能影響;"
        f"手動縮放 {z_manual},切走再切回後 {z_back}"
    )
