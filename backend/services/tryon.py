"""
AI 虚拟试穿（阶段四核心）

模特全身照 + 衣柜衣物 → 图像编辑模型 → 穿着效果图。

和推荐引擎一样分两层：这里只负责把「穿什么」翻译成模型能可靠执行的 prompt，
HTTP 调用交给 services/seedream_client.call_image_api。

关键约束（见 CLAUDE.md）：喂**原图** image_path，绝不喂 cropped_path ——
抠图边缘有 halo，rembg 还可能误裁衣物部件（裤脚连着的鞋），喂给图像编辑模型会带出脏边。
"""
from services.garment_roles import CATEGORY_ROLE, ROLE_ORDER

# 未识别出角色的衣物排在最后，不参与「按部位从上到下」的叙述顺序
_UNKNOWN_ROLE_RANK = len(ROLE_ORDER)
_ROLE_RANK = {role: index for index, role in enumerate(ROLE_ORDER)}

TRYON_PROMPT_TEMPLATE = """你是一位虚拟试穿助手。请把下面列出的衣物穿到模特身上，生成一张真实的试穿照片。

参考图（顺序即编号）：
- 第 1 张参考图是模特：保持这个人的脸部、发型、身材、姿势、场景和光线不变
{references}

要把{garment_refs} 穿到模特身上。

规则：
1. 只替换上面列出的衣物；模特身上**未列出的衣物**（原有的鞋、包、首饰等）必须保持原样
2. 同一部位列了多件时，以先列出的那件为准，后列出的忽略
3. 模特的姿势、脸部、发型、肤色、背景一律不变
4. 衣物要自然贴合身体，褶皱、垂坠与光影跟场景一致，不要像贴图
5. 只输出效果图，不加任何文字、水印或边框"""


def role_of(item: dict) -> str | None:
    """取衣物角色：优先用已算好的 role，否则由 category 推导（识别失败的衣物返回 None）"""
    return item.get("role") or CATEGORY_ROLE.get(item.get("category") or "")


def describe_garment(item: dict) -> str:
    """把一件衣物写成一句可读描述。语义字段可能为 null，必须折叠掉，不能漏出字面量「None」"""
    color = item.get("color") or ""
    name = item.get("sub_category") or item.get("category") or "衣物"
    if color and color in name:
        color = ""  # 视觉模型有时把颜色写进品类（「白色运动鞋」「深蓝色牛仔裤」），叠加会重复
    label = f"{color}{name}"
    role = role_of(item)
    return f"{label}（{role}）" if role else label


def sort_key(item: dict) -> tuple[int, int]:
    """按「角色自上而下 + id 升序」排序。

    排序必须确定，否则「第 N 张参考图」的含义会随前端勾选顺序漂移，
    同角色多件时模型拿到哪件就成了随机事件 —— 不可测，而且白烧一次生成费用。
    """
    return (_ROLE_RANK.get(role_of(item) or "", _UNKNOWN_ROLE_RANK), item["id"])


def build_tryon_prompt(garments: list[dict]) -> str:
    """构建试穿 prompt。参考图顺序约定为：[模特, 衣物 1, 衣物 2, ...]"""
    if not garments:
        raise ValueError("试穿至少需要一件衣物")

    ordered = sorted(garments, key=sort_key)
    references = "\n".join(
        f"- 第 {index + 2} 张参考图是衣物 {index + 1}：{describe_garment(item)}"
        for index, item in enumerate(ordered)
    )
    return TRYON_PROMPT_TEMPLATE.format(
        references=references,
        garment_refs="、".join(f"衣物 {index + 1}" for index in range(len(ordered))),
    )
