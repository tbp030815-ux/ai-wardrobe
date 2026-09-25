"""
火山方舟（Seedream / Doubao）API 客户端

负责：
- 视觉理解（衣物识别）：chat/completions 接口
- 图像生成/编辑（AI 试穿）：images/generations 接口
"""
import asyncio
import base64
import io
import json
import re

import httpx
from PIL import Image

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 2K 生成实测远超 chat 的 60s。超时算错等于「钱付了，图没有」——
# read timeout 发生在请求已被上游受理之后，所以超时后不自动重试。
IMAGE_TIMEOUT = httpx.Timeout(180.0, connect=10.0)

# 参考图总像素上限（实测契约；下限 921,600 上游并未强制，见 prepare_reference_image）
MAX_PIXELS = 16_777_216


class UpstreamError(Exception):
    """上游返回非 2xx。status_code 供 API 层区分：429 透传，其余转 503。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code

CLOTHES_PROMPT = (
    "请分析这张衣物照片，以 JSON 格式返回以下字段：\n"
    "- category: 大类（上衣/裤子/裙子/鞋/配饰）\n"
    "- sub_category: 细分品类（如 T恤/卫衣/牛仔裤）\n"
    "- color: 主色调\n"
    "- style: 风格（休闲/商务/运动/甜美等）\n"
    "- season: 适用季节（春季/夏季/秋季/冬季/四季）\n"
    "只返回 JSON，不要其他解释。"
)


def parse_semantics_json(text: str) -> dict:
    """从模型输出中提取 JSON（兼容 markdown 代码块和前后夹杂文字）"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从模型输出中提取 JSON：{text[:200]}")


def guess_mime(image_bytes: bytes) -> str:
    """根据图片内容判断 MIME 类型，无法识别时回退 PNG"""
    try:
        fmt = Image.open(io.BytesIO(image_bytes)).format
    except Exception:
        return "image/png"
    if fmt == "JPEG":
        return "image/jpeg"
    if fmt:
        return f"image/{fmt.lower()}"
    return "image/png"


def prepare_reference_image(image_bytes: bytes) -> bytes:
    """把参考图规范到 API 可接受的像素上限内。

    **只降不升**：文档写的下限 921,600 px 实测并未强制（430×458 = 196,940 px 生成成功），
    放大只会引入插值伪影，对保真度没有好处。
    超出上限时统一转 JPEG —— 参考图是照片，而 base64 的 4/3 膨胀会把超大 PNG 撑爆请求体。
    """
    with Image.open(io.BytesIO(image_bytes)) as image:
        if image.width * image.height <= MAX_PIXELS:
            return image_bytes
        scale = (MAX_PIXELS / (image.width * image.height)) ** 0.5
        size = (int(image.width * scale), int(image.height * scale))
        resized = image.convert("RGB").resize(size, Image.LANCZOS)

    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _encode_reference_images(images: list[bytes]) -> list[str]:
    """规范化 + base64 编码成 data URI。

    纯 CPU（大图解码 + 缩放要 1-2 秒），调用方必须用 `asyncio.to_thread` 挪出事件循环，
    否则会冻住单 worker 上所有并发请求。
    """
    return [
        f"data:{guess_mime(prepared)};base64,{base64.b64encode(prepared).decode()}"
        for prepared in map(prepare_reference_image, images)
    ]


async def call_vision_api(
    image_bytes: bytes,
    prompt: str,
    *,
    api_key: str,
    model: str,
    base_url: str = ARK_BASE_URL,
) -> str:
    """调用火山方舟视觉理解接口，返回模型文本输出"""
    mime = guess_mime(image_bytes)
    image_b64 = base64.b64encode(image_bytes).decode()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        raise ValueError(f"识别接口调用失败（{response.status_code}）：{response.text[:300]}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


async def analyze_clothes(
    image_bytes: bytes,
    *,
    api_key: str,
    model: str,
    base_url: str = ARK_BASE_URL,
) -> dict:
    """识别衣物语义，返回结构化字典（category/sub_category/color/style/season）"""
    text = await call_vision_api(
        image_bytes, CLOTHES_PROMPT, api_key=api_key, model=model, base_url=base_url
    )
    return parse_semantics_json(text)


CHAT_TIMEOUT = 60.0  # Seed 2.1 是思考型模型，完整推荐 prompt 实测超过 30s，与识图调用对齐


async def call_chat_api(
    prompt: str,
    *,
    api_key: str,
    model: str,
    base_url: str = ARK_BASE_URL,
) -> str:
    """调用火山方舟文本对话接口（无图片），返回模型文本输出"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }

    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        raise ValueError(f"推荐接口调用失败（{response.status_code}）：{response.text[:300]}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


async def call_image_api(
    prompt: str,
    images: list[bytes],
    *,
    api_key: str,
    model: str,
    base_url: str = ARK_BASE_URL,
    size: str = "2K",
) -> bytes:
    """调用火山方舟图像生成/编辑接口，返回结果图字节。

    `image` 字段是多态的（上游契约）：单张传 JSON 字符串，多张传数组。
    用 b64_json 而不是 URL —— 签名链接 24h 过期，落盘前失效就是这个故障模式的来源。
    """
    data_uris = await asyncio.to_thread(_encode_reference_images, images)

    payload = {
        "model": model,
        "prompt": prompt,
        "image": data_uris[0] if len(data_uris) == 1 else data_uris,
        "size": size,
        "response_format": "b64_json",
        "watermark": False,
    }

    async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        raise UpstreamError(
            response.status_code,
            f"图像生成调用失败（{response.status_code}）：{response.text[:300]}",
        )

    try:
        encoded = response.json()["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"图像生成响应缺少 b64_json：{response.text[:200]}") from exc
    return base64.b64decode(encoded)
