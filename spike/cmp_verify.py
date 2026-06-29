"""生死點 spike 的 playwright 驗證:雙 OSD 同 iframe + 雙向連動 + 無回授風暴。
前置:streamlit run spike/cmp_spike.py --server.port 8788 --server.headless true(已 ready)。
跑法:python spike/cmp_verify.py    印 SPIKE GREEN/RED + 5 命題結果。
"""
import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://localhost:8788"


def find_cmp_frame(page, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in page.frames:
            try:
                if f.locator("canvas").count() >= 2 and \
                        f.evaluate("() => !!(window.viewerA && window.viewerB)"):
                    return f
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def wait_both_open(vf, timeout=30000):
    vf.wait_for_function(
        "() => window.viewerA && window.viewerB && "
        "window.viewerA.isOpen && window.viewerA.isOpen() && "
        "window.viewerB.isOpen && window.viewerB.isOpen()",
        timeout=timeout)


def main():
    results = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1500, "height": 800})
        pg.goto(URL)
        pg.get_by_text("cmp spike").first.wait_for(timeout=60000)
        vf = find_cmp_frame(pg)
        if vf is None:
            print("RED: 找不到含兩個 canvas + window.viewerA/B 的 compare iframe")
            b.close(); sys.exit(1)
        wait_both_open(vf)

        # P1:兩顆 OSD 都 open + 各一(以上)canvas
        ncanvas = vf.locator("canvas").count()
        p1 = vf.evaluate("() => window.viewerA.isOpen() && window.viewerB.isOpen()") and ncanvas >= 2
        results["P1 兩顆 OSD 同 iframe 都 open"] = p1

        def za(): return vf.evaluate("() => window.viewerA.viewport.getZoom(false)")
        def zb(): return vf.evaluate("() => window.viewerB.viewport.getZoom(false)")
        def ca(): return vf.evaluate("() => {const c=window.viewerA.viewport.getCenter(false);return [c.x,c.y];}")
        def cb(): return vf.evaluate("() => {const c=window.viewerB.viewport.getCenter(false);return [c.x,c.y];}")

        # P2:在 A 縮放 → B 同步
        vf.evaluate("() => { window.viewerA.viewport.zoomBy(3.0); window.viewerA.viewport.applyConstraints(true); }")
        vf.wait_for_timeout(700)
        zA, zB = za(), zb()
        results["P2 A 縮放→B 同步 zoom"] = abs(zA - zB) < 0.05 * max(zA, 1e-6) and zA > 1.5

        # P3:在 A 平移 → B 同步 center
        vf.evaluate("() => { window.viewerA.viewport.panBy(new OpenSeadragon.Point(0.12, 0.06)); window.viewerA.viewport.applyConstraints(true); }")
        vf.wait_for_timeout(700)
        cA, cB = ca(), cb()
        results["P3 A 平移→B 同步 center"] = abs(cA[0] - cB[0]) < 0.02 and abs(cA[1] - cB[1]) < 0.02

        # P4:在 B 縮放 → A 同步(雙向)
        vf.evaluate("() => { window.viewerB.viewport.zoomBy(0.5); window.viewerB.viewport.applyConstraints(true); }")
        vf.wait_for_timeout(700)
        zA2, zB2 = za(), zb()
        results["P4 B 縮放→A 同步(雙向)"] = abs(zA2 - zB2) < 0.05 * max(zB2, 1e-6)

        # P5:無回授風暴 —— 再做一次互動,sync 次數增量有界(非指數爆炸),且最終 A≈B 收斂
        probe = vf.locator("#cmpprobe")
        c_before = int(probe.get_attribute("data-sync-count") or "0")
        vf.evaluate("() => { window.viewerA.viewport.zoomBy(1.4); window.viewerA.viewport.applyConstraints(true); }")
        vf.wait_for_timeout(1000)
        c_after = int(probe.get_attribute("data-sync-count") or "0")
        delta = c_after - c_before
        zA3, zB3 = za(), zb()
        converged = abs(zA3 - zB3) < 0.05 * max(zA3, 1e-6)
        # 一次互動的 sync 增量應有界(animation 每幀觸發,但值差門檻使其收斂;設寬鬆上界 200)
        results["P5 無回授風暴(sync 增量有界 + 收斂)"] = converged and 0 < delta < 200

        print("sync_count delta(一次互動) =", delta, " | zA,zB =", round(zA3, 3), round(zB3, 3))
        b.close()

    allok = all(results.values())
    for k, v in results.items():
        print(("  [OK] " if v else "  [X]  ") + k)
    print("SPIKE", "GREEN" if allok else "RED")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
