"""app 的真實 E2E 冒煙(對應「使用者真的能開圖、看 viewer、切換」的可感知行為)。
跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_app_e2e.py -m e2e -v
需 sample_images/(python fixtures/make_samples.py)與 playwright。
不進 PG 自主修綠迴圈;由 /ux-test 或人觸發。conftest 的 app_server 會自動起 streamlit run 5_PG_Develop/app.py。"""
import time

import pytest


@pytest.mark.e2e
def test_app_loads_viewer_and_navigates(page):
    # 1) app 載入
    page.get_by_text("YOLO Image Viewer").first.wait_for(timeout=60000)
    # 2) P1 探針出現(app 真的算繪完成)。頂列資訊徽章「N/total…」整條移除後不再有可見『N / 8』,
    #    改讀主文件 P1 探針 [data-render-ms](設計 §5 P1 機器讀面)。
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    # 3) OSD viewer canvas 真的出現在巢狀元件 iframe(= 影像真的能檢視)
    frame = None
    deadline = time.time() + 45
    while time.time() < deadline and frame is None:
        for f in page.frames:
            try:
                if f.locator("canvas").count() > 0:
                    frame = f
                    break
            except Exception:
                pass
        if frame is None:
            page.wait_for_timeout(500)
    assert frame is not None, "OSD viewer canvas 未出現(viewer 沒載入)"
    frame.locator("canvas").first.wait_for(state="visible", timeout=30000)
    # 4) 導覽:點「下一張」後 app 仍正常算繪(不崩、可操作)。頂列資訊徽章移除後改驗 P1 探針
    #    仍在且 data-idx 可解析(主文件 DOM,設計 §5 P1 機器讀面)。
    page.get_by_role("button", name="下一張 ⟶").click()
    probe = page.locator("[data-render-ms]").first
    probe.wait_for(state="attached", timeout=30000)
    assert probe.get_attribute("data-idx") is not None, "切換後 P1 探針 data-idx 應存在(app 未崩)"
