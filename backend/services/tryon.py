"""
AI 虚拟试穿（阶段四核心）

模特全身照 + 衣柜衣物 → 图像编辑模型 → 穿着效果图。

和推荐引擎一样分两层：这里只负责把「穿什么」翻译成模型能可靠执行的 prompt，
HTTP 调用交给 services/seedream_client.call_image_api。

关键约束（见 CLAUDE.md）：喂**原图** image_path，绝不喂 cropped_path ——
抠图边缘有 halo，rembg 还可能误裁衣物部件（裤脚连着的鞋），喂给图像编辑模型会带出脏边。

**prompt 的两个已知限制**（2026-09-25 实测 7 次真实调用得出，别再重复尝试修）：

1. **换上衣时姿势会漂**：手臂原本弯曲、手抬到胸前，成图会变成直垂。成因是衣物与手臂重叠，
   模型必须重绘该区域，重绘时顺手重摆了手臂 —— 换裤子（不涉及手臂）时姿势就保得住。
   已试过「局部修图」「手臂位置必须一致」「点明遮挡关系」三种强指令，**全部无效**，
   故不再投入。产品侧在试穿页注明这一差异。
2. **参考图的水印会传染到成图**，已用显式规则挡住，**代价是衣物自带的品牌标志可能一起丢**。

当前模板的结构是「保持一致 / 需要改动」两段对比，比原来的 7 条规则列表效果好：
规则列表下会出现左右袖长不一致，对比结构下不会（但 n=1，也可能是偶然）。
"""
from services.garment_roles import CATEGORY_ROLE, ROLE_ORDER
from services.seedream_client import ARK_BASE_URL, call_image_api

# 未识别出角色的衣物排在最后，不参与「按部位从上到下」的叙述顺序
_UNKNOWN_ROLE_RANK = len(ROLE_ORDER)
_ROLE_RANK = {role: index for index, role in enumerate(ROLE_ORDER)}

# 参考图「明显不可用」的像素地板。**这不是画质标准**：探路时 430×458（196,940 px）
# 的鞋子参考图出图是好的，阈值定高了会对实际能用的图标报，用户就会学会无视这个提示。
# 只拦缩略图级别（40×40 = 1,600 px）那种模型只能靠脑补的输入。
MIN_REFERENCE_PIXELS = 10_000

TRYON_PROMPT_TEMPLATE = """你是一位虚拟试穿助手。请把下面列出的衣物穿到模特身上，生成一张真实的试穿照片。

参考图（顺序即编号）：
- 第 1 张参考图是模特本人
{references}

要把{garment_refs} 穿到模特身上。

**必须与第 1 张参考图完全一致，不要改动**：手臂位置、手部动作、站姿、机位、裁切范围、发型、肤色、
光影、背景、镜面反光，以及模特身上**未列出的衣物**（原有的鞋、包、首饰等）。

**需要改动**：只把{garment_refs}换成对应参考图的款式，自然贴合身体，褶皱、垂坠与光影跟场景一致。
手臂挡在衣物前面时，被遮住的部分照原样保留，不要为了展示衣物而挪动手臂。

同一部位列了多件时，以先列出的那件为准，后列出的忽略。
只输出效果图，不加任何文字、水印或边框，也不要复制参考图角落的水印和店铺标记。"""


def is_low_resolution(size: tuple[int, int]) -> bool:
    """参考图像素低于地板值时返回 True —— 这种输入模型只能靠脑补，保真无从谈起"""
    return size[0] * size[1] < MIN_REFERENCE_PIXELS


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


async def build_tryon(
    model_image: bytes,
    garments: list[dict],
    *,
    api_key: str,
    model: str,
    base_url: str = ARK_BASE_URL,
) -> bytes:
    """试穿主流程：返回结果图字节。

    garments 是带 `image_bytes` 的衣物 dict。参考图顺序固定为 [模特, 衣物 1, 衣物 2, ...] ——
    必须与 `build_tryon_prompt` 里的编号严格对应，所以只排序一次、两处共用同一份序列。
    """
    if not garments:
        raise ValueError("试穿至少需要一件衣物")

    ordered = sorted(garments, key=sort_key)
    images = [model_image] + [item["image_bytes"] for item in ordered]
    return await call_image_api(
        build_tryon_prompt(ordered),
        images,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
