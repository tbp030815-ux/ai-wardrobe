"""
跨用户越权访问测试（API 层）

身份只来自签名 cookie。这里用 user 2 的**合法**会话去访问 user 1 的数据，
期望一律 404 —— 用 403 等于向调用方确认「这条记录存在，只是不属于你」。
"""
import asyncio
import io

import aiosqlite
import pytest
from PIL import Image

from api.auth import SESSION_COOKIE
from main import app
from security.session import issue_token
from storage.clothes_store import save_clothes
from storage.model_store import save_model
from tests.conftest import TEST_PASSWORD_HASH, make_client


def make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), (180, 160, 140)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    calls = []

    async def fake_build_tryon(*args, **kwargs):
        calls.append(True)
        return make_jpeg_bytes()

    monkeypatch.setattr("api.tryon.build_tryon", fake_build_tryon)

    # make_client 会在 tmp_path 上建库建表，所以必须先拿到 client 再插数据
    client = make_client(tmp_path)

    async def seed():
        async with aiosqlite.connect(str(tmp_path / "test.db")) as conn:
            conn.row_factory = aiosqlite.Row
            await save_clothes(
                conn,
                user_id=1,
                image_path="/uploads/mine.jpg",
                cropped_path="/uploads/mine_cropped.png",
                category="上衣",
            )
            # id = 2：属于 user 2
            await save_clothes(
                conn, user_id=2, image_path="/uploads/theirs.jpg", category="上衣"
            )
            # id = 1：属于 user 2
            await save_model(conn, user_id=2, image_path="/uploads/theirs_model.jpg")

    try:
        asyncio.run(seed())
        with client as c:
            yield c, calls
    finally:
        app.dependency_overrides.clear()


def as_user(client, user_id: int) -> dict:
    """不登录，直接伪造请求头：避免登录 cookie 与目标用户的 cookie 同时在 jar 里"""
    token = issue_token(user_id, 30, TEST_PASSWORD_HASH)
    return {"cookie": f"{SESSION_COOKIE}={token}"}


# ---------- GET /api/clothes/{id} ----------

def test_clothes_detail_404_for_another_users_clothes(ctx):
    client, _ = ctx

    response = client.get("/api/clothes/2", headers=as_user(client, 1))

    assert response.status_code == 404
    assert response.json()["detail"] == "衣物不存在"


def test_clothes_detail_200_for_the_owner(ctx):
    """正向对照：404 不是因为整个端点坏了"""
    client, _ = ctx

    response = client.get("/api/clothes/2", headers=as_user(client, 2))

    assert response.status_code == 200
    assert response.json()["id"] == 2


# ---------- DELETE /api/clothes/{id} ----------

def test_clothes_delete_404_for_another_users_clothes(ctx):
    client, _ = ctx

    response = client.delete("/api/clothes/2", headers=as_user(client, 1))

    assert response.status_code == 404
    assert client.get("/api/clothes/2", headers=as_user(client, 2)).status_code == 200


# ---------- POST /api/tryon ----------

def test_tryon_404_for_another_users_clothes(ctx):
    client, calls = ctx

    response = client.post(
        "/api/tryon", json={"clothes_ids": [2]}, headers=as_user(client, 1)
    )

    assert response.status_code == 404
    assert "2" in response.json()["detail"]
    assert calls == []


def test_tryon_404_for_another_users_model(ctx):
    """显式传别人模特的 model_id：不能拿别人的照片去生成"""
    client, calls = ctx

    response = client.post(
        "/api/tryon",
        json={"clothes_ids": [1], "model_id": 1},
        headers=as_user(client, 1),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "模特不存在"
    assert calls == []
