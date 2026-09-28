"""
穿搭记录数据存取层测试（阶段四 TDD 循环 I）

`outfits` 表已存在于 storage/database.py，无需改 schema。
"""
import json

import aiosqlite
import pytest_asyncio

from storage.database import create_tables
from storage.outfits_store import (
    delete_outfit,
    get_outfit,
    list_outfits,
    row_to_outfit,
    save_outfit,
)

MODEL_ID = "doubao-seedream-4-0-250828"


@pytest_asyncio.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await create_tables(conn)
        yield conn


async def save_sample(db, *, user_id=1, clothes_ids=(3, 4), model_id=1):
    return await save_outfit(
        db,
        user_id=user_id,
        model_id=model_id,
        clothes_ids=list(clothes_ids),
        generated_by=MODEL_ID,
        result_image_url="/uploads/tryon/abc.jpg",
    )


async def test_save_and_get_outfit(db):
    outfit_id = await save_sample(db)

    row = await get_outfit(db, outfit_id)

    assert row["user_id"] == 1
    assert row["model_id"] == 1
    assert row["generated_by"] == MODEL_ID
    assert row["result_image_url"] == "/uploads/tryon/abc.jpg"


async def test_get_outfit_returns_none_for_unknown_id(db):
    assert await get_outfit(db, 999) is None


async def test_clothes_ids_round_trip_as_json_text(db):
    """表里是 TEXT 列，存进去必须是 JSON 字符串"""
    outfit_id = await save_sample(db, clothes_ids=(3, 7, 12))

    row = await get_outfit(db, outfit_id)

    assert json.loads(row["clothes_ids"]) == [3, 7, 12]


async def test_row_to_outfit_returns_clothes_ids_as_list(db):
    outfit_id = await save_sample(db, clothes_ids=(3, 7))

    payload = row_to_outfit(await get_outfit(db, outfit_id))

    assert payload["clothes_ids"] == [3, 7]
    assert payload["id"] == outfit_id


async def test_row_to_outfit_treats_null_clothes_ids_as_empty_list(db):
    """schema 允许 NULL（非本模块写入的行），直接 json.loads(None) 会 500"""
    await db.execute(
        "INSERT INTO outfits (user_id, model_id, result_image_url) VALUES (1, 1, '/x.jpg')"
    )
    await db.commit()

    payload = row_to_outfit(await get_outfit(db, 1))

    assert payload["clothes_ids"] == []


async def test_row_to_outfit_survives_broken_json(db):
    await db.execute(
        "INSERT INTO outfits (user_id, model_id, clothes_ids) VALUES (1, 1, 'not json')"
    )
    await db.commit()

    payload = row_to_outfit(await get_outfit(db, 1))

    assert payload["clothes_ids"] == []


async def test_list_outfits_is_newest_first(db):
    first = await save_sample(db, clothes_ids=(1,))
    second = await save_sample(db, clothes_ids=(2,))

    rows = await list_outfits(db, 1)

    assert [row["id"] for row in rows] == [second, first]


async def test_list_outfits_respects_limit(db):
    for index in range(5):
        await save_sample(db, clothes_ids=(index,))

    rows = await list_outfits(db, 1, limit=3)

    assert len(rows) == 3


async def test_list_outfits_is_scoped_to_user(db):
    await save_sample(db, user_id=1)
    await save_sample(db, user_id=2)

    assert len(await list_outfits(db, 1)) == 1


# ---------- delete_outfit ----------

async def test_delete_outfit_removes_the_row_and_returns_it(db):
    """必须返回被删的行：调用方要拿 result_image_url 去删磁盘上的结果图，
    那才是「结果图持续累积」的解药"""
    outfit_id = await save_sample(db)

    deleted = await delete_outfit(db, 1, outfit_id)

    assert deleted["result_image_url"] == "/uploads/tryon/abc.jpg"
    assert await get_outfit(db, outfit_id) is None


async def test_delete_outfit_returns_none_for_unknown_id(db):
    assert await delete_outfit(db, 1, 999) is None


async def test_delete_outfit_is_scoped_to_user(db):
    theirs = await save_sample(db, user_id=2)

    assert await delete_outfit(db, 1, theirs) is None
    assert await get_outfit(db, theirs) is not None


async def test_delete_outfit_leaves_other_rows_alone(db):
    keep = await save_sample(db, clothes_ids=(1,))
    drop = await save_sample(db, clothes_ids=(2,))

    assert await delete_outfit(db, 1, drop) is not None

    rows = await list_outfits(db, 1)
    assert [row["id"] for row in rows] == [keep]
