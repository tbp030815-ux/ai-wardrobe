"""
模特（全身照）数据存取

`models` 表见 storage/database.py，无需迁移。
"""
import aiosqlite


async def save_model(
    db: aiosqlite.Connection,
    user_id: int,
    image_path: str,
    height_cm: float | None = None,
    body_type: str | None = None,
) -> int:
    """保存模特照，返回新记录 id。

    该用户的**第一张自动成为默认** —— 否则上传完模特直接去试穿会拿不到模特。
    之后的照片不抢默认，切换默认只能显式调 `set_default_model`。
    """
    cursor = await db.execute(
        "SELECT COUNT(*) FROM models WHERE user_id = ?", (user_id,)
    )
    is_first = (await cursor.fetchone())[0] == 0

    cursor = await db.execute(
        """
        INSERT INTO models (user_id, image_path, height_cm, body_type, is_default)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, image_path, height_cm, body_type, 1 if is_first else 0),
    )
    await db.commit()
    return cursor.lastrowid


async def get_model(db: aiosqlite.Connection, model_id: int) -> aiosqlite.Row | None:
    """按 id 查询模特，不存在返回 None"""
    cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
    return await cursor.fetchone()


async def get_default_model(db: aiosqlite.Connection, user_id: int) -> aiosqlite.Row | None:
    """取默认模特，没有则回退到最新一张。

    回退是必要的：手工改库或历史数据里可能一条标记都没有（传了 3 张却从没点过
    「设为默认」），此时返回 None 会让试穿直接 404，而用户明明已经上传过照片。
    """
    cursor = await db.execute(
        """
        SELECT * FROM models WHERE user_id = ?
        ORDER BY is_default DESC, id DESC LIMIT 1
        """,
        (user_id,),
    )
    return await cursor.fetchone()


async def set_default_model(
    db: aiosqlite.Connection, user_id: int, model_id: int
) -> bool:
    """把指定模特设为该用户唯一的默认模特。id 不存在或属于他人时返回 False 且不改动任何状态。

    先置位、再清其余，全部在一个事务里：置位失败就回滚，
    否则「先清零」的写法会在失败时把用户留在「一张默认都没有」的状态。
    `WHERE user_id = ?` 同时完成越权校验 —— 不能把别人的模特设成自己的默认。
    """
    cursor = await db.execute(
        "UPDATE models SET is_default = 1 WHERE id = ? AND user_id = ?",
        (model_id, user_id),
    )
    if cursor.rowcount == 0:
        await db.rollback()
        return False

    await db.execute(
        "UPDATE models SET is_default = 0 WHERE user_id = ? AND id != ?",
        (user_id, model_id),
    )
    await db.commit()
    return True


async def list_models(db: aiosqlite.Connection, user_id: int) -> list[aiosqlite.Row]:
    """列出该用户的全部模特，默认的排最前，其余按最新优先"""
    cursor = await db.execute(
        """
        SELECT * FROM models WHERE user_id = ?
        ORDER BY is_default DESC, created_at DESC, id DESC
        """,
        (user_id,),
    )
    return await cursor.fetchall()


async def delete_model(
    db: aiosqlite.Connection, user_id: int, model_id: int
) -> aiosqlite.Row | None:
    """删除模特，返回**被删的那一行**；id 不存在或不属于该用户时返回 None。

    删掉的若是默认模特，把该用户**最新的一张提为默认**：否则一条默认标记都不剩，
    试穿靠 `get_default_model` 的回退才没坏，但前端的「默认」徽标全灭，状态含糊。
    删到一张不剩时不硬造默认（子查询为 NULL，UPDATE 匹配不到行），
    让试穿走到 400「请先上传一张模特全身照」。
    """
    cursor = await db.execute(
        "DELETE FROM models WHERE id = ? AND user_id = ? RETURNING *",
        (model_id, user_id),
    )
    row = await cursor.fetchone()
    if row is None:
        await db.commit()
        return None

    if row["is_default"]:
        # 补位查询必须带 user_id，否则会把别人的模特提成我的默认
        await db.execute(
            """
            UPDATE models SET is_default = 1
            WHERE user_id = ? AND id = (
                SELECT id FROM models WHERE user_id = ? ORDER BY id DESC LIMIT 1
            )
            """,
            (user_id, user_id),
        )
    await db.commit()
    return row


def row_to_model(row: aiosqlite.Row) -> dict:
    """把 DB 行转成出参字典。

    SQLite 没有原生布尔：`is_default` 读出来是整数 0/1，直接扔给前端会变成 1/0
    而不是 true/false，前端 `model.is_default === true` 之类的判断会静默失效。
    """
    payload = dict(row)
    payload["is_default"] = bool(payload["is_default"])
    return payload
