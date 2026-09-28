"""
衣物数据存取层测试（TDD 循环 1）
"""
import pytest
import pytest_asyncio
import aiosqlite

from storage.database import create_tables
from storage.clothes_store import delete_clothes, save_clothes, get_clothes, list_clothes


@pytest_asyncio.fixture
async def db():
    """内存数据库，预建表结构"""
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await create_tables(conn)
        yield conn


async def test_save_and_get_clothes(db):
    clothes_id = await save_clothes(
        db, user_id=1, image_path="uploads/a.jpg", cropped_path="uploads/a.png"
    )
    row = await get_clothes(db, clothes_id)

    assert row["user_id"] == 1
    assert row["image_path"] == "uploads/a.jpg"
    assert row["cropped_path"] == "uploads/a.png"
    assert row["id"] == clothes_id


async def test_save_clothes_with_semantics(db):
    clothes_id = await save_clothes(
        db,
        user_id=1,
        image_path="uploads/b.jpg",
        cropped_path="uploads/b.png",
        category="上衣",
        sub_category="T恤",
        color="藏青色",
        style="休闲",
        season="夏季",
    )
    row = await get_clothes(db, clothes_id)

    assert row["category"] == "上衣"
    assert row["sub_category"] == "T恤"
    assert row["color"] == "藏青色"
    assert row["style"] == "休闲"
    assert row["season"] == "夏季"


async def test_list_clothes_returns_all(db):
    await save_clothes(db, user_id=1, image_path="uploads/a.jpg")
    await save_clothes(db, user_id=1, image_path="uploads/b.jpg")

    rows = await list_clothes(db, user_id=1)

    assert len(rows) == 2
    paths = {r["image_path"] for r in rows}
    assert paths == {"uploads/a.jpg", "uploads/b.jpg"}


async def test_list_clothes_only_returns_own_user(db):
    await save_clothes(db, user_id=1, image_path="uploads/a.jpg")
    await save_clothes(db, user_id=2, image_path="uploads/b.jpg")

    rows = await list_clothes(db, user_id=1)

    assert len(rows) == 1
    assert rows[0]["image_path"] == "uploads/a.jpg"


async def test_get_clothes_returns_none_when_missing(db):
    row = await get_clothes(db, 999)
    assert row is None


# ---------- delete_clothes ----------

async def test_delete_clothes_removes_the_row_and_returns_it(db):
    """必须返回被删的行：调用方要拿 image_path / cropped_path 去删磁盘上的两个文件，
    删完再查就来不及了（行已经没了）"""
    clothes_id = await save_clothes(
        db, user_id=1, image_path="/uploads/a.jpg", cropped_path="/uploads/a_cropped.png"
    )

    deleted = await delete_clothes(db, 1, clothes_id)

    assert deleted["image_path"] == "/uploads/a.jpg"
    assert deleted["cropped_path"] == "/uploads/a_cropped.png"
    assert await get_clothes(db, clothes_id) is None


async def test_delete_clothes_returns_none_for_unknown_id(db):
    assert await delete_clothes(db, 1, 999) is None


async def test_delete_clothes_is_scoped_to_user(db):
    """漏掉 user_id 就能删掉别人的衣物"""
    theirs = await save_clothes(db, user_id=2, image_path="/uploads/b.jpg")

    assert await delete_clothes(db, 1, theirs) is None
    assert await get_clothes(db, theirs) is not None


async def test_delete_clothes_leaves_other_rows_alone(db):
    keep = await save_clothes(db, user_id=1, image_path="/uploads/a.jpg")
    drop = await save_clothes(db, user_id=1, image_path="/uploads/b.jpg")

    await delete_clothes(db, 1, drop)

    assert [row["id"] for row in await list_clothes(db, 1)] == [keep]
