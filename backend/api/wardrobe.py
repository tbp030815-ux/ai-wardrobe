"""
衣柜查询 API
"""
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from storage.clothes_store import get_clothes, list_clothes
from storage.database import get_db

router = APIRouter()


@router.get("/api/wardrobe")
async def wardrobe_list(
    user_id: int = 1,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await list_clothes(db, user_id)
    return [dict(r) for r in rows]


@router.get("/api/clothes/{clothes_id}")
async def clothes_detail(
    clothes_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await get_clothes(db, clothes_id)
    if row is None:
        raise HTTPException(status_code=404, detail="衣物不存在")
    return dict(row)
