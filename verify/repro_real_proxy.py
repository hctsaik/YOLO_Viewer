"""受限網路元件橫幅 —— 『真 forward proxy』重現 + 加固迴歸(2026-07-08)。

與 repro_component_banner.py 的差別:那支用 Playwright page.route(瀏覽器內攔截);本支架一個
『真正的 HTTP forward proxy』,Chromium 真的走它(--proxy-server),忠實模擬「受限網路 + proxy
在路徑上」。自起 App(獨立埠)與 proxy(獨立埠),跑完自清。

驗兩件真實故障/修正:
  [strip] 真 proxy 剝掉 HTML 內嵌 <script>(= 現場 #3)→ 外部 main.js 版必須『無橫幅且完整算繪』
          (main.js/OSD/按鈕圖都被抓)。若跳橫幅 = 加固退化。
  [block+IP] 真 proxy 擋掉 /component/ + 用非 localhost 位址開(= 現場 #1,元件碼不可修)→ 元件必然
          仍被擋(橫幅),但『app 端 guard 指示』必須出現在主頁(引導使用者改用 localhost/加例外)。

需求:playwright + chromium。用法:python verify/repro_real_proxy.py
"""
import os, re, socket, subprocess, sys, threading, time, urllib.request
from collections import Counter
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PORT = int(os.environ.get("RRP_APP_PORT", "8531"))
PROXY_PORT = int(os.environ.get("RRP_PROXY_PORT", "8898"))
ORIGIN = ("127.0.0.1", APP_PORT)
WAIT = 67  # > 60s componentReady 逾時

MODE = "pass"          # 由各情境設定:block / strip / pass
_reqs = []
_lock = threading.Lock()


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
        if method.upper() == "CONNECT":               # https/ws 隧道(websocket 走這)
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
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
            client.close(); return
        hdrs = []
        for l in lines[1:]:
            ll = l.lower()
            if ll.startswith(b"proxy-connection:"):
                continue
            if not is_ws and ll.startswith((b"connection:", b"accept-encoding:")):
                continue  # 拿掉 accept-encoding → 強制未壓縮,strip 才能改寫 HTML
            hdrs.append(l)
        if not is_ws:
            hdrs.append(b"Connection: close")
        origin = socket.create_connection(ORIGIN)
        origin.sendall(f"{method} {path} {ver}".encode("latin1") + b"\r\n" + b"\r\n".join(hdrs) + b"\r\n\r\n" + rest)
        if MODE == "strip" and not is_ws and re.search(r"/component/.*index\.html", path):
            buf = b""
            while b"\r\n\r\n" not in buf:
                c = origin.recv(65536)
                if not c:
                    break
                buf += c
            rh, _, body = buf.partition(b"\r\n\r\n")
            cl = re.search(rb"(?i)content-length:\s*(\d+)", rh)
            if cl:
                while len(body) < int(cl.group(1)):
                    c = origin.recv(65536)
                    if not c:
                        break
                    body += c
            nb = re.sub(r"<script>.*?</script>", "<!-- inline stripped -->",
                        body.decode("utf-8", "replace"), flags=re.S).encode("utf-8")
            rh = re.sub(rb"(?i)content-length:\s*\d+", b"Content-Length: %d" % len(nb), rh)
            client.sendall(rh + b"\r\n\r\n" + nb)
            client.close(); origin.close(); return
        threading.Thread(target=_pipe, args=(client, origin), daemon=True).start()
        _pipe(origin, client)
    except Exception:
        try:
            client.close()
        except Exception:
            pass


def _serve():
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", PROXY_PORT)); s.listen(128)
    while True:
        c, _ = s.accept()
        threading.Thread(target=_handle, args=(c,), daemon=True).start()


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


def _start_app():
    cmd = f'"{sys.executable}" -m streamlit run 5_PG_Develop/app.py --server.headless true --server.port {APP_PORT}'
    proc = subprocess.Popen(cmd, shell=True, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    for _ in range(60):
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/_stcore/health", timeout=1).status == 200:
                return proc
        except Exception:
            time.sleep(1)
    proc.terminate(); raise RuntimeError("App 未就緒")


def _scenario(pw, mode, url):
    global MODE, _reqs
    MODE = mode
    with _lock:
        _reqs = []
    browser = pw.chromium.launch(proxy={"server": f"http://127.0.0.1:{PROXY_PORT}"})
    page = browser.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    time.sleep(WAIT)
    body = page.inner_text("body")
    banner = "trouble loading" in body.lower()
    guard = "偵測到你用非 localhost" in body
    reqs = dict(Counter(_reqs))
    browser.close()
    return banner, guard, reqs


def main():
    lan = _lan_ip()
    proc = _start_app()
    threading.Thread(target=_serve, daemon=True).start()
    time.sleep(0.5)
    results = {}
    try:
        with sync_playwright() as pw:
            # [strip] 真 proxy 剝內嵌 script + 外部 main.js 版 → 應無橫幅、main.js 被抓
            b, g, r = _scenario(pw, "strip", f"http://localhost:{APP_PORT}")
            results["strip_fix_survives"] = {"banner": b, "main_js_fetched": r.get("main.js", 0) > 0, "reqs": r}
            # [block+IP] guard 應出現(用 localhost 若無 LAN IP 則跳過 guard 判定)
            if lan:
                b2, g2, r2 = _scenario(pw, "block", f"http://{lan}:{APP_PORT}")
                results["block_ip_guard"] = {"banner": b2, "guard_shown": g2, "reqs": r2}
    finally:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        except Exception:
            proc.terminate()

    print("=== 真 proxy 迴歸結果 ===")
    ok = True
    s = results["strip_fix_survives"]
    strip_ok = (not s["banner"]) and s["main_js_fetched"]
    ok &= strip_ok
    print(f"[strip] 外部 main.js 過真剝離 proxy:banner={s['banner']} main.js抓到={s['main_js_fetched']} "
          f"-> {'✅ 修正有效' if strip_ok else '❌ 加固退化'}")
    if "block_ip_guard" in results:
        g = results["block_ip_guard"]
        guard_ok = g["guard_shown"]  # 元件仍被擋(banner=True 屬預期);重點是 guard 要出現
        ok &= guard_ok
        print(f"[block+IP] 元件被擋(banner={g['banner']},#1環境問題預期為真)+ app guard 指示={g['guard_shown']} "
              f"-> {'✅ guard 正確引導' if guard_ok else '❌ guard 未顯示'}")
        print("GREEN" if ok else "REGRESSION")
        sys.exit(0 if ok else 1)
    else:
        # 無 LAN IP → guard/#1 情境『沒跑過』。不可印 GREEN/exit 0(那是假綠,違反
        # CLAUDE.md『沒紅過的綠燈不算數』):標記 INCOMPLETE 並以非 0 退出,絕不當通過閘門。
        print("[block+IP] ⚠️ 本機無非 loopback LAN IP,guard/#1 真模擬『未執行』。")
        print(f"[strip] 單獨結果:{'✅' if strip_ok else '❌'}(僅涵蓋 #3,未涵蓋 #1/guard)")
        print("INCOMPLETE")   # 非 GREEN:guard 分支未實跑,不得用作通過閘門
        sys.exit(2)


if __name__ == "__main__":
    main()
