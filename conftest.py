"""U-Net 測試基礎設施(由 PM 擁有,PG 唯讀):
- 讓 4_PM_Feedback/ 能 import 5_PG_Develop/ 的模組
- 註冊 e2e marker;缺 playwright 時讓 e2e 測試在收集階段就 skip(不空等 server)
- 提供 E2E harness fixtures(只有 e2e 測試請求時才啟動 App;單元測試完全不受影響)
"""
import os, sys, subprocess, time, urllib.request
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "5_PG_Develop"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "e2e: 真實端對端驗收(/ux-test 或人觸發,不進 PG 自主修綠迴圈)")


def pytest_collection_modifyitems(config, items):
    try:
        import playwright.sync_api  # noqa: F401
        return
    except Exception:
        skip = pytest.mark.skip(
            reason="未安裝 playwright(pip install playwright && playwright install chromium)")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip)


# ===== E2E harness(TODO:改成你的 App 啟動方式;預設假設 Streamlit)=====
E2E_CMD = os.environ.get(
    "UNET_E2E_CMD",
    sys.executable + " -m streamlit run 5_PG_Develop/app.py "
    "--server.headless true --server.port 8765")
E2E_URL = os.environ.get("UNET_E2E_URL", "http://localhost:8765")


def _wait_ready(url, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def app_server():
    """啟動 App、輪詢 ready、yield base_url、收尾關閉。只有 e2e 測試會用到。"""
    # E2E 位置記憶隔離:session 啟動前清掉 .cvr_state.json,避免前一輪/前一檔導航留下的 idx
    # 污染『用起始圖』的測試(歷史 flaky 根因,見 ROADMAP 2026-06-25;App 啟動無檔 → 從 idx 0 起)。
    _state = os.path.join(os.path.dirname(__file__), ".cvr_state.json")
    try:
        if os.path.exists(_state):
            os.remove(_state)
    except OSError:
        pass
    # The legacy interaction suite exercises the iframe-based full viewer.
    # Production defaults to safe mode, so make this test intent explicit.
    env = dict(os.environ, CVR_SAFE_MODE="0")
    proc = subprocess.Popen(E2E_CMD, shell=True, cwd=os.path.dirname(__file__), env=env)
    try:
        if not _wait_ready(E2E_URL):
            proc.terminate()
            pytest.skip("E2E App 未在時限內 ready:" + E2E_URL)
        yield E2E_URL
    finally:
        # Windows + shell=True:proc 是 shell,terminate() 只殺 shell、留下 streamlit 子程序
        # 佔住埠 → 下一輪連到殘留 server 造成假紅。用 taskkill /T 殺整個程序樹。
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


@pytest.fixture
def page(app_server):
    """playwright 真實瀏覽器頁面(function scope)。"""
    sync_api = pytest.importorskip("playwright.sync_api", reason="需要 playwright")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(app_server)
        yield pg
        browser.close()
