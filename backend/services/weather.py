"""
Open-Meteo 天气服务（免费、无需 Key）

两段调用：
1. 地理编码：城市名 → 经纬度（中文名直接可用，language=zh 返回中文标准名）
2. 天气预报：经纬度 → 当前天气 + 今日温度区间
"""
from dataclasses import dataclass

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT = 10.0

# WMO 天气代码 → 中文描述（未知代码统一兜底）
WMO_CODE_DESCRIPTIONS: dict[int, str] = {
    0: "晴",
    1: "晴间多云",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "密毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷阵雨伴冰雹",
}


class CityNotFoundError(ValueError):
    """地理编码查不到该城市（前端应提示换一个说法）"""


@dataclass(frozen=True)
class Weather:
    city: str  # 地理编码解析出的标准城市名（回显给用户确认）
    temperature: float  # 当前气温 °C
    apparent_temperature: float  # 体感温度 °C
    description: str  # 中文天气描述
    temp_max: float
    temp_min: float
    precipitation_probability: int  # 今日最大降水概率 %
    weather_code: int

    @property
    def reference_temperature(self) -> int:
        """推荐引擎使用的基准温度：体感温度取整"""
        return round(self.apparent_temperature)


def describe_weather_code(code: int) -> str:
    return WMO_CODE_DESCRIPTIONS.get(code, "未知天气")


def _first_float(values, default: float) -> float:
    """取数组首元素；0.0°C 是合法值，不能走 `or` 兜底"""
    if isinstance(values, list) and values and values[0] is not None:
        return float(values[0])
    return default


def parse_weather(data: dict, city: str) -> Weather:
    """Open-Meteo 原始响应 → Weather（纯函数，便于单测）"""
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(current.get("weather_code") or 0)
    temperature = _first_float([current.get("temperature_2m")], 0.0)
    apparent = _first_float([current.get("apparent_temperature")], temperature)
    return Weather(
        city=city,
        temperature=temperature,
        apparent_temperature=apparent,
        description=describe_weather_code(code),
        temp_max=_first_float(daily.get("temperature_2m_max"), temperature),
        temp_min=_first_float(daily.get("temperature_2m_min"), temperature),
        precipitation_probability=int(
            _first_float(daily.get("precipitation_probability_max"), 0.0)
        ),
        weather_code=code,
    )


async def geocode_city(name: str) -> tuple[float, float, str]:
    """城市名 → (纬度, 经度, 标准城市名)；查不到抛 CityNotFoundError"""
    city = name.strip()
    if not city:
        raise ValueError("城市名不能为空")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
        )
    response.raise_for_status()

    results = response.json().get("results") or []
    if not results:
        raise CityNotFoundError(f"没有找到城市「{city}」，请换个说法试试")

    first = results[0]
    return float(first["latitude"]), float(first["longitude"]), str(first.get("name") or city)


async def fetch_forecast(latitude: float, longitude: float) -> dict:
    """经纬度 → 原始预报数据"""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,apparent_temperature,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
    response.raise_for_status()
    return response.json()


async def get_weather(location: str) -> Weather:
    """对外唯一入口：城市名 → Weather"""
    latitude, longitude, city = await geocode_city(location)
    return parse_weather(await fetch_forecast(latitude, longitude), city)
