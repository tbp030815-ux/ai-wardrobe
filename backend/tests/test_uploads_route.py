"""
`/uploads/` 图片路由测试（阶段五）

原来这里是裸 `StaticFiles` 挂载：知道文件名就能绕过登录直接看图。
现在换成带 `current_user_id` 依赖的普通路由，文件目录取自 `settings.upload_dir`。
"""
import io

import pytest
from PIL import Image
from starlette.routing import Mount

from api.auth import SESSION_COOKIE
from main import app
from tests.conftest import login, make_client


def make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def write_upload(root, relative: str, content: bytes) -> bytes:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        try:
            assert login(c).status_code == 200
            yield c
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(tmp_path):
    with make_client(tmp_path) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------- 鉴权 ----------

def test_uploads_require_a_session(anonymous_client, tmp_path):
    write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = anonymous_client.get("/uploads/hello.png")

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_uploads_redirect_browser_navigation_to_the_app(anonymous_client, tmp_path):
    """在地址栏直接打开图片 URL 时回前端登录页，而不是吐一串 JSON"""
    write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = anonymous_client.get(
        "/uploads/hello.png",
        headers={"accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    # 原地址要带回去，登录成功后前端才能跳回这张图
    assert response.headers["location"] == "/?next=%2Fuploads%2Fhello.png"


def test_uploads_redirect_keeps_the_query_string(anonymous_client, tmp_path):
    write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = anonymous_client.get(
        "/uploads/hello.png?v=1",
        headers={"accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/?next=%2Fuploads%2Fhello.png%3Fv%3D1"


def test_uploads_keep_json_401_for_image_requests(anonymous_client, tmp_path):
    """`<img>` 拿到的必须还是 401：302 到登录页 HTML 只会变成一张坏图"""
    write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = anonymous_client.get(
        "/uploads/hello.png",
        headers={"accept": "image/avif,image/webp,*/*"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_uploads_reject_a_forged_cookie(anonymous_client, tmp_path):
    write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = anonymous_client.get(
        "/uploads/hello.png",
        headers={"cookie": f"{SESSION_COOKIE}=v1.1.9999999999.bogus"},
    )

    assert response.status_code == 401


# ---------- 正常读取 ----------

def test_uploads_serve_image_to_logged_in_user(client, tmp_path):
    content = write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = client.get("/uploads/hello.png")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "image/png"
    # 内容按 URL 不可变（文件名是 uuid），但**只允许私有缓存**：
    # 共享缓存会把图发给别的请求方，等于绕开登录
    assert (
        response.headers["cache-control"]
        == "private, max-age=31536000, immutable"
    )


def test_uploads_serve_image_for_browser_navigation_when_logged_in(client, tmp_path):
    """已登录时地址栏打开图片仍应看到图，不能因为 Accept 是 text/html 就被跳走"""
    content = write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = client.get(
        "/uploads/hello.png", headers={"accept": "text/html,application/xhtml+xml"}
    )

    assert response.status_code == 200
    assert response.content == content


def test_uploads_serve_files_in_subdirectories(client, tmp_path):
    """试穿结果图在 uploads/tryon/ 下：取文件名时不能把目录丢掉"""
    content = write_upload(tmp_path / "uploads", "tryon/x.png", make_png_bytes())

    response = client.get("/uploads/tryon/x.png")

    assert response.status_code == 200
    assert response.content == content


def test_uploads_return_404_for_missing_file(client):
    """必须先 is_file() 再返回：FileResponse 对不存在的文件会抛 RuntimeError（500）"""
    response = client.get("/uploads/nope.png")

    assert response.status_code == 404
    assert response.json()["detail"] == "文件不存在"


def test_uploads_reject_path_traversal(client, tmp_path):
    """%2e%2e%2f 是必需的：httpx 在发送前会把字面 `..` 规范化掉，测不到路由"""
    (tmp_path / "secret.png").write_bytes(b"secret")

    response = client.get("/uploads/%2e%2e%2fsecret.png")

    assert response.status_code == 404


def test_uploads_support_range_requests(client, tmp_path):
    """浏览器/图片查看器可能带 Range；FileResponse 原生支持，别自己读全量"""
    content = write_upload(tmp_path / "uploads", "hello.png", make_png_bytes())

    response = client.get("/uploads/hello.png", headers={"range": "bytes=0-3"})

    assert response.status_code == 206
    assert response.content == content[:4]
    assert response.headers["accept-ranges"] == "bytes"


# ---------- 元测试 ----------

def test_uploads_is_no_longer_a_static_mount():
    """Mount 对路由级元测试不可见：漏删的话鉴权断言会全绿，而图片仍然公开"""
    mounts = [
        route
        for route in app.routes
        if isinstance(route, Mount) and route.path == "/uploads"
    ]

    assert mounts == []
