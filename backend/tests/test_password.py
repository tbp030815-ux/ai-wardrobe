"""
登录密码的哈希与校验

密码哈希存在 `backend/.env` 的 `APP_PASSWORD_HASH` 里（单用户，不建 users 表）。
格式 `pbkdf2_sha256$<迭代数>$<b64 salt>$<b64 hash>` —— **迭代数随哈希走**，
所以测试可以塞一个低迭代数的哈希把登录跑快，不需要任何额外开关。
"""
import pytest

from security.password import DEFAULT_ITERATIONS, hash_password, is_usable, verify_password

# 测试专用：迭代数低到毫秒级。生产用 DEFAULT_ITERATIONS，不传就是它。
FAST = 1_000


# ---------- 正常路径 ----------

def test_verifies_a_correct_password():
    stored = hash_password("hunter2", iterations=FAST)

    assert verify_password("hunter2", stored) is True


def test_rejects_a_wrong_password():
    stored = hash_password("hunter2", iterations=FAST)

    assert verify_password("hunter3", stored) is False
    assert verify_password("", stored) is False
    assert verify_password("hunter2 ", stored) is False   # 末尾空格不该被吃掉


def test_salts_so_the_same_password_hashes_differently():
    """无盐的话两个用户同密码就同哈希，彩虹表直接命中"""
    first = hash_password("hunter2", iterations=FAST)
    second = hash_password("hunter2", iterations=FAST)

    assert first != second
    assert verify_password("hunter2", first) is True
    assert verify_password("hunter2", second) is True


def test_hash_carries_its_own_iteration_count():
    """迭代数写在哈希里，校验时才不用靠外部配置去猜"""
    stored = hash_password("hunter2", iterations=FAST)

    assert stored.startswith(f"pbkdf2_sha256${FAST}$")
    assert hash_password("hunter2").startswith(f"pbkdf2_sha256${DEFAULT_ITERATIONS}$")


def test_verifies_a_hash_made_with_a_different_iteration_count():
    """换迭代数（提高强度）后，老哈希必须继续能验 —— 否则改参数等于把所有人踢出去"""
    assert verify_password("hunter2", hash_password("hunter2", iterations=FAST)) is True
    assert verify_password("hunter2", hash_password("hunter2", iterations=FAST * 2)) is True


def test_handles_non_ascii_passwords():
    stored = hash_password("密码🔒", iterations=FAST)

    assert verify_password("密码🔒", stored) is True
    assert verify_password("密码", stored) is False


# ---------- 畸形输入：.env 里写错一个字符不该变成 500 ----------

@pytest.mark.parametrize(
    "stored",
    [
        "",
        "garbage",
        "pbkdf2_sha256$1000$onlythree",            # 段数不对
        "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA==",  # 迭代数不是数字
        "md5$1000$c2FsdA==$aGFzaA==",              # 算法名不对
        "pbkdf2_sha256$0$c2FsdA==$aGFzaA==",       # 迭代数为 0
        "pbkdf2_sha256$-1$c2FsdA==$aGFzaA==",      # 负数
        "pbkdf2_sha256$1000$$",                    # 盐和摘要都空
        "pbkdf2_sha256$1000$c2FsdA==",             # 少一段
        "$1000$c2FsdA==$aGFzaA==",                 # 算法名为空
    ],
)
def test_returns_false_instead_of_raising_on_a_malformed_hash(stored):
    """`.env` 手抖写错，用户该看到"密码错误"或启动提示，不是一个 traceback"""
    assert verify_password("hunter2", stored) is False


def test_returns_false_when_no_password_is_configured():
    """`.env` 还没设密码（或设成空串）—— 失败关闭，绝不能反而放行"""
    assert verify_password("hunter2", "") is False
    assert verify_password("", "") is False


# ---------- is_usable：把"密码错了"和"配置根本不可用"分开 ----------

def test_reports_a_well_formed_hash_as_usable():
    assert is_usable(hash_password("hunter2", iterations=FAST)) is True


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "garbage",
        "pbkdf2_sha256$1000$onlythree",
        "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA==",
        "md5$1000$c2FsdA==$aGFzaA==",
        "pbkdf2_sha256$0$c2FsdA==$aGFzaA==",
        "pbkdf2_sha256$1000$$",
    ],
)
def test_reports_a_malformed_hash_as_unusable(stored):
    """登录端点靠这个区分：不可用 → 503 让用户去重设密码，
    而不是一直回 401「密码错误」让人以为是自己记错了。"""
    assert is_usable(stored) is False
