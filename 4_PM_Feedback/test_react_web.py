"""驗收測試：React Web 本機影像 API。

依 `3_Architect_Design/28_react_web_migration.md`。每案標註設計 AC；
測試以 FastAPI TestClient 驗 API 邊界，瀏覽器授權／畫面驗收另由 Playwright 執行。
"""

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import tifffile

from web_api import create_app


ORIGIN = "http://127.0.0.1:8765"
PAIRING = "cv-viewer-test-pairing"


def _client(tmp_path):
    app = create_app(pairing_code=PAIRING, data_dir=tmp_path,
                     allowed_origins={ORIGIN})
    return TestClient(app, base_url=ORIGIN)


def _png_bytes(array):
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()


def _tiff_bytes(array):
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="TIFF")
    return output.getvalue()


def _session(client, *, origin=ORIGIN, code=PAIRING):
    response = client.post("/api/session", headers={"Origin": origin},
                           json={"pairing_code": code})
    return response


def _auth_headers(client):
    response = _session(client)
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CV-Session": response.json()["session_token"]}


def test_health_is_available_without_exposing_local_paths(tmp_path):
    # AC1 — 本機服務提供健康檢查，回應不含使用者路徑。
    client = _client(tmp_path)
    response = client.get("/api/health", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert str(tmp_path) not in response.text


def test_pairing_and_origin_are_required_for_session_and_image_io(tmp_path):
    # AC2 — 錯配對碼與未授權來源不可建立工作階段或讀寫影像。
    client = _client(tmp_path)
    assert _session(client, code="wrong-code").status_code == 401
    assert _session(client, origin="http://evil.example").status_code == 403
    response = client.post("/api/images/view", headers={"Origin": ORIGIN},
                           files={"file": ("pixel.png", _png_bytes(
                               np.zeros((1, 1), dtype=np.uint8)), "image/png")})
    assert response.status_code == 401


def test_16bit_image_view_and_pixel_query_preserve_source_value(tmp_path):
    # AC3 — 16-bit TIFF 顯示映射與像素真值分離，點擊取回原始 uint16 值。
    client = _client(tmp_path)
    headers = _auth_headers(client)
    source = np.array([[0, 65535], [40000, 257]], dtype=np.uint16)
    upload = client.post("/api/images/view", headers=headers,
                         files={"file": ("wafer16.tif", _tiff_bytes(source),
                                         "image/tiff")})
    assert upload.status_code == 200
    result = upload.json()
    assert result["width"] == 2
    assert result["height"] == 2
    assert result["bit_depth"] == 16
    assert result["channels"] == 1
    assert "path" not in result

    handle = result["image_handle"]
    display = client.get(f"/api/images/{handle}/display",
                         headers={"X-CV-Session": headers["X-CV-Session"]})
    assert display.status_code == 200
    assert display.headers["content-type"].startswith("image/png")
    assert Image.open(io.BytesIO(display.content)).mode == "RGB"

    pixel = client.get(f"/api/images/{handle}/pixel", headers=headers,
                       params={"x": 1, "y": 0})
    assert pixel.status_code == 200
    assert pixel.json() == {"x": 1, "y": 0, "value": 65535}


def test_unsupported_image_and_out_of_bounds_pixel_are_rejected(tmp_path):
    # AC4 — 不支援格式與越界座標明確拒絕，不回傳部分影像結果。
    client = _client(tmp_path)
    headers = _auth_headers(client)
    unsupported = client.post("/api/images/view", headers=headers,
                              files={"file": ("notes.gif", b"GIF89a", "image/gif")})
    assert unsupported.status_code == 415

    image = client.post("/api/images/view", headers=headers,
                        files={"file": ("pixel.png", _png_bytes(
                            np.array([[1, 2]], dtype=np.uint8)), "image/png")})
    handle = image.json()["image_handle"]
    outside = client.get(f"/api/images/{handle}/pixel", headers=headers,
                         params={"x": 2, "y": 0})
    assert outside.status_code == 422


def test_released_image_handle_cannot_be_reused(tmp_path):
    # AC5 — 關閉目前影像後 opaque handle 失效，服務不留無限期 pixel cache。
    client = _client(tmp_path)
    headers = _auth_headers(client)
    image = client.post("/api/images/view", headers=headers,
                        files={"file": ("pixel.png", _png_bytes(
                            np.array([[3]], dtype=np.uint8)), "image/png")})
    handle = image.json()["image_handle"]
    released = client.delete(f"/api/images/{handle}", headers=headers)
    assert released.status_code == 204
    assert client.get(f"/api/images/{handle}/pixel", headers=headers,
                      params={"x": 0, "y": 0}).status_code == 404


def test_roi_crop_download_preserves_source_dtype_and_pixels(tmp_path):
    # AC6 — ROI 匯出裁切原始影像資料，TIFF 保留 16-bit dtype 與逐像素真值。
    client = _client(tmp_path)
    headers = _auth_headers(client)
    source = np.array([[0, 1, 2], [3, 40000, 5], [6, 7, 65535]], dtype=np.uint16)
    upload = client.post("/api/images/view", headers=headers,
                         files={"file": ("wafer16.tif", _tiff_bytes(source), "image/tiff")})
    handle = upload.json()["image_handle"]

    response = client.get(f"/api/images/{handle}/roi-crop", headers=headers,
                          params={"x": 1, "y": 0, "w": 2, "h": 2})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/tiff")
    actual = tifffile.imread(io.BytesIO(response.content))
    assert actual.dtype == np.uint16
    np.testing.assert_array_equal(actual, np.array([[1, 2], [40000, 5]], dtype=np.uint16))
    unchanged = client.get(f"/api/images/{handle}/pixel", headers=headers,
                           params={"x": 1, "y": 1})
    assert unchanged.json() == {"x": 1, "y": 1, "value": 40000}


def test_roi_crop_download_preserves_rgb_pixels(tmp_path):
    # AC7 — RGB TIFF crop 保留 shape、channel 順序與 uint8 像素值。
    client = _client(tmp_path)
    headers = _auth_headers(client)
    source = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
    upload = client.post("/api/images/view", headers=headers,
                         files={"file": ("rgb.png", _png_bytes(source), "image/png")})
    handle = upload.json()["image_handle"]

    response = client.get(f"/api/images/{handle}/roi-crop", headers=headers,
                          params={"x": 1, "y": 1, "w": 2, "h": 1})
    assert response.status_code == 200
    actual = tifffile.imread(io.BytesIO(response.content))
    assert actual.dtype == np.uint8
    np.testing.assert_array_equal(actual, source[1:2, 1:3, :])


def test_roi_crop_download_requires_session_and_rejects_empty_intersection(tmp_path):
    # AC8 — ROI 匯出沿用 session 權限，零尺寸與完全越界 ROI 拒絕。
    client = _client(tmp_path)
    source = np.arange(9, dtype=np.uint8).reshape(3, 3)
    headers = _auth_headers(client)
    image = client.post("/api/images/view", headers=headers,
                        files={"file": ("image.png", _png_bytes(source), "image/png")})
    handle = image.json()["image_handle"]

    unauthenticated = client.get(f"/api/images/{handle}/roi-crop",
                                 params={"x": 0, "y": 0, "w": 1, "h": 1})
    assert unauthenticated.status_code == 401
    zero_area = client.get(f"/api/images/{handle}/roi-crop", headers=headers,
                           params={"x": 0, "y": 0, "w": 0, "h": 1})
    outside = client.get(f"/api/images/{handle}/roi-crop", headers=headers,
                         params={"x": 3, "y": 3, "w": 1, "h": 1})
    assert zero_area.status_code == 422
    assert zero_area.json()["detail"]["code"] == "roi_crop_empty"
    assert outside.status_code == 422
    assert outside.json()["detail"]["code"] == "roi_crop_empty"
