"""
模特 API 测试（阶段四 TDD 循环 J）

模特照不需要抠图（试穿直接喂原图），所以这里没有外部 AI 依赖，
被测的是上传落盘、默认模特的记账、以及出参的类型。
"""
import io

import pytest
from PIL import Image

from main import app
from tests.conftest import login, make_client


def make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), (180, 160, 140)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        try:
            assert login(c).status_code == 200
            yield c
        finally:
            app.dependency_overrides.clear()


def upload(client, name="model.jpg"):
    return client.post(
        "/api/model", files={"file": (name, make_jpeg_bytes(), "image/jpeg")}
    )


# ---------- POST /api/model ----------

def test_upload_model_returns_record(client):
    response = upload(client)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["image_path"].startswith("/uploads/")
    assert data["image_path"].endswith(".jpg")


def test_upload_model_saves_file_on_disk(client, tmp_path):
    upload(client)

    files = list((tmp_path / "uploads").iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == make_jpeg_bytes()


def test_upload_model_keeps_original_content(client, tmp_path):
    """试穿喂的是模特原图，任何转码都会影响出图质量"""
    upload(client)

    saved = next((tmp_path / "uploads").iterdir()).read_bytes()
    assert Image.open(io.BytesIO(saved)).size == (60, 80)


def test_first_uploaded_model_is_default(client):
    """不自动设默认，用户上传完立刻去试穿就会拿不到模特"""
    assert upload(client).json()["is_default"] is True


def test_second_uploaded_model_is_not_default(client):
    upload(client)

    assert upload(client, "second.jpg").json()["is_default"] is False


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/api/model", files={"file": ("m.jpg", b"", "image/jpeg")}
    )

    assert response.status_code == 400


def test_upload_rejects_invalid_image(client):
    """在这里挡掉，而不是等 60 秒的付费生成跑完才报错"""
    response = client.post(
        "/api/model", files={"file": ("m.jpg", b"not an image", "image/jpeg")}
    )

    assert response.status_code == 400


def test_upload_rejects_invalid_image_without_writing_file(client, tmp_path):
    client.post("/api/model", files={"file": ("m.jpg", b"not an image", "image/jpeg")})

    assert list((tmp_path / "uploads").iterdir()) == []


# ---------- GET /api/models ----------

def test_list_models_returns_bool_not_int(client):
    """SQLite 存的是 0/1，直接序列化出去前端拿到的是 1 而不是 true"""
    is_default = upload(client).json()["is_default"]

    assert is_default is True


def test_list_models_puts_default_first(client):
    first = upload(client).json()["id"]
    second = upload(client, "second.jpg").json()["id"]
    client.put(f"/api/models/{second}/default")

    response = client.get("/api/models")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [second, first]


def test_list_models_is_empty_for_new_user(client):
    assert client.get("/api/models").json() == []


# ---------- PUT /api/models/{id}/default ----------

def test_set_default_switches_default(client):
    upload(client)
    second = upload(client, "second.jpg").json()["id"]

    response = client.put(f"/api/models/{second}/default")

    assert response.status_code == 200
    assert response.json()["id"] == second
    assert response.json()["is_default"] is True

    models = client.get("/api/models").json()
    assert [row["id"] for row in models if row["is_default"]] == [second]


def test_set_default_404_for_unknown_id(client):
    response = client.put("/api/models/999/default")

    assert response.status_code == 404


def test_set_default_404_keeps_existing_default(client):
    """失败的切换不能把用户留在「一张默认都没有」的状态"""
    first = upload(client).json()["id"]

    client.put("/api/models/999/default")

    models = client.get("/api/models").json()
    assert [row["id"] for row in models if row["is_default"]] == [first]


# ---------- DELETE /api/models/{id} ----------

def test_delete_model_removes_record_and_file(client, tmp_path):
    """传错的模特照必须能在 UI 里删掉，图片文件也要跟着走"""
    model_id = upload(client).json()["id"]
    assert len(list((tmp_path / "uploads").iterdir())) == 1

    response = client.delete(f"/api/models/{model_id}")

    assert response.status_code == 200
    assert response.json()["id"] == model_id
    assert response.json()["is_default"] is True  # 出参必须是真 bool，不是 1
    assert list((tmp_path / "uploads").iterdir()) == []
    assert client.get("/api/models").json() == []


def test_delete_model_404_for_unknown_id(client):
    response = client.delete("/api/models/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "模特不存在"


def test_delete_model_promotes_the_newest_remaining(client):
    """删掉默认模特后必须有人补位：否则「默认」徽标全灭，用户不知道该用哪张"""
    first = upload(client).json()["id"]
    second = upload(client, "second.jpg").json()["id"]

    client.delete(f"/api/models/{first}")

    models = client.get("/api/models").json()
    assert [(row["id"], row["is_default"]) for row in models] == [(second, True)]


def test_delete_model_leaves_other_files_alone(client, tmp_path):
    first = upload(client).json()["id"]
    upload(client, "second.jpg")

    client.delete(f"/api/models/{first}")

    assert len(list((tmp_path / "uploads").iterdir())) == 1
