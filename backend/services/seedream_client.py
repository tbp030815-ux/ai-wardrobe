"""
火山方舟（Seedream / Doubao）API 客户端

负责：
- 视觉理解（衣物识别）：chat/completions 接口
- 后续的图像编辑（试穿/换装）：images/generations 接口
"""
import base64
import io
import json
import re

import httpx
from PIL import Image

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

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
