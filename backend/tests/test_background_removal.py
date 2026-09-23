"""
抠图服务测试（TDD 循环 2）

注意：这些测试真实调用 rembg（U2-Net 模型），首次运行会下载模型文件。
"""
import io

import pytest
from PIL import Image, ImageDraw

from services.background_removal import remove_background


def make_test_photo() -> bytes:
    """合成一张'人像'测试图：浅灰背景 + 深色人形"""
    img = Image.new("RGB", (300, 400), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    # 头
    draw.ellipse((120, 40, 180, 100), fill=(60, 60, 80))
    # 身体
    draw.rectangle((105, 100, 195, 320), fill=(60, 60, 80))
    # 腿
    draw.rectangle((115, 320, 145, 380), fill=(50, 50, 70))
    draw.rectangle((155, 320, 185, 380), fill=(50, 50, 70))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def test_remove_background_returns_valid_png():
    result = await remove_background(make_test_photo())
    assert result[:8] == b"\x89PNG\r\n\x1a\n"


async def test_remove_background_has_transparent_pixels():
    result = await remove_background(make_test_photo())
    img = Image.open(io.BytesIO(result))
    assert img.mode == "RGBA"
    alphas = [px[3] for px in img.getdata()]
    assert min(alphas) < 128  # 存在接近全透明的背景像素


async def test_remove_background_keeps_subject_visible():
    result = await remove_background(make_test_photo())
    img = Image.open(io.BytesIO(result))
    center_alpha = img.getpixel((150, 200))[3]  # 身体中央
    assert center_alpha > 128  # 主体保留


async def test_remove_background_rejects_invalid_bytes():
    with pytest.raises(ValueError):
        await remove_background(b"not an image")
