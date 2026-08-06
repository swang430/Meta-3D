"""P1-41 门：UXM 错误查询自身被拒时不得自增殖刷满磁盘。

事故形态是 ``SYSTem:ERRor?`` 每问一次都返回同一条
``-113,"Undefined header"``。如果查询本身不受当前 Test App 支持，
每次查询又会制造下一条 -113；以“直到队列为空”为终止条件永远停不下来。

NotebookLM 对厂商手册的核对结论（2026-08-06）：手册只明确完整形式
``SYSTem:ERRor[:NEXT]?``、弹出最旧错误、空队列回 ``+0,"No error"``；
没有明确保证该命令适用于 5G_NR_Test / LTE_NR_IRAT，也没有定义查询自身
返回 -113 时的终止语义。因此这里只做安全判定，不猜另一条命令。
"""
from __future__ import annotations

import asyncio

import pytest

from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import UxmLteNrIratProfile
from tests.test_p02_uxm_truth_source import _echo_session_for_config


_UNDEFINED = '-113,"Undefined header"'


def _driver() -> RealUxmDriver:
    driver = RealUxmDriver(
        "uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"}
    )
    driver._cmds = UxmLteNrIratProfile()
    return driver


def test_repeated_undefined_header_stops_after_two_queries():
    """变异：删掉“连续两条相同 -113”判据，旧上界会读满 16 次。"""
    driver = _driver()
    queries: list[str] = []

    def _query(cmd: str) -> str:
        queries.append(cmd)
        return _UNDEFINED

    driver._do_query = _query  # type: ignore[method-assign]

    errors = driver._drain_errors()

    assert queries == [driver._cmds.ERR, driver._cmds.ERR]
    assert errors[:2] == [_UNDEFINED, _UNDEFINED]
    assert any("疑似不受支持" in item for item in errors)


def test_real_stale_undefined_header_then_clean_is_not_misclassified():
    """反向门：一条历史 -113 后回 clean，是正常可排空队列，不得恒判不可用。"""
    driver = _driver()
    replies = iter([_UNDEFINED, '+0,"No error"'])
    queries: list[str] = []

    def _query(cmd: str) -> str:
        queries.append(cmd)
        return next(replies)

    driver._do_query = _query  # type: ignore[method-assign]

    assert driver._drain_errors() == [_UNDEFINED]
    assert queries == [driver._cmds.ERR, driver._cmds.ERR]


def test_malformed_error_reply_stops_after_one_query_and_is_not_clean():
    """非错误码回复既不能当 clean，也不应为同一不可解析形态重复刷 16 次。"""
    driver = _driver()
    queries: list[str] = []

    def _query(cmd: str) -> str:
        queries.append(cmd)
        return "<garbled>"

    driver._do_query = _query  # type: ignore[method-assign]

    errors = driver._drain_errors()

    assert queries == [driver._cmds.ERR]
    assert errors[0] == "<garbled>"
    assert any("不可解析" in item for item in errors)


@pytest.mark.parametrize("limit", [0, 1])
def test_limit_exhaustion_is_unusable_even_at_small_limits(limit: int):
    """内审 F1：上限耗尽意味着无法证明队列已净，不能继续业务流程。"""
    driver = _driver()
    queries: list[str] = []

    def _query(cmd: str) -> str:
        queries.append(cmd)
        return '-221,"Settings conflict"'

    driver._do_query = _query  # type: ignore[method-assign]

    errors = driver._drain_errors(limit=limit)

    assert len(queries) == limit
    assert errors[-1].startswith("<队列未排空:")
    assert driver._error_queue_unusable(errors) is True


def test_mac_configuration_aborts_without_writes_when_default_limit_is_exhausted():
    """16 条各不相同的真错误也不能绕过“连续相同 -113”分支继续下发。"""
    driver = _driver()
    queries: list[str] = []
    writes: list[str] = []
    error_index = 0

    async def _enable(_cell: str) -> None:
        return None

    def _query(cmd: str) -> str:
        nonlocal error_index
        queries.append(cmd)
        if cmd == driver._cmds.ERR:
            error_index += 1
            return f'-2{error_index:02d},"distinct error {error_index}"'
        return "1"

    driver._enable_kpi_measurements = _enable  # type: ignore[method-assign]
    driver._do_query = _query  # type: ignore[method-assign]
    driver._do_write = writes.append  # type: ignore[method-assign]

    result = asyncio.run(driver.configure_mac_throughput_test(scs_khz=15))

    assert len([q for q in queries if q == driver._cmds.ERR]) == 16
    assert writes == []
    assert result.ok is False
    assert result.error is not None and "队列未排空" in result.error


def test_mac_configuration_aborts_before_business_writes_when_err_query_self_replenishes():
    """错误门本身不可判定时，当前 MAC 流程应立刻失败，不再逐组重复查询/下发。"""
    driver = _driver()
    queries: list[str] = []
    writes: list[str] = []

    async def _enable(_cell: str) -> None:
        return None

    def _query(cmd: str) -> str:
        queries.append(cmd)
        return _UNDEFINED if cmd == driver._cmds.ERR else "1"

    driver._enable_kpi_measurements = _enable  # type: ignore[method-assign]
    driver._do_query = _query  # type: ignore[method-assign]
    driver._do_write = writes.append  # type: ignore[method-assign]

    result = asyncio.run(driver.configure_mac_throughput_test(scs_khz=15))

    assert queries == [driver._cmds.ERR, driver._cmds.ERR]
    assert writes == []
    assert result.ok is False
    assert result.error is not None and "错误查询疑似不受支持" in result.error


def test_mac_configuration_aborts_at_first_group_when_err_query_turns_self_replenishing():
    """反向时序：基线 clean 也不能让首组后的自增殖一路扩散到后续组。"""
    driver = _driver()
    err_replies = iter(['+0,"No error"', _UNDEFINED, _UNDEFINED])
    queries: list[str] = []
    writes: list[str] = []

    async def _enable(_cell: str) -> None:
        return None

    def _query(cmd: str) -> str:
        queries.append(cmd)
        if cmd == driver._cmds.ERR:
            return next(err_replies)
        if "NUM:PRBS" in cmd:
            return "273"
        return "1"

    driver._enable_kpi_measurements = _enable  # type: ignore[method-assign]
    driver._do_query = _query  # type: ignore[method-assign]
    driver._do_write = writes.append  # type: ignore[method-assign]

    result = asyncio.run(driver.configure_mac_throughput_test(scs_khz=15))

    assert [q for q in queries if q == driver._cmds.ERR] == [
        driver._cmds.ERR,
        driver._cmds.ERR,
        driver._cmds.ERR,
    ]
    assert any("QCONFig" in cmd for cmd in writes), "首组业务写应已发生"
    assert not any("RRESource:APOLicy" in cmd for cmd in writes), (
        "错误查询自增殖后仍继续下发 AMC"
    )
    assert result.ok is False
    assert result.error is not None and "错误查询疑似不受支持" in result.error


@pytest.mark.asyncio
async def test_apply_uses_profile_error_command_and_stops_after_two_queries():
    """APPLY 后的独立硬编码循环也属于同一爆炸面，必须走统一安全读取。"""
    driver = _driver()
    session = _echo_session_for_config(active_state="1", status_reply="ON")
    original_query = session.query

    def _query(cmd: str) -> str:
        if "ERR" in cmd.upper():
            session.queried.append(cmd.strip())
            return _UNDEFINED
        return original_query(cmd)

    session.query = _query  # type: ignore[method-assign]
    driver._visa_session = session

    ok = await driver.set_cell_config({"dl_power_dbm": -46.0})

    err_queries = [q for q in session.queried if "ERR" in q.upper()]
    assert ok is False
    assert err_queries == [driver._cmds.ERR, driver._cmds.ERR]
