"""
设置（或重置）登录密码：把 pbkdf2 哈希写入 `backend/.env` 的 `APP_PASSWORD_HASH`

用法（在 backend 目录）：
    ./venv/Scripts/python.exe scripts/set_password.py

**不要手写哈希**，用这个脚本。改完必须重启后端：
`get_settings` 带 `lru_cache`，且会话签名密钥派生自 `password_hash` ——
改密码会让所有旧 cookie 立刻失效（等于「退出所有设备」）。
"""
import getpass
import os
import sys
import tempfile
from pathlib import Path

# 从 backend 目录运行时，`scripts/` 是脚本所在目录，`security/` 在上一级
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from security.env_file import upsert_env_line  # noqa: E402
from security.password import hash_password  # noqa: E402

ENV_PATH = BACKEND_DIR / ".env"
ENV_KEY = "APP_PASSWORD_HASH"


def write_password_file(env_path: Path, password: str) -> None:
    """写入密码哈希；其余行（含 CRLF）原样保留，用临时文件原子替换。

    `newline=""` 关闭 Windows 的换行翻译，否则整份文件会被改成 LF。
    """
    try:
        with open(env_path, encoding="utf-8", newline="") as file:
            content = file.read()
    except FileNotFoundError:
        content = ""

    updated = upsert_env_line(content, ENV_KEY, hash_password(password))

    fd, tmp_name = tempfile.mkstemp(
        dir=str(env_path.parent), prefix=".env.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(updated)
        os.replace(tmp_name, env_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    password = getpass.getpass("新密码：")
    confirm = getpass.getpass("再输一次：")

    if not password:
        print("密码不能为空，未写入任何内容")
        return 1
    if password != confirm:
        print("两次输入不一致，未写入任何内容")
        return 1

    write_password_file(ENV_PATH, password)
    print(f"已写入 {ENV_PATH}")
    print("请重启后端使新密码生效；所有旧会话（cookie）已全部失效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
