"""dinodiff 真實 E2E 驗收(設計 3_Architect_Design/27_dinodiff.md §6)。

分兩段:
  (A) 真實模型鏈路(AC-E1 / AC-E2)—— 真的載 88MB DINOv2 權重、真的跑 ViT 前向。
      這是「done 的定義」要求的實跑實證:單元測試用的是合成特徵,證明不了模型接得起來。
  (B) GUI(AC-E3)—— 比較模式選「🔥 DINO 語意差異」後畫面真的長出熱力圖 + Top-K 框 + 分數。

找不到權重 → skip(不是 fail):權重不進 repo(88MB),由 CVR_DINO_MODEL / models/ 夾 / 📁 選檔提供。
跑法:cd CV_Viewer && pytest 4_PM_Feedback/test_dinodiff_e2e.py -m e2e -v
"""
import os
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import dinodiff

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_images"
APP_TITLE = "YOLO Image Viewer"


def _model_path():
    return dinodiff.resolve_model_path(None, os.environ, [ROOT / "models"])


_HAVE_MODEL = _model_path() is not None
_needs_model = pytest.mark.skipif(
    not _HAVE_MODEL,
    reason="找不到 DINOv2 權重(放進 CV_Viewer/models/ 或設 CVR_DINO_MODEL);"
           "此為離線部署的預期狀態,不算失敗")


@pytest.fixture(scope="module")
def extractor():
    from dinodiff import Dinov2PatchExtractor
    return Dinov2PatchExtractor(_model_path(), ROOT / "5_PG_Develop" / "dinov2_hub")


def _rgb(name):
    return np.asarray(Image.open(SAMPLES / name).convert("RGB"), dtype=np.uint8)


# ============================== AC-E1 — 真實模型:兩張不同的圖 → 有熱區 ==============================
@pytest.mark.e2e
@_needs_model
def test_ace1_real_model_two_different_images_produce_a_heatmap(extractor):
    fa = extractor(_rgb("lot42_frame_000.png"))
    fb = extractor(_rgb("lot42_frame_001.png"))
    assert fa.shape == fb.shape, "同一 extractor 對兩張圖應給出同形狀特徵"
    assert fa.shape[0] == 1369, f"518/14=37 → 37x37=1369 個 patch token;實得 {fa.shape[0]}"

    dmap = dinodiff.cosine_distance_map(fa, fb)
    assert dmap.shape == (37, 37)
    assert not np.isnan(dmap).any(), "真實特徵不得產生 NaN"

    score = dinodiff.diff_score(dmap)
    assert score > 1.0, f"兩張不同的圖語意差異分數應 > 1;實得 {score:.2f}"

    heat = dinodiff.normalize_heat(dmap)
    assert np.count_nonzero(heat) > 0, "兩張不同的圖應該要有熱區"
    assert heat.max() == pytest.approx(1.0)


# ============================== AC-E2 ★ 反自欺:同一張圖 vs 自己 → 全冷 ==============================
@pytest.mark.e2e
@_needs_model
def test_ace2_same_image_against_itself_stays_cold(extractor):
    """設計 §2.3 的陷阱實證:相對拉伸會把『幾乎沒差異』燒成通紅。真實模型必須跑出全冷。"""
    f = extractor(_rgb("lot42_frame_000.png"))
    dmap = dinodiff.cosine_distance_map(f, f)

    score = dinodiff.diff_score(dmap)
    assert score < 1.0, f"同一張圖跟自己比,差異分數應趨近 0;實得 {score:.2f}"

    heat = dinodiff.normalize_heat(dmap)
    assert np.count_nonzero(heat) == 0, "同一張圖跟自己比卻燒出熱區 = 對使用者說謊(假紅)"
    assert dinodiff.top_regions(heat, w=640, h=480) == [], "沒有差異就不該框出任何『差異區』"


# ============================== AC-E3 — GUI:比較模式的 DINO 檢視真的算得出來 ==============================
def _wait_app_ready(page):
    page.set_viewport_size({"width": 1400, "height": 1000})
    page.get_by_text(APP_TITLE).first.wait_for(timeout=60000)
    page.locator("[data-render-ms]").first.wait_for(state="attached", timeout=60000)
    page.get_by_role("button", name=re.compile(r"下一張")).first.wait_for(timeout=60000)
    page.wait_for_timeout(1500)


def _find_thumbwall_frame(page, min_imgs=2, timeout=30):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in page.frames:
            try:
                if ("/component/thumbwall.cv_thumbwall/" in (f.url or "")
                        and f.locator("img").count() >= min_imgs):
                    return f
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def _probe(page, attr):
    return page.locator("[data-render-ms]").first.get_attribute(attr)


@pytest.mark.e2e
@_needs_model
def test_ace3_compare_mode_dino_view_renders_heatmap_and_regions(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page)
    assert tf is not None, "縮圖牆 iframe 未出現"

    # 標記兩張影像(①=A / ②=B)
    tf.locator(".cmpmark").nth(0).click()
    page.wait_for_timeout(1200)
    tf.locator(".cmpmark").nth(1).click()
    page.wait_for_timeout(1200)
    assert _probe(page, "data-cmp-marks-n") == "2"

    # 進比較模式
    page.locator('[data-testid="stCheckbox"]').filter(has_text="比較模式").first.click()
    page.wait_for_timeout(1200)

    # 切到「🔥 DINO 語意差異」
    page.locator('[data-testid="stSelectbox"]').filter(has_text="檢視方式").click()
    page.wait_for_timeout(200)
    page.get_by_role("option", name=re.compile("DINO")).first.click()
    page.wait_for_timeout(25000)   # 真模型首跑要載權重 + 前向,給足時間

    assert _probe(page, "data-cmp-view-mode") == "dino", "切到 DINO 檢視後 view-mode 應為 dino"
    assert _probe(page, "data-dino-model") == "1", "應已解析到權重(models/ 或 CVR_DINO_MODEL)"

    score = float(_probe(page, "data-dino-score"))
    assert score > 1.0, f"兩張不同的圖應算出 >1 的語意差異分數;實得 {score}"
    assert int(_probe(page, "data-dino-regions")) >= 1, "應至少框出 1 塊 Top-K 差異區"

    assert page.get_by_text(re.compile("Traceback")).count() == 0, "DINO 檢視不應崩潰"
    assert page.get_by_text(re.compile(r"語意差異")).count() > 0, "應顯示語意差異分數 caption"


# ============================== AC-E3b — 沒有模型時要好好提示,不是崩潰 ==============================
@pytest.mark.e2e
@pytest.mark.skipif(_HAVE_MODEL, reason="本機有權重;此測試驗的是『無權重』的降級提示")
def test_ace3b_missing_model_shows_picker_hint_not_a_crash(page):
    _wait_app_ready(page)
    tf = _find_thumbwall_frame(page)
    assert tf is not None
    tf.locator(".cmpmark").nth(0).click()
    page.wait_for_timeout(1200)
    tf.locator(".cmpmark").nth(1).click()
    page.wait_for_timeout(1200)
    page.locator('[data-testid="stCheckbox"]').filter(has_text="比較模式").first.click()
    page.wait_for_timeout(1200)
    page.locator('[data-testid="stSelectbox"]').filter(has_text="檢視方式").click()
    page.wait_for_timeout(200)
    page.get_by_role("option", name=re.compile("DINO")).first.click()
    page.wait_for_timeout(2000)

    assert _probe(page, "data-dino-model") == "0"
    assert page.get_by_text(re.compile("Traceback")).count() == 0, "沒有權重不該崩潰"
    assert page.get_by_text(re.compile(r"選擇.*權重|選模型|\.pth")).count() > 0, \
        "沒有權重時應提示使用者用 📁 選擇 .pth,而不是靜默空白"
