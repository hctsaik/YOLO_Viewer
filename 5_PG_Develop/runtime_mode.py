"""Runtime mode selection kept separate from Streamlit for easy regression tests."""

import os


def default_safe_mode(environ=None):
    """Full (component) mode is the default; safe mode is an explicit opt-in.

    契約演進(2026-07-13,User 裁決):安全模式沒有 OpenSeadragon —— 沒有滾輪縮放、沒有拖曳平移、
    沒有 Shift 框選 ROI、不能點取像素值。把它當全域預設,等於每台正常機器都吃降級體驗。
    受限網路的那台機器改用 run_safe.bat(CVR_SAFE_MODE=1)或側欄開關明確 opt-in。
    """
    env = os.environ if environ is None else environ
    return str(env.get("CVR_SAFE_MODE", "0")).strip().lower() in {
        "1", "true", "yes", "on"
    }
