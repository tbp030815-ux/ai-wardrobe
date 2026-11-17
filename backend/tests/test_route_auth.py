"""
路由鉴权的元测试与行为测试

这组测试守的是**覆盖面**，不是某一条端点的业务逻辑：新增一个 router、
或者不小心把 `Depends(current_user_id)` 从哪个端点上删掉，这里必须红。

注意：FastAPI 0.141 的 `app.routes` 里，`include_router()` 注册的是
`_IncludedRouter` 而不是展开后的 `APIRoute`。直接遍历只能看到 `/` 和
`/health`，所以必须递归下钻，否则元测试等于没测。
"""
import pytest
from fastapi.routing import APIRoute

from api.auth import current_user_id
from main import app
from tests.conftest import make_client

# 这些端点必须保持公开：登录页要能先问「配置没配置密码」，退出要能在会话
# 过期后照样清理状态；`/` 和 `/health` 是探活与首页提示。
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
}


def iter_api_routes(routes):
    """递归展开 include_router 产生的 _IncludedRouter"""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue

        nested = getattr(route, "routes", None)
        if nested is None:
            original = getattr(route, "original_router", None)
            nested = getattr(original, "routes", None) if original is not None else None
        if nested:
            yield from iter_api_routes(nested)


def iter_dependants(dependant):
    yield dependant
    for child in dependant.dependencies:
        yield from iter_dependants(child)


def requires_auth(route: APIRoute) -> bool:
    return any(
        dependant.call is current_user_id
        for dependant in iter_dependants(route.dependant)
    )


@pytest.fixture
def anonymous_client(tmp_path):
    """没有 cookie 的客户端；登录后能拿到的 session 这里刻意不拿"""
    with make_client(tmp_path) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------- 行为：未登录一律 401 ----------

# 请求体刻意选成「任何一步都不会触发付费调用或外网请求」：
# 空文件在读字节阶段就 400，空衣柜在查库阶段就 404，空城市在天气调用前就 400。
# FastAPI 先解决依赖再校验请求体，所以加鉴权后这些都会先撞上 401。
@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/wardrobe", {}),
        ("get", "/api/clothes/1", {}),
        ("delete", "/api/clothes/1", {}),
        ("post", "/api/upload", {"files": {"file": ("a.png", b"", "image/png")}}),
        ("get", "/api/recommendation", {"params": {"location": "   "}}),
        ("post", "/api/model", {"files": {"file": ("m.jpg", b"", "image/jpeg")}}),
        ("get", "/api/models", {}),
        ("put", "/api/models/1/default", {}),
        ("delete", "/api/models/1", {}),
        ("post", "/api/tryon", {"json": {"clothes_ids": [1]}}),
        ("get", "/api/outfits", {}),
        ("delete", "/api/outfits/1", {}),
    ],
)
def test_business_routes_reject_requests_without_a_session(
    anonymous_client, method, path, kwargs
):
    response = getattr(anonymous_client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_business_route_accepts_a_valid_session(anonymous_client):
    from tests.conftest import login

    assert login(anonymous_client).status_code == 200
    assert anonymous_client.get("/api/wardrobe").status_code == 200


# ---------- 元测试：每条路由要么公开、要么受保护 ----------

def test_every_api_route_is_explicitly_public_or_protected():
    routes = list(iter_api_routes(app.routes))
    seen = {route.path for route in routes}

    # 先证明收集器真的展开了 include_router：漏掉 /api/auth/* 说明只看到了 / 和 /health
    assert PUBLIC_PATHS <= seen

    unprotected = sorted(
        {
            route.path
            for route in routes
            if route.path not in PUBLIC_PATHS and not requires_auth(route)
        }
    )
    assert unprotected == []

    overprotected = sorted(
        {
            route.path
            for route in routes
            if route.path in PUBLIC_PATHS and requires_auth(route)
        }
    )
    assert overprotected == []


def test_no_api_route_declares_a_user_id_query_parameter():
    """身份只能来自签过名的 cookie，查询参数里的 user_id 等于洞还开着"""
    offenders = []

    for route in iter_api_routes(app.routes):
        for dependant in iter_dependants(route.dependant):
            for param in dependant.query_params:
                names = {getattr(param, "name", None), getattr(param, "alias", None)}
                if "user_id" in names:
                    offenders.append(route.path)

    assert sorted(set(offenders)) == []
