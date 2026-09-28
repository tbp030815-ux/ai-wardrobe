"""
模特（全身照）管理 API：上传 / 列表 / 设为默认 / 删除

模特照**不做抠图**：试穿时喂给图像编辑模型的是原图，抠图结果只用于衣柜卡片展示。
"""
import io
import uuid

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from config import Settings, get_settings
from storage.database import get_db
from storage.model_store import (
    delete_model,
    get_model,
    list_models,
    row_to_model,
    save_model,
    set_default_model,
)
from storage.uploads_store import delete_upload_files

router = APIRouter()


@router.post("/api/model")
async def upload_model(
    file: UploadFile = File(...),
    user_id: int = 1,
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 在这里挡掉坏图，而不是等 60 秒的付费生成跑完才报错
    try:
        image_format = Image.open(io.BytesIO(image_bytes)).format
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="无法识别的图片格式")

    # 扩展名取自**图片内容**而非文件名：浏览器传来的 filename 经常是错的
    # （.png 里装 JPEG），而 StaticFiles 会照着扩展名发 Content-Type
    ext = ".jpg" if image_format in ("JPEG", "MPO") else f".{image_format.lower()}"
    name = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{name}{ext}").write_bytes(image_bytes)

    model_id = await save_model(db, user_id=user_id, image_path=f"/uploads/{name}{ext}")
    return row_to_model(await get_model(db, model_id))


@router.get("/api/models")
async def models_list(
    user_id: int = 1,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await list_models(db, user_id)
    return [row_to_model(row) for row in rows]


@router.put("/api/models/{model_id}/default")
async def set_default(
    model_id: int,
    user_id: int = 1,
    db: aiosqlite.Connection = Depends(get_db),
):
    if not await set_default_model(db, user_id, model_id):
        raise HTTPException(status_code=404, detail="模特不存在")

    return row_to_model(await get_model(db, model_id))


@router.delete("/api/models/{model_id}")
async def model_delete(
    model_id: int,
    user_id: int = 1,
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """删除模特照，返回被删的那一行。

    删掉的若是默认模特，`delete_model` 会在同一个事务里把最新的一张提为默认 ——
    前端拿到的「哪张是默认」始终以服务端为准，不自己猜。
    """
    row = await delete_model(db, user_id, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="模特不存在")

    delete_upload_files(settings.upload_dir, [row["image_path"]])
    return row_to_model(row)
