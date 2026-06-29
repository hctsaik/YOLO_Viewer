"""Playwright 實證腳本(throwaway):逐條驗 5 個命題,印具體數據。

前置:先在 8799 起 streamlit:
  streamlit run spike/kbd_spike.py --server.port 8799 --server.headless true
本腳本用 chromium headless 連 http://localhost:8799,操作真實元件 iframe。

用法:
  python spike/kbd_probe.py            # 主測(fixed key)
  python spike/kbd_probe.py idx        # 對照組(idx key,證 remount)
"""
import sys
import time

from playwright.sync_api import sync_playwright

PORT = 8799
BASE = f"http://localhost:{PORT}"


def log(*a):
    print(*a, flush=True)


def viewer_frame(page):
    """找到元件 iframe(title=kbd_iframe)。Streamlit 元件 iframe 是 components.v1。"""
    for _ in range(60):
        for fr in page.frames:
            try:
                if fr.evaluate("() => document.title") == "kbd_iframe":
                    # 確認 OSD 已開
                    return fr
            except Exception:
                pass
        page.wait_for_timeout(250)
    raise RuntimeError("找不到 kbd_iframe 元件 iframe")


def wait_osd_open(fr):
    for _ in range(60):
        try:
            if fr.evaluate("() => !!(window.viewer && window.viewer.isOpen && window.viewer.isOpen())"):
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("OSD 未 open")


def probe_attr(page, name):
    el = page.query_selector("#probe")
    return el.get_attribute(name) if el else None


def wait_idx(page, want, timeout=8.0):
    """等主文件 probe 的 data-idx1 變成 want(rerun 完成)。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if probe_attr(page, "data-idx1") == str(want):
            return True
        page.wait_for_timeout(100)
    return False


def main():
    keymode = sys.argv[1] if len(sys.argv) > 1 else "fixed"
    url = BASE + (f"/?keymode=idx" if keymode == "idx" else "/")
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(url, wait_until="domcontentloaded")
        # 等 streamlit 跑完首屏 + 元件就緒
        page.wait_for_selector("#probe", timeout=30000)
        fr = viewer_frame(page)
        wait_osd_open(fr)
        page.wait_for_timeout(800)

        log(f"\n===== keymode={keymode} =====")
        log("初始 idx1 =", probe_attr(page, "data-idx1"),
            " loadCount =", fr.evaluate("() => window.__loadCount"))

        # ---------------- 命題1:固定 key → 不 remount ----------------
        load0 = fr.evaluate("() => window.__loadCount")
        # births = 跨 iframe 存活的「iframe 出生數」(寫在 window.top);remount 會累加
        births0 = page.evaluate("() => window.__iframeBirths")
        # 連切 5 次(→),每次等 rerun
        idx_seq = [int(probe_attr(page, "data-idx1"))]
        for k in range(5):
            want = ((idx_seq[-1] - 1 + 1) % 8) + 1  # next, 1-based wrap
            # 確保焦點在 viewer(命題2/3 要;這裡先 focus 再按)
            fr.evaluate("() => document.getElementById('osd').focus()")
            page.keyboard.press("ArrowRight")
            ok = wait_idx(page, want)
            # rerun 後 iframe 可能換引用,重新抓
            fr = viewer_frame(page)
            wait_osd_open(fr)
            idx_seq.append(int(probe_attr(page, "data-idx1")))
            log(f"  press#{k+1} ArrowRight → idx1={idx_seq[-1]} "
                f"thisIframeLoadCount={fr.evaluate('() => window.__loadCount')} "
                f"births={page.evaluate('() => window.__iframeBirths')} wait_ok={ok}")
        load_after = fr.evaluate("() => window.__loadCount")
        births_after = page.evaluate("() => window.__iframeBirths")
        results["P1_thisIframeLoadCount_start"] = load0
        results["P1_thisIframeLoadCount_after5"] = load_after
        results["P1_iframeBirths_start"] = births0
        results["P1_iframeBirths_after5"] = births_after
        results["P1_iframeBirths_delta"] = (births_after - births0) if (births_after is not None and births0 is not None) else None
        results["P1_idx_seq"] = idx_seq

        # ---------------- 命題2:連按不吃首鍵(混合 ← →)----------------
        # 重置到 img1
        seq2 = [int(probe_attr(page, "data-idx1"))]
        plan = ["ArrowRight", "ArrowRight", "ArrowLeft", "ArrowRight", "ArrowLeft"]
        deltas_expected = {"ArrowRight": +1, "ArrowLeft": -1}
        miss = 0
        for k, key in enumerate(plan):
            before = int(probe_attr(page, "data-idx1"))
            want = ((before - 1 + deltas_expected[key]) % 8) + 1
            fr.evaluate("() => document.getElementById('osd').focus()")
            page.keyboard.press(key)
            ok = wait_idx(page, want)
            fr = viewer_frame(page)
            after = int(probe_attr(page, "data-idx1"))
            seq2.append(after)
            if after != want:
                miss += 1
            log(f"  {key}#{k+1}: {before}→{after} (want {want}) {'OK' if after==want else 'MISS'}")
        results["P2_seq"] = seq2
        results["P2_miss"] = miss

        # ---------------- 命題3:rerun 後焦點自動回 viewer ----------------
        # 切一張(不手動點畫面),立刻讀 activeElement;再按一次驗仍生效
        fr.evaluate("() => document.getElementById('osd').focus()")
        before3 = int(probe_attr(page, "data-idx1"))
        page.keyboard.press("ArrowRight")
        wait_idx(page, ((before3 - 1 + 1) % 8) + 1)
        fr = viewer_frame(page)
        wait_osd_open(fr)
        page.wait_for_timeout(400)  # 等 open handler focus()
        active_id = fr.evaluate("() => (document.activeElement && document.activeElement.id) || '(none)'")
        active_tag = fr.evaluate("() => (document.activeElement && document.activeElement.tagName) || '(none)'")
        mid3 = int(probe_attr(page, "data-idx1"))
        # 不手動點畫面,直接再按一次(若焦點沒回 viewer,這次會落空)
        page.keyboard.press("ArrowRight")
        ok3 = wait_idx(page, ((mid3 - 1 + 1) % 8) + 1)
        after3 = int(probe_attr(page, "data-idx1"))
        results["P3_active_id"] = active_id
        results["P3_active_tag"] = active_tag
        results["P3_second_key_worked"] = ok3 and (after3 != mid3)
        results["P3_idx"] = [before3, mid3, after3]
        log(f"  rerun 後 activeElement: id={active_id} tag={active_tag}")
        log(f"  不點畫面再按一次: {mid3}→{after3} worked={results['P3_second_key_worked']}")

        # ---------------- 命題4:zoom/pan 跨切張保存 ----------------
        fr = viewer_frame(page)
        wait_osd_open(fr)
        # 控制基準:這張新影像「未操作」時的 fit zoom(restore 必須明顯異於它才算真保住)
        fit_zoom = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
        # zoom in 到明顯非 fit 的倍率(client-side,不 rerun);用 3.0x
        fr.evaluate("""() => {
            const v = window.viewer;
            v.viewport.zoomTo(v.viewport.getZoom(true) * 3.0, null, true);
            // 平移到非置中,驗 pan 也保住
            v.viewport.panBy(new OpenSeadragon.Point(0.1, 0.07), true);
            v.viewport.applyConstraints(true);
        }""")
        page.wait_for_timeout(400)
        z1 = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
        c1 = fr.evaluate("() => { const c=window.viewer.viewport.getCenter(true); return [c.x,c.y]; }")
        log(f"  fit_zoom(基準)={fit_zoom:.4f}  →  zoom/pan 操作後 z1={z1:.4f} center={c1}")
        idx_b = int(probe_attr(page, "data-idx1"))
        # 鍵盤切下一張(nav 會把 z1/c1 回傳 app 存起來,新影像 open 後 restore)
        fr.evaluate("() => document.getElementById('osd').focus()")
        page.keyboard.press("ArrowRight")
        wait_idx(page, ((idx_b - 1 + 1) % 8) + 1)
        fr = viewer_frame(page); wait_osd_open(fr); page.wait_for_timeout(500)
        z_next = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
        c_next = fr.evaluate("() => { const c=window.viewer.viewport.getCenter(true); return [c.x,c.y]; }")
        log(f"  切下一張後 zoom={z_next:.4f} center={c_next} (restore 後;基準 fit={fit_zoom:.4f})")
        # 再切回(prev)
        idx_b2 = int(probe_attr(page, "data-idx1"))
        fr.evaluate("() => document.getElementById('osd').focus()")
        page.keyboard.press("ArrowLeft")
        wait_idx(page, ((idx_b2 - 1 - 1) % 8) + 1)
        fr = viewer_frame(page); wait_osd_open(fr); page.wait_for_timeout(500)
        z2 = fr.evaluate("() => window.viewer.viewport.getZoom(true)")
        c2 = fr.evaluate("() => { const c=window.viewer.viewport.getCenter(true); return [c.x,c.y]; }")
        log(f"  切回後 z2={z2:.4f} center={c2}")
        results["P4_fit_zoom_baseline"] = fit_zoom
        results["P4_z1"] = z1
        results["P4_z_next"] = z_next
        results["P4_z2"] = z2
        results["P4_c1"] = c1
        results["P4_c_next"] = c_next
        # 真保住 = (a) restore 後 zoom≈z1  且  (b) z1 明顯異於 fit 基準(證明不是巧合落在 fit)
        zoom_matches = abs(z_next - z1) / max(z1, 1e-6) < 0.05 and abs(z2 - z1) / max(z1, 1e-6) < 0.05
        differs_from_fit = abs(z1 - fit_zoom) / max(fit_zoom, 1e-6) > 0.2
        center_matches = abs(c_next[0] - c1[0]) < 0.02 and abs(c_next[1] - c1[1]) < 0.02
        results["P4_zoom_restored_matches_z1"] = zoom_matches
        results["P4_z1_differs_from_fit"] = differs_from_fit
        results["P4_center_restored"] = center_matches
        results["P4_zoom_preserved"] = zoom_matches and differs_from_fit

        # ---------------- 命題5:打字不誤觸熱鍵 ----------------
        idx_before_type = int(probe_attr(page, "data-idx1"))
        # 聚焦主文件的 text_input(它在主文件 DOM,非元件 iframe 內)
        ti = page.query_selector("div[data-testid='stTextInput'] input")
        if ti is None:
            ti = page.query_selector("input")
        ti.click()
        page.wait_for_timeout(200)
        # 真打字母+數字到 input;每鍵之間檢查不要觸發 nav
        for ch in "drb123":
            page.keyboard.type(ch)
            page.wait_for_timeout(50)
        # 在 input 內按方向鍵(焦點在主文件 input → 元件 iframe 的 document keydown 看不到)
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)
        # input 的即時 DOM 值(證明字元真的進了 input、焦點確在 input)
        input_dom_val = ti.input_value()
        idx_after_type = int(probe_attr(page, "data-idx1"))
        results["P5_idx_before"] = idx_before_type
        results["P5_idx_after"] = idx_after_type
        results["P5_input_dom_value"] = input_dom_val
        results["P5_no_trigger"] = (idx_before_type == idx_after_type)
        log(f"  打字 'drb123'+←→: idx {idx_before_type}→{idx_after_type} "
            f"input_dom_value='{input_dom_val}' no_trigger={results['P5_no_trigger']}")

        # 打完點回 viewer → 鍵盤導覽恢復
        fr.evaluate("() => document.getElementById('osd').focus()")
        page.wait_for_timeout(150)
        idx_pre = int(probe_attr(page, "data-idx1"))
        page.keyboard.press("ArrowRight")
        ok5b = wait_idx(page, ((idx_pre - 1 + 1) % 8) + 1)
        results["P5_recover_after_click"] = ok5b
        log(f"  點回 viewer 後鍵盤恢復: worked={ok5b}")

        # 截圖佐證
        page.screenshot(path="spike/kbd_spike_shot.png", full_page=True)
        log("  screenshot → spike/kbd_spike_shot.png")

        browser.close()

    log("\n===== RESULTS =====")
    for k, v in results.items():
        log(f"  {k} = {v}")


if __name__ == "__main__":
    main()
