"""
衣柜查询 / 删除 API
"""
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from api.auth import current_user_id
from config import Settings, get_settings
from services.garment_roles import CATEGORY_ROLE
from storage.clothes_store import delete_clothes, get_clothes, list_clothes
from storage.database import get_db
from storage.uploads_store import delete_upload_files

router = APIRouter()


@router.get("/api/wardrobe")
async def wardrobe_list(
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await list_clothes(db, user_id)
    # role 是算出来的，不入库：改了映射规则不会让历史数据变陈旧。
    # 识别失败的衣物 category 为 null，role 也就是 null，前端据此归入单独分组。
    return [
        {**dict(row), "role": CATEGORY_ROLE.get(row["category"] or "")} for row in rows
    ]


@router.get("/api/clothes/{clothes_id}")
async def clothes_detail(
    clothes_id: int,
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await get_clothes(db, clothes_id, user_id=user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="衣物不存在")
    return dict(row)


@router.delete("/api/clothes/{clothes_id}")
async def clothes_delete(
    clothes_id: int,
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """删除衣物：先删库、再删磁盘上的两个文件。

    顺序不能反 —— 先删文件而删库失败，会留下一行指向不存在图片的记录，
    衣柜页上就是一个永远加载不出来的破图。反过来最坏只是留个孤儿文件。
    """
    row = await delete_clothes(db, user_id, clothes_id)
    if row is None:
        raise HTTPException(status_code=404, detail="衣物不存在")

    delete_upload_files(settings.upload_dir, [row["image_path"], row["cropped_path"]])
    return dict(row)
