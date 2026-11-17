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
    # 以下三项都带默认值 —— frozen dataclass 里带默认值的字段必须排在最后，
    # 且现有调用方一律按关键字构造，所以加它们不破坏任何既有代码。
    password_hash: str = ""
    """登录密码的 pbkdf2 哈希，由 `scripts/set_password.py` 写进 `.env`。
    空或格式不对时**失败关闭**：所有受保护端点 401，登录端点 503。"""
    cookie_secure: bool = False
    """只在 HTTPS 部署时打开。`secure=True` 而实际走 HTTP 时，浏览器会收下
    cookie 但永不回传 —— 表现为"登录成功但立刻又未登录"，且毫无报错线索。"""
    session_ttl_days: int = 30


@lru_cache
def get_settings() -> Settings:
    # 注意 @lru_cache：改了 .env 必须**重启后端**才生效。set_password.py 会提示这一点，
    # 否则用户会以为"设了密码但登录还是 503、功能坏了"。
    return Settings(
        api_key=os.getenv("SEEDREAM_API_KEY", ""),
        vision_model=os.getenv("SEEDREAM_VISION_MODEL", "doubao-seed-1-6-vision-250815"),
        image_model=os.getenv("SEEDREAM_IMAGE_MODEL", "doubao-seedream-4-0-250828"),
        base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        upload_dir=BASE_DIR / "uploads",
        password_hash=os.getenv("APP_PASSWORD_HASH", ""),
        cookie_secure=os.getenv("APP_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes", "on"),
    )
