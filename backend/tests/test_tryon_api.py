"""
试穿 API 测试（阶段四 TDD 循环 K）

上游生成调用（`build_tryon`）替换为可控实现 —— 真实调用一次约 ¥0.2 且要 30-60s。
被测的是参数校验、原图/抠图的取用、落库、结果图落盘、以及错误分类。

这是全项目最贵的一条路径：每次请求都会真实扣费，所以「不该调上游却调了」
和「该落库却没落」都必须钉死在测试里。
"""
import asyncio
import io
import json

import aiosqlite
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from config import Settings
from main import app
from services.seedream_client import UpstreamError
from storage.clothes_store import save_clothes
from storage.database import create_tables, get_db
from storage.model_store import save_model

def make_image(width: int, height: int, color, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format=fmt)
    return buf.getvalue()


# 必须是真图：端点会读尺寸做低分辨率检查，随便一段字节会在这里就被挡掉
MODEL_PHOTO_BYTES = make_image(300, 400, (240, 230, 220))


@pytest.fixture
def ctx(tmp_path, monkeypatch):
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

    state = {
        "calls": [],
        "result": make_image(90, 120, (10, 20, 30), fmt="JPEG"),
        "error": None,
    }

    async def fake_build_tryon(model_image, garments, **kwargs):
        state["calls"].append(
            {"model_image": model_image, "garments": garments, "kwargs": kwargs}
        )
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    monkeypatch.setattr("api.tryon.build_tryon", fake_build_tryon)

    with TestClient(app) as c:
        yield c, state

    app.dependency_overrides.clear()


def seed(db_path, upload_dir, items, models=("/uploads/m1.jpg",)):
    """插入衣物 + 模特，并把对应的图写到 uploads/（原图与抠图内容不同）"""

    async def _seed():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            for item in items:
                image_bytes = make_image(400, 500, (item["id"], 0, 0))
                (upload_dir / f"g{item['id']}.jpg").write_bytes(image_bytes)
                (upload_dir / f"g{item['id']}_cropped.png").write_bytes(
                    make_image(40, 40, (0, item["id"], 0), fmt="PNG")
                )
                await save_clothes(
                    conn,
                    user_id=1,
                    image_path=f"/uploads/g{item['id']}.jpg",
                    cropped_path=f"/uploads/g{item['id']}_cropped.png",
                    category=item["category"],
                    sub_category=item.get("sub_category"),
                    color=item.get("color"),
                )
            for path in models:
                await save_model(conn, user_id=1, image_path=path)

    asyncio.run(_seed())


def seed_wardrobe(db_path, upload_dir):
    (upload_dir / "m1.jpg").write_bytes(MODEL_PHOTO_BYTES)
    seed(
        db_path,
        upload_dir,
        [
            {"id": 1, "category": "上衣", "sub_category": "T恤", "color": "蓝色"},
            {"id": 2, "category": "裤子", "sub_category": "牛仔裤", "color": "藏青色"},
        ],
    )


def post_tryon(client, **body):
    return client.post("/api/tryon", json=body)


# ---------- 参数校验（不得触达上游） ----------

def test_tryon_rejects_empty_clothes_ids(ctx):
    client, state = ctx

    response = post_tryon(client, clothes_ids=[])

    assert response.status_code == 400
    assert state["calls"] == []


def test_tryon_rejects_too_many_clothes(ctx, tmp_path):
    """每件参考图都加 token 和延迟，不设上限迟早撞上请求体限制"""
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=list(range(1, 10)))  # 9 件

    assert response.status_code == 400
    assert state["calls"] == []


def test_tryon_deduplicates_clothes_ids(ctx, tmp_path):
    """前端重复勾选不该变成两张一样的参考图"""
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    post_tryon(client, clothes_ids=[1, 1, 2])

    assert len(state["calls"][0]["garments"]) == 2


def test_tryon_404_when_clothes_missing(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=[1, 999])

    assert response.status_code == 404
    assert "999" in response.json()["detail"]
    assert state["calls"] == []


def test_tryon_400_when_no_model_uploaded(ctx, tmp_path):
    """没传 model_id 又一张模特都没有时，要有能照着做的提示"""
    client, state = ctx
    db_path = tmp_path / "test.db"
    seed(
        db_path,
        tmp_path / "uploads",
        [{"id": 1, "category": "上衣", "sub_category": "T恤"}],
        models=[],
    )

    response = post_tryon(client, clothes_ids=[1])

    assert response.status_code == 400
    assert state["calls"] == []


def test_tryon_404_when_model_id_unknown(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=[1], model_id=999)

    assert response.status_code == 404
    assert state["calls"] == []


# ---------- 正常流程 ----------

def test_tryon_returns_outfit_with_result_url(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=[1, 2])

    assert response.status_code == 200
    data = response.json()
    assert data["result_image_url"].startswith("/uploads/tryon/")
    assert data["clothes_ids"] == [1, 2]


def test_tryon_feeds_original_images_not_cropped(ctx, tmp_path):
    """CLAUDE.md 约定：抠图边缘有 halo，rembg 还可能误裁衣物部件，喂给图像编辑模型会带出脏边"""
    client, state = ctx
    upload_dir = tmp_path / "uploads"
    seed_wardrobe(tmp_path / "test.db", upload_dir)
    original = (upload_dir / "g1.jpg").read_bytes()

    post_tryon(client, clothes_ids=[1])

    assert state["calls"][0]["garments"][0]["image_bytes"] == original


def test_tryon_sends_model_photo_first(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    post_tryon(client, clothes_ids=[1])

    assert state["calls"][0]["model_image"] == MODEL_PHOTO_BYTES


def test_tryon_uses_default_model_when_omitted(ctx, tmp_path):
    client, state = ctx
    upload_dir = tmp_path / "uploads"
    first_model = make_image(300, 400, (1, 1, 1))
    second_model = make_image(300, 400, (2, 2, 2))
    (upload_dir / "m1.jpg").write_bytes(first_model)
    (upload_dir / "m2.jpg").write_bytes(second_model)
    seed(
        tmp_path / "test.db",
        upload_dir,
        [{"id": 1, "category": "上衣"}],
        models=["/uploads/m1.jpg", "/uploads/m2.jpg"],
    )

    post_tryon(client, clothes_ids=[1])

    assert state["calls"][0]["model_image"] == first_model


def test_tryon_passes_explicit_model_id(ctx, tmp_path):
    """显式指定的模特必须是它自己那张图，不能回落到默认"""
    client, state = ctx
    upload_dir = tmp_path / "uploads"
    first_model = make_image(300, 400, (1, 1, 1))
    second_model = make_image(300, 400, (2, 2, 2))
    (upload_dir / "m1.jpg").write_bytes(first_model)
    (upload_dir / "m2.jpg").write_bytes(second_model)
    seed(
        tmp_path / "test.db",
        upload_dir,
        [{"id": 1, "category": "上衣"}],
        models=["/uploads/m1.jpg", "/uploads/m2.jpg"],
    )

    post_tryon(client, clothes_ids=[1], model_id=2)

    assert state["calls"][0]["model_image"] == second_model


def test_tryon_passes_credentials_and_base_url(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    post_tryon(client, clothes_ids=[1])

    assert state["calls"][0]["kwargs"] == {
        "api_key": "test-key",
        "model": "test-image-model",
        "base_url": "https://test.example.com/api/v3",
    }


def test_tryon_reports_real_image_model_in_generated_by(ctx, tmp_path):
    """写死的 'seedream' 在换模型后会让历史记录说谎"""
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=[1])

    assert response.json()["generated_by"] == "test-image-model"


def test_tryon_saves_result_image_on_disk(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    post_tryon(client, clothes_ids=[1])

    saved = list((tmp_path / "uploads" / "tryon").iterdir())
    assert len(saved) == 1
    assert saved[0].read_bytes() == state["result"]


def test_tryon_result_url_extension_follows_content_type(ctx, tmp_path):
    """上游返回 JPEG 却存成 .png 时，StaticFiles 会照扩展名发 image/png"""
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")
    state["result"] = make_image(90, 120, (10, 20, 30), fmt="JPEG")

    response = post_tryon(client, clothes_ids=[1])

    assert response.json()["result_image_url"].endswith(".jpg")


def test_tryon_persists_outfit_in_db(ctx, tmp_path):
    """直接查库：只看 HTTP 响应的话，不落库的实现也能全绿"""
    client, state = ctx
    db_path = tmp_path / "test.db"
    seed_wardrobe(db_path, tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=[1, 2])

    async def read():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM outfits")
            return await cursor.fetchall()

    rows = asyncio.run(read())
    assert len(rows) == 1
    assert rows[0]["id"] == response.json()["id"]
    assert json.loads(rows[0]["clothes_ids"]) == [1, 2]
    assert rows[0]["generated_by"] == "test-image-model"
    assert rows[0]["model_id"] == 1


def test_tryon_500_when_image_file_missing(ctx, tmp_path):
    """库里有行、盘上没文件（清理 uploads/ 之后就会这样）要给出能照做的提示"""
    client, state = ctx
    upload_dir = tmp_path / "uploads"
    seed_wardrobe(tmp_path / "test.db", upload_dir)
    (upload_dir / "g1.jpg").unlink()

    response = post_tryon(client, clothes_ids=[1])

    assert response.status_code == 500
    assert state["calls"] == []


# ---------- 错误分类 ----------

def test_tryon_passes_through_429(ctx, tmp_path):
    """限流是可重试的，一律转 503 会让前端无法区分「稍后再试」和「彻底坏了」"""
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")
    state["error"] = UpstreamError(429, "rate limited")

    response = post_tryon(client, clothes_ids=[1])

    assert response.status_code == 429


def test_tryon_returns_503_on_other_upstream_errors(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")
    state["error"] = UpstreamError(401, "invalid key")

    response = post_tryon(client, clothes_ids=[1])

    assert response.status_code == 503


def test_tryon_503_does_not_persist_a_failed_attempt(ctx, tmp_path):
    """失败的生成没产出图，落一条空记录会污染历史列表"""
    client, state = ctx
    db_path = tmp_path / "test.db"
    seed_wardrobe(db_path, tmp_path / "uploads")
    state["error"] = UpstreamError(500, "boom")

    post_tryon(client, clothes_ids=[1])

    assert client.get("/api/outfits").json() == []


# ---------- warnings ----------

def test_tryon_warns_about_low_resolution_garment(ctx, tmp_path):
    client, state = ctx
    upload_dir = tmp_path / "uploads"
    seed_wardrobe(tmp_path / "test.db", upload_dir)
    (upload_dir / "g1.jpg").write_bytes(make_image(40, 40, (200, 0, 0)))

    response = post_tryon(client, clothes_ids=[1])

    assert response.status_code == 200
    assert any("40×40" in w for w in response.json()["warnings"])


def test_tryon_has_no_warnings_for_normal_images(ctx, tmp_path):
    """warnings 不能常驻，否则用户学会无视它"""
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    response = post_tryon(client, clothes_ids=[1])

    assert response.json()["warnings"] == []


# ---------- GET /api/outfits ----------

def test_list_outfits_returns_history_with_array_clothes_ids(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")
    post_tryon(client, clothes_ids=[1])

    response = client.get("/api/outfits")

    assert response.status_code == 200
    assert response.json()[0]["clothes_ids"] == [1]


def test_list_outfits_respects_limit(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")
    for _ in range(3):
        post_tryon(client, clothes_ids=[1])

    assert len(client.get("/api/outfits?limit=2").json()) == 2


def test_list_outfits_is_empty_before_any_generation(ctx, tmp_path):
    client, state = ctx
    seed_wardrobe(tmp_path / "test.db", tmp_path / "uploads")

    assert client.get("/api/outfits").json() == []
