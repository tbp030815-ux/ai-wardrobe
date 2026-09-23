"""
Seedream（火山方舟）客户端测试（TDD 循环 3）

外部 HTTP 调用用 pytest-httpx 拦截，测试的是我们代码的请求构造与响应解析逻辑。
"""
import io
import json

import pytest
from PIL import Image

from services.seedream_client import (
    ARK_BASE_URL,
    CLOTHES_PROMPT,
    analyze_clothes,
    call_vision_api,
    guess_mime,
    parse_semantics_json,
)


def make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (0, 255, 0)).save(buf, format="JPEG")
    return buf.getvalue()


# ---------- parse_semantics_json ----------

def test_parse_plain_json():
    text = '{"category": "上衣", "sub_category": "T恤", "color": "藏青色", "style": "休闲", "season": "夏季"}'
    result = parse_semantics_json(text)
    assert result["category"] == "上衣"
    assert result["sub_category"] == "T恤"
    assert result["color"] == "藏青色"
    assert result["style"] == "休闲"
    assert result["season"] == "夏季"


def test_parse_json_in_markdown_block():
    text = '```json\n{"category": "裤子"}\n```'
    assert parse_semantics_json(text)["category"] == "裤子"


def test_parse_json_with_surrounding_text():
    text = '分析结果如下：{"category": "鞋"} 希望对你有帮助'
    assert parse_semantics_json(text)["category"] == "鞋"


def test_parse_invalid_text_raises():
    with pytest.raises(ValueError):
        parse_semantics_json("这里没有任何 JSON 内容")


# ---------- guess_mime ----------

def test_guess_mime_detects_png():
    assert guess_mime(make_png_bytes()) == "image/png"


def test_guess_mime_detects_jpeg():
    assert guess_mime(make_jpeg_bytes()) == "image/jpeg"


def test_guess_mime_falls_back_on_unknown():
    assert guess_mime(b"not an image") == "image/png"


# ---------- call_vision_api ----------

async def test_call_vision_api_sends_request_and_returns_text(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": "识别结果文本"}}]})

    text = await call_vision_api(
        make_png_bytes(), "识别这件衣服", api_key="test-key", model="doubao-vision-test"
    )

    assert text == "识别结果文本"

    request = httpx_mock.get_request()
    assert str(request.url) == f"{ARK_BASE_URL}/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"

    body = json.loads(request.content)
    assert body["model"] == "doubao-vision-test"
    image_part = [p for p in body["messages"][0]["content"] if p["type"] == "image_url"][0]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


async def test_call_vision_api_raises_on_http_error(httpx_mock):
    httpx_mock.add_response(status_code=401, json={"error": {"message": "invalid key"}})

    with pytest.raises(ValueError):
        await call_vision_api(
            make_png_bytes(), "prompt", api_key="bad-key", model="m"
        )


# ---------- analyze_clothes ----------

async def test_analyze_clothes_returns_parsed_semantics(httpx_mock):
    httpx_mock.add_response(
        json={"choices": [{"message": {"content": '{"category": "上衣", "color": "白色"}'}}]}
    )

    result = await analyze_clothes(make_png_bytes(), api_key="k", model="m")

    assert result == {"category": "上衣", "color": "白色"}


async def test_analyze_clothes_uses_clothes_prompt(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": '{"category": "上衣"}'}}]})

    await analyze_clothes(make_png_bytes(), api_key="k", model="m")

    body = json.loads(httpx_mock.get_request().content)
    text_part = [p for p in body["messages"][0]["content"] if p["type"] == "text"][0]
    assert text_part["text"] == CLOTHES_PROMPT


async def test_analyze_clothes_allows_custom_base_url(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": '{"category": "上衣"}'}}]})

    await analyze_clothes(
        make_png_bytes(), api_key="k", model="m", base_url="https://example.com/api/v3"
    )

    assert str(httpx_mock.get_request().url) == "https://example.com/api/v3/chat/completions"
