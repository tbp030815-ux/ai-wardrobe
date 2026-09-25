"""
Seedream（火山方舟）客户端测试（TDD 循环 3）

外部 HTTP 调用用 pytest-httpx 拦截，测试的是我们代码的请求构造与响应解析逻辑。
"""
import base64
import io
import json
import threading

import pytest
from PIL import Image

from services import seedream_client
from services.seedream_client import (
    ARK_BASE_URL,
    CLOTHES_PROMPT,
    IMAGE_TIMEOUT,
    MAX_PIXELS,
    UpstreamError,
    analyze_clothes,
    call_chat_api,
    call_image_api,
    call_vision_api,
    guess_mime,
    parse_semantics_json,
    prepare_reference_image,
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


# ---------- call_chat_api（阶段三：推荐用的纯文本对话） ----------

async def test_call_chat_api_sends_text_only_content(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": "推荐结果"}}]})

    text = await call_chat_api(
        "请推荐一套穿搭", api_key="test-key", model="doubao-chat-test"
    )

    assert text == "推荐结果"

    request = httpx_mock.get_request()
    assert str(request.url) == f"{ARK_BASE_URL}/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"

    body = json.loads(request.content)
    assert body["model"] == "doubao-chat-test"
    content = body["messages"][0]["content"]
    assert content == [{"type": "text", "text": "请推荐一套穿搭"}]
    # 纯文本对话不应带任何 image_url
    assert not any(p.get("type") == "image_url" for p in content)


async def test_call_chat_api_raises_on_http_error(httpx_mock):
    httpx_mock.add_response(status_code=401, json={"error": {"message": "invalid key"}})

    with pytest.raises(ValueError):
        await call_chat_api("prompt", api_key="bad-key", model="m")


# ---------- prepare_reference_image（阶段四：把参考图规范到 API 契约内） ----------

def make_image_bytes(width: int, height: int, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 120, 120)).save(buf, format=fmt)
    return buf.getvalue()


def test_image_timeout_is_generous_enough_for_2k_generation():
    """契约常量：2K 生成实测远超 60s，超时算错会导致「付了钱但拿不到图」"""
    assert IMAGE_TIMEOUT.read >= 180.0


def test_prepare_returns_in_range_image_untouched():
    """区间内原样返回 —— 不重编码，不损失画质，不改格式"""
    data = make_image_bytes(1000, 1000)  # 1,000,000 px

    assert prepare_reference_image(data) == data


def test_prepare_accepts_image_below_minimum_without_upscaling():
    """实测上游并未强制 921,600 最小像素，放大只引入插值伪影（循环 F0 结论）"""
    data = make_image_bytes(10, 10)

    result = prepare_reference_image(data)

    assert Image.open(io.BytesIO(result)).size == (10, 10)


def test_prepare_downscales_oversized_image_below_upper_bound():
    data = make_image_bytes(5000, 3500)  # 17,500,000 px > MAX_PIXELS

    image = Image.open(io.BytesIO(prepare_reference_image(data)))

    assert image.width * image.height <= MAX_PIXELS


def test_prepare_preserves_aspect_ratio_when_downscaling():
    data = make_image_bytes(5000, 3500)

    image = Image.open(io.BytesIO(prepare_reference_image(data)))

    assert image.width / image.height == pytest.approx(5000 / 3500, rel=1e-2)


# ---------- call_image_api（阶段四：图像生成/编辑） ----------

def make_b64_response(image_bytes: bytes) -> dict:
    return {"data": [{"b64_json": base64.b64encode(image_bytes).decode()}]}


async def test_call_image_api_sends_single_reference_as_string(httpx_mock):
    """只有一张参考图时 image 必须是字符串，不是单元素数组"""
    httpx_mock.add_response(json=make_b64_response(make_jpeg_bytes()))

    await call_image_api(
        "试穿", [make_png_bytes()], api_key="k", model="doubao-image-test"
    )

    body = json.loads(httpx_mock.get_request().content)
    assert isinstance(body["image"], str)
    assert body["image"].startswith("data:image/png;base64,")
    assert body["model"] == "doubao-image-test"


async def test_call_image_api_sends_multiple_references_as_array(httpx_mock):
    httpx_mock.add_response(json=make_b64_response(make_jpeg_bytes()))

    await call_image_api(
        "试穿", [make_png_bytes(), make_jpeg_bytes()], api_key="k", model="m"
    )

    body = json.loads(httpx_mock.get_request().content)
    assert isinstance(body["image"], list)
    assert len(body["image"]) == 2
    assert body["image"][0].startswith("data:image/png;base64,")
    assert body["image"][1].startswith("data:image/jpeg;base64,")


async def test_call_image_api_requests_b64_json_without_watermark(httpx_mock):
    """b64_json 避免签名 URL 24h 过期；watermark 显式关闭，行为不受账号策略变化影响"""
    httpx_mock.add_response(json=make_b64_response(make_jpeg_bytes()))

    await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m", size="2K")

    body = json.loads(httpx_mock.get_request().content)
    assert body["response_format"] == "b64_json"
    assert body["watermark"] is False
    assert body["size"] == "2K"


async def test_call_image_api_posts_to_generations_endpoint(httpx_mock):
    httpx_mock.add_response(json=make_b64_response(make_jpeg_bytes()))

    await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m")

    request = httpx_mock.get_request()
    assert str(request.url) == f"{ARK_BASE_URL}/images/generations"
    assert request.headers["Authorization"] == "Bearer k"


async def test_call_image_api_returns_decoded_image_bytes(httpx_mock):
    expected = make_jpeg_bytes()
    httpx_mock.add_response(json=make_b64_response(expected))

    result = await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m")

    assert result == expected


async def test_call_image_api_normalizes_oversized_reference(httpx_mock):
    """规范化由客户端内部完成，调用方不需要记得先处理"""
    httpx_mock.add_response(json=make_b64_response(make_jpeg_bytes()))

    await call_image_api(
        "试穿", [make_image_bytes(5000, 3500)], api_key="k", model="m"
    )

    sent = json.loads(httpx_mock.get_request().content)["image"]
    image = Image.open(io.BytesIO(base64.b64decode(sent.split(",", 1)[1])))
    assert image.width * image.height <= MAX_PIXELS


async def test_call_image_api_normalizes_off_the_event_loop(httpx_mock, monkeypatch):
    """规范化是纯 CPU：4800 万像素手机照解码 + LANCZOS 缩放要 1-2 秒，
    同步跑会冻住单 worker 上所有并发请求"""
    httpx_mock.add_response(json=make_b64_response(make_jpeg_bytes()))

    loop_thread = threading.current_thread()
    seen: list[threading.Thread] = []
    real = seedream_client.prepare_reference_image

    def record(image_bytes):
        seen.append(threading.current_thread())
        return real(image_bytes)

    monkeypatch.setattr("services.seedream_client.prepare_reference_image", record)

    await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m")

    assert seen and all(thread is not loop_thread for thread in seen)


async def test_call_image_api_raises_value_error_without_b64_payload(httpx_mock):
    httpx_mock.add_response(json={"data": [{"url": "https://example.com/x.jpg"}]})

    with pytest.raises(ValueError):
        await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m")


async def test_call_image_api_carries_upstream_status_code(httpx_mock):
    """状态码必须能被上层读到：429 要透传给前端提示可重试，其余转 503"""
    httpx_mock.add_response(status_code=429, json={"error": {"message": "rate limited"}})

    with pytest.raises(UpstreamError) as excinfo:
        await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m")

    assert excinfo.value.status_code == 429


async def test_call_image_api_raises_upstream_error_on_auth_failure(httpx_mock):
    httpx_mock.add_response(status_code=401, json={"error": {"message": "invalid key"}})

    with pytest.raises(UpstreamError) as excinfo:
        await call_image_api("试穿", [make_png_bytes()], api_key="k", model="m")

    assert excinfo.value.status_code == 401
