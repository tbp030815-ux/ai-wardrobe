"""
衣物角色映射（品类 → 角色）

被两处复用：
- services/recommendation.py：按角色筛候选、检测缺什么
- services/tryon.py：按角色分组生成 prompt、判断「同角色多件」以拆分对比变体
- api/wardrobe.py：给每条衣物算一个 role 字段返回给前端，避免前端再复制一份映射规则

注意：这里是**品类到角色的映射**，不含「一套搭配需要哪些角色」这类造型约束
（那是 REQUIRED_ROLES，留在 recommendation.py，因为试穿没有「必须凑齐」的语义）。
"""

ROLE_TOP, ROLE_BOTTOM, ROLE_SHOES, ROLE_ACCESSORY = "上衣", "下装", "鞋", "配饰"

# 角色 → 允许的 category 取值（下装把裤子和裙子合成一个角色，二者只穿一件）
ROLE_CATEGORIES: dict[str, set[str]] = {
    ROLE_TOP: {"上衣"},
    ROLE_BOTTOM: {"裤子", "裙子"},
    ROLE_SHOES: {"鞋"},
    ROLE_ACCESSORY: {"配饰"},
}

CATEGORY_ROLE: dict[str, str] = {c: r for r, cats in ROLE_CATEGORIES.items() for c in cats}

ROLE_ORDER = (ROLE_TOP, ROLE_BOTTOM, ROLE_SHOES, ROLE_ACCESSORY)

# 用于「衣柜里还没有 X」这类缺失提示的措辞，比角色名更口语
ROLE_LABELS = {
    ROLE_TOP: "上衣",
    ROLE_BOTTOM: "裤子或裙子",
    ROLE_SHOES: "鞋",
    ROLE_ACCESSORY: "配饰",
}
