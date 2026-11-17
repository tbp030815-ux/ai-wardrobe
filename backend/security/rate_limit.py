"""
登录失败限流（进程内内存字典）

没有它，登录端点就是一个可以无限猜密码的接口。

**只记失败，绝不记成功。** 记成功的话正常用户一分钟登录几次就把自己锁死，
而且测试里 4 个 fixture 一共 67 次登录会立刻打穿窗口 —— 症状是那些测试
全部拿到 429 而不是 401，看起来像认证依赖写坏了。

两个已知边界，用之前得知道：
- **进程内**：`uvicorn --workers N` 时每进程一份计数。当前启动命令不带 `--workers`，
  单进程成立；多进程要换成 Redis 之类
- **按 IP**：dev 下走 Vite 代理，所有请求都来自 `127.0.0.1`，单用户无所谓。
  uvicorn 默认 `forwarded_allow_ips=127.0.0.1`，远端客户端伪造不了 `X-Forwarded-For`
"""
import time

MAX_FAILURES = 5
WINDOW_SECONDS = 300

_failures: dict[str, list[float]] = {}


def record_failure(key: str, *, now: float | None = None) -> None:
    moment = time.time() if now is None else now
    recent = _recent(key, moment)
    recent.append(moment)
    _failures[key] = recent


def is_locked_out(key: str, *, now: float | None = None) -> bool:
    moment = time.time() if now is None else now
    recent = _recent(key, moment)
    # 读的时候顺手写回：过期的条目在任何人访问这个 key 时被清掉，字典不会无限涨
    if recent:
        _failures[key] = recent
    else:
        _failures.pop(key, None)
    return len(recent) >= MAX_FAILURES


def reset(key: str | None = None) -> None:
    """清空计数。测试之间必须调用 —— 模块级全局状态会跨测试泄漏。"""
    if key is None:
        _failures.clear()
    else:
        _failures.pop(key, None)


def _recent(key: str, now: float) -> list[float]:
    """只保留窗口内的失败。老失败不能被新失败"续命"，否则慢慢猜也能把人锁死。"""
    cutoff = now - WINDOW_SECONDS
    return [moment for moment in _failures.get(key, []) if moment > cutoff]
