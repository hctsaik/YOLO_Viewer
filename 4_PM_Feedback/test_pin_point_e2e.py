"""右鍵釘選 hover 點的真實 E2E 驗收(單圖模式)。

對應設計 `3_Architect_Design/20_viewer_workbench_redesign.md` §3.12 / §5「右鍵釘選 hover 點」
的 AC-pin1..5。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_pin_point_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
conftest 的 app_server 會自動起 streamlit run 5_PG_Develop/app.py;page fixture 已開好瀏覽器。
"""
import re
import time

import pytest

APP_TITLE = "YOLO Image Viewer"


def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)


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


def _hud_text(vf, timeout=30000):
    hud = vf.locator("#hud")
    hud.first.wait_for(state="attached", timeout=timeout)
    return hud.first.inner_text()


def _image_point_to_page_xy(page, vf, canvas_box, ix, iy):
    """把『影像座標』(ix,iy)換算成 page 絕對座標(供 page.mouse.move/click 使用)。
    用 viewer.viewport 的 image→viewport→pixel 換算(比硬猜畫面像素穩,沿既有 test_viewer_ux_e2e
    的 test_hover_inside_known_box_shows_cls 慣例)。"""
    px = vf.evaluate(
        "(p) => { const ip = new OpenSeadragon.Point(p.ix, p.iy);"
        " const vp = window.viewer.viewport.imageToViewportCoordinates(ip);"
        " const pf = window.viewer.viewport.pixelFromPoint(vp, true);"
        " return {x: pf.x, y: pf.y}; }",
        {"ix": ix, "iy": iy},
    )
    return canvas_box["x"] + px["x"], canvas_box["y"] + px["y"]


def _setup_viewer(page):
    _wait_app_ready(page)
    vf = _find_viewer_frame(page)
    assert vf is not None, "viewer canvas frame 未出現"
    vf.wait_for_function(
        "() => window.viewer && window.viewer.isOpen && window.viewer.isOpen()", timeout=30000)
    canvas = vf.locator("canvas").first
    canvas.wait_for(state="visible", timeout=30000)
    box = canvas.bounding_box()
    return vf, canvas, box


# ============================== AC-pin1 — 右鍵釘選 + 蓋掉原生選單 ==============================
@pytest.mark.e2e
def test_right_click_pins_point_and_suppresses_context_menu(page):
    vf, canvas, box = _setup_viewer(page)
    x, y = _image_point_to_page_xy(page, vf, box, 600, 450)
    page.mouse.move(x, y, steps=5)
    page.mouse.click(x, y, button="right")
    page.wait_for_timeout(400)
    hud = _hud_text(vf)
    assert "\U0001F4CC" in hud, f"右鍵後 HUD 應出現釘選列(📌),實得:{hud!r}"
    # 座標換算(viewport pixelFromPoint)容許 ±1px 捨入誤差,不綁死整數精確值。
    m = re.search(r"x=(\d+),\s*y=(\d+)", hud.split("\U0001F4CC", 1)[1])
    assert m and abs(int(m.group(1)) - 600) <= 1 and abs(int(m.group(2)) - 450) <= 1, \
        f"釘選列應含右鍵當下的影像座標(約 600,450,容差 ±1px),實得:{hud!r}"
    # 蓋掉原生選單:瀏覽器原生 context menu 不會出現在頁面 DOM(用『沒有原生選單覆蓋層』代理;
    # 主要證據仍是 AC 本身能讀到 e.preventDefault() 生效——若原生選單彈出會擋住後續互動,
    # 但既有測試基礎設施無法直接偵測瀏覽器原生選單,以下一步『pin-ov 存在』佐證事件被我方接管)。
    assert vf.locator(".pin-ov").count() == 1, "釘選後應在畫面畫出一個 pin-ov 標記"


# ============================== AC-pin2 — 移開滑鼠後釘選列不消失(與 hover 列獨立)==============================
@pytest.mark.e2e
def test_pin_persists_after_mouse_moves_away(page):
    vf, canvas, box = _setup_viewer(page)
    x, y = _image_point_to_page_xy(page, vf, box, 600, 450)
    page.mouse.move(x, y, steps=5)
    page.mouse.click(x, y, button="right")
    page.wait_for_timeout(400)
    hud_pinned = _hud_text(vf)
    assert "\U0001F4CC" in hud_pinned

    page.mouse.move(box["x"] + 10, box["y"] + 10, steps=10)
    page.wait_for_timeout(300)
    hud_after = _hud_text(vf)
    assert "\U0001F4CC" in hud_after, "移開滑鼠後釘選列不應消失"
    # 釘選列文字本身(座標/RGB)應與剛釘選時一致(不受之後 hover 影響)。
    pin_line_before = next(l for l in hud_pinned.splitlines() if "\U0001F4CC" in l)
    pin_line_after = next(l for l in hud_after.splitlines() if "\U0001F4CC" in l)
    assert pin_line_before == pin_line_after, "釘選列內容不應隨滑鼠移動改變"


# ============================== AC-pin3 — 再次右鍵 → 覆蓋,不累積 ==============================
@pytest.mark.e2e
def test_second_right_click_overwrites_not_accumulates(page):
    vf, canvas, box = _setup_viewer(page)
    x1, y1 = _image_point_to_page_xy(page, vf, box, 600, 450)
    page.mouse.move(x1, y1, steps=5)
    page.mouse.click(x1, y1, button="right")
    page.wait_for_timeout(400)
    hud1 = _hud_text(vf)

    x2, y2 = _image_point_to_page_xy(page, vf, box, 900, 100)
    page.mouse.move(x2, y2, steps=5)
    page.mouse.click(x2, y2, button="right")
    page.wait_for_timeout(400)
    hud2 = _hud_text(vf)

    assert hud1 != hud2, "第二次右鍵後釘選列座標應更新"
    # 座標換算(viewport pixelFromPoint)容許 ±1px 捨入誤差,不綁死整數精確值。
    m = re.search(r"x=(\d+),\s*y=(\d+)", hud2.split("\U0001F4CC", 1)[1])
    assert m and abs(int(m.group(1)) - 900) <= 1 and abs(int(m.group(2)) - 100) <= 1, \
        f"應顯示第二次右鍵的新座標(約 900,100,容差 ±1px),實得:{hud2!r}"
    assert vf.locator(".pin-ov").count() == 1, "覆蓋而非累積:畫面上應只有一個 pin-ov 標記"


# ============================== AC-pin4 — 切下一張圖 → 釘選清空 ==============================
@pytest.mark.e2e
def test_pin_clears_on_navigate(page):
    vf, canvas, box = _setup_viewer(page)
    x, y = _image_point_to_page_xy(page, vf, box, 600, 450)
    page.mouse.move(x, y, steps=5)
    page.mouse.click(x, y, button="right")
    page.wait_for_timeout(400)
    assert "\U0001F4CC" in _hud_text(vf)

    page.get_by_role("button", name=re.compile(r"下一張")).first.click()
    page.wait_for_timeout(1200)
    vf2 = _find_viewer_frame(page)
    vf2.wait_for_function(
        "() => window.viewer && window.viewer.isOpen && window.viewer.isOpen()", timeout=30000)
    hud_new = _hud_text(vf2)
    assert "\U0001F4CC" not in hud_new, "切圖後不應殘留上一張的釘選"
    assert vf2.locator(".pin-ov").count() == 0, "切圖後不應殘留釘選標記 overlay"
