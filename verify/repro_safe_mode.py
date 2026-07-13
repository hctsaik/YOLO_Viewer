"""🛟 安全模式 —— 受限網路下的 red→green 對抗驗證(2026-07-10)。

背景:viewer / thumbwall 是 Streamlit 自訂元件,瀏覽器須另抓 /component/ 資產、在 iframe 內執行
腳本、60 秒內回報 componentReady。現場某些機器上這條路被擋(A=資產被 proxy/防毒攔;B=iframe 內
腳本被端點防護封),元件必然逾時跳「trouble loading」橫幅,且『元件端程式碼修不了』。
安全模式(CVR_SAFE_MODE=1 或側欄開關)完全不走那條路,改為 server 端算繪。

作法沿用 repro_real_proxy.py 的路線:架一個**真 forward proxy**(擋 /component/ → 403),Chromium 真的
走它(--proxy-server),並用**機器 IP** 開(Chromium 只對 localhost 隱含繞過 proxy)。三個情境:

  [S1 normal_blocked] 安全模式 OFF + /component/ 被擋 → **必須看到橫幅**(紅基線;沒紅過的綠不算數)
  [S2 safe_blocked]   安全模式 ON  + /component/ 被擋 → 必須『無橫幅、proxy 上看不到任何 /component/
                      請求、零個 component iframe、影像與縮圖真的算繪』(綠)
  [S3 safe_normal]    安全模式 ON  + 無 proxy(localhost)→ 仍綠(不因加了安全模式而壞掉)

S2 的『零個 /component/ 請求』比「這次沒跳橫幅」更強:一個請求都不發、一個 iframe 都不掛,
環境對 /component/ 或對 iframe 內腳本做什麼都與我們無關 —— A 類與 B 類同時被繞開。

⚠ 不要用 Playwright 的 page.route 來擋:實測只要啟用請求攔截,Streamlit 前端就會停在半路(圖都不算繪),
   會造成假紅/假綠。要觀察請求請用被動的 page.on("request")。

需求:playwright + chromium,且機器要有非 loopback 的 LAN IP(否則印 INCOMPLETE、exit 2,不假綠)。
用法:python verify/repro_safe_mode.py
"""
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PORT = int(os.environ.get("RSM_APP_PORT", "8551"))
PROXY_PORT = int(os.environ.get("RSM_PROXY_PORT", "8899"))
ORIGIN = ("127.0.0.1", APP_PORT)
WAIT_BLOCKED = 67   # > 60s componentReady 逾時;等不夠會誤判「沒重現」(本案踩過的坑)
WAIT_NORMAL = 20    # 安全模式無元件,不需等逾時

MODE = "pass"       # block / pass
_reqs = []
_lock = threading.Lock()


# ---------------- 真 forward proxy(擋 /component/)----------------
def _pipe(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _read_head(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        c = sock.recv(65536)
        if not c:
            return None, b""
        data += c
    h, _, rest = data.partition(b"\r\n\r\n")
    return h, rest


def _handle(client):
    try:
        head, rest = _read_head(client)
        if head is None:
            client.close(); return
        lines = head.split(b"\r\n")
        parts = lines[0].decode("latin1").split(" ")
        if len(parts) != 3:
            client.close(); return
        method, uri, ver = parts
        if method.upper() == "CONNECT":
            origin = socket.create_connection(ORIGIN)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            threading.Thread(target=_pipe, args=(client, origin), daemon=True).start()
            _pipe(origin, client); return
        m = re.match(r"[a-zA-Z]+://[^/]+(/.*)?$", uri)
        path = (m.group(1) or "/") if m else uri
        is_ws = b"upgrade: websocket" in head.lower()
        if "/component/" in path and not is_ws:
            with _lock:
                _reqs.append(path.split("?")[0].rsplit("/", 1)[-1])
        if MODE == "block" and "/component/" in path and not is_ws:
            body = b"blocked by test content-filter proxy"
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                           % len(body) + body)
            client.close(); return
        hdrs = []
        for l in lines[1:]:
            ll = l.lower()
            if ll.startswith(b"proxy-connection:"):
                continue
            if not is_ws and ll.startswith(b"connection:"):
                continue
            hdrs.append(l)
        if not is_ws:
            hdrs.append(b"Connection: close")
        origin = socket.create_connection(ORIGIN)
        origin.sendall(f"{method} {path} {ver}".encode("latin1") + b"\r\n"
                       + b"\r\n".join(hdrs) + b"\r\n\r\n" + rest)
        threading.Thread(target=_pipe, args=(client, origin), daemon=True).start()
        _pipe(origin, client)
    except Exception:
        try:
            client.close()
        except OSError:
            pass


def _serve():
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", PROXY_PORT)); s.listen(128)
    while True:
        c, _ = s.accept()
        threading.Thread(target=_handle, args=(c,), daemon=True).start()


def _lan_ip():
    if os.environ.get("RSM_FORCE_NO_LAN"):
        return None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


# ---------------- app 生命週期 ----------------
def _start_app(safe):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if safe:
        env["CVR_SAFE_MODE"] = "1"
    else:
        env["CVR_SAFE_MODE"] = "0"
    cmd = (f'"{sys.executable}" -m streamlit run 5_PG_Develop/app.py '
           f'--server.headless true --server.port {APP_PORT}')
    proc = subprocess.Popen(cmd, shell=True, cwd=ROOT, env=env)
    for _ in range(60):
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/_stcore/health",
                                      timeout=1).status == 200:
                return proc
        except Exception:
            time.sleep(1)
    proc.terminate(); raise RuntimeError("App 未就緒")


def _stop_app(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    # shell=True 下 streamlit 是子孫程序;確認埠真的釋放,否則下一情境會連到上一個 app(假綠)。
    for _ in range(20):
        try:
            socket.create_connection(("127.0.0.1", APP_PORT), timeout=0.5).close()
        except OSError:
            return
        subprocess.run(f'powershell -Command "Get-NetTCPConnection -LocalPort {APP_PORT} '
                       f'-State Listen -ErrorAction SilentlyContinue | '
                       f'ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}"',
                       shell=True, capture_output=True)
        time.sleep(1)
    raise RuntimeError(f"埠 {APP_PORT} 未釋放")


# ---------------- 情境 ----------------
def _scenario(pw, name, safe, mode, use_proxy, host, wait, shot=None):
    global MODE, _reqs
    MODE = mode
    with _lock:
        _reqs = []
    proc = _start_app(safe)
    seen = []
    try:
        launch = {"proxy": {"server": f"http://127.0.0.1:{PROXY_PORT}"}} if use_proxy else {}
        browser = pw.chromium.launch(**launch)
        page = browser.new_page()
        # 被動觀察,不攔截(攔截會弄壞 Streamlit 算繪 → 假紅/假綠)
        page.on("request", lambda r: seen.append(r.url) if "/component/" in r.url else None)
        try:
            page.goto(f"http://{host}:{APP_PORT}", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        time.sleep(wait)
        body = page.inner_text("body")
        mm = re.search(r"顯示 (\d+) 框", body)
        res = {
            # ⚠ 錨點必須是 Streamlit 橫幅的原句「Your app is having trouble loading the X component.」。
            #   不可只比對 "trouble loading" —— app.py 的非-localhost 條件式提示裡字面就含
            #   「trouble loading the component」,用 IP 開時會誤判成橫幅(已踩過)。
            "banner": "is having trouble loading" in body.lower(),
            "proxy_reqs": len(_reqs),
            "page_reqs": len(seen),
            "comp_iframes": page.locator("iframe[src*='/component/']").count(),
            "imgs": page.locator("img").count(),
            "safe_wall": "安全模式縮圖牆" in body,
            "safe_hud": "安全模式 ·" in body,
            "boxes": int(mm.group(1)) if mm else -1,
        }
        if shot:
            page.screenshot(path=os.path.join(ROOT, shot), full_page=False)
        browser.close()
    finally:
        _stop_app(proc)
    print(f"[{name}] {res}")
    return res


def main():
    lan = _lan_ip()
    if not lan:
        print("INCOMPLETE:本機無非 loopback 的 LAN IP,無法讓 Chromium 真的走 proxy"
              "(localhost 會隱含繞過)。不判綠。")
        return 2

    threading.Thread(target=_serve, daemon=True).start()
    print(f"proxy 127.0.0.1:{PROXY_PORT} → app {ORIGIN};LAN IP = {lan}\n")

    with sync_playwright() as pw:
        s1 = _scenario(pw, "S1 normal_blocked", safe=False, mode="block",
                       use_proxy=True, host=lan, wait=WAIT_BLOCKED)
        s2 = _scenario(pw, "S2 safe_blocked", safe=True, mode="block",
                       use_proxy=True, host=lan, wait=WAIT_BLOCKED, shot="safe_mode_blocked.png")
        s3 = _scenario(pw, "S3 safe_normal", safe=True, mode="pass",
                       use_proxy=False, host="localhost", wait=WAIT_NORMAL, shot="safe_mode_normal.png")

    ok = True
    # S1 紅基線:壞環境 + 安全模式關掉 → 必須壞。它若沒紅,代表沒模擬到故障,S2 的綠就是假綠。
    s1_ok = s1["banner"] and s1["proxy_reqs"] > 0
    ok &= s1_ok
    print(f"\n[S1] 紅基線(OFF + 資產被擋):banner={s1['banner']} "
          f"proxy看到的/component/請求={s1['proxy_reqs']} → "
          f"{'RED as expected' if s1_ok else 'FAIL(沒重現故障,S2 的綠不可信)'}")

    s2_ok = ((not s2["banner"]) and s2["proxy_reqs"] == 0 and s2["page_reqs"] == 0
             and s2["comp_iframes"] == 0 and s2["imgs"] >= 2 and s2["safe_wall"]
             and s2["safe_hud"] and s2["boxes"] >= 1)
    ok &= s2_ok
    print(f"[S2] 安全模式 ON + 同一個壞環境:banner={s2['banner']} "
          f"/component/請求 proxy={s2['proxy_reqs']} page={s2['page_reqs']} "
          f"元件iframe={s2['comp_iframes']} img={s2['imgs']} 縮圖牆={s2['safe_wall']} "
          f"HUD={s2['safe_hud']} 框數={s2['boxes']} → {'GREEN' if s2_ok else 'FAIL'}")

    s3_ok = ((not s3["banner"]) and s3["page_reqs"] == 0 and s3["imgs"] >= 2
             and s3["safe_wall"] and s3["boxes"] >= 1)
    ok &= s3_ok
    print(f"[S3] 安全模式 ON + 正常網路:banner={s3['banner']} /component/請求={s3['page_reqs']} "
          f"img={s3['imgs']} 框數={s3['boxes']} → {'GREEN' if s3_ok else 'FAIL'}")

    print("\n" + ("GREEN — 安全模式在受限網路下可用,且已先證明同環境下不開它必紅"
                  if ok else "RED — 見上方 FAIL 項"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
