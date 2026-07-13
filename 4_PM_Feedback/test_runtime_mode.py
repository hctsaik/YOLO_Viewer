from runtime_mode import default_safe_mode

# 契約演進(2026-07-13,User 裁決):預設由「安全模式」改回「完整模式」。
# 理由:安全模式沒有 OpenSeadragon,滾輪不縮放、不能拖曳/框選 ROI/點像素值——把它當全域預設,
# 等於讓每台正常機器都吃降級體驗。受限網路的那台改用 run_safe.bat / 側欄開關明確 opt-in。
# 這是錨點遷移不是放寬斷言:「明確要求安全模式時必須是安全模式」的檢查原封不動保留在下面。


def test_full_mode_is_the_default_without_environment_override():
    assert default_safe_mode({}) is False


def test_safe_mode_requires_explicit_opt_in():
    for value in ("1", "true", "True", "yes", "on"):
        assert default_safe_mode({"CVR_SAFE_MODE": value}) is True


def test_falsy_overrides_keep_full_mode():
    for value in ("0", "false", "False", "no", "off", "", "   "):
        assert default_safe_mode({"CVR_SAFE_MODE": value}) is False
