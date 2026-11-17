"""
衣物上传 API：上传 → 抠图 → 识别 → 入库
"""
import uuid
from pathlib import Path

import aiosqlite
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.auth import current_user_id
from config import Settings, get_settings
from services.background_removal import remove_background
from services.seedream_client import analyze_clothes
from storage.clothes_store import get_clothes, save_clothes
from storage.database import get_db

router = APIRouter()


@router.post("/api/upload")
async def upload_clothes(
    file: UploadFile = File(...),
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 1. 抠图（本地 rembg，失败则拒绝上传）
    try:
        cropped_bytes = await remove_background(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. 保存原图 + 抠图结果
    name = uuid.uuid4().hex
    ext = Path(file.filename or "").suffix.lower() or ".png"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    image_file = settings.upload_dir / f"{name}{ext}"
    cropped_file = settings.upload_dir / f"{name}_cropped.png"
    image_file.write_bytes(image_bytes)
    cropped_file.write_bytes(cropped_bytes)

    # 3. AI 识别语义（失败不阻塞入库，语义字段留空）
    semantics: dict = {}
    if settings.api_key:
        try:
            semantics = await analyze_clothes(
                image_bytes,
                api_key=settings.api_key,
                model=settings.vision_model,
                base_url=settings.base_url,
            )
        except (ValueError, httpx.HTTPError):
            semantics = {}

    # 4. 入库
    clothes_id = await save_clothes(
        db,
        user_id=user_id,
        image_path=f"/uploads/{image_file.name}",
        cropped_path=f"/uploads/{cropped_file.name}",
        category=semantics.get("category"),
        sub_category=semantics.get("sub_category"),
        color=semantics.get("color"),
        style=semantics.get("style"),
        season=semantics.get("season"),
    )

    row = await get_clothes(db, clothes_id, user_id=user_id)
    return dict(row)
