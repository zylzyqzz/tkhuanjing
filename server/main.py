from __future__ import annotations

import logging
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_db
from .models import DownloadStat, Release, Setting, now_iso
from .public_page import render_home, unavailable_page
from .migrate import run as migrate
from .routers import admin, client


settings = get_settings()
logger = logging.getLogger("tk-platform")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(settings.data_dir / "server.log", maxBytes=5_000_000, backupCount=7, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

app = FastAPI(title="VD开播助手管理平台", version="2.9.1", docs_url="/api/docs" if settings.env != "production" else None)
app.include_router(client.router, prefix="/api/v1/client")
app.include_router(client.router, prefix="/api/client", include_in_schema=False)
app.include_router(admin.router)


@app.get("/api/v1/health", tags=["system"])
def health() -> dict:
    database_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
            database_ok = True
    except Exception:
        logger.exception("health_database_failed")
    assets_ok = (Path(__file__).resolve().parents[1] / "admin" / "dist" / "index.html").is_file()
    return {
        "status": "ok" if database_ok and assets_ok else "degraded",
        "version": app.version,
        "database": "ok" if database_ok else "error",
        "admin_assets": "ok" if assets_ok else "missing",
    }


@app.on_event("startup")
def startup() -> None:
    migrate()
    logger.info("server_started env=%s", settings.env)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:80]
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用", "request_id": request_id}})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", "")
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "request_id": request_id}})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "提交内容格式不正确", "details": exc.errors()}})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home_page(db: Session = Depends(get_db)) -> str:
    values = {row.key: row.value for row in db.scalars(select(Setting)).all()}
    release = db.scalar(select(Release).where(Release.active.is_(True), Release.channel == "stable").limit(1))
    return render_home(values, release)


@app.get("/download/", include_in_schema=False)
def legacy_download_page() -> RedirectResponse:
    return RedirectResponse("/", status_code=308)


@app.get("/download/latest", include_in_schema=False)
def latest_download(db: Session = Depends(get_db)):
    release = db.scalar(select(Release).where(Release.active.is_(True), Release.channel == "stable").limit(1))
    if not release:
        return HTMLResponse(unavailable_page(), status_code=503)
    filename = release.installer_filename or release.filename
    target = settings.downloads_dir / Path(filename).name
    if not target.is_file() or target.stat().st_size != release.file_size:
        logger.error("active_release_file_invalid version=%s file=%s", release.version, target)
        return HTMLResponse(unavailable_page(), status_code=503)
    day = datetime.now().date().isoformat()
    stat = db.get(DownloadStat, {"day": day, "version": release.version})
    if stat:
        stat.count += 1; stat.updated_at = now_iso()
    else:
        db.add(DownloadStat(day=day, version=release.version, count=1))
    db.commit()
    return FileResponse(target, filename=f"WeiDu-WD-Live-Check-{release.version}.exe", media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@app.get("/downloads/{filename}", include_in_schema=False)
def download_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    target = settings.downloads_dir / safe_name
    if not target.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(target, filename=safe_name, media_type="application/octet-stream")


admin_dist = Path(__file__).resolve().parents[1] / "admin" / "dist"
if admin_dist.exists():
    app.mount("/tk-admin/assets", StaticFiles(directory=admin_dist / "assets"), name="admin-assets")


@app.get("/tk-admin/{path:path}", response_class=HTMLResponse, include_in_schema=False)
def admin_page(path: str = ""):
    index = admin_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>管理端尚未构建</h1><p>请在 admin 目录执行 npm install 与 npm run build。</p>", status_code=503)


@app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
def branded_not_found(path: str) -> HTMLResponse:
    return HTMLResponse("""<!doctype html><meta charset='utf-8'><title>页面不存在</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#030812;color:#eef7ff;font-family:'Microsoft YaHei UI';text-align:center}.box{padding:46px;border:1px solid #244768;border-radius:22px;background:#0a1726}b{font:900 64px/1 monospace;color:#4dbbff}p{color:#8197ae}a{color:#55d6d0}</style><div class='box'><b>404</b><h1>页面不存在</h1><p>请返回产品主页或检查访问地址。</p><a href='/'>返回主页</a></div>""", status_code=404)
