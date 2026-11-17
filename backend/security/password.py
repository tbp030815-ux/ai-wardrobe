"""
登录密码的哈希与校验（标准库 pbkdf2-sha256，不引入新依赖）

单用户场景不建 `users` 表，密码哈希直接存在 `backend/.env` 的 `APP_PASSWORD_HASH` 里。
存哈希而不存明文，是为了 `.env` 被看到（贴进 issue、发给别人帮忙排查）时不泄露密码本身。

格式：`pbkdf2_sha256$<迭代数>$<b64 salt>$<b64 hash>`

**迭代数写进字符串本身**，校验时从里面读 —— 这样以后调高强度不用管老哈希，
测试也能塞一个低迭代数的哈希把登录跑快。
"""
import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16


def hash_password(plain: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """把明文密码变成可存进 `.env` 的哈希串。"""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_encode(salt)}${_encode(digest)}"


def is_usable(stored: str) -> bool:
    """`.env` 里配的哈希是否可用（存在且格式正确）。

    登录端点靠它区分两种失败：配置不可用 → 503，让用户去重设密码；
    密码不对 → 401。不分开的话，`.env` 里一个笔误会让人一直看到「密码错误」，
    以为是自己记错了密码。
    """
    return _parse(stored) is not None


def verify_password(plain: str, stored: str) -> bool:
    """校验密码。`stored` 畸形或为空一律返回 False，**不抛异常**。

    `.env` 里手抖写错一个字符，用户该看到「密码错误」或配置提示，
    而不是一个 500 traceback。空哈希也走这条路径 —— 没配密码时失败关闭。
    """
    parsed = _parse(stored)
    if parsed is None:
        return False

    iterations, salt, expected = parsed
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    # 定长比较：不因为"第几个字符开始不一样"而改变耗时
    return hmac.compare_digest(digest, expected)


def _parse(stored: str) -> tuple[int, bytes, bytes] | None:
    """解析哈希串，任何畸形都返回 None 而不是抛异常。

    `stored` 最终来自 `.env`，但校验路径上的输入是不可信的（登录请求会走到这），
    所以这里必须把"坏输入"和"密码不对"归一到同一个返回值上。
    """
    if not stored:
        return None

    try:
        algorithm, raw_iterations, raw_salt, raw_digest = stored.split("$")
        if algorithm != ALGORITHM:
            return None
        iterations = int(raw_iterations)
        salt = _decode(raw_salt)
        expected = _decode(raw_digest)
    except (ValueError, TypeError):   # b64 解码失败抛的是 binascii.Error，它是 ValueError 的子类
        return None

    # 迭代数为 0 或负数时 pbkdf2_hmac 会抛；盐/摘要为空说明哈希是残缺的
    if iterations <= 0 or not salt or not expected:
        return None

    return iterations, salt, expected


def _encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)
