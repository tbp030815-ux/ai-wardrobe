"""
穿搭记录（试穿结果）数据存取

`outfits` 表见 storage/database.py，无需迁移。
"""
import json

import aiosqlite

# 历史列表缺省条数。结果图是按 MB 计的，不设上限迟早把前端拖垮
DEFAULT_LIST_LIMIT = 20


async def save_outfit(
    db: aiosqlite.Connection,
    *,
    user_id: int,
    model_id: int | None,
    clothes_ids: list[int],
    generated_by: str,
    result_image_url: str,
) -> int:
    """保存一次试穿结果，返回新记录 id。

    `clothes_ids` 表里是 TEXT 列，存 JSON 字符串 —— 出参由 `row_to_outfit` 还原成数组。
    """
    cursor = await db.execute(
        """
        INSERT INTO outfits (user_id, model_id, clothes_ids, generated_by, result_image_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, model_id, json.dumps(clothes_ids), generated_by, result_image_url),
    )
    await db.commit()
    return cursor.lastrowid


async def get_outfit(db: aiosqlite.Connection, outfit_id: int) -> aiosqlite.Row | None:
    """按 id 查询穿搭记录，不存在返回 None"""
    cursor = await db.execute("SELECT * FROM outfits WHERE id = ?", (outfit_id,))
    return await cursor.fetchone()


async def list_outfits(
    db: aiosqlite.Connection, user_id: int, limit: int = DEFAULT_LIST_LIMIT
) -> list[aiosqlite.Row]:
    """列出该用户的试穿历史（最新优先）"""
    cursor = await db.execute(
        """
        SELECT * FROM outfits WHERE user_id = ?
        ORDER BY created_at DESC, id DESC LIMIT ?
        """,
        (user_id, limit),
    )
    return await cursor.fetchall()


def _parse_clothes_ids(raw: str | None) -> list[int]:
    """TEXT 列 → 数组。任何读不出来的情况都退化成空数组，不让响应 500"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    return parsed if isinstance(parsed, list) else []


def row_to_outfit(row: aiosqlite.Row) -> dict:
    """把 DB 行转成出参字典：`clothes_ids` 库里是 TEXT，出参必须是数组"""
    payload = dict(row)
    payload["clothes_ids"] = _parse_clothes_ids(payload.get("clothes_ids"))
    return payload
