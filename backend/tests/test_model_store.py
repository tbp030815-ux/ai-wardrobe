"""
模特数据存取层测试（阶段四 TDD 循环 I）

`models` 表已存在于 storage/database.py，无需改 schema。
"""
import aiosqlite
import pytest_asyncio

from storage.database import create_tables
from storage.model_store import (
    get_default_model,
    get_model,
    list_models,
    row_to_model,
    save_model,
    set_default_model,
)


@pytest_asyncio.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await create_tables(conn)
        yield conn


async def test_save_and_get_model(db):
    model_id = await save_model(db, user_id=1, image_path="/uploads/m.jpg")

    row = await get_model(db, model_id)

    assert row["user_id"] == 1
    assert row["image_path"] == "/uploads/m.jpg"


async def test_get_model_returns_none_for_unknown_id(db):
    assert await get_model(db, 999) is None


async def test_first_model_becomes_default_automatically(db):
    """否则第一次试穿就没有可用模特，直接 404"""
    model_id = await save_model(db, user_id=1, image_path="/uploads/a.jpg")

    assert (await get_default_model(db, 1))["id"] == model_id


async def test_later_models_do_not_steal_default(db):
    first = await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    await save_model(db, user_id=1, image_path="/uploads/b.jpg")

    assert (await get_default_model(db, 1))["id"] == first


async def test_default_is_per_user(db):
    """每条语句都必须带 user_id：漏掉就会被另一个用户的行选中"""
    mine = await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    theirs = await save_model(db, user_id=2, image_path="/uploads/b.jpg")

    assert (await get_default_model(db, 1))["id"] == mine
    assert (await get_default_model(db, 2))["id"] == theirs


async def test_default_returns_none_when_user_has_no_model(db):
    assert await get_default_model(db, 1) is None


async def test_default_falls_back_to_newest_without_flag(db):
    """手工改库或历史数据里可能一条默认标记都没有，此时不该返回 None"""
    await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    newest = await save_model(db, user_id=1, image_path="/uploads/b.jpg")
    await db.execute("UPDATE models SET is_default = 0")
    await db.commit()

    assert (await get_default_model(db, 1))["id"] == newest


async def test_set_default_is_exclusive(db):
    first = await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    second = await save_model(db, user_id=1, image_path="/uploads/b.jpg")

    assert await set_default_model(db, 1, second) is True

    assert (await get_default_model(db, 1))["id"] == second
    assert (await get_model(db, first))["is_default"] == 0


async def test_set_default_returns_false_for_unknown_id(db):
    first = await save_model(db, user_id=1, image_path="/uploads/a.jpg")

    assert await set_default_model(db, 1, 999) is False
    # 失败必须整体回滚，不能把原有默认清空
    assert (await get_default_model(db, 1))["id"] == first


async def test_set_default_is_idempotent(db):
    """用户连点两次「设为默认」不该第二次返回 404"""
    model_id = await save_model(db, user_id=1, image_path="/uploads/a.jpg")

    assert await set_default_model(db, 1, model_id) is True
    assert await set_default_model(db, 1, model_id) is True
    assert (await get_default_model(db, 1))["id"] == model_id


async def test_set_default_rejects_another_users_model(db):
    mine = await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    theirs = await save_model(db, user_id=2, image_path="/uploads/b.jpg")

    assert await set_default_model(db, 1, theirs) is False
    assert (await get_default_model(db, 1))["id"] == mine


async def test_list_models_puts_default_first(db):
    first = await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    second = await save_model(db, user_id=1, image_path="/uploads/b.jpg")
    await set_default_model(db, 1, second)

    rows = await list_models(db, 1)

    assert [row["id"] for row in rows] == [second, first]


async def test_list_models_is_newest_first_after_the_default(db):
    first = await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    second = await save_model(db, user_id=1, image_path="/uploads/b.jpg")
    third = await save_model(db, user_id=1, image_path="/uploads/c.jpg")
    await set_default_model(db, 1, second)

    rows = await list_models(db, 1)

    assert [row["id"] for row in rows] == [second, third, first]


async def test_list_models_is_scoped_to_user(db):
    await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    await save_model(db, user_id=2, image_path="/uploads/b.jpg")

    assert len(await list_models(db, 1)) == 1


async def test_row_to_model_converts_is_default_to_real_bool(db):
    """SQLite 存的是 INTEGER：直接扔给前端会变成 1/0 而不是 true/false"""
    model_id = await save_model(db, user_id=1, image_path="/uploads/a.jpg")

    payload = row_to_model(await get_model(db, model_id))

    assert payload["is_default"] is True


async def test_row_to_model_keeps_false_as_bool(db):
    await save_model(db, user_id=1, image_path="/uploads/a.jpg")
    second = await save_model(db, user_id=1, image_path="/uploads/b.jpg")

    payload = row_to_model(await get_model(db, second))

    assert payload["is_default"] is False
