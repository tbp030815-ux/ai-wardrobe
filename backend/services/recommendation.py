"""
穿搭推荐引擎（阶段三核心）

混合架构：
1. 规则层按温度/场合筛出候选衣物（保证不推荐不存在的衣服）
2. 把候选列表交给 LLM 精选一套并写自然语言理由
3. 后端严格校验 LLM 返回的 id 必须在候选集内
4. LLM 不可用（无 Key/报错/输出非法）时降级为纯规则推荐
"""
import httpx

from services.seedream_client import ARK_BASE_URL, call_chat_api, parse_semantics_json

DEFAULT_OCCASION = "休闲"
OCCASION_STYLES: dict[str, set[str]] = {
    "通勤": {"商务", "正式", "简约", "休闲"},
    "休闲": {"休闲", "运动", "甜美", "简约"},
    "运动": {"运动", "休闲"},
    "约会": {"甜美", "优雅", "时尚", "休闲"},
    "正式": {"商务", "正式", "优雅"},
}
SUPPORTED_OCCASIONS = tuple(OCCASION_STYLES)

ROLE_TOP, ROLE_BOTTOM, ROLE_SHOES, ROLE_ACCESSORY = "上衣", "下装", "鞋", "配饰"
# 角色 → 允许的 category 取值（下装把裤子和裙子合成一个角色，二者只穿一件）
ROLE_CATEGORIES: dict[str, set[str]] = {
    ROLE_TOP: {"上衣"},
    ROLE_BOTTOM: {"裤子", "裙子"},
    ROLE_SHOES: {"鞋"},
    ROLE_ACCESSORY: {"配饰"},
}
CATEGORY_ROLE: dict[str, str] = {c: r for r, cats in ROLE_CATEGORIES.items() for c in cats}
REQUIRED_ROLES = (ROLE_TOP, ROLE_BOTTOM, ROLE_SHOES)  # 配饰是可选加分项
ROLE_ORDER = (ROLE_TOP, ROLE_BOTTOM, ROLE_SHOES, ROLE_ACCESSORY)
ROLE_LABELS = {ROLE_TOP: "上衣", ROLE_BOTTOM: "裤子或裙子", ROLE_SHOES: "鞋"}
MAX_CANDIDATES_PER_ROLE = 4

HEAVY_KEYWORDS = ("羽绒", "棉服", "棉袄", "大衣", "毛衣", "针织", "加绒", "羊绒", "厚")
LIGHT_KEYWORDS = ("T恤", "短袖", "背心", "吊带", "短裤", "短裙", "凉鞋", "雪纺", "薄", "拖鞋")
HOT_THRESHOLD, COLD_THRESHOLD = 28, 10


def season_bands(temperature: float) -> set[str]:
    """温度（°C）→ 可接受的季节集合（同一温度可能横跨多季）"""
    if temperature >= 28:
        return {"夏季"}
    if temperature >= 20:
        return {"春季", "夏季", "秋季"}
    if temperature >= 10:
        return {"春季", "秋季"}
    return {"冬季"}


def matches_season(item_season: str | None, band: set[str]) -> bool:
    if not item_season or item_season in ("四季", "未知"):
        return True  # 通用款/未识别 → 永不被筛掉，只影响打分排序
    return item_season in band


def score_item(item: dict, *, band: set[str], occasion: str, temperature: float) -> int:
    """单件衣物当日适配度打分（整数、确定性、无副作用）。

    输入假定已通过季节筛选，因此季节项只区分「精确当季」与「通用/未知」。
    """
    score = 0

    season = item.get("season")
    if season in band:
        score += 40
    elif not season or season in ("四季", "未知"):
        score += 10

    style = item.get("style")
    if style and style in OCCASION_STYLES.get(occasion, set()):
        score += 30
    elif not style:
        score += 5

    text = f"{item.get('sub_category') or ''}{item.get('tags') or ''}"
    if temperature >= HOT_THRESHOLD:
        if any(k in text for k in HEAVY_KEYWORDS):
            score -= 30
        if any(k in text for k in LIGHT_KEYWORDS):
            score += 15
    elif temperature < COLD_THRESHOLD:
        if any(k in text for k in LIGHT_KEYWORDS):
            score -= 30
        if any(k in text for k in HEAVY_KEYWORDS):
            score += 15

    return score


def pick_best(items: list[dict], *, band, occasion, temperature) -> dict | None:
    """取分数最高的一件；同分取 id 最大（最新添加，与衣柜列表倒序一致）"""
    if not items:
        return None
    return max(
        items,
        key=lambda it: (score_item(it, band=band, occasion=occasion, temperature=temperature), it["id"]),
    )


def build_candidates(
    wardrobe: list[dict], *, weather, occasion: str, per_role: int = MAX_CANDIDATES_PER_ROLE
) -> dict[str, list[dict]]:
    """按温度筛出候选，按角色分组，每组按分数降序取前 per_role 件"""
    band = season_bands(weather.reference_temperature)
    temperature = weather.reference_temperature
    grouped: dict[str, list[dict]] = {role: [] for role in ROLE_CATEGORIES}

    for item in wardrobe:
        if not matches_season(item.get("season"), band):
            continue
        role = CATEGORY_ROLE.get(item.get("category") or "")
        if role is None:
            continue  # 分类未识别 → 无法判断角色，不进候选
        grouped[role].append(dict(item, role=role))

    for role, items in grouped.items():
        items.sort(
            key=lambda it: (
                score_item(it, band=band, occasion=occasion, temperature=temperature),
                it["id"],
            ),
            reverse=True,
        )
        del items[per_role:]
    return grouped


def find_gaps(wardrobe: list[dict], candidates: dict[str, list[dict]]) -> list[str]:
    """检测缺什么：分「真的没有」和「有但不适合当前天气」两档文案"""
    if not wardrobe:
        return ["衣柜还是空的，先去「我的衣柜」添加衣物吧"]

    hints: list[str] = []
    for role in REQUIRED_ROLES:
        if candidates[role]:
            continue
        owned = [it for it in wardrobe if CATEGORY_ROLE.get(it.get("category") or "") == role]
        label = ROLE_LABELS[role]
        if owned:
            hints.append(f"衣柜里的{label}不太适合当前天气，建议添置当季款")
        else:
            hints.append(f"衣柜里还没有{label}")
    return hints


def build_template_reason(items: list[dict], weather, occasion: str) -> str:
    names = " + ".join(
        f"{it.get('color') or ''}{it.get('sub_category') or it.get('category') or '衣物'}"
        for it in items
    )
    return (
        f"{weather.city}今天{weather.description}，体感 {weather.reference_temperature}°C"
        f"（{weather.temp_min:.0f}~{weather.temp_max:.0f}°C），"
        f"{occasion}场合推荐这套：{names}。"
    )


RECOMMEND_PROMPT_TEMPLATE = """你是一位中文穿搭顾问。请只从下面的候选衣物中挑选今天最合适的一套，并说明理由。

天气：{city} {description}，当前 {temperature:.1f}°C（体感 {apparent:.1f}°C），今日 {temp_min:.0f}~{temp_max:.0f}°C
场合：{occasion}
候选衣物（每行一件，格式：id 大类/细分 颜色 风格 季节）：
{candidates}

要求：
1. 尽量同时包含上衣、下装（裤子或裙子）、鞋各一件；配饰可选
2. 只能使用上面出现过的 id，不要编造任何衣物
3. 理由用一句自然的中文说明为什么这样搭，40 字以内
只返回 JSON，不要任何其他文字：{{"clothes_ids": [3, 7, 12], "reason": "……"}}"""


def format_candidates(items: list[dict]) -> str:
    return "\n".join(
        f"- id={it['id']} {it.get('category') or '未知'}/{it.get('sub_category') or '未知'} "
        f"{it.get('color') or '颜色未知'} {it.get('style') or '风格未知'} {it.get('season') or '季节未知'}"
        for it in items
    )


def build_prompt(items: list[dict], weather, occasion: str) -> str:
    return RECOMMEND_PROMPT_TEMPLATE.format(
        city=weather.city,
        description=weather.description,
        temperature=weather.temperature,
        apparent=weather.apparent_temperature,
        temp_min=weather.temp_min,
        temp_max=weather.temp_max,
        occasion=occasion,
        candidates=format_candidates(items),
    )


def validate_llm_result(raw: str, candidate_ids: set[int]) -> tuple[list[int], str]:
    """解析并校验 LLM 输出 → (合法 id 列表, 理由)；整体不可用则抛 ValueError 由调用方降级。

    分层处理：
    - JSON 解析失败 / 缺 clothes_ids / 全越界 → 抛 ValueError（整体降级）
    - 个别 id 越界（幻觉）→ 丢弃该 id，其余照用
    - 重复 id → 去重保序；字符串 id → 容错转 int；bool → 先排除
    - 缺 reason → 不算失败，返回空串由调用方用模板理由补齐
    """
    data = parse_semantics_json(raw)

    raw_ids = data.get("clothes_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("模型未返回 clothes_ids")

    ids: list[int] = []
    for value in raw_ids:
        if isinstance(value, bool):
            continue
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        if not isinstance(value, int) or value not in candidate_ids:
            continue
        if value not in ids:
            ids.append(value)

    if not ids:
        raise ValueError("模型返回的衣物 id 都不在候选集内")

    reason = data.get("reason")
    return ids, reason.strip() if isinstance(reason, str) else ""


def _dedupe_by_role(items: list[dict]) -> list[dict]:
    """同一必备角色只保留一件（LLM 可能同时返回裤子和裙子）"""
    seen: set[str] = set()
    kept: list[dict] = []
    for item in items:
        role = item.get("role") or CATEGORY_ROLE.get(item.get("category") or "")
        if role in REQUIRED_ROLES:
            if role in seen:
                continue
            seen.add(role)
        kept.append(item)
    return kept


def _complete_roles(picked: list[dict], candidates: dict[str, list[dict]]) -> list[dict]:
    """LLM 漏选某个必备角色时，用规则补上该角色分数最高的一件"""
    result = _dedupe_by_role(picked)
    have = {it.get("role") for it in result}
    for role in REQUIRED_ROLES:
        if role not in have and candidates[role]:
            result.append(candidates[role][0])
    order = {role: i for i, role in enumerate(ROLE_ORDER)}
    result.sort(key=lambda it: order.get(it.get("role") or "", len(ROLE_ORDER)))
    return result


def _pick_by_rule(candidates: dict[str, list[dict]]) -> list[dict]:
    """纯规则降级：每个必备角色取第一名，配饰有就带上"""
    picked = [candidates[role][0] for role in REQUIRED_ROLES if candidates[role]]
    if candidates[ROLE_ACCESSORY]:
        picked.append(candidates[ROLE_ACCESSORY][0])
    return _dedupe_by_role(picked)


async def build_recommendation(
    wardrobe: list[dict],
    weather,
    occasion: str,
    *,
    api_key: str,
    model: str,
    base_url: str = ARK_BASE_URL,
) -> dict:
    """混合推荐主流程：规则筛选 → LLM 精选 → 严格校验 →（失败/不可用）规则降级"""
    if occasion not in OCCASION_STYLES:
        occasion = DEFAULT_OCCASION
    candidates = build_candidates(wardrobe, weather=weather, occasion=occasion)
    flat = [it for role in ROLE_ORDER for it in candidates[role]]
    gaps = find_gaps(wardrobe, candidates)

    selected: list[dict] = []
    reason, source = "", "rule"

    if api_key and flat:
        try:
            raw = await call_chat_api(
                build_prompt(flat, weather, occasion),
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
            ids, llm_reason = validate_llm_result(raw, {it["id"] for it in flat})
            chosen = [it for it in flat if it["id"] in ids]
            selected = _complete_roles(chosen, candidates)
            reason = llm_reason or build_template_reason(selected, weather, occasion)
            source = "llm"
        except (ValueError, httpx.HTTPError, KeyError, TypeError):
            selected, reason, source = [], "", "rule"  # 任何异常都降级，绝不阻塞

    if not selected:
        selected = _pick_by_rule(candidates)
        reason = (
            build_template_reason(selected, weather, occasion)
            if selected
            else "衣柜里还没有可搭配的衣物，先去添加几件吧。"
        )

    return {"items": selected, "reason": reason, "source": source, "gaps": gaps}
