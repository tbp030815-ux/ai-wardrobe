"""
跨测试文件共用的 helper 与 fixture

放这里的理由：`Settings` 每加一个字段，4 个 API 测试 fixture 就要各改一遍。
集中成 `make_settings` / `make_client` 之后，改动只有一处。
"""
import asyncio

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from main import app
from security import rate_limit
from security.password import hash_password
from storage.database import create_tables, get_db

TEST_PASSWORD = "correct horse battery staple"

# 迭代数写在哈希串本身里（见 security/password.py），所以这里用 1000 次，
# 每个测试登录一次只花几毫秒 —— 不需要 monkeypatch 任何东西，
# 也不需要一个"测试专用"的开关去改生产代码。
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD, iterations=1_000)


def make_settings(upload_dir, **overrides) -> Settings:
    """测试用 Settings。默认就是"已配好密码"的状态。"""
    values = {
        "api_key": "test-key",
        "vision_model": "test-vision-model",
        "image_model": "test-image-model",
        "base_url": "https://test.example.com/api/v3",
        "upload_dir": upload_dir,
        "password_hash": TEST_PASSWORD_HASH,
    }
    values.update(overrides)
    return Settings(**values)


def make_client(tmp_path, **settings_overrides) -> TestClient:
    """跑在 `tmp_path` 上的 TestClient（DB 与上传目录都在临时目录里）。

    返回的对象**还没进 `with`** —— 调用方自己决定怎么用它（fixture 里 `with` 一下，
    lifespan 才会跑）。
    """
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)

    async def setup_db():
        async with aiosqlite.connect(str(db_path)) as conn:
            await create_tables(conn)

    asyncio.run(setup_db())

    async def override_db():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    settings = make_settings(upload_dir, **settings_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def login(client, password=TEST_PASSWORD):
    """走**真实**的登录端点拿 cookie。

    **不要**改成 `app.dependency_overrides` 掉认证依赖 —— 那会让 67 个 API 测试
    全部不再检验认证，认证写坏了也照样绿。测试的价值就在这里。
    """
    return client.post("/api/auth/login", json={"password": password})


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """限流器是模块级全局状态，会跨测试泄漏。

    pytest 按文件名排序，`test_auth_api.py` 排在最前 —— 不重置的话，
    那个文件里的 429 测试会污染窗口，导致后面 4 个 fixture 的 67 次登录
    全部返回 429 而不是 401，看起来像认证依赖写坏了。
    """
    rate_limit.reset()
    yield
    rate_limit.reset()
