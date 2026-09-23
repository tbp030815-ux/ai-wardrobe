"""
衣物数据存取
"""
import aiosqlite


async def save_clothes(
    db: aiosqlite.Connection,
    user_id: int,
    image_path: str,
    cropped_path: str | None = None,
    category: str | None = None,
    sub_category: str | None = None,
    color: str | None = None,
    style: str | None = None,
    season: str | None = None,
    tags: str | None = None,
) -> int:
    """保存衣物记录，返回新记录 id"""
    cursor = await db.execute(
        """
        INSERT INTO clothes
            (user_id, image_path, cropped_path, category, sub_category, color, style, season, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, image_path, cropped_path, category, sub_category, color, style, season, tags),
    )
    await db.commit()
    return cursor.lastrowid


async def get_clothes(db: aiosqlite.Connection, clothes_id: int) -> aiosqlite.Row | None:
    """按 id 查询衣物，不存在返回 None"""
    cursor = await db.execute("SELECT * FROM clothes WHERE id = ?", (clothes_id,))
    return await cursor.fetchone()


async def list_clothes(db: aiosqlite.Connection, user_id: int) -> list[aiosqlite.Row]:
    """列出指定用户的全部衣物（按创建时间倒序）"""
    cursor = await db.execute(
        "SELECT * FROM clothes WHERE user_id = ? ORDER BY created_at DESC, id DESC",
        (user_id,),
    )
    return await cursor.fetchall()
