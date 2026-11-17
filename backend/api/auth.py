"""
认证 API：登录 / 退出 / 查状态

单用户登录门禁 —— 一个账号，不注册、不建 `users` 表。密码哈希在 `.env`，
会话是 HMAC 自签的 HttpOnly cookie（见 `security/session.py`）。

**为什么是 Cookie 而不是 Bearer token**：浏览器自动带 cookie，所以
`frontend/src/api/client.ts` 的 `request()` 一个字都不用改；更要紧的是
`<img src="/uploads/...">` 带不了 Authorization 头（Bearer 方案得另搞签名 URL）。

**CSRF 说明（改这里之前先读）**：`main.py` 里没有任何 CORS 中间件，
这干了实际的活 —— `DELETE` 是非简单方法，跨源必预检而 `OPTIONS` 拿不到 CORS 头，
请求根本发不出去。但 `POST /api/upload` / `POST /api/model` 是 `multipart/form-data`，
属于**简单请求**，浏览器会跨源直接发 —— **SameSite=Strict 是拦住它们的唯一一道**。
所以：① 给 `main.py` 加 `CORSMiddleware(allow_credentials=True)` 是唯一会重新打开
CSRF 的操作；② SameSite 是**站点**属性不是端口属性，Vite 代理让一切同源，
将来若把 API 换成绝对 URL，会同时废掉 cookie 与这层防护。
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from config import Settings, get_settings
from security import rate_limit
from security.password import is_usable, verify_password
from security.session import issue_token, verify_token

router = APIRouter()

# cookie 名带上应用前缀：localhost 上可能同时跑着别的 dev 应用，
# 叫 "session" 会和它们打架
SESSION_COOKIE = "wardrobe_session"

# 单用户模式下的那个用户。存储层的 user_id 都是它。
SOLE_USER_ID = 1

_NOT_CONFIGURED = (
    "登录密码未配置或格式不正确，请先在 backend 目录运行："
    "./venv/Scripts/python.exe scripts/set_password.py（改完需要重启后端）"
)


class LoginRequest(BaseModel):
    password: str


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """设置会话 cookie。

    **不要加 `domain=`** —— host-only 才能让 Vite 代理（页面在 :5173、
    转发到 :8000）两边的请求都带上它。
    """
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/api/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
):
    """登录。

    **同步 `def`，不要改成 `async def`**：pbkdf2 是几百毫秒的纯 CPU 计算，
    异步端点会把单 worker 的事件循环整个卡住 —— 而攻击者正好能靠这点打
    （每猜一次密码就让全站卡半秒）。FastAPI 会把同步端点丢进线程池。
    """
    ip = _client_ip(request)

    # 先查限流再做密码校验：锁住之后连正确的密码也不放行，
    # 否则限流对爆破毫无意义
    if rate_limit.is_locked_out(ip):
        raise HTTPException(status_code=429, detail="密码错误次数过多，请 5 分钟后再试")

    if not is_usable(settings.password_hash):
        # 失败关闭。分开报 503 而不是 401：否则 `.env` 里一个笔误会让用户
        # 一直看到「密码错误」，以为是自己记错了
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)

    if not verify_password(payload.password, settings.password_hash):
        rate_limit.record_failure(ip)
        raise HTTPException(status_code=401, detail="密码错误")

    _set_session_cookie(response, issue_token(SOLE_USER_ID, settings.session_ttl_days, settings.password_hash), settings)
    rate_limit.reset(ip)
    return {"authenticated": True}


@router.post("/api/auth/logout")
def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
):
    """退出。**刻意不要求已登录** —— cookie 过期后再调用它应该也能正常返回，
    否则前端拿 401 就清不干净状态。

    删除时必须用与设置时**完全相同**的 path / samesite / httponly，
    否则浏览器会认为删的是另一个 cookie，那个陈旧的会被一直带着发出去。
    """
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )
    return {"authenticated": False}


@router.get("/api/auth/me")
def me(request: Request, settings: Settings = Depends(get_settings)):
    """当前登录状态。

    **返 200 而不是 401**，两个原因：登录页要在用户开口之前就知道"还没设密码"，
    得先拿到 `configured`；以及每次开页面在控制台留一条红色 401 很吵。
    """
    user_id = verify_token(request.cookies.get(SESSION_COOKIE), settings.password_hash)
    return {
        "authenticated": user_id is not None,
        "configured": is_usable(settings.password_hash),
    }


async def current_user_id(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> int:
    """所有受保护端点的身份来源。

    **查询参数里的 `user_id` 已经全部删掉了** —— 留着它等于洞还开着：
    登录了的人改个数字就能碰别人的数据。身份只能来自签过名的 cookie。

    目前返回的是 `SOLE_USER_ID`（单用户模式），但存储层的每个读写都带
    `user_id` 条件，所以将来要变多用户，只需要让会话携带真实用户 id。
    """
    user_id = verify_token(request.cookies.get(SESSION_COOKIE), settings.password_hash)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user_id
