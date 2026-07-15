from __future__ import annotations

import logging
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import get_settings
from .database import SessionLocal
from .migrate import run as migrate
from .routers import admin, client


settings = get_settings()
logger = logging.getLogger("tk-platform")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(settings.data_dir / "server.log", maxBytes=5_000_000, backupCount=7, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

app = FastAPI(title="TK 直播开播检测平台", version="2.4.0", docs_url="/api/docs" if settings.env != "production" else None)
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


PUBLIC_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>维度 TikTok 直播开播助手</title><style>
*{box-sizing:border-box}body{margin:0;background:#07101f;color:#e7edf8;font:15px/1.7 "Microsoft YaHei UI",sans-serif}a{color:inherit}
.nav{height:68px;display:flex;align-items:center;justify-content:space-between;max-width:1120px;margin:auto;padding:0 24px}.brand{font-weight:800;font-size:18px}.tag{color:#8ca0bf}
.hero{max-width:1120px;margin:72px auto 0;padding:0 24px;display:grid;grid-template-columns:1.25fr .75fr;gap:44px;align-items:center}.badge{display:inline-block;color:#63d6a4;background:#122c29;border:1px solid #245846;padding:5px 12px;border-radius:99px}.hero h1{font-size:48px;line-height:1.15;margin:18px 0}.hero p{color:#9badc9;font-size:17px}.btn{display:inline-block;background:#3e7bfa;padding:13px 24px;border-radius:10px;text-decoration:none;font-weight:700;margin-top:15px}.panel{background:#0e1a2d;border:1px solid #1d2c45;border-radius:20px;padding:24px;box-shadow:0 24px 80px #0008}.status{display:flex;justify-content:space-between;padding:14px 0;border-bottom:1px solid #21304a}.pass{color:#62d49e}.warn{color:#f5c465}.grid{max-width:1120px;margin:90px auto;padding:0 24px;display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#0c1728;border:1px solid #192943;border-radius:14px;padding:22px}.card h3{margin:0 0 8px}.card p{color:#8fa2c0}.foot{max-width:1120px;margin:40px auto;padding:30px 24px;color:#7386a3;border-top:1px solid #17263e}@media(max-width:800px){.hero{grid-template-columns:1fr}.hero h1{font-size:36px}.grid{grid-template-columns:1fr}}
</style></head><body><nav class="nav"><div class="brand">◈ 维度 TikTok 直播开播助手</div><div class="tag">开播前，先检查</div></nav>
<main class="hero"><section><span class="badge">专业直播技术准备度检测</span><h1>让每一次电脑直播<br>从准备充分开始</h1><p>集中检查网络稳定性、电脑性能、直播设备、系统状态和直播软件准备情况，快速定位影响开播的实际问题。</p><a class="btn" href="/api/v1/client/update">下载最新版</a></section>
<section class="panel"><h3>开播检查概览</h3><div class="status"><span>网络持续上传</span><b class="pass">通过</b></div><div class="status"><span>摄像头与麦克风</span><b class="pass">通过</b></div><div class="status"><span>硬件编码能力</span><b class="warn">建议确认</b></div><div class="status"><span>系统准备状态</span><b class="pass">通过</b></div></section></main>
<section class="grid"><article class="card"><h3>一次完成全面检查</h3><p>七组核心检查统一执行，结果按严重程度排列。</p></article><article class="card"><h3>问题说清楚</h3><p>每个异常都包含原因、影响和可执行处理建议。</p></article><article class="card"><h3>适合工作室协作</h3><p>检查报告可保存、导出并主动上传给技术支持。</p></article></section>
<footer class="foot">本产品仅判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。</footer></body></html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/download/", response_class=HTMLResponse, include_in_schema=False)
def download_page() -> str:
    return PUBLIC_PAGE


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
