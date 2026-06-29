"""命題4 對照組:?restore=off → 不還原 viewport,證明切圖會重置回 fit。
跑法: python spike/kbd_p4_control.py
"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8799/?restore=off"


def vframe(page):
    for _ in range(60):
        for fr in page.frames:
            try:
                if fr.evaluate("() => document.title") == "kbd_iframe":
                    return fr
            except Exception:
                pass
        page.wait_for_timeout(250)
    raise RuntimeError("no iframe")


def osd_open(fr):
    for _ in range(60):
        try:
            if fr.evaluate("() => !!(window.viewer && window.viewer.isOpen && window.viewer.isOpen())"):
                return
        except Exception:
            pass
        time.sleep(0.2)


def idx1(page):
    el = page.query_selector("#probe")
    return int(el.get_attribute("data-idx1"))


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_selector("#probe", timeout=30000)
    fr = vframe(page); osd_open(fr); page.wait_for_timeout(800)

    fit = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
    fr.evaluate("() => { const v=window.viewer; v.viewport.zoomTo(v.viewport.getZoom(true)*3.0,null,true); v.viewport.applyConstraints(true); }")
    page.wait_for_timeout(400)
    z1 = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
    before = idx1(page)
    fr.evaluate("() => document.getElementById('osd').focus()")
    page.keyboard.press("ArrowRight")
    # 等切圖
    t0 = time.time()
    while time.time() - t0 < 8 and idx1(page) == before:
        page.wait_for_timeout(100)
    fr = vframe(page); osd_open(fr); page.wait_for_timeout(600)
    z_after = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
    print(f"[restore=off] fit={fit:.4f}  zoomed z1={z1:.4f}  切圖後 z_after={z_after:.4f}")
    reset = abs(z_after - fit) / max(fit, 1e-6) < 0.05
    kept = abs(z_after - z1) / max(z1, 1e-6) < 0.05
    print(f"  → reset_to_fit={reset}  kept_zoom={kept}  "
          f"(預期 restore=off 時 reset_to_fit=True、kept_zoom=False)")
    b.close()
