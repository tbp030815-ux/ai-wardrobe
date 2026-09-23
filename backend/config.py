"""
应用配置（从 .env 读取）
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Settings:
    api_key: str
    vision_model: str
    image_model: str
    base_url: str
    upload_dir: Path


@lru_cache
def get_settings() -> Settings:
    return Settings(
        api_key=os.getenv("SEEDREAM_API_KEY", ""),
        vision_model=os.getenv("SEEDREAM_VISION_MODEL", "doubao-seed-1-6-vision-250815"),
        image_model=os.getenv("SEEDREAM_IMAGE_MODEL", "doubao-seedream-4-0-250828"),
        base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        upload_dir=BASE_DIR / "uploads",
    )
