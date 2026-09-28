"""
上传 + 衣柜 API 测试（TDD 循环 4）

外部依赖（rembg 抠图、火山方舟识别）在测试中替换为可控实现，
被测的是 API 层的流程编排与错误处理逻辑。
"""
import asyncio
import io
import sqlite3

import aiosqlite
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from config import Settings
from main import app
from storage.database import create_tables, get_db


def make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (200, 100, 50)).save(buf, format="PNG")
    return buf.getvalue()


def count_rows(db_path, table: str) -> int:
    """直接查库：只看 HTTP 响应的话，不删库的实现也能全绿"""

    async def _count():
        async with aiosqlite.connect(str(db_path)) as conn:
            cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")
            return (await cursor.fetchone())[0]

    return asyncio.run(_count())


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def setup_db():
        async with aiosqlite.connect(str(db_path)) as conn:
            await create_tables(conn)

    asyncio.run(setup_db())

    async def override_db():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    test_settings = Settings(
        api_key="test-key",
        vision_model="test-vision-model",
        image_model="test-image-model",
        base_url="https://test.example.com/api/v3",
        upload_dir=upload_dir,
    )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[__import__("config").get_settings] = lambda: test_settings

    async def fake_remove_background(image_bytes: bytes) -> bytes:
        return make_png_bytes()

    async def fake_analyze_clothes(image_bytes: bytes, **kwargs) -> dict:
        return {
            "category": "上衣",
            "sub_category": "T恤",
            "color": "藏青色",
            "style": "休闲",
            "season": "夏季",
        }

    monkeypatch.setattr("api.upload.remove_background", fake_remove_background)
    monkeypatch.setattr("api.upload.analyze_clothes", fake_analyze_clothes)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_upload_returns_clothes_with_semantics(client):
    response = client.post(
        "/api/upload",
        files={"file": ("shirt.jpg", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["category"] == "上衣"
    assert data["sub_category"] == "T恤"
    assert data["color"] == "藏青色"
    assert data["image_path"].startswith("/uploads/")
    assert data["cropped_path"].startswith("/uploads/")
    assert data["cropped_path"].endswith(".png")


def test_upload_saves_files_on_disk(client, tmp_path):
    client.post(
        "/api/upload",
        files={"file": ("shirt.jpg", make_png_bytes(), "image/png")},
    )

    upload_dir = tmp_path / "uploads"
    files = list(upload_dir.iterdir())
    assert len(files) == 2  # 原图 + 抠图结果


def test_upload_rejects_invalid_image(client, monkeypatch):
    async def failing_remove(image_bytes: bytes) -> bytes:
        raise ValueError("无法识别的图片格式")

    monkeypatch.setattr("api.upload.remove_background", failing_remove)

    response = client.post(
        "/api/upload",
        files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400


def test_upload_keeps_record_when_analysis_fails(client, monkeypatch):
    """识别失败不应阻塞入库，语义字段留空"""
    async def failing_analyze(image_bytes: bytes, **kwargs) -> dict:
        raise ValueError("识别接口调用失败")

    monkeypatch.setattr("api.upload.analyze_clothes", failing_analyze)

    response = client.post(
        "/api/upload",
        files={"file": ("shirt.jpg", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["category"] is None
    assert data["cropped_path"] is not None


def test_wardrobe_item_exposes_role(client):
    """试穿页要按角色分组，前端不该再复制一份 category → role 映射"""
    client.post(
        "/api/upload",
        files={"file": ("a.jpg", make_png_bytes(), "image/png")},
    )

    assert client.get("/api/wardrobe").json()[0]["role"] == "上衣"


def test_wardrobe_role_is_none_for_unrecognized_category(client, monkeypatch):
    """识别失败的衣物（category 为 null）前端需要单独一个分组，不能算进任何角色"""

    async def unknown_analyze(image_bytes: bytes, **kwargs) -> dict:
        return {"category": None, "sub_category": None, "color": None}

    monkeypatch.setattr("api.upload.analyze_clothes", unknown_analyze)

    client.post(
        "/api/upload",
        files={"file": ("a.jpg", make_png_bytes(), "image/png")},
    )

    assert client.get("/api/wardrobe").json()[0]["role"] is None


def test_wardrobe_lists_uploaded_clothes(client):
    client.post(
        "/api/upload",
        files={"file": ("a.jpg", make_png_bytes(), "image/png")},
    )
    client.post(
        "/api/upload",
        files={"file": ("b.jpg", make_png_bytes(), "image/png")},
    )

    response = client.get("/api/wardrobe")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["id"] == 2  # 倒序：最新在前


def test_wardrobe_item_detail(client):
    upload = client.post(
        "/api/upload",
        files={"file": ("a.jpg", make_png_bytes(), "image/png")},
    )
    clothes_id = upload.json()["id"]

    response = client.get(f"/api/clothes/{clothes_id}")

    assert response.status_code == 200
    assert response.json()["id"] == clothes_id


def test_wardrobe_detail_404_when_missing(client):
    response = client.get("/api/clothes/999")
    assert response.status_code == 404


# ---------- DELETE /api/clothes/{id} ----------

def upload_one(client, name="a.jpg"):
    response = client.post(
        "/api/upload", files={"file": (name, make_png_bytes(), "image/png")}
    )
    return response.json()["id"]


def test_delete_clothes_removes_row_files_and_returns_the_row(client, tmp_path):
    """传错的图必须能在 UI 里删掉；两个图片文件也要跟着走，否则只是换个地方堆垃圾"""
    clothes_id = upload_one(client)
    upload_dir = tmp_path / "uploads"
    assert len(list(upload_dir.iterdir())) == 2  # 原图 + 抠图

    response = client.delete(f"/api/clothes/{clothes_id}")

    assert response.status_code == 200
    assert response.json()["id"] == clothes_id
    assert list(upload_dir.iterdir()) == []
    assert count_rows(tmp_path / "test.db", "clothes") == 0
    assert client.get(f"/api/clothes/{clothes_id}").status_code == 404


def test_delete_clothes_404_for_unknown_id(client):
    response = client.delete("/api/clothes/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "衣物不存在"


def test_delete_clothes_leaves_other_items_alone(client, tmp_path):
    first = upload_one(client)
    upload_one(client, "b.jpg")

    client.delete(f"/api/clothes/{first}")

    assert [item["id"] for item in client.get("/api/wardrobe").json()] == [2]
    assert len(list((tmp_path / "uploads").iterdir())) == 2  # 第二件的原图 + 抠图
