"""P2-52 —— UXM 权威测量窗口关闭边界（非现场半）的守门测试。

取证结论（docs/plans/2026-08-30-p2-52-uxm-window-boundary-evidence.md）：
NR 域 BTHRoughput 树只有 clear 边界（CLEar 手册原文 + IRAT 现场实测双证据），
无权威 stop/closed 边界，`[:STATe]?` 查询形无手册原文。据此：

- manifest lifecycle 升级 unavailable → **clear_read_only**（不升
  authoritative_closed —— IRAT 适用性未说明 + 查询形无原文两缺口都在）；
- per-window trust 的 clear 阶段按本窗口 CLEar 是否真发成逐次记账；
- STATe 查询形只进诊断探针（uxm_window_boundary_probe，零写命令），
  不进正式 MEASURE 路径。

门的形态（⓪④）：交集用**不变量门**（从两 profile registry 派生），
窗口/探针用**行为门**（造场景断言可观察后果），推断标注用存在性门粗筛
（旁边配探针行为门）。每道门的变异见同名 evidence 文档 §门与变异。
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from app.hal.base_station import ThroughputMetrics
from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILES_PATH = (
    REPO_ROOT / "api-service/app/hal/uxm_command_profiles.py"
)
_SEQUENCE_PATH = (
    REPO_ROOT
    / "api-service/app/diagnostics/sequences/uxm_window_boundary_probe.py"
)


def _driver(profile_cls) -> RealUxmDriver:
    driver = RealUxmDriver("uxm", {"ip": "192.0.2.1"})
    driver._cmds = profile_cls()
    return driver


# ─────────────────────────────────────────────────────────────────────
# 门 A（不变量）：manifest.measurement.metrics == 两 profile registry 的
# 保守交集 —— 新增 profile metric 或删除既有 metric 时本门自动红，
# 逼着 manifest 声明跟着事实走而不是靠记性。
# ─────────────────────────────────────────────────────────────────────

def test_manifest_metrics_equal_profile_registry_intersection():
    registries = [
        _driver(profile_cls).resolve_metric_registry()
        for profile_cls in (UxmLteNrIratProfile, Uxm5GNRTestAppProfile)
    ]
    common_keys = set.intersection(
        *({metric.key for metric in registry.metrics} for registry in registries)
    )
    manifest = RealUxmDriver.adapter_manifest
    assert manifest.measurement is not None
    declared = {metric.key: metric for metric in manifest.measurement.metrics}
    assert set(declared) == common_keys, (
        "manifest 交集声明与 profile registry 的实际交集漂移 —— "
        f"声明 {sorted(declared)} vs 交集 {sorted(common_keys)}"
    )
    # 逐字段：交集里每个 metric 的语义必须是两 registry 的公共值。
    for key in common_keys:
        per_profile = [
            next(metric for metric in registry.metrics if metric.key == key)
            for registry in registries
        ]
        shapes = {
            (metric.direction, metric.unit, metric.scopes, metric.evidence)
            for metric in per_profile
        }
        assert len(shapes) == 1, (
            f"metric {key} 在两个 profile 里语义不一致 {shapes} —— "
            "不构成可声明的 adapter 级交集"
        )
        declared_metric = declared[key]
        assert (
            declared_metric.direction,
            declared_metric.unit,
            declared_metric.scopes,
            declared_metric.evidence,
        ) == shapes.pop(), f"manifest 交集 metric {key} 的语义与 registry 漂移"


# ─────────────────────────────────────────────────────────────────────
# 门 B（行为）：lifecycle 契约链。
# ─────────────────────────────────────────────────────────────────────

def test_uxm_lifecycle_is_clear_read_only_and_never_authoritative_closed():
    manifest = RealUxmDriver.adapter_manifest
    assert manifest.measurement is not None
    assert manifest.measurement.lifecycle == "clear_read_only"
    # source_reference 指向 clear 边界的手册锚点（zip!member#anchor），
    # 且锚点真的在归档 HTML 里 —— 防"编一个出处"。
    source = manifest.measurement.source_reference
    assert source is not None
    archive_path, member_anchor = source.split("!", 1)
    member_name, anchor = member_anchor.split("#", 1)
    assert anchor == "scpi/bse:measure:nr5g:bthroughput:clear"
    with ZipFile(REPO_ROOT / archive_path) as manual:
        html = manual.read(member_name)
    assert f'id="{anchor}"'.encode() in html


@pytest.mark.asyncio
async def test_window_confirms_clear_stage_only_with_real_clear_exchange():
    """CLEar 真发成（write/ok/非模拟）→ clear 阶段 confirmed 且携该 exchange；
    run/ready/closed 仍 unavailable，formal 信任面零扩大。"""
    driver = _driver(UxmLteNrIratProfile)
    clear_command = UxmLteNrIratProfile.MEAS_BTHROUGHPUT_CLEAR

    async def clear_then_read(*_args, **_kwargs):
        record_exchange_intent(
            exchange_id="uxm-clear-1",
            instrument_id="uxm",
            operation="command",  # 与传输层真实 intent 同源（内审 F1）
            command=clear_command,
        )
        record_exchange_terminal(exchange_id="uxm-clear-1", result_type="ok")
        record_exchange_intent(
            exchange_id="uxm-metric-1",
            instrument_id="uxm",
            operation="query",
            command="BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:CELL1?",
        )
        record_exchange_terminal(
            exchange_id="uxm-metric-1",
            result_type="response",
            response="10.0",
        )
        return ThroughputMetrics(
            dl_throughput_mbps=10.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            kpi_valid={"dl_throughput": True},
        )

    driver.measure_throughput_window = AsyncMock(side_effect=clear_then_read)
    from tests.test_p2_48_adapter_window_truth import _request

    request = _request(lifecycle="clear_read_only", expected=3)
    window = await driver.measure_base_station_window(0.0, request=request)

    assert window.trust is not None
    stages = {stage.stage: stage for stage in window.trust.stages}
    assert stages["clear"].status == "confirmed"
    assert stages["clear"].exchange_ids == ("uxm-clear-1",)
    for stage in ("run", "ready", "closed"):
        assert stages[stage].status == "unavailable"
    assert window.preclear_off_confirmed is True
    assert window.closed_off_confirmed is False
    assert window.trust.formally_confirmed is False
    assert window.trust.diagnostic_execution_allowed is True
    assert window.confirmed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result_type", "simulated"),
    [
        ("timeout", False),   # 写没走完 —— 终态不是 ok
        ("ok", True),         # 模拟传输 —— 不是硬件证据
    ],
)
async def test_window_refuses_clear_confirmation_without_hard_evidence(
    result_type, simulated
):
    driver = _driver(UxmLteNrIratProfile)
    clear_command = UxmLteNrIratProfile.MEAS_BTHROUGHPUT_CLEAR

    async def flawed_clear(*_args, **_kwargs):
        record_exchange_intent(
            exchange_id="uxm-clear-1",
            instrument_id="uxm",
            operation="command",  # 与传输层真实 intent 同源（内审 F1）
            command=clear_command,
            simulated=simulated,
        )
        record_exchange_terminal(
            exchange_id="uxm-clear-1",
            result_type=result_type,
            simulated=simulated,
        )
        return ThroughputMetrics(
            dl_throughput_mbps=10.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            kpi_valid={"dl_throughput": True},
        )

    driver.measure_throughput_window = AsyncMock(side_effect=flawed_clear)
    from tests.test_p2_48_adapter_window_truth import _request

    request = _request(lifecycle="clear_read_only", expected=3)
    window = await driver.measure_base_station_window(0.0, request=request)

    assert window.trust is not None
    stages = {stage.stage: stage.status for stage in window.trust.stages}
    assert stages["clear"] == "unavailable"
    assert window.preclear_off_confirmed is False


# ─────────────────────────────────────────────────────────────────────
# 门 C（行为 + 存在性粗筛）：STATe 查询形只进诊断探针，探针零写命令。
# ─────────────────────────────────────────────────────────────────────

class _FakeUxmDriver:
    """类名不以 Mock 开头 → 序列的 mock 拒绝门放行（按既有名字判据）。"""

    def __init__(self, profile, responses):
        self._cmds = profile
        self._responses = responses  # command -> list[str] | Exception
        self.queries: list[str] = []
        self.writes: list[str] = []

    def _query(self, cmd: str) -> str:
        self.queries.append(cmd)
        entry = self._responses.get(cmd)
        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry, list):
            return entry.pop(0) if entry else '0,"No error"'
        return entry if entry is not None else '0,"No error"'

    def _write(self, cmd: str) -> None:
        self.writes.append(cmd)


class _FakeHal:
    def __init__(self, driver):
        self.drivers = {"baseStation": driver}


async def _run_probe(driver):
    from app.diagnostics.sequences import uxm_window_boundary_probe as probe

    return await probe.run(
        None, _FakeHal(driver), {}, log=lambda _msg: None
    )


@pytest.mark.asyncio
async def test_probe_reads_state_without_any_write_command():
    query_cmd = UxmLteNrIratProfile.MEAS_BTHROUGHPUT_STATE_QUERY
    driver = _FakeUxmDriver(
        UxmLteNrIratProfile(),
        {query_cmd: "1", "SYSTem:ERRor?": '0,"No error"'},
    )
    result = await _run_probe(driver)

    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["state_query_supported"] is True
    assert result.extra["bthroughput_state"] == "1"
    # 剧本核心：读到 ON 也不动 —— 全程零写命令（连 *CLS 都不发）。
    assert driver.writes == []
    assert all(
        cmd in {query_cmd, "SYSTem:ERRor?"} for cmd in driver.queries
    )


@pytest.mark.asyncio
async def test_probe_records_rejected_inferred_query_as_an_answer():
    query_cmd = UxmLteNrIratProfile.MEAS_BTHROUGHPUT_STATE_QUERY
    driver = _FakeUxmDriver(
        UxmLteNrIratProfile(),
        {
            query_cmd: TimeoutError("no reply"),
            "SYSTem:ERRor?": [
                '0,"No error"',                    # 预排水
                '-113,"Undefined header"',         # STATe? 后归属
                '0,"No error"',                    # 归属排水收口
                '0,"No error"',                    # 收尾排水
            ],
        },
    )
    result = await _run_probe(driver)

    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["state_query_supported"] is False
    assert result.extra["bthroughput_state"] is None
    assert driver.writes == []


@pytest.mark.asyncio
async def test_probe_aborts_on_profile_without_inferred_query_definition():
    """5G_NR_Test 方言未定义推断查询形（BSE 树认不认未经查证）→ 拒跑，
    STATe? 一条都不发。"""
    driver = _FakeUxmDriver(Uxm5GNRTestAppProfile(), {})
    result = await _run_probe(driver)

    assert result.extra["verdict"] == "ABORTED"
    assert driver.queries == []
    assert driver.writes == []


def test_inferred_state_query_is_probe_only_and_labelled():
    """存在性粗筛（行为门在上面三条）：

    ① IRAT 定义了显式查询形、5G_NR_Test/基类保持 None（禁盲试）；
    ② 定义处带「推断」标注 + 手册锚点；
    ③ 查询形与 STATe 写形都不进正式 MEASURE 窗口路径 —— 唯一消费方是
      诊断探针（_enable_kpi_measurements 的 STATe ON 属 attach 前置，
      不在窗口路径里）。
    """
    assert (
        UxmLteNrIratProfile.MEAS_BTHROUGHPUT_STATE_QUERY
        == "BSE:MEASure:NR5G:BTHRoughput:STATe?"
    )
    assert Uxm5GNRTestAppProfile.MEAS_BTHROUGHPUT_STATE_QUERY is None

    profile_src = _PROFILES_PATH.read_text(encoding="utf-8")
    irat_definition = re.search(
        r"((?:[ \t]*#[^\n]*\n)+)[ \t]*MEAS_BTHROUGHPUT_STATE_QUERY = ",
        profile_src,
    )
    assert irat_definition is not None, "IRAT 的查询形定义必须带注释块"
    assert "推断" in irat_definition.group(1), (
        "查询形定义处必须显式标注「推断」（方括号展开 + 查询形无手册原文）"
    )

    # 正式 MEASURE 窗口路径不引用 STATe（写形或查询形）。
    window_src = inspect.getsource(RealUxmDriver.measure_base_station_window)
    window_src += inspect.getsource(RealUxmDriver.measure_throughput_window)
    assert "MEAS_BTHROUGHPUT_STATE" not in window_src

    # 全仓消费方：查询形只被诊断探针读取。
    consumers = set()
    for path in (REPO_ROOT / "api-service/app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "MEAS_BTHROUGHPUT_STATE_QUERY" in text:
            consumers.add(path.name)
    assert consumers == {
        "uxm_command_profiles.py",
        "uxm_window_boundary_probe.py",
    }, f"STATe 查询形出现了未审的消费方: {sorted(consumers)}"


@pytest.mark.asyncio
async def test_clear_accounting_survives_real_transport_template_path():
    """内审 F1 的成因门：clear 记账的过滤 token 必须与**真实传输模板路径**
    记录的 intent 同源——本门不手工记 exchange，只 stub 最底层
    _do_write/_do_query，让 CLEar 走 base.py 的真实写模板。首版
    fake 手工记 operation="write" 曾 pin 住错误契约（生产 intent 是
    "command"），过滤条件在生产/测试两侧的正命中集合都是空集。"""
    driver = _driver(UxmLteNrIratProfile)
    driver._visa_session = object()
    written: list[str] = []
    driver._do_write = lambda cmd: written.append(cmd)
    driver._do_query = lambda cmd: "0"

    async def read_metrics(*_a, **_k):
        # 真实路径里 CLEar 由 measure_throughput_window 经 self._write 发出；
        # 这里复刻该次序（真模板写 → 读值）
        driver._write(UxmLteNrIratProfile.MEAS_BTHROUGHPUT_CLEAR)
        return ThroughputMetrics(
            dl_throughput_mbps=10.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            kpi_valid={"dl_throughput": True},
        )

    driver.measure_throughput_window = AsyncMock(side_effect=read_metrics)
    from tests.test_p2_48_adapter_window_truth import _request

    request = _request(lifecycle="clear_read_only", expected=3)
    window = await driver.measure_base_station_window(0.0, request=request)

    assert UxmLteNrIratProfile.MEAS_BTHROUGHPUT_CLEAR in written
    stages = {stage.stage: stage for stage in window.trust.stages}
    assert stages["clear"].status == "confirmed", (
        f"真实传输模板路径下 clear 未 confirmed：{stages['clear'].reason}"
    )
    assert stages["clear"].exchange_ids, "confirmed 必须携真实 exchange id"


@pytest.mark.asyncio
async def test_probe_aborts_when_drain_hits_cap_instead_of_misattributing():
    """内审 F2：预排水撞上限（cap 内未见 0）= 队列未清空——探针必须
    ABORTED 不发 STATe?，不许把 stale 残留归属成「查询形被拒」的
    反向假结论。把撞 cap 当可判本门要红。"""
    query_cmd = UxmLteNrIratProfile.MEAS_BTHROUGHPUT_STATE_QUERY

    class _NeverEmptyQueue(_FakeUxmDriver):
        def _query(self, cmd: str) -> str:
            if cmd == "SYSTem:ERRor?":
                self.queries.append(cmd)
                return '-350,"Queue overflow (stale)"'
            return super()._query(cmd)

    driver = _NeverEmptyQueue(UxmLteNrIratProfile(), {query_cmd: "1"})
    result = await _run_probe(driver)

    assert result.extra["verdict"] == "ABORTED", result.extra
    assert result.extra["state_query_supported"] is None
    assert query_cmd not in driver.queries, "撞 cap 后不许再发 STATe?"
