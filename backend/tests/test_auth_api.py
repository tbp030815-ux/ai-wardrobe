"""
认证端点与身份依赖

三条约定，改之前先读：
1. `POST /api/auth/login` 是**同步** `def` —— pbkdf2 是几百毫秒的纯 CPU 活，
   写成 `async def` 会把单 worker 的事件循环整个卡住。FastAPI 会把同步端点丢进线程池
2. `GET /api/auth/me` 返 **200** 不是 401 —— 登录页要在用户开口之前就知道"还没设密码"
3. `POST /api/auth/logout` **不要求已登录** —— cookie 过期后前端还得能清状态
"""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.auth import SESSION_COOKIE, current_user_id
from main import app
from security.session import issue_token
from tests.conftest import TEST_PASSWORD, TEST_PASSWORD_HASH, login, make_client, make_settings


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unconfigured(tmp_path):
    """还没跑 set_password.py 的状态"""
    with make_client(tmp_path, password_hash="") as c:
        yield c
    app.dependency_overrides.clear()


def make_request(cookie: str | None = None) -> Request:
    """手搓一个 Request，好直接单测依赖本身，不用先接一条真实路由上去。"""
    headers = [] if cookie is None else [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())]
    return Request({"type": "http", "headers": headers, "client": ("127.0.0.1", 12345)})


def cookie_attributes(response) -> set[str]:
    """`Set-Cookie` 头里的属性集合（不含 cookie 本身）。"""
    header = response.headers["set-cookie"]
    return {part.strip().lower() for part in header.split(";")[1:]}


# ---------- 登录 ----------

def test_login_accepts_the_configured_password_and_sets_a_cookie(client):
    response = login(client)

    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies


def test_login_rejects_a_wrong_password(client):
    response = login(client, "wrong")

    assert response.status_code == 401
    assert response.json()["detail"] == "密码错误"


def test_login_cookie_is_httponly_and_strict(client):
    """HttpOnly 让 XSS 偷不走 cookie；SameSite=Strict 是**唯一**挡住跨源
    `multipart/form-data` 上传请求的东西（那是简单请求，不走 CORS 预检）。"""
    attributes = cookie_attributes(login(client))

    assert "httponly" in attributes
    assert "samesite=strict" in attributes


def test_login_cookie_is_not_secure_by_default(client):
    """`secure=True` 在 `TestClient`（base URL 是 http://testserver）下会被存下
    但**永不回传** —— 登录 200、下一跳 401，而且响应里一点线索都没有。
    HTTPS 部署时才该打开，所以默认必须是 False。"""
    assert "secure" not in cookie_attributes(login(client))


def test_login_returns_503_when_no_password_is_configured(unconfigured):
    """失败关闭：没配密码时绝不能放行，且要告诉用户下一步做什么"""
    response = login(unconfigured)

    assert response.status_code == 503
    assert "set_password" in response.json()["detail"]


def test_login_returns_503_when_the_configured_hash_is_malformed(tmp_path):
    """`.env` 里手抖写错：给配置提示，不是 500 traceback，也不是一直「密码错误」"""
    with make_client(tmp_path, password_hash="not-a-valid-hash") as c:
        response = login(c)

    assert response.status_code == 503
    assert "set_password" in response.json()["detail"]


def test_login_does_not_set_a_cookie_when_it_fails(client):
    assert SESSION_COOKIE not in login(client, "wrong").cookies


# ---------- /me ----------

def test_me_reports_not_authenticated_without_a_cookie(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 200          # 200 而不是 401：见模块 docstring
    assert response.json() == {"authenticated": False, "configured": True}


def test_me_reports_authenticated_after_login(client):
    login(client)

    assert client.get("/api/auth/me").json()["authenticated"] is True


def test_me_reports_not_configured_when_no_password_is_set(unconfigured):
    """登录页据此在用户输入之前就提示"还没设密码"，而不是让人输完才报错"""
    assert unconfigured.get("/api/auth/me").json() == {"authenticated": False, "configured": False}


def test_me_reports_not_authenticated_when_the_cookie_is_forged(client):
    client.cookies.set(SESSION_COOKIE, "v1.1.9999999999.forged")

    assert client.get("/api/auth/me").json()["authenticated"] is False


# ---------- 退出 ----------

def test_logout_clears_the_session(client):
    login(client)

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_logout_works_even_when_not_logged_in(client):
    """cookie 过期后前端还得能清状态 —— 要求已登录的话会拿到 401，状态清不干净"""
    assert client.post("/api/auth/logout").status_code == 200


def test_logout_deletes_the_cookie_with_the_same_attributes_it_was_set_with(client):
    """path/samesite/httponly 不一致的话浏览器会认为删的是另一个 cookie，
    于是那个陈旧 cookie 会被一直带着发出去"""
    login(client)

    attributes = cookie_attributes(client.post("/api/auth/logout"))

    assert "httponly" in attributes
    assert "samesite=strict" in attributes
    assert "max-age=0" in attributes


# ---------- current_user_id 依赖本身 ----------

async def test_current_user_id_returns_the_user_id_from_a_valid_cookie(tmp_path):
    settings = make_settings(tmp_path)
    token = issue_token(1, settings.session_ttl_days, TEST_PASSWORD_HASH)

    assert await current_user_id(make_request(token), settings) == 1


async def test_current_user_id_rejects_a_missing_cookie(tmp_path):
    with pytest.raises(HTTPException) as excinfo:
        await current_user_id(make_request(), make_settings(tmp_path))

    assert excinfo.value.status_code == 401


async def test_current_user_id_rejects_a_forged_cookie(tmp_path):
    with pytest.raises(HTTPException) as excinfo:
        await current_user_id(make_request("v1.1.9999999999.forged"), make_settings(tmp_path))

    assert excinfo.value.status_code == 401


async def test_current_user_id_rejects_an_expired_cookie(tmp_path):
    """过期时间已经是过去时"""
    settings = make_settings(tmp_path)
    token = issue_token(1, -1, TEST_PASSWORD_HASH)

    with pytest.raises(HTTPException) as excinfo:
        await current_user_id(make_request(token), settings)

    assert excinfo.value.status_code == 401


async def test_current_user_id_rejects_everything_when_no_password_is_configured(tmp_path):
    """没配密码 → 密钥都派生不出来 → 任何 cookie 都不认。失败关闭。"""
    settings = make_settings(tmp_path, password_hash="")
    token = issue_token(1, 30, TEST_PASSWORD_HASH)

    with pytest.raises(HTTPException) as excinfo:
        await current_user_id(make_request(token), settings)

    assert excinfo.value.status_code == 401


# ---------- 限流 ----------

def test_login_locks_out_after_repeated_failures(client):
    from security.rate_limit import MAX_FAILURES

    for _ in range(MAX_FAILURES):
        assert login(client, "wrong").status_code == 401

    response = login(client, "wrong")

    assert response.status_code == 429


def test_lockout_also_blocks_the_correct_password(client):
    """锁住之后连对的密码也不放行 —— 否则限流对爆破毫无意义"""
    from security.rate_limit import MAX_FAILURES

    for _ in range(MAX_FAILURES):
        login(client, "wrong")

    assert login(client).status_code == 429


def test_successful_logins_never_trip_the_limiter(client):
    """只记失败。记成功的话，正常用户登录几次就把自己锁死，
    更要命的是 4 个 fixture 的 67 次登录会全部变成 429。"""
    from security.rate_limit import MAX_FAILURES

    for _ in range(MAX_FAILURES * 3):
        assert login(client).status_code == 200
