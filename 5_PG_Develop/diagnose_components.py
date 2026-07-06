# -*- coding: utf-8 -*-
"""元件載入診斷頁(獨立小工具,不影響主 app)。

用途:主 app 的 viewer/thumbwall 跳出
  "Your app is having trouble loading the viewer.cv_viewer component..."
時,在同一台機器跑本頁,免開 F12 就能判讀是哪種故障、該修哪裡。

背景(2026-07-06 換機故障診斷輪,詳見 DEPLOYMENT.md):
  該 banner = Streamlit 前端「元件 60 秒內沒送出 setComponentReady()」的逾時橫幅,
  與 CDN 無關(本專案資產全 vendored)。兩大情境:
    A) /component/ 資產抓不到或被拖慢(proxy 內容過濾、防毒即時掃描、防火牆)
       —— 已實測:瀏覽器用「機器 IP」開 + 內容過濾 proxy 可逐字重現;
          Chromium/Edge 對 localhost 有「隱含 proxy 繞過」,用 http://localhost 開即免疫。
    B) 資產有載入但元件腳本沒執行(企業政策/瀏覽器封鎖內嵌腳本、瀏覽器過舊)

啟動:python -m streamlit run 5_PG_Develop/diagnose_components.py --server.port 8502
     (與主 app 各用各的埠,可同時開)

注意:本頁的瀏覽器端探針走 st.components.v1.html(srcdoc 內嵌),不依賴 /component/
路徑——所以即使主 app 元件全掛,本頁仍能顯示並完成診斷。
"""
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# 註冊與主 app 完全相同的兩個元件 URL 路徑(只註冊、不渲染):
# declare_component 發生在這兩個模組的 import 時;沒有它們,本診斷 server 上的
# /component/viewer.cv_viewer/... 會 404,②的探針就測不到「跟主 app 同一條路」。
sys.path.insert(0, str(Path(__file__).parent))
import viewer      # noqa: F401,E402  → 註冊 /component/viewer.cv_viewer/
import thumbwall   # noqa: F401,E402  → 註冊 /component/thumbwall.cv_thumbwall/

st.set_page_config(page_title="元件載入診斷", layout="wide")
st.title("🔧 CV Viewer 元件載入診斷")

ROOT = Path(__file__).parent

# ---------- ① 伺服器端:磁碟資產(純 Python,必定能跑) ----------
st.subheader("① 伺服器端:磁碟上的元件資產")
rows = []
for name, d, expect_min in [
    ("viewer.cv_viewer", ROOT / "viewer_component", 42),      # index.html + osd.min.js + 40 張按鈕圖
    ("thumbwall.cv_thumbwall", ROOT / "thumbwall_component", 1),  # index.html
]:
    files = [p for p in d.rglob("*") if p.is_file()] if d.exists() else []
    ok = d.exists() and (d / "index.html").exists() and len(files) >= expect_min
    rows.append({
        "元件": name,
        "資料夾": "✅ 存在" if d.exists() else "❌ 不存在",
        "index.html": "✅" if (d / "index.html").exists() else "❌ 缺",
        "檔案數": f"{len(files)}(應 ≥{expect_min})",
        "判定": "✅ 齊全" if ok else "❌ 缺檔 → 重新完整複製專案(git clone;勿用會排除 images/ 的打包)",
    })
st.table(rows)
st.caption(
    f"Python {sys.version.split()[0]} · Streamlit {st.__version__} · 專案位置 {ROOT.parent}")

# ---------- ② 瀏覽器端:實測 /component/ 抓取(跟主 app 同一條路) ----------
st.subheader("② 瀏覽器端:實際抓取元件資產(與主 app 元件同一條路)")
st.caption("本區塊用內嵌 iframe 直接從你目前這個瀏覽器發出與主 app 相同的 /component/ 請求。")

PROBE = """
<div style="font-family:ui-monospace,Consolas,monospace;font-size:14px;line-height:2">
  <div id="js">❌ 內嵌腳本未執行 —— 你的瀏覽器/安全政策封鎖了腳本(情境 B):
      換一般的新版 Chrome/Edge,或請 IT 放行 localhost 的內嵌 script</div>
  <div id="host">⏳ 檢查存取位址…</div>
  <div id="f_viewer">⏳ viewer.cv_viewer:index.html 抓取測試中…</div>
  <div id="f_thumb">⏳ thumbwall.cv_thumbwall:index.html 抓取測試中…</div>
  <div id="f_img">⏳ viewer 圖示資產(img 標籤路徑)測試中…</div>
  <div id="ua" style="color:#888"></div>
</div>
<script>
(function(){
  var $ = function(id){ return document.getElementById(id); };
  $('js').textContent = '✅ 內嵌腳本可執行(排除情境 B 的「腳本被封鎖」)';
  $('ua').textContent = '瀏覽器:' + navigator.userAgent;

  // 存取位址:localhost 有 Chromium「隱含 proxy 繞過」;機器 IP/主機名沒有 → proxy 會介入
  var host = '';
  try { host = window.parent.location.hostname; } catch(e) { host = location.hostname; }
  if (host === 'localhost' || host === '127.0.0.1' || host === '[::1]') {
    $('host').textContent = '✅ 用 ' + host + ' 開(瀏覽器對 localhost 一律繞過 proxy,最安全)';
  } else {
    $('host').innerHTML = '⚠️ 你目前用 <b>' + host + '</b> 開 —— 這個位址「不會」繞過 proxy,' +
      '公司 proxy/內容過濾會攔截元件資產(已實測可造成主 app 的元件錯誤橫幅)。' +
      '<b>請改用 http://localhost:8501 開</b>';
  }

  // fetch 探針:讀得到 HTTP 狀態碼,最準
  function fprobe(id, url, label){
    var t0 = performance.now();
    fetch(url + '?diag=' + Math.random(), {cache: 'no-store'})
      .then(function(r){
        var ms = Math.round(performance.now() - t0);
        if (r.status === 200) {
          $(id).textContent = '✅ ' + label + ':HTTP 200(' + ms + ' ms)' +
            (ms > 5000 ? ' —— 偏慢!防毒即時掃描/proxy 可能把載入拖過 60 秒逾時' : '');
        } else {
          $(id).textContent = '❌ ' + label + ':HTTP ' + r.status +
            ' —— 伺服器端資產有問題或被中間設備改寫(情境 A);對照上方①的磁碟檢查';
        }
      })
      .catch(function(e){
        $(id).textContent = '❌ ' + label + ':抓取失敗(' + e + ')' +
          ' —— 網路層被擋:proxy/防火牆/防毒(情境 A)。改用 localhost 開、把 localhost 加入 proxy 例外、將本專案資料夾加防毒白名單';
      });
  }
  fprobe('f_viewer', '/component/viewer.cv_viewer/index.html', 'viewer.cv_viewer');
  fprobe('f_thumb', '/component/thumbwall.cv_thumbwall/index.html', 'thumbwall.cv_thumbwall');

  // img 探針:與 fetch 走不同載入管線(有些過濾設備只擋 XHR/fetch),交叉驗證
  var t1 = performance.now(), done = false, img = new Image();
  img.onload = function(){ done = true;
    $('f_img').textContent = '✅ viewer 圖示資產(img):載入成功(' + Math.round(performance.now()-t1) + ' ms)'; };
  img.onerror = function(){ done = true;
    $('f_img').textContent = '❌ viewer 圖示資產(img):載入失敗 —— 同情境 A,或磁碟缺 images/(見①)'; };
  setTimeout(function(){ if (!done)
    $('f_img').textContent = '❌ viewer 圖示資產(img):>20 秒沒回應 —— 被嚴重拖慢,主 app 會因此逾時跳橫幅'; }, 20000);
  img.src = '/component/viewer.cv_viewer/images/home_rest.png?diag=' + Math.random();
})();
</script>
"""
components.html(PROBE, height=260)

# ---------- ③ 判讀對照表 ----------
st.subheader("③ 判讀")
st.markdown("""
| ② 的結果 | 診斷 | 處置 |
|---|---|---|
| 全部 ✅ 且不慢 | 這台瀏覽器到伺服器這條路是通的 | 回主 app 重新整理;若仍跳橫幅,主 app 分頁可能開的是**不同位址**(改用 `http://localhost:8501`)或等第一次載入超過 60 秒後重新整理一次 |
| 第一行就 ❌(腳本未執行) | **情境 B**:瀏覽器/政策封鎖內嵌腳本 | 換一般的新版 Chrome/Edge;或請 IT 放行 localhost 內嵌 script |
| ⚠️ 用機器 IP 開 | proxy 不會繞過該位址 | **改用 `http://localhost:8501` 開**(最常見解法) |
| fetch/img ❌ 抓取失敗 | **情境 A**:proxy / 防火牆 / 防毒攔截 | proxy 例外加 `localhost;127.0.0.1`、專案資料夾加防毒白名單 |
| ✅ 但 >5000 ms | **情境 A 變體**:被拖慢,主 app 60 秒逾時 | 防毒白名單;重新整理主 app(第二次通常有快取變快) |

> 主 app 橫幅的機制:Streamlit 前端要求每個自訂元件在 **60 秒**內回報
> `setComponentReady()`,逾時就顯示那條「trouble loading … proxy settings」橫幅。
> 本專案資產全部 vendored 在本機,**與外網/CDN 無關**。
""")
