# AI 交接手冊:修復「Your app is having trouble loading the … component」橫幅

> 這份是給**另一個 AI 助理**(在出問題的那台機器上、無先前對話脈絡)照著做的。
> 目標:把 CV_Viewer 的 `viewer.cv_viewer` / `thumbwall.cv_thumbwall` 兩個元件從
> 「trouble loading」橫幅修到正常顯示。**照順序做,別跳步。**

---

## 0. 給接手 AI 的話(務必先讀)

**你的任務**:診斷 → 確認是哪一類故障 → 套用對應修法 → 驗證轉綠。**不是**改程式碼——
repo 本身已被證明無罪(見下)。這是**環境/部署**問題,九成是「怎麼開瀏覽器」或 proxy/防毒。

**已驗證的事實(請直接採信,不要浪費時間重查):**
1. 這條橫幅 = **Streamlit 前端「元件 60 秒內沒回報 `setComponentReady()`」的逾時訊息**
   (原始碼 `ComponentInstance.js` 內 `B=6e4` = 60000ms)。**與 CDN / 外網完全無關**——
   本專案前端資產(OpenSeadragon 等)全部 vendored 在 `5_PG_Develop/viewer_component/`、
   `thumbwall_component/`。
2. 以下都**已排除**、不是原因,別再測:Streamlit 版本(1.56 與 1.58 都正常)、中文/空格路徑、
   `browser.serverAddress` 設定、專案缺檔(git 追蹤 42 個元件檔且無 ignore)。
3. **唯一在乾淨環境重現成功的條件**:內容過濾 proxy 擋掉 `/component/` 請求 **且** 瀏覽器用
   「機器 IP / 主機名」而非 `localhost` 開。→ 主頁正常、兩元件 60 秒後跳橫幅(與現場一字不差)。
   機理:**Chromium / Edge 對 `localhost` 有「隱含 proxy 繞過」,對 IP / 主機名沒有。**

**紀律(重要)**:不要「猜一個修法就宣稱修好」。先用第 3 節的診斷**看到證據**,再套第 4 節對應修法,
最後第 5 節**親眼確認轉綠**。沒驗證過的綠不算數。

**故障分類(整份手冊都用這套代號):**
- **A = 資產被攔/拖慢**:proxy 內容過濾、防火牆、防毒即時掃描擋住或拖慢 `/component/` 請求。
- **B = 腳本沒跑**:瀏覽器或群組原則封鎖 iframe 內嵌 script,或瀏覽器過舊跑不動元件 ES6。
- **C = 缺檔**:專案沒複製齊(常見:用了會排除 `images/` 的打包工具)。
- **D = 都正常但仍逾時**:防毒讓「首次載入」超過 60 秒;或瀏覽器開的其實是別的位址。

---

## 1. 先確認症狀對得上

在出問題的機器上,App 主畫面(側邊「資料來源」、上方控制列)**正常顯示**,只有
viewer / thumbwall 兩塊位置各出現黃色橫幅:

> Your app is having trouble loading the **viewer.cv_viewer** component. If this is an installed
> component that works locally, the app may be having trouble accessing the component frontend
> assets due to network latency or proxy settings in your app deployment.

若「整個 App 都打不開」→ 那是別的問題(Streamlit 沒起來 / 埠不通),不適用本手冊。

---

## 2. 先把修復版本拉下來

診斷頁與啟動器在近期 commit 才加入。先更新:

```bash
cd <專案資料夾>            # 例:cd CV_Viewer
git pull                  # 取得 diagnose.bat / run.bat / DEPLOYMENT.md / diagnose_components.py
```

確認這些檔存在(缺的話代表沒 pull 到,或該機不是用 git 裝的——見第 4 節 C):
`run.bat`、`diagnose.bat`、`DEPLOYMENT.md`、`5_PG_Develop/diagnose_components.py`、
`.streamlit/config.toml`。

---

## 3. 診斷(分兩半:你自己跑 + 請人看瀏覽器)

### 3a. AI 自己能跑的「伺服器端」檢查(不需瀏覽器)

用 shell 直接查磁碟資產與環境。以下 Python 片段跨平台可用:

```bash
python - <<'PY'
from pathlib import Path
import sys
root = Path("5_PG_Develop")
for name, d, need in [("viewer.cv_viewer", root/"viewer_component", 42),
                      ("thumbwall.cv_thumbwall", root/"thumbwall_component", 1)]:
    files = [p for p in d.rglob("*") if p.is_file()] if d.exists() else []
    idx = (d/"index.html").exists()
    print(f"{name}: 資料夾={'有' if d.exists() else '無'} index.html={'有' if idx else '缺'} "
          f"檔案數={len(files)}(應≥{need}) → {'OK' if d.exists() and idx and len(files)>=need else '缺檔=故障C'}")
import streamlit; print("Streamlit", streamlit.__version__, "| Python", sys.version.split()[0])
PY
```

- 若印出 **「缺檔=故障C」** → 跳到第 4 節 **C**。
- 否則資產齊全,問題在「這台瀏覽器到伺服器這條路」→ 繼續 3b。

### 3b. 需要人操作的「瀏覽器端」檢查(最關鍵)

跑內建診斷頁(它**不依賴** `/component/` 路徑,所以主 App 元件全掛它也能開):

```bash
diagnose.bat
# 或:python -m streamlit run 5_PG_Develop/diagnose_components.py --server.port 8502
```

**請機器前的人用 `http://localhost:8502` 開,把整頁截圖或把②區塊每一行的文字回報給你。**
你依②的結果對照:

| ② 診斷頁顯示 | 判定 | 去第 4 節 |
|---|---|---|
| 第一行「❌ 內嵌腳本未執行」 | **B** 腳本被封 / 瀏覽器過舊 | **B** |
| 「⚠️ 你目前用 `<某IP/主機名>` 開」 | 位址不繞過 proxy | **A**(先試「改用 localhost 開」) |
| viewer / thumbwall「❌ 抓取失敗」或「❌ HTTP 4xx/5xx」 | **A** 被 proxy/防火牆/防毒攔 | **A** |
| 「✅ HTTP 200」但括號 ms 很大(>5000) | **D** 被拖慢 | **D** |
| 全部 ✅ 且不慢 | 這條路是通的 | **D**(見「都正常卻仍跳橫幅」) |

**若無法請人看瀏覽器**(純遠端 / 無人在機器前):請對方在出問題的**主 App** 畫面按 `F12` →
`Console`,把紅字回報。console 簽名直接對應分類:
- `Custom Component … source error` / `fetch error` / `net::ERR_…` / `4xx/5xx` → **A**
- 只有 `… timeout error`(可能伴隨 `Content Security Policy` 或 `SyntaxError`)→ **B**

---

## 4. 依分類套用修法(只做你在第 3 節看到證據的那一類)

### A — proxy / 防火牆 / 防毒攔住 `/component/` 資產

**先試(解掉八成情況):**
1. **改用 `http://localhost:8501` 開**,不要用 Streamlit 印的 Network URL(機器 IP)、不要用主機名。
   → 直接用 `run.bat` 啟動,它就是固定開 localhost。這一步常常就好了。

**若用 localhost 仍紅:**
2. 把 `localhost` 排除在 proxy 外:Windows「設定 → 網路和網際網路 → Proxy → 手動設定 proxy」,
   「請勿對下列項目使用 Proxy」加入 `localhost;127.0.0.1`,勾選「近端(內部網路)網址不使用 Proxy」。
3. 把**專案資料夾**與 `localhost` 加進防毒 / 端點防護的白名單(即時掃描每個被 serve 的檔會攔或拖慢)。
4. (企業環境)請 IT 對 `127.0.0.1:8501` 這條本機流量放行,不要走內容過濾。

### B — 瀏覽器封鎖內嵌腳本 / 瀏覽器過舊

1. 換一般的**新版 Chrome 或 Edge**,用 `http://localhost:8501` 開。不要用 IE 模式、不要用嵌入式/
   鎖定式 kiosk 瀏覽器。
2. 若是群組原則(GPO)/端點防護注入了 CSP 擋內嵌 script → 請 IT 對本機 `localhost` 例外放行。
3. 驗證瀏覽器夠新:診斷頁②第一行要顯示「✅ 內嵌腳本可執行」。

### C — 專案缺檔

1. **重新完整取得專案**:`git clone <repo>`(最保險),或完整複製,**不要**用會排除 `images/`、
   `.bat` 的打包工具(本專案的 `viewer_component/images/` 是 OSD 按鈕圖,漏掉會缺元件資產)。
2. 若必須打包:確認 zip 內含 `5_PG_Develop/viewer_component/images/*.png`(約 40 張)、
   兩個 `index.html`、`viewer_component/openseadragon.min.js`。
3. 複製後重跑第 3a 節確認「OK」。

### D — 都正常卻仍跳橫幅(拖慢 / 開錯位址)

1. 確認瀏覽器網址列是 `http://localhost:8501`(不是 IP、不是 `https`)。
2. 防毒白名單(見 A-3);裝好白名單後**重新整理主 App 一次**(第二次通常有快取、快很多)。
3. 首次載入慢 → 重整一次讓它在 60 秒逾時內完成。

---

## 5. 驗證(必做:親眼確認轉綠)

1. 用 `run.bat` 啟動主 App(或 `python -m streamlit run 5_PG_Develop/app.py --server.port 8501`)。
2. 瀏覽器開 `http://localhost:8501`,選一個影像資料夾。
3. **確認**:縮圖牆(thumbwall)出現一排可點縮圖、主檢視區(viewer)顯示影像且可滾輪縮放,
   **兩塊都不再有黃色橫幅**。
4. 再跑一次 `diagnose.bat`,②區塊應**全 ✅**。
5. 把「修好後」的主 App 截圖留存 / 回報。

> 若做完對應修法仍紅:表示分類判斷有誤 → 回第 3 節,把診斷頁②整段 + F12 console 紅字一起收集,
> 重新歸類。不要在沒有新證據下換另一個修法亂試。

---

## 6.(選用)要更硬的證據時:在**開發機**上完整 red→green 重現

只有在需要向他人證明、或懷疑判斷時才做。需要一台有網路、能裝 playwright 的機器
(**不是**出問題的離線機)。

```bash
pip install playwright && playwright install chromium
git clone <repo> fresh_clone
```

重現「紅」(= 工廠症狀):起一個「只擋 `/component/`、其餘放行」的本地 proxy,
用 `--proxy-server` 指給 Chromium,並用**機器 IP**(非 localhost)開 App,等 **>60 秒** →
兩元件跳出一字不差的橫幅。
證「綠」:同一個壞 proxy,改用 `http://localhost` 開,或給 Chromium `--no-proxy-server` → 正常。

> 關鍵:等待必須 **>60000ms**,否則 Streamlit 還沒到逾時、看不到橫幅(容易誤判「沒重現」)。
> 這正是本案一開始只等 10 秒導致誤以為重現不出來的坑。

---

## 附錄

**A. 已排除的假設(別重測)**:Streamlit 版本(1.56/1.58 皆綠)、中文+空格路徑、LAN IP 直連
(無 proxy 時)、`browser.serverAddress`、專案缺檔(git 完整)。

**B. console 簽名速查**:
- A 類:`Custom Component viewer.cv_viewer source error - <狀態碼>`、`fetch error - Failed to fetch`、
  `net::ERR_…`
- B 類:僅 `Custom Component … timeout error`,可能伴 `… violates the following Content Security
  Policy` 或 `SyntaxError`

**C. 相關檔案**:
- `DEPLOYMENT.md` — 人看的部署 + 排障(本手冊的精簡版)
- `run.bat` / `diagnose.bat` — 啟動器,固定開 localhost
- `5_PG_Develop/diagnose_components.py` — 診斷頁本體
- `.streamlit/config.toml` — headless + 不回報統計

**D. 一句話總結給使用者**:「**用 `run.bat` 啟動、瀏覽器一律 `http://localhost:8501` 開**;
還不行就跑 `diagnose.bat` 照頁面判讀表處置(多半是把 localhost 加進 proxy 例外、或防毒白名單)。」
