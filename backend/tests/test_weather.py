"""
天气服务（Open-Meteo）测试（阶段三 TDD 循环 A）

外部 HTTP 调用用 pytest-httpx 拦截（默认按注册顺序消费响应），
测试的是请求构造、响应解析与错误处理。
"""
import httpx
import pytest

from services.weather import (
    GEOCODING_URL,
    CityNotFoundError,
    describe_weather_code,
    geocode_city,
    get_weather,
    parse_weather,
)


# ---------- describe_weather_code ----------

@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "晴"),
        (1, "晴间多云"),
        (3, "阴"),
        (45, "雾"),
        (61, "小雨"),
        (75, "大雪"),
        (95, "雷阵雨"),
        (99, "强雷阵雨伴冰雹"),
    ],
)
def test_describe_weather_code_known_codes(code, expected):
    assert describe_weather_code(code) == expected


def test_describe_weather_code_unknown_falls_back():
    assert describe_weather_code(1234) == "未知天气"


# ---------- parse_weather ----------

def test_parse_weather_maps_open_meteo_payload():
    data = {
        "current": {
            "time": "2026-09-24T09:45",
            "temperature_2m": 28.8,
            "apparent_temperature": 30.8,
            "weather_code": 1,
        },
        "daily": {
            "temperature_2m_max": [31.0],
            "temperature_2m_min": [23.5],
            "precipitation_probability_max": [14],
        },
    }

    weather = parse_weather(data, "上海")

    assert weather.city == "上海"
    assert weather.temperature == 28.8
    assert weather.apparent_temperature == 30.8
    assert weather.description == "晴间多云"
    assert weather.temp_max == 31.0
    assert weather.temp_min == 23.5
    assert weather.precipitation_probability == 14
    assert weather.weather_code == 1
    assert weather.reference_temperature == 31  # round(30.8)


def test_parse_weather_keeps_zero_temperature():
    """0.0°C 是合法温度但是 falsy，兜底不能用 `or default`"""
    data = {
        "current": {"temperature_2m": 0.0, "weather_code": 0},
        "daily": {},
    }

    weather = parse_weather(data, "北京")

    assert weather.temperature == 0.0
    assert weather.apparent_temperature == 0.0  # 体感缺失回退到气温


# ---------- geocode_city ----------

async def test_geocode_city_returns_coordinates_and_standard_name(httpx_mock):
    httpx_mock.add_response(
        json={"results": [{"name": "上海", "latitude": 31.22222, "longitude": 121.45806}]}
    )

    latitude, longitude, city = await geocode_city("上海")

    assert latitude == 31.22222
    assert longitude == 121.45806
    assert city == "上海"


async def test_geocode_city_sends_expected_params(httpx_mock):
    httpx_mock.add_response(
        json={"results": [{"name": "上海", "latitude": 31.2, "longitude": 121.5}]}
    )

    await geocode_city("上海")

    request = httpx_mock.get_request()
    assert str(request.url).startswith(GEOCODING_URL)
    assert request.url.params["name"] == "上海"
    assert request.url.params["count"] == "1"
    assert request.url.params["language"] == "zh"


async def test_geocode_city_raises_city_not_found(httpx_mock):
    # 实测：查不到城市时响应体只有 generationtime_ms，没有 results 键
    httpx_mock.add_response(json={"generationtime_ms": 0.05})

    with pytest.raises(CityNotFoundError):
        await geocode_city("不存在的城市")


async def test_geocode_city_rejects_blank_name(httpx_mock):
    with pytest.raises(ValueError):
        await geocode_city("   ")

    assert httpx_mock.get_requests() == []  # 根本没发请求


# ---------- get_weather ----------

async def test_get_weather_uses_geocoded_coordinates(httpx_mock):
    """第二个请求（预报）的坐标必须来自第一个请求（地理编码）的结果"""
    httpx_mock.add_response(
        json={"results": [{"name": "上海", "latitude": 31.22222, "longitude": 121.45806}]}
    )
    httpx_mock.add_response(
        json={
            "current": {
                "temperature_2m": 28.8,
                "apparent_temperature": 30.8,
                "weather_code": 1,
            },
            "daily": {
                "temperature_2m_max": [31.0],
                "temperature_2m_min": [23.5],
                "precipitation_probability_max": [14],
            },
        }
    )

    weather = await get_weather("上海")

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    forecast = requests[1]
    assert forecast.url.params["latitude"] == "31.22222"
    assert forecast.url.params["longitude"] == "121.45806"
    assert weather.city == "上海"
    assert weather.temperature == 28.8


async def test_get_weather_raises_on_http_error(httpx_mock):
    httpx_mock.add_response(
        json={"results": [{"name": "上海", "latitude": 31.2, "longitude": 121.5}]}
    )
    httpx_mock.add_response(status_code=500)

    with pytest.raises(httpx.HTTPError):
        await get_weather("上海")
