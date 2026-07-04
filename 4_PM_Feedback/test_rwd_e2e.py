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


# ============================== 防「手動收合 sidebar 後拉不回來 + 直排窄條」==============================
# 2026-07-04 第二輪(設計 20_viewer_workbench_redesign.md §3.11.1):User 回報「左邊的資料夾選項
# 縮進去就再也拉不出來了,造成版面異常」(截圖 = ~40px 直排文字窄條)。根因:前一輪 transform:none
# 只擋「平移出畫面」,點收合鈕「«」時 Streamlit 仍把寬度收 0 → 卡半收合直排窄條;且 1.56 的展開鈕
# stExpandSidebarButton 在 header 工具列裡、已被「拿掉頂部空白」CSS 藏掉 → 真的拉不回來。
# 修法:收合鈕「«」隱藏(觸發器移除)+ aria-expanded=false 收合態寬度照鎖(任何寬度都不再有窄條)。


@pytest.mark.e2e
def test_sidebar_collapse_trap_removed(page):  # AC-sbfix1
    _wait_app_ready(page)
    sidebar = page.locator("[data-testid='stSidebar']").first
    folder_input = page.locator("[data-testid='stTextInput'] input").first

    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(300)

    # 收合鈕「«」原本 hover sidebar 才現身 —— 先 hover 再檢查,不給它藏身之處
    sidebar.hover()
    page.wait_for_timeout(300)
    collapse_btn = page.locator("[data-testid='stSidebarCollapseButton']")
    btn_visible = collapse_btn.count() > 0 and collapse_btn.first.is_visible()

    # 防禦縱深:萬一收合鈕仍可見(如未來 Streamlit 改 testid 使隱藏 CSS 失效),
    # 點下去也不得把 sidebar 弄壞 —— 修法前的版本會在此重現 User 的直排窄條(寬度 →0)。
    if btn_visible:
        collapse_btn.first.locator("button").first.click()
        page.wait_for_timeout(800)

    box = sidebar.bounding_box()
    assert box is not None and box["width"] >= 280, (
        f"sidebar 在 1280px 下應恆維持完整寬度(~300px),不得因收合(手動或自動)擠成"
        f"直排文字窄條(User 截圖重現:收合後只剩 ~40px);實得 width={box['width'] if box else None}"
    )
    assert folder_input.is_visible(), "資料夾路徑輸入框應恆可見可用(收合陷阱移除後不可能消失)"
    assert not btn_visible, (
        "sidebar 收合鈕「«」應已隱藏(stSidebarCollapseButton display:none)——它是「縮進去"
        "就拉不回來」陷阱的觸發器:收合後的展開鈕(stExpandSidebarButton)位在已被「拿掉頂部空白」"
        "CSS 隱藏的 header 工具列裡,使用者無法自行復原"
    )


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
