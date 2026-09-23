"""
rembg 背景移除服务（本地 U2-Net 推理）
"""
import asyncio
import io

from PIL import Image, UnidentifiedImageError


def _remove_background_sync(image_bytes: bytes) -> bytes:
    """同步抠图：输入图片字节，返回透明底 PNG 字节"""
    from rembg import remove  # 延迟导入：模型加载耗时，也避免未安装时拖垮整个应用

    try:
        input_img = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        raise ValueError("无法识别的图片格式") from exc

    output = remove(input_img)

    buf = io.BytesIO()
    output.save(buf, format="PNG")
    return buf.getvalue()


async def remove_background(image_bytes: bytes) -> bytes:
    """移除图片背景，返回透明底 PNG 字节（在线程中执行，不阻塞事件循环）"""
    return await asyncio.to_thread(_remove_background_sync, image_bytes)
