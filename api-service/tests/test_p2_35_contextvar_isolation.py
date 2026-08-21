"""P2-35 行为门：``current_execution_id`` 的测试间泄漏必须被套件级隔离兜住。

守的对象：``tests/conftest.py`` 的 ``_suite_isolate_execution_contextvar``
（autouse，每条测试后把该 ContextVar 恢复到进入时的值）。

为什么是行为门而不是静态门：``current_execution_id.set(...)`` 在测试里
既有合法形态（p1_42 在被 AuditMiddleware 包裹的模拟 downstream 里 set，
中间件自己 reset），也有泄漏形态（主线程直调生产 set 函数后不还原）——
静态判据分不开两者，会误伤；而套件级 fixture 把危害本身清零，行为门
直接断言"泄漏到不了下一条测试"这个可观察后果（CLAUDE.md ⓪④：存在性门
可被绕过，行为门不行）。

门自带泄漏源：a 制造、b 断言，同文件定义序保证 a 先跑 —— 不依赖套件里
其它文件的字母序巧合（全量、单跑本文件、任意子集顺序下判据一致）。

变异（已实跑）：把 conftest 的 ``_suite_isolate_execution_contextvar``
整个注释掉 → ``test_b_leak_from_previous_test_must_not_arrive`` 当场红，
全量顺序下 ``test_p1_36_execution_id::test_no_execution_means_default_not_empty``
也复红。fixture 改坏（set 后不 reset / reset 错 token）同样由 b 抓住。
"""

from app.core.logging_config import current_execution_id

_LEAK_SENTINEL = "p2-35-deliberate-leak"


def test_a_simulate_mainthread_leak_without_restoring():
    """坏输入制造者：复刻"主线程同步直调生产 set 函数"的泄漏形态。

    （真实案例：test_mimo_ota_report_verified_backcompat 直调
    VrtExecutionService.stop/complete → get() 内 set 不还原；
    47C 的 _execution 帮手同形态。）

    故意不 reset —— 还原正是套件级 fixture 的职责，本条测的就是它。
    """
    current_execution_id.set(_LEAK_SENTINEL)
    # 泄漏在本测试内是可见的（这是 set 的正常语义，不是被测缺陷）：
    assert current_execution_id.get("-") == _LEAK_SENTINEL


def test_b_leak_from_previous_test_must_not_arrive():
    """断言者：上一条测试制造的泄漏必须没有到达本条。

    断言的是"必须是默认干净态 ``-``"，不是"不等于哨兵" —— 这样即使
    泄漏来自别的文件（fixture 被摘掉时全量顺序里的任意上游），本门
    照样红，且红得出处可查（失败信息里会带上泄漏的值）。
    """
    leaked = current_execution_id.get("-")
    assert leaked == "-", (
        f"current_execution_id 泄漏到了下一条测试（值={leaked!r}）—— "
        "套件级隔离 fixture（tests/conftest.py 的 "
        "_suite_isolate_execution_contextvar）被摘掉或改坏了；"
        "全量顺序下 test_p1_36 的「无关日志行应为 -」也会随之失败"
    )
