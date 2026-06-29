# 專案開發協定:U-Net Agent Workflow

本專案用「U-Net 五階段循環」開發。每個階段是一個**獨立的大腦模式**,透過 slash command 切換。
**嚴禁跨階段越界**(例如在設計階段偷寫實作)。

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

`1`、`2` 是 **feature 粒度**;`3`–`5` 是 **module 粒度**。**PO 是把 feature 拆成 module 的地方** ——
這是整條管線最關鍵、也最易失控的收斂步驟(它是唯一沒有客觀紅綠信號保護的單點)。

## 鐵則

1. **各司其職,不准越界。** User 只講想要什麼;PO 決定做什麼 / 什麼順序;Architect 只出設計不寫實作;
   PM 先於 PG,驗收測試只依設計;PG 寫完跑客觀綠燈閘門。
2. **契約不可在下游被偷改。** 尤其 PG **嚴禁**為了過綠而:改測試 / 改設計、硬編碼回傳值、加特例、
   `try/except` 吞錯、`skip`/`xfail`/放寬斷言、動 `verify/`、`.unet/`、`conftest.py`。
3. **雙向閘門 (Reverse Gates)。** 發現上游有錯,停手回報、往回退一層,並由 PO 在 ROADMAP「決策日誌」記一行:
   `/pg →(設計/測試錯)→ /architect 或 /pm`;`/architect →(需求不清/不可行)→ /po`;`/po →(需求矛盾)→ /user`。

## 命名約定(skip connection)+ 可追溯性

module 在 `3`–`5` 用**同名**對齊:`3_Architect_Design/01_x.md`、`4_PM_Feedback/test_x.py`、`5_PG_Develop/x.py`。
每個測試在註解標注對應設計的哪一條 AC(`# AC1`…)。可用 `python verify/unet_status.py` 稽核三層對齊與 AC 雙向覆蓋。

## 「完成 (done)」的定義(分層,避免 false-green)

- **純邏輯模組**:`python verify/gate.py <module>` 印 `GREEN` 即完成。
- **GUI / 整合 / 外部編解碼 / 非同步模組**:done = 單元綠 **AND** 真實 E2E 綠。
  E2E 測試獨立放 `4_PM_Feedback/test_<module>_e2e.py` 並標 `@pytest.mark.e2e`,
  讓 `gate.py` 只跑單元、E2E 交給 `/ux-test` 或人觸發(不進 PG 自主修綠迴圈)。
- 「element 存在 / bytes 非空 / fourcc=h264」都只是代理,**不等於使用者真的能用**。

## 機器判綠(不由 PG 自述)

PG 寫完跑 `python verify/gate.py <module>`,它同時檢:收集到的測試數>0、pytest 回傳碼==0、
無 failed/errors、且 `3_/4_` 契約檔未被竄改。只有它印 `GREEN` 才算過。

## 模組分級(Tier,由 PO 在 ROADMAP 標)

Tier A(無 I/O + 無跨模組契約 + 無 GUI):設計可極簡、人審可只一次,**但測試不省**。
Tier B(其餘):完整五層 + 真實 E2E 閘門。模組一旦長出 I/O 或被依賴 → 自動升 Tier B。

## 全局狀態

`ROADMAP.md`(PO 維護)是單一真相來源:模組狀態、相依、里程碑、appetite、決策日誌。
**狀態(待設計→完成)是人的判斷,不可由「檔案存在」自動推斷。** 不確定該做什麼時先看它,
並用 `verify/unet_status.py` 核對它是否與磁碟漂移。

## 測試基礎設施歸屬

`conftest.py` / `fixtures/` / `sys.path` 設定由 **PM 擁有**,PG **唯讀**。

## 技術假設

Python + pytest + Streamlit。測試指令:`pytest 4_PM_Feedback/test_<module>.py -v`;閘門:`python verify/gate.py <module>`。
Streamlit 進入點:`5_PG_Develop/app.py`(`streamlit run 5_PG_Develop/app.py`)。
**換語言/框架**:改 `.unet/gate.json`(test_path / test_cmd / collect_cmd / collect_mark)與 conftest 的 E2E 啟動指令即可,不必改 `verify/gate.py` 本體。
