"""Loopback HTTP adapter for the React CV Review Workbench.

The service accepts image bytes from an explicitly authorized browser folder
handle. It never accepts a host file path and keeps only the current decoded
image in memory for display and pixel-value requests.
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import tempfile
import time
import uuid

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

import imgio


MAX_IMAGE_BYTES = 512 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000
SESSION_TTL_SECONDS = 12 * 60 * 60
IMAGE_IDLE_TTL_SECONDS = 15 * 60
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def create_app(*, pairing_code: str, data_dir, allowed_origins=None) -> FastAPI:
    """Create the local API app; pairing code and allowed origins are per run."""
    if not pairing_code or len(pairing_code) < 8:
        raise ValueError("pairing_code must contain at least 8 characters")

    root = Path(data_dir).expanduser().resolve()
    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if allowed_origins is None:
        allowed_origins = {
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }
    allowed_origins = frozenset(allowed_origins)

    app = FastAPI(title="CV Review Workbench", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]"],
    )
    app.state.sessions = {}
    app.state.images = {}

    def require_origin(request: Request, *, optional: bool = False):
        origin = request.headers.get("origin")
        if origin is None and optional:
            return
        if origin not in allowed_origins:
            raise HTTPException(status_code=403, detail={"code": "origin_rejected"})

    def prune_expired():
        now = time.monotonic()
        expired_sessions = {
            token for token, session in app.state.sessions.items()
            if session["expires_at"] <= now
        }
        for token in expired_sessions:
            app.state.sessions.pop(token, None)
        for handle, image in list(app.state.images.items()):
            if image["owner"] in expired_sessions or now - image["last_used"] > IMAGE_IDLE_TTL_SECONDS:
                app.state.images.pop(handle, None)

    def require_session(request: Request, token: str | None):
        # Browsers commonly omit Origin on same-origin GET fetches. The opaque
        # session header remains mandatory, and any supplied Origin is checked.
        require_origin(request, optional=request.method == "GET")
        prune_expired()
        session = app.state.sessions.get(token or "")
        if session is None:
            raise HTTPException(status_code=401, detail={"code": "session_required"})
        return token

    def get_image(handle: str, owner: str):
        image = app.state.images.get(handle)
        if image is None or image["owner"] != owner:
            raise HTTPException(status_code=404, detail={"code": "image_handle_not_found"})
        image["last_used"] = time.monotonic()
        return image

    @app.get("/api/health")
    def health(request: Request):
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            raise HTTPException(status_code=403, detail={"code": "origin_rejected"})
        return {"status": "ok", "app": "cv-viewer-web"}

    @app.post("/api/session")
    def create_session(request: Request, payload: dict):
        require_origin(request)
        candidate = payload.get("pairing_code") if isinstance(payload, dict) else None
        if not isinstance(candidate, str) or not secrets.compare_digest(candidate, pairing_code):
            raise HTTPException(status_code=401, detail={"code": "pairing_code_invalid"})
        token = secrets.token_urlsafe(32)
        app.state.sessions[token] = {"expires_at": time.monotonic() + SESSION_TTL_SECONDS}
        return {"session_token": token, "expires_in": SESSION_TTL_SECONDS}

    @app.post("/api/images/view")
    async def open_image(
        request: Request,
        file: UploadFile = File(...),
        session_token: str | None = Header(default=None, alias="X-CV-Session"),
    ):
        owner = require_session(request, session_token)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(status_code=415, detail={"code": "unsupported_image_format"})

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=suffix, delete=False) as temporary:
                temp_path = Path(temporary.name)
                total = 0
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail={"code": "image_too_large"})
                    temporary.write(chunk)
            try:
                loaded = imgio.load(temp_path)
                if loaded["width"] * loaded["height"] > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail={"code": "image_dimensions_too_large"})
                display = imgio.to_png_bytes(imgio.to_display_rgb(loaded["array"]))
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=415, detail={"code": "image_decode_failed"}) from None
        finally:
            await file.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        for old_handle, old_image in list(app.state.images.items()):
            if old_image["owner"] == owner:
                app.state.images.pop(old_handle, None)
        handle = uuid.uuid4().hex
        app.state.images[handle] = {
            "owner": owner,
            "array": loaded["array"],
            "display": display,
            "last_used": time.monotonic(),
        }
        return {
            "image_handle": handle,
            "width": loaded["width"],
            "height": loaded["height"],
            "bit_depth": loaded["bit_depth"],
            "channels": loaded["channels"],
        }

    @app.get("/api/images/{handle}/display")
    def image_display(
        handle: str,
        request: Request,
        session_token: str | None = Header(default=None, alias="X-CV-Session"),
    ):
        owner = require_session(request, session_token)
        image = get_image(handle, owner)
        return Response(
            image["display"], media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/images/{handle}/pixel")
    def image_pixel(
        handle: str,
        x: int,
        y: int,
        request: Request,
        session_token: str | None = Header(default=None, alias="X-CV-Session"),
    ):
        owner = require_session(request, session_token)
        image = get_image(handle, owner)
        try:
            value = imgio.value_at(image["array"], x, y)
        except IndexError:
            raise HTTPException(status_code=422, detail={"code": "pixel_out_of_bounds"}) from None
        return {"x": x, "y": y, "value": value}

    @app.delete("/api/images/{handle}", status_code=204)
    def close_image(
        handle: str,
        request: Request,
        session_token: str | None = Header(default=None, alias="X-CV-Session"),
    ):
        owner = require_session(request, session_token)
        get_image(handle, owner)
        app.state.images.pop(handle, None)
        return Response(status_code=204)

    dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
    if (dist_dir / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="web")

    return app


def main():
    import uvicorn

    port = int(os.environ.get("CV_VIEWER_PORT", "8765"))
    code = os.environ.get("CV_VIEWER_PAIRING_CODE") or secrets.token_urlsafe(18)
    data_dir = Path(os.environ.get("CV_VIEWER_DATA_DIR", str(Path.home() / ".cv-viewer-web")))
    app = create_app(pairing_code=code, data_dir=data_dir)
    print(f"CV Review Workbench http://127.0.0.1:{port} | local pairing code: {code}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)


if __name__ == "__main__":
    main()
