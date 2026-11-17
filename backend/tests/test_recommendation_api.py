"""
穿搭推荐 API 测试（阶段三 TDD 循环 E）

外部依赖（Open-Meteo 天气、火山方舟 LLM）替换为可控实现，
被测的是 API 层的参数处理、天气错误 → HTTP 状态码的转换、与 settings 的透传。
"""
import asyncio

import aiosqlite
import httpx
import pytest

from main import app
from services.weather import CityNotFoundError, Weather
from storage.clothes_store import save_clothes
from tests.conftest import login, make_client


def make_weather(city="上海"):
    return Weather(
        city=city,
        temperature=28.8,
        apparent_temperature=30.8,
        description="晴间多云",
        temp_max=31.0,
        temp_min=23.5,
        precipitation_probability=14,
        weather_code=1,
    )


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    async def fake_chat(*args, **kwargs):
        raise ValueError("LLM disabled in API tests")

    monkeypatch.setattr("services.recommendation.call_chat_api", fake_chat)

    state = {"location": None, "exc": None, "city": "上海"}

    async def fake_get_weather(location: str):
        state["location"] = location
        if state["exc"]:
            raise state["exc"]
        return make_weather(state["city"])

    monkeypatch.setattr("api.recommendation.get_weather", fake_get_weather)

    with make_client(tmp_path) as c:
        try:
            assert login(c).status_code == 200
            yield c, state
        finally:
            app.dependency_overrides.clear()


def seed_clothes(db_path, items):
    """向测试库插入衣物（直接走存储层，不经过上传接口）"""

    async def _seed():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            for item in items:
                await save_clothes(
                    conn,
                    user_id=1,
                    image_path=f"/uploads/{item['id']}.jpg",
                    category=item["category"],
                    sub_category=item.get("sub_category"),
                    color=item.get("color"),
                    style=item.get("style"),
                    season=item.get("season"),
                )

    asyncio.run(_seed())


def seed_summer_outfit(db_path):
    seed_clothes(
        db_path,
        [
            {"id": 1, "category": "上衣", "sub_category": "T恤", "color": "蓝色",
             "style": "休闲", "season": "夏季"},
            {"id": 2, "category": "裤子", "sub_category": "牛仔裤", "color": "藏青色",
             "style": "休闲", "season": "夏季"},
            {"id": 3, "category": "鞋", "sub_category": "运动鞋", "color": "白色",
             "style": "运动", "season": "夏季"},
        ],
    )


def test_recommendation_returns_weather_reason_and_items(ctx, tmp_path):
    client, state = ctx
    seed_summer_outfit(tmp_path / "test.db")

    response = client.get("/api/recommendation")

    assert response.status_code == 200
    data = response.json()
    assert data["weather"]["city"] == "上海"
    assert data["weather"]["temperature"] == 28.8
    assert data["weather"]["description"] == "晴间多云"
    assert data["source"] in {"llm", "rule"}
    assert data["reason"]
    assert len(data["items"]) == 3
    assert all("role" in it for it in data["items"])


def test_recommendation_404_when_city_not_found(ctx):
    client, state = ctx

    state["exc"] = CityNotFoundError("没有找到城市「火星」，请换个说法试试")
    response = client.get("/api/recommendation?location=火星")

    assert response.status_code == 404
    assert "火星" in response.json()["detail"]


def test_recommendation_400_when_location_blank(ctx):
    client, state = ctx

    response = client.get("/api/recommendation", params={"location": "   "})

    assert response.status_code == 400
    assert state["location"] is None  # 天气服务根本没被调用


def test_recommendation_503_when_weather_unavailable(ctx):
    client, state = ctx

    state["exc"] = httpx.ConnectError("timeout")
    response = client.get("/api/recommendation")

    assert response.status_code == 503


def test_recommendation_forwards_location_and_occasion(ctx, tmp_path):
    client, state = ctx
    seed_summer_outfit(tmp_path / "test.db")

    response = client.get("/api/recommendation", params={"location": "杭州", "occasion": "通勤"})

    assert response.status_code == 200
    assert state["location"] == "杭州"
    assert response.json()["occasion"] == "通勤"


def test_recommendation_defaults_to_shanghai(ctx):
    client, state = ctx

    client.get("/api/recommendation")

    assert state["location"] == "上海"


def test_recommendation_empty_wardrobe_returns_gaps(ctx):
    client, state = ctx

    response = client.get("/api/recommendation")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert "衣柜还是空的" in "".join(data["gaps"])


def test_recommendation_passes_api_key_from_settings(ctx, monkeypatch):
    client, state = ctx

    captured = {}

    async def fake_build(wardrobe, weather, occasion, *, api_key, model, base_url):
        captured["api_key"] = api_key
        captured["model"] = model
        return {"items": [], "reason": "r", "source": "rule", "gaps": []}

    monkeypatch.setattr("api.recommendation.build_recommendation", fake_build)

    response = client.get("/api/recommendation")

    assert response.status_code == 200
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "test-vision-model"


def test_recommendation_normalizes_unknown_occasion(ctx, tmp_path):
    client, state = ctx
    seed_summer_outfit(tmp_path / "test.db")

    response = client.get("/api/recommendation", params={"occasion": "蹦迪"})

    assert response.status_code == 200
    assert response.json()["occasion"] == "休闲"
