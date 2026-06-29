"""生死點 spike(非契約層,throwaway):
證明在「獨立 Streamlit」裡,OpenSeadragon 能用滑鼠滾輪縮放(client-side、不 rerun),
且點擊的影像座標 + 當前 zoom 能透過宣告式元件回傳 Python。

跑法:  streamlit run spike/viewer_spike.py
過關判準:用滾輪在圖上縮放後,點一下格線交點 → 下方出現「Python 收到點擊:影像座標 (x,y),縮放 N×」,
         且 zoom 不是 1.0(代表滾輪縮放確實改變了 client 狀態、值也回到了 Python)。
"""
import base64
import io
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw

st.set_page_config(page_title="OSD spike", layout="wide")
st.title("Spike:OpenSeadragon in Streamlit(滾輪縮放 + 座標回傳 Python)")

# 宣告式元件(path 指向手寫 static index.html;無 React/npm build)
_osd = components.declare_component("osd_viewer", path=str(Path(__file__).parent / "osd_component"))


@st.cache_data
def sample_image_data_url(w: int = 1200, h: int = 900) -> str:
    """產生一張有格線/座標標記的測試圖,轉成 base64 data URL(spike 免 static server)。"""
    img = Image.new("RGB", (w, h), (20, 20, 30))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 100):
        d.line([(x, 0), (x, h)], fill=(60, 60, 80))
        d.text((x + 2, 2), str(x), fill=(150, 150, 180))
    for y in range(0, h, 100):
        d.line([(0, y), (w, y)], fill=(60, 60, 80))
        d.text((2, y + 2), str(y), fill=(150, 150, 180))
    d.ellipse([500, 350, 700, 550], outline=(0, 200, 0), width=4)
    d.text((520, 360), "ROI", fill=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


st.caption("滑鼠滾輪在圖上縮放(client-side,不會 rerun);點圖會把『影像座標 + 當前 zoom』回傳 Python ↓")
value = _osd(image=sample_image_data_url(), key="osd")

st.subheader("元件回傳給 Python 的值")
st.write(value if value else "(還沒點;先滾輪縮放,再點一下格線交點試試)")
if isinstance(value, dict) and value.get("type") == "click":
    st.success(
        f"✅ Python 收到點擊:影像座標 ({value['x']},{value['y']})、"
        f"縮放 {value['zoom']}×、第 {value['n']} 次 "
        f"{'(zoom≠1 → 滾輪縮放成立)' if abs(value['zoom'] - 1.0) > 1e-6 else '(先滾輪縮放再點,zoom 會≠1)'}"
    )
