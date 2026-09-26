"""
AI 试穿测试（阶段四 TDD 循环 H）

H1 组：纯函数（衣物描述 / prompt 构建）——无 IO
H2 组：编排层（build_tryon），monkeypatch call_image_api 验证调用与失败传播
"""
import pytest

from services.garment_roles import (
    ROLE_ACCESSORY,
    ROLE_BOTTOM,
    ROLE_SHOES,
    ROLE_TOP,
)
from services.seedream_client import UpstreamError
from services.tryon import (
    MIN_REFERENCE_PIXELS,
    build_tryon,
    build_tryon_prompt,
    describe_garment,
    is_low_resolution,
)


DEFAULT_CATEGORY = {
    ROLE_TOP: "上衣",
    ROLE_BOTTOM: "裤子",
    ROLE_SHOES: "鞋",
    ROLE_ACCESSORY: "配饰",
}


def make_garment(
    item_id,
    *,
    role=ROLE_TOP,
    category=None,
    sub_category="T恤",
    color="蓝色",
):
    return {
        "id": item_id,
        "category": category if category is not None else DEFAULT_CATEGORY.get(role),
        "sub_category": sub_category,
        "color": color,
        "role": role,
    }


# ---------- describe_garment ----------

def test_describe_garment_combines_color_name_and_role():
    item = make_garment(1, sub_category="短袖T恤", color="蓝色")

    assert describe_garment(item) == "蓝色短袖T恤（上衣）"


def test_describe_garment_falls_back_to_category():
    item = make_garment(1, category="裤子", sub_category=None, color=None, role=ROLE_BOTTOM)

    assert describe_garment(item) == "裤子（下装）"


def test_describe_garment_never_emits_none():
    """识别失败时语义字段全为 null，折叠进 prompt 会出现字面量「None」"""
    item = make_garment(1, category=None, sub_category=None, color=None, role=None)

    assert describe_garment(item) == "衣物"


def test_describe_garment_does_not_repeat_color_already_in_the_name():
    """视觉模型的 sub_category 有时自带颜色（「白色运动鞋」），再叠加 color 会写成「白色白色运动鞋」"""
    item = make_garment(1, role=ROLE_SHOES, sub_category="白色运动鞋", color="白色")

    assert describe_garment(item) == "白色运动鞋（鞋）"


def test_describe_garment_drops_color_when_name_qualifies_it():
    item = make_garment(1, role=ROLE_BOTTOM, sub_category="深蓝色牛仔裤", color="蓝色")

    assert describe_garment(item) == "深蓝色牛仔裤（下装）"


# ---------- is_low_resolution ----------

def test_is_low_resolution_flags_tiny_reference():
    """40×40 是缩略图级别，模型只能靠脑补，保真无从谈起"""
    assert is_low_resolution((40, 40)) is True


def test_is_low_resolution_accepts_a_thumbnail_that_actually_worked():
    """探路时 430×458（196,940 px）的鞋子参考图出图是好的，
    阈值必须低于它，否则会对实际可用的图误报"""
    assert is_low_resolution((430, 458)) is False


def test_min_reference_pixels_is_a_floor_not_a_quality_bar():
    assert MIN_REFERENCE_PIXELS <= 430 * 458


# ---------- build_tryon_prompt ----------

def test_build_tryon_prompt_orders_garments_by_role_then_id():
    """顺序必须确定：「第 N 张参考图」要有稳定含义，不能随勾选顺序漂移"""
    garments = [
        make_garment(1, role=ROLE_ACCESSORY, sub_category="帽子"),
        make_garment(2, role=ROLE_SHOES, sub_category="运动鞋"),
        make_garment(3, role=ROLE_BOTTOM, sub_category="牛仔裤"),
        make_garment(4, role=ROLE_TOP, sub_category="卫衣"),
    ]

    prompt = build_tryon_prompt(garments)

    assert (
        prompt.index("卫衣")
        < prompt.index("牛仔裤")
        < prompt.index("运动鞋")
        < prompt.index("帽子")
    )


def test_build_tryon_prompt_orders_same_role_by_id():
    garments = [
        make_garment(9, role=ROLE_TOP, sub_category="卫衣"),
        make_garment(5, role=ROLE_TOP, sub_category="衬衫"),
    ]

    prompt = build_tryon_prompt(garments)

    assert prompt.index("衬衫") < prompt.index("卫衣")


def test_build_tryon_prompt_puts_unknown_role_last():
    garments = [
        make_garment(1, category=None, sub_category="神秘物件", role=None),
        make_garment(2, role=ROLE_SHOES, sub_category="运动鞋"),
    ]

    prompt = build_tryon_prompt(garments)

    assert prompt.index("运动鞋") < prompt.index("神秘物件")


def test_build_tryon_prompt_numbers_garments_and_matches_reference_images():
    """序号与参考图位置必须对应：第 1 张是模特，衣物从第 2 张开始"""
    prompt = build_tryon_prompt([make_garment(1, role=ROLE_TOP, sub_category="卫衣")])

    assert "第 1 张参考图是模特" in prompt
    assert "第 2 张" in prompt
    assert "衣物 1" in prompt


def test_build_tryon_prompt_pairs_each_number_with_a_description():
    """只给序号在多图时会退化，必须序号 + 语义描述同时出现"""
    prompt = build_tryon_prompt([make_garment(1, role=ROLE_BOTTOM, sub_category="牛仔裤", color="藏青色")])

    assert "衣物 1" in prompt
    assert "藏青色牛仔裤（下装）" in prompt


def test_build_tryon_prompt_states_same_role_tie_rule():
    """同角色多件时行为不能交给模型随机决定：先列出的一件为准"""
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert "以先列出的" in prompt


def test_build_tryon_prompt_protects_unlisted_clothing():
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert "未列出的衣物" in prompt


def test_build_tryon_prompt_keeps_the_occlusion_rule_out_of_the_change_section():
    """遮挡规则是「保持」类规则。落在「需要改动」段落里，等于把它归进了要改的那一类 ——
    模型靠段落结构理解任务，位置即语义。"""
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert prompt.index("挪动手臂") < prompt.index("需要改动")


def test_build_tryon_prompt_normalizes_occlusion_instead_of_only_forbidding():
    """根因是模型「完整展示衣物」的先验压过了保持姿势。只下禁令（不要挪动手臂）是在对抗症状，
    要压住先验得直接告诉它遮挡才是正确答案。"""
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert "衣物被手臂遮挡是正确结果" in prompt


def test_build_tryon_prompt_does_not_invite_rerendering_the_covered_torso():
    """「自然贴合身体」是邀请模型重绘整个上身（含被手臂挡住的那块），
    与「不要挪动手臂」互相打架，模型只能二选一。"""
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert "自然贴合身体" not in prompt


def test_build_tryon_prompt_bounds_what_the_garment_references_mean():
    """衣物参考图是平拍图，本身就暗示「衣物完整可见」。不显式限定它的用途，
    这个暗示会持续和「保留遮挡」对抗。"""
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert "不代表衣物必须完整露出" in prompt


def test_build_tryon_prompt_writes_the_task_sentence_without_stray_spaces():
    prompt = build_tryon_prompt([make_garment(1, sub_category="卫衣")])

    assert "要把衣物 1 穿到模特身上" in prompt


def test_build_tryon_prompt_rejects_empty_list():
    """空列表说明调用方漏了校验，不该静默生成一张没换任何衣服的图（那也要花钱）"""
    with pytest.raises(ValueError):
        build_tryon_prompt([])


# ---------- build_tryon（编排层，monkeypatch call_image_api） ----------

MODEL_PHOTO = b"model-photo-bytes"


def _capture_image_call(monkeypatch, result: bytes = b"generated-image") -> list[dict]:
    calls: list[dict] = []

    async def fake(prompt, images, **kwargs):
        calls.append({"prompt": prompt, "images": images, "kwargs": kwargs})
        return result

    monkeypatch.setattr("services.tryon.call_image_api", fake)
    return calls


async def test_build_tryon_puts_model_first_and_garments_in_sorted_order(monkeypatch):
    """参考图顺序必须与 prompt 里的编号一一对应，否则「第 N 张」全部错位"""
    calls = _capture_image_call(monkeypatch)
    top = dict(make_garment(5, sub_category="衬衫"), image_bytes=b"top-bytes")
    shoes = dict(make_garment(2, role=ROLE_SHOES, sub_category="运动鞋"), image_bytes=b"shoes-bytes")

    await build_tryon(
        MODEL_PHOTO, [shoes, top], api_key="k", model="m"  # 故意乱序传入
    )

    assert calls[0]["images"] == [MODEL_PHOTO, b"top-bytes", b"shoes-bytes"]


async def test_build_tryon_sends_the_shared_prompt(monkeypatch):
    calls = _capture_image_call(monkeypatch)
    garments = [dict(make_garment(1, sub_category="卫衣"), image_bytes=b"x")]

    await build_tryon(MODEL_PHOTO, garments, api_key="k", model="m")

    assert calls[0]["prompt"] == build_tryon_prompt(garments)


async def test_build_tryon_passes_credentials_through(monkeypatch):
    calls = _capture_image_call(monkeypatch)
    garments = [dict(make_garment(1), image_bytes=b"x")]

    await build_tryon(
        MODEL_PHOTO, garments, api_key="secret", model="doubao-image-test",
        base_url="https://example.com/api/v3",
    )

    assert calls[0]["kwargs"] == {
        "api_key": "secret",
        "model": "doubao-image-test",
        "base_url": "https://example.com/api/v3",
    }


async def test_build_tryon_rejects_empty_garments_without_calling_api(monkeypatch):
    calls = _capture_image_call(monkeypatch)

    with pytest.raises(ValueError):
        await build_tryon(MODEL_PHOTO, [], api_key="k", model="m")

    assert calls == []


async def test_build_tryon_propagates_upstream_error(monkeypatch):
    """上游错误必须往上抛给 API 层分类（429 透传 / 其余 503），不能在这里吞掉"""

    async def failing(prompt, images, **kwargs):
        raise UpstreamError(429, "rate limited")

    monkeypatch.setattr("services.tryon.call_image_api", failing)

    with pytest.raises(UpstreamError):
        await build_tryon(
            MODEL_PHOTO, [dict(make_garment(1), image_bytes=b"x")], api_key="k", model="m"
        )
