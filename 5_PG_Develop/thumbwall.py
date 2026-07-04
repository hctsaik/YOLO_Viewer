"""縮圖牆的 Streamlit 包裝(宣告式元件,無 React build)。

設計:3_Architect_Design/19_viewer_ux.md §2.2 / §2.2a;markable 見 23_compare.md §9.2。
渲染一排可點縮圖(整張 <img> 可點)+ 角標(label)+ mark(⭐/✓)+ 偵測數徽章(nd>0)+
兩圖疊圖比較標記(markable=True 時,左下角 ①/②)。

items: list[dict],每筆 = {
    "img":     str,  # 縮圖 data URL(已含框,由 app 用 imgio.to_data_url 產生)
    "label":   str,  # 角標文字,如 "3"
    "mark":    str,  # ⭐/✓ 標記(可空)
    "nd":      int,  # 偵測框數(0 → 不顯示徽章)
    "cmpmark": str,  # "1"/"2"/""(markable=True 時,左下角疊圖比較標記;可空)
}
selected: 目前選中的 index(高亮邊框用)。

回傳值(JS → Python,依 markable 分岐):
- markable=False(預設,向後相容):回傳被點縮圖的 index(int)或 None(本 run 無點擊/仍是舊值)。
- markable=True:回傳 {"type": "select"|"mark", "index": int} 或 None——"select"=整格點擊(導覽),
  "mark"=左下角標記圖示點擊(疊圖比較用);呼叫端自行依 type 分派,不會互相觸發
  (元件端用 stopPropagation 隔開兩個 click handler)。
去重靠 n 單調遞增(同 viewer 慣例),避免 rerun 重複觸發同一次點擊。去重計數器存在
`st.session_state`(每個 Streamlit session 各自獨立),不是模組層級 Python 全域字典——
後者會被同一伺服器行程內的「不同瀏覽器分頁/session」共用,導致跨 session 的去重計數污染
(2026-07-05 debug 兩圖疊圖比較 E2E 時發現:同一 pytest session 內多個測試各開新分頁但共用
同一伺服器行程,前一個測試的點擊次數會讓下一個測試『新分頁的第一次點擊』被誤判成舊事件而略過)。
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_DIR = Path(__file__).parent / "thumbwall_component"
_component = components.declare_component("cv_thumbwall", path=str(_DIR))
_LAST_N_KEY = "_thumbwall_last_n"


def thumbwall(items, selected: int = 0, height: int = 620, key: str = "thumbwall",
              horizontal: bool = False, markable: bool = False):
    """渲染可點縮圖牆。回傳值見模組 docstring(依 markable 決定 int 或 dict)。

    horizontal=True → 橫向可捲縮圖條(`overflow-x:auto` 原生水平捲軸,整列渲染全部縮圖、
    可快速捲到任一張);label 建議放檔名。預設 False = 縱向縮圖牆(向後相容,主縮圖牆/viewer_ux 不變)。
    markable=True → 每格左下角加疊圖比較標記圖示(①/②),供兩圖疊圖比較功能標記影像。"""
    ev = _component(items=items or [], selected=int(selected), height=int(height),
                    horizontal=bool(horizontal), markable=bool(markable), key=key, default=None)
    if isinstance(ev, dict) and "index" in ev:
        idx = ev.get("index")
        n = ev.get("n", 0)
        last_n = st.session_state.setdefault(_LAST_N_KEY, {})
        last = last_n.get(key, 0)
        if n > last:
            last_n[key] = n
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                return None
            if markable:
                return {"type": ev.get("type", "select"), "index": idx}
            return idx
    return None
