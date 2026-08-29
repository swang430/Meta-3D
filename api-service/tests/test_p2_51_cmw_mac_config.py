"""P2-51：CMW500 MAC/调度配置正式证据闭环（非现场半）。

门覆盖（各配变异，见 PR 记录）：
  ① wire 形态白名单 —— builder 输出逐字节锁定 + 未取证 token 拒绝；
  ② 满配 RMC 表与手册逐行一致（表 2-38 p.78 / 表 2-33 pp.70-71）；
  ③ 行为门 —— happy path 全组回读确认、回读不一致 fail-loud、错误队列非空
     fail-loud、DLEQual 耦合生效端（DL2 回读）不符 fail-loud；
  ④ 选件依赖拒绝 —— enable_amc(CQI/KS510)、HARQ 组不驱动只探测；
  ⑤ 形态空间拒绝 —— mimo_layers=4 / 部分 RB / TDD duplex / 未知带宽 /
     低固件 / SAFE_IDLE 未确认；
  ⑥ P2-50 计划接通 —— RealCmw500Driver 的 mac_throughput.planned is True 且
     capability_source 为 manifest token 形态；manifest 镜像同步；
  ⑦ 固件下限常量与命令规格表派生值一致（不变量门）。

取证底本：R&S CMW LTE UE User Manual 1173.9628.02-41
（docs/plans/2026-08-30-p2-51-cmw500-mac-scheduling-evidence.md）。
"""

from __future__ import annotations

from collections import deque

import pytest

from app.hal.base_station import resolve_base_station_execution_plan
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.cmw500_command_profile import (
    CMW500_LTE_COMMANDS,
    CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH,
    Cmw500LteCommandProfile,
    CmwLteFullRbRmcPlan,
    CmwRmcSelection,
)
from app.hal.uxm_base_station import MacThroughputConfigResult
from app.services.mimo_ota.executors.measure import MeasureExecutor


DL1_HEADER = "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:DL1"
DL2_HEADER = "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:DL2"
MCLUSTER_QUERY = "CONFigure:LTE:SIGN1:CONNection:PCC:MCLuster:UL?"
HARQ_QUERY = "CONFigure:LTE:SIGN1:CONNection:HARQ:DL:ENABle?"
PADDING_QUERY = "CONFigure:LTE:SIGN1:CONNection:DLPadding?"


class _MacDriver(RealCmw500Driver):
    """回读式仿真 transport：写进 state、查询回显，可注入拒绝/覆盖。"""

    def __init__(
        self,
        *,
        duplex: str = "FDD",
        bandwidth: str = "B200",
        firmware: str = "V4.0.20",
        cell_state: str = "OFF,ADJ",
        reject_writes: tuple[str, ...] = (),
        query_overrides: dict | None = None,
    ) -> None:
        super().__init__("cmw-mac", {"ip_address": "192.0.2.10"})
        self._visa_session = object()
        self._firmware_version = firmware
        self.duplex = duplex
        self.bandwidth = bandwidth
        self.cell_state_response = cell_state
        self.reject_writes = set(reject_writes)
        self.query_overrides = dict(query_overrides or {})
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.state: dict[str, str] = {}
        self.pending_errors: deque[str] = deque()

    def _do_write(self, command: str) -> None:
        self.writes.append(command)
        header, _, value = command.partition(" ")
        if header in self.reject_writes:
            self.pending_errors.append('-113,"Undefined header"')
            return
        self.state[header] = value

    def _do_query(self, command: str) -> str:
        self.queries.append(command)
        if command in self.query_overrides:
            response = self.query_overrides[command]
            if isinstance(response, Exception):
                raise response
            return response
        if command == "SYSTem:ERRor:ALL?":
            if self.pending_errors:
                return self.pending_errors.popleft()
            return '0,"No error"'
        if command == "*OPC?":
            return "1"
        if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
            return self.cell_state_response
        if command == "CONFigure:LTE:SIGN1:DMODe?":
            return self.duplex
        if command == "CONFigure:LTE:SIGN1:CELL:BANDwidth:DL?":
            return self.bandwidth
        if command.endswith("?"):
            header = command[:-1]
            if header in self.state:
                return self.state[header]
            if header == DL2_HEADER:
                # 模拟 DLEQual 耦合：流 2 回显流 1 的配置
                if DL1_HEADER in self.state:
                    return self.state[DL1_HEADER]
            if command == MCLUSTER_QUERY:
                return "OFF"
            if command == HARQ_QUERY:
                return "OFF"
        raise AssertionError(f"unexpected query: {command}")


def _fields_by_name(result: MacThroughputConfigResult) -> dict:
    return {field.field: field for field in result.receipt.fields}


# ---------------------------------------------------------------------------
# ① wire 形态白名单
# ---------------------------------------------------------------------------


def test_mac_builders_emit_exact_manual_wire_forms():
    profile = Cmw500LteCommandProfile
    b200 = CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH["B200"]

    assert profile.mac_scheduling_type_rmc(1) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:STYPe RMC"
    )
    assert profile.mac_scheduling_type_query(1) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:STYPe?"
    )
    assert profile.build_mac_rmc_dl(1, 1, b200.downlink) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:DL1 N100,Q16,T13"
    )
    assert profile.mac_rmc_dl_query(1, 2) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:DL2?"
    )
    assert profile.build_mac_rmc_ul(1, b200.uplink) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:UL N100,QPSK,T2"
    )
    assert profile.mac_rbposition_dl_low(1, 1) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:RBPosition:DL1 LOW"
    )
    assert profile.mac_rbposition_ul_low(1) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:RBPosition:UL LOW"
    )
    assert profile.mac_dl_stream_coupling_on(1) == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:DLEQual ON"
    )
    assert profile.mac_dl_padding_on(1) == (
        "CONFigure:LTE:SIGN1:CONNection:DLPadding ON"
    )
    assert profile.mac_ul_multicluster_query(1) == MCLUSTER_QUERY
    assert profile.mac_harq_dl_enable_query(1) == HARQ_QUERY


def test_mac_builders_reject_undocumented_tokens():
    profile = Cmw500LteCommandProfile

    with pytest.raises(ValueError, match="number-RB"):
        profile.build_mac_rmc_dl(1, 1, CmwRmcSelection("N11", "QPSK", "T5"))
    with pytest.raises(ValueError, match="modulation"):
        # UL 无 Q1024（手册 p.800 UL 枚举止于 Q256）
        profile.build_mac_rmc_ul(1, CmwRmcSelection("N100", "Q1024", "T2"))
    with pytest.raises(ValueError, match="TBS"):
        profile.build_mac_rmc_dl(1, 1, CmwRmcSelection("N100", "Q16", "T38"))
    with pytest.raises(ValueError, match="stream suffix"):
        profile.mac_rmc_dl_query(1, 3)


def test_mac_readback_parsers_are_strict_whitelists():
    profile = Cmw500LteCommandProfile

    assert profile.parse_mac_scheduling_type("RMC") == "RMC"
    assert profile.parse_mac_scheduling_type("CQI,TTIB") == "CQI"
    with pytest.raises(ValueError):
        profile.parse_mac_scheduling_type("WHATEVER")
    parsed = profile.parse_mac_rmc_readback("N100,Q16,T13", direction="dl")
    assert parsed.encoded() == "N100,Q16,T13"
    with pytest.raises(ValueError):
        profile.parse_mac_rmc_readback("N100,Q1024,T2", direction="ul")
    with pytest.raises(ValueError):
        profile.parse_mac_rmc_readback("N100,Q16,KEEP", direction="dl")
    assert profile.parse_mac_on_off("1") == "ON"
    assert profile.parse_mac_on_off("OFF") == "OFF"
    with pytest.raises(ValueError):
        profile.parse_mac_on_off("MAYBE")
    assert profile.parse_mac_rb_position("LOW", direction="dl") == "LOW"
    with pytest.raises(ValueError):
        profile.parse_mac_rb_position("P7", direction="dl")
    assert profile.parse_mac_rb_position("P7", direction="ul") == "P7"


# ---------------------------------------------------------------------------
# ② 满配 RMC 表与手册逐行一致
# ---------------------------------------------------------------------------


def test_full_rb_rmc_table_matches_manual_rows():
    """表 2-38（DL, FDD 多天线, p.78）满配行最高无选件调制 + 表 2-33
    （UL QPSK 列, pp.70-71）。单边改表即红。"""

    assert CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH == {
        "B014": CmwLteFullRbRmcPlan(
            downlink=CmwRmcSelection("N6", "QPSK", "T4"),
            uplink=CmwRmcSelection("N6", "QPSK", "T6"),
        ),
        "B030": CmwLteFullRbRmcPlan(
            downlink=CmwRmcSelection("N15", "QPSK", "T5"),
            uplink=CmwRmcSelection("N15", "QPSK", "T6"),
        ),
        "B050": CmwLteFullRbRmcPlan(
            downlink=CmwRmcSelection("N25", "Q16", "T12"),
            uplink=CmwRmcSelection("N25", "QPSK", "T5"),
        ),
        "B100": CmwLteFullRbRmcPlan(
            downlink=CmwRmcSelection("N50", "Q64", "T18"),
            uplink=CmwRmcSelection("N50", "QPSK", "T6"),
        ),
        "B150": CmwLteFullRbRmcPlan(
            downlink=CmwRmcSelection("N75", "QPSK", "T5"),
            uplink=CmwRmcSelection("N75", "QPSK", "T3"),
        ),
        "B200": CmwLteFullRbRmcPlan(
            downlink=CmwRmcSelection("N100", "Q16", "T13"),
            uplink=CmwRmcSelection("N100", "QPSK", "T2"),
        ),
    }
    # 带宽键集必须与驱动声明的支持带宽一一对应（防单边扩带宽）
    assert set(CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH) == set(
        RealCmw500Driver.bandwidth_token_by_mhz.values()
    )


def test_mac_min_firmware_constant_derives_from_spec_table():
    """⑦ 不变量门：常量 = mac_* 规格 minimum_firmware 的最大值。"""

    def _parts(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.removeprefix("V").split("."))

    mac_minimums = [
        spec.minimum_firmware
        for name, spec in CMW500_LTE_COMMANDS.items()
        if name.startswith("mac_")
    ]
    assert all(isinstance(item, str) for item in mac_minimums)
    derived = max(mac_minimums, key=_parts)
    assert RealCmw500Driver.MAC_CFG_MIN_FIRMWARE == derived


# ---------------------------------------------------------------------------
# ③ 行为门：happy path / 回读不一致 / 错误队列 / 耦合生效端
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_2x2_configures_and_confirms_every_group():
    driver = _MacDriver()

    result = await driver.configure_mac_throughput_test(
        mimo_layers=2,
        mcs=28,
        enable_amc=False,
        tdd_pattern="DDDDDDDSUU",
        tdd_period="5MS",
        harq_max_trans=4,
        harq_processes=16,
        stat_count=5000,
        scs_khz=30,
        csi_rs_ports=None,
    )

    assert result.ok
    assert result.error is None
    assert result.rejected == ()
    assert result.missing_mandatory == ()
    assert result.applied == (
        "SCHED_TYPE_RMC",
        "DL_STREAM_COUPLING",
        "RMC_DL",
        "RMC_RBPOS_DL",
        "RMC_UL",
        "RMC_RBPOS_UL",
        "DL_PADDING",
    )
    assert result.skipped == ("HARQ_DL_NHT",)
    assert set(result.no_equivalent) == {
        "NR_MCS_INDEX",
        "TDD_SLOT_PATTERN",
        "HARQ_PROCESSES",
        "MEAS_TPUT_STAT_COUNT",
        "NR_SCS",
        "CSI_RS_PORTS",
    }
    # 行为门：写序逐字节锁定 —— 任何额外/缺失/变形写入即红
    assert driver.writes == [
        "CONFigure:LTE:SIGN1:CONNection:PCC:STYPe RMC",
        "CONFigure:LTE:SIGN1:CONNection:PCC:DLEQual ON",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:DL1 N100,Q16,T13",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:RBPosition:DL1 LOW",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:UL N100,QPSK,T2",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:RBPosition:UL LOW",
        "CONFigure:LTE:SIGN1:CONNection:DLPadding ON",
    ]
    # 回执：正确 operation、逐字段确认、耦合生效端（DL2）已核
    assert result.receipt is not None
    assert result.receipt.operation == "mac_throughput_config"
    assert result.receipt.operation_succeeded is True
    fields = _fields_by_name(result)
    for name in (
        "scheduling_type",
        "ul_multicluster",
        "dl_stream_coupling",
        "rmc_dl",
        "rmc_dl_stream2",
        "rmc_rb_position_dl",
        "rmc_ul",
        "rmc_rb_position_ul",
        "dl_padding",
    ):
        assert fields[name].status == "confirmed", name
    assert fields["rmc_dl"].applied == "N100,Q16,T13"
    assert fields["rmc_ul"].applied == "N100,QPSK,T2"
    # HARQ：选件域不驱动，回执如实声明选件依赖 + 探测观测值
    assert fields["harq_max_trans"].status == "unknown"
    assert "KS510" in fields["harq_max_trans"].reason
    assert "ENABle=OFF" in fields["harq_max_trans"].reason
    # measure 执行器的既有判定对该结果放行（不改 MEASURE 的接通证据）
    assert MeasureExecutor._mac_config_blocker(result) is None


@pytest.mark.asyncio
async def test_readback_mismatch_is_fail_loud():
    driver = _MacDriver(query_overrides={PADDING_QUERY: "OFF"})

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert any(item.startswith("DL_PADDING") for item in result.rejected)
    assert result.receipt.operation_succeeded is False
    blocker = MeasureExecutor._mac_config_blocker(result)
    assert blocker is not None and "不能继续测" in blocker


@pytest.mark.asyncio
async def test_instrument_rejection_via_error_queue_is_fail_loud():
    driver = _MacDriver(
        reject_writes=("CONFigure:LTE:SIGN1:CONNection:PCC:RMC:UL",)
    )

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert "RMC_UL" in result.rejected
    assert "RMC_UL" not in result.applied
    fields = _fields_by_name(result)
    assert fields["rmc_ul"].status == "unknown"
    assert "-113" in fields["rmc_ul"].reason


@pytest.mark.asyncio
async def test_stream2_coupling_mismatch_is_fail_loud():
    driver = _MacDriver(
        query_overrides={f"{DL2_HEADER}?": "N100,QPSK,T2"}
    )

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert any(
        item.startswith("RMC_DL_STREAM2_COUPLED") for item in result.rejected
    )


@pytest.mark.asyncio
async def test_single_layer_rejected_without_writes():
    """内审 F2 收窄：满配 DL 行取自表 2-38（TM2-6 多天线专用）——单天线
    表 2-37 同带宽行是另一组调制/TBS，mimo=1 下发即适用域外的行。
    只取证了 2 流，=1 与 =4 一样拒绝且零写入。"""
    driver = _MacDriver()

    result = await driver.configure_mac_throughput_test(mimo_layers=1)

    assert not result.ok
    assert "只取证了 2 流" in result.error
    assert driver.writes == []


@pytest.mark.asyncio
async def test_mcluster_on_breaks_contiguous_premise():
    driver = _MacDriver(query_overrides={MCLUSTER_QUERY: "ON"})

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert any(
        item.startswith("UL_MULTICLUSTER_PROBE") for item in result.rejected
    )


@pytest.mark.asyncio
async def test_harq_probe_failure_is_recorded_not_fatal():
    driver = _MacDriver(
        query_overrides={HARQ_QUERY: ConnectionError("probe boom")}
    )

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert result.ok
    assert "探测异常" in _fields_by_name(result)["harq_max_trans"].reason


# ---------------------------------------------------------------------------
# ④⑤ 选件依赖与形态空间拒绝（全部不碰仪器写入）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"enable_amc": True}, "KS510"),
        ({"mimo_layers": 4}, "只取证了 2 流"),
        ({"rb_alloc": "HALF"}, "满 RB"),
    ],
)
async def test_unevidenced_request_shapes_are_rejected_without_writes(
    kwargs, match
):
    driver = _MacDriver()

    result = await driver.configure_mac_throughput_test(**kwargs)

    assert not result.ok
    assert result.error is not None and match in result.error
    assert driver.writes == []
    assert MeasureExecutor._mac_config_blocker(result) is not None


@pytest.mark.asyncio
async def test_tdd_duplex_fails_loud_without_config_writes():
    driver = _MacDriver(duplex="TDD")

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert "ULD" in (result.error or "")
    assert driver.writes == []


@pytest.mark.asyncio
async def test_unknown_live_bandwidth_fails_loud():
    driver = _MacDriver(bandwidth="B040")

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert "B040" in (result.error or "")
    assert driver.writes == []


@pytest.mark.asyncio
async def test_firmware_below_command_set_floor_is_rejected():
    driver = _MacDriver(firmware="V3.2.10")

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert RealCmw500Driver.MAC_CFG_MIN_FIRMWARE in (result.error or "")
    assert driver.writes == []
    assert driver.queries == []


@pytest.mark.asyncio
async def test_unconfirmed_safe_idle_blocks_configuration():
    driver = _MacDriver(cell_state="GARBAGE")

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert "SAFE_IDLE" in (result.error or "")
    assert driver.writes == []


# ---------------------------------------------------------------------------
# ⑥ P2-50 计划接通 + manifest 镜像
# ---------------------------------------------------------------------------


def test_execution_plan_marks_cmw_mac_throughput_planned_via_manifest_token():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    plan = resolve_base_station_execution_plan(
        driver, manifest=RealCmw500Driver.adapter_manifest
    )

    assert plan.mac_throughput.planned is True
    assert (
        plan.mac_throughput.capability_source
        == "manifest.operations:mac_throughput_config"
    )


def test_manifest_operation_token_mirrors_classvar():
    assert "mac_throughput_config" in RealCmw500Driver.adapter_manifest.operations
    assert RealCmw500Driver.mac_throughput_configuration_supported is True


def test_result_receipt_field_defaults_to_none_for_uxm_compat():
    assert MacThroughputConfigResult().receipt is None


@pytest.mark.asyncio
async def test_stale_error_queue_is_drained_not_misattributed():
    """内审 F5-MU1：进入配置前的残留错误必须被排空（记日志），
    不许误归属为活体 duplex/带宽查询被拒——删排空段本门要红。"""
    driver = _MacDriver()
    driver.pending_errors.append('-350,"Queue overflow (stale)"')

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert result.ok, f"残留错误被误归属: {result.error or result.rejected}"


class _ErrorAfterReadbackDriver(_MacDriver):
    """回读查询本身有响应、但其后错误队列非空的时序注入。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._arm_error_after_readback = False

    def _do_query(self, command: str) -> str:
        if command == "SYSTem:ERRor:ALL?" and self._arm_error_after_readback:
            self._arm_error_after_readback = False
            return '-221,"Settings conflict (post-readback)"'
        response = super()._do_query(command)
        # 命中 STYPe 回读（查询形、非 ERR/OPC）后武装下一次 ERR
        if command.endswith("STYPe?"):
            self._arm_error_after_readback = True
        return response


@pytest.mark.asyncio
async def test_error_after_readback_rejects_group():
    """内审 F5-MU2：回读有响应但仪器同时压错 → 该组必须记 rejected
    （回读被拒），不许把错误吞掉当回读成功——删 query_gate 验错本门要红。"""
    driver = _ErrorAfterReadbackDriver()

    result = await driver.configure_mac_throughput_test(mimo_layers=2)

    assert not result.ok
    assert any("回读被拒" in item for item in result.rejected), result.rejected
