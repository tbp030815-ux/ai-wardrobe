"""
AI 试穿 API：一次请求生成一张效果图

批量对比（同角色多件）刻意不做成批量端点 —— 逻辑放前端串行调用。
理由：单张生成就要 30-60s，一个请求里串 4 张会撞上网关超时，而且用户无法中途放弃。
"""
import io
import uuid
from pathlib import Path

import aiosqlite
import httpx
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from api.auth import current_user_id
from config import Settings, get_settings
from services.seedream_client import UpstreamError, guess_mime
from services.tryon import build_tryon, is_low_resolution
from storage.clothes_store import get_clothes
from storage.database import get_db
from storage.model_store import get_default_model, get_model
from storage.outfits_store import (
    DEFAULT_LIST_LIMIT,
    delete_outfit,
    get_outfit,
    list_outfits,
    row_to_outfit,
    save_outfit,
)
from storage.uploads_store import delete_upload_files, resolve_upload_path

router = APIRouter()

# 每件参考图都要额外 token 和延迟。上游上限是 13 件（含模特照），这里留出余量
MAX_GARMENTS = 8

_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class TryOnRequest(BaseModel):
    clothes_ids: list[int]
    model_id: int | None = None


def _upload_file(upload_dir: Path, image_path: str) -> Path:
    """`/uploads/xxx.jpg` → `<upload_dir>/xxx.jpg`。

    走 `resolve_upload_path` 而不是 `Path(image_path).name`：后者会把
    `uploads/tryon/` 下的结果图错解到 uploads 根目录（子目录是真实存在的层级）。
    """
    path = resolve_upload_path(upload_dir, image_path)
    if path is None:
        raise HTTPException(status_code=500, detail="图片路径不合法，请重新上传")
    return path


def _read_image(path: Path, label: str) -> tuple[bytes, tuple[int, int]]:
    """读参考图字节 + 尺寸。尺寸用于判断这张图是否小到没法用"""
    try:
        data = path.read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            size = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise HTTPException(
            status_code=500, detail=f"{label}的图片文件缺失或已损坏，请重新上传"
        ) from exc
    return data, size


def _result_extension(result: bytes) -> str:
    """扩展名取自**内容**：上游返回 JPEG 却存成 .png 时，响应会照扩展名发 Content-Type"""
    return _EXTENSIONS.get(guess_mime(result), ".jpg")


@router.post("/api/tryon")
async def generate_tryon(
    payload: TryOnRequest,
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    clothes_ids = list(dict.fromkeys(payload.clothes_ids))  # 去重保序
    if not clothes_ids:
        raise HTTPException(status_code=400, detail="至少要选一件衣物")
    if len(clothes_ids) > MAX_GARMENTS:
        raise HTTPException(
            status_code=400, detail=f"一次最多试穿 {MAX_GARMENTS} 件衣物"
        )

    if not settings.api_key:
        raise HTTPException(
            status_code=503, detail="未配置 SEEDREAM_API_KEY，无法生成试穿图"
        )

    # 调上游要 30-60s，所有读操作都在它之前做完，中间不持有写事务
    garments, missing = [], []
    for clothes_id in clothes_ids:
        row = await get_clothes(db, clothes_id, user_id=user_id)
        (garments if row is not None else missing).append(row or clothes_id)
    if missing:
        raise HTTPException(status_code=404, detail=f"衣物不存在：{missing}")

    if payload.model_id is None:
        model_row = await get_default_model(db, user_id)
        if model_row is None:
            raise HTTPException(status_code=400, detail="请先上传一张模特全身照")
    else:
        model_row = await get_model(db, payload.model_id, user_id=user_id)
        if model_row is None:
            raise HTTPException(status_code=404, detail="模特不存在")

    model_image, model_size = _read_image(
        _upload_file(settings.upload_dir, model_row["image_path"]), "模特照"
    )

    warnings = []
    if is_low_resolution(model_size):
        warnings.append(
            f"模特照分辨率过低（{model_size[0]}×{model_size[1]}），试穿保真度可能较差"
        )

    # 喂 **image_path 原图**：抠图边缘有 halo，rembg 还可能误裁衣物部件（见 CLAUDE.md）
    tryon_garments = []
    for row in garments:
        image_bytes, size = _read_image(
            _upload_file(settings.upload_dir, row["image_path"]), f"衣物 {row['id']}"
        )
        if is_low_resolution(size):
            warnings.append(
                f"衣物 {row['id']} 的参考图分辨率过低（{size[0]}×{size[1]}），试穿保真度可能较差"
            )
        tryon_garments.append({**dict(row), "image_bytes": image_bytes})

    try:
        result = await build_tryon(
            model_image,
            tryon_garments,
            api_key=settings.api_key,
            model=settings.image_model,
            base_url=settings.base_url,
        )
    except UpstreamError as exc:
        # 限流是可重试的，一律转 503 会让前端分不清「稍后再试」和「彻底坏了」
        if exc.status_code == 429:
            raise HTTPException(
                status_code=429, detail="生成请求过于频繁，请稍后重试"
            ) from exc
        raise HTTPException(
            status_code=503, detail=f"图像生成服务不可用：{exc}"
        ) from exc
    except httpx.HTTPError as exc:
        # read timeout 发生在请求已被上游受理之后：这张图可能已计费但拿不到
        raise HTTPException(
            status_code=503, detail="图像生成超时，请稍后重试（本次可能已产生费用）"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail=f"图像生成返回异常：{exc}"
        ) from exc

    name = f"{uuid.uuid4().hex}{_result_extension(result)}"
    result_dir = settings.upload_dir / "tryon"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / name).write_bytes(result)

    outfit_id = await save_outfit(
        db,
        user_id=user_id,
        model_id=model_row["id"],
        clothes_ids=clothes_ids,
        generated_by=settings.image_model,
        result_image_url=f"/uploads/tryon/{name}",
    )
    # warnings 只出参、不落库：它描述的是这次输入的质量，不是这张图的性质
    return {
        **row_to_outfit(await get_outfit(db, outfit_id, user_id=user_id)),
        "warnings": warnings,
    }


@router.get("/api/outfits")
async def outfits_list(
    user_id: int = Depends(current_user_id),
    limit: int = DEFAULT_LIST_LIMIT,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await list_outfits(db, user_id, limit)
    return [row_to_outfit(row) for row in rows]


@router.delete("/api/outfits/{outfit_id}")
async def outfit_delete(
    outfit_id: int,
    user_id: int = Depends(current_user_id),
    db: aiosqlite.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """删除一次试穿记录并删掉结果图 —— 结果图是按 MB 计的，这条路径才是累积的解药"""
    row = await delete_outfit(db, user_id, outfit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="试穿记录不存在")

    delete_upload_files(settings.upload_dir, [row["result_image_url"]])
    return row_to_outfit(row)
