"""
衣柜查询 API
"""
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from services.garment_roles import CATEGORY_ROLE
from storage.clothes_store import get_clothes, list_clothes
from storage.database import get_db

router = APIRouter()


@router.get("/api/wardrobe")
async def wardrobe_list(
    user_id: int = 1,
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
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await get_clothes(db, clothes_id)
    if row is None:
        raise HTTPException(status_code=404, detail="衣物不存在")
    return dict(row)
