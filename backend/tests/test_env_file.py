"""
`upsert_env_line` 的测试：只改目标键，其余字节原样保留
"""
import io

from dotenv import dotenv_values

from security.env_file import upsert_env_line


def test_replaces_existing_line():
    content = "A=1\nAPP_PASSWORD_HASH=old\nB=2\n"

    assert upsert_env_line(content, "APP_PASSWORD_HASH", "new") == (
        "A=1\nAPP_PASSWORD_HASH=new\nB=2\n"
    )


def test_appends_missing_line():
    assert upsert_env_line("A=1\n", "APP_PASSWORD_HASH", "new") == (
        "A=1\nAPP_PASSWORD_HASH=new\n"
    )


def test_appends_to_empty_file():
    assert upsert_env_line("", "APP_PASSWORD_HASH", "new") == (
        "APP_PASSWORD_HASH=new\n"
    )


def test_adds_newline_when_file_has_no_trailing_newline():
    """否则追加的键会粘在最后一行末尾，变成 `A=1APP_PASSWORD_HASH=new`"""
    assert upsert_env_line("A=1", "APP_PASSWORD_HASH", "new") == (
        "A=1\nAPP_PASSWORD_HASH=new\n"
    )


def test_preserves_crlf():
    content = "A=1\r\nAPP_PASSWORD_HASH=old\r\n"

    assert upsert_env_line(content, "APP_PASSWORD_HASH", "new") == (
        "A=1\r\nAPP_PASSWORD_HASH=new\r\n"
    )


def test_appends_with_crlf_when_file_is_crlf():
    assert upsert_env_line("A=1\r\n", "APP_PASSWORD_HASH", "new") == (
        "A=1\r\nAPP_PASSWORD_HASH=new\r\n"
    )


def test_preserves_comments_and_blank_lines():
    content = "# 注释\n\nA=1\n"

    assert upsert_env_line(content, "K", "v") == "# 注释\n\nA=1\nK=v\n"


def test_does_not_touch_a_key_with_the_same_prefix():
    content = "APP_PASSWORD_HASH_OLD=keep\n"

    assert upsert_env_line(content, "APP_PASSWORD_HASH", "new") == (
        "APP_PASSWORD_HASH_OLD=keep\nAPP_PASSWORD_HASH=new\n"
    )


def test_replaces_every_duplicate():
    """python-dotenv 取最后一条：只改第一条会留下旧密码继续生效"""
    content = "APP_PASSWORD_HASH=old1\nAPP_PASSWORD_HASH=old2\n"

    assert upsert_env_line(content, "APP_PASSWORD_HASH", "new") == (
        "APP_PASSWORD_HASH=new\nAPP_PASSWORD_HASH=new\n"
    )


def test_hash_with_dollar_signs_round_trips_through_dotenv():
    """`pbkdf2_sha256$600000$salt$hash` 里的 `$` 不能被当成变量插值"""
    value = "pbkdf2_sha256$600000$c2FsdA==$aGFzaA=="
    updated = upsert_env_line("A=1\n", "APP_PASSWORD_HASH", value)

    assert dotenv_values(stream=io.StringIO(updated))["APP_PASSWORD_HASH"] == value
