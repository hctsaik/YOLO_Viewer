# 專案開發協定:U-Net Agent Workflow

本專案用「U-Net 五階段循環」開發。每個階段是一個**獨立的大腦模式**,透過 slash command 切換。
**嚴禁跨階段越界**(例如在設計階段偷寫實作)。

## 運作模式(本專案已授權自主跑)

User 已授權 orchestrator **一整輪自主跑完、不逐項確認**:接到「做完某里程碑 / 某功能」時,
你當 PO/orchestrator,自己定範圍 / appetite、釘跨模組契約、按 architect→pm→pg 推進,
**每個決策寫進 `ROADMAP.md` 決策日誌一行留痕即可**,不必每步停下來問。
只在「需求本身矛盾 / 有多個都合理的方向、選錯成本高」時才回頭問 User。

**兩條車道**(判斷「值不值得開一個模組」):
- **完整五層**:長出**新純邏輯模組**(如 imgadjust 的 7 個純函式、labelfmt 的多格式解析)或新 Tier B
  功能時,走 architect→pm→pg 全流程。判準:能獨立寫出「輸入→輸出」契約、值得單元 gate 鎖住。
- **維護車道**:User 回饋的版面 / 整合微調(挑「顯示框裡最高信心」這種一行 `max()`、搬控制項位置、
  改 CSS),orchestrator **直接改 app 層** + 對抗驗證 + 全套回歸 + ROADMAP 決策日誌一行;不硬開模組。

## 角色與目錄(資料夾即架構)

| 階段 | 角色 | U-Net 對應 | 目錄 | 只能產出 |
|------|------|-----------|------|----------|
| `/user`      | 終端使用者 | 原始輸入信號 | `1_user_needs/`      | 需求 Markdown(feature 粒度) |
| `/po`        | Product Owner | 訓練總監+前處理 | `2_PO_PRD/` + `ROADMAP.md` | PRD、模組分解、路線圖 |
| `/architect` | 系統架構師 | 下採樣(壓實語義) | `3_Architect_Design/` | 技術設計 Markdown(module 粒度) |
| `/pm`        | 專案經理(驗收回饋) | 跳接(鎖住契約) | `4_PM_Feedback/`    | 驗收測試程式碼 |
| `/pg`        | 程式設計師 | 上採樣(生成實作) | `5_PG_Develop/`     | 實作程式碼 |

> **誠實聲明**:這不是真的神經網路,本質是 **Spec-Driven + TDD + Phase Gating**,U-Net 只是好記的
> 心智模型,價值來自紀律不是類比。真正的 U-Net 只有 architect / pm / pg 三層;User / PO 不是
> 網路的「層」,而是資料來源與訓練總監。skip connection = PM 把契約原封不動旁傳到驗收端;
> 但沒有 training / loss / 反向傳播,reverse gate 是方法論自加的人工紀律。**別把類比當規格。**

## 粒度轉換點

`1`、`2` 是 **feature 粒度**;`3`–`5` 是 **module 粒度**。**PO 把 feature 拆成 module** 是整條管線最關鍵、
也最易失控的收斂步驟——**它是唯一沒有客觀紅綠信號保護的單點**(所以「配對 / 收斂」類邏輯要盡量抽成
純模組用單元 gate 鎖住,如 pairset / modeldiff / labelfmt)。

## 鐵則

1. **各司其職,不准越界。** User 只講想要什麼;PO 決定做什麼 / 什麼順序;Architect 只出設計不寫實作;
   PM 先於 PG,驗收測試只依設計;PG 寫完跑客觀綠燈閘門。
2. **契約不可在下游被偷改。** 尤其 PG **嚴禁**為了過綠而:改測試 / 改設計、硬編碼回傳值、加特例、
   `try/except` 吞錯、`skip`/`xfail`/放寬斷言、動 `verify/`、`.unet/`、`conftest.py`。
3. **雙向閘門 (Reverse Gates)。** 發現上游有錯,停手回報、往回退一層,並由 PO 在 ROADMAP「決策日誌」記一行:
   `/pg →(設計/測試錯)→ /architect 或 /pm`;`/architect →(需求不清/不可行)→ /po`;`/po →(需求矛盾)→ /user`。

> **契約演進協定(鐵則 2 的合法例外)**:鐵則 2 禁的是「PG 為過綠偷改」。但實務上最常見的是
> **User 改需求 → 契約需要合法演進**——這**不是**作弊。合法演進的辨識:① 由 orchestrator/PO 主持、
> User 有裁決;② 順序 = architect 改設計(加「設計演進」節)→ PM 改測試 → `gate.py --snapshot` 重打
> baseline → PG 實作;③ **是「錨點遷移」不是「放寬斷言」**——機器讀數改由 P1 探針 / 新斷言承接,
> **不刪掉對「真正該過的行為」的檢查**;④ 全程留痕在 ROADMAP。與作弊的差別就在 ①③④。

## 命名約定(skip connection)+ 可追溯性

module 在 `3`–`5` 用**同名**對齊:`3_Architect_Design/01_x.md`、`4_PM_Feedback/test_x.py`、`5_PG_Develop/x.py`。
每個測試在註解標注對應設計的哪一條 AC(`# AC1`…)。可用 `python verify/unet_status.py` 稽核三層對齊與 AC 雙向覆蓋。

## 「完成 (done)」的定義(分層,避免 false-green)

- **純邏輯模組**:`python verify/gate.py <module>` 印 `GREEN` 即完成。
- **GUI / 整合 / 外部編解碼 / 非同步模組**:done = 單元綠 **AND** 真實 E2E 綠(**AND 截圖 / 實跑肉眼實證**)。
  E2E 測試獨立放 `4_PM_Feedback/test_<module>_e2e.py` 並標 `@pytest.mark.e2e`,
  讓 `gate.py` 只跑單元、E2E 交給 `/ux-test` 或人觸發(不進 PG 自主修綠迴圈)。
- 「element 存在 / bytes 非空 / fourcc=h264」都只是代理,**不等於使用者真的能用**。
- **對抗驗證是標配**:修 bug / 契約演進後,先 `git stash` 還原成修前程式碼,確認新測試「修前必紅」
  (證明測試真的在測那件事),再 `stash pop` 修復轉綠——沒紅過的綠燈不算數。

## 機器判綠(不由 PG 自述)

PG 寫完跑 `python verify/gate.py <module>`,它同時檢:收集到的測試數>0、pytest 回傳碼==0、
無 failed/errors、且 `3_/4_` 契約檔未被竄改。只有它印 `GREEN` 才算過。
**判綠親自重跑,不信子代理自述**;E2E 各檔**獨立 session 逐檔跑**(見工程備忘的跨檔污染)。

## 模組分級(Tier,由 PO 在 ROADMAP 標)

Tier A(無 I/O + 無跨模組契約 + 無 GUI):設計可極簡、人審可只一次,**但測試不省**。
Tier B(其餘):完整五層 + 真實 E2E 閘門。模組一旦長出 I/O 或被依賴 → 自動升 Tier B。

## 全局狀態 + ROADMAP 衛生

`ROADMAP.md`(PO 維護)是單一真相來源:模組狀態、相依、里程碑、appetite、決策日誌。
**狀態(待設計→完成)是人的判斷,不可由「檔案存在」自動推斷。** 不確定該做什麼時先看它,
並用 `verify/unet_status.py` 核對它是否與磁碟漂移。
- **模組表數字以 `unet_status.py` 為準**(表只可靠記「狀態」,測試數/新模組列已知漂移,非每輪範圍)。
- **決策日誌會膨脹**:append-only 已近千行。輪替政策——只留最近約 15 輪在 ROADMAP,更舊的搬
  `DECISIONS_ARCHIVE.md`(未建則第一次瘦身時建)。

## 測試基礎設施歸屬

`conftest.py` / `fixtures/` / `sys.path` 設定由 **PM 擁有**,PG **唯讀**。

## 工程備忘(進場必看:已用血換來的坑,一行一條,詳見出處)

- **§4.l widget 順序鐵律**:任何 keyed widget(值要跨 rerun 保留)必須在**會呼叫 `st.rerun()` 的按鈕
  之前**實例化,否則被 Streamlit 當孤兒 widget 清空回預設(踩過≥3 次:信心門檻歸零 / Focus toggle /
  排序下拉)。每次新增控制都要主動檢查。詳見 `3_Architect_Design/20_viewer_workbench_redesign.md §4.l`。
- **E2E 逐檔跑**:跨檔位置記憶污染會造成假紅(「用起始圖」的測試被前一檔導航到 idx≠0 污染)。
  **全套回歸 = 12 個 `test_*_e2e.py` 逐檔各自 session + 全單元**(未來可收成 `verify/regression.py`)。
- **`.cvr_state.json`** 是 repo root 的跨進程共享位置記憶檔;開發 app(8501)與 E2E harness(8765)
  **同時操作會互相 clobber**(conftest session 啟動前會清它)。批次 E2E 跑時別同時驅動 8501。
- **Playwright 截圖假象**:`page.screenshot()` 對 iframe 自訂元件(viewer/thumbwall)resize 後有殘影;
  驗版面用 `bounding_box()` / `elementFromPoint` **DOM 斷言**,不用像素比對;真要看肉眼畫面用 OS 級截圖。
- **`sample_images/` 是 E2E 契約**(TOTAL=8、只 2 張有偵測、wafer16 為 16-bit)——往裡加圖會弄紅一排測試。
- **離線部署約束**:目標機可能無外網 / 擋 CDN。前端資產一律 **vendored**(`viewer_component/`、
  `thumbwall_component/` 已內含 OpenSeadragon),新增 JS/CSS/字型/圖示**不得用 CDN**;搬專案這兩夾要跟著走。
- **元件「trouble loading」橫幅 = 60s ready 逾時**(非 CDN):換機出現時先跑 `diagnose.bat` 判
  A(proxy/防毒攔 `/component/`)或 B(內嵌腳本被封);**瀏覽器一律開 `http://localhost:8501`**
  (Chromium 對 localhost 隱含繞過 proxy,用機器 IP 開會被內容過濾攔——已實測紅→綠)。見 `DEPLOYMENT.md`。

## 技術假設 + 環境實務

Python + pytest + Streamlit。測試:`pytest 4_PM_Feedback/test_<module>.py -v`;閘門:`python verify/gate.py <module>`。
**換語言/框架**:改 `.unet/gate.json`(test_path / test_cmd / collect_cmd / collect_mark)與 conftest 的 E2E 啟動指令即可,不必改 `verify/gate.py` 本體。
- **啟動 app**:`python -m streamlit run 5_PG_Develop/app.py --server.port 8501`(`streamlit` 常不在 PATH,用 `python -m`)。
- **殺埠(Windows)**:`netstat -ano | grep :8501` 找 pid → `taskkill //F //PID <pid>`。
- **中文輸出**:跑 pytest / 腳本前設 `PYTHONIOENCODING=utf-8`,否則 console 中文變亂碼。
