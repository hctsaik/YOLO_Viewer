"""🧰 CV 顯示調整工具箱的真實 E2E 驗收(2026-07-04)。

對應設計 `3_Architect_Design/20_viewer_workbench_redesign.md` §3.14 的 AC-cvbox1..4。
純邏輯(imgadjust 各函式數值正確性)已由 `4_PM_Feedback/test_imgadjust.py`(AC1..23)驗過;
本檔只驗 app.py 這層『UI 接線』:預設收合、勾選後主圖真的變了、切圖自動重設、不影響偵測框判定。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_cv_toolbox_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
"""
import re
import time

import pytest

APP_TITLE = "YOLO Image Viewer"
_TOOLBOX_LABEL = "CV 顯示調整工具箱"


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


def _wait_viewer_open(vf, timeout=30000):
    vf.wait_for_function(
        "() => window.viewer && window.viewer.viewport "
        "&& window.viewer.isOpen && window.viewer.isOpen()",
        timeout=timeout)


def _jump_to(page, n):
    jump = page.get_by_role("spinbutton").first
    jump.fill(str(n))
    jump.press("Enter")
    page.wait_for_timeout(800)


def _perf(page):
    """讀 #perf 隱藏探針的 data-* 屬性(見 app.py 尾端 P1 探針區塊)。"""
    return page.evaluate(
        "() => { const d = document.querySelector('#perf'); const o = {};"
        " for (const a of d.attributes) o[a.name] = a.value; return o; }")


def _expand_toolbox(page):
    page.get_by_text(_TOOLBOX_LABEL, exact=False).first.click()
    page.wait_for_timeout(400)


def _toggle_control(page, label):
    page.get_by_text(label, exact=False).first.click()
    page.wait_for_timeout(800)


def _pixel_at(vf, x, y):
    """從目前 OSD tileSource 的真實 image URL(= app 端送進來的『已調整』data URL)離線畫到
    canvas 讀 (x,y) 像素值 —— 直接驗證『app 送進 viewer 的影像內容』,不依賴 zoom/DPI 換算。"""
    return vf.evaluate(
        """({x, y}) => new Promise((resolve) => {
            const url = window.viewer.world.getItemAt(0).source.url;
            const im = new Image();
            im.onload = () => {
                const c = document.createElement('canvas');
                c.width = im.naturalWidth; c.height = im.naturalHeight;
                const ctx = c.getContext('2d');
                ctx.drawImage(im, 0, 0);
                const d = ctx.getImageData(x, y, 1, 1).data;
                resolve([d[0], d[1], d[2]]);
            };
            im.src = url;
        })""",
        {"x": x, "y": y})


# ============================== AC-cvbox1 — 平常收合,展開後才看得到控制項 ==============================
@pytest.mark.e2e
def test_toolbox_collapsed_by_default(page):
    _wait_app_ready(page)
    _jump_to(page, 1)
    label = page.get_by_text(_TOOLBOX_LABEL, exact=False).first
    label.wait_for(timeout=15000)
    brightness_ctrl = page.get_by_text("亮度 / 對比", exact=False).first
    assert not brightness_ctrl.is_visible(), "工具箱應預設收合,內部控制項不應可見"

    _expand_toolbox(page)
    brightness_ctrl.wait_for(state="visible", timeout=10000)
    assert brightness_ctrl.is_visible(), "點擊工具箱標題展開後,內部控制項應變可見"


# ============================== AC-cvbox2 — 勾選「反色」後,主圖畫面真的變了 ==============================
@pytest.mark.e2e
def test_toolbox_invert_changes_displayed_pixels(page):
    _wait_app_ready(page)
    _jump_to(page, 1)
    vf = _find_viewer_frame(page)
    assert vf is not None
    _wait_viewer_open(vf)

    before = _pixel_at(vf, 10, 10)
    assert _perf(page)["data-adj-active"] == "0", "尚未開任何調整時,探針應顯示 0(無啟用中的調整)"

    _expand_toolbox(page)
    _toggle_control(page, "反色 (Invert)")
    assert _perf(page)["data-adj-active"] == "1", "勾選反色後,探針應顯示 1(有調整啟用中)"

    after = _pixel_at(vf, 10, 10)
    for b, a in zip(before, after):
        assert abs((255 - b) - a) <= 3, (
            f"反色後 (10,10) 像素應近似 255-原值(容差 3,吸收 PNG/canvas 捨入);"
            f"原值 {before},反色後 {after}"
        )


# ============================== AC-cvbox3 — 切圖後自動全部關閉,恢復原本顯示 ==============================
@pytest.mark.e2e
def test_toolbox_resets_on_image_switch(page):
    _wait_app_ready(page)
    _jump_to(page, 1)
    vf = _find_viewer_frame(page)
    _wait_viewer_open(vf)

    _expand_toolbox(page)
    _toggle_control(page, "反色 (Invert)")
    assert _perf(page)["data-adj-active"] == "1"

    page.get_by_role("button", name=re.compile(r"下一張")).first.click()
    page.wait_for_timeout(1200)
    assert _perf(page)["data-adj-active"] == "0", (
        "切到下一張影像後,🧰 工具箱調整應自動全部關閉、恢復原本顯示(需求 06_cv_toolbox.md §2)"
    )


# ============================== AC-cvbox4 — 純顯示層:不影響偵測框判定(kept/k/n 不變) ==============================
@pytest.mark.e2e
def test_toolbox_does_not_affect_detection_filtering(page):
    _wait_app_ready(page)
    _jump_to(page, 1)  # lot42_frame_000:有偵測框(同 test_focus_object_e2e 樣本分布)
    vf = _find_viewer_frame(page)
    _wait_viewer_open(vf)

    before = _perf(page)
    k0, n0 = before["data-shown-k"], before["data-shown-n"]

    _expand_toolbox(page)
    _toggle_control(page, "反色 (Invert)")
    _toggle_control(page, "亮度 / 對比")
    _toggle_control(page, "對比度極限拉伸")

    after = _perf(page)
    assert after["data-shown-k"] == k0 and after["data-shown-n"] == n0, (
        f"🧰 工具箱是純顯示層,啟用亮度/對比/反色/拉伸不應改變偵測框判定;"
        f"開前 k={k0} n={n0},開後 k={after['data-shown-k']} n={after['data-shown-n']}"
    )
