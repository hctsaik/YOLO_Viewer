"""元件「trouble loading」橫幅 —— 受限網路重現 + 加固迴歸工具(2026-07-08)。

自起一個 App(獨立埠,預設 8766),用 Playwright 攔截網路,精準模擬「網路受限電腦」對
viewer/thumbwall 兩個自訂元件的各種攔法,每種等過 Streamlit 的 60s componentReady 逾時
(COMPONENT_READY_WARNING_TIME_MS = 60000)後,判斷是否跳出橫幅。

用途:
  python verify/repro_component_banner.py
  - 印出紅/綠矩陣(哪種網路限制會讓元件壞掉)。
  - 迴歸判定:把 JS 從內嵌 <script> 搬成外部 main.js 之後,#3(內容過濾剝內嵌 script)與
    #4(CSP script-src 'self' 禁內嵌)必須翻綠;若又變紅代表加固退化 → exit 1。
  - #1(整條 /component/ 被擋)、#5(拖過 60s)是環境問題、非程式可修,恆紅、僅供對照。

需求:playwright + chromium(pip install playwright && playwright install chromium)。
"""
import asyncio, os, re, subprocess, sys, time, urllib.request
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("REPRO_PORT", "8766"))
APP = f"http://localhost:{PORT}"
WAIT_MS = 67_000  # 必須 > 60000 才看得到逾時橫幅


async def _abort(route):
    await route.abort()

async def _strip_inline(route):
    r = await route.fetch()
    body = await r.text()
    # 模擬內容過濾 proxy:剝掉 HTML 內嵌 <script>(無 src),保留 <script src=...>
    stripped = re.sub(r"<script>.*?</script>", "<!-- inline removed -->", body, flags=re.S)
    await route.fulfill(response=r, body=stripped)

async def _csp_block_inline(route):
    r = await route.fetch()
    headers = dict(r.headers)
    headers["content-security-policy"] = "script-src 'self'"  # 禁內嵌、允許同源外部
    await route.fulfill(status=r.status, headers=headers, body=await r.body())

async def _delay(route):
    await asyncio.sleep(90)
    try:
        await route.continue_()
    except Exception:
        pass

# (代號, 說明, url pattern, handler, 期望: True=應綠/False=應紅[環境問題])
SCENARIOS = [
    ("0_baseline",          "無限制(對照)",              None,                          None,             True),
    ("1_block_/component/", "擋整條 /component/(環境)",   "**/component/**",             _abort,           False),
    ("2_block_only_osd",    "只擋 openseadragon.min.js",   "**/openseadragon.min.js*",    _abort,           True),
    ("3_strip_inline_JS",   "內容過濾剝內嵌 script",       "**/component/**/index.html*", _strip_inline,    True),
    ("4_CSP_block_inline",  "CSP 禁內嵌 script",           "**/component/**/index.html*", _csp_block_inline, True),
    ("5_delay_90s",         "拖過 60s(環境)",            "**/component/**",             _delay,           False),
]


def _start_app():
    cmd = (f'"{sys.executable}" -m streamlit run 5_PG_Develop/app.py '
           f"--server.headless true --server.port {PORT}")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", CVR_SAFE_MODE="0")
    proc = subprocess.Popen(cmd, shell=True, cwd=ROOT, env=env)
    for _ in range(60):
        try:
            if urllib.request.urlopen(f"{APP}/_stcore/health", timeout=1).status == 200:
                return proc
        except Exception:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("App 未能在 60s 內就緒")


async def _run_one(browser, name, pattern, handler):
    ctx = await browser.new_context()
    page = await ctx.new_page()
    console = []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    if handler:
        await page.route(pattern, handler)
    try:
        await page.goto(APP, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    return name, ctx, page, console


async def _main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        started = await asyncio.gather(*[_run_one(browser, s[0], s[2], s[3]) for s in SCENARIOS])
        print(f"6 情境已載入,等 {WAIT_MS//1000}s(> 60s 逾時)...")
        await asyncio.sleep(WAIT_MS / 1000)
        expect = {s[0]: s[4] for s in SCENARIOS}
        desc = {s[0]: s[1] for s in SCENARIOS}
        regressed = []
        print("\n=== 紅/綠矩陣 ===")
        for name, ctx, page, console in started:
            body = (await page.inner_text("body")).lower()
            banner = "trouble loading" in body
            ok = (not banner)
            mark = "✅無橫幅" if ok else "❌橫幅"
            tag = "" if ok == expect[name] else "  <== 非預期!"
            if expect[name] and banner:
                regressed.append(name)
            sig = next((c for c in console if "error" in c.lower() or "Policy" in c), "")
            print(f"  [{name:20}] {mark}  {desc[name]}{tag}")
            if not ok and sig:
                print(f"        signature: {sig[:90]}")
            await ctx.close()
        await browser.close()
        return regressed


if __name__ == "__main__":
    proc = _start_app()
    try:
        regressed = asyncio.run(_main())
    finally:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        except Exception:
            proc.terminate()
    if regressed:
        print(f"\nREGRESSION: 應綠卻紅的情境 = {regressed}(加固退化)")
        sys.exit(1)
    print("\nGREEN: 可修情境(0/2/3/4)全綠;1/5 為環境問題、恆紅、非程式可修。")
