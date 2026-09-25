"""
推荐引擎测试（阶段三 TDD 循环 C/D）

C 组：纯函数（季节带 / 打分 / 候选构建 / 缺失检测 / prompt / LLM 输出校验）——无 IO
D 组：编排层（build_recommendation），monkeypatch call_chat_api 验证降级路径
"""
import httpx
import pytest

from services.recommendation import (
    ROLE_ACCESSORY,
    ROLE_BOTTOM,
    ROLE_TOP,
    build_candidates,
    build_prompt,
    build_recommendation,
    build_template_reason,
    find_gaps,
    pick_best,
    score_item,
    season_bands,
    validate_llm_result,
)
from services.weather import Weather


def make_item(
    item_id,
    *,
    category="上衣",
    sub_category="T恤",
    color="蓝色",
    style="休闲",
    season="夏季",
    tags=None,
):
    return {
        "id": item_id,
        "user_id": 1,
        "image_path": f"/uploads/{item_id}.jpg",
        "cropped_path": None,
        "category": category,
        "sub_category": sub_category,
        "color": color,
        "style": style,
        "season": season,
        "tags": tags,
        "created_at": "2026-09-24 10:00:00",
    }


def make_weather(temperature=30.0, *, city="上海", description="晴", apparent=None):
    return Weather(
        city=city,
        temperature=temperature,
        apparent_temperature=apparent if apparent is not None else temperature,
        description=description,
        temp_max=temperature + 2,
        temp_min=temperature - 2,
        precipitation_probability=10,
        weather_code=0,
    )


# ---------- season_bands ----------

@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (28, {"夏季"}),
        (27.9, {"春季", "夏季", "秋季"}),
        (20, {"春季", "夏季", "秋季"}),
        (19.9, {"春季", "秋季"}),
        (10, {"春季", "秋季"}),
        (9.9, {"冬季"}),
    ],
)
def test_season_bands_boundaries(temp, expected):
    assert season_bands(temp) == expected


# ---------- score_item ----------

def test_score_prefers_season_match_over_universal():
    band = {"夏季"}
    in_season = make_item(1, season="夏季")
    universal = make_item(2, season="四季")

    assert score_item(in_season, band=band, occasion="休闲", temperature=30) > score_item(
        universal, band=band, occasion="休闲", temperature=30
    )


def test_score_prefers_occasion_style():
    band = {"夏季"}
    business = make_item(1, style="商务")
    sweet = make_item(2, style="甜美")

    assert score_item(business, band=band, occasion="通勤", temperature=30) > score_item(
        sweet, band=band, occasion="通勤", temperature=30
    )


def test_score_penalizes_heavy_item_in_hot_weather():
    band = {"夏季"}
    sweater = make_item(1, sub_category="毛衣")
    tee = make_item(2, sub_category="T恤")

    assert score_item(tee, band=band, occasion="休闲", temperature=32) > score_item(
        sweater, band=band, occasion="休闲", temperature=32
    )


def test_score_penalizes_light_item_in_cold_weather():
    band = {"冬季"}
    tee = make_item(1, sub_category="T恤", season="冬季")
    down_jacket = make_item(2, sub_category="羽绒服", season="冬季")

    assert score_item(down_jacket, band=band, occasion="休闲", temperature=5) > score_item(
        tee, band=band, occasion="休闲", temperature=5
    )


# ---------- pick_best ----------

def test_pick_best_breaks_ties_by_newest_id():
    items = [make_item(3), make_item(5)]  # 完全同分

    best = pick_best(items, band={"夏季"}, occasion="休闲", temperature=30)

    assert best["id"] == 5


def test_pick_best_returns_none_for_empty_list():
    assert pick_best([], band={"夏季"}, occasion="休闲", temperature=30) is None


# ---------- build_candidates ----------

def test_build_candidates_keeps_universal_and_unknown_season():
    items = [make_item(1, season="四季"), make_item(2, season=None)]

    candidates = build_candidates(items, weather=make_weather(30), occasion="休闲")

    assert {it["id"] for it in candidates[ROLE_TOP]} == {1, 2}


def test_build_candidates_drops_out_of_season_items():
    items = [make_item(1, season="夏季"), make_item(2, season="冬季")]

    candidates = build_candidates(items, weather=make_weather(30), occasion="休闲")

    top_ids = {it["id"] for it in candidates[ROLE_TOP]}
    assert top_ids == {1}


def test_build_candidates_groups_pants_and_skirts_as_bottom():
    pants = make_item(1, category="裤子", sub_category="牛仔裤")
    skirt = make_item(2, category="裙子", sub_category="短裙")

    candidates = build_candidates([pants, skirt], weather=make_weather(30), occasion="休闲")

    assert {it["id"] for it in candidates[ROLE_BOTTOM]} == {1, 2}


def test_build_candidates_limits_each_role():
    """每组最多 4 件，留下的是分数最高的 4 件"""
    tops = [make_item(i) for i in range(1, 6)]
    tops[4] = make_item(5, style="商务")  # 休闲场合下分数最低

    candidates = build_candidates(tops, weather=make_weather(30), occasion="休闲")

    kept = candidates[ROLE_TOP]
    assert len(kept) == 4
    assert 5 not in {it["id"] for it in kept}


def test_build_candidates_orders_by_score():
    low = make_item(1, style="商务")
    high = make_item(2, style="休闲")

    candidates = build_candidates([low, high], weather=make_weather(30), occasion="休闲")

    assert candidates[ROLE_TOP][0]["id"] == 2


def test_build_candidates_ignores_items_without_category():
    unknown = make_item(1, category=None)

    candidates = build_candidates([unknown], weather=make_weather(30), occasion="休闲")

    for role_items in candidates.values():
        assert role_items == []


def test_build_candidates_attaches_role_to_items():
    candidates = build_candidates([make_item(1)], weather=make_weather(30), occasion="休闲")

    assert candidates[ROLE_TOP][0]["role"] == ROLE_TOP


# ---------- find_gaps ----------

def test_find_gaps_lists_missing_categories():
    items = [make_item(1)]

    gaps = find_gaps(items, build_candidates(items, weather=make_weather(30), occasion="休闲"))

    assert gaps == ["衣柜里还没有裤子或裙子", "衣柜里还没有鞋"]


def test_find_gaps_distinguishes_wrong_season():
    """有该类衣物但被季节筛掉时，文案是「不适合当前天气」而不是「还没有」"""
    items = [make_item(1, sub_category="羽绒服", season="冬季")]

    gaps = find_gaps(items, build_candidates(items, weather=make_weather(30), occasion="休闲"))

    assert gaps[0] == "衣柜里的上衣不太适合当前天气，建议添置当季款"
    assert "衣柜里还没有裤子或裙子" in gaps


def test_find_gaps_empty_wardrobe():
    gaps = find_gaps([], build_candidates([], weather=make_weather(30), occasion="休闲"))

    assert gaps == ["衣柜还是空的，先去「我的衣柜」添加衣物吧"]


def test_find_gaps_empty_when_outfit_complete():
    items = [
        make_item(1),
        make_item(2, category="裤子"),
        make_item(3, category="鞋"),
    ]

    gaps = find_gaps(items, build_candidates(items, weather=make_weather(30), occasion="休闲"))

    assert gaps == []


# ---------- build_template_reason ----------

def test_build_template_reason_mentions_city_temp_and_items():
    items = [make_item(1, color="藏青色", sub_category="T恤")]

    reason = build_template_reason(items, make_weather(28, city="杭州"), "通勤")

    assert "杭州" in reason
    assert "通勤" in reason
    assert "藏青色T恤" in reason


# ---------- build_prompt ----------

def test_build_prompt_lists_every_candidate_id():
    items = [make_item(1), make_item(2), make_item(3, category="鞋", sub_category="运动鞋")]

    prompt = build_prompt(items, make_weather(28, city="上海"), "休闲")

    assert "id=1" in prompt
    assert "id=2" in prompt
    assert "id=3" in prompt
    assert "上海" in prompt
    assert "休闲" in prompt


# ---------- validate_llm_result ----------

def test_validate_accepts_valid_ids_and_reason():
    ids, reason = validate_llm_result(
        '{"clothes_ids": [3, 7], "reason": "清爽好看"}', {3, 7}
    )

    assert ids == [3, 7]
    assert reason == "清爽好看"


def test_validate_drops_out_of_range_ids():
    ids, _ = validate_llm_result('{"clothes_ids": [3, 999]}', {3})

    assert ids == [3]


def test_validate_deduplicates_ids():
    ids, _ = validate_llm_result('{"clothes_ids": [3, 3, 7]}', {3, 7})

    assert ids == [3, 7]


def test_validate_raises_when_all_ids_out_of_range():
    with pytest.raises(ValueError):
        validate_llm_result('{"clothes_ids": [999]}', {3})


def test_validate_raises_when_field_missing():
    with pytest.raises(ValueError):
        validate_llm_result('{"reason": "没有id"}', {3})


def test_validate_raises_on_unparseable_text():
    with pytest.raises(ValueError):
        validate_llm_result("抱歉，我无法推荐", {3})


def test_validate_accepts_string_ids():
    ids, _ = validate_llm_result('{"clothes_ids": ["3", "7"]}', {3, 7})

    assert ids == [3, 7]


def test_validate_returns_empty_reason_when_missing():
    ids, reason = validate_llm_result('{"clothes_ids": [3]}', {3})

    assert ids == [3]
    assert reason == ""


def test_validate_ignores_bool_elements():
    """bool 是 int 的子类，必须显式排除"""
    ids, _ = validate_llm_result('{"clothes_ids": [true, 3]}', {3})

    assert ids == [3]


# ---------- build_recommendation 编排层（monkeypatch call_chat_api） ----------

def make_full_wardrobe():
    """上衣 + 下装 + 鞋 齐全的衣柜（30°C 夏季全部适用）"""
    return [
        make_item(1, sub_category="T恤", color="蓝色"),
        make_item(2, category="裤子", sub_category="牛仔裤", color="藏青色"),
        make_item(3, category="鞋", sub_category="运动鞋", color="白色", style="运动"),
        make_item(4, sub_category="卫衣", color="灰色", style="休闲"),
    ]


class _Spy:
    """记录 call_chat_api 是否被调用；被调用即视为失败（用于「不该调 LLM」的断言）"""

    def __init__(self, monkeypatch):
        self.calls: list[tuple] = []
        monkeypatch.setattr("services.recommendation.call_chat_api", self)

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("测试预期 LLM 不被调用")


def _fake_chat(monkeypatch, result: str | Exception):
    async def fake(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("services.recommendation.call_chat_api", fake)


async def test_build_recommendation_uses_rule_when_no_api_key(monkeypatch):
    spy = _Spy(monkeypatch)

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="", model="test-model",
    )

    assert spy.calls == []  # 无 Key 时根本不调用 LLM
    assert result["source"] == "rule"
    assert len(result["items"]) == 3  # 上衣+下装+鞋
    assert result["reason"]


async def test_build_recommendation_uses_llm_ids_and_reason(monkeypatch):
    _fake_chat(monkeypatch, '{"clothes_ids": [1, 2, 3], "reason": "清爽运动风"}')

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    assert result["source"] == "llm"
    assert {it["id"] for it in result["items"]} == {1, 2, 3}
    assert result["reason"] == "清爽运动风"


async def test_build_recommendation_falls_back_on_invalid_json(monkeypatch):
    _fake_chat(monkeypatch, "抱歉，我无法推荐")

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    assert result["source"] == "rule"
    assert len(result["items"]) == 3


async def test_build_recommendation_falls_back_on_http_error(monkeypatch):
    _fake_chat(monkeypatch, httpx.ConnectError("connection failed"))

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    assert result["source"] == "rule"
    assert len(result["items"]) == 3


async def test_build_recommendation_drops_hallucinated_ids(monkeypatch):
    """个别幻觉 id 丢弃、合法 id 照用；全部幻觉才整体降级"""
    _fake_chat(monkeypatch, '{"clothes_ids": [1, 999], "reason": "r"}')

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    assert result["source"] == "llm"
    assert 999 not in {it["id"] for it in result["items"]}

    _fake_chat(monkeypatch, '{"clothes_ids": [999], "reason": "r"}')
    fallback = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="k", model="test-model",
    )
    assert fallback["source"] == "rule"


async def test_build_recommendation_completes_missing_roles(monkeypatch):
    """LLM 只给上衣 id → 规则补上其他必备角色"""
    _fake_chat(monkeypatch, '{"clothes_ids": [1], "reason": "r"}')

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    assert {it["role"] for it in result["items"]} == {"上衣", "下装", "鞋"}


async def test_build_recommendation_keeps_single_bottom(monkeypatch):
    """LLM 同时给裤子和裙子 → 只留一件下装"""
    wardrobe = [
        make_item(1),
        make_item(2, category="裤子", sub_category="牛仔裤"),
        make_item(3, category="裙子", sub_category="短裙"),
        make_item(4, category="鞋", sub_category="运动鞋"),
    ]
    _fake_chat(monkeypatch, '{"clothes_ids": [1, 2, 3, 4], "reason": "r"}')

    result = await build_recommendation(
        wardrobe, make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    bottoms = [it for it in result["items"] if it["role"] == "下装"]
    assert len(bottoms) == 1


async def test_build_recommendation_fills_template_reason_when_missing(monkeypatch):
    _fake_chat(monkeypatch, '{"clothes_ids": [1, 2, 3]}')

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30, city="上海"), "休闲",
        api_key="k", model="test-model",
    )

    assert result["source"] == "llm"
    assert "上海" in result["reason"]


async def test_build_recommendation_empty_wardrobe(monkeypatch):
    spy = _Spy(monkeypatch)

    result = await build_recommendation(
        [], make_weather(30), "休闲",
        api_key="k", model="test-model",
    )

    assert spy.calls == []  # 候选为空时不调 LLM
    assert result["items"] == []
    assert result["source"] == "rule"
    assert result["gaps"]


async def test_build_recommendation_falls_back_to_default_occasion(monkeypatch):
    spy = _Spy(monkeypatch)

    result = await build_recommendation(
        make_full_wardrobe(), make_weather(30), "蹦迪",
        api_key="", model="test-model",
    )

    assert result["source"] == "rule"
    assert len(result["items"]) == 3  # 按「休闲」处理，不抛错
