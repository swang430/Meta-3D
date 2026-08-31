"""P1-74（非现场半）：CMW500 Extended BLER 统计基必须由 execution 冻结并回读确认。

**唯一要修的可观察故障**：TestCase 的 ``stat_count`` 只被换算成 sleep 秒数
（``measure.py`` 的 ``window_s``），``CONFigure:LTE:SIGN<i>:EBLer:SFRames``
全仓零下发 —— 统计基继承仪器保留的旧值（``*RST`` 是 10E+3，上一 session 可能是
任意值）。「睡够时间」不等于「统计够子帧」，于是两次同参执行的置信区间不同，
正式 KPI 不可重复，而报告里看不出差别。

手册取证（CMW500 无 NotebookLM，本地 PDF 为权威源；逐条页码见
``docs/plans/2026-08-31-p1-74-cmw500-ebler-subframes-design.md`` §2）：
  · 命令形式 / 参数域 ``100 to 400E+3`` / ``*RST 10E+3`` / 最低固件 V3.0.30 —— printed p.953
  · 无 stop condition（正式窗口即 ``SCONdition NONE``）时 SFRames =
    每 measurement cycle 处理的子帧数 —— printed p.938、§3.3.1 示例 p.940
  · 「只影响 trace 长度」那句**限定于 confidence 模式**，不适用于本片的
    continuous 正式窗口 —— printed p.938 / p.953
"""

from __future__ import annotations

from collections import deque
from unittest.mock import patch

import pytest

from app.hal.base_station import (
    BaseStationMeasurementWindowRequest,
    ThroughputMetrics,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.cmw500_command_profile import (
    CMW500_LTE_COMMANDS,
    EBLER_SUBFRAMES_MAX,
    EBLER_SUBFRAMES_MIN,
    EBLER_SUBFRAMES_RESET,
    Cmw500LteCommandProfile,
)
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    capture_scpi_exchanges,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    BaseStationMeasurementWindowRequestEvidence,
    canonical_snapshot_digest,
)
from app.services.mimo_ota.executors.measure import MeasureExecutor


ABSOLUTE = "0,900,100,1000,123456.5,120000,125000,0,1000,15"
RELATIVE = "0,99.5,0.5,0.5,87.25,0"
STATE_QUERY = "FETCh:LTE:SIGN1:EBLer:STATe?"
SFRAMES_QUERY = "CONFigure:LTE:SIGN1:EBLer:SFRames?"


def _sframes_write(subframes: int) -> str:
    return f"CONFigure:LTE:SIGN1:EBLer:SFRames {subframes}"


def _window_request(
    *,
    scope: str = "pcell",
    statistical_basis_subframes: int | None = 5000,
) -> BaseStationMeasurementWindowRequest:
    return BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope=scope,
        lifecycle="authoritative_closed",
        cardinality="single",
        requested_window_count=1,
        expected_window_count=1,
        window_index=0,
        statistical_basis_subframes=statistical_basis_subframes,
    )


class _WindowDriver(RealCmw500Driver):
    """真实 CMW 驱动 + 可控传输层（不模拟：``simulated`` 仍为 False）。"""

    def __init__(
        self,
        *,
        states: list[str],
        subframes_readback: int | str | Exception = 5000,
        error_after: dict[str, str] | None = None,
        absolute: str | Exception = ABSOLUTE,
        relative: str | Exception = RELATIVE,
    ) -> None:
        super().__init__("cmw-window", {"ip_address": "192.0.2.10"})
        self._visa_session = object()
        self.states = deque(states)
        self.subframes_readback = subframes_readback
        # 写命令 → 紧随其后的 SYSTem:ERRor:ALL? 应答（缺省即空队列）
        self.error_after = dict(error_after or {})
        self.absolute = absolute
        self.relative = relative
        self.writes: list[str] = []
        self.queries: list[str] = []
        self._last_write: str | None = None

    def _do_write(self, command: str) -> None:
        self.writes.append(command)
        self._last_write = command

    def _do_query(self, command: str) -> str:
        self.queries.append(command)
        if command == STATE_QUERY:
            return self.states.popleft()
        if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
            return "ON,ADJ"
        if command == "FETCh:LTE:SIGN1:PSWitched:STATe?":
            return "CEST"
        if command == "SYSTem:ERRor:ALL?":
            return self.error_after.get(self._last_write or "", '0,"No error"')
        if command == "*OPC?":
            return "1"
        if command == SFRAMES_QUERY:
            if isinstance(self.subframes_readback, Exception):
                raise self.subframes_readback
            return str(self.subframes_readback)
        if command == "FETCh:LTE:SIGN1:EBLer:PCC:ABSolute?":
            if isinstance(self.absolute, Exception):
                raise self.absolute
            return self.absolute
        if command == "FETCh:LTE:SIGN1:EBLer:PCC:RELative?":
            if isinstance(self.relative, Exception):
                raise self.relative
            return self.relative
        raise AssertionError(f"unexpected query: {command}")


async def _no_sleep(_seconds: float) -> None:
    return None


def _statistical_basis(window) -> dict:
    """窗口证据里的统计基三态（requested / applied / confirmed）。"""

    items = [
        item
        for item in window.evidence
        if item.evidence_key == "cmw500.extended_bler.statistical_basis"
    ]
    assert len(items) == 1, "统计基必须恰好有一条独立证据项"
    return {"item": items[0], **items[0].readback}


# ===========================================================================
# A. 命令 profile：手册出处、参数域、回读解析
# ===========================================================================


def test_subframes_spec_is_registered_with_manual_source_and_firmware():
    setter = CMW500_LTE_COMMANDS["ebler_subframes"]
    query = CMW500_LTE_COMMANDS["ebler_subframes_query"]

    assert setter.template == "CONFigure:LTE:SIGN{i}:EBLer:SFRames"
    assert query.template == "CONFigure:LTE:SIGN{i}:EBLer:SFRames?"
    for spec in (setter, query):
        assert "1173.9628.02-41" in spec.source_reference
        assert "printed p." in spec.source_reference
        assert spec.purpose
        # p.953：最低固件 V3.0.30；定义块无 Options 行 → 无选件要求
        assert spec.minimum_firmware == "V3.0.30"
        assert spec.required_options == ()
    # p.953 的参数域与复位值就是判据本身，必须来自 profile 而不是散落字面量
    assert (EBLER_SUBFRAMES_MIN, EBLER_SUBFRAMES_MAX) == (100, 400_000)
    assert EBLER_SUBFRAMES_RESET == 10_000


def test_setter_and_query_builders_match_the_manual_command_form():
    assert Cmw500LteCommandProfile.build_ebler_subframes(1, 5000) == (
        "CONFigure:LTE:SIGN1:EBLer:SFRames 5000"
    )
    assert Cmw500LteCommandProfile.ebler_subframes_query(2) == (
        "CONFigure:LTE:SIGN2:EBLer:SFRames?"
    )


@pytest.mark.parametrize("subframes", [100, 400_000, 5000, 10_000])
def test_documented_range_endpoints_are_accepted(subframes):
    assert Cmw500LteCommandProfile.build_ebler_subframes(1, subframes) == (
        f"CONFigure:LTE:SIGN1:EBLer:SFRames {subframes}"
    )


@pytest.mark.parametrize(
    "subframes",
    [99, 0, -1, 400_001, 1_000_000, True, False, 5000.0, "5000", None],
)
def test_out_of_domain_requests_are_rejected_never_clamped(subframes):
    """越界一律 fail-loud —— clamp 会静默换成另一个统计基，正是本片要消灭的形态。"""

    with pytest.raises((TypeError, ValueError)):
        Cmw500LteCommandProfile.build_ebler_subframes(1, subframes)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("5000", 5000),
        ("+5000", 5000),
        ("  400000  ", 400_000),
        ("100", 100),
        # 外审 R3：docstring 声称接受 `5.0E+03` 这类科学计数形态，此前却无用例
        # 守着 —— 「声称 X 但无门」。SCPI 仪器回读常用指数形式，现场半在真机上
        # 才发现解析不了会直接 fail-closed 掉整个窗口。
        ("5.0E+03", 5000),
        ("4.00000E+05", 400_000),
        ("1.0E+02", 100),
        ("5.5E+03", 5500),
    ],
)
def test_readback_parser_accepts_documented_forms(response, expected):
    assert Cmw500LteCommandProfile.parse_ebler_subframes(response) == expected


@pytest.mark.parametrize(
    "response",
    [
        "99", "400001", "5000.5", "NAV", "", "  ", "5000,1", "ON",
        # 外审 R3：科学计数形态同样要走域校验与整数校验，不能因为「长得像
        # 合法数字」就放行。9.9E+01 = 99（越界）、5.0005E+03 = 5000.5（非整数）。
        "9.9E+01", "5.0005E+03", "4.00001E+05",
    ],
)
def test_readback_parser_rejects_undocumented_forms(response):
    with pytest.raises(ValueError):
        Cmw500LteCommandProfile.parse_ebler_subframes(response)


# ===========================================================================
# B. execution-frozen 请求：新槽位 + 历史 digest 不变
# ===========================================================================


def test_request_carries_the_execution_frozen_statistical_basis():
    request = _window_request(statistical_basis_subframes=5000)

    assert request.statistical_basis_subframes == 5000
    legacy = _window_request(statistical_basis_subframes=None)
    assert legacy.statistical_basis_subframes is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, TypeError), (False, TypeError), (5000.0, TypeError),
     ("5000", TypeError), (0, ValueError), (-1, ValueError)],
)
def test_request_raises_the_documented_exception_kind(value, expected):
    """外审 R1：类型不符 → TypeError，值越界 → ValueError。

    此前三个校验点（请求 / 持久化 / 执行器）分别抛 TypeError / ValueError /
    TypeError —— 同一个字段三种行为，调用方按其中一种捕获就会漏掉另一种。
    下面那条用 (TypeError, ValueError) 元组的旧断言抓不到这种不一致，保留它
    作为「拒绝」的粗筛，由本条负责钉住异常种类。
    """

    with pytest.raises(expected):
        _window_request(statistical_basis_subframes=value)


@pytest.mark.parametrize("value", [0, -1, True, False, 5000.0, "5000"])
def test_request_rejects_a_non_positive_or_non_integer_statistical_basis(value):
    with pytest.raises((TypeError, ValueError)):
        _window_request(statistical_basis_subframes=value)


def test_statistical_basis_changes_the_frozen_request_digest():
    assert (
        _window_request(statistical_basis_subframes=5000).digest
        != _window_request(statistical_basis_subframes=4000).digest
    )


def test_legacy_request_digest_is_byte_for_byte_unchanged():
    """历史读取路径：没有统计基的旧请求 digest 必须与新增字段前完全一致。

    这两个值是 P1-74 改动**前**在本仓实跑取得的。digest 变了 = 历史
    ``base_station_execution_evidence`` 里的 ``request_digest`` 全部失配，
    旧 execution 的证据再也读不出来。
    """

    legacy_pcell = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="pcell",
        lifecycle="authoritative_closed",
        cardinality="single",
        requested_window_count=5,
        expected_window_count=1,
        window_index=0,
    )
    legacy_all_cells = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="all_cells",
        lifecycle="clear_read_only",
        cardinality="requested",
        requested_window_count=3,
        expected_window_count=3,
        window_index=2,
    )

    assert legacy_pcell.statistical_basis_subframes is None
    assert legacy_pcell.digest == (
        "d9c63dc240594fa4bcf582117fa5928d0bb51afc12cf4a9a447f9ee9e579b880"
    )
    assert legacy_all_cells.digest == (
        "0dc0932cccf3e7358c8c0760f2132761e24d0ca5a57483c6d50d8b5f43be61e9"
    )


@pytest.mark.parametrize("basis", [None, 5000])
def test_hal_and_persisted_request_digests_agree(basis):
    """不变量：HAL 冻结请求与持久化证据模型必须算出同一个 digest。

    ``BaseStationMeasurementWindowTrustEvidence`` 用
    ``request_digest != request.digest`` 当门；两侧 canonical 形态一旦漂移，
    新写进去的证据当场读不回来。
    """

    request = _window_request(statistical_basis_subframes=basis)
    persisted = BaseStationMeasurementWindowRequestEvidence.model_validate(
        {
            "schema_version": 1,
            "scope": "pcell",
            "lifecycle": "authoritative_closed",
            "cardinality": "single",
            "requested_window_count": 1,
            "expected_window_count": 1,
            "window_index": 0,
            **(
                {}
                if basis is None
                else {"statistical_basis_subframes": basis}
            ),
        }
    )

    assert persisted.statistical_basis_subframes == basis
    assert persisted.digest == request.digest


def test_persisted_legacy_payload_without_the_field_still_loads():
    """旧证据（无统计基键）不得因新字段崩掉历史读取路径。"""

    persisted = BaseStationMeasurementWindowRequestEvidence.model_validate(
        {
            "schema_version": 1,
            "scope": "pcell",
            "lifecycle": "authoritative_closed",
            "cardinality": "single",
            "requested_window_count": 5,
            "expected_window_count": 1,
            "window_index": 0,
        }
    )

    assert persisted.statistical_basis_subframes is None
    assert persisted.digest == (
        "d9c63dc240594fa4bcf582117fa5928d0bb51afc12cf4a9a447f9ee9e579b880"
    )


def test_brownfield_evidence_blob_without_the_new_key_still_parses():
    """历史 BaseStation 证据整块必须原样往返 —— 缺席保留为缺席。

    ``parse_base_station_execution_evidence`` 以 ``normalized == value``
    严格相等判合法。新增的可选字段若被 ``model_dump`` 补成 ``null`` 写回
    normalized，**每一行**历史证据都会被判 malformed（execution 的诊断/正式
    生命周期判定随之全部退化）——这不是 KPI 变保守，是历史数据整片读不出来。
    """

    from tests.test_base_station_diagnostic_lifecycle_hotfix import (
        _diagnostic_evidence,
    )
    from app.services.mimo_ota.base_station_execution_evidence import (
        parse_base_station_execution_evidence,
    )

    legacy = _diagnostic_evidence()
    for window in legacy["measurement_windows"]:
        assert "statistical_basis_subframes" not in window["trust"]["request"]

    assert parse_base_station_execution_evidence(legacy) == legacy

    fresh = _diagnostic_evidence()
    for window in fresh["measurement_windows"]:
        request = window["trust"]["request"]
        request["statistical_basis_subframes"] = 5000
        window["trust"]["request_digest"] = canonical_snapshot_digest(request)

    assert parse_base_station_execution_evidence(fresh) == fresh


# ===========================================================================
# C. 窗口行为：下发 + 回读确认 + 全域 fail-closed
# ===========================================================================


@pytest.mark.asyncio
async def test_window_drives_and_confirms_the_frozen_statistical_basis():
    driver = _WindowDriver(states=["OFF", "RUN", "RUN", "RDY", "OFF"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1, request=_window_request(statistical_basis_subframes=5000)
        )

    # SFRames 落在 window configuration 组内（手册 §3.3.1 p.940 示例同序）
    assert driver.writes == [
        "ABORt:LTE:SIGN1:EBLer",
        "CONFigure:LTE:SIGN1:EBLer:TOUT 0",
        "CONFigure:LTE:SIGN1:EBLer:REPetition CONTinuous",
        "CONFigure:LTE:SIGN1:EBLer:SCONdition NONE",
        _sframes_write(5000),
        "INITiate:LTE:SIGN1:EBLer",
        "STOP:LTE:SIGN1:EBLer",
        "ABORt:LTE:SIGN1:EBLer",
    ]
    assert SFRAMES_QUERY in driver.queries
    assert window.confirmed is True
    assert window.metrics.is_valid("dl_throughput") is True

    basis = _statistical_basis(window)
    assert basis["requested_subframes"] == 5000
    assert basis["applied_subframes"] == 5000
    assert basis["confirmed"] is True
    assert basis["item"].evidence_level is EvidenceLevel.APPLIED
    assert basis["item"].verdict is EvidenceVerdict.PASSED
    assert basis["item"].command_sent == _sframes_write(5000)
    assert "p.953" in basis["item"].source_reference
    # 内审 F4：窗口证据项本身不落库（append_base_station_measurement_window
    # 只取 exchange_ids 做账本校验），所以仪器回读的 applied 值必须搭 trust.reason
    # 这个既有落库字段出去，否则现场排障看不到「仪器当时报了多少」。
    assert "5000 subframes applied" in window.reason
    assert "requested 5000" in window.reason


@pytest.mark.asyncio
async def test_readback_mismatch_fails_closed_without_backfilling():
    """回读 ≠ 请求：窗口不确认，且 applied 只能是仪器报的值。"""

    driver = _WindowDriver(states=["OFF", "OFF"], subframes_readback=10_000)

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1, request=_window_request(statistical_basis_subframes=5000)
        )

    assert window.confirmed is False
    assert "INITiate:LTE:SIGN1:EBLer" not in driver.writes
    assert window.metrics.dl_throughput_mbps is None
    assert window.metrics.is_valid("dl_throughput") is False

    basis = _statistical_basis(window)
    assert basis["requested_subframes"] == 5000
    assert basis["applied_subframes"] == 10_000  # 绝不从请求值回填
    assert basis["confirmed"] is False
    assert basis["item"].verdict is EvidenceVerdict.REJECTED
    assert basis["item"].evidence_level is not EvidenceLevel.APPLIED
    assert "5000" in window.reason and "10000" in window.reason


@pytest.mark.asyncio
async def test_write_error_queue_fails_closed():
    driver = _WindowDriver(
        states=["OFF", "OFF"],
        error_after={_sframes_write(5000): '-113,"Undefined header"'},
    )

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1, request=_window_request(statistical_basis_subframes=5000)
        )

    assert window.confirmed is False
    assert "INITiate:LTE:SIGN1:EBLer" not in driver.writes
    basis = _statistical_basis(window)
    assert basis["confirmed"] is False
    assert basis["applied_subframes"] is None
    assert basis["item"].verdict is EvidenceVerdict.UNKNOWN


@pytest.mark.asyncio
async def test_readback_query_failure_fails_closed():
    driver = _WindowDriver(
        states=["OFF", "OFF"],
        subframes_readback=TimeoutError("VISA timeout"),
    )

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1, request=_window_request(statistical_basis_subframes=5000)
        )

    assert window.confirmed is False
    assert "INITiate:LTE:SIGN1:EBLer" not in driver.writes
    basis = _statistical_basis(window)
    assert basis["confirmed"] is False
    assert basis["applied_subframes"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("subframes", [99, 400_001])
async def test_out_of_range_frozen_basis_never_reaches_the_wire(subframes):
    driver = _WindowDriver(states=["OFF", "OFF"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1,
            request=_window_request(statistical_basis_subframes=subframes),
        )

    # 统计基不可用 → **整个 window configuration 组**都不下发：不确认的统计基
    # 下改仪器保留的 TOUT/REPetition/SCONdition，只是白改状态。线上只剩前后
    # 两条 ABORT（前置清窗 + finally 收尾）。
    assert driver.writes == [
        "ABORt:LTE:SIGN1:EBLer",
        "ABORt:LTE:SIGN1:EBLer",
    ]
    assert SFRAMES_QUERY not in driver.queries
    assert window.confirmed is False
    basis = _statistical_basis(window)
    assert basis["requested_subframes"] == subframes
    assert basis["applied_subframes"] is None
    assert basis["confirmed"] is False
    assert basis["item"].verdict is EvidenceVerdict.REJECTED
    assert basis["item"].command_sent is None
    # 内审 F3：拒绝理由必须进 lifecycle_failures。丢掉它 details 就空了，
    # reason 会落成 "…confirmed"，让一个 confirmed=False 的窗口带着
    # 「confirmed」字样进 trust.reason 与 _BaseStationWindowBlocked 的报错。
    # 证据项本身不落库，reason 是这条失败唯一的持久化解释通道。
    assert "confirmed" not in window.reason
    assert "statistical basis" in window.reason
    assert str(subframes) in window.reason


@pytest.mark.asyncio
async def test_legacy_request_without_a_frozen_basis_fails_closed():
    """旧请求（无统计基）不崩，但也绝不当成已确认 —— 那正是原故障。"""

    driver = _WindowDriver(states=["OFF", "OFF"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1, request=_window_request(statistical_basis_subframes=None)
        )

    assert driver.writes == [
        "ABORt:LTE:SIGN1:EBLer",
        "ABORt:LTE:SIGN1:EBLer",
    ]
    assert SFRAMES_QUERY not in driver.queries
    assert window.confirmed is False
    basis = _statistical_basis(window)
    assert basis["requested_subframes"] is None
    assert basis["confirmed"] is False
    # 内审 F3：同上 —— 缺失路径的 reason 也不得说反话。
    assert "confirmed" not in window.reason
    assert "statistical basis" in window.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("subframes", [100, 400_000])
async def test_boundary_basis_values_are_driven_and_confirmed(subframes):
    driver = _WindowDriver(
        states=["OFF", "RUN", "RUN", "RDY", "OFF"],
        subframes_readback=subframes,
    )

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1,
            request=_window_request(statistical_basis_subframes=subframes),
        )

    assert _sframes_write(subframes) in driver.writes
    assert window.confirmed is True
    assert _statistical_basis(window)["applied_subframes"] == subframes


@pytest.mark.asyncio
async def test_statistical_basis_exchange_ids_use_the_real_transport_intent():
    """wire 记账门：传输层写命令的 intent token 是 ``command``，不是 ``write``。

    ``write`` 只出现在 mock 模拟边界（``base.py::_simulate_scpi_write``）；
    照抄测试 fake 会让这里恒空 —— P2-52 内审 F1 同款。
    """

    driver = _WindowDriver(states=["OFF", "RUN", "RUN", "RDY", "OFF"])

    with capture_scpi_exchanges() as exchanges:
        with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
            window = await driver.measure_base_station_window(
                0.1, request=_window_request(statistical_basis_subframes=5000)
            )

    basis = _statistical_basis(window)
    by_id = {exchange.exchange_id: exchange for exchange in exchanges}
    assert basis["exchange_ids"], "已确认的统计基必须携带真实往返证据"
    observed = {
        (by_id[eid].command, by_id[eid].operation)
        for eid in basis["exchange_ids"]
    }
    assert observed == {
        (_sframes_write(5000), "command"),
        (SFRAMES_QUERY, "query"),
    }
    assert all(by_id[eid].simulated is False for eid in basis["exchange_ids"])


@pytest.mark.asyncio
async def test_window_evidence_ledger_stays_writer_compatible():
    """不变量：证据项 exchange_ids 顺序拼接 == trust 账本，且无重复。

    这正是 ``execution_scpi_evidence.append_base_station_measurement_window``
    落库前的前置条件（重复即 raise、顺序不等即 raise）。新增第二条证据项
    如果去认领窗口账本里已有的 id，历史落库路径当场崩。
    """

    driver = _WindowDriver(states=["OFF", "RUN", "RUN", "RDY", "OFF"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(
            0.1, request=_window_request(statistical_basis_subframes=5000)
        )

    ledger = [
        exchange_id
        for item in window.evidence
        for exchange_id in item.exchange_ids
    ]
    assert len(set(ledger)) == len(ledger)
    assert ledger == list(window.trust.exchange_ids)


# ===========================================================================
# D. 冻结链路：TestCase stat_count → 窗口请求
# ===========================================================================


def test_window_plan_freezes_the_statistical_basis_for_every_window():
    requests = MeasureExecutor._measurement_window_requests(
        RealCmw500Driver.adapter_manifest,
        throughput_scope="pcell",
        requested_sample_count=5,
        simulated_diagnostic=False,
        statistical_basis_subframes=5000,
    )

    assert [request.statistical_basis_subframes for request in requests] == [5000]


def test_window_plan_requires_an_explicit_statistical_basis():
    """统计基不得有默认值 —— 默认值回填正是不变量 1 禁止的形态。"""

    with pytest.raises(TypeError):
        MeasureExecutor._measurement_window_requests(
            RealCmw500Driver.adapter_manifest,
            throughput_scope="pcell",
            requested_sample_count=1,
            simulated_diagnostic=False,
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, TypeError), (5000.0, TypeError), ("5000", TypeError),
     (0, ValueError), (-1, ValueError)],
)
def test_window_plan_raises_the_documented_exception_kind(value, expected):
    """外审 R1：执行器层与请求层共用同一套异常契约。"""

    with pytest.raises(expected):
        MeasureExecutor._measurement_window_requests(
            RealCmw500Driver.adapter_manifest,
            throughput_scope="pcell",
            requested_sample_count=1,
            simulated_diagnostic=False,
            statistical_basis_subframes=value,
        )


@pytest.mark.parametrize("value", [0, -1, True, 5000.0, "5000"])
def test_window_plan_rejects_an_invalid_statistical_basis(value):
    with pytest.raises((TypeError, ValueError)):
        MeasureExecutor._measurement_window_requests(
            RealCmw500Driver.adapter_manifest,
            throughput_scope="pcell",
            requested_sample_count=1,
            simulated_diagnostic=False,
            statistical_basis_subframes=value,
        )


@pytest.mark.asyncio
async def test_measure_samples_carry_the_frozen_basis_to_the_instrument():
    """端到端（无 DB）：采样器把冻结的统计基一路带到 SCPI 线上。"""

    driver = _WindowDriver(
        states=["OFF", "RUN", "RUN", "RDY", "OFF"],
        subframes_readback=3000,
    )

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        samples = await MeasureExecutor._measure_base_station_samples(
            driver,
            window_s=0.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            requested_sample_count=1,
            manifest=RealCmw500Driver.adapter_manifest,
            simulated_diagnostic=False,
            statistical_basis_subframes=3000,
        )

    assert len(samples) == 1
    assert _sframes_write(3000) in driver.writes
    assert samples[0].window.confirmed is True
