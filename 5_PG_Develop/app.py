"""CV Review Workbench — 獨立 Streamlit 原型(M1…M7a)。
跑法:streamlit run 5_PG_Develop/app.py

M7a Viewer-First 版面重設計(設計 3_Architect_Design/20_viewer_workbench_redesign.md):
  - 頂列 Command Bar(全寬一行):上一張/下一張 + 跳頁 + 檔名/偵測N框 + 召喚入口鈕
  - Stage 三欄:左=縮圖牆(可收 0 寬)| 中=主 viewer + viewer-footer | 右=判定 Rail(可收 0 寬)
  - viewer-footer 薄條常駐:顯示偵測框 toggle + 信心門檻 slider + 顯示 k/n 框 + 最後點擊
  - 🧰 CV 工具箱:亮度/對比/gamma/直方圖均衡化/反色/拉伸/二值化/Canny,平常收合、純顯示層
             (不影響偵測/判定/匯出;設計 3_Architect_Design/25_imgadjust.md + 20_*.md §3.14)
  - sidebar:篩選/搜尋/資料源/智慧排序 維持(預設收合)
  - 固定 key viewer(key="cv_viewer")修 remount;zoom/pan 跨切張保存(純 client 端)
  - P1 隱藏探針 data-render-ms / data-reruns / data-thumb-recalc / data-tool-calls

模組:imageset / imgio / sidecar / tagging / viewer / yolo / overlay / framecompare /
      filtersort / casepkg / framediff / missedq / simhash / embcluster / cocoio / dzitiles / htmlreport。
"""
import json
import os
import sys
import time
from pathlib import Path

# streamlit run 不會載 conftest,需自行把本目錄放到 sys.path 最前(讓 imgio 等本地模組優先)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import streamlit as st
from PIL import Image

_STRETCH = "stretch"  # st.* width 參數(取代已棄用的 width=_STRETCH)

import casepkg
import cocoio
import dzitiles
import embcluster
import filtersort
import framecompare
import framediff
import htmlreport
import imageset
import imgadjust
import imgio
import labelfmt
import labelloc
import missedq
import overlay
import sidecar
import simhash
import tagging
import yolo
from thumbwall import thumbwall
from viewer import osd_viewer

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = str(ROOT / "sample_images")
STATE = str(ROOT / ".cvr_state.json")

# ★ M7a §效能量測:本 run server 端 render 起點(結尾寫進 P1 探針 data-render-ms)
_T0 = time.perf_counter()

# 注意:sidebar 預設『展開』(不設 initial_sidebar_state="collapsed")—— 既有 M6 回歸測試
# test_sidebar_has_no_duplicate_overlay_toggle 會 wait_for(sidebar 可見)後才斷言『無重複開關』,
# 收合會使該 wait_for 逾時。設計 §1.1 的『收合 sidebar』為可選優化,不得犧牲既有契約測試;
# 使用者仍可手動收合(篩選/資料源/排序留在 sidebar,M7a 不改其行為)。
st.set_page_config(page_title="YOLO Image Viewer", layout="wide")

# ── 受限網路提示(2026-07-08;紅隊修正:降級為『條件式提示』、正確判 loopback)────────
# 現場最常見的元件 60s「trouble loading」橫幅根因 = 內容過濾 proxy／防火牆／防毒在『非 localhost
# 路徑』上擋掉自訂元件的 /component/ 資產(Chromium 對 localhost 有隱含 proxy 繞過、對 IP／主機名
# 沒有)。此故障(#1 全擋)元件碼救不了——iframe 的 HTML 根本抓不到;主頁不走 /component/ 仍可載,
# 故在此給提示。⚠ 紅隊實測:『無 proxy 的正常 LAN/遠端存取』元件其實好好的,所以本提示**不是紅色
# 警告、也不斷言一定壞**,而是『若下方元件載入失敗,這裡是原因與解法』的條件式 st.info,避免狼來了。
# loopback 判定用 ipaddress.is_loopback(涵蓋 127.0.0.0/8、::1、::ffff:127.0.0.1),非字面清單。
# 真 forward-proxy 重現/驗證見 verify/repro_real_proxy.py(repro_component_banner.py 是較早 page.route 版)。
try:
    import ipaddress as _ipaddress
    from urllib.parse import urlparse as _urlparse
    _ctx_url = st.context.url or ""
    _pu = _urlparse(_ctx_url)
    _host = (_pu.hostname or "").lower()
    _port = _pu.port or 8501
    if _host in ("", "localhost"):
        _is_localhost = True
    else:
        try:
            _is_localhost = _ipaddress.ip_address(_host).is_loopback
        except ValueError:
            _is_localhost = False   # 非 IP 的主機名(FQDN 等)視為非 localhost
except Exception:
    _is_localhost, _host, _port = True, "", 8501
if not _is_localhost:
    st.info(
        f"ℹ️ 你透過非 localhost 位址存取(`{_host}`)。**若**下方影像檢視器或縮圖牆出現"
        f"「trouble loading the component」載入失敗,通常是內容過濾 proxy／防火牆／防毒擋掉了元件的"
        f" `/component/` 資產(瀏覽器只對 `localhost` 隱含繞過 proxy)。解法:\n\n"
        f"　• 在本機 → 改用 [http://localhost:{_port}](http://localhost:{_port}) 開啟。\n\n"
        f"　• 從別台連入 → 將此位址(`{_host}`)加入 proxy／防毒例外白名單,或請 IT 放行。\n\n"
        f"（元件若正常顯示,請忽略本訊息。）"
    )

# ── 元件檔完整性 guard(2026-07-08;紅隊修正:覆蓋所有會被 .js.txt 改名/漏檔的元件檔)──────
# 現場已證的另一種同症故障:打包/搬運把元件檔弄不見或改名(例:Gmail-safe 打包 .js→.js.txt,
# 解壓沒還原 → 瀏覽器抓該檔得 404 → componentReady 送不出 → 同一條 60s 橫幅)。紅隊指出只查 main.js
# 覆蓋不全:index.html 還 <script src="openseadragon.min.js">(同樣 .js),index.html 本身也會漏,
# 任一缺失都同症。故檢查這幾個關鍵檔;缺了就在主頁明講(比 60s 後才跳神秘橫幅好排查)。
try:
    _cdir = Path(__file__).parent
    _required = (
        "viewer_component/index.html", "viewer_component/main.js",
        "viewer_component/openseadragon.min.js",
        "thumbwall_component/index.html", "thumbwall_component/main.js",
    )
    _missing_js = [rel for rel in _required if not (_cdir / rel).exists()]
except Exception:
    _missing_js = []
if _missing_js:
    st.error(
        f"⚠️ **元件檔缺失或被改名**:`{_missing_js}` 在磁碟上找不到。\n\n"
        f"這會讓下方元件跳「trouble loading」橫幅。常見原因:打包/搬運時漏檔,或 **Gmail-safe 打包把 "
        f"`.js` 改成 `.js.txt`** 而解壓後沒還原。請確認這些檔存在且副檔名正確,或重新完整取得專案。"
    )

# Streamlit checkbox 的原生 <input> 預設 width/height=0、opacity=0(視覺由樣式化方塊取代),
# 導致精準點擊(含自動化點擊)落不到實際 input 上。給它一個真實的透明命中區(疊在視覺方塊上),
# 不改變外觀,只讓「點到框」更可靠。純展示層調整,不動任何功能行為。
st.markdown(
    "<style>[data-testid='stCheckbox'] input[type='checkbox']{"
    "width:1em !important;height:1em !important;opacity:0 !important;cursor:pointer;}"
    "/* User 回饋:拿掉頂部空白 —— 收掉 Streamlit 預設 header 列 + 緊湊化 block-container 上緣 */"
    "header[data-testid='stHeader']{height:0 !important;min-height:0 !important;overflow:visible !important;}"
    "[data-testid='stDecoration']{display:none !important;}"
    "/* 2026-07-05 修正:不再整顆隱藏 stToolbar —— 它是 stExpandSidebarButton(sidebar 展開鈕)"
    "的容器,display:none 會連同子元素一起消失,導致收合 sidebar 後永久拉不回來(見下方"
    "「側邊欄可收合」區塊的完整說明)。改為只隱藏工具列裡不需要的子元素(部署鈕/主選單/狀態列),"
    "留下展開鈕、並用 fixed 定位讓它脫離被收成 0 高的 header,恆可見可點。*/"
    "[data-testid='stStatusWidget']{display:none !important;}"
    "[data-testid='stToolbarActions']{display:none !important;}"
    "[data-testid='stAppDeployButton']{display:none !important;}"
    "[data-testid='stMainMenu']{display:none !important;}"
    "[data-testid='stExpandSidebarButton']{position:fixed !important;top:6px !important;"
    "left:6px !important;z-index:9999 !important;}"
    "/* 展開鈕的祖先 stToolbar/stHeader 各自建立獨立堆疊環境(z-index:999990),而 sidebar 本身"
    "z-index:999991 更高 —— 子元素(展開鈕)無論自己設多高的 z-index 都只在祖先的堆疊環境內比較,"
    "永遠贏不了 sidebar(Playwright 實測:點擊被 stSidebarContent 攔截)。修法:祖先一起拉高過"
    "sidebar 的 999991,展開鈕才真正疊在最上層可點。*/"
    "header[data-testid='stHeader'],[data-testid='stToolbar']{z-index:1000000 !important;}"
    "/* 頂列工具列專業排版:標籤/按鈕不換行(避免『顯示偵測\\n框』『可撤 0\\n筆』醜換行)*/"
    "[data-testid='stCheckbox'] label{white-space:nowrap !important;}"
    ".stButton button{white-space:nowrap !important;}"
    "/* User 回饋:標題上方一大塊空白 = 主內容容器預設上 padding(新版 Streamlit 用 .block-container/"
    "   stMainBlockContainer,舊選擇器 section.main 不一定命中)→ 用 class + testid 雙保險收到接近 0 */"
    ".block-container,[data-testid='stMainBlockContainer'],section.main div.block-container"
    "{padding-top:0.4rem !important;padding-bottom:0.5rem !important;}"
    "/* 隱藏只放 <style> 的空 markdown 容器(本身佔一行高,造成標題上方留白)*/"
    "[data-testid='stMarkdownContainer']:has(> style){display:none !important;}"
    "/* 標題上緣不再額外留白 */"
    ".block-container > div:first-child{margin-top:0 !important;}"
    "</style>",
    unsafe_allow_html=True,
)

# ============================== 側邊欄可收合、且恆有路回來(2026-07-04→07-05,三輪演進)===
# 第一輪(07-04):User 回報「側邊欄整個不見了、進不去,滑鼠移過去也不會跑出來」。實測根因:
# Streamlit 在窄視窗(實測 700px)會自己判定 sidebar 進入 collapsed 狀態(aria-expanded="false"),
# 靠 CSS `transform: translateX(-寬度px)` 把整個 sidebar 平移到畫面外——Streamlit 內建的響應式
# 行為,非本專案改動造成(移除全部自訂 CSS 仍重現)。修法:`transform:none` 恆不讓它被推出畫面。
#
# 第二輪(07-04,User 回報「資料夾選項縮進去就再也拉不出來 + 版面異常〔直排文字窄條〕」):
# transform:none 只擋「平移出畫面」,手動點收合鈕「«」時 Streamlit 仍把**寬度**收到 0,
# 且展開鈕 `stExpandSidebarButton` 位在已被「拿掉頂部空白」整個藏掉的 header 工具列裡、
# 不可見不可點——當時**誤把「收合功能整個關掉」當成解法**(鎖寬 300px 恆展開 + 隱藏兩顆按鈕)。
#
# 第三輪(07-05,User 回報「收合鈕移除了,版面就一直被佔用,難道只能靠移除收合鈕?」——
# 上一輪修法犧牲了「收合以騰出空間」這個正當需求,只是把問題壓下去,非真正解法)。
# **真正根因**:`stExpandSidebarButton` 不可點,是因為它是 `stToolbar` 的子元素,而
# `stToolbar{display:none}`(上方「拿掉頂部空白」CSS)連同子元素一起吃掉——與「header 高度
# 收到 0」無關(header 有 overflow:visible,子元素仍可見;真正兇手是 stToolbar 的 display:none)。
# **修法(見上方 stToolbar 區塊)**:改成只隱藏工具列裡不需要的子元素(部署鈕/主選單/狀態列),
# 保留展開鈕並 fixed 定位。展開鈕恆可見可點 → 收合鈕「«」與展開鈕都**還原顯示**,收合/展開
# 恢復成 Streamlit 原生行為(收合真的騰出空間、點展開鈕真的拉得回來)。
# 唯一保留的例外:**窄視窗**(≤1100/760px,見下方 RWD 區塊)刻意維持「強制展開、鎖寬」——
# 這是第一輪那個更嚴重 bug(自動收合 + 完全找不到任何展開路徑)的專屬防護,窄視窗下 Streamlit
# 的自動收合行為仍不受信任,收合鈕在窄視窗按了也不會生效(僅此範圍犧牲收合彈性,換取零風險)。
st.markdown(
    "<style>[data-testid='stSidebar']{transform:none !important;}</style>",
    unsafe_allow_html=True,
)

# ============================== RWD(2026-07-04,User 回報大圖窄窗下版面沒跟著縮)==============================
# 實測:Streamlit sidebar 用 inline style 固定 width:300px,與 viewport 寬度無關;窄窗(如 nativeApp
# 較窄的 iframe、筆電視窗)下這 300px 佔掉不成比例的空間,把縮圖牆/主 viewer 一起擠小。
# 縮圖牆本身已用 `.cell img{width:100%}`(見 thumbwall_component)隨容器縮放,不需額外處理;
# 主要瓶頸是 sidebar 這個固定像素寬。修法:純 CSS media query,`!important` 可蓋掉 inline style
# (已實測驗證),依 viewport 寬分三級縮窄 sidebar,無需 JS round-trip、無風險影響既有互動邏輯。
# 注意:media query 內把 [aria-expanded='false'] 變體也列進 selector —— Streamlit 自己對收合態
# 有一條 `[data-testid='stSidebar'][aria-expanded='false']{width:0 !important}`(specificity
# 0,2,0),此處若只寫 [data-testid='stSidebar'](0,1,0)會輸給它,窄窗下 Streamlit 自動收合仍會
# 把寬度吃成 0(07-04 那個「完全找不到展開路徑」的原始 bug);同 specificity + 後載才能蓋掉——
# 這是 07-05 決定「窄視窗維持強制展開」唯一保留的鎖寬點(見上方 §側邊欄可收合 說明)。
st.markdown(
    "<style>"
    "@media (max-width: 1100px){"
    "[data-testid='stSidebar'],[data-testid='stSidebar'][aria-expanded='false']"
    "{width:220px !important;min-width:220px !important;}"
    "}"
    "@media (max-width: 760px){"
    "[data-testid='stSidebar'],[data-testid='stSidebar'][aria-expanded='false']"
    "{width:160px !important;min-width:160px !important;}"
    "}"
    "</style>",
    unsafe_allow_html=True,
)

ss = st.session_state

# ============================== M7a session_state 旗標(全域持久,跨圖不重置)==============================
ss.setdefault("thumb_collapsed", False)  # 縮圖牆收合(0 寬)
ss.setdefault("compare_on", False)       # 🔀 比較模式(兩圖疊圖;設計 23_compare.md §9)
ss.setdefault("cmp_marks", [])           # 疊圖比較標記的影像 name(最多 2 個,順序=標記順序=A/B;§9.2)
ss.setdefault("undo_stack", [])          # ★ M7b 跨圖 undo 軌跡({path,idx,field,old,new},LIFO,留近 5;設計 §3.6)
ss.setdefault("reruns", 0)               # 累積 rerun 計數(P1 探針 data-reruns)
ss.reruns += 1
# 本 run 的效能計數器(P3:重函式呼叫計數,寫進 P1 探針)。每 run 歸零後累加。
_counters = {"thumb_recalc": 0, "tool_calls": 0}

# ★ M7b:flush 上一個 run(緊接 st.rerun() 而無法當場顯示)留下的 toast 訊息。
_pending_toast = ss.pop("_pending_toast", None)
if _pending_toast:
    st.toast(_pending_toast)


# ============================== 快取資料層 ==============================
@st.cache_resource
def _position():
    return imageset.Position(STATE)


@st.cache_data(show_spinner=False)
def _records(folder, sort_key):
    # imageset 的檔案系統排序(name/time/size);M3 的智慧排序另由 filtersort 處理
    return imageset.sort_records(imageset.scan(folder), key=sort_key)


@st.cache_data(show_spinner=False)
def _array(path):
    return imgio.load(path)["array"]


@st.cache_data(show_spinner=False)
def _meta(path):
    d = imgio.load(path)
    return d["width"], d["height"], d["bit_depth"], d["channels"]


@st.cache_data(show_spinner=False)
def _display_rgb(path):
    return imgio.to_display_rgb(_array(path))


# 類別 → 顏色:穩定調色盤(涵蓋任意類別名);主 viewer 元件與縮圖『共用同一函式』→ 兩處顏色一致。
# (取代 overlay.CLASS_COLORS 只有 3 類、其餘退紅 → User 真實 10 類資料才有分辨度且前後一致。)
_PALETTE = [(0, 200, 0), (0, 160, 255), (255, 90, 0), (255, 0, 170), (170, 0, 255),
            (255, 190, 0), (0, 210, 200), (255, 70, 70), (130, 200, 0), (0, 110, 255),
            (200, 120, 255), (255, 150, 40)]


def _cls_color(cls):
    """類別名 → 穩定 RGB(同名同色;主 viewer 與縮圖共用,顏色一致)。"""
    s = str(cls or "")
    return _PALETTE[sum(ord(c) for c in s) % len(_PALETTE)] if s else (255, 0, 0)


@st.cache_data(show_spinner=False)
def _thumb_cached(path, max_px, dets_key, show, conf_thr, classes_key):
    """實際算縮圖(+可選疊框)的 cache 函式;所有參數皆可雜湊。
    dets_key/classes_key 為投影成 tuple 的可雜湊鍵。
    ★ M7a §效能(P3):每次真算(cache miss 進到這裡)即一次 thumb_recalc。"""
    thumb = imgio.thumbnail(_array(path), max_px=max_px)
    if not show or not dets_key:
        return imgio.to_png_bytes(thumb)
    th, tw = thumb.shape[0], thumb.shape[1]
    ow, oh = _meta(path)[0], _meta(path)[1]
    sx = tw / float(ow) if ow else 1.0
    sy = th / float(oh) if oh else 1.0
    scaled = []
    for (cls, conf, bx, by, bw, bh) in dets_key:
        scaled.append({"cls": cls, "conf": conf,
                       "bbox": [round(bx * sx), round(by * sy),
                                max(1, round(bw * sx)), max(1, round(bh * sy))]})
    classes = list(classes_key) if classes_key else None
    kept_t = overlay.filter_detections(scaled, conf_threshold=conf_thr, classes=classes)
    # 依類別調色盤逐色畫(與主 viewer 元件 _cls_color 同色 → 縮圖/大圖顏色一致;overlay.draw 每次回新陣列可鏈式)。
    drawn = thumb
    by_color = {}
    for det in kept_t:
        by_color.setdefault(_cls_color(det.get("cls")), []).append(det)
    for col, group in by_color.items():
        drawn = overlay.draw(drawn, group, color=col, thickness=1, draw_label=False)
    return imgio.to_png_bytes(drawn)


def _dets_key(dets):
    """把 list[dict] 偵測投影成可雜湊 tuple,當 cache key(避免 unhashable 崩潰)。"""
    out = []
    for d in (dets or []):
        b = d.get("bbox", [0, 0, 0, 0])
        out.append((d.get("cls"), round(float(d.get("conf", 0.0)), 3),
                    int(b[0]), int(b[1]), int(b[2]), int(b[3])))
    return tuple(out)


def _thumb(path, max_px=130, dets=None, show=False, conf_thr=0.0, classes=None):
    """show=False 或 dets 空 → 純縮圖(向後相容);否則縮圖座標系疊『過濾後』框。
    回傳 PNG bytes。dets 投影成可雜湊 tuple 進 cache(避免 unhashable list 破 cache)。
    ★ M7a §效能(P3):以 cache 命中與否估 thumb_recalc(miss → +1)。"""
    dets_key = _dets_key(dets) if (show and dets) else ()
    classes_key = tuple(classes) if classes else ()
    args = (path, max_px, dets_key, bool(show and dets), conf_thr, classes_key)
    # cache miss 估算:同 args 第一次見 → 視為真算(+1 thumb_recalc),之後視為命中。
    # 與 st.cache_data(同 args→同結果)語義一致,供 §效能 PerfC「改門檻不重建整牆」量測。
    if args not in _thumb_seen:
        _counters["thumb_recalc"] += 1
        _thumb_seen[args] = True
    return _thumb_cached(*args)


# 進程級「已算過的縮圖 cache key」集合(估 thumb_recalc:同 key 二次視為命中,不再 +1)。
# 與 st.cache_data 命中語義一致(同 args → 同結果),供 §效能 PerfC「改門檻不重建整牆」量測。
_thumb_seen = {}


@st.cache_data(show_spinner=False)
def _main_url_cached(path, dets_key, show, conf_thr, classes_key):
    """主 viewer 影像 data URL(可選燒框)的 cache:keyed by (path, dets, show, conf, classes)。
    ★ M7a:把『overlay.draw 全解析度 + PNG 編碼 + base64』結果快取,讓信心門檻連改時相同 conf
    命中、不同 conf 也只算一次 → 縮短 rerun(footer slider 連按即時反映,M7a-AC5)。"""
    base = _display_rgb(path)
    if show and dets_key:
        dets = [{"cls": c, "conf": cf, "bbox": [bx, by, bw, bh]}
                for (c, cf, bx, by, bw, bh) in dets_key]
        classes = list(classes_key) if classes_key else None
        disp = overlay.draw(base, dets, thickness=2, conf_threshold=conf_thr,
                            classes=classes, draw_label=True)
    else:
        disp = base
    return imgio.to_data_url(disp)


def _main_url(path, dets, show, conf_thr, classes):
    dets_key = _dets_key(dets) if (show and dets) else ()
    classes_key = tuple(classes) if classes else ()
    return _main_url_cached(path, dets_key, bool(show and dets), conf_thr, classes_key)


def _apply_adjustments(rgb):
    """依🧰 CV 工具箱目前勾選狀態,依設計建議管線順序(25_imgadjust.md §3.8)疊加套用。
    純顯示層:輸出只餵給主 viewer 顯示用,不寫回 sidecar、不影響 kept/偵測/匯出(imgadjust 契約 §6)。
    threshold/canny 為『終端替換』:一旦啟用即視為管線終點,忽略其後步驟(設計 §3.8 建議)。"""
    out = rgb
    if ss.get("adj_stretch_on"):
        out = imgadjust.stretch_contrast(out)
    if ss.get("adj_gamma_on"):
        out = imgadjust.gamma(out, ss.get("adj_gamma_val", 1.0))
    if ss.get("adj_bc_on"):
        out = imgadjust.brightness_contrast(out, ss.get("adj_brightness_val", 0.0),
                                             ss.get("adj_contrast_val", 1.0))
    if ss.get("adj_eq_on"):
        out = imgadjust.equalize_histogram(out)
    if ss.get("adj_invert_on"):
        out = imgadjust.invert(out)
    if ss.get("adj_thresh_on"):
        return imgadjust.threshold(out, ss.get("adj_thresh_val", 128.0))
    if ss.get("adj_canny_on"):
        return imgadjust.canny_edges(out, ss.get("adj_canny_low", 100.0), ss.get("adj_canny_high", 200.0))
    return out


def _display_url_adjusted(path):
    """主 viewer 用『已套用 CV 工具箱調整』的顯示影像 data URL。
    不掛 @st.cache_data:調整參數隨滑桿即時變動,若入 cache key 只會隨滑桿位置無限增生、無助於
    效能(對照 _main_url_cached 的『同組合可能重複命中』前提在此不成立);對顯示解析度影像
    (非原始全解析度)套用 numpy/cv2 運算已經夠快,不需要快取。"""
    rgb = _display_rgb(path)
    if not _adjustments_active():
        return imgio.to_data_url(rgb)
    return imgio.to_data_url(_apply_adjustments(rgb))


def _adjustments_active():
    """任一 CV 工具箱調整目前是否啟用中(供顯示管線走捷徑 + E2E 探針判斷)。"""
    return bool(ss.get("adj_stretch_on") or ss.get("adj_gamma_on") or ss.get("adj_bc_on")
                or ss.get("adj_eq_on") or ss.get("adj_invert_on") or ss.get("adj_thresh_on")
                or ss.get("adj_canny_on"))


def _label_path(label_dir, image_path):
    """偵測檔慣例:<label_dir>/<stem>.json 優先,否則 .txt(YOLO);兩者皆無 → 回 .json 路徑(yolo.load 容錯回 [])。"""
    stem = Path(image_path).stem
    pj = str(Path(label_dir) / f"{stem}.json")
    if os.path.isfile(pj):
        return pj
    pt = str(Path(label_dir) / f"{stem}.txt")
    return pt if os.path.isfile(pt) else pj


@st.cache_data(show_spinner=False)
def _detections(pred_folder, image_path, w, h, names_key=()):
    """載入單張圖偵測。**先試多格式自動偵測**(COCO/VOC/LabelMe/NDJSON,見 labelfmt,26_labelfmt.md);
    labelfmt 找不到任何(非 YOLO-txt)標註來源(回 None)才退回 YOLO `.json`/`.txt`(yolo.load)。
    兩條路徑輸出都是 Detection,下游 overlay/縮圖零改;names_key=類別名 tuple(僅 YOLO txt id→名用)。"""
    multi = labelfmt.load_for_image(image_path, w, h)
    if multi is not None:
        return multi
    return yolo.load(_label_path(pred_folder, image_path), img_w=w, img_h=h,
                     names=list(names_key) or None)


@st.cache_data(show_spinner=False)
def _names_from_yaml(path):
    """從 data.yaml 取 names(list 或 {id:name} dict)→ list[str];失敗 → []。"""
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        names = data.get("names") if isinstance(data, dict) else None
        if isinstance(names, list):
            return [str(x) for x in names]
        if isinstance(names, dict):
            return [str(names[k]) for k in sorted(names, key=lambda k: int(k))]
    except Exception:
        pass
    return []


@st.cache_data(show_spinner=False)
def _class_names(start_dir):
    """沿目錄上行(≤6 層)找 data.yaml(names:)或 classes.txt → list[str](YOLO .txt 的 id→名);找不到 → []。"""
    d = os.path.abspath(start_dir)
    for _ in range(6):
        for fn in ("data.yaml", "data.yml", "dataset.yaml"):
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                ns = _names_from_yaml(p)
                if ns:
                    return ns
        for fn in ("classes.txt", "obj.names"):
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        ns = [ln.strip() for ln in f if ln.strip()]
                    if ns:
                        return ns
                except OSError:
                    pass
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return []


@st.cache_data(show_spinner=False)
def _resolve_pred(folder, stems_key):
    """自動判定偵測標註目錄(labels/ 子夾 vs 同層);labelloc 純函式 → 同 key 同結果,cache 安全。
    stems_key = tuple(stems)(可雜湊)。回絕對路徑或 None(folder 非資料夾)。"""
    return labelloc.resolve_label_dir(folder, list(stems_key))


def _resize_to(arr, h, w):
    """把 RGB uint8 陣列縮放到 (h, w),供 framecompare 同形運算。"""
    if arr.shape[0] == h and arr.shape[1] == w:
        return arr
    return np.asarray(Image.fromarray(arr).resize((w, h)), dtype=np.uint8)


@st.cache_data(show_spinner=False)
def _feat_vec(path):
    """簡易特徵向量(8×8 灰階 flatten,64 維)供 embcluster 示範;非 DINO/SAM。"""
    g = np.asarray(Image.fromarray(_display_rgb(path)).convert("L").resize((8, 8)), dtype=np.float64)
    return g.flatten().tolist()


@st.cache_data(show_spinner=False)
def _dzi_tiles(path):
    """把圖建成 DZI 金字塔,瓦片轉 data url 供 OSD 自訂 tile source(只在可視區被取)。"""
    import base64
    bt = dzitiles.build_tiles(_display_rgb(path), tile_size=254, overlap=1)
    tiles = {lvl: {k: "data:image/png;base64," + base64.b64encode(v).decode("ascii")
                   for k, v in d.items()} for lvl, d in bt["tiles"].items()}
    return {"width": bt["width"], "height": bt["height"], "tile_size": bt["tile_size"],
            "overlap": bt["overlap"], "max_level": bt["max_level"], "num_levels": bt["num_levels"],
            "tiles": tiles}


# ============================== Sidebar(精簡:資料來源常駐,篩選/排序/進階收進折疊區)==============================
# User 回饋:左側功能列過長、多數功能不常用。改為「資料來源」常駐 + 單一折疊「篩選 / 排序 / 進階」,
# 不刪功能(可逆),只把低頻項收起來,預設視圖只剩 2 個資料夾欄。
def _pick_folder():
    """開原生資料夾選擇對話框(local 桌面 Streamlit;headless/無顯示則回 None、不崩)。
    Streamlit 在 worker thread 跑;tkinter 一次性 askdirectory 在 Windows 本機可用(已驗)。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        path = filedialog.askdirectory(parent=root)
        root.destroy()
        return path or None
    except Exception:
        return None


def _folder_field(label, key, default, help_txt):
    """資料夾輸入欄 + 原生『📁 瀏覽』選擇鈕(可打字、也可用選的)。回目前路徑字串。
    瀏覽鈕在 text_input 實例化『之前』寫 ss[key](合法)再 rerun → 把選到的路徑回填欄位。"""
    ss.setdefault(key, default)
    col_in, col_btn = st.columns([5, 1], vertical_alignment="bottom")
    if col_btn.button("📁", key=f"{key}__browse", help=help_txt):
        picked = _pick_folder()
        if picked:
            ss[key] = picked
            st.rerun()
    return col_in.text_input(label, key=key)


with st.sidebar:
    st.header("📁 資料來源")
    # 2026-07-05:比較模式改成「在縮圖牆標記兩張影像疊圖」,不再需要第二個 model 資料夾
    # (見 23_compare.md §9)→ 只剩單一影像資料夾(標註自動偵測)。
    folder = _folder_field("影像資料夾(labels/ 子夾或同層自動偵測標註)", "folder_input", SAMPLE,
                           "瀏覽選擇影像資料夾(含影像 + 標註)")


# User 回饋:移除整個『🔍 篩選 / 排序 / 進階』折疊區(這些功能都不要)。以下給無作用預設值,
# 讓既有篩選/排序流程仍可運作:不做任何篩選;排序由頂列『排序』下拉(檔名 / 信心)控制。
fs_sort = "name"
f_tags, f_tag_mode, f_verdict, f_reviewed = [], "any", "(全部)", "(全部)"
f_book, f_text, f_class = False, "", ""
smart, smart_rev, use_queue = "(關閉)", False, False


if not os.path.isdir(folder):
    st.error(f"找不到資料夾:{folder}")
    st.stop()

# YOLO 切分佈局:選到的夾若無『直接影像』但有 images/ 子夾(典型 <split>/images + <split>/labels)→ 改掃 images/。
img_dir = folder
if not _records(folder, fs_sort) and os.path.isdir(os.path.join(folder, "images")):
    img_dir = os.path.join(folder, "images")
records = _records(img_dir, fs_sort)
if not records:
    st.warning("這個資料夾沒有支援的影像(支援 .png/.jpg/.tif…;YOLO 資料集請選含 images/ 的那層,或 images/ 本身)。")
    st.stop()

# 類別名:沿目錄上行找 data.yaml(names:)/classes.txt → YOLO .txt 的 id→名;找不到則框上顯示數字 id。
class_names = _class_names(img_dir)
_names_key = tuple(class_names)

# ---- 標註目錄 ----
# YOLO 切分:影像在 <X>/images → 標註在 sibling <X>/labels;否則 labelloc(同層 / labels 子夾)。
_pred_stems = tuple(Path(r["name"]).stem for r in records)
_img_norm = os.path.normpath(img_dir)
_sibling_labels = os.path.join(os.path.dirname(_img_norm), "labels")
if os.path.basename(_img_norm).lower() == "images" and os.path.isdir(_sibling_labels):
    pred_folder = _sibling_labels
    _pred_caption = "標註於 sibling labels/(YOLO 切分)"
else:
    _resolved_pred = _resolve_pred(img_dir, _pred_stems)
    pred_folder = _resolved_pred or img_dir
    if _resolved_pred and os.path.normcase(os.path.abspath(_resolved_pred)) != \
            os.path.normcase(os.path.abspath(img_dir)):
        _pred_caption = f"標註於子資料夾 {os.path.basename(_resolved_pred)}/"
    else:
        _pred_caption = "標註於同影像資料夾"
if class_names:
    _pred_caption += f" · 類別名 {len(class_names)} 個已載入"
# 多格式標註偵測(COCO/VOC/LabelMe/NDJSON):若偵測到,caption 直接標示——這條路徑優先於 YOLO
# .json/.txt(見 _detections),讓使用者知道框是哪種來源畫的。
try:
    if labelfmt.folder_has_annotations(img_dir):
        _pred_caption = "標註格式:COCO / VOC / LabelMe / NDJSON 自動偵測(優先於 YOLO)"
except Exception:
    pass
st.sidebar.caption(_pred_caption)


# ============================== 信心雙界過濾(app inline 慣例,不擴 overlay 單下界契約) ==============================
# 2026-07-04 設計演進(20_viewer_workbench_redesign.md §7):單張模式信心門檻由單值升級為雙界,
# 且同時卡縮圖牆/導覽清單(triage),不只濾主圖疊框。與既有比較模式 _cmp_filter 共用同一過濾邏輯。
def _cmp_filter(dets, lo, hi, classes):
    """conf 雙界 + 類別過濾(沿 §7.2 app inline 慣例;不擴 overlay 單下界契約)。"""
    return [d for d in dets if lo <= float(d.get("conf", 0.0)) <= hi
            and (not classes or d.get("cls") in classes)]


# ============================== 兩圖疊圖比較:標記狀態(23_compare.md §9.2)==============================
def _toggle_cmp_mark(name):
    """切換某影像的疊圖比較標記:已標記則移除;否則附加,超過 2 張時 FIFO 踢掉最舊一張
    (使用者永遠『點了就有效』,不需先想清楚要取消哪一張)。標記存 name(非 index)——
    排序/篩選可能改變 index,name 才是跨 rerun 穩定的 key。"""
    marks = list(ss.cmp_marks)
    if name in marks:
        marks.remove(name)
    else:
        marks.append(name)
        if len(marks) > 2:
            marks.pop(0)
    ss.cmp_marks = marks


def _in_conf_range(it, lo, hi, classes=None):
    """影像清單 triage 述詞:全開且未選類別 (0.0,1.0)/classes=None 為向後相容關閉點,不濾
    (含 0 框圖,同現狀);使用者主動偏離全開**或**選了特定 Object 類別才啟動 triage,此時需
    至少一個偵測『同時』落在 [lo,hi] 且(若有選類別)屬於該類別才保留——語義與 `kept`
    的 `_cmp_filter` 一致(同一個偵測要同時滿足兩個條件,不是分開各自滿足)。
    2026-07-04 擴充(User 回報:選了 Object 類別後,某圖明明沒有該類別的框卻仍留在清單、
    右側自然畫不出框,造成『縮圖沒消失但沒看到框』的困惑):原僅濾信心,現信心+類別一併觸發
    triage,兩者任一偏離預設即啟動,行為與『kept』的框級過濾完全一致、不再兩套邏輯各管一半。"""
    if lo <= 0.0 and hi >= 1.0 and not classes:
        return True
    return len(_cmp_filter(it["detections"], lo, hi, classes)) > 0


# ============================== 組裝 items(含 sidecar / detections) ==============================
def _item_for(r):
    w, h, _bit, _ch = _meta(r["path"])
    sc = sidecar.load(r["path"])
    dets = _detections(pred_folder, r["path"], w, h, _names_key)
    return {"name": r["name"], "path": r["path"], "time": float(r.get("mtime", 0.0)),
            "sidecar": sc, "detections": dets, "record": r, "w": w, "h": h}


need_class = bool(f_class.strip())  # 類別篩選需要載入每張圖的偵測
items = [_item_for(r) for r in records]

# ---- 套用篩選 ----
query = {}
if f_tags:
    query["tags"] = f_tags
    query["mode"] = f_tag_mode
if f_verdict != "(全部)":
    query["verdict"] = f_verdict
if f_reviewed == "已 review":
    query["reviewed"] = True
elif f_reviewed == "未 review":
    query["reviewed"] = False
if f_book:
    query["bookmarked"] = True
if f_text.strip():
    query["text"] = f_text.strip()

# 信心門檻(雙界):footer slider 在 Command Bar 之後才畫,先用其 session_state key 讀值
# (Streamlit widget key 跨 rerun 持久;沿用 M7a 既有「先讀後畫」慣例,見 footer slider 附近註解)。
conf_lo, conf_hi = ss.get("footer_conf_thr", (0.0, 1.0))

# Object 類別下拉選項:只套信心範圍(尚未套類別本身)的中繼結果,避免「選了類別後選項只剩
# 自己」的自我循環;同「先讀後畫」慣例提前讀 cls_filter 目前值(widget 在 Command Bar 才畫)。
# 2026-07-04(User 回報:選了 Object 類別後,某圖明明沒有該類別的框卻仍留在清單、右側自然
# 畫不出框——縮圖沒消失、右邊也沒框,一頭霧水):Object 類別現在也一併觸發清單 triage,
# 語義與 `kept` 的框級過濾一致(見 `_in_conf_range` 擴充後的說明)。
_conf_only_items = [it for it in items if _in_conf_range(it, conf_lo, conf_hi, None)]
_all_classes = sorted({d.get("cls", "") for it in _conf_only_items
                       for d in it["detections"] if d.get("cls")})
_cls_sel_raw = ss.get("cls_filter", "全部")
if _cls_sel_raw not in (["全部"] + _all_classes):
    _cls_sel_raw = "全部"
    ss["cls_filter"] = "全部"
_sel_classes = None if _cls_sel_raw == "全部" else [_cls_sel_raw]


def _passes(it):
    if query and not tagging.matches(it["sidecar"], query):
        return False
    if need_class:
        cls_set = {d["cls"] for d in it["detections"]}
        if f_class.strip() not in cls_set:
            return False
    if not _in_conf_range(it, conf_lo, conf_hi, _sel_classes):
        return False
    return True


shown_items = [it for it in items if _passes(it)]
if not shown_items:
    st.warning("沒有符合篩選條件的影像。")
    # 防卡死(設計 §4k,2026-07-04 擴充):清單被 triage 篩空時,若不重畫同 key 的控制就
    # st.stop(),使用者連拉寬/改選回去的控制都會從畫面消失。**Object 類別觸發清單 triage 後
    # (§7 擴充),單獨重畫信心 slider 已不夠**——若是類別選擇本身造成篩空(信心範圍其實沒問題),
    # 使用者會連改回「全部」的下拉都看不到,卡死無解(同 §4k 那個坑,換了個觸發源)。
    # 兩個控制都要重畫,才能保證無論哪個是篩空成因,使用者都能自行脫困。同 key 在互斥分支
    # 各畫一次合法,不衝突。
    st.slider("信心門檻", 0.0, 1.0, (conf_lo, conf_hi), 0.01, key="footer_conf_thr")
    st.selectbox("Object 類別", ["全部"] + _all_classes, key="cls_filter")
    st.stop()

# ---- 排序:User 主排序(by 檔名 / by 信心,可見控制,單張與比較共用)+ 進階(智慧排序鍵 / Review Queue,sidebar)----
# 複用 filtersort.sort_items(key="name"/"conf";conf=該圖最大偵測信心,tie-break name)。
_sort_mode = ss.get("sort_mode", "檔名")
if use_queue:
    shown_items = filtersort.review_queue(shown_items)
elif smart != "(關閉)":
    shown_items = filtersort.sort_items(shown_items, smart, reverse=smart_rev)
elif _sort_mode == "信心(高→低)":
    shown_items = filtersort.sort_items(shown_items, "conf", reverse=True)
elif _sort_mode == "信心(低→高)":
    shown_items = filtersort.sort_items(shown_items, "conf", reverse=False)
else:
    shown_items = filtersort.sort_items(shown_items, "name")


# ============================== 索引 + 位置記憶 ==============================
pos = _position()
nav_sig = (folder, len(shown_items))
if ss.get("nav_sig") != nav_sig:
    ss.nav_sig = nav_sig
    ss.idx = min(pos.get(folder, 0), len(shown_items) - 1)
    ss.last_n = 0
    ss.last_click = None
ss.idx = max(0, min(ss.get("idx", 0), len(shown_items) - 1))
total = len(shown_items)

# 偵測框總開關:M7a 由 viewer-footer 控制(footer 在三欄之內、於下方渲染)。
# User:移除『顯示偵測框』開關(無實質意義)→ 偵測框恆顯示,改由『信心門檻』過濾。
# 保留 show_overlay 名稱供既有讀取點(縮圖牆 show=show_overlay 等),恆 True。
# conf_lo/conf_hi 已在 shown_items 組裝前讀好(見上方「信心門檻(雙界)」),此處沿用同一值,
# 不重讀(footer slider 尚未在本輪畫出,但其 session_state key 已跨 rerun 持久)。
show_overlay = True

# 漏檢 queue(恆算極輕:只看 sidecar/detections,不碰重函式)→ 供 Command Bar 徽章 N
_mq = missedq.missed_queue(shown_items)
_name2idx = {it["name"]: i for i, it in enumerate(shown_items)}
_path2idx = {it["path"]: i for i, it in enumerate(shown_items)}  # ★ M7b undo 跳轉用


# ============================== M7b 鍵盤工作流:nav 事件處理 + 改值即時存 + 跨圖 undo ==============================
_STATUS_CYCLE = ["none", "need_review", "done"]
# verdict/狀態 仍同步到工具台「✏️ 標記」分頁的 widget(那些 widget 在本檔較後渲染);
# bookmark 已移到『頂列 button』(在 nav 處理之前渲染,且 button 無持久 widget-state)→ 不走 widget 同步,
# 只讀寫 sidecar 當單一真相(避免『widget 實例化後再改 session_state』的 StreamlitAPIException)。
_WIDGET_PREFIX = {"verdict": "vd", "review_status": "stt"}


def _sync_rail_widget(idx, field, value):
    """把改動同步到 Rail widget 的 session_state key(單一真相:熱鍵改值後 Rail 顯示一致;AC10)。
    在 Rail widget 於本 run 被建立『之前』設定才合法;nav 處理在中欄、Rail 在右欄之後 + 立即 rerun,故安全。"""
    wp = _WIDGET_PREFIX.get(field)
    if wp:
        ss[f"{wp}_{idx}"] = value


def _push_change(path, idx, field, old, new):
    """改值即時寫 sidecar + 推入 undo_stack(留近 5)+ 同步 Rail widget。old==new 不記(避免空轉)。"""
    if old == new:
        return
    sc = sidecar.load(path)
    d = sidecar.default()
    d.update(sc)
    d[field] = new
    sidecar.save(path, d)
    ss.undo_stack.append({"path": path, "idx": idx, "field": field, "old": old, "new": new})
    del ss.undo_stack[:-5]  # 只留近 5 筆(設計 §3.6)
    _sync_rail_widget(idx, field, new)


def _handle_nav(ev, cur, total):
    """處理 viewer 元件鍵盤 nav 事件(設計 §3.4 鍵位表 / §3.5 autosave / §3.6 undo)。"""
    action = ev.get("action")
    value = ev.get("value")
    if action == "next":
        ss.idx = min(total - 1, ss.idx + 1)
        st.rerun()
    elif action == "prev":
        ss.idx = max(0, ss.idx - 1)
        st.rerun()
    elif action == "verdict":
        sc = sidecar.load(cur["path"])
        if value in tagging.VERDICTS:
            _push_change(cur["path"], ss.idx, "verdict", sc.get("verdict", "unset"), value)
        st.rerun()
    elif action == "status":
        sc = sidecar.load(cur["path"])
        old = sc.get("review_status", "none")
        nxt = (_STATUS_CYCLE[(_STATUS_CYCLE.index(old) + 1) % len(_STATUS_CYCLE)]
               if old in _STATUS_CYCLE else "need_review")
        _push_change(cur["path"], ss.idx, "review_status", old, nxt)
        st.rerun()
    elif action == "bookmark":
        sc = sidecar.load(cur["path"])
        old = bool(sc.get("bookmarked", False))
        _push_change(cur["path"], ss.idx, "bookmarked", old, (not old))
        st.rerun()
    elif action == "undo":
        if ss.undo_stack:
            e = ss.undo_stack.pop()
            tgt = max(0, min(total - 1, _path2idx.get(e["path"], e["idx"])))
            sc = sidecar.load(e["path"])
            d = sidecar.default()
            d.update(sc)
            d[e["field"]] = e["old"]
            sidecar.save(e["path"], d)
            _sync_rail_widget(tgt, e["field"], e["old"])
            ss.idx = tgt  # 撤銷會跳轉(設計 §3.6,刻意)
            # toast 用 pending 模式:本 run 緊接 st.rerun() 會在 toast 提交前撕掉本 run,
            # 故把訊息存進 session_state,下一個『正常完成』的 run 開頭再 st.toast 顯示。
            ss["_pending_toast"] = f"已撤銷:{Path(e['path']).name} {e['field']} → {e['old']}"
        else:
            ss["_pending_toast"] = "無可撤銷"
        st.rerun()


# ============================== 頂列 Command Bar(導覽 + 控制)==============================
# 控制只剩:導覽(⟵ ⟶ 跳頁)+ ⭐書籤 + 信心門檻 slider + Object 類別 下拉。
# User 本輪回饋:移除信心門檻旁 [−][＋] 鈕、移除「顯示k/n·可撤N」文字;新增『Object 類別』下拉(放信心門檻旁,單選/全部)。
# 偵測框恆顯示,由『信心門檻 + Object 類別』過濾(顯示框數/可撤筆數改由 P1 探針 data-shown-k/n、data-undo-n 機器讀)。
_USER_MANUAL = """### 📖 YOLO Image Viewer — 使用手冊

**載入資料(左側『資料來源』)**
- **影像資料夾**:選含影像的夾;支援 YOLO 切分佈局(自動偵測 `images/` 子夾)。標註自動找同層或 `labels/` 子夾。
- 可按 **📁** 用選的(原生資料夾對話框)。
- 標註支援 **YOLO `.txt`** 與 **`.json`**;類別名自動讀 `data.yaml` / `classes.txt`。

**檢視 / 導覽**
- 上一張 / 下一張 / 跳頁;鍵盤 **←/→** 切張。
- 主圖:**滾輪縮放**、拖曳平移、**Shift+拖** 框 ROI、**點擊** 取像素值。
- 偵測框**恆顯示**(類別色 + `類別 信心` 標籤);**信心門檻** 過濾;**Object 類別** 下拉選一種或全部。
- **排序**(縮圖牆上方):by 檔名 / by 信心(高→低 / 低→高);旁邊會顯示目前信心範圍內符合的張數。

**標記(鍵盤)**
- **1 / 2 / 3** = 判定 true_defect / false_alarm / reflection
- **r** = 切換 review 狀態 · **b** / 空白 = 書籤 · **u** = 復原

**比較模式(🔀 兩圖疊圖比較)**
- 在左側縮圖牆每張縮圖**左下角**點一下標記圖示,標記 2 張影像(①藍 / ②橘,最多同時 2 張;
  再點第 3 張會把最舊那張換掉)。
- 標記滿 2 張後開啟「🔀 比較模式」,可切換**像素疊合**(並排/差異/混合)或
  **偵測框疊合**(兩張影像各自的偵測框疊在一起,A 藍 / B 橘)。
- 兩張影像不需同尺寸,尺寸不同時第二張會縮放對齊第一張。
"""
# 用 st.dialog(modal)而非 popover:dialog 內容只在『開啟時』才進 DOM,關閉時不存在 →
# 手冊內提到的控制名(如『信心門檻』粗體)不會被 E2E 的 get_by_text 誤命中為隱藏元素(實測 popover 會)。
@st.dialog("📖 YOLO Image Viewer — 使用手冊", width="large")
def _show_manual():
    st.markdown(_USER_MANUAL)


# ★ 修 bug(同 §4.l 那個成因,2026-07-04):兩個 toggle 必須搶在**任何**可能呼叫 st.rerun()
# 的元件之前實例化(含本列的「❓使用手冊」——st.dialog 開啟也會觸發 rerun——與再下面 Command Bar
# 的 ⟵/⟶/跳頁/⭐)。實測重現:Focus Object 開啟後按「下一張」,curFocusBbox 在新圖變成 None
# (探針證實,session_state 被孤兒 widget 清理打回預設 False)。故 toggle 呼叫必須排在 manual_btn
# 按鈕之前(程式碼執行順序,與下面 st.columns 的視覺欄位順序無關)。
# User 回饋:標題/兩個 toggle/使用手冊 合併成一列(說明文字移到 help= 滑鼠懸停提示,不佔版面)。
_top = st.columns([0.34, 0.19, 0.17, 0.14, 0.16], gap="small", vertical_alignment="center")
_top[0].markdown("##### 🖼️ YOLO Image Viewer")
# 🎯 Focus Object 模式(2026-07-04,User:「自動放大到這張圖最高 confidence 的 object,
# 幫助快速看 YOLO 判斷結果」)。ON 時每次切圖 / 改信心門檻 / 改 Object 類別(kept 因而改變)
# 都會蓋掉既有的『zoom/pan 跨切張保存』(M7a),改為自動 fit 到目前顯示框(kept)裡信心最高的
# 那一個(含邊界留白,見 viewer_component focusOnBbox);kept 為空(該圖無框或全被篩掉)→
# 無 focus 目標,退回一般 fit-to-image,不崩潰。標籤含『Focus Object』供 E2E 命中。
_top[1].toggle("🎯 Focus Object", key="focus_object_on",
               help="開啟後每次切圖自動放大到目前顯示框裡信心最高的那個,幫助快速看 YOLO 判斷結果。")
# 🔀 比較模式入口 toggle。標籤含『比較模式』供 E2E 命中。
# User 版面回饋(可發現性):比較模式的入口是縮圖左下角的小圖示,不易發現;在 toggle 標籤上
# 直接顯示目前已標記張數(N/2),進比較模式前就看得到進度、更好上手(仍含『比較模式』子字串)。
_cmp_n = len(ss.get("cmp_marks", []))
_cmp_lbl = f"🔀 比較模式 · 已標記 {_cmp_n}/2" if _cmp_n else "🔀 比較模式"
_top[2].toggle(_cmp_lbl, key="compare_on",
               help="在左側縮圖牆標記兩張影像(左下角圖示),疊圖比較像素或偵測框。")
if _top[3].button("❓ 使用手冊", type="tertiary", key="manual_btn"):
    _show_manual()
# Object 類別下拉選項(_all_classes)與目前選值(_cls_sel_raw)已於 shown_items 組裝前算好、
# 消毒過(見上方「Object 類別下拉選項」區塊),此處不重算——理由同信心門檻:widget 只負責畫,
# 值已由 session_state key 跨 rerun 持久。
# 信心門檻 slider 欄需夠寬(過窄會使鍵盤 ArrowRight 微調不可靠 — 見 ROADMAP 2026-06-26)。
# 2026-07-05(User 版面回饋:slider 佔 ~55% 列寬偏奢侈,縮到 ~1/3):由 3.2 收斂到 2.6
# (約 40% 列寬)——刻意保守而非直接砍到 1/3(2.0 附近),留足鍵盤微調寬度以免重蹈 2026-06-26
# 那個『slider 太窄 → ArrowRight 單步不可靠』的歷史 flaky;類別欄同步微調 1.35→1.5 平衡版面。
bar = st.columns([0.8, 0.8, 0.45, 0.4, 2.6, 1.5], vertical_alignment="center")

# ★ 修 bug(User 回報「filter 切下一張就不見了」,2026-07-04):bar[4]/bar[5] 必須在
#   bar[0]/bar[1]/bar[2]/bar[3] 任何『可能呼叫 st.rerun() 提早結束本輪』的按鈕**之前**實例化。
#   Streamlit 對『本輪指令碼執行到 stop 為止都沒被呼叫到』的 keyed widget 會清掉其 session_state
#   (孤兒 widget 狀態清理);⟵/⟶/跳頁/⭐ 的 handler 若排在 bar[4]/bar[5] 之前,按下後
#   st.rerun() 會在抵達 bar[4]/bar[5] 之前就結束本輪 → 下一輪它們被判定為「本輪未出現」而清空,
#   值打回預設(信心門檻回全開、Object 類別回全部)。實測重現:設信心下界後按「下一張」,
#   下界立即歸零。修法:讓這兩個 widget 的**實例化**(非僅讀值)搶在任何 nav 按鈕之前執行——
#   `st.columns` 的視覺欄位順序只由 `bar = st.columns([...])` 當下決定,與『之後往哪個 bar[i]
#   寫入』的程式碼順序無關,故此處對 bar[4]/bar[5] 提前呼叫不影響版面(仍在原本欄位)。
# 信心門檻 slider(User:移除旁邊 [−][＋] 鈕,只留滑桿;2026-07-04 契約演進:單值→雙界 range slider,
# 同時卡縮圖牆/導覽清單,見 _in_conf_range)。回傳值不接(conf_lo/conf_hi 已於 shown_items 組裝前讀好,
# 同一 rerun 內兩者必然一致,沿用既有「先讀後畫」慣例)。
bar[4].slider("信心門檻", 0.0, 1.0, (conf_lo, conf_hi), 0.01, key="footer_conf_thr")
# Object 類別 下拉(User:放信心門檻旁;選『全部』或單一類別 → 只畫該類別框,現在也一併觸發
# 清單 triage,見 §7 擴充)。選項/消毒已提前算好(_all_classes/_cls_sel_raw),此處只負責畫。
bar[5].selectbox("Object 類別", ["全部"] + _all_classes, key="cls_filter")
overlay_classes = _sel_classes

if bar[0].button("⟵ 上一張", width=_STRETCH):
    ss.idx = max(0, ss.idx - 1)
    st.rerun()
if bar[1].button("下一張 ⟶", width=_STRETCH):
    ss.idx = min(total - 1, ss.idx + 1)
    st.rerun()
if total > 1:
    jump = bar[2].number_input("跳到第幾張", 1, total, ss.idx + 1, label_visibility="collapsed",
                               help="跳到第幾張(輸入頁碼)")
    if jump - 1 != ss.idx:
        ss.idx = jump - 1
        st.rerun()
pos.set(folder, ss.idx)
cur = shown_items[ss.idx]
_cur_sc = sidecar.load(cur["path"])
# ⭐ Bookmark(頂列 toggle button,讀寫 sidecar);與鍵盤 b/空白鍵走同一 _push_change 路徑(入 undo)。
_bk_on = bool(_cur_sc.get("bookmarked", False))
if bar[3].button("⭐" if _bk_on else "☆", key="bk_btn", width=_STRETCH,
                 help="Bookmark(熱鍵 b / 空白鍵)"):
    _push_change(cur["path"], ss.idx, "bookmarked", _bk_on, (not _bk_on))
    st.rerun()
# kept(過濾後偵測):偵測框恆顯示,由信心門檻(雙界)+ Object 類別過濾;主 viewer dets 與 P1 探針
# data-shown-k 共用。改雙界內嵌過濾(比照比較模式 _cmp_filter),不擴充 overlay.filter_detections 的單下界契約。
kept = _cmp_filter(cur["detections"], conf_lo, conf_hi, overlay_classes)

# ============================== 🧰 CV 顯示調整工具箱(純顯示層;設計 25_imgadjust.md + 20_*.md §3.14)==============================
# User:「增加一個 tool box,平常折疊,裡面是CV常用功能(調亮度對比之類),方便看圖」;澄清後鎖定
# 範圍:只影響『畫面』,不影響偵測/判定/匯出;只套用在主 viewer(不含左側縮圖牆)。
# 切圖(ss.idx 改變)時自動全部關閉、恢復原本顯示(需求 1_user_needs/06_cv_toolbox.md §2)。
# ★ expander 內容『每輪都照樣執行』(只是視覺上收合/展開,非 Python if 條件式隱藏該段程式碼)——
#   與縮圖牆收合(_left_w≈0)那種『仍要渲染但視覺隱藏』同理,不是本 session 已知的『孤兒 widget
#   清理』(§4.l,那是『這輪程式碼真的沒跑到某 widget』才會觸發);故本段可安全放在此處,
#   不受 compare_on / thumb_collapsed 影響,永遠實例化。
# 2026-07-05(User 版面回饋:sidebar 利用率過低):把工具箱從主舞台『搬進 sidebar』——User 原話
#   「工具箱在 sidebar 也符合『看圖時順手調』的使用情境」。用 `st.sidebar.expander(...)` 讓它
#   『渲染在 sidebar』但『程式碼仍在此處執行』(ss.idx 已於上方定案、§4.l 執行順序不變;
#   避免移到 sidebar 區塊 466 行時 ss.idx 尚未定案的順序陷阱)。效果:主舞台少一整列全寬 expander、
#   主圖上移;原本空盪的 sidebar 被填滿。誠實界線:sidebar 較窄(~300px),內部滑桿較擠但可用
#   (工具箱屬次要/偶用功能,可接受)。
if ss.get("_adj_last_idx") != ss.idx:
    for _k in ("adj_stretch_on", "adj_gamma_on", "adj_bc_on", "adj_eq_on",
               "adj_invert_on", "adj_thresh_on", "adj_canny_on"):
        ss[_k] = False
    ss["_adj_last_idx"] = ss.idx

with st.sidebar.expander("🧰 CV 顯示調整工具箱(僅影響顯示,不影響判定/匯出)", expanded=False):
    st.caption("以下調整只影響你目前看到的主圖畫面(不含左側縮圖牆);不會改變偵測框判定,"
               "也不會存進匯出檔案。切換影像會自動全部關閉、恢復原本顯示。")
    # 2026-07-05:工具箱搬進較窄的 sidebar 後,原本 2/3 欄並排會讓 checkbox 標籤互相重疊(實測),
    #   改為『單欄垂直堆疊』——sidebar 縱向空間充足、標籤不再擠壓,是窄容器的自然版面。
    st.checkbox("亮度 / 對比", key="adj_bc_on")
    st.slider("亮度", -100, 100, 0, key="adj_brightness_val")
    st.slider("對比", 0.0, 3.0, 1.0, 0.1, key="adj_contrast_val")
    st.checkbox("Gamma", key="adj_gamma_on", help="標準 gamma correction:>1 整體變亮、<1 整體變暗。")
    st.slider("Gamma 值", 0.1, 3.0, 1.0, 0.1, key="adj_gamma_val")

    _eq_help = None if imgadjust.HAS_CV2 else "缺 opencv-python,此功能目前不可用(降級為原圖)"
    st.checkbox("直方圖均衡化", key="adj_eq_on", help=_eq_help)
    st.checkbox("反色 (Invert)", key="adj_invert_on")
    st.checkbox("對比度極限拉伸", key="adj_stretch_on", help="min-max stretch")

    st.checkbox("二值化", key="adj_thresh_on", help="啟用後視為顯示管線終點,忽略其後步驟。")
    st.slider("二值化門檻", 0, 255, 128, key="adj_thresh_val")
    _canny_help = "啟用後視為顯示管線終點,忽略其後步驟。" + \
                  ("" if imgadjust.HAS_CV2 else " 缺 opencv-python,此功能目前不可用(降級為原圖)")
    st.checkbox("Canny 邊緣偵測", key="adj_canny_on", help=_canny_help)
    st.slider("Canny 低門檻", 0, 255, 100, key="adj_canny_low")
    st.slider("Canny 高門檻", 0, 255, 200, key="adj_canny_high")

    # ★ 重設鈕搶在本段**所有**上述 widget 實例化之後才呼叫 st.rerun(),同 §4.l 那條鐵律:
    #   若排在前面,按下後 rerun 會在跑到後面 slider/checkbox 之前結束本輪 → 它們被判定
    #   『本輪未出現』而清空 session_state,值打回預設(信心門檻/Object 類別 bug 同一成因)。
    if st.button("🔄 重設調整(全部關閉)", key="adj_reset_btn"):
        for _k in ("adj_stretch_on", "adj_gamma_on", "adj_bc_on", "adj_eq_on",
                   "adj_invert_on", "adj_thresh_on", "adj_canny_on"):
            ss[_k] = False
        st.rerun()


# ============================== 🔀 比較模式(兩圖疊圖比較;設計 23_compare.md §9)==============================
# User 第四輪裁決:在縮圖牆標記兩張影像(左下角圖示,①藍/②橘),不再需要第二個資料夾。
# 取代舊『雙 model 覆蓋 triage』(modeldiff.py 本體保留未刪、未來可回退,只是 app 不再呼叫)。
_CMP_VIEW_MODES = [("pixel", "🖼️ 像素疊合"), ("box", "📦 偵測框疊合")]
_CMP_PIXEL_MODES = [("side", "並排"), ("diff", "差異"), ("blend", "混合")]
# _cmp_filter 已上移為模組層級共用函式(見「信心雙界過濾」節),供本節與單張模式 kept 共用。


def _render_compare():
    """兩圖疊圖比較(設計 23_compare.md §9):在縮圖牆標記的 2 張影像(①=A 藍 / ②=B 橘),
    切換像素疊合(並排/差異/混合,重用 framecompare)或偵測框疊合(各自的偵測框疊在一起)。"""
    marks = ss.get("cmp_marks", [])
    if len(marks) < 2:
        st.info(f"🔀 **兩圖疊圖比較**:請在左側縮圖牆每張縮圖**左下角**點一下標記圖示,標記兩張影像"
                f"(目前已標記 **{len(marks)}/2** 張)。第 1 張 = A(藍)、第 2 張 = B(橘)。")
        return

    by_name = {it["name"]: it for it in items}
    it_a, it_b = by_name.get(marks[0]), by_name.get(marks[1])
    if it_a is None or it_b is None:
        st.warning("標記的影像已不在目前資料夾清單中,請重新標記。")
        return

    arr_a = _display_rgb(it_a["path"])
    arr_b_raw = _display_rgb(it_b["path"])
    arr_b = _resize_to(arr_b_raw, arr_a.shape[0], arr_a.shape[1])

    c0 = st.columns([1.4, 3.6])
    view_mode = c0[0].selectbox("檢視方式", [k for k, _ in _CMP_VIEW_MODES],
                                format_func=lambda k: dict(_CMP_VIEW_MODES)[k], key="cmp_view_mode")

    if view_mode == "pixel":
        pixel_mode = c0[1].selectbox("疊合方式", [k for k, _ in _CMP_PIXEL_MODES],
                                     format_func=lambda k: dict(_CMP_PIXEL_MODES)[k],
                                     key="cmp_pixel_mode")
        if pixel_mode == "side":
            out = framecompare.side_by_side(arr_a, arr_b)
        elif pixel_mode == "diff":
            out = framecompare.difference(arr_a, arr_b)
        else:
            alpha = st.slider("混合比例(A→B)", 0.0, 1.0, 0.5, 0.01, key="cmp_blend_alpha")
            out = framecompare.blend(arr_a, arr_b, alpha)
        st.image(out, width=_STRETCH, caption=f"🔵 A:{it_a['name']}　🟠 B:{it_b['name']}")
    else:
        c = st.columns([1.6, 1.3])
        lo, hi = c[0].slider("信心範圍(下界–上界)", 0.0, 1.0, (0.0, 1.0), 0.01, key="cmp_conf")
        all_cls = sorted({d.get("cls", "") for d in (it_a["detections"] + it_b["detections"])
                          if d.get("cls")})
        cck = "cmp_cls"
        if cck in ss:  # 去掉已不在選項中的舊選類別(widget 實例化前改 state 合法)
            ss[cck] = [x for x in ss[cck] if x in all_cls]
        sel_cls = c[1].multiselect("Object 類別(空=全部)", all_cls, key=cck) or None

        ka = _cmp_filter(it_a["detections"], lo, hi, sel_cls)
        kb = _cmp_filter(it_b["detections"], lo, hi, sel_cls)
        # B 的框座標依 A/B 尺寸比例縮放(resize 對齊 A 時,框也要跟著縮放才會落在正確位置)。
        sx = arr_a.shape[1] / max(1, arr_b_raw.shape[1])
        sy = arr_a.shape[0] / max(1, arr_b_raw.shape[0])
        kb_scaled = [{"bbox": [b["bbox"][0] * sx, b["bbox"][1] * sy,
                               b["bbox"][2] * sx, b["bbox"][3] * sy],
                     "cls": b.get("cls", ""), "conf": b.get("conf", 0.0)} for b in kb]
        base = framecompare.blend(arr_a, arr_b, 0.5)
        out = overlay.draw(base, ka, color=(0, 160, 255), thickness=2, draw_label=True)   # A = 藍
        out = overlay.draw(out, kb_scaled, color=(255, 90, 0), thickness=2, draw_label=True)  # B = 橘
        st.image(out, width=_STRETCH, caption=(
            f"🔵 A({it_a['name']}):{len(ka)} 框　🟠 B({it_b['name']}):{len(kb)} 框"))

    if st.button("✖️ 清除標記", key="cmp_clear_marks"):
        ss.cmp_marks = []
        st.rerun()

    # --- 回寫 compare 統計供 P1 探針(穩定數字,E2E 機器讀;設計 §5 P1 機器讀面)---
    ss["_cmp_probe"] = {"view_mode": view_mode}



# ============================== Stage 兩欄:縮圖牆 | 主 viewer / 比較區塊 ==============================
# 縮圖牆收合旗標控制欄寬(收成 0 寬把寬度讓回 viewer);旗標跨 rerun/跨圖持久(M7a-AC4)。
# 2026-07-05:比較模式改為「在主縮圖牆標記兩張影像」(設計 23_compare.md §9),主縮圖牆
# 不再因 compare_on 而隱藏;只有中欄在 compare_on 時切換成疊圖比較視圖(見下方 with center)。

# ★ 修 bug(User 回報「收合縮圖後再也展開不回來」+「版面跑掉、文字變直排」,2026-07-04,
# 實測用 bounding_box 確認:收合後「展開縮圖」鈕 width=0、is_visible=False,真的卡死不是誤會)。
# 根因:收合/排序/符合張數 原本跟縮圖格一起放在同一個 `left` 欄,而 `left` 欄寬會被
# `_left_w=0.0001` 擠到近乎 0——連這三個控制項本身都被擠壞。修法:控制項獨立一組
# **不隨收合狀態變窄**的欄,縮圖格本身(下面的 left/center)才依 `_left_w` 收合——
# 即「控制項」與「內容格」分兩層。
# 2026-07-05(23_compare.md §9):比較模式改為「在主縮圖牆標記兩張影像」,主縮圖牆
# **不再因 compare_on 而隱藏**(否則使用者進了比較模式就沒地方改標記)——只依 thumb_collapsed 收合。
# 2026-07-05(User 版面回饋):排序 / 符合張數 / 收合鈕 原本在窄的左欄裡『垂直堆疊三列』,
# 右側大片全空、白白佔掉三列高度。改成『單一橫向工具列』(排序 | 收合鈕 | 符合張數),
# 收回約兩列垂直空間、主圖上移。仍是獨立於下方會收合的 stage 欄的一列 → 不隨收合變窄
# (thumbwall_collapse_recovery 契約:收合後排序寬>40、收合鈕寬>20 仍成立——各子欄權重夠寬)。
_ctrl = st.columns([1.6, 1.5, 3.0, 3.4], vertical_alignment="bottom")
# 排序下拉(標籤『排序』可見,供 widget_state/collapse_recovery 測試以 has_text 命中)。
_ctrl[0].selectbox("排序", ["檔名", "信心(高→低)", "信心(低→高)"], key="sort_mode",
                   help="縮圖牆與導覽順序:by 檔名 或 by 信心(高→低 / 低→高)")
# 收合 toggle(名稱含『縮圖』+收合語義,供 M7a-AC4 定位)——恆在這個安全寬度欄內,
# 收合後仍可正常點擊展開,不會卡死。★ 排在 selectbox 之後才可能呼叫 st.rerun()(§4.l:
# sort_mode 已先實例化,不會被收合的 rerun 判成孤兒 widget 而清空)。
_lbl = "▸ 展開縮圖" if ss.thumb_collapsed else "◂ 收合縮圖"
if _ctrl[1].button(_lbl, key="toggle_thumb", width=_STRETCH):
    ss.thumb_collapsed = not ss.thumb_collapsed
    st.rerun()
# 目前信心範圍底下還有多少張影像(全開時 = 資料夾總數;零額外開關的全開/篩選中兩態指示器)。
_ctrl[2].caption(f"此信心範圍內符合:**{total} / {len(items)}** 張")

_left_w = 0.0001 if ss.thumb_collapsed else 0.85
left, center = st.columns([_left_w, 6.6])

# -------- 左欄:縮圖牆本體(可收 0 寬;比較模式仍顯示,供標記兩圖用)--------
with left:
    if not ss.thumb_collapsed:
        import base64 as _b64
        # ★ M7a §效能(PerfC 基礎 + 連改門檻不卡):縮圖牆的『燒框』只跟『顯示偵測框開關』走,
        #   不跟『信心門檻 slider』的每一格走 —— 否則每按一格 slider 都觸發縮圖牆 iframe 重渲染
        #   round-trip,serialize WebSocket,使連按 slider 的 widget 更新被丟棄(M7a-AC5 連改即時失效)。
        #   縮圖以固定門檻 0.0 燒『全部偵測框』(開關 on 時),主 viewer 的 k 計數才是 conf 即時反映處。
        #   on/off 切換仍即時改縮圖 src(AC15/AC18);conf 改動只重算主 viewer,不重建整牆。
        _TW_CONF = 0.0
        _marks = ss.get("cmp_marks", [])
        tw_items = []
        for i, it in enumerate(shown_items):
            s = it["sidecar"]
            mark = ("⭐" if s.get("bookmarked") else "") + ("✓" if tagging.is_reviewed(s) else "")
            nd = len(it["detections"])
            png = _thumb(it["path"], dets=it["detections"], show=show_overlay,
                         conf_thr=_TW_CONF, classes=overlay_classes)
            img_url = "data:image/png;base64," + _b64.b64encode(png).decode("ascii")
            cmpmark = "1" if (_marks and it["name"] == _marks[0]) else \
                      "2" if (len(_marks) > 1 and it["name"] == _marks[1]) else ""
            # label = 檔名(元件在縮圖右上角小字顯示,取代原本的索引數字;User 要在縮圖牆看檔名)。
            tw_items.append({"img": img_url, "label": it["name"], "mark": mark, "nd": nd,
                             "cmpmark": cmpmark})
        # markable=True:縮圖左下角加疊圖比較標記(23_compare.md §9.2);回傳
        # {"type":"select"|"mark","index":int} 依 type 分派 —— select 沿用既有導覽,
        # mark 呼叫 _toggle_cmp_mark(不影響 ss.idx,兩個 click handler 用 stopPropagation 隔開)。
        ev_tw = thumbwall(tw_items, selected=ss.idx, height=620, key="thumbwall", markable=True)
        if ev_tw is not None:
            _tw_idx = ev_tw["index"]
            if ev_tw["type"] == "mark":
                if 0 <= _tw_idx < len(shown_items):
                    _toggle_cmp_mark(shown_items[_tw_idx]["name"])
                    st.rerun()
            elif _tw_idx != ss.idx and 0 <= _tw_idx < total:
                ss.idx = _tw_idx
                st.rerun()

# -------- 中欄:比較模式 → 雙區塊;否則 → 主 viewer + viewer-footer --------
with center:
    if ss.compare_on:
        _render_compare()
    else:
        w, h, bit, ch = cur["w"], cur["h"], *_meta(cur["path"])[2:]
        # 主 viewer:影像『不燒框』(url=純顯示圖,可能已套用🧰 CV 工具箱的顯示調整);偵測框由元件
        #   畫成『類別色向量框 + cls·conf 文字標籤』—— 與縮圖同 _cls_color 色盤(顏色一致)、
        #   清晰不隨縮放糊化、且顯示類型/信心(User 回饋 B)。
        url = _display_url_adjusted(cur["path"])
        sc = sidecar.load(cur["path"])
        rois_draw = [{"bbox": rr["bbox"], "label": rr.get("label", "")} for rr in sc.get("rois", [])]
        # dets 帶 color(類別色,與縮圖一致)+ cls/conf(元件畫框+文字標籤);kept 已於 Command Bar 算好。
        dets_draw = [{"bbox": d["bbox"], "cls": d.get("cls", ""),
                      "conf": float(d.get("conf", 0.0)), "color": list(_cls_color(d.get("cls")))}
                     for d in kept]
        # 🎯 Focus Object:kept 已依信心門檻(雙界)+ Object 類別過濾,直接在其中找最高 conf
        # 的框(平手取 list 中第一個,`max` 對相等值穩定回傳先出現者,結果可重現)。
        # 三態區分(None=模式關閉沿用 M7a 跨切張保存;[]=模式開但本圖無框→退回 fit,非保留上一張
        # 的殘留 zoom;非空 list=聚焦該框),None 與 [] 不可合併,見 viewer_component 三分支處理。
        focus_bbox = None
        if ss.get("focus_object_on"):
            focus_bbox = list(max(kept, key=lambda d: float(d.get("conf", 0.0)))["bbox"]) if kept else []
        # ★ M7a 固定 key(不含 idx)修 remount + auto_height 最大化;切圖只靠 args.image 改變。
        # ★ M7b:nav_keys=True 啟用鍵盤工作流(←/→/1/2/3/r/b/u)。
        ev = osd_viewer(url, rois=rois_draw, height=720, key="cv_viewer",
                        meta={"name": cur["name"], "idx1": ss.idx + 1, "total": total,
                              "w": w, "h": h, "bit": bit, "channels": ch},
                        dets=dets_draw, auto_height=True, nav_keys=True, focus_bbox=focus_bbox)
        if isinstance(ev, dict) and ev.get("n", 0) > ss.get("last_n", 0):
            ss.last_n = ev["n"]
            if ev.get("type") == "click":
                try:
                    val = imgio.value_at(_array(cur["path"]), ev["x"], ev["y"])
                except Exception:
                    val = "(界外)"
                ss.last_click = {"x": ev["x"], "y": ev["y"], "val": val, "zoom": ev.get("zoom")}
            elif ev.get("type") == "roi":
                sidecar.save(cur["path"], sidecar.add_roi(sc, ev["bbox"]))
                st.rerun()
            elif ev.get("type") == "nav":
                _handle_nav(ev, cur, total)  # 內含對應 st.rerun()

        # 16-bit 影像保留一行語義界線(hover=顯示值、點擊=真值)—— 誠實物理界線(設計 §6);8-bit 不顯示。
        if bit > 8:
            st.caption("ℹ️ 16-bit 影像:hover RGB = 顯示值(8-bit 顯示);點擊取真值")
        # 點擊後的像素值資訊(僅在點擊時出現,平時不佔位)。
        lc = ss.get("last_click")
        if lc:
            st.info(f"📍 ({lc['x']}, {lc['y']}) → 像素值 **{lc['val']}**　(zoom {lc['zoom']}×)")

# ============================== 比較模式說明 ==============================
# User 裁決:工具台其餘 tab(標記/相似/聚類/DZI/漏檢/匯出)移除,只留比較;比較改為頂部『🔀 比較模式』
# toggle 進入的兩圖疊圖視圖(在主縮圖牆標記兩張影像;見上方 _render_compare / 設計 23_compare.md §9)。
# 底層模組(framecompare/overlay)重用、modeldiff.py 保留未來可重接。


# ============================== P1 隱藏效能探針(主文件 DOM;Playwright 讀 data-*)==============================
# 設計 §5 效能量測機制 (P1):render 計時 + rerun 計數 + thumb 重算 + 工具台重函式呼叫。
# M7a-AC8 只需『探針存在且 data-* 皆可解析為數字』;PerfA/B/C(M7b/M7c)再據此斷言門檻。
_render_ms = round((time.perf_counter() - _T0) * 1000.0, 2)
# ★ M7b:探針『額外』回寫目前顯示圖的判定狀態(供 test_m7b_e2e 機器讀;設計 §5 P1 已預期 data-verdict)。
# ★ 本輪(資訊徽章移除):進度序號/總數從可見徽章移到探針 data-idx/data-total ——
#   頂列「N / total」文字拿掉後,E2E 的 ready/進度錨點改讀此探針(主文件 DOM,設計 §5 P1 機器讀面)。
_sc_cur = sidecar.load(cur["path"])
_cur_verdict = _sc_cur.get("verdict", "unset")
_cur_status = _sc_cur.get("review_status", "none")
_cur_book = 1 if _sc_cur.get("bookmarked") else 0
# 契約演進(2026-07-04):data-conf 單值拆為 data-conf-lo/hi(雙界,見 20_viewer_workbench_redesign.md §7)。
_cur_conf_lo, _cur_conf_hi = ss.get("footer_conf_thr", (0.0, 1.0))
# ★ compare 第四輪(兩圖疊圖比較,23_compare.md §9.3):探針回寫供 test_compare_e2e 用穩定數字斷言
#   而非脆弱像素。marks-n 不論 compare_on 皆回寫(標記發生在主縮圖牆,與 toggle 正交);
#   view-mode 只在 compare_on 且已標記 2 張時有值,否則空字串。
_cmpp = ss.get("_cmp_probe", {}) if ss.get("compare_on") else {}
st.markdown(
    f"<div id='perf' style='display:none' "
    f"data-render-ms='{_render_ms}' "
    f"data-reruns='{ss.reruns}' "
    f"data-thumb-recalc='{_counters['thumb_recalc']}' "
    f"data-tool-calls='{_counters['tool_calls']}' "
    f"data-verdict='{_cur_verdict}' "
    f"data-status='{_cur_status}' "
    f"data-bookmarked='{_cur_book}' "
    f"data-conf-lo='{_cur_conf_lo}' "
    f"data-conf-hi='{_cur_conf_hi}' "
    f"data-idx='{ss.idx + 1}' "
    f"data-total='{total}' "
    f"data-shown-k='{len(kept)}' "
    f"data-shown-n='{len(cur['detections'])}' "
    f"data-adj-active='{1 if _adjustments_active() else 0}' "
    f"data-undo-n='{len(ss.undo_stack)}' "
    f"data-cmp-marks-n='{len(ss.get('cmp_marks', []))}' "
    f"data-cmp-view-mode='{_cmpp.get('view_mode', '')}'></div>",
    unsafe_allow_html=True,
)
