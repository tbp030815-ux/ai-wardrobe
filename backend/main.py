"""
AI 智能衣橱 — FastAPI 后端入口
"""
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.auth import current_user_id
from api.auth import router as auth_router
from api.model import router as model_router
from api.recommendation import router as recommendation_router
from api.tryon import router as tryon_router
from api.upload import router as upload_router
from api.wardrobe import router as wardrobe_router
from config import Settings, get_settings
from storage.database import init_db
from storage.uploads_store import UPLOAD_URL_PREFIX, resolve_upload_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AI Wardrobe API",
    description="智能衣橱管理系统",
    version="1.0.0",
    lifespan=lifespan,
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.exception_handler(StarletteHTTPException)
async def redirect_uploads_to_the_app(request: Request, exc: StarletteHTTPException):
    """未登录时直接在地址栏打开图片：回前端登录页，而不是吐一串 JSON。

    只对浏览器导航跳转（Accept 含 `text/html`）。`<img>` 的请求保持 401 ——
    给它 302 到登录页 HTML 只会变成一张坏图，而且 HTML 会被当图片缓存。
    """
    if (
        exc.status_code == 401
        and request.url.path.startswith(UPLOAD_URL_PREFIX)
        and "text/html" in request.headers.get("accept", "")
    ):
        # 带上原始地址：登录成功后前端会校验同源再跳回来
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(f"/?next={quote(target, safe='')}", status_code=302)
    return await http_exception_handler(request, exc)


@app.get("/uploads/{path:path}")
async def serve_upload(
    path: str,
    user_id: int = Depends(current_user_id),
    settings: Settings = Depends(get_settings),
):
    """上传图片**必须登录后才能读**。

    不能挂 `StaticFiles`：它是公开的，知道文件名就能绕开登录看图。
    路径映射走 `resolve_upload_path`，`..` / 绝对路径 / Windows 盘符都由它挡掉；
    子目录（`uploads/tryon/`）必须保留，不能取 `Path(url).name`。
    """
    file_path = resolve_upload_path(settings.upload_dir, f"{UPLOAD_URL_PREFIX}{path}")
    # 先确认是可读文件：FileResponse 对不存在的路径会抛 RuntimeError（500）
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        file_path,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(wardrobe_router)
app.include_router(recommendation_router)
app.include_router(model_router)
app.include_router(tryon_router)


@app.get("/")
async def root():
    return {"message": "AI 智能衣橱 API", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
