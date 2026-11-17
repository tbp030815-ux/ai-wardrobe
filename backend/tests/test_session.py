"""
会话 Cookie 的签发与校验

用标准库 HMAC 自签，不建 sessions 表：省掉一张表、一个 store、一个过期清理规则。
签名密钥从 `APP_PASSWORD_HASH` 派生，于是**改密码 = 所有旧会话自动失效** ——
这是"退出所有设备"的效果，表方案反而还得另外写。

`now` 是注入的：过期测试不该靠 sleep 或者改系统时钟。
"""
import pytest

from security.session import issue_token, verify_token

PASSWORD_HASH = "pbkdf2_sha256$1000$c2FsdA==$aGFzaA=="
OTHER_HASH = "pbkdf2_sha256$1000$b3RoZXI=$b3RoZXI="
TTL_DAYS = 30
DAY = 86_400
NOW = 1_700_000_000.0


# ---------- 正常路径 ----------

def test_issues_and_verifies_a_token():
    token = issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW)

    assert verify_token(token, PASSWORD_HASH, now=NOW) == 1


def test_token_stays_valid_right_up_to_its_expiry():
    """边界：到期前一秒还有效，到期那一刻起失效"""
    token = issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW)
    expires_at = NOW + TTL_DAYS * DAY

    assert verify_token(token, PASSWORD_HASH, now=expires_at - 1) == 1
    assert verify_token(token, PASSWORD_HASH, now=expires_at) is None
    assert verify_token(token, PASSWORD_HASH, now=expires_at + 1) is None


def test_carries_the_user_id_it_was_issued_for():
    assert verify_token(issue_token(7, TTL_DAYS, PASSWORD_HASH, now=NOW), PASSWORD_HASH, now=NOW) == 7


# ---------- 伪造与篡改 ----------

def test_rejects_a_tampered_signature():
    token = issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW)
    payload, signature = token.rsplit(".", 1)

    assert verify_token(f"{payload}.{signature[:-1]}X", PASSWORD_HASH, now=NOW) is None


def test_rejects_a_tampered_payload():
    """自己把 user_id 改成 2、签名却还是原来那个 —— 必须挡下"""
    token = issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW)
    _, _, expires_at, signature = token.split(".")

    assert verify_token(f"v1.2.{expires_at}.{signature}", PASSWORD_HASH, now=NOW) is None


def test_rejects_a_token_whose_expiry_was_pushed_out():
    """把过期时间往后改同样要重签，不然会话永不过期"""
    token = issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW)
    _, user_id, _, signature = token.split(".")

    assert verify_token(f"v1.{user_id}.{int(NOW) + 10 * 365 * DAY}.{signature}", PASSWORD_HASH, now=NOW) is None


def test_rejects_a_token_signed_with_a_different_password():
    """改密码后旧 cookie 立刻失效 —— 这正是密钥从密码哈希派生的目的"""
    token = issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW)

    assert verify_token(token, OTHER_HASH, now=NOW) is None


@pytest.mark.parametrize(
    "token",
    [
        "",
        None,
        "garbage",
        "v1.1.1700000000",                  # 少一段
        "v1.1.1700000000.sig.extra",        # 多一段
        "v2.1.1700000000.c2ln",             # 版本号不对
        "v1.abc.1700000000.c2ln",           # user_id 不是数字
        "v1.1.notanumber.c2ln",             # 过期时间不是数字
        "v1.0.1700000000.c2ln",             # user_id 为 0
        "v1.-1.1700000000.c2ln",            # user_id 为负
    ],
)
def test_returns_none_instead_of_raising_on_a_malformed_token(token):
    """cookie 是攻击者可控输入 —— 畸形值只能变成"未登录"，不能变成 500"""
    assert verify_token(token, PASSWORD_HASH, now=NOW) is None


def test_returns_none_when_no_password_is_configured():
    """没配密码时连密钥都派生不出来 —— 失败关闭"""
    assert verify_token(issue_token(1, TTL_DAYS, PASSWORD_HASH, now=NOW), "", now=NOW) is None
