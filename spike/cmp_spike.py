"""生死點 spike(throwaway,非契約層):同一 iframe 內雙 OSD + 雙向 viewport 連動。
驗 V3 比較功能最大物理風險(ROADMAP 多次明令『開工前先補』)。

跑法:  streamlit run spike/cmp_spike.py --server.port 8788 --server.headless true
驗證:  python spike/cmp_verify.py   (playwright,需先把 app 跑起來)
"""
import base64
import io
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="cmp spike", layout="wide")

_comp = components.declare_component(
    "cmp_viewer", path=str(Path(__file__).parent / "cmp_component"))


@st.cache_data
def make_img(letter, color, w=900, h=700):
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", 320)
    except Exception:
        font = ImageFont.load_default()
    try:
        bb = d.textbbox((0, 0), letter, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((w - tw) / 2 - bb[0], (h - th) / 2 - bb[1]), letter,
               fill=(255, 255, 255), font=font)
    except Exception:
        d.text((w / 2, h / 2), letter, fill=(255, 255, 255))
    for gx in range(0, w, 100):
        d.line([(gx, 0), (gx, h)], fill=(0, 0, 0))
    for gy in range(0, h, 100):
        d.line([(0, gy), (w, gy)], fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


st.title("cmp spike — linked dual-OSD")
img_a = make_img("A", (40, 80, 200))
img_b = make_img("B", (200, 60, 40))

_comp(image_a=img_a, image_b=img_b, key="cmp", default=None)

st.caption("在左(A)滾輪縮放/拖曳,右(B)應同步;反之亦然。playwright 驗證見 spike/cmp_verify.py")
