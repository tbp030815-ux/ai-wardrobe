"""
AI 智能衣橱 — FastAPI 后端入口
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.recommendation import router as recommendation_router
from api.upload import router as upload_router
from api.wardrobe import router as wardrobe_router
from storage.database import init_db


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

# 挂载静态文件（上传的图片）
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(upload_router)
app.include_router(wardrobe_router)
app.include_router(recommendation_router)


@app.get("/")
async def root():
    return {"message": "AI 智能衣橱 API", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
