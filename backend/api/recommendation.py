"""
穿搭推荐 API：天气 + 衣柜 → 今日搭配

错误边界：API 层只负责「天气错误 → HTTP 状态码」，LLM 降级由服务层内部消化。
"""
from dataclasses import asdict

import aiosqlite
import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.auth import current_user_id
from config import Settings, get_settings
from services.recommendation import DEFAULT_OCCASION, SUPPORTED_OCCASIONS, build_recommendation
from services.weather import CityNotFoundError, get_weather
from storage.clothes_store import list_clothes
from storage.database import get_db

router = APIRouter()


@router.get("/api/recommendation")
async def recommendation(
    location: str = "上海",
    occasion: str = DEFAULT_OCCASION,
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    city = location.strip()
    if not city:
        raise HTTPException(status_code=400, detail="请填写城市名")

    try:
        weather = await get_weather(city)
    except CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="天气服务暂时不可用，请稍后重试")

    wardrobe = [dict(row) for row in await list_clothes(db, user_id)]
    result = await build_recommendation(
        wardrobe,
        weather,
        occasion,
        api_key=settings.api_key,
        model=settings.vision_model,
        base_url=settings.base_url,
    )

    return {
        "weather": {**asdict(weather), "reference_temperature": weather.reference_temperature},
        "occasion": occasion if occasion in SUPPORTED_OCCASIONS else DEFAULT_OCCASION,
        "source": result["source"],
        "reason": result["reason"],
        "items": result["items"],
        "gaps": result["gaps"],
    }
