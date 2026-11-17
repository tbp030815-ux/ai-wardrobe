"""
登录失败限流

没有它，登录端点就是一个可以无限猜密码的接口。按客户端 IP 记**失败次数**，
窗口内超过阈值就锁住。

**只记失败，绝不记成功** —— 记成功的话正常用户一分钟登录几次就把自己锁死了，
而且测试里那 67 次 fixture 登录会立刻打穿窗口。

`now` 是注入的：窗口滑动的测试不该靠 sleep。
"""
from security.rate_limit import MAX_FAILURES, WINDOW_SECONDS, is_locked_out, record_failure, reset

IP = "127.0.0.1"
NOW = 1_700_000_000.0


def test_nothing_is_locked_out_to_begin_with():
    assert is_locked_out(IP, now=NOW) is False


def test_stays_open_just_below_the_threshold():
    for _ in range(MAX_FAILURES - 1):
        record_failure(IP, now=NOW)

    assert is_locked_out(IP, now=NOW) is False


def test_locks_out_once_the_threshold_is_reached():
    for _ in range(MAX_FAILURES):
        record_failure(IP, now=NOW)

    assert is_locked_out(IP, now=NOW) is True


def test_one_ip_being_locked_out_does_not_lock_out_another():
    """同一台机器上另一个浏览器窗口不该被牵连"""
    for _ in range(MAX_FAILURES):
        record_failure(IP, now=NOW)

    assert is_locked_out("10.0.0.9", now=NOW) is False


def test_failures_fall_out_of_the_window():
    """锁是暂时的：窗口滑过去就该自动放开，不需要重启服务"""
    for _ in range(MAX_FAILURES):
        record_failure(IP, now=NOW)
    assert is_locked_out(IP, now=NOW) is True

    assert is_locked_out(IP, now=NOW + WINDOW_SECONDS) is False


def test_only_failures_inside_the_window_count():
    """老失败不能被新失败"续命" —— 否则慢慢猜也能把人锁死"""
    for _ in range(MAX_FAILURES - 1):
        record_failure(IP, now=NOW)

    older = NOW + WINDOW_SECONDS
    record_failure(IP, now=older)

    assert is_locked_out(IP, now=older) is False


def test_reset_clears_one_key():
    for _ in range(MAX_FAILURES):
        record_failure(IP, now=NOW)

    reset(IP)

    assert is_locked_out(IP, now=NOW) is False


def test_reset_clears_everything():
    for _ in range(MAX_FAILURES):
        record_failure(IP, now=NOW)
        record_failure("10.0.0.9", now=NOW)

    reset()

    assert is_locked_out(IP, now=NOW) is False
    assert is_locked_out("10.0.0.9", now=NOW) is False
