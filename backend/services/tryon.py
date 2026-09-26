"""
AI 虚拟试穿（阶段四核心）

模特全身照 + 衣柜衣物 → 图像编辑模型 → 穿着效果图。

和推荐引擎一样分两层：这里只负责把「穿什么」翻译成模型能可靠执行的 prompt，
HTTP 调用交给 services/seedream_client.call_image_api。

关键约束（见 CLAUDE.md）：喂**原图** image_path，绝不喂 cropped_path ——
抠图边缘有 halo，rembg 还可能误裁衣物部件（裤脚连着的鞋），喂给图像编辑模型会带出脏边。

**根因**（2026-09-25 探路 7 次 + 2026-09-26 端到端 12 次真实调用得出）：

Seedream 是**整图重绘**的通用图像编辑模型，缺三样专用试穿模型（IDM-VTON 那类）天生就有的东西：
mask（mask 外的像素原样拷贝回去）、pose 条件分支、garment 编码器。于是「哪些像素不能变」
只能靠 prompt 软引导，而 prompt 对扩散采样器是**概率性**约束，不是硬约束。

由此产生的三个限制：

1. **参考衣物与手臂区域重叠时，模型可能挪动手臂**。它优先满足「完整展示衣物」这一训练先验，
   而不是保持姿势。注意触发条件是**遮挡**而非「换上衣」——手臂搭在胯上挡住裤子时，换裤子一样会漂。
   已试过两轮强指令，共 19 次真实调用，**姿势指标一次都没动过**：
   - 2026-09-25：「局部修图」「手臂位置必须一致」「点明遮挡关系」（7 次，全无效）
   - 2026-09-26：把遮挡规则移回「保持」段、改写成「遮挡是正确结果」的正常化表述、
     去掉与保持姿势打架的「自然贴合身体」、限定参考图用途（12 次，含 3v3 配对）
   配对实测（同输入 [9,10,11]，旧 3 次 vs 新 3 次）：
   - **姿势保持 2/2 → 0/3**。点估计反向；Fisher p≈0.10，n=3 不足以判定退化，但**无任何改善证据**
   - 构图稳定**明显改善**：人物占画布高极差 25.1 → 4.8，旧 prompt 出过一次裁头
   - 裤子白侧条 1/3 → 2/3（噪声内）；水印两轮都干净
   - 新失效：一次头发变披→马尾，且「假两件」只渲染了挂脖那一半（袖子整条丢失）
   推测「不代表衣物必须完整露出」正是给模型重排身体的许可。
   **结论：prompt 调优到此为止** —— 保留改动（构图收益是实测的），接受姿势限制并写进产品文案。
2. **参考图的水印会被复制到成图，但概率低**。2026-09-26 全库 9 张结果逐张查底边：**1/9**。
   唯一一次来自 id=6 参考图的「豆包AI生成」水印（参考图水印在右下、距右 6.8% 宽、89×33px；
   成图 ghost 在右下、距右约 5.8%、约 193×38px，按 1728/1279 缩放吻合）。
   6 次 [9,10,11] 即使参考图自带水印也一次没泄漏。代价是衣物自带的品牌标志可能一起丢。
   （注：2026-09-26 早前记的「多图 5 次泄漏 3 次」是错的，已按全库逐张复测更正。）
3. **输出整体抖动**：同一输入连跑 3 次得到「丢侧条 / 丢侧条 / 完整」，另有一次构图漂移
   （模特被放大到裁掉头顶）。单张结果不可信，**重跑是目前唯一的缓解手段**。

模板结构是「保持一致 / 需要改动」两段对比，比原来的 7 条规则列表效果好：
规则列表下会出现左右袖长不一致，对比结构下不会（但 n=1，也可能是偶然）。

**验证门槛**：输出是随机的，所以「改完跑一次看着好了」什么都证明不了。
判断一个 prompt 变体是否有效至少要 n≥3 同输入 + 对照（约 ¥0.6/变体），
且 n=3 时 1/3 vs 2/3 仍在噪声范围内 —— 只能抓住大幅改善。
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
手臂挡在衣物前面时，被遮住的部分照原样保留 —— **衣物被手臂遮挡是正确结果**，
不要为了展示完整衣物而挪动手臂或改变站姿。

**需要改动**：只把{garment_refs}换成对应参考图的款式，褶皱、垂坠与光影跟场景一致。
第 2 张及之后的参考图**仅用于确认款式、颜色与材质，不代表衣物必须完整露出**。

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
