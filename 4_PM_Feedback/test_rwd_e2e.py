"""窄視窗 RWD 的真實 E2E 驗收(2026-07-04,User 回報「這個圖並不是完整的,應該要做好 RWD」;
同日再回報「側邊欄整個不見了、進不去,滑鼠移過去也不會跑出來」,嚴重問題)。

背景:M7c 設計(20_viewer_workbench_redesign.md §3.11)規劃過 RWD 斷點但從未實作。實測(用真實
1254×1254 無標註影像資料集)發現:Streamlit sidebar 用 inline style 固定 `width:300px`,與 viewport
寬度無關,窄窗下佔掉不成比例的空間、把縮圖牆/主 viewer 一起擠小。修法為純 CSS media query
(`!important` 蓋掉 inline style,見 app.py RWD 區塊),不涉 Python/JS round-trip。

**同日發現的獨立、更嚴重問題**:Streamlit 在窄視窗(實測 700px)會自己判定 sidebar 進入
collapsed 狀態(`aria-expanded="false"`),用 `transform: translateX(-寬度px)` 把整個 sidebar
平移到畫面外——這是 Streamlit 內建的響應式行為,**移除本專案所有自訂 CSS 後在同一視窗寬度下
依然重現**,證明不是本專案任何一輪改動造成的。問題是負責「點回來展開」的控制項在這個視窗寬度
下找不到(`[data-testid="stSidebarCollapsedControl"]` 計數為 0),使用者卡住無法回到 sidebar。
修法:CSS 直接鎖住 `transform:none !important`,讓 sidebar 永遠不被推出畫面(縮寬但不消失)。

跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_rwd_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
"""
import pytest

APP_TITLE = "YOLO Image Viewer"


def _wait_app_ready(page):
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)


@pytest.mark.e2e
def test_sidebar_narrows_at_narrow_viewport(page):
    _wait_app_ready(page)
    sidebar = page.locator("[data-testid='stSidebar']").first

    page.set_viewport_size({"width": 1920, "height": 1080})
    page.wait_for_timeout(300)
    w_wide = sidebar.bounding_box()["width"]
    assert w_wide >= 280, f"寬視窗(1920px)下 sidebar 應維持 Streamlit 預設寬度,實得 {w_wide}"

    page.set_viewport_size({"width": 1000, "height": 800})
    page.wait_for_timeout(300)
    w_medium = sidebar.bounding_box()["width"]
    assert w_medium <= 230, (
        f"視窗縮到 1000px(≤1100px 斷點)後 sidebar 應收窄(設計 220px),"
        f"不應仍固定佔 300px 不成比例的空間;實得 {w_medium}"
    )

    page.set_viewport_size({"width": 700, "height": 800})
    page.wait_for_timeout(300)
    w_narrow = sidebar.bounding_box()["width"]
    assert w_narrow <= 230, (
        f"視窗縮到 700px(≤760px 斷點)後 sidebar 應更窄(設計 160px,此寬度以下 Streamlit "
        f"原生行為也可能介入把它收得更窄);實得 {w_narrow}"
    )
    assert w_narrow <= w_medium, (
        f"視窗越窄,sidebar 應越窄或至少不變寬(單調不遞增);"
        f"1000px→{w_medium}, 700px→{w_narrow}"
    )


# ============================== 防「側邊欄整個跑出畫面外、進不去」==============================
@pytest.mark.e2e
def test_sidebar_never_pushed_off_screen(page):
    _wait_app_ready(page)
    sidebar = page.locator("[data-testid='stSidebar']").first
    folder_input = page.locator("[data-testid='stTextInput'] input").first

    # 700px 是實測重現「sidebar 被 transform 推到畫面外(x=-300)、且找不到展開控制項」的寬度。
    for vw in (1920, 1000, 700, 500):
        page.set_viewport_size({"width": vw, "height": 900})
        page.wait_for_timeout(500)
        box = sidebar.bounding_box()
        assert box is not None and box["x"] >= 0, (
            f"視窗寬 {vw}px 下 sidebar 不應被推到畫面外(x<0);Streamlit 原生窄視窗行為會用 "
            f"transform 把它平移出去,且本應用的「展開」控制項在這個寬度下不存在,一旦跑出去"
            f"就進不來了(User 回報「進不去,滑鼠移過去也不會跑出來」);實得 x={box['x'] if box else None}"
        )
        assert folder_input.is_visible(), (
            f"視窗寬 {vw}px 下,資料夾路徑輸入框應維持可見可用(不應因 sidebar 跑出畫面而消失)"
        )


# ============================== sidebar 收合/展開恆可用(2026-07-04→07-05,三輪演進)==========
# 07-04 第二輪:User 回報「左邊的資料夾選項縮進去就再也拉不出來了,造成版面異常」(截圖=直排窄條)。
# 當時誤把「收合功能整個關掉」(鎖寬 300px 恆展開 + 隱藏收合/展開兩鈕)當成解法。
# 07-05 第三輪:User 回報「收合鈕移除了,版面就一直被佔用,難道只能靠移除收合鈕?」——上一輪修法
# 犧牲了「收合以騰出空間」這個正當需求。真正根因是 `stExpandSidebarButton` 為 `stToolbar` 的子元素,
# 而 `stToolbar{display:none}`(拿掉頂部空白 CSS)連同子元素一起吃掉;此外，展開鈕的祖先
# `stToolbar`/`stHeader` 建立獨立堆疊環境(z-index 999990)、被 sidebar(999991)蓋過,即使展開鈕
# 自己 z-index 設多高也點不到。修法:改成只隱藏工具列裡不需要的子元素(見設計 §3.11.1),保留
# 展開鈕 + fixed 定位 + 連祖先一起拉高 z-index,收合鈕/展開鈕皆恢復顯示、收合恢復成 Streamlit
# 原生行為(真的騰出空間,展開鈕真的點得回來)。


@pytest.mark.e2e
def test_sidebar_collapse_actually_shrinks_and_expand_button_restores_it(page):  # AC-sbfix1(07-05 改版)
    _wait_app_ready(page)
    sidebar = page.locator("[data-testid='stSidebar']").first
    folder_input = page.locator("[data-testid='stTextInput'] input").first

    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(300)

    box0 = sidebar.bounding_box()
    assert box0 is not None and box0["width"] >= 280, f"初始應為展開寬度;實得 {box0}"

    # 收合鈕「«」原本 hover sidebar 才現身
    sidebar.hover()
    page.wait_for_timeout(300)
    collapse_btn = page.locator("[data-testid='stSidebarCollapseButton']")
    assert collapse_btn.count() > 0 and collapse_btn.first.is_visible(), (
        "sidebar 收合鈕「«」應可見可點——這是使用者要求收合以騰出畫面空間的正當入口"
        "(User 07-05 回報:移除收合鈕會讓版面一直被佔用)"
    )
    collapse_btn.first.locator("button").first.click()
    page.wait_for_timeout(800)

    box1 = sidebar.bounding_box()
    assert box1 is not None and box1["width"] < 50, (
        f"點擊收合鈕後 sidebar 應真的收窄(騰出畫面空間給 viewer),不應像 07-04 第二輪那樣"
        f"被鎖回展開寬度;實得 width={box1['width'] if box1 else None}"
    )

    # 展開鈕(stExpandSidebarButton)必須可見可點——這是「收合後真的拉得回來」的關鍵,
    # 07-05 的根因(stToolbar display:none 連帶毀掉它 + z-index 被 sidebar 蓋過)修好才會通過。
    expand_btn = page.locator("[data-testid='stExpandSidebarButton']")
    assert expand_btn.count() > 0 and expand_btn.first.is_visible(), (
        "收合後展開鈕「»」應可見——07-05 根因:它是 stToolbar 的子元素,`stToolbar{display:none}`"
        "(拿掉頂部空白 CSS)會連同子元素一起吃掉,導致收合後找不到任何路徑展開"
    )
    expand_btn.first.click()
    page.wait_for_timeout(800)

    box2 = sidebar.bounding_box()
    assert box2 is not None and box2["width"] >= 280, (
        f"點擊展開鈕後 sidebar 應恢復完整寬度;實得 width={box2['width'] if box2 else None}"
    )
    assert folder_input.is_visible(), "展開後資料夾路徑輸入框應恢復可見可用"


@pytest.mark.e2e
def test_sidebar_usable_even_when_streamlit_autocollapses(page):  # AC-sbfix2
    _wait_app_ready(page)
    sidebar = page.locator("[data-testid='stSidebar']").first
    folder_input = page.locator("[data-testid='stTextInput'] input").first

    # 700px:實測 Streamlit 內部自動進入收合態(aria-expanded="false")的寬度。
    # 鎖寬規則必須讓「內部收合態」在畫面上與展開完全無異(寬 = media 斷點 160px、輸入框可用),
    # 不得出現寬度 <150 的擠壓(直排窄條 ~40px 即由此而來)。
    page.set_viewport_size({"width": 700, "height": 800})
    page.wait_for_timeout(500)
    box = sidebar.bounding_box()
    assert box is not None and box["x"] >= 0, f"sidebar 不得被推出畫面;x={box['x'] if box else None}"
    assert 150 <= box["width"] <= 230, (
        f"700px 下 sidebar 寬應鎖在 media 斷點 160px 左右(下界 150 防擠壓成直排窄條、"
        f"上界 230 防 media query 失效卡回 300px);實得 width={box['width']}"
    )
    assert folder_input.is_visible(), "窄窗自動收合態下,資料夾路徑輸入框仍應可見可用"
