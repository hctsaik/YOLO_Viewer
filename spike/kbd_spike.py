"""生死點 spike(throwaway,非契約層):image-viewer-first + 鍵盤連切。

用「真實 Streamlit 1.56 + 真實宣告式元件」驗 5 個命題(playwright 實證):
  1. 固定 key="kv" → iframe 跨 rerun 不 remount(__loadCount 恆 ==1);對照 idx-key 會變多。
  2. 元件端 keydown → setComponentValue → app rerun → 切圖,連按不吃首鍵(idx 序列正確)。
  3. rerun 後焦點自動回 viewer(不手動點畫面,第二鍵仍生效;activeElement 在 canvas/osd)。
  4. zoom/pan 跨切張可保存(切圖前存 zoom/center,新影像 open 後還原)。
  5. 焦點守衛:打字(activeElement=INPUT/TEXTAREA)不誤觸熱鍵。

跑法:  streamlit run spike/kbd_spike.py --server.port 8799 --server.headless true
URL 參數 ?keymode=idx 可切到「對照組 idx-key」以證 remount 會發生。
"""
import base64
import io
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="kbd spike", layout="wide")

_comp = components.declare_component(
    "kbd_viewer", path=str(Path(__file__).parent / "kbd_component"))

# 8 張可辨識的純色 + 大編號圖(放記憶體,免 static server)
COLORS = [
    (220, 40, 40), (40, 180, 60), (40, 80, 220), (230, 180, 30),
    (180, 40, 200), (30, 200, 200), (240, 120, 30), (120, 120, 120),
]
N_IMAGES = len(COLORS)


@st.cache_data
def make_images(w: int = 900, h: int = 700):
    urls = []
    try:
        font = ImageFont.truetype("arialbd.ttf", 320)
    except Exception:
        font = ImageFont.load_default()
    for i, c in enumerate(COLORS):
        img = Image.new("RGB", (w, h), c)
        d = ImageDraw.Draw(img)
        # 大數字 = 第 N 張(1-based)
        txt = str(i + 1)
        try:
            bb = d.textbbox((0, 0), txt, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            d.text(((w - tw) / 2 - bb[0], (h - th) / 2 - bb[1]), txt,
                   fill=(255, 255, 255), font=font)
        except Exception:
            d.text((w / 2, h / 2), txt, fill=(255, 255, 255))
        # 角落格線方便看 pan/zoom 是否保住
        for gx in range(0, w, 100):
            d.line([(gx, 0), (gx, h)], fill=(0, 0, 0))
        for gy in range(0, h, 100):
            d.line([(0, gy), (w, gy)], fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        urls.append("data:image/png;base64," +
                    base64.b64encode(buf.getvalue()).decode())
    return urls


IMAGES = make_images()

# 對照組開關:?keymode=idx → 用 idx-key(預期 remount);預設 fixed
keymode = st.query_params.get("keymode", "fixed")
# ?restore=off → 關掉 zoom/pan 還原(命題4 的對照組:證明不還原就會重置回 fit)
restore_enabled = st.query_params.get("restore", "on") != "off"

ss = st.session_state
ss.setdefault("idx", 0)
ss.setdefault("ev_seen", 0)
ss.setdefault("zoom", None)
ss.setdefault("center", None)

st.title(f"kbd spike (keymode={keymode})")
# 焦點守衛測試用:一個位於主文件(非元件 iframe)的 text_input
typed = st.text_input("type-guard 測試輸入框", key="ti", value="")

# 元件 key:fixed → 不含 idx(命題1);idx → 含 idx(對照組,預期 remount)
comp_key = "kv" if keymode != "idx" else f"viewer_{ss.idx}"

cur_color = COLORS[ss.idx]
ev = _comp(
    image=IMAGES[ss.idx],
    idx1=ss.idx + 1,
    total=N_IMAGES,
    color=list(cur_color),
    restore_zoom=ss.zoom if restore_enabled else None,
    restore_center=ss.center if restore_enabled else None,
    height=600,
    key=comp_key,
    default=None,
)

# 處理元件回傳事件:nav(鍵盤切圖)/ state(zoom/center 回灌)
if isinstance(ev, dict):
    n = ev.get("n", 0)
    if n > ss.ev_seen:
        ss.ev_seen = n
        t = ev.get("type")
        if t == "nav":
            # 切圖前把元件回傳的 zoom/center 存起來供下一張還原
            if ev.get("zoom") is not None:
                ss.zoom = ev["zoom"]
            if ev.get("center") is not None:
                ss.center = ev["center"]
            d = ev.get("dir")
            if d == "next":
                ss.idx = (ss.idx + 1) % N_IMAGES
            elif d == "prev":
                ss.idx = (ss.idx - 1) % N_IMAGES
            st.rerun()
        elif t == "state":
            # 純存 zoom/center(無切圖),供 playwright 觀測 round-trip
            if ev.get("zoom") is not None:
                ss.zoom = ev["zoom"]
            if ev.get("center") is not None:
                ss.center = ev["center"]

# playwright 可讀的狀態探針(主文件 DOM,跨 iframe 可讀)
st.markdown(
    f"<div id='probe' "
    f"data-idx='{ss.idx}' "
    f"data-idx1='{ss.idx + 1}' "
    f"data-evseen='{ss.ev_seen}' "
    f"data-typed='{typed}' "
    f"data-zoom='{ss.zoom}' "
    f"data-keymode='{keymode}'>"
    f"idx={ss.idx} (img #{ss.idx + 1}) ev_seen={ss.ev_seen} "
    f"zoom={ss.zoom} typed='{typed}'</div>",
    unsafe_allow_html=True,
)
