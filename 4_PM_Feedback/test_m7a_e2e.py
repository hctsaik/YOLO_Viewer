"""M7a 切片的真實 E2E 驗收(Viewer-First 版面重設計 — 版面收疊 / viewer 最大化 /
固定 key viewer 不 remount / zoom·pan 跨切張保存 / 修 remount bug / footer 常駐信心 slider)。

對應設計 `3_Architect_Design/20_viewer_workbench_redesign.md` §5 的 M7a-AC1…AC8。
只落本切片(M7a)的 AC;M7b(鍵盤 verdict/undo)、M7c(比較/虛擬化/RWD/DZI)不在此檔。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_m7a_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
conftest 的 app_server 會自動起 streamlit run 5_PG_Develop/app.py;page fixture 已開好瀏覽器。

TDD 提醒:M7a 的實作(app.py 版面重組、viewer.py 固定 key + restore_zoom/restore_center +
auto_height、index.html 量視窗高 + 跨 rerun 不 remount、footer 信心 slider、P1 隱藏探針)
PG 尚未完成,故本檔現在預期『紅』是正常的。本檔職責是把「使用者真的能用」釘成可機器斷言。

定位約定(沿用既有 test_app_e2e.py / test_viewer_ux_e2e.py 的掃 page.frames 法):
- viewer frame:該 iframe 內有 `canvas`;OSD 物件以全域 `window.viewer` 暴露;固定 key 後跨切張同一 iframe。
- thumbwall frame:該 iframe 內有『多張 <img>』且無 canvas。
- 固定 key 證據探針:viewer 元件端 `window.__loadCount`(沿用 spike `kbd_component/index.html`:
  同一 iframe 跨 rerun 不重跑 → 恆 ==1;idx-key 每切張新生 iframe → __loadCount 會在新 window 重置但
  iframe 換掉 → 舊 frame handle 失效。本檔斷言「切張後同一 viewer frame 上 __loadCount 仍 ==1」)。
- P1 效能探針:主文件 DOM `[data-render-ms]`(設計 §5 效能量測機制,id='perf',
  data-render-ms / data-reruns / data-thumb-recalc / data-tool-calls 皆可被 Playwright 讀為數字)。
"""
import re
import time

import pytest

APP_TITLE = "YOLO Image Viewer"
TOTAL = 8  # sample_images 內 8 張(5 lot42 png + 3 wafer16 tif)


# ============================== 共用定位 helper(沿用 test_viewer_ux_e2e.py 範式)==============================
def _wait_app_ready(page):
    """等首頁標題 + P1 探針 + 『下一張』鈕 hydrate(app 真的算繪完成)。
    版面演進(User 回饋,跨輪):頂列資訊徽章「N/total · 判定 · 偵測N框 · 檔名」整條移除 →
    進度不再以可見『N / 8』文字呈現;改以 P1 探針 [data-render-ms]/data-idx/data-total
    (主文件 DOM,設計 §5 P1 機器讀面)當 ready 與進度錨點;再加等『下一張』鈕 hydrate(查鈕不撲空)。"""
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name=re.compile(r"下一張")).first.wait_for(timeout=60000)


def _find_viewer_frame(page, timeout=45):
    """回傳含 OSD canvas 的 iframe(主 viewer);找不到回 None。"""
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


def _find_thumbwall_frame(page, min_imgs=2, timeout=45):
    """回傳縮圖牆 iframe(URL 身分判定)+ 就緒(img≥min_imgs);找不到回 None。
    2026-07-10 修(同 test_viewer_ux_e2e.py):內容嗅探(無 canvas + 多 img)會在 OSD canvas
    掛上前的窗口把 viewer 誤認成縮圖牆 → 改元件 URL 確定性身分,img 數只當就緒條件。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in page.frames:
            try:
                if ("/component/thumbwall.cv_thumbwall/" in (f.url or "")
                        and f.locator("img").count() >= min_imgs):
                    return f
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def _wait_viewer_open(vf, timeout=30000):
    """等全域 window.viewer 物件 open 完成(OSD 影像就緒)。"""
    vf.wait_for_function(
        "() => window.viewer && window.viewer.viewport "
        "&& window.viewer.isOpen && window.viewer.isOpen()",
        timeout=timeout)


def _next_button(page):
    """Command Bar『下一張』鈕(§7 釘死保留『下一張』語義;⟶ 為新版面圖示)。"""
    # 沿用 test_app_e2e 的 name="下一張 ⟶";退而以含「下一張」的鈕命中(避免綁死圖示)
    btn = page.get_by_role("button", name=re.compile(r"下一張"))
    return btn.first


def _prev_button(page):
    btn = page.get_by_role("button", name=re.compile(r"上一張"))
    return btn.first


def _progress_index(page):
    """讀目前進度序號 N(頂列資訊徽章移除後改讀 P1 探針 data-idx;設計 §5 P1 機器讀面);失敗回 None。"""
    v = page.locator("[data-render-ms]").first.get_attribute("data-idx")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _click_next_and_settle(page):
    """按『下一張』並等進度文字穩定(rerun 完成)。"""
    before = _progress_index(page)
    _next_button(page).click()
    # 等進度序號改變(或至少等一次 rerun 渲染)
    deadline = time.time() + 30
    while time.time() < deadline:
        cur = _progress_index(page)
        if cur is not None and cur != before:
            return
        page.wait_for_timeout(300)


# ============================== M7a-AC1 — 版面骨架(Command Bar + viewer + footer 控制)==============================
@pytest.mark.e2e
def test_layout_skeleton_command_bar_viewer_footer(page):
    # M7a-AC1:存在 Command Bar(⟵/⟶ 鈕 + 跳頁 number_input + 偵測數 caption『顯示 k/n 框』),
    #          主 viewer canvas frame 可見,『信心門檻』slider 在 sidebar 外(常駐控制)。
    #          ★ 契約演進(User 回饋 D):『顯示偵測框』checkbox 已移除(偵測框恆顯示)→ 不再斷言它。
    _wait_app_ready(page)

    # Command Bar:上一張/下一張 鈕(§7 保留「上一張」「下一張」語義)
    assert _prev_button(page).count() > 0, "Command Bar 缺『上一張』鈕"
    assert _next_button(page).count() > 0, "Command Bar 缺『下一張』鈕"
    # Command Bar:跳頁 number_input(spinbutton)
    assert page.get_by_role("spinbutton").count() > 0, "Command Bar 缺跳頁 number_input"
    # Command Bar:偵測數呈現 —— 『顯示 k/n 框』caption 已移除(User 回饋);改驗 P1 探針
    #             data-shown-n(偵測總框數)可解析(機器讀面取代可見文字)。
    _probe1 = page.locator("[data-render-ms]").first
    _probe1.wait_for(state="attached", timeout=30000)
    assert (_probe1.get_attribute("data-shown-n") or "").isdigit(), "P1 探針應暴露 data-shown-n(偵測框數)"

    # 主 viewer canvas 可見
    vf = _find_viewer_frame(page)
    assert vf is not None, "主 viewer canvas frame 未出現"
    vf.locator("canvas").first.wait_for(state="visible", timeout=30000)

    # 『信心門檻』slider 在 main(sidebar 外,常駐控制,單一真相)。顯示偵測框 checkbox 已移除(User D)。
    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    main.wait_for(timeout=30000)
    main.get_by_text("信心門檻").first.wait_for(timeout=30000)
    sidebar = page.locator("[data-testid='stSidebar']")
    assert sidebar.get_by_text("信心門檻").count() == 0, \
        "『信心門檻』slider 不應在 sidebar(常駐於頂列 Command Bar,§7)"
    assert page.get_by_text("顯示偵測框", exact=False).count() == 0, \
        "『顯示偵測框』checkbox 應已整個移除(偵測框恆顯示;User 回饋 D)"


# ============================== M7a-AC2 — 修 remount bug:固定 key viewer 跨切張不 remount ==============================
@pytest.mark.e2e
def test_fixed_key_viewer_no_remount_on_navigate(page):
    # M7a-AC2:連續切張(按 ⟵/⟶)後 viewer iframe 不 remount——元件端 window.__loadCount === 1 恆成立
    #          (固定 key="cv_viewer";對照 idx-key 會生新 iframe)。沿用 spike 命題1 證據手段。
    # 斷言法:同一 viewer frame handle 上切張 3 次後讀 __loadCount 仍 === 1。
    _wait_app_ready(page)
    vf = _find_viewer_frame(page)
    assert vf is not None, "主 viewer canvas frame 未出現"
    _wait_viewer_open(vf)

    # 起始 __loadCount 應為 1(元件第一次載入)
    lc0 = vf.evaluate("() => window.__loadCount")
    assert lc0 == 1, f"viewer 元件起始 __loadCount 應為 1(設計 §3.1 探針),實得 {lc0!r}"

    # 連切 3 次(下一張),每次後在『同一 vf handle』上讀 __loadCount
    # 固定 key:同一 iframe 跨 rerun 不重跑 → __loadCount 恆 1;
    # idx-key(舊 bug):每切張 remount → 此 frame handle 會失效或 __loadCount 重置/不一致。
    for i in range(3):
        _click_next_and_settle(page)
        # 切張後 viewer 仍需 open(換影像),等其就緒
        _wait_viewer_open(vf)
        lc = vf.evaluate("() => window.__loadCount")
        assert lc == 1, (
            f"第 {i + 1} 次切張後 viewer 元件 __loadCount={lc!r}(應恆 ==1);"
            "!=1 代表 iframe remount(idx-key bug 未修,設計 §2.5/§3.1)")


# ============================== M7a-AC3 — zoom/pan 跨切張保存 ==============================
@pytest.mark.e2e
def test_zoom_pan_preserved_across_navigation(page):
    # M7a-AC3:在第 N 張放大記下 getZoom(true)=z0 / getCenter(true)=c0,按 →(下一張)再按 ←(上一張)
    #          回來後 viewer getZoom(true) 與 z0 差 < 容差(|Δ|<0.05*z0),center 同理。
    #          沿用 spike 命題4;maxZoomPixelRatio=24 沿用(§3.2/§6:預設 1.1 會 clamp 回 fit)。
    _wait_app_ready(page)
    vf = _find_viewer_frame(page)
    assert vf is not None, "主 viewer canvas frame 未出現"
    _wait_viewer_open(vf)

    # 放大:zoomBy(3) + applyConstraints(true),記下 z0/c0
    vf.evaluate(
        "() => { window.viewer.viewport.zoomBy(3.0); "
        "window.viewer.viewport.applyConstraints(true); }")
    vf.wait_for_timeout(400)
    z0 = vf.evaluate("() => window.viewer.viewport.getZoom(true)")
    c0 = vf.evaluate("() => { const c = window.viewer.viewport.getCenter(true); return [c.x, c.y]; }")
    assert z0 and z0 > 0, f"放大後 z0 應為正數,實得 {z0!r}"

    # 下一張 → 上一張(切回原圖)
    _click_next_and_settle(page)
    _wait_viewer_open(vf)
    _prev_button(page).click()
    # 等回到原圖且 viewer open
    page.wait_for_timeout(500)
    _wait_viewer_open(vf)
    # 給 open handler 的 restore(zoomTo/panTo immediately=true)時間落地
    vf.wait_for_timeout(500)

    z1 = vf.evaluate("() => window.viewer.viewport.getZoom(true)")
    c1 = vf.evaluate("() => { const c = window.viewer.viewport.getCenter(true); return [c.x, c.y]; }")
    assert abs(z1 - z0) < 0.05 * z0, (
        f"切張後 zoom 未保存:z0={z0}, z1={z1}(容差 5%);"
        "restore_zoom 未經 args 帶回或被 clamp(設計 §3.2,maxZoomPixelRatio 須=24)")
    # center 容差用 viewport 座標的 0.05 絕對量(viewport 座標約 0..1 量級)
    assert abs(c1[0] - c0[0]) < 0.05 and abs(c1[1] - c0[1]) < 0.05, (
        f"切張後 pan(center)未保存:c0={c0}, c1={c1}(容差 0.05);"
        "restore_center 未還原(設計 §3.2)")


# ============================== M7a-AC4 — 收合狀態全域持久(跨切張不重置)==============================
@pytest.mark.e2e
def test_collapse_state_persists_across_navigation(page):
    # M7a-AC4:收合縮圖牆後切張 2 次,縮圖牆仍維持收合(thumbwall iframe 不渲染 / 0 寬 / img 數歸 0 可斷);
    #          ss.thumb_collapsed 不被切張重置(設計 §2.4 / User-role 第8點)。
    _wait_app_ready(page)
    # 起始:縮圖牆存在(多張 img)
    tf = _find_thumbwall_frame(page, min_imgs=2)
    assert tf is not None, "起始縮圖牆 iframe 未出現(無法驗收合持久)"

    # 收合縮圖牆:點「收縮圖」鈕(名稱含『縮圖』且語義為收合/隱藏)
    collapse_btn = page.get_by_role("button", name=re.compile(r"(收|隱藏|摺疊|收合).*縮圖|縮圖.*(收|隱藏|摺疊|收合)"))
    assert collapse_btn.count() > 0, "找不到『收縮圖』(收合縮圖牆)鈕(設計 §1.1 縮圖牆可收 0 寬)"
    collapse_btn.first.click()
    page.wait_for_timeout(1200)

    def _thumbwall_collapsed():
        # 收合後:縮圖牆 iframe 不渲染(找不到多 img 的子 frame)→ 視為收合
        return _find_thumbwall_frame(page, min_imgs=2, timeout=3) is None

    assert _thumbwall_collapsed(), "點『收縮圖』後縮圖牆未收合(仍渲染多張縮圖)"

    # 切張 2 次,收合狀態須維持(跨圖持久)
    for i in range(2):
        _click_next_and_settle(page)
        page.wait_for_timeout(600)
        assert _thumbwall_collapsed(), (
            f"切張第 {i + 1} 次後縮圖牆收合狀態被重置(又渲染縮圖牆);"
            "ss.thumb_collapsed 應跨切張持久(設計 §2.4/User-role 第8點)")


# ============================== M7a-AC5 — footer 信心 slider 常駐 + 即時反映 ==============================
@pytest.mark.e2e
def test_footer_conf_slider_resident_and_live(page):
    # M7a-AC5:footer slider 在三欄牆下方常駐(不在任何 expander 內);改門檻一格後,
    #          主 viewer caption/HUD「顯示 k/總 框」之 k 即時變化(同一 rerun 後讀文字確認 k 改變)。
    _wait_app_ready(page)
    # 先確保停在有框的第 1 張(lot42_frame_000.png,有 scratch/dent/edge)
    jump = page.get_by_role("spinbutton").first
    jump.fill("1")
    jump.press("Enter")
    # 有框(data-shown-k>0)— 『顯示 k/n 框』caption 已移除,改讀 P1 探針 data-shown-k
    _pb = page.locator("[data-render-ms]").first
    _dl = time.time() + 30
    while time.time() < _dl:
        _kv = _pb.get_attribute("data-shown-k")
        if _kv and _kv.isdigit() and int(_kv) > 0:
            break
        page.wait_for_timeout(300)

    main = page.locator("section.main, [data-testid='stAppViewContainer']").first
    conf_label = main.get_by_text("信心門檻").first
    conf_label.wait_for(timeout=30000)

    # 「信心門檻」slider 須常駐(不在 expander 內):祖先不含展開的 expander 容器。
    # 以「不在任何 [data-testid='stExpander'] 內」斷言常駐(召喚層工具台是 expander,footer 不是)。
    in_expander = conf_label.evaluate(
        "el => !!el.closest('[data-testid=\"stExpander\"]')")
    assert not in_expander, "『信心門檻』slider 不應在 expander(工具台召喚層)內;M7a 要求 footer 常駐"

    # 讀目前 k(『顯示 k/n 框』caption 已移除 → 改讀 P1 探針 data-shown-k)
    def _shown_k():
        v = page.locator("[data-render-ms]").first.get_attribute("data-shown-k")
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    k_before = _shown_k()
    assert k_before and k_before > 0, f"起始『顯示 k/總 框』k 應>0,實得 {k_before!r}"

    # 把信心門檻拉高一大段(提高門檻 → 留下的框變少 → k 應下降)。
    # 用鍵盤對 slider 連續 PageUp/ArrowRight 提高(Streamlit slider = role=slider)。
    slider = main.get_by_role("slider").first
    slider.wait_for(timeout=30000)
    slider.click()
    # 連按 ArrowRight 多次拉高門檻(step=0.01 → 多按以跨過某些框的 conf)
    for _ in range(60):
        slider.press("ArrowRight")
    # 等門檻生效:輪詢 data-shown-k 直到改變(取代固定 sleep —— 60 次快速按鍵在 server 忙時 rerun
    # 未沉澱會 flaky;輪詢到值變或逾時,斷言不變)。
    deadline = time.time() + 15
    k_after = _shown_k()
    while time.time() < deadline and k_after == k_before:
        page.wait_for_timeout(400)
        k_after = _shown_k()

    assert k_after is not None, "改門檻後仍應可讀 P1 探針 data-shown-k"
    assert k_after != k_before, (
        f"提高信心門檻後主 viewer『顯示框數』k 應變化:"
        f"before={k_before}, after={k_after}(設計 §3.7 即時反映)")


# ============================== M7a-AC6 — HUD 語義界線保留(hover RGB=顯示值)==============================
@pytest.mark.e2e
def test_hud_semantics_hover_rgb_is_display_value(page):
    # M7a-AC6:對 16-bit 樣本(wafer16_*.tif)hover 後,HUD 或 footer caption 明示
    #          hover RGB=「顯示值」、點擊取真值(含「顯示值」或「點擊取」或「取真值」其一)。
    #          承接 M6-AC9,版面位移後仍清楚(設計 §6 語義界線)。
    _wait_app_ready(page)
    # 跳到第 6 張(wafer16,16-bit;name 排序下落在 lot42(5)之後)
    jump = page.get_by_role("spinbutton").first
    jump.fill("6")
    jump.press("Enter")
    # 已導到第 6 張(wafer16,16-bit)—— 頂列資訊徽章移除後不再有可見檔名「wafer16」;改讀 P1 探針 data-idx 確認導航
    _probe6 = page.locator("[data-render-ms]").first
    _dl6 = time.time() + 30
    while time.time() < _dl6:
        if _probe6.get_attribute("data-idx") == "6":
            break
        page.wait_for_timeout(250)
    assert _probe6.get_attribute("data-idx") == "6", \
        f"跳頁到第 6 張(wafer16)後 P1 探針 data-idx 應為 '6',實得 {_probe6.get_attribute('data-idx')!r}"

    vf = _find_viewer_frame(page)
    assert vf is not None, "主 viewer canvas frame 未出現"
    _wait_viewer_open(vf)

    # 對 canvas 中心派 mousemove 觸發 hover 取樣
    canvas = vf.locator("canvas").first
    canvas.wait_for(state="visible", timeout=30000)
    box = canvas.bounding_box()
    cx, cy = box["width"] / 2, box["height"] / 2
    canvas.hover(position={"x": cx, "y": cy})
    canvas.dispatch_event("mousemove", {"clientX": box["x"] + cx, "clientY": box["y"] + cy})
    vf.wait_for_timeout(400)

    # HUD 文字 + 主頁 caption 皆可承載「顯示值/點擊取真值」語義(設計 §6:hover=顯示值、click=真值)
    hud = ""
    try:
        h = vf.locator("#hud")
        if h.count() > 0:
            hud = h.first.inner_text()
    except Exception:
        pass
    page_text = page.locator("body").inner_text()
    haystack = hud + "\n" + page_text
    assert ("顯示值" in haystack) or ("點擊取" in haystack) or ("取真值" in haystack), (
        "16-bit 圖須明示 hover RGB=顯示值、真值靠點擊(設計 §6 語義界線,M7a 版面位移後仍須清楚);"
        f"HUD/caption 皆未見此語義:\nHUD={hud!r}")


# ============================== M7a-AC7 — viewer 最大化(height 動態 ~720,顯著大於 M6 的 600)==============================
@pytest.mark.e2e
def test_viewer_maximized_height(page):
    # M7a-AC7 [截圖實證]:主 viewer 佔 stage ~85% 高(height 由 JS 量視窗動態給,~720 起),
    #          顯著大於 M6 的 600 固定高。截圖視覺驗收屬 [截圖實證],此處落『可量的高度下限』E2E 代理:
    #          viewer 元件 iframe / 內部 #osd 高度 > 660(明顯大於 600,留 auto_height 動態餘裕)。
    #          純像素級「三欄比例 = 窄|寬|窄」由 /ux-test 截圖人工驗收(設計 §5 [截圖實證])。
    _wait_app_ready(page)
    vf = _find_viewer_frame(page)
    assert vf is not None, "主 viewer canvas frame 未出現"
    _wait_viewer_open(vf)

    # 量 viewer 內部 #osd(或 canvas)的渲染高度(元件端 auto_height 量 window.innerHeight 動態給)
    h = vf.evaluate(
        "() => { const el = document.getElementById('osd') "
        "|| document.querySelector('canvas'); "
        "return el ? el.getBoundingClientRect().height : 0; }")
    assert h and h > 660, (
        f"主 viewer 高度應顯著大於 M6 的 600(auto_height ~720,M7a-AC7 viewer 最大化),實得 {h!r};"
        "若 ==600 表示仍用 M6 固定高、auto_height 未生效(設計 §1.1/§2.1 auto_height)")


# ============================== M7a-AC8 — P1 效能探針就緒(可讀為數字)==============================
@pytest.mark.e2e
def test_perf_probe_present_and_numeric(page):
    # M7a-AC8 [效能量測]:P1 隱藏探針 DOM 存在且 data-render-ms / data-reruns /
    #          data-thumb-recalc / data-tool-calls 皆為可解析數字(為後續 PerfA/B/C 鋪底;
    #          本 AC 只驗探針管線通、可讀,不硬斷門檻)。設計 §5 效能量測機制 (P1),探針在主文件 DOM。
    _wait_app_ready(page)
    # 探針在主文件:沿用 spike 命名 id='perf',帶 data-render-ms 等。
    probe = page.locator("[data-render-ms]").first
    probe.wait_for(state="attached", timeout=30000)

    for attr in ("data-render-ms", "data-reruns", "data-thumb-recalc", "data-tool-calls"):
        val = probe.get_attribute(attr)
        assert val is not None, f"P1 效能探針缺屬性 {attr}(設計 §5 P1:{attr} 須可被 Playwright 讀)"
        # 可解析為數字(int 或 float)
        try:
            float(val)
        except (TypeError, ValueError):
            pytest.fail(f"P1 探針 {attr}={val!r} 非可解析數字(設計 §5 要求 data-* 為數值)")
