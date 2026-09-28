"""
上传文件（`backend/uploads/`）的磁盘侧操作

`/uploads/` 前缀是 URL 约定（main.py 挂载的 StaticFiles 根），这里负责它到磁盘
路径的映射与删除；数据库侧的增删查在同目录的 `*_store.py` 里。
"""
from collections.abc import Iterable
from pathlib import Path

# main.py 的 StaticFiles 挂载点，改动必须同步
UPLOAD_URL_PREFIX = "/uploads/"


def resolve_upload_path(upload_dir: Path, url: str | None) -> Path | None:
    """`/uploads/tryon/a.jpg` → `<upload_dir>/tryon/a.jpg`，取不出合法路径时返回 None。

    **不能用 `Path(url).name` 代替**：那会把 `uploads/tryon/` 下的试穿结果错解到
    `uploads/` 根目录，指向一个不存在的文件。子目录是真实存在的层级，必须保留。

    越界判定放在 resolve 之后 —— `..`、绝对路径、Windows 盘符都能被同一条规则挡住，
    逐个字符串过滤反而容易漏。校验用 resolve 后的形态，返回值保留调用方传入的形态。
    """
    if not url or not url.startswith(UPLOAD_URL_PREFIX):
        return None
    relative = url[len(UPLOAD_URL_PREFIX):]
    if not relative:
        return None

    root = upload_dir.resolve()
    target = upload_dir / relative
    resolved = target.resolve()
    # 与 root 相等说明 URL 指向 upload_dir 本身，那是目录不是文件
    if resolved == root or root not in resolved.parents:
        return None
    return target


def delete_upload_files(upload_dir: Path, urls: Iterable[str | None]) -> None:
    """尽力删除这些 URL 对应的文件。

    **刻意不抛异常、也不返回失败清单**：调用方一律先删库再删文件，
    走到这里行已经没了；此时文件删不掉（Windows 上被占用是常见情形）只能留成孤儿，
    为此让整个请求报错、或者把已成功的删除回滚，都比留一个孤儿文件更糟。
    传 None 与不存在的路径都静默跳过，所以重复调用是安全的。
    """
    for url in urls:
        path = resolve_upload_path(upload_dir, url)
        if path is None:
            continue
        try:
            path.unlink()
        except OSError:
            pass
