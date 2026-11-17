"""
`.env` 文本的单行更新

只做一件事：把某个键改成指定值，其余字节原样保留（注释、空行、其他变量、
Windows 的 CRLF 换行都不动）。写到磁盘的原子性由调用方负责。
"""


def upsert_env_line(content: str, key: str, value: str) -> str:
    """返回把 `key=value` 写入后的完整文本。

    - 已存在该键：**所有**重复行都替换。python-dotenv 取最后一条，
      只替换第一条会让旧密码继续生效。
    - 不存在：追加到末尾，换行符跟随文件现有风格（有 CRLF 就用 CRLF）。
    - 只匹配精确的键名：`APP_PASSWORD_HASH_OLD` 不会被 `APP_PASSWORD_HASH` 误伤。
    """
    newline = "\r\n" if "\r\n" in content else "\n"
    replacement = f"{key}={value}"
    lines = content.splitlines(keepends=True)
    result = []
    replaced = False

    for line in lines:
        ending = ""
        body = line
        if body.endswith("\r\n"):
            ending, body = "\r\n", body[:-2]
        elif body.endswith("\n") or body.endswith("\r"):
            ending, body = body[-1], body[:-1]

        if body.strip().startswith(f"{key}="):
            result.append(replacement + ending)
            replaced = True
        else:
            result.append(line)

    if not replaced:
        # 最后一行没有换行符时先补一个，否则追加的键会粘在它末尾
        if result and not result[-1].endswith(("\n", "\r")):
            result[-1] += newline
        result.append(replacement + newline)

    return "".join(result)
