"""
会话 Cookie 的签发与校验（标准库 HMAC 自签，不建 sessions 表）

格式：`v1.<user_id>.<过期时间戳>.<b64url 签名>`，签名覆盖前两段之前的那一整串。

**密钥从 `APP_PASSWORD_HASH` 派生**，于是有一个白送的性质：改密码 → 密钥变 →
所有旧 cookie 立刻失效，等于「退出所有设备」。建 sessions 表反而要另外写这个功能。

**固定过期，不做滑动续期**：滑动意味着每个请求一次写库，且 cookie 的 TTL 会和
服务端状态漂开。会话过期就是回到登录页 —— 前端把 401 当作「去登录」即可。
"""
import base64
import hashlib
import hmac
import time

VERSION = "v1"
DAY_SECONDS = 86_400
_KEY_PREFIX = b"session-key:"


def issue_token(
    user_id: int,
    ttl_days: int,
    password_hash: str,
    *,
    now: float | None = None,
) -> str:
    """签一个会话 cookie 值。

    调用方必须先确认 `password_hash` 非空 —— 空哈希签出来的串谁都能伪造。
    `/api/auth/login` 在没配密码时会先返 503，走不到这里。
    """
    expires_at = int((time.time() if now is None else now) + ttl_days * DAY_SECONDS)
    payload = f"{VERSION}.{user_id}.{expires_at}"
    return f"{payload}.{_sign(payload, password_hash)}"


def verify_token(token: str | None, password_hash: str, *, now: float | None = None) -> int | None:
    """校验 cookie，通过则返回 `user_id`，否则返回 `None`。

    cookie 是攻击者可控输入，所以任何畸形（段数不对、字段不是数字、签名不符、
    已过期、没配密码）都只变成 `None`，绝不抛异常。
    """
    if not token or not password_hash:
        return None

    try:
        version, raw_user_id, raw_expires_at, signature = token.split(".")
        if version != VERSION:
            return None
        # 先验签名再解析内容：签名不符就没必要相信里面写的任何东西
        if not hmac.compare_digest(_sign(f"{version}.{raw_user_id}.{raw_expires_at}", password_hash), signature):
            return None
        user_id = int(raw_user_id)
        expires_at = int(raw_expires_at)
    except (ValueError, TypeError):
        return None

    if user_id <= 0:
        return None
    if expires_at <= (time.time() if now is None else now):
        return None
    return user_id


def _key(password_hash: str) -> bytes:
    return hashlib.sha256(_KEY_PREFIX + password_hash.encode("utf-8")).digest()


def _sign(payload: str, password_hash: str) -> str:
    """base64url 且去掉 `=` 填充 —— cookie 值里不该出现需要转义的字符。"""
    digest = hmac.new(_key(password_hash), payload.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
