"""
上传文件路径解析与删除测试

`/uploads/` 前缀是 URL 约定（main.py 挂载的 StaticFiles 根），
`resolve_upload_path` 是它到磁盘路径的唯一映射。

**别用 `Path(url).name` 代替它**：试穿结果存在 `uploads/tryon/` 子目录下，
只取文件名会把它错解到 `uploads/` 根目录，指向一个不存在的文件。
"""
import pytest

from storage.uploads_store import UPLOAD_URL_PREFIX, delete_upload_files, resolve_upload_path


@pytest.fixture
def upload_dir(tmp_path):
    path = tmp_path / "uploads"
    path.mkdir()
    return path


# ---------- resolve_upload_path ----------

def test_resolves_a_file_at_the_uploads_root(upload_dir):
    assert resolve_upload_path(upload_dir, "/uploads/a.jpg") == upload_dir / "a.jpg"


def test_resolves_a_file_in_a_subdirectory(upload_dir):
    """试穿结果在 uploads/tryon/ 下 —— 取 `.name` 的写法会在这里错到 uploads/ 根目录"""
    assert resolve_upload_path(upload_dir, "/uploads/tryon/a.jpg") == upload_dir / "tryon" / "a.jpg"


def test_rejects_traversal(upload_dir):
    """路径穿越：`..` 必须被挡住，否则能删掉 uploads/ 之外的任意文件"""
    assert resolve_upload_path(upload_dir, "/uploads/../secret.jpg") is None


def test_rejects_paths_outside_the_uploads_prefix(upload_dir):
    assert resolve_upload_path(upload_dir, "/etc/passwd") is None
    assert resolve_upload_path(upload_dir, "https://example.com/a.jpg") is None


def test_rejects_empty_input(upload_dir):
    """cropped_path 在识别失败时仍会有值，但 NULL 也要能吃下"""
    assert resolve_upload_path(upload_dir, None) is None
    assert resolve_upload_path(upload_dir, "") is None
    assert resolve_upload_path(upload_dir, UPLOAD_URL_PREFIX) is None


# ---------- delete_upload_files ----------

def test_deletes_files_at_the_root_and_in_a_subdirectory(upload_dir):
    (upload_dir / "a.jpg").write_bytes(b"x")
    (upload_dir / "tryon").mkdir()
    (upload_dir / "tryon" / "b.jpg").write_bytes(b"y")

    delete_upload_files(upload_dir, ["/uploads/a.jpg", "/uploads/tryon/b.jpg"])

    assert not (upload_dir / "a.jpg").exists()
    assert not (upload_dir / "tryon" / "b.jpg").exists()


def test_tolerates_missing_and_null_paths(upload_dir):
    """重复删、删不存在的、传 None —— 都不该抛"""
    delete_upload_files(upload_dir, ["/uploads/nope.jpg", None, "/uploads/nope.jpg"])


def test_rejects_everything_outside_the_upload_dir(upload_dir, tmp_path):
    """穿越的 URL 必须一个文件都删不掉"""
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"x")
    (upload_dir / "a.jpg").write_bytes(b"y")

    delete_upload_files(upload_dir, ["/uploads/../secret.jpg", "http://x/a.jpg", "/uploads/a.jpg"])

    assert outside.exists()      # 越界的目标必须还在
    assert not (upload_dir / "a.jpg").exists()   # 合法的那条要照删


def test_does_not_raise_when_a_file_cannot_be_deleted(upload_dir):
    """库里的行已经删了，文件删不掉只能留成孤儿 —— 不能因此让整个请求失败。
    用同名目录制造失败：unlink 对目录会抛 OSError（Windows 是 PermissionError）。"""
    (upload_dir / "a.jpg").mkdir()

    delete_upload_files(upload_dir, ["/uploads/a.jpg"])

    assert (upload_dir / "a.jpg").is_dir()
