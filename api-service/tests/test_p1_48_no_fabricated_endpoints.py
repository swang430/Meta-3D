"""P1-48：那四条整体返回随机数的接口不许回来。

它们相似度、趋势、置信度全是 `np.random` 现编的，而且连传进去的报告 ID
存不存在都不查 —— 当时的测试就是传随机 UUID 断言返回 200。
一份看不出是编的对比结论，比没有这个功能危险得多。
"""
from __future__ import annotations

from app.main import app
from tests.test_rule_gates import _expand_app_routes

_DELETED = {
    "/api/v1/reports/compare",
    "/api/v1/reports/statistics/compare",
    "/api/v1/reports/statistics/benchmark",
    "/api/v1/reports/statistics/time-series",
}


def test_fabricated_endpoints_stay_deleted():
    """那四条不许以任何形式回到路由表里。

    ⚠️ `_expand_app_routes` 返回的是 **(动词, 路径) 元组**，必须先投影成路径集合 ——
    直接拿元组跟字符串求交，两边永远不相等，门会恒绿
    （设计阶段就是在这里差点又造一个假门）。

    让它报错的改法：把任一条路由的装饰器加回来，哪怕函数体只写 `raise`。
    """
    # ⚠️ 它收的是**路由列表**不是 app 对象（第一版传错，当场 TypeError）
    live_paths = {path for _verb, path in _expand_app_routes(app.routes)}

    # 自检：投影出来的必须是字符串，且路由表不能是空的 ——
    # 否则「交集为空」这个结论可能只是因为我根本没取到路由
    assert live_paths, "路由表是空的，本门的结论不可信"
    assert all(isinstance(p, str) for p in live_paths), (
        "投影出来的不是字符串 —— _expand_app_routes 的返回形状变了，请更新本门"
    )
    assert "/api/v1/reports" in live_paths, (
        "连 /api/v1/reports 都取不到，说明取数方式有问题，本门的结论不可信"
    )

    back = _DELETED & live_paths
    assert not back, (
        f"这些整体返回随机数的接口又回到路由表里了：{sorted(back)} —— "
        f"它们的返回值是编的，且不校验报告是否存在"
    )


def test_the_fabricating_statistics_service_is_gone():
    """那个整体编数的统计服务不许回来。

    让它报错的改法：把 `app/services/statistics_service.py` 加回来。
    """
    import importlib

    try:
        importlib.import_module("app.services.statistics_service")
    except ModuleNotFoundError:
        return
    raise AssertionError(
        "app/services/statistics_service.py 又回来了 —— "
        "它的 compare_reports / analyze_time_series 用 np.random 现编数值"
    )
