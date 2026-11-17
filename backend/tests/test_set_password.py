"""
`scripts/set_password.py` 的测试

**绝不碰真实的 backend/.env**：所有路径都在 tmp_path 下。
哈希统一换成 1000 轮，避免每个用例多花几百毫秒。
"""
import pytest

from scripts import set_password
from security.password import hash_password, verify_password


def fast_hash(password: str) -> str:
    return hash_password(password, iterations=1_000)


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    monkeypatch.setattr(set_password, "hash_password", fast_hash)


def stored_hash(content: str) -> str:
    values = dict(
        line.split("=", 1) for line in content.splitlines() if "=" in line
    )
    return values["APP_PASSWORD_HASH"]


def test_write_password_file_stores_a_hash_not_the_plaintext(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SEEDREAM_API_KEY=abc\n", encoding="utf-8")

    set_password.write_password_file(env, "s3cret")

    content = env.read_text(encoding="utf-8")
    assert "s3cret" not in content
    stored = stored_hash(content)
    assert verify_password("s3cret", stored)
    assert verify_password("wrong", stored) is False


def test_write_password_file_keeps_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# 注释\nSEEDREAM_API_KEY=abc\n", encoding="utf-8")

    set_password.write_password_file(env, "s3cret")

    content = env.read_text(encoding="utf-8")
    assert "# 注释" in content
    assert "SEEDREAM_API_KEY=abc" in content


def test_write_password_file_creates_a_missing_file(tmp_path):
    env = tmp_path / ".env"

    set_password.write_password_file(env, "s3cret")

    assert verify_password("s3cret", stored_hash(env.read_text(encoding="utf-8")))


def test_write_password_file_preserves_crlf(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"A=1\r\nAPP_PASSWORD_HASH=old\r\n")

    set_password.write_password_file(env, "s3cret")

    raw = env.read_bytes()
    assert b"A=1\r\n" in raw
    # 没有混入 Only-LF 的行：Windows 上整份文件不该被改写
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_main_rejects_empty_password(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    monkeypatch.setattr(set_password, "ENV_PATH", env)
    monkeypatch.setattr(set_password.getpass, "getpass", lambda prompt="": "")

    assert set_password.main() == 1
    assert not env.exists()
    assert "不能为空" in capsys.readouterr().out


def test_main_does_not_write_when_passwords_differ(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    answers = iter(["one", "two"])
    monkeypatch.setattr(set_password, "ENV_PATH", env)
    monkeypatch.setattr(set_password.getpass, "getpass", lambda prompt="": next(answers))

    assert set_password.main() == 1
    assert not env.exists()
    assert "不一致" in capsys.readouterr().out


def test_main_writes_hash_and_prints_restart_hint(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    answers = iter(["new-password", "new-password"])
    monkeypatch.setattr(set_password, "ENV_PATH", env)
    monkeypatch.setattr(set_password.getpass, "getpass", lambda prompt="": next(answers))

    assert set_password.main() == 0

    content = env.read_text(encoding="utf-8")
    assert "A=1" in content
    assert verify_password("new-password", stored_hash(content))
    out = capsys.readouterr().out
    assert "重启" in out
    assert "旧会话" in out


def test_main_replaces_the_previous_hash(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("APP_PASSWORD_HASH=old\n", encoding="utf-8")
    answers = iter(["new-password", "new-password"])
    monkeypatch.setattr(set_password, "ENV_PATH", env)
    monkeypatch.setattr(set_password.getpass, "getpass", lambda prompt="": next(answers))

    set_password.main()

    content = env.read_text(encoding="utf-8")
    assert "APP_PASSWORD_HASH=old" not in content
    assert verify_password("new-password", stored_hash(content))
