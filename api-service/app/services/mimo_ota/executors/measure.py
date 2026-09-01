"""Phase 3: Static MIMO throughput measurement (the core of MIMO OTA).

Replaces commissioning_service.phase3_static_mimo_test. The flow:

1. Set base station cell config + 3GPP MAC throughput parameters from the
   bound TestCase.configuration (no longer hard-coded in the service).
2. Generate the CDL channel via ChannelEngineClient and load it into the
   channel emulator (ASC or GCM strategy depending on engine_mode).
3. Walk the turntable through each azimuth in config.azimuths_deg and aggregate
   only the base-station KPIs whose per-field validity is explicitly confirmed.
   Missing RSRP/SINR/RI remain N/A; target settings are never measurements.

LabProfile contributes the chamber row (calibration entries, geometry).
TestCase.calibration_certificate_id (optional) is referenced for traceability;
the actual per-probe path-loss data still comes from chamber-keyed
ProbePathLossCalibration rows.

── 路径 A/B 边界 (P2-11 Phase 5 固化) ──────────────────────────────────────
本 executor 是**路径 B (正式测试) 的核心**: 仪表关键参数全由 TestCase
(MIMOOTAConfiguration) 单一真值源驱动, **不读 HAL-init 默认** —— UXM
set_cell_config(arfcn=freq→ARFCN) / F64 emulation_file(GCM)+ engine 频率 /
switch orchestrate(switch_mode_id)/ 路损 cert(operating_mode 过滤)/ SA /
positioner 全 TestCase 派生, 下发后多方频率一致性 + GCM .smu + switch mode 三道
fail-loud 门挡静默错配 (Phase 1/2/3)。路径 A (bring-up 默认: P0-8 F64 .smu /
P1-17 UXM profile) 主要在 HAL-init 用 —— F64 .smu 这里由 emulation_file 覆盖,
UXM port routing / TDD / scheduler (mimo_port_preset/tdd_pattern/sched_algo/
csi_rs_ports) **P2-11 #1974 已补**: path B 经 _build_pcell_cell_config 从 TestCase
显式驱动 set_cell_config, 不再残留 HAL-init 默认 profile (原 Codex on PR #112 缺口)。
边界总览见 docs/architecture/testcase-driven-instrument-config.md §2/§6/§6.1。
"""
import asyncio
import inspect
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from app.models.chamber import ChamberConfiguration
from app.services.mimo_ota.executors._helpers import (
    load_mimo_ota_config,
    stddev,
    write_phase_result,
)
from app.services.mimo_ota.path_loss_application import (
    build_path_loss_application,
    path_loss_application_message,
)
from app.services.mimo_ota.rf_kpi_trust import (
    build_rf_kpi_trust,
    rf_kpi_trust_is_formally_verified,
)
from app.services.base_station_port_mapping import (
    resolve_base_station_port_mapping,
)
from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.schemas.mimo_ota.config import MIMOOTAStepType
from app.hal.base_station import (
    BaseStationExecutionPlan,
    BaseStationExecutionPlanItem,
    BaseStationMeasurementWindowRequest,
    BaseStationRequestedConfig,
    ThroughputMetrics,
    resolve_base_station_execution_plan,
)
from app.hal.base_station_compatibility import (
    verify_frozen_base_station_compatibility,
)
from app.hal.base_station_manifest import BaseStationAdapterManifest
from app.hal.base_station_mac_profile import FrozenMacTestProfile
from app.hal.scpi_evidence import capture_scpi_exchanges
from app.hal.propsim_f64 import _TOPOLOGY_ESCAPE_HINT
from app.services.execution_evidence_outcome import (
    execution_evidence_blocks_formal_outputs,
)

logger = logging.getLogger(__name__)

# Phase 2d: each "sample" is now an independent UXM stat window (≈ stat_count
# subframes ≈ stat_count ms), not a 20ms poll. Production wants ≥ 5-12 windows
# per azimuth for stable std; dev caps at 3 to keep smoke tests fast.
_DEV_SAMPLE_WINDOWS = 3
# Floor for window duration so mock paths still take a perceptible amount of
# time (helps surface ordering bugs) but don't actually wait 5s in unit tests.
_MOCK_WINDOW_FLOOR_S = 0.05

# Phase 2m: DUT 掉线检测周期 (每 N 个 azimuth 检查一次而非每窗口, 节省 SCPI 流量)
# 单 azimuth 内不检查（adapter-native 统计窗口自身负责确认窗口边界与链路状态）；
# azimuth 间隔检查能在转台移动期间发现掉线。
_DUT_HEALTH_CHECK_EVERY_N_AZIMUTHS = 1


def _frozen_mac_measurement_basis(profile: FrozenMacTestProfile) -> int:
    """Return the one profile-owned statistics basis for wait/request/audit."""

    if not isinstance(profile, FrozenMacTestProfile):
        raise TypeError("profile must be a FrozenMacTestProfile")
    return profile.profile.statistical_window.count


def _frozen_mcs_consistency_request(
    profile: FrozenMacTestProfile,
) -> tuple[int, bool] | None:
    """Return NR-only consistency intent; LTE RMC has no NR MCS semantics."""

    if not isinstance(profile, FrozenMacTestProfile):
        raise TypeError("profile must be a FrozenMacTestProfile")
    if profile.profile.kind != "nr_throughput":
        return None
    return profile.profile.mcs, profile.profile.enable_amc


async def _reconfigure_rrc_if_supported(
    base_station: Any,
    *,
    plan: BaseStationExecutionPlanItem,
    mimo_layers: int,
    modulation: str,
) -> Optional[bool]:
    """只按 execution-frozen 计划项决定是否下发 RRC 重配（P2-50）。

    计划说 planned 但 adapter 缺 ``reconfigure_rrc`` 属于计划/实现漂移，
    fail-loud，不回退成跳过。
    """
    if plan.planned is not True:
        return None
    method = getattr(base_station, "reconfigure_rrc", None)
    if not callable(method):
        raise RuntimeError(
            "执行计划声明 RRC 重配能力，但 adapter 缺 reconfigure_rrc"
            "（计划与实现漂移）"
        )
    return await method(
        mimo_layers=mimo_layers,
        modulation=modulation,
    )


class _CaSetupBlocked(RuntimeError):
    """Carry a CA setup blocker through cleanup before building the result."""


@dataclass(frozen=True)
class _BaseStationSample:
    """One adapter-native sample plus its optional confirmed lifecycle window."""

    metrics: ThroughputMetrics
    window: Any | None
    exchanges: tuple[Any, ...]


class _BaseStationWindowBlocked(RuntimeError):
    """Carry an unconfirmed native window through shared chamber cleanup."""

    def __init__(self, window: Any):
        self.window = window
        super().__init__(
            "BaseStation measurement-window lifecycle was not confirmed: "
            f"{window.reason}"
        )


@dataclass(frozen=True)
class _BaseStationAttemptContext:
    frozen_adapter: Dict[str, Any]
    attempt_id: str | None
    lease_identity: Any
    simulated_diagnostic: bool
    # P2-50: execution-frozen vendor-neutral 能力计划；attempt 路径上已与
    # evidence 里冻结的计划做过 digest 对账（漂移 fail-loud）。
    execution_plan: BaseStationExecutionPlan
    # P2-54: parsed exactly once from the execution freeze.  No downstream
    # consumer may rebuild this intent from the mutable TestCase.
    mac_profile: FrozenMacTestProfile | None


def _is_path_loss_certificate_verified(use_mock: Optional[bool]) -> bool:
    """Only an explicitly real certificate may be labelled verified."""
    return use_mock is False


def _missing_rf_chain_path_loss_azimuths(
    *,
    num_probes: int,
    azimuths_deg: List[float],
    chain_pl_by_probe_pol: Dict[tuple, float],
    polarization: str = "V",
) -> List[Dict[str, Any]]:
    """Return requested azimuths absent from a non-empty per-chain map."""
    from app.services.probe_pattern.consumer import (
        select_active_rf_chain_probe_id,
    )

    probe_id_base = _rf_chain_probe_id_base(
        num_probes=num_probes,
        chain_pl_by_probe_pol=chain_pl_by_probe_pol,
    )
    missing: List[Dict[str, Any]] = []
    pol = polarization.upper()
    for azimuth in azimuths_deg:
        probe_id = (
            select_active_rf_chain_probe_id(
                num_probes,
                azimuth,
                probe_id_base=probe_id_base,
            )
            if probe_id_base is not None
            else None
        )
        if probe_id is None or (probe_id, pol) not in chain_pl_by_probe_pol:
            missing.append(
                {
                    "azimuth_deg": float(azimuth),
                    "probe_id": probe_id,
                    "polarization": pol,
                }
            )
    return missing


def _rf_chain_probe_id_base(
    *,
    num_probes: int,
    chain_pl_by_probe_pol: Dict[tuple, float],
) -> Optional[int]:
    """Recognize a zero/one-based namespace only when its edge proves the base."""
    probe_ids = {probe_id for probe_id, _ in chain_pl_by_probe_pol}
    zero_based = set(range(num_probes))
    one_based = set(range(1, num_probes + 1))
    if probe_ids == zero_based or (
        probe_ids and probe_ids <= zero_based and 0 in probe_ids
    ):
        return 0
    if probe_ids == one_based or (
        probe_ids and probe_ids <= one_based and num_probes in probe_ids
    ):
        return 1
    return None


def _describe_f64_frequency_verification_gap(
    *,
    f64_center_mhz: Optional[float],
    f64_bandwidth_source: str,
    declared_bandwidth_mhz: Optional[float],
) -> str:
    """Explain the exact missing half of the F64 frequency identity."""
    bandwidth_declared = (
        f64_bandwidth_source == "channel_asset_or_scd_declared"
        and declared_bandwidth_mhz is not None
    )
    if f64_center_mhz is None and bandwidth_declared:
        return (
            "F64 中心频率未回读；资产/SCD 已声明带宽 "
            f"{declared_bandwidth_mhz:g} MHz，但缺少 live center，"
            "P0-5 不得据此判完整闭环。"
        )
    if f64_center_mhz is not None and not bandwidth_declared:
        return (
            "F64 中心频率已回读，但当前场景带宽没有可信资产声明；"
            "频率中心一致，带宽保持 unknown，P0-5 不得据此判完整闭环。"
        )
    return (
        "F64 中心频率未回读，当前场景带宽也没有可信资产声明；"
        "频率身份保持 unknown，P0-5 不得据此判完整闭环。"
    )


def _evaluate_path_loss_provenance_for_measure(
    use_mock: Optional[bool],
    *,
    channel_emulator_is_real: bool,
    strict: bool,
    diagnostic: bool = False,
) -> tuple[bool, Optional[str]]:
    """判定一张路损证书能否参与本次测量补偿。

    真实测量只接受显式 ``use_mock=False``。严格模式额外阻断执行；显式
    opt-out 只允许继续做未补偿的调试测量，不能把模拟/未知值洗进正式 KPI。
    mock 仪表链本身不产出正式 KPI，可继续复用 mock 证书做流程演练。
    """
    if diagnostic:
        return False, None
    if not channel_emulator_is_real or use_mock is False:
        return True, None

    provenance = "simulated" if use_mock is True else "unknown"
    blocker = None
    if strict:
        blocker = (
            f"path-loss calibration has {provenance} provenance "
            f"(use_mock={use_mock!r}); real measurement requires explicit "
            "use_mock=False"
        )
    return False, blocker


def _managed_attach_failure(
    *,
    managed: bool,
    strict: bool,
    base_station_is_real: bool,
    milestone: Dict[str, Any],
) -> Optional[str]:
    """返回标准受控 attach 动态门的失败原因；通过/不适用返回 ``None``。

    PRECHECK 在 ``managed_rf_attach`` 流程里只做静态门，所以真实连接门必须
    在本次 TestCase 的 UXM/F64/开关配置已建立后补回。mock 不产生真 UE
    事实；显式 opt-out 只留下审计记录，不在这里假造失败。
    """
    if not managed or not strict or not base_station_is_real:
        return None
    if milestone.get("attached") is True:
        return None
    return (
        "受控 UE attach 动态门失败：本次 TestCase 的 RF 测量态未确认 CONN。"
        f"{milestone.get('reason') or '小区连接状态未知'}"
    )


def _managed_sim_identity_unverified_failure(
    *,
    managed: bool,
    strict: bool,
    sim_profile_id: Optional[str],
    sim_profile_exists: bool,
    declared_imsi: Optional[str],
    observed_imsi: Optional[str],
) -> Optional[str]:
    """严格 SIM 身份门无法形成真实观测时 fail-closed。

    操作员登记的 IMSI 只能用于追溯和非严格审计，不能证明当前 attach 的
    就是那张卡；严格门只接受 UXM/UE 的本次实测 IMSI。
    """
    if not managed or not strict or not sim_profile_id:
        return None
    if not sim_profile_exists:
        return (
            f"严格 SIM 身份门无法验证：sim_profile_id={sim_profile_id} 不存在"
        )
    if not declared_imsi:
        return "严格 SIM 身份门无法验证：所选 SIMProfile 没有声明 IMSI"
    if not observed_imsi:
        return (
            "严格 SIM 身份门无法验证：受控 attach 后未获得 UXM/UE 实测 IMSI；"
            "操作员登记值不能证明实际插入的 SIM。若仪表方言暂不支持实测 IMSI，"
            "只能显式设置 precheck_strict_sim_identity=False 以未验证方式运行"
        )
    return None


def _call_topology_getter(emulator, getter_name: str):
    """调 CE 驱动的拓扑 getter, 返回原始值; 拿不到 / 不可用返回 None。

    这些 getter (`get_active_output_ports` / `get_active_input_count` …) 是**同步**的
    —— 只读加载时回读进内存的拓扑, 不发 SCPI。这里不直接调用而绕一层, 是为了区分
    三种"拿不到"并给出不同诊断:
      · 驱动没这个方法 (非 F64 / mock) → None, 安静降级;
      · 调用抛异常 → None, 不冒泡打断编排;
      · **返回 coroutine** (有人把 getter 改成了 `async def`, 或测试替身用了 AsyncMock)
        → None, 但记 **error 日志点名是代码问题**。不单独识别的话, 这个纯代码重构会
        被下游报成"仿真未加载 / MODEL:INFO? 回读失败", 把改代码诬告成仪器故障。
        同时 close() 掉那个 coroutine, 免得留下 never-awaited 警告。
    """
    getter = getattr(emulator, getter_name, None)
    if not callable(getter):
        return None
    try:
        val = getter()
    except Exception:  # noqa: BLE001 — 读能力失败等同"未知", 不冒泡打断编排
        return None
    if inspect.iscoroutine(val):
        val.close()
        logger.error(
            "CE 驱动的 %s 返回了 coroutine —— 拓扑 getter 约定是**同步**的。"
            "这是代码问题(getter 被改成 async / 测试替身用了 AsyncMock), 不是仪器故障。",
            getter_name,
        )
        return None
    return val


def _read_port_count(emulator, getter_name: str) -> Optional[int]:
    """读**物理端口数** (F64R-2), 只认正整数, 其它一律当"未知"。

    bool 是 int 的子类, 显式排除 (True 当成 1 个口是荒谬的)。0 / 负数同样当未知。
    用于 sanity bound 之类只关心"几个口"的地方; 要**逐口下发**的用 `_read_port_list`
    —— 端口号不保证是 1..N 连续。
    """
    val = _call_topology_getter(emulator, getter_name)
    if isinstance(val, bool) or not isinstance(val, int):
        return None
    return val if val > 0 else None


def _read_port_list(emulator, getter_name: str) -> Optional[List[int]]:
    """读**物理端口号列表** (F64R-2)。逐口下发的调用方必须用这个而不是 `range(1, N+1)`
    —— 仿真占用的端口号可能非连续 (如输出口 {2,4}), 照 1..N 发会误配一个、漏配一个。

    只认"全是正整数的非空 list/tuple"; 任一元素不合格 → 整体当"未知"(不拿半个列表
    去配硬件)。bool 同样排除。"""
    val = _call_topology_getter(emulator, getter_name)
    if not isinstance(val, (list, tuple)) or not val:
        return None
    out: List[int] = []
    for p in val:
        if isinstance(p, bool) or not isinstance(p, int) or p <= 0:
            return None
        out.append(p)
    return out


def _extract_b2_cluster_inputs(config) -> Dict[str, Any]:
    """B-2 (Codex P1 #169): 从 TestCase config 提取 geometric_native_fit 聚类输入。

    `B2ParametricTdlStrategy.generate_and_load` 消费 ``cdl_model_data["rt_rays"]``
    (真实 RT 子径) + ``test_class`` + ``f64_profile``; caller **不透传则 strategy 在调
    CE 前永远 fail-loud → B-2 路死** (Codex P1 #169: 即便 test case 含 RT 射线也丢)。

    真实 RT 子径经 RT-Release 现场写进 ``TestCase.configuration`` (MIMOOTAConfiguration
    ``extra="allow"`` forward-compat, 见 config.py L160) —— 无则 ``rt_rays=None``,
    strategy fail-loud = **设计预期** (standard CDL 路无子径, V1.0 §3.3 (5)(6))。

    返回 ``{rt_rays, test_class, f64_profile, ue_velocity_mps}``: rt_rays / f64_profile /
    velocity 缺省 ``None`` (strategy 各自 fail-loud / 降级), test_class 缺省
    ``throughput_psd`` (与 strategy / CE 端点默认一致)。
    """
    extra = config.model_extra or {}
    return {
        "rt_rays": extra.get("rt_rays"),
        "test_class": extra.get("test_class", "throughput_psd"),
        "f64_profile": extra.get("f64_profile"),
        "ue_velocity_mps": extra.get("ue_velocity_mps"),
    }


def _build_pcell_cell_config(
    config,
    *,
    mac_profile: FrozenMacTestProfile | None,
    frequency_mhz: float,
    arfcn: int,
    bandwidth_mhz: float,
    scs_khz: int,
    band: str,
) -> Dict[str, Any]:
    """构造 measure path B 的 PCell set_cell_config dict (P2-11 #1974)。

    path B 显式驱动端口路由/调度 (mimo_port_preset/sched_algo/csi_rs_ports), 避免残留
    HAL-init 默认 topology profile 的值 (如 2x2 TestCase 跑在残留 4x4 端口路由上)。

    ⚠️ 三个可选字段 **None 时不放进 dict** (Codex P1 #127): None = "TestCase 未指定",
    不传则 set_cell_config 不改该项 → 保持 HAL profile (旧 saved case 没这些字段, 反序列
    化得 None, 不被强加值覆盖; 否则旧 4x4 case 被默认 "2x2" 强制成 2x2 路由)。显式给才
    驱动。csi_rs_ports 额外语义: 不传时 set_cell_config 按 mimo_layers 自动推断。

    tdd_pattern/tdd_period **不在这里** —— 已由 configure_mac_throughput_test 驱动 (见
    execute), 这里再传是冗余 + 引入默认覆盖风险。频率/arfcn 由 caller 算好传入。
    """
    cell_cfg: Dict[str, Any] = {
        "frequency_mhz": frequency_mhz,
        "arfcn": arfcn,
        "bandwidth_mhz": bandwidth_mhz,
        "scs_khz": scs_khz,
        "band": band,
        "mimo_layers": config.mimo_layers,
        "dl_power_dbm": config.target_tx_power_dbm,
    }
    # UXM 整带宽口径优先（2026-08-07）：给了就由 UXM 驱动**只走**
    # `:DL:POWer:CHANnel`，上面的 dBm/SCS 仅保留审计痕迹（UXM 驱动侧是
    # if/elif，见 uxm_base_station 第 8 节）。CMW 不消费这个 UXM 专属字段，
    # 只按手册写入并回读通用 `dl_power_dbm` 的 PCC RS-EPRE。
    if config.uxm_dl_power_dbm_per_bw is not None:
        cell_cfg["dl_power_dbm_per_bw"] = config.uxm_dl_power_dbm_per_bw
    # 可选字段: 仅 TestCase 显式给 (非 None) 才驱动, 否则保持 HAL profile (backward-compat)
    if config.mimo_port_preset is not None:
        cell_cfg["mimo_port_preset"] = config.mimo_port_preset
    if mac_profile is not None and mac_profile.profile.kind == "nr_throughput":
        cell_cfg["sched_algo"] = mac_profile.profile.scheduler_algorithm
        cell_cfg["csi_rs_ports"] = mac_profile.profile.csi_rs_ports
    return cell_cfg


def _build_pcell_requested_config(
    config,
    *,
    mac_profile: FrozenMacTestProfile | None = None,
) -> BaseStationRequestedConfig:
    """Build the single RAT-aware request handed to every base-station adapter."""

    if mac_profile is None:
        mac_profile = getattr(config, "mac_profile", None)

    pcell = config.primary_carrier
    if pcell.radio_technology == "lte":
        channel_kind = "lte_dl_earfcn"
        nr_arfcn = None
        lte_dl_earfcn = pcell.lte_dl_earfcn
    else:
        from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn

        channel_kind = "nr_arfcn"
        nr_arfcn = pcell.nr_arfcn
        if nr_arfcn is None:
            nr_arfcn = freq_mhz_to_nr_arfcn(pcell.frequency_hz / 1e6)
        lte_dl_earfcn = None

    return BaseStationRequestedConfig(
        radio_technology=pcell.radio_technology,
        channel_kind=channel_kind,
        frequency_mhz=pcell.frequency_hz / 1e6,
        bandwidth_mhz=pcell.bandwidth_mhz,
        band=pcell.band,
        duplex=pcell.duplex,
        nr_arfcn=nr_arfcn,
        lte_dl_earfcn=lte_dl_earfcn,
        lte_transmission_mode=(
            pcell.lte_transmission_mode
            if pcell.radio_technology == "lte"
            else None
        ),
        subcarrier_spacing_khz=pcell.subcarrier_spacing_khz,
        mimo_layers=config.mimo_layers,
        downlink_power_dbm=config.target_tx_power_dbm,
        # 旧 UXM 整带宽功率字段不是跨厂商契约；LTE/CMW 不得消费它。
        downlink_power_dbm_per_bandwidth=(
            config.uxm_dl_power_dbm_per_bw
            if pcell.radio_technology == "nr5g"
            else None
        ),
        port_preset=config.mimo_port_preset,
        scheduler_algorithm=(
            mac_profile.profile.scheduler_algorithm
            if mac_profile is not None
            and mac_profile.profile.kind == "nr_throughput"
            else None
        ),
        csi_rs_ports=(
            mac_profile.profile.csi_rs_ports
            if mac_profile is not None
            and mac_profile.profile.kind == "nr_throughput"
            else None
        ),
    )


def _frequency_identity_from_requested_config(requested: BaseStationRequestedConfig):
    """Return the RAT-aware identity used by the cross-instrument gate."""

    from app.services.mimo_ota.frequency_consistency import ChannelFrequencyIdentity

    if requested.radio_technology == "lte":
        return ChannelFrequencyIdentity.from_lte_earfcn(
            band=requested.band,
            dl_earfcn=requested.lte_dl_earfcn,
            bandwidth_mhz=requested.bandwidth_mhz,
        )
    return ChannelFrequencyIdentity.from_nr_arfcn(
        nr_arfcn=requested.nr_arfcn,
        bandwidth_mhz=requested.bandwidth_mhz,
    )


def _validate_port_preset(
    preset: Optional[str], valid_presets
) -> Optional[str]:
    """P2-11 #1974 (Codex P2 #127): 校验 mimo_port_preset 合法性, 非法 → error message。

    set_cell_config 对 unknown preset 只 log + return False 不 abort → 会静默保留旧端口
    路由 (正是本改要堵的残留)。所以 measure 前置校验, typo → fail-loud。

    - preset is None (TestCase 未指定) → None (不校验; 走 backward-compat 不传路径)。
    - valid_presets is None (mock driver 没 MIMO_PORT_PRESETS) → None (mock-aware skip)。
    - preset 不在合法集 → 返回 error message; 合法 → None。
    """
    if preset is None or valid_presets is None:
        return None
    if preset.lower() not in valid_presets:
        return f"mimo_port_preset={preset!r} 非法 (支持: {list(valid_presets)})"
    return None


def _resolve_base_station_route_snapshot(
    base_station,
    *,
    configured_preset: Optional[str],
    mimo_layers: int,
    inherit: bool,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Return display/audit route metadata without making it a runtime gate.

    Physical connector readback is deliberately optional in P1-73A.  A
    missing or failing adapter readback must leave the logical topology usable
    and surface as resolver warnings; it must never guess connector names.
    """

    default_preset = {1: "siso", 2: "2x2", 4: "4x4"}.get(
        mimo_layers, f"{mimo_layers}x{mimo_layers}"
    )
    effective_preset = (
        configured_preset.strip().lower()
        if isinstance(configured_preset, str) and configured_preset.strip()
        else default_preset
    )
    getter = getattr(base_station, "get_mimo_route_snapshot", None)
    if inherit or not callable(getter):
        return effective_preset, None
    try:
        snapshot = getter(effective_preset)
    except Exception as exc:
        logger.warning(
            "BaseStation route snapshot unavailable for preset %s: %s",
            effective_preset,
            exc,
        )
        return effective_preset, None
    return effective_preset, snapshot if isinstance(snapshot, dict) else None


def _formal_mac_configuration_blocker(
    base_station,
    *,
    plan: BaseStationExecutionPlanItem,
) -> Optional[str]:
    """Return a blocker when real hardware cannot configure this MAC test.

    P2-50：能力判据只来自 execution-frozen 计划项；mock 的 simulated
    语义不变（mock 本来就不进正式 KPI，不需要 MAC 配置 blocker）。
    """

    from app.services.instrument_hal_service import is_mock_driver

    if is_mock_driver(base_station):
        return None
    if plan.planned is not True:
        return (
            "当前基站适配器尚未开放正式 MAC 吞吐配置能力；"
            "为避免沿用旧调度器/FRC 状态，本次结果不得进入正式 KPI。"
            f"（{plan.reason}）"
        )
    return None


def resolve_model_load_requested(emulator, gen_ok: bool, intent):
    """f64.model_loaded 归档用的 requested 真值（P2-29，内审 F1）。

    加载成功 → 驱动真值 `_loaded_emulation_file`（= 发进 CALC:FILT:FILE 的串，
    ASC/B2 是驱动构造的远端路径，config 意图值与之必然不等，直传会把成功的
    加载谎报成 rejected）。加载失败/读不到 → 保持意图值，fail-closed。
    """
    loaded = getattr(emulator, "_loaded_emulation_file", None) if gen_ok else None
    return loaded if loaded else intent



@register_executor(MIMOOTAStepType.MEASURE.value)
class MeasureExecutor(IStepExecutor):
    """Drive the chamber + base station through the azimuth grid, collect KPIs."""

    @staticmethod
    def _all_requested_throughput_is_valid(
        requested_azimuths: List[float],
        azimuth_results: List[Dict[str, Any]],
        *,
        required_scope: Optional[str] = None,
    ) -> bool:
        """Only a complete scan with trusted throughput at every azimuth passes."""
        return (
            bool(requested_azimuths)
            and len(azimuth_results) == len(requested_azimuths)
            and all(
                azimuth.get("throughput_valid") is True
                and (
                    required_scope is None
                    or azimuth.get("throughput_scope") == required_scope
                )
                for azimuth in azimuth_results
            )
        )

    @staticmethod
    def _trusted_throughput_value(
        metrics: Any,
        *,
        required_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> Optional[float]:
        """返回显式可信且口径匹配的 DL average；其余均 fail-closed。"""
        validity = getattr(metrics, "kpi_valid", None)
        if not isinstance(validity, dict):
            return None
        if getattr(metrics, "throughput_scope", None) != required_scope:
            return None
        value = getattr(metrics, "dl_throughput_mbps", None)
        if validity.get("dl_throughput") is not True or value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @staticmethod
    def _trusted_rf_kpi_value(
        metrics: Any,
        *,
        key: str,
        attribute: str,
    ) -> Optional[float]:
        """只接受驱动逐指标显式标真的有限数值。"""
        validity = getattr(metrics, "kpi_valid", None)
        if not isinstance(validity, dict) or validity.get(key) is not True:
            return None
        value = getattr(metrics, attribute, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    @staticmethod
    def _measurement_window_requests(
        manifest: BaseStationAdapterManifest | None,
        *,
        throughput_scope: str,
        requested_sample_count: int,
        simulated_diagnostic: bool,
        statistical_basis_subframes: int,
    ) -> tuple[BaseStationMeasurementWindowRequest, ...]:
        """Freeze one vendor-neutral native-window plan before any window I/O.

        ``statistical_basis_subframes`` is the TestCase's requested statistics
        length (how many subframes this window must accumulate).  It is a
        required argument on purpose: a default here would be exactly the
        "backfill truth from a default" shape the window invariants forbid.
        Vendor parameter domains are checked by each driver against its own
        manual; this layer only freezes what the TestCase asked for.
        """

        if (
            isinstance(requested_sample_count, bool)
            or not isinstance(requested_sample_count, int)
            or requested_sample_count <= 0
        ):
            raise TypeError("requested measurement window count must be positive")
        if isinstance(statistical_basis_subframes, bool) or not isinstance(
            statistical_basis_subframes, int
        ):
            raise TypeError("statistical basis subframes must be an integer")
        if statistical_basis_subframes <= 0:
            raise ValueError("statistical basis subframes must be positive")
        scope_by_runtime_value = {
            ThroughputMetrics.SCOPE_PCELL: "pcell",
            ThroughputMetrics.SCOPE_NR_ALL_CELLS: "all_cells",
        }
        scope = scope_by_runtime_value.get(throughput_scope)
        if scope is None:
            raise ValueError("measurement window scope is not a formal request scope")

        if manifest is None:
            if simulated_diagnostic is not True:
                raise ValueError("frozen manifest has no measurement capability")
            lifecycle = "unavailable"
            cardinality = "requested"
        else:
            if not isinstance(manifest, BaseStationAdapterManifest):
                raise TypeError("measurement plan requires a frozen adapter manifest")
            measurement = manifest.measurement
            if measurement is None:
                if simulated_diagnostic is not True:
                    raise ValueError("frozen manifest has no measurement capability")
                lifecycle = "unavailable"
                cardinality = "requested"
            else:
                if scope not in measurement.scopes:
                    raise ValueError(
                        "measurement window scope is outside the frozen manifest"
                    )
                lifecycle = measurement.lifecycle
                cardinality = measurement.cardinality

        expected_count = 1 if cardinality == "single" else requested_sample_count
        return tuple(
            BaseStationMeasurementWindowRequest(
                schema_version=1,
                scope=scope,
                lifecycle=lifecycle,
                cardinality=cardinality,
                requested_window_count=requested_sample_count,
                expected_window_count=expected_count,
                window_index=index,
                statistical_basis_subframes=statistical_basis_subframes,
            )
            for index in range(expected_count)
        )

    @staticmethod
    async def _measure_base_station_samples(
        base_station: Any,
        *,
        window_s: float,
        throughput_scope: str,
        requested_sample_count: int,
        manifest: BaseStationAdapterManifest | None,
        simulated_diagnostic: bool,
        statistical_basis_subframes: int,
    ) -> List[_BaseStationSample]:
        """Collect only adapter-native structured windows through the common SPI."""

        requests = MeasureExecutor._measurement_window_requests(
            manifest,
            throughput_scope=throughput_scope,
            requested_sample_count=requested_sample_count,
            simulated_diagnostic=simulated_diagnostic,
            statistical_basis_subframes=statistical_basis_subframes,
        )

        samples: List[_BaseStationSample] = []
        for request in requests:
            with capture_scpi_exchanges() as exchanges:
                window = await base_station.measure_base_station_window(
                    window_s,
                    request=request,
                )
            trust = getattr(window, "trust", None)
            if trust is None:
                raise RuntimeError(
                    "BaseStation measurement-window trust receipt is missing"
                )
            if trust.request != request or trust.request_digest != request.digest:
                raise RuntimeError(
                    "BaseStation measurement-window frozen request mismatch"
                )
            if trust.diagnostic_execution_allowed is not True:
                raise _BaseStationWindowBlocked(window)
            samples.append(
                _BaseStationSample(
                    metrics=window.metrics,
                    window=window,
                    exchanges=tuple(exchanges),
                )
            )
        return samples

    @staticmethod
    def _base_station_attempt_context(
        context: StepExecutionContext,
        base_station: Any,
    ) -> _BaseStationAttemptContext:
        """Resolve server-owned frozen/attempt/lease truth for every adapter."""

        from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
        from app.services.base_station_adapter_profile import (
            frozen_mac_profile_from_adapter_freeze,
        )
        from app.services.execution_scpi_evidence import (
            load_base_station_execution_evidence,
        )
        from app.services.instrument_test_lease import (
            active_base_station_lease_identity,
        )
        from app.services.mimo_ota.base_station_execution_evidence import (
            BaseStationExecutionEvidence,
        )

        execution_config = (
            context.test_execution.config
            if isinstance(context.test_execution.config, dict)
            else {}
        )
        frozen = execution_config.get(FREEZE_CONFIG_KEY)
        if not isinstance(frozen, dict):
            raise RuntimeError("BaseStation execution is missing its frozen adapter profile")
        # P2-50: 由当前加载的 adapter 声明推导 live 计划。attempt 路径随后
        # 与 evidence 冻结计划做 digest 对账；无 evidence 的 legacy/unbound
        # 诊断路径直接消费 live 计划（与窗口计划的 manifest=None 形态同构）。
        live_manifest = getattr(base_station, "adapter_manifest", None)
        live_execution_plan = resolve_base_station_execution_plan(
            base_station,
            manifest=live_manifest,
        )
        try:
            frozen_mac_profile = frozen_mac_profile_from_adapter_freeze(frozen)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        # P1-75 站点 B：lease 后、首次 I/O 前，对当前 live manifest 复核
        # 冻结时的兼容性结论；digest 漂移或 verdict 翻转都拒绝进入 I/O。
        # 旧 frozen dict 缺 compatibility → 当时未评估，按既有行为放行。
        compatibility_error = verify_frozen_base_station_compatibility(
            frozen.get("compatibility"),
            live_manifest=live_manifest,
            simulated=getattr(base_station, "simulated", False) is True,
        )
        if compatibility_error is not None:
            raise RuntimeError(
                "BaseStation frozen compatibility re-check failed: "
                + compatibility_error
            )
        resolution = frozen.get("resolution")
        frozen_adapter_id = (
            resolution.get("adapter") if isinstance(resolution, dict) else None
        )
        execution_mode = (
            resolution.get("execution_mode")
            if isinstance(resolution, dict)
            else None
        )
        resolution_status = (
            resolution.get("status") if isinstance(resolution, dict) else None
        )
        if frozen_adapter_id is None:
            if (
                resolution_status != "diagnostic_unbound"
                or execution_mode != "simulated"
                or getattr(base_station, "simulated", False) is not True
            ):
                raise RuntimeError(
                    "unbound BaseStation execution is not an authoritative diagnostic"
                )
            lease_identity = active_base_station_lease_identity()
            if (
                lease_identity is None
                or lease_identity.measurement_attempt_id is not None
                or lease_identity.adapter_id
                != getattr(base_station, "adapter_id", None)
            ):
                raise RuntimeError(
                    "unbound BaseStation diagnostic lease does not match the loaded mock"
                )
            return _BaseStationAttemptContext(
                frozen_adapter=frozen,
                attempt_id=None,
                lease_identity=lease_identity,
                simulated_diagnostic=True,
                execution_plan=live_execution_plan,
                mac_profile=frozen_mac_profile,
            )
        if (
            not isinstance(frozen_adapter_id, str)
            or frozen_adapter_id != getattr(base_station, "adapter_id", None)
        ):
            raise RuntimeError(
                "BaseStation loaded adapter does not match the frozen execution adapter"
            )
        simulated_diagnostic = execution_mode == "simulated"
        if simulated_diagnostic:
            if getattr(base_station, "simulated", False) is not True:
                raise RuntimeError(
                    "BaseStation simulated execution is not using the authoritative mock"
                )
        elif getattr(base_station, "simulated", False) is True:
            raise RuntimeError("real execution cannot use a simulated BaseStation adapter")

        raw_evidence = load_base_station_execution_evidence(context.test_execution)
        if raw_evidence is None:
            from app.services.mimo_ota.base_station_execution_evidence import (
                base_station_metric_projection_required,
            )

            execution_config = context.test_execution.config or {}
            if base_station_metric_projection_required(execution_config):
                raise RuntimeError(
                    "BaseStation execution evidence is missing before MEASURE"
                )
            lease_identity = active_base_station_lease_identity()
            if (
                lease_identity is None
                or lease_identity.measurement_attempt_id is not None
                or lease_identity.adapter_id != frozen_adapter_id
            ):
                raise RuntimeError(
                    "legacy BaseStation lease does not match the frozen adapter"
                )
            return _BaseStationAttemptContext(
                frozen_adapter=frozen,
                attempt_id=None,
                lease_identity=lease_identity,
                simulated_diagnostic=simulated_diagnostic,
                execution_plan=live_execution_plan,
                mac_profile=frozen_mac_profile,
            )
        evidence = BaseStationExecutionEvidence.model_validate(raw_evidence)
        if evidence.adapter != frozen_adapter_id:
            raise RuntimeError("BaseStation evidence adapter does not match frozen adapter")
        # P2-50: 本次 attempt 的 evidence 由同一会话在首个测量 I/O 前冻结，
        # 计划必须在场且与当前加载 adapter 推导结果一致；缺席/漂移都是缺陷。
        if (
            evidence.execution_plan_contract_version != 1
            or evidence.execution_plan is None
        ):
            raise RuntimeError(
                "BaseStation execution plan is not frozen for the current attempt"
            )
        if evidence.execution_plan.digest != live_execution_plan.digest:
            raise RuntimeError(
                "BaseStation frozen execution plan does not match the loaded adapter"
            )
        attempt_id = evidence.current_measurement_attempt_id
        if not attempt_id or evidence.current_measurement_attempt_state != "running":
            raise RuntimeError("BaseStation current measurement attempt is not running")
        lease_identity = active_base_station_lease_identity()
        if (
            lease_identity is None
            or lease_identity.measurement_attempt_id != attempt_id
            or lease_identity.adapter_id != frozen_adapter_id
        ):
            raise RuntimeError(
                "BaseStation active lease is not bound to the current attempt"
            )
        return _BaseStationAttemptContext(
            frozen_adapter=frozen,
            attempt_id=attempt_id,
            lease_identity=lease_identity,
            simulated_diagnostic=simulated_diagnostic,
            execution_plan=live_execution_plan,
            mac_profile=frozen_mac_profile,
        )

    @staticmethod
    async def _configure_requested_secondary_cells(
        base_station: Any,
        scells: List[Any],
        *,
        plan: BaseStationExecutionPlanItem,
        inherit: bool,
        execution_id: Any,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """配置并确认完整 CA 集合；任何未知/部分成功都阻断正式采样。

        P2-50：能力判据只来自 execution-frozen 计划项。计划未 planned →
        在首次 SCell 写入前阻断（沿用既有 fail-closed 语义）；计划 planned
        但 adapter 缺方法 → 计划/实现漂移，fail-loud。
        """
        if not scells:
            return [], None
        if inherit:
            return [], (
                "CA TestCase 不能使用 base_station_config_mode=inherit：本次没有 SCell "
                "写入与激活真值；请改用 dispatch 模式。"
            )
        if plan.planned is not True:
            return [], f"正式 CA 未列入执行计划：{plan.reason}。"

        add_secondary_cell = getattr(base_station, "add_secondary_cell", None)
        activate_secondary_cells = getattr(
            base_station,
            "activate_secondary_cells",
            None,
        )
        if not callable(add_secondary_cell) or not callable(
            activate_secondary_cells
        ):
            missing = [
                name
                for name, method in (
                    ("add_secondary_cell", add_secondary_cell),
                    ("activate_secondary_cells", activate_secondary_cells),
                )
                if not callable(method)
            ]
            raise RuntimeError(
                "执行计划声明 SCell 能力，但 adapter 缺 "
                f"{'/'.join(missing)}（计划与实现漂移）"
            )

        added: List[Dict[str, Any]] = []
        for cc_idx, scell in enumerate(scells, start=1):
            try:
                ok = await add_secondary_cell(
                    cc_idx,
                    {
                        "frequency_mhz": scell.frequency_hz / 1e6,
                        "bandwidth_mhz": scell.bandwidth_mhz,
                        "scs_khz": scell.subcarrier_spacing_khz,
                        "band": scell.band,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                return added, f"SCell {cc_idx} 添加异常：{exc}"
            if ok is not True:
                return added, (
                    f"SCell {cc_idx} 添加失败；已阻断正式 CA，防止少载波 KPI 入报告。"
                )
            added.append({
                "cc_index": cc_idx,
                "frequency_ghz": scell.frequency_hz / 1e9,
                "bandwidth_mhz": scell.bandwidth_mhz,
                "band": scell.band,
            })

        try:
            activated = await activate_secondary_cells(
                expected_indices=[item["cc_index"] for item in added],
            )
        except Exception as exc:  # noqa: BLE001
            return added, f"SCell 激活异常：{exc}"
        if activated is not True:
            return added, "SCell 激活未获确认；已阻断正式 CA 吞吐采样。"

        logger.info(
            "[%s] Phase 2g: 已添加并激活 %d 个 SCell",
            execution_id,
            len(added),
        )
        return added, None

    @staticmethod
    def _mac_config_blocker(mac_cfg: Any) -> Optional[str]:
        """MAC 吞吐量配置的结果够不够格**继续测**；不够就返回给操作员的原因。

        `None` = 可以继续。抽成独立方法是为了**能打行为门** —— 内嵌在
        `execute()` 里时只能靠源码文本判，而把 `or` 改成 `and` 那种变异
        在 138 个用例下**全绿**（内审 F3 实证）。

        形态空间（内审 F2）：
          · 结构体 → `__bool__` 即 `ok`（必要项齐 **且** 无异常）；
          · 旧布尔契约 `True` → 放行、`False` → 拦；
          · `None`（驱动啥都没做）→ 拦。
        """
        if mac_cfg is True:                 # 旧布尔契约：全好
            return None
        if mac_cfg:                         # 结构体 ok
            return None
        missing = tuple(getattr(mac_cfg, "missing_mandatory", ()) or ())
        err = getattr(mac_cfg, "error", None)
        # ⚠ 内审 F4：`rejected`（发出去被仪器拒）此前没有分支 ——
        #   落到 else 里被贴上「驱动报告配置失败：（无详情）」，
        #   而"哪几组被拒"正是 P1-33 要产出的**现场实测答案**。
        rejected = tuple(getattr(mac_cfg, "rejected", ()) or ())
        if rejected and not missing and not err:
            return (
                f"P1-33: 3GPP MAC 吞吐量配置**被仪器拒了** {len(rejected)} 组: "
                f"{', '.join(rejected)}。命令形式取自厂商手册，但该 Test App "
                f"是否支持**本来就是本片要现场问的** —— 这就是答案。"
                f"把这份清单填回 roadmap P1-33，再决定换哪条命令形式。"
                "配置未受控时测得的吞吐量不是 3GPP MAC 层吞吐量结果，**不能继续测**。"
            )
        # ⚠ **`error` 优先于 `missing`**（Codex #279 P2）—— 传输层炸了却报
        #   "profile 未定义"，会把操作员指向 P1-33 补命令，而真正要修的是
        #   VISA 连接。两者可以同时成立，所以两段都要说，但**先说真凶**。
        if err:
            return (
                f"P1-32: 3GPP MAC 吞吐量配置未生效 —— **下发过程中出错**: {err}。"
                f"已发出 {len(getattr(mac_cfg, 'applied', ()) or ())} 条、"
                f"跳过 {len(getattr(mac_cfg, 'skipped', ()) or ())} 条；"
                f"其余命令**未及下发**。"
                + (f"（另：本 profile 未定义 {len(missing)} 条必要命令 "
                   f"{', '.join(missing)}，见 P1-33 —— 但**先查上面那个错误**）"
                   if missing else "")
                + "**先排查仪器连接/超时，不要据此改 profile。**"
                "配置未受控时测得的吞吐量不是 3GPP MAC 层吞吐量结果，**不能继续测**。"
            )
        # ⚠️ 2026-08-07 现场血泪：这里此前对所有 `missing` 一律说
        #   「**本 profile 未定义**」。但 `missing_mandatory` 是
        #   `mandatory ∩ skipped`，而 `skipped` 有**两种成因**：
        #     ① profile 上这条命令真是 None（真缺口）
        #     ② 命令在，但**值翻译失败/校验不过导致整组没发**
        #   ②的情况下那句话是**假话**，而它当天把诊断带偏了两次：
        #   先据此把 fail-loud 门降级（以为手册没这命令），
        #   再据此准备"补命令"（那 6 条 TDD 命令 P1-33 早就补进 profile 了，
        #   真凶是 `tdd_pattern` 翻不成手册的六个数形态）。
        #   现在按 `undefined_on_profile` 分开说 —— **说不出成因就别断言成因**。
        undefined = tuple(getattr(mac_cfg, "undefined_on_profile", ()) or ())
        not_dispatched = tuple(n for n in missing if n not in undefined)
        return (
            "P1-32: 3GPP MAC 吞吐量配置未生效 —— "
            + ((
                (f"**本驱动的 profile 未定义** {len(undefined)} 条必要命令: "
                 f"{', '.join(undefined)}。⚠ 该 Test App 到底支不支持这些命令"
                 f"**未经查证** —— 手册的 `Application Mode` 字段答不了这个问题"
                 f"（我们 profile 里已定义、现场在用的 `BAND`/`DL:ARFCN`/`DL:BW` "
                 f"同样标 `NSA | SA` 不含 `IRAT`），且这批命令从未被真机普查过。"
                 f"**别据此下结论** —— 出发前用 `uxm_scpi_compatibility` 普查确认"
                 f"（⚠ 该序列跳过 None 模板，要先临时补进去才探得到）。见 P1-33。"
                 if undefined else "")
                + (f"**命令在 profile 里但整组没下发** {len(not_dispatched)} 条: "
                   f"{', '.join(not_dispatched)} —— **不是 profile 缺项**，"
                   f"是参数值翻不成手册形态或自洽性校验没过（如 TDD pattern "
                   f"排布/周期/SCS 对不上）。**真正的原因在上一条驱动 ERROR 日志里**，"
                   f"照那条改配置，别来补命令。"
                   if not_dispatched else "")
              ) if missing else
               f"驱动报告配置失败: {err or '（无详情，返回值 %r）' % (mac_cfg,)}。")
            + "AMC / 固定 MCS / 全 RB / TDD 格式 / CSI-RS 端口未受控时，"
            "测得的吞吐量反映的是**基站调度器行为**而非 DUT 的 MIMO 能力，"
            "不是 3GPP MAC 层吞吐量结果，**不能继续测**。"
        )

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        lab = context.require_lab_profile()
        config = load_mimo_ota_config(context.test_execution)
        pcell = config.primary_carrier

        from app.services.channel_engine_client import ChannelEngineClient
        from app.services.channel_generation.asc_strategy import (
            ExternalWaveformStrategy,
        )
        from app.services.channel_generation.base_generator import EngineMode
        from app.services.channel_generation.b2_parametric_strategy import (
            B2ParametricTdlStrategy,
        )
        from app.services.channel_generation.external_asc_strategy import (
            ExternalAscPathStrategy,
        )
        from app.services.channel_generation.gcm_strategy import NativeModelStrategy
        from app.services.instrument_hal_service import get_hal_service, is_mock_driver
        from app.services.mimo_ota.cleanup import cleanup_chamber_instruments
        from app.services.mimo_ota.channel_asset_resolver import (
            ChannelAssetResolveError,
            resolve_channel_asset,
        )
        from app.services.mimo_ota.emulation_file_gate import (
            evaluate_emulation_file_gate,
        )
        from app.services.mimo_ota.switch_mode_gate import (
            evaluate_switch_mode_gate,
        )
        from app.services.mimo_ota.switch_orchestrator import (
            orchestrate_switch_topology,
        )
        from app.services.probe_pattern.consumer import (
            get_probe_gain_at_azimuth,
            select_active_probe_id,
            select_active_rf_chain_probe_id,
        )
        from app.hal.channel_emulator import ChannelLoadMode
        from app.hal.positioner import (
            current_positioner_operation_stop_generation,
        )
        from app.hal.scpi_evidence import EvidenceLevel, capture_scpi_exchanges
        from app.services.execution_scpi_evidence import (
            record_f64_command_capture,
            record_positioner_capture,
            record_base_station_config_capture,
            record_base_station_throughput_capture,
            register_required_scpi_evidence,
        )
        from app.services.path_loss_calibration_service import (
            ProbePathLossCalibrationService,
        )
        from app.services.positioner_coordinate_profile import (
            FREEZE_CONFIG_KEY as POSITIONER_COORDINATE_FREEZE_CONFIG_KEY,
            validate_frozen_positioner_before_motion,
        )

        hal = get_hal_service()
        chamber: ChamberConfiguration = lab.chamber_config
        if chamber is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message=f"LabProfile {lab.name} has no chamber_config",
            )

        # P2-23: 显式 ChannelAsset 必须在任何仪表连接/配置前完成解析与 active 门。
        # 历史记录仍可读，但退役资产不得用于新的 MEASURE。
        try:
            resolved_asset = resolve_channel_asset(context.db, config)
        except ChannelAssetResolveError as e:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED, error_message=str(e)
            )
        if resolved_asset is not None:
            config.engine_mode = resolved_asset.engine_mode
            # ChannelAsset 是唯一信道源：清掉保存用例中的 legacy 残留引用。
            config.cdl_profile_id = None
            config.scd_id = None
            if resolved_asset.cdl_model_name:
                config.cdl_model_name = resolved_asset.cdl_model_name
            # vendor_file authoritative：None 也必须覆盖旧 .smu，避免 declared-only
            # 资产被保存用例中的 stale 路径绕过。
            if resolved_asset.engine_mode == EngineMode.GCM_NATIVE.value:
                config.emulation_file = resolved_asset.emulation_file

        emulator = hal.drivers.get("channelEmulator")
        channel_emulator_is_real = (
            emulator is not None and not is_mock_driver(emulator)
        )
        pl_service = ProbePathLossCalibrationService(context.db, use_mock=False)
        path_loss_selection = pl_service.resolve_latest_calibration(
            chamber.id,
            pcell.frequency_hz / 1e6,
            operating_mode=config.switch_mode_id,
            require_real=channel_emulator_is_real,
        )
        if path_loss_selection.certificate is None and channel_emulator_is_real:
            # 保留任意来源候选的身份，让 strict/bypass 能准确叙述“被拒绝”，
            # 但只有下方 provenance 门裁决后的 path_loss_cert 才能进入计算。
            path_loss_selection = pl_service.resolve_latest_calibration(
                chamber.id,
                pcell.frequency_hz / 1e6,
                operating_mode=config.switch_mode_id,
            )
        selected_path_loss_cert = path_loss_selection.certificate
        selected_path_loss_use_mock = (
            selected_path_loss_cert.use_mock
            if selected_path_loss_cert is not None
            else None
        )
        if selected_path_loss_cert is None:
            path_loss_cert_usable = False
            provenance_blocker = (
                "path-loss calibration is missing or expired; real measurement "
                "strict mode requires a currently valid explicit-real certificate"
                if channel_emulator_is_real and config.precheck_strict_cal
                else None
            )
        else:
            path_loss_cert_usable, provenance_blocker = (
                _evaluate_path_loss_provenance_for_measure(
                    selected_path_loss_use_mock,
                    channel_emulator_is_real=channel_emulator_is_real,
                    strict=config.precheck_strict_cal,
                    diagnostic=execution_evidence_blocks_formal_outputs(
                        context.test_execution
                    ),
                )
            )
        path_loss_cert = (
            selected_path_loss_cert if path_loss_cert_usable else None
        )
        path_loss_gate_mode = (
            "mock_not_applicable"
            if not channel_emulator_is_real
            else "strict"
            if config.precheck_strict_cal
            else "operator_bypass"
        )
        path_loss_application = build_path_loss_application(
            selected_certificate=selected_path_loss_cert,
            applied_certificate=path_loss_cert,
            selection_reason=path_loss_selection.reason,
            gate_mode=path_loss_gate_mode,
        )
        if provenance_blocker is not None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                measurements={"path_loss_application": path_loss_application},
                error_message=(
                    "P1-27 calibration provenance gate failed before hardware "
                    f"connect: {provenance_blocker}"
                ),
            )
        if selected_path_loss_cert is not None and path_loss_cert is None:
            logger.warning(
                "[%s] P1-27: ignoring untrusted path-loss certificate %s "
                "(use_mock=%r) for real measurement; strict gate was explicitly "
                "bypassed, continuing without path-loss compensation",
                context.test_execution.id,
                selected_path_loss_cert.id,
                selected_path_loss_use_mock,
            )

        positioner = hal.drivers.get("positioner")
        base_station = hal.drivers.get("baseStation")
        if positioner is None or base_station is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="positioner + baseStation drivers required (HAL)",
            )
        execution_config = (
            context.test_execution.config
            if isinstance(context.test_execution.config, dict)
            else {}
        )
        frozen_positioner = execution_config.get(
            POSITIONER_COORDINATE_FREEZE_CONFIG_KEY
        )
        if not isinstance(frozen_positioner, dict):
            if is_mock_driver(positioner):
                frozen_positioner = {
                    "resolution": {
                        "schema_version": 1,
                        "adapter": None,
                        "status": "diagnostic_unbound",
                        "execution_mode": "simulated",
                    },
                    "profile": None,
                }
            else:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "转台坐标 profile 未在 execution 中冻结；"
                        "已在任何转台连接或动作前中止。"
                    ),
                )
        positioner_validation_error = validate_frozen_positioner_before_motion(
            hal,
            frozen_positioner,
        )
        if positioner_validation_error:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message=(
                    "转台执行冻结坐标与当前驱动不一致；"
                    f"已在任何转台连接或动作前中止: {positioner_validation_error}"
                ),
            )
        base_station_attempt = self._base_station_attempt_context(
            context,
            base_station,
        )
        stop_generation_reader = getattr(
            positioner, "operator_stop_generation", None
        )
        retained_stop_generation = (
            current_positioner_operation_stop_generation.get()
        )
        motion_stop_generation = retained_stop_generation
        if motion_stop_generation is None and callable(stop_generation_reader):
            motion_stop_generation = stop_generation_reader()
        motion_stop_kwargs = (
            {"expected_operator_stop_generation": motion_stop_generation}
            if motion_stop_generation is not None
            else {}
        )
        simulated_sources = [
            category
            for category in ("baseStation", "channelEmulator", "positioner")
            if (driver := hal.drivers.get(category)) is None
            or bool(getattr(driver, "simulated", is_mock_driver(driver)))
        ]
        measurement_simulated = bool(simulated_sources)

        await positioner.connect()
        await base_station.connect()
        # Anything from here through the azimuth loop must be wrapped so an
        # exception (HAL hiccup, channel-gen timeout, DUT drop) doesn't leave
        # base-station signaling, F64 emulating, and the turntable mid-rotation.
        cleanup_warnings: List[str] = []
        pending_base_station_windows: List[tuple[float, Any]] = []
        ca_setup_blocker: Optional[str] = None
        base_station_config_capture_manager = None
        base_station_config_exchanges = []
        try:
            # --- Phase 2g: PCell from component_carriers[0] (always populated
            # by MIMOOTAConfiguration._resolve_component_carriers); SCells
            # added below before attach so RRC reconfig sees full set.
            ccs = list(config.component_carriers or [])
            scells = ccs[1:]

            # P2-11 (Codex on PR #109 P1): 从 TestCase 中心频推导规范 ARFCN 显式下发。
            # 不传 arfcn 时既有 NR adapter 的 set_cell_config 走 band fallback (R6 起 =
            # EMQuest 基线, N78→636666=3549.99 MHz), 让 UXM 实际下发频率 ≠ TestCase,
            # 下面的频率一致性校验会正确判失败 → 任何 TestCase 频率 ≠ band fallback
            # 的真实 run 都被误杀。ARFCN 是频率真值 (frequency_mhz 只是派生视图), 必须显式驱动。
            pcell_freq_mhz = pcell.frequency_hz / 1e6
            # P2-11 #1974 Codex P2 #127: mimo_port_preset typo 前置 fail-loud (set_cell_config
            # 对 unknown preset 只 log+return False 不 abort → 静默保留旧路由)。mock-aware。
            _preset_err = _validate_port_preset(
                config.mimo_port_preset,
                getattr(base_station, "MIMO_PORT_PRESETS", None),
            )
            if _preset_err:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        f"P2-11 #1974: {_preset_err}。typo 会让 set_cell_config 静默保留旧路由。"
                    ),
                )
            # 开关 1 (base_station_config_mode): "inherit" 跳过小区参数下发, 沿用仪器当前
            # 态 (如 EMQuest 基线); 频率核对改走下方一致性网的 live 读回 (知情
            # 继承)。MAC 吞吐配置 / attach / RRC reconfig 不属于小区
            # 参数, 两种模式都执行。
            base_station_inherit = config.base_station_config_mode == "inherit"
            pcell_requested_config = _build_pcell_requested_config(
                config,
                mac_profile=base_station_attempt.mac_profile,
            )
            pcell_channel_number = (
                pcell_requested_config.nr_arfcn
                if pcell_requested_config.radio_technology == "nr5g"
                else pcell_requested_config.lte_dl_earfcn
            )
            # 即使选择 inherit，也必须把“本次 TestCase 期望的 PCell 配置”登记为
            # mandatory。inherit 路径当前没有同事务写入/回读/APPLY 证据，因此应在
            # 正式判定中保持 missing/unknown，不能因跳过控制动作而从证据门消失。
            register_required_scpi_evidence(
                context.test_execution,
                requirement_id="base_station.pcell.config_applied",
                evidence_key="base_station.config_apply",
                requested=pcell_channel_number,
                required_evidence_level=EvidenceLevel.APPLIED,
            )
            context.db.commit()
            if base_station_inherit:
                logger.info(
                    "[%s] 开关1 base_station_config_mode=inherit: 跳过基站小区级参数下发 "
                    "(set_cell_config + SCell), 沿用仪器当前态; 频率核对走 live "
                    "读回。仍会写: MAC 吞吐配置 / CELL ON / RRC 按 TestCase 推 "
                    "%d 层 (层数未纳入 live 核对) / 输入闭环调 DL 功率",
                    context.test_execution.id, config.mimo_layers,
                )
            # path B 显式驱动端口路由/调度 (见 _build_pcell_cell_config); None 字段不传 →
            # 保持 HAL profile (backward-compat, 旧 case 不被默认值覆盖)。
            if not base_station_inherit:
                # 配置事务跨越 set_cell_config 与 attach：CELL 已 ON 时
                # 走 APPLY；初始 OFF 时手册规定后续 CELL ON 自动应用。两条合法
                # recipe 必须留在同一 capture，不能依赖执行前仪器恰好为 ON。
                base_station_config_capture_manager = capture_scpi_exchanges()
                base_station_config_exchanges = (
                    base_station_config_capture_manager.__enter__()
                )
                # Codex #195 R5 P1: set_cell_config 布尔契约必须消费 — HAL 层回读对账
                # mismatch / 下发被拒都只 return False (不裸抛), 这里不检查会带着错配
                # 小区配置进测量, 正是回读门要拦的实验污染。
                # 先落“必需项”，即使 HAL 调用随后异常/进程中断，收尾也会显示
                # missing，而不是空集合误绿。
                config_receipt = await base_station.apply_config(
                    pcell_requested_config,
                )
                route_receipt = await base_station.apply_route(
                    base_station_attempt.frozen_adapter
                )
                from app.services.execution_scpi_evidence import (
                    confirm_base_station_configuration_and_route,
                )

                if base_station_attempt.attempt_id is not None:
                    confirm_base_station_configuration_and_route(
                        context.db,
                        context.test_execution.id,
                        attempt_id=base_station_attempt.attempt_id,
                        lease_identity=base_station_attempt.lease_identity,
                        config_receipt=config_receipt,
                        route_receipt=route_receipt,
                    )
                    context.db.commit()
                if config_receipt.diagnostic_execution_allowed is not True:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "PCell set_cell_config 失败 (下发被拒或回读对账 mismatch, "
                            "明细见基站驱动日志) — 中止执行, 防止错配配置进测量。"
                        ),
                    )
                if not base_station.route_allows_diagnostic_execution(route_receipt):
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "BaseStation execution route 未获足够权威确认；"
                            f"中止执行: {route_receipt.reason}"
                        ),
                    )

            # --- Phase 2g: SCell add + activate for CA scenarios ---
            scells_added, ca_blocker = await self._configure_requested_secondary_cells(
                base_station,
                scells,
                plan=base_station_attempt.execution_plan.scell,
                inherit=base_station_inherit,
                execution_id=context.test_execution.id,
            )
            if ca_blocker:
                # Do not construct the failure result until cleanup has run:
                # a partial SCell add can leave residual cells, and a rejected
                # removal must be visible to the operator rather than lost by
                # returning from inside this try block.
                raise _CaSetupBlocked(ca_blocker)
            throughput_scope = (
                ThroughputMetrics.SCOPE_NR_ALL_CELLS
                if scells
                else ThroughputMetrics.SCOPE_PCELL
            )

            # --- 3GPP MAC throughput config (was hard-coded; now from TestCase) ---
            # P1-32: 返回值**必须消费**。上一版丢弃它、然后无条件 attach
            # —— 于是「一条都没配上」与「全配好了」在这里长得一模一样，测试照常
            # 在**没配置过的链路**上跑完，数却当 3GPP 合规结果用。
            # 同构先例见本文件 mimo_port_preset 前置门（driver 静默不生效 →
            # 调用方 fail-loud）；CMW 尚无手册支撑的同类配置，只允许保留
            # UNKNOWN 诊断值，不得用默认 fallback 恢复正式 KPI。
            _mac_capability_blocker = _formal_mac_configuration_blocker(
                base_station,
                plan=base_station_attempt.execution_plan.mac_throughput,
            )
            if _mac_capability_blocker:
                logger.warning(
                    "[%s] BaseStation MAC configuration unconfirmed; continuing "
                    "diagnostic measurement with formal KPI forced UNKNOWN: %s",
                    context.test_execution.id,
                    _mac_capability_blocker,
                )
                if (
                    not base_station_inherit
                    and base_station_attempt.attempt_id is not None
                ):
                    from app.services.execution_scpi_evidence import (
                        mark_base_station_configuration_unconfirmed,
                    )

                    mark_base_station_configuration_unconfirmed(
                        context.db,
                        context.test_execution.id,
                        attempt_id=base_station_attempt.attempt_id,
                    )
                    context.db.commit()
            if base_station_attempt.execution_plan.mac_throughput.planned is True:
                # P2-50: 计划 planned 但 adapter 缺方法 = 计划/实现漂移，fail-loud。
                if not callable(
                    getattr(base_station, "configure_mac_throughput_test", None)
                ):
                    raise RuntimeError(
                        "执行计划声明 MAC 吞吐配置能力，但 adapter 缺 "
                        "configure_mac_throughput_test（计划与实现漂移）"
                    )
                frozen_mac_profile = base_station_attempt.mac_profile
                if frozen_mac_profile is None:
                    raise RuntimeError(
                        "execution-frozen BaseStation MAC profile is missing"
                    )
                mac_cfg = await base_station.configure_mac_throughput_test(
                    frozen_mac_profile
                )
                if base_station_attempt.attempt_id is not None:
                    from app.services.execution_scpi_evidence import (
                        confirm_base_station_mac_profile,
                    )

                    confirm_base_station_mac_profile(
                        context.db,
                        context.test_execution.id,
                        attempt_id=base_station_attempt.attempt_id,
                        lease_identity=base_station_attempt.lease_identity,
                        result=mac_cfg,
                    )
                    context.db.commit()
                # ⚠ 判定收窄进 `_mac_config_blocker`（内审 F3）—— 内嵌时
                #   只能靠源码文本判，`or`→`and` 那种变异在 138 个用例下全绿。
                _blocker = self._mac_config_blocker(mac_cfg)
                if _blocker:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=_blocker,
                    )

            # --- RF 冷启动初始化：第一次 attach 前准备本次信道与工作点 ---
            # 2026-08-07 的旧顺序在这里先发起 attach，成功后才加载
            # .smu；这会依赖 F64 上一轮遗留模型/频率/STATIC。以下整段完成后才
            # 允许第一次 attach，任何失败都直接返回。
            ce_client = ChannelEngineClient(context.db)
            if emulator is None:
                from app.hal.channel_emulator import MockChannelEmulator

                logger.warning(
                    "[%s] No channelEmulator in HAL — falling back to MockChannelEmulator",
                    context.test_execution.id,
                )
                emulator = MockChannelEmulator(
                    instrument_id="mock_ce_mimo_ota",
                    config={"model": "Mock"},
                )
                await emulator.connect()

            # --- Phase 2c: resolve TestCase-driven switch mode for this chamber ---
            # P2-11 Phase 3: mode_id 由 TestCase.switch_mode_id 驱动 (chamber active
            # SwitchTopology + TestCase 选哪个 operating mode), 不再硬编码 "mimo_ota"。
            # CAICT 固定布线时这是 *declaration check* 非 live switching: surface
            # topology id/mode/CE→probe 绑定供下游 channel-gen 消费。无 active topology
            # row = warning (固定布线手工接线, 见下面门放行); 有 topology 但请求 mode
            # 不提供 = strict FAIL (switch_mode_gate)。
            effective_port_preset, route_snapshot = (
                _resolve_base_station_route_snapshot(
                    base_station,
                    configured_preset=config.mimo_port_preset,
                    mimo_layers=int(config.mimo_layers),
                    inherit=base_station_inherit,
                )
            )
            base_station_port_mapping = resolve_base_station_port_mapping(
                adapter_id=str(getattr(base_station, "adapter_id", "unknown")),
                mimo_port_preset=effective_port_preset,
                mimo_layers=int(config.mimo_layers),
                route_snapshot=route_snapshot,
            )
            topology_result = orchestrate_switch_topology(
                context.db,
                chamber.id,
                mode_id=config.switch_mode_id,
                base_station_port_mapping=base_station_port_mapping,
            )
            if topology_result.success:
                logger.info(
                    "[%s] Phase 2c: switch topology '%s' v%s mode=%s, %d probe bindings",
                    context.test_execution.id,
                    topology_result.topology_name,
                    topology_result.topology_version,
                    topology_result.mode_id,
                    len(topology_result.probe_bindings),
                )
            else:
                for w in topology_result.warnings:
                    logger.warning("[%s] %s", context.test_execution.id, w)
            # P2-11 Phase 3 门: 有 active topology 但 TestCase 请求的 mode 未解析 →
            # strict FAIL (无 topology row 时放行 —— 固定布线 orchestrator 已 warn)。
            switch_gate = evaluate_switch_mode_gate(
                topology_present=topology_result.topology_id is not None,
                mode_resolved=topology_result.success,
                requested_mode_id=config.switch_mode_id,
                strict=config.precheck_strict_switch_mode,
            )
            if switch_gate.should_fail:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=switch_gate.message,
                )
            if switch_gate.should_warn:
                logger.warning(
                    "[%s] %s", context.test_execution.id, switch_gate.message
                )

            # P2-11 Phase 3 (Codex on PR #111): 校准 cert 按 TestCase 的 switch
            # operating mode 过滤 —— 否则多 mode 同频校准的 lab 会喂错 RF 通路的损耗。
            calibration_entries = ce_client._query_calibration_entries(
                chamber.id, pcell.frequency_hz, chamber,
                operating_mode=config.switch_mode_id,
                path_loss_calibration=path_loss_cert,
                phase_use_mock=not channel_emulator_is_real,
            )

            # --- Phase 2a / P0: path-loss compensation ---
            # Old: chamber-wide avg (`avg_path_loss_db`) applied uniformly.
            # New: per-RFChain `total_insertion_loss_db` looked up by
            #   (active_probe_id, polarization) → connection_id, populated
            #   when the cert was created via /calibration/path-loss/start-for-lab.
            # Falls back to avg when the cert is legacy (no per-chain map) so
            # existing chamber-keyed calibrations still work.
            if path_loss_cert is not None:
                avg_path_loss_db = float(path_loss_cert.avg_path_loss_db or 0.0)
                per_chain_pl: Dict[str, Any] = (
                    getattr(path_loss_cert, "path_loss_db_by_rf_chain", None) or {}
                )
                logger.info(
                    "[%s] Phase 2a/P0: path-loss avg=%.2f dB cert=%s mode=%s "
                    "(req=%s, per-chain entries: %d)",
                    context.test_execution.id,
                    avg_path_loss_db, path_loss_cert.id,
                    getattr(path_loss_cert, "operating_mode", None),
                    config.switch_mode_id, len(per_chain_pl),
                )
            else:
                avg_path_loss_db = 0.0
                per_chain_pl = {}
                logger.warning(
                    "[%s] Phase 2a: no path-loss calibration for chamber %s @ %.0f MHz; "
                    "RSRP baseline uncompensated",
                    context.test_execution.id,
                    chamber.id,
                    pcell.frequency_hz / 1e6,
                )

            # P0: invert per_chain_pl into a (probe_id, pol) → total_insertion_loss_db map.
            # Each entry already has probe_id + polarization stamped at calibration
            # time, so we don't have to re-resolve the topology here — saving a
            # query and keeping the compensation pinned to whatever topology was
            # active when the cert was issued.
            chain_pl_by_probe_pol: Dict[tuple, float] = {}
            for entry in per_chain_pl.values():
                if not isinstance(entry, dict):
                    continue
                pid = entry.get("probe_id")
                pol = entry.get("polarization")
                total = entry.get("total_insertion_loss_db")
                if pid is not None and pol and total is not None:
                    chain_pl_by_probe_pol[(int(pid), str(pol).upper())] = float(total)

            # P2-12 slice 4: scd_id 引用优先于裸 emulation_file。但 SCD/.smu **只 GCM 相关**
            # (ASC 按 frequency 生成 .asc 不用 .smu)。这里给 ASC / 非 GCM 路径的默认值: 裸
            # emulation_file (ASC strategy 忽略它) + 无 SCD 频率 (不进一致性网)。SCD 解析只在
            # 下方 GCM 分支做 —— Codex on #122: 在 GCM 选了 SCD 再切 ASC 时 config 残留 scd_id,
            # 不该让 ASC run 去 resolve (SCD 删了/非法会误 fail) 或撞 SCD 频率门 (ASC 不用 SCD)。
            resolved_emulation_file = config.emulation_file
            scd_freq_identity = None

            engine_mode = EngineMode(config.engine_mode)
            if engine_mode == EngineMode.GCM_NATIVE:
                supported = emulator.get_supported_load_modes()
                if ChannelLoadMode.NATIVE_MODEL not in supported:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            f"channelEmulator ({type(emulator).__name__}) does not support "
                            f"native model loading; engine_mode=GCM_NATIVE rejected. "
                            f"Supported modes: {[m.value for m in supported]}"
                        ),
                    )
                generator = NativeModelStrategy(emulator, chamber, calibration_entries)
                # P2-12 slice 4: 只在 GCM 分支 resolve scd_id → SCD (associated .smu + 声明
                # ARFCN 喂下方频率门)。ASC config 残留的 scd_id 在此不触发 (Codex on #122)。
                from app.services.standard_channel_service import (
                    StandardChannelError,
                    resolve_emulation_for_measure,
                )
                try:
                    resolved_emulation_file, scd_freq_identity = resolve_emulation_for_measure(
                        context.db,
                        scd_id=config.scd_id,
                        fallback_emulation_file=config.emulation_file,
                    )
                except (StandardChannelError, ValueError) as e:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=f"P2-12 slice 4: scd_id={config.scd_id} 无效/不存在: {e}",
                    )
                # vendor_file ChannelAsset (清了 scd_id 不走 SCD 表): scd_config 声明频率从
                # resolver 喂频率一致性网, 否则 .smu 文件名不可解析时选错频率文件也通过
                # (Codex #174 复查 P2)。
                if resolved_asset is not None and resolved_asset.scd_freq_identity is not None:
                    scd_freq_identity = resolved_asset.scd_freq_identity
                # P2-11 Phase 2: GCM 的 .smu 必须由 TestCase 驱动 (路径 B), 不能静默
                # fallback 到 F64 驱动默认 .smu —— 默认频率可能跟 TestCase 错配。strict
                # 默认 FAIL; opt-out (bring-up 路径 A) 降级 warning 用驱动默认。下面
                # sim_rules 透传 emulation_file 给 F64。门只对**真 F64** 生效 (mock-aware,
                # 读 LIVE HAL, 同 precheck cal/dut 门 Codex on PR #75); 决策见
                # emulation_file_gate.evaluate_emulation_file_gate。
                # P2-12 (Codex #120 后端另一半): 同一道门还校验 resolved_emulation_file
                # 扩展非 .smu (.rtc/.asc) → strict FAIL, 抓 API 直传 / 绕过前端 #120
                # filter 的非 GCM 原生文件 (覆盖 scd_id 解析 + 裸路径两路)。
                emulation_gate = evaluate_emulation_file_gate(
                    emulator_is_real=(
                        emulator is not None and not is_mock_driver(emulator)
                    ),
                    emulation_file=resolved_emulation_file,
                    strict=config.precheck_strict_emulation_file,
                )
                if emulation_gate.should_fail:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=emulation_gate.message,
                    )
                if emulation_gate.should_warn:
                    logger.warning(
                        "[%s] %s", context.test_execution.id, emulation_gate.message
                    )
            elif engine_mode == EngineMode.EXTERNAL_ASC:
                # 2026-05-18 P0-7: operator-supplied .asc directory; skip
                # channel-engine-service entirely. Schema already validated
                # asc_source_path is set; path-exists check happens in
                # ExternalAscPathStrategy.generate_and_load so failures land
                # with the same logging context as other generator failures.
                generator = ExternalAscPathStrategy(
                    emulator,
                    chamber,
                    calibration_entries,
                    asc_source_path=config.asc_source_path,
                )
            elif engine_mode == EngineMode.B2_PARAMETRIC_TDL:
                # P2-14 B-2: 参数化 TDL + F64 硬件实时衰落 (F6 路由 + 能力门;
                # .tap/.rtc 生成 + F64 加载在 F7 + 现场落地, V1.0 §9)。
                generator = B2ParametricTdlStrategy(
                    emulator, ce_client, chamber, calibration_entries
                )
            else:
                generator = ExternalWaveformStrategy(
                    emulator, ce_client, chamber, calibration_entries
                )

            sim_rules = {
                "frequency_hz": pcell.frequency_hz,
                # 2026-07-03 现场热修 → P1-18 已正修: 驱动 Step 4 现在缺省不写 CENT
                # (保留 .smu 工程频率)。此桥接仍保留 —— TestCase 显式驱动频率是路径 B
                # 正路 (下发=配置, _center_freq_programmed 置位, 上报诚实), EMQuest
                # 运行时同时向 UXM+F64 下发频点的行为与此同构。
                # Codex #193 P2 + P1-55: 取规范化 PCell 频率，与 UXM、校准、波形和
                # 一致性网同源；顶层 legacy frequency_hz 仅为受写入门约束的兼容镜像。
                "center_frequency_mhz": pcell.frequency_hz / 1e6,
                "target_tx_power_dbm": config.target_tx_power_dbm,
                "target_rsrp_dbm": config.target_rsrp_dbm,
                "target_snr_db": config.target_snr_db,
            }
            # P2-11 Phase 2: TestCase 显式指定 .smu → 透传给 F64 GCM
            # (NativeModelStrategy → load_channel parameters["emulation_file"],
            # propsim_f64 line 745 优先于驱动默认; 加载失败 P0-8 gate fail-loud)。
            # slice 4: resolved = SCD 解析的 .smu (scd_id 优先) 或裸 emulation_file (legacy)
            if resolved_emulation_file:
                sim_rules["emulation_file"] = resolved_emulation_file
            cdl_model_data = {
                "model_name": config.cdl_model_name,
                "session_id": str(context.test_execution.id),
                # P2-15: custom CDL profile id (设了 → ASC strategy 走 input_mode=custom)
                "cdl_profile_id": getattr(config, "cdl_profile_id", None),
            }
            if resolved_asset is not None and resolved_asset.scenario:
                cdl_model_data["scenario"] = resolved_asset.scenario
            # P2-16 S2: ChannelAsset custom_static → 透传 payload clusters (不查 CustomCDLProfile 表)
            if resolved_asset is not None and resolved_asset.clusters_payload is not None:
                cdl_model_data["clusters"] = resolved_asset.clusters_payload
                cdl_model_data["channel_asset"] = resolved_asset.asset
            # P2-14 B-2 (Codex P1 #169): 把聚类输入透传进 cdl_model_data / sim_rules,
            # 否则 B2ParametricTdlStrategy 永远拿不到 rt_rays → 调 CE 前 fail-loud, B-2 路
            # 死 (即便 test case 含 RT 射线也丢)。来源 = TestCase.configuration extra
            # (RT-Release 现场写入); 无则 rt_rays=None → strategy fail-loud = 设计预期。
            if engine_mode == EngineMode.B2_PARAMETRIC_TDL:
                _b2 = _extract_b2_cluster_inputs(config)
                # rt_dynamic ChannelAsset payload rays 优先于 legacy config.model_extra rt_rays
                # (Codex #174 复查 P2: 否则选 rt_dynamic 资产却用 saved TestCase 残留 legacy rays)
                if resolved_asset is not None and resolved_asset.rt_rays_payload is not None:
                    cdl_model_data["rt_rays"] = resolved_asset.rt_rays_payload
                else:
                    cdl_model_data["rt_rays"] = _b2["rt_rays"]
                # rt_dynamic 顶层声明频率 → 喂频率一致性网 (Codex #174 复查 P2: 否则复用别 band 的
                # RT 射线在错误载频聚类, 频率门无资产源可比; 对称 vendor 的 GCM 517-518 注入)。
                if resolved_asset is not None and resolved_asset.scd_freq_identity is not None:
                    scd_freq_identity = resolved_asset.scd_freq_identity
                cdl_model_data["test_class"] = _b2["test_class"]
                cdl_model_data["f64_profile"] = _b2["f64_profile"]
                # rt_dynamic 资产顶层速度优先于 legacy config.model_extra (Codex 9d4e758 P2:
                # 否则选带速度的 RT 资产却用 legacy/零速度聚类, 丢多普勒上下文)
                _vel = (resolved_asset.ue_velocity_mps
                        if resolved_asset is not None and resolved_asset.ue_velocity_mps is not None
                        else _b2["ue_velocity_mps"])
                if _vel is not None:
                    sim_rules["ue_velocity_mps"] = _vel

            # P2-15 (Codex P2 #171): cdl_profile_id (自定义 CDL) 只 ASC_SYNTHESIS 实现 custom
            # 分支; GCM/external strategy 忽略它 → 静默跑标准信道。capability↔gate 一致, fail-fast。
            if getattr(config, "cdl_profile_id", None) and engine_mode != EngineMode.ASC_SYNTHESIS:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        f"自定义 CDL (cdl_profile_id) 仅 engine_mode=mimo_first_asc 支持; 当前 "
                        f"engine_mode={config.engine_mode} 的 strategy 会忽略它静默跑标准信道。"
                        f"改用 MIMO-First ASC 引擎, 或清空自定义 CDL 选择。"
                    ),
                )
            # 三种信道管线都必须证明 F64 已加载本次模型。P2-29 起三管线统一
            # 归档：加载走同一条 CALC:FILT:FILE 事务（手册确认判成功流程与状态机
            # 均与文件来源无关，AN §2.2.2/§2.1 + UR §20.4.3.14），驱动侧三路
            # 都带 MODEL:STATE?/STATE? 探针，recipe 原样复用、零新目录条目。
            register_required_scpi_evidence(
                context.test_execution,
                requirement_id="f64.model_loaded",
                evidence_key="f64.model_load",
                requested=resolved_emulation_file,
                required_evidence_level=EvidenceLevel.APPLIED,
            )
            context.db.commit()
            with capture_scpi_exchanges() as channel_load_exchanges:
                gen_ok = await generator.generate_and_load(sim_rules, cdl_model_data)
            # P2-29: 归档条件按驱动能力判（有 build 能力 = F64 语义驱动），
            # 不按管线枚举 —— 用 engine_mode 当判据曾把 ASC/B2 锁在 unknown。
            if hasattr(emulator, "build_p0_5_command_evidence"):
                try:
                    # requested 换判据来源（内审 F1）：ASC/B2 下 config.emulation_file
                    # 常为 None/被忽略，而 wire operand 是驱动内部构造的远端路径
                    # （FTP 目录 + 反斜杠），两端必然不等 → builder 会把成功的加载
                    # 谎报成 rejected（requested_command_mismatch）。加载成功后取
                    # **驱动真值** `_loaded_emulation_file`（它就是发进 CALC:FILT:FILE
                    # 的那个串），register 幂等更新后再归档 —— GCM 两端本就同源，
                    # 行为不变；「选 A 实际加载 B」的防错配仍由 builder 对比
                    # requested vs wire 保住（真值若与 wire 脱钩照样抓）。
                    # 加载失败/读不到真值 → 保持意图值，fail-closed 不变。
                    _model_load_requested = resolve_model_load_requested(
                        emulator, gen_ok, resolved_emulation_file
                    )
                    # 真值与意图不同（ASC/B2 的常态）才需要幂等更新 requirement；
                    # GCM 两端同源、register 里已是同值，跳过等价。
                    if gen_ok and _model_load_requested != resolved_emulation_file:
                        register_required_scpi_evidence(
                            context.test_execution,
                            requirement_id="f64.model_loaded",
                            evidence_key="f64.model_load",
                            requested=_model_load_requested,
                            required_evidence_level=EvidenceLevel.APPLIED,
                        )
                    record_f64_command_capture(
                        context.test_execution,
                        requirement_id="f64.model_loaded",
                        evidence_key="f64.model_load",
                        requested=_model_load_requested,
                        driver=emulator,
                        exchanges=channel_load_exchanges,
                    )
                    context.db.commit()
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "[%s] F64 model-load P1-47C 证据归档失败；正式判定将保持 unknown",
                        context.test_execution.id,
                    )
            if not gen_ok:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=f"Channel generation failed for engine_mode={config.engine_mode}",
                )

            # --- P2-11 Phase 1: 多方频率一致性 fail-loud 校验 ---
            # BaseStation + F64 (信道加载后) 都已配置; 把各
            # 仪表归一到 (中心 ARFCN, 带宽) 跟 TestCase 精确比对。不一致 = 静默错配
            # (GCM 模式 F64 默认 .smu 3600 但 TestCase 3500, 或基站未下发 channel → 实际
            # 下发 band fallback 基线值 ≠ 标称), strict 模式 FAIL。频率错了下面
            # input level / RSRP / 吞吐都不可信, 所以放在 Phase 2b input level 之前。
            from app.services.mimo_ota.frequency_consistency import (
                CenterFrequencyObservation,
                as_channel_frequency_identity,
                check_frequency_consistency,
            )
            # 资产声明频率统一兜底喂一致性网 (Codex 0ea6cca P2: standard_3gpp 走 ASC 路, GCM/B2
            # 分支没设 scd_freq_identity; 补 standard 资产声明载频; GCM/B2 已设则 is None 跳过)
            if (resolved_asset is not None and resolved_asset.scd_freq_identity is not None
                    and scd_freq_identity is None):
                scd_freq_identity = resolved_asset.scd_freq_identity
            # 开关 1 inherit: BaseStation identity 换源 — 下发记录必 None (没下发过),
            # 改从仪器 live 读回实际 ARFCN/BW (知情继承); 读不回 (mock / 老
            # profile 无查询能力 / 查询失败) → None 走"未报告跳过"+ 显式告警,
            # 操作员知道核对没发生 (不是静默盲信)。
            if base_station_inherit:
                base_station_identity = (
                    await base_station.read_live_frequency_identity()
                    if hasattr(base_station, "read_live_frequency_identity")
                    else None
                )
                if base_station_identity is None:
                    logger.warning(
                        "[%s] 开关1 inherit: 仪器实际频率读不回 (mock/无查询"
                        "能力/失败) — BaseStation 频率核对未发生, 继承态未经比对",
                        context.test_execution.id,
                    )
                # P0-2 D6 (S5): inherit 此前只核对频率身份, 不核对小区状态。
                # 补一次真值源读取 (get_cell_state 已换 BSE:STATus:NR5G, D1)
                # 当现场证据行: OFF **不算错** (手册: OFF 态缓存的配置在
                # CELL ON 时自动应用, 后续 attach 会拉起); 但读不到
                # (ERROR) 要大声 — 那说明"继承了什么"完全不可知。
                if hasattr(base_station, "get_cell_state"):
                    _inherit_cs = await base_station.get_cell_state()
                    _cs_txt = getattr(_inherit_cs, "value", str(_inherit_cs))
                    if _cs_txt == "ERROR":
                        logger.warning(
                            "[%s] 开关1 inherit: 小区状态读不到 (ERROR) — "
                            "继承态不可知, 频率核对结果是唯一依据",
                            context.test_execution.id,
                        )
                    else:
                        logger.info(
                            "[%s] 开关1 inherit: 小区状态核对 = %s",
                            context.test_execution.id, _cs_txt,
                        )
            else:
                base_station_identity = (
                    base_station.get_frequency_identity()
                    if hasattr(base_station, "get_frequency_identity") else None
                )

            # F64 的 ATE 运行时能回读中心频率，但手册没有当前 .smu 仿真带宽
            # 的查询。绝不再把 SYST:INFO? 的系统能力 100 MHz 当场景带宽。
            # 有 ChannelAsset/SCD 时，用其已登记带宽与 live 中心频组合；没有时
            # 只核对中心频率，并在 payload 留 BW unknown，不能假装完整闭环。
            f64_center_mhz = (
                emulator.get_center_frequency_mhz()
                if hasattr(emulator, "get_center_frequency_mhz") else None
            )
            declared_f64_bandwidth_mhz = (
                float(scd_freq_identity.bandwidth_mhz)
                if scd_freq_identity is not None
                else None
            )
            if f64_center_mhz is not None and scd_freq_identity is not None:
                declared_identity = as_channel_frequency_identity(scd_freq_identity)
                live_center_hz = int(round(float(f64_center_mhz) * 1_000_000))
                f64_identity = (
                    declared_identity
                    if live_center_hz == declared_identity.center_frequency_hz
                    else CenterFrequencyObservation(
                        center_frequency_hz=live_center_hz,
                        source=(
                            "F64 CALC:FILT:CENT:CH?; differs from typed "
                            "ChannelAsset/SCD identity"
                        ),
                    )
                )
                f64_bandwidth_source = "channel_asset_or_scd_declared"
            elif f64_center_mhz is not None:
                f64_identity = CenterFrequencyObservation.from_center_freq_mhz(
                    f64_center_mhz,
                    source="F64 CALC:FILT:CENT:CH?; no verified asset bandwidth",
                )
                f64_bandwidth_source = "unknown"
            else:
                f64_identity = None
                f64_bandwidth_source = (
                    "channel_asset_or_scd_declared"
                    if declared_f64_bandwidth_mhz is not None
                    else "unknown"
                )
            instrument_frequency_identities = {
                "BaseStation": base_station_identity,
                "F64": f64_identity,
            }
            # SCD is optional.  Once selected it participates in the gate, but
            # an absent SCD is not a listed instrument with a missing readback.
            if scd_freq_identity is not None:
                instrument_frequency_identities["SCD"] = scd_freq_identity
            freq_result = check_frequency_consistency(
                _frequency_identity_from_requested_config(
                    pcell_requested_config
                ),
                instrument_frequency_identities,
            )
            frequency_consistency_payload = freq_result.to_payload()
            frequency_consistency_payload["f64_center_readback_mhz"] = f64_center_mhz
            frequency_consistency_payload["f64_bandwidth_source"] = f64_bandwidth_source
            f64_frequency_fully_verified = (
                f64_center_mhz is not None
                and f64_bandwidth_source == "channel_asset_or_scd_declared"
            )
            if not f64_frequency_fully_verified:
                frequency_consistency_payload["fully_verified"] = False
                _unverified = list(
                    frequency_consistency_payload.get("unverified") or []
                )
                if "F64" not in _unverified:
                    _unverified.append("F64")
                frequency_consistency_payload["unverified"] = _unverified
            if not freq_result.consistent:
                if config.precheck_strict_frequency:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "P2-11 频率一致性校验失败: "
                            + (freq_result.failure_reason() or "")
                        ),
                        measurements={
                            "frequency_consistency": frequency_consistency_payload
                        },
                    )
                logger.warning(
                    "[%s] P2-11 频率不一致 (precheck_strict_frequency=False, 继续): %s",
                    context.test_execution.id, freq_result.failure_reason(),
                )
            elif not frequency_consistency_payload["fully_verified"]:
                logger.warning(
                    "[%s] %s",
                    context.test_execution.id,
                    _describe_f64_frequency_verification_gap(
                        f64_center_mhz=f64_center_mhz,
                        f64_bandwidth_source=f64_bandwidth_source,
                        declared_bandwidth_mhz=declared_f64_bandwidth_mhz,
                    ),
                )

            # --- 仪表参数 (开关 3 块 2): F64 输出增益, 显式给才写 ---
            if (config.f64_output_gain_db is not None
                    and not hasattr(emulator, "set_output_gain")):
                # 门审 #217 F1: 显式配了参数, CE 无能力不得静默无痕跳过
                logger.warning(
                    "[%s] f64_output_gain_db=%s 已配置但 CE 驱动无 "
                    "set_output_gain 能力 (mock/非 F64) — 跳过, 真机不受此限",
                    context.test_execution.id, config.f64_output_gain_db,
                )
            if (config.f64_output_gain_db is not None
                    and hasattr(emulator, "set_output_gain")):
                _gain_err = await self._apply_output_gain(
                    emulator=emulator,
                    gain_db=config.f64_output_gain_db,
                    execution_id=str(context.test_execution.id),
                )
                if _gain_err is not None:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED, error_message=_gain_err,
                    )

            # 2026-08-07 现场: 绝对输出电平 (OUTP:LEV:AMP:CH)。
            # ⚠ 跟 f64_output_gain_db (OUTP:GAIN:CH) 是**两条不同命令**, 手册
            #   **未给出**两者的换算关系式 —— 同时给会写两次、谁最后生效不确定,
            #   所以 fail-loud 让操作员二选一, 不替他猜。
            if (config.f64_output_level_dbm is not None
                    and config.f64_output_gain_db is not None):
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "f64_output_level_dbm 与 f64_output_gain_db 同时配置 —— "
                        "前者写绝对电平 (OUTP:LEV:AMP:CH)、后者写增益 (OUTP:GAIN:CH), "
                        "手册未定义两者的换算关系, 同时下发结果不可预测。请只留一个。"
                    ),
                )
            if config.f64_output_level_dbm is not None:
                if not hasattr(emulator, "set_output_level_dbm"):
                    # 显式配了参数, CE 无能力不得静默无痕跳过 (门审 #217 F1 同款)
                    logger.warning(
                        "[%s] f64_output_level_dbm=%s 已配置但 CE 驱动无 "
                        "set_output_level_dbm 能力 (mock/非 F64) — 跳过, 真机不受此限",
                        context.test_execution.id, config.f64_output_level_dbm,
                    )
                elif not await emulator.set_output_level_dbm(
                    float(config.f64_output_level_dbm)
                ):
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            f"F64 输出电平下发被拒 "
                            f"({config.f64_output_level_dbm} dBm) — 明细见驱动日志"
                            "(限值查 OUTP:LEV:AMP:LIM?, 拓扑未知时驱动拒绝按猜测端口下发)。"
                        ),
                    )

            # --- RF 冷启动初始化：显式 F64 输入参考/crest ---
            # 现场给定工作点时不需要 DUT 已 attach；模型已经加载，真实输入口也已
            # 回读，因此在第一次 attach 前完成下发。未显式给定时仍保留 attach 后
            # AUTOSET 闭环，因为 AUTOSET 必须有真实下行信号，不能在无信号态假失败。
            input_level_payload = None
            if config.f64_input_ref_dbm is not None:
                input_level_payload = await self._apply_manual_input_reference(
                    emulator=emulator,
                    config=config,
                    execution_id=context.test_execution.id,
                )
                if (
                    not input_level_payload.get("skipped")
                    and not input_level_payload.get("success")
                    and config.precheck_strict_input_level
                ):
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        measurements={"input_level_calibration": input_level_payload},
                        error_message=(
                            "F64 显式输入工作点初始化失败（发生在 DUT attach 前）: "
                            f"{input_level_payload.get('failure_reason')}。"
                            "不带着未知输入参考/crest 继续 attach。"
                        ),
                    )

            # --- P2-17：本次模型加载后建立 attach 所需 F64 输出态 ---
            # 执行链原本无人调 start_emulation (现场靠脚本手动 GO) — attach 默认
            # 直通态落地后, 不启动 = 测量在 STOPPED+STATIC 3 下跑 (无衰落输出)。
            # start_emulation 内建 GO 前无条件 STATIC 0 恢复衰落 (P2-17 ①), 此
            # 调用同时完成"attach 直通 → 测量衰落"的闭环; 布尔契约 fail-loud。
            #
            # 开关 3 块 2: f64_bypass_mode 非 None = **直通态测量** (无衰落
            # 基线, 官方用法: Butler(2) 保 MIMO 秩; Calibration(3) 统一 -10dB
            # 但 4 层塌秩只适合单层) — 设直通、不 GO。注意直通稳态下 F64
            # 输出功率显示冻结 (07-03 实证), 判据以 DUT 侧吞吐为准。
            if config.f64_bypass_mode is not None:
                if not hasattr(emulator, "set_passthrough_mode"):
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "f64_bypass_mode 已配置但 CE 驱动无直通能力 "
                            "(set_passthrough_mode) — 不静默降级为衰落测量。"
                        ),
                    )
                if hasattr(emulator, "stop_emulation"):
                    # 门审 #217 F5: 布尔契约必须消费 — GOS 被拒 (仍在播放)
                    # 时继续写 STATIC 会把真因掩盖成"直通建立失败"
                    if not await emulator.stop_emulation():
                        return StepExecutionResult(
                            status=StepExecutionStatus.FAILED,
                            error_message=(
                                "F64 停止播放被拒 (stop_emulation=False) — "
                                "直通态测量前置失败, 明细见驱动日志。"
                            ),
                        )
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id="f64.output_state",
                    evidence_key="f64.bypass_mode",
                    requested=config.f64_bypass_mode,
                    required_evidence_level=EvidenceLevel.APPLIED,
                )
                context.db.commit()
                with capture_scpi_exchanges() as f64_state_exchanges:
                    _bp_ok = await emulator.set_passthrough_mode(
                        mode=config.f64_bypass_mode
                    )
                if hasattr(emulator, "build_p0_5_command_evidence"):
                    try:
                        record_f64_command_capture(
                            context.test_execution,
                            requirement_id="f64.output_state",
                            evidence_key="f64.bypass_mode",
                            requested=config.f64_bypass_mode,
                            driver=emulator,
                            exchanges=f64_state_exchanges,
                        )
                        context.db.commit()
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[%s] F64 bypass P1-47C 证据归档失败；正式判定将保持 unknown",
                            context.test_execution.id,
                        )
                if not _bp_ok:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            f"F64 直通建立失败 (f64_bypass_mode="
                            f"{config.f64_bypass_mode}) — 明细见驱动日志。"
                        ),
                    )
                logger.info(
                    "[%s] attach 前已置 F64 直通 mode=%s（本次模型加载后建立）—— %s",
                    context.test_execution.id,
                    config.f64_bypass_mode,
                    "DUT 挂上后撤掉直通并启动衰落"
                    if config.f64_fade_after_attach
                    else "本次为纯直通基线，全程不启动衰落",
                )
            else:
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id="f64.output_state",
                    evidence_key="f64.simulation_state",
                    requested="RUNNING",
                    required_evidence_level=EvidenceLevel.APPLIED,
                )
                context.db.commit()
                with capture_scpi_exchanges() as f64_state_exchanges:
                    started = await emulator.start_emulation()
                if hasattr(emulator, "build_p0_5_command_evidence"):
                    try:
                        record_f64_command_capture(
                            context.test_execution,
                            requirement_id="f64.output_state",
                            evidence_key="f64.simulation_state",
                            requested="RUNNING",
                            driver=emulator,
                            exchanges=f64_state_exchanges,
                        )
                        context.db.commit()
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[%s] F64 run-state P1-47C 证据归档失败；正式判定将保持 unknown",
                            context.test_execution.id,
                        )
                if not started:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "信道仿真启动失败 (start_emulation=False, 明细见仿真器"
                            "驱动日志) — 中止, 不在 STOPPED/直通态下测量。"
                        ),
                    )

            # --- 第一次 DUT attach：只有本次 RF 初始态全部成功后才允许进入 ---
            # BaseStation 的 channel/BW/功率已由上面的配置入口下发并回读；F64
            # 模型、中心频率、显式工作点和 STATIC/GO 状态也均已建立。这里不再
            # 能借用仪表上一次执行的遗留场景。
            attach_receipt = await base_station.attach()
            if base_station_attempt.attempt_id is not None:
                from app.hal.base_station_manifest import BaseStationAdapterManifest
                from app.services.execution_scpi_evidence import (
                    confirm_base_station_attach,
                )

                resolved_binding = base_station_attempt.frozen_adapter.get(
                    "resolved_binding"
                )
                execution_manifest = BaseStationAdapterManifest.model_validate(
                    resolved_binding.get("manifest")
                    if isinstance(resolved_binding, dict)
                    else None
                )
                confirm_base_station_attach(
                    context.db,
                    context.test_execution.id,
                    attempt_id=base_station_attempt.attempt_id,
                    lease_identity=base_station_attempt.lease_identity,
                    manifest=execution_manifest,
                    receipt=attach_receipt,
                )
                context.db.commit()
            if base_station_config_capture_manager is not None:
                base_station_config_capture_manager.__exit__(None, None, None)
                base_station_config_capture_manager = None
            if not base_station_inherit and hasattr(
                base_station, "build_p0_5_config_evidence"
            ):
                try:
                    record_base_station_config_capture(
                        context.test_execution,
                        requirement_id="base_station.pcell.config_applied",
                        requested=pcell_channel_number,
                        driver=base_station,
                        exchanges=base_station_config_exchanges,
                    )
                    context.db.commit()
                except Exception:  # noqa: BLE001 — 证据失败不得伪装业务失败原因
                    logger.exception(
                        "[%s] BaseStation P1-47C 证据归档失败；正式判定将保持 unknown",
                        context.test_execution.id,
                    )
            if attach_receipt.diagnostic_execution_allowed is not True:
                terminal_attach_stage = attach_receipt.terminal_stage_receipt
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "RF 初始化已完成，但 BaseStation 本次 attach 未确认可继续；"
                        f"终止阶段={attach_receipt.terminal_stage or 'none'}，"
                        "证据="
                        f"{terminal_attach_stage.evidence if terminal_attach_stage else 'none'}，"
                        f"原因={attach_receipt.reason}。中止测量，防止读取上一轮"
                        "缓存吞吐造成假绿。"
                        + (
                            "\n💡 若这个 DUT 在衰落下反复挂不上：把 `f64_bypass_mode` "
                            "设成 2（Butler 直通）可先用直通扶它挂上，挂上后自动撤掉"
                            "直通再开衰落测量。撤掉之后还在不在，会记进 "
                            "`attach_milestones.fading_attach`。"
                            if config.f64_bypass_mode is None else
                            "\n⚠ 本次已加载指定场景并建立直通扶持（f64_bypass_mode="
                            f"{config.f64_bypass_mode}）仍未挂上 —— 说明问题不在"
                            "「旧场景/未建直通」这一层，查 F64 输出电平、馈线与 DUT。"
                        )
                    ),
                )

            # --- Phase 2e: attach 后 RRC reconfig ---
            rrc_ok = await _reconfigure_rrc_if_supported(
                base_station,
                plan=base_station_attempt.execution_plan.rrc_reconfiguration,
                mimo_layers=config.mimo_layers,
                modulation=config.modulation,
            )
            if rrc_ok is False:
                logger.warning(
                    "[%s] RRC reconfig returned False; UE may still be on prior layer/modulation",
                    context.test_execution.id,
                )

            # === 2026-08-07 现场时序: 直通 attach → 开衰落 → 再确认 → 测吞吐 ===
            # 用户当场定的顺序: F64 先 Butler 直通让 DUT 挂上, attach 成功后再
            # 启动衰落。三个节点各留一条里程碑, 现场一眼看出卡在哪一环:
            #   bypass_attach  — 直通态 DUT 挂上了吗
            #   fading_attach  — 开了衰落之后还在吗 (衰落一上掉线 = 功率/信道问题)
            #   throughput     — 有没有真跑出吞吐 (在下面的方位扫描里落)
            # ⚠ 每一环失败都**当场停**, 不带着"其实没挂上"继续测 —— 那会产出
            #   看着像数的假结果, 正是本项目一直在治的东西。
            milestones: Dict[str, Any] = {
                "bypass_attach": None,
                "fading_attach": None,
                "throughput": None,
            }

            def _attach_milestone(
                stage: str,
                *,
                attached: bool | None,
                reason: str,
                exchange_ids: tuple[str, ...] = (),
                simulated: bool = False,
                cell_state: Any = None,
                semantic_state_confirmed: bool = True,
            ) -> Dict[str, Any]:
                manifest_stages = tuple(attach_receipt.stages)
                terminal = next(
                    (
                        item.stage
                        for item in reversed(manifest_stages)
                        if item.evidence not in {"unavailable", "not_applicable"}
                    ),
                    None,
                )
                stage_truth = []
                for item in manifest_stages:
                    confirmed = (
                        not simulated
                        and semantic_state_confirmed
                        and item.stage == terminal
                        and attached is not None
                        and bool(exchange_ids)
                    )
                    stage_truth.append(
                        {
                            "stage": item.stage,
                            "requested": True,
                            "applied": attached if confirmed else None,
                            "status": "confirmed" if confirmed else "unknown",
                            "evidence": item.evidence,
                            "reason": reason if item.stage == terminal else item.reason,
                            "exchange_ids": list(exchange_ids) if confirmed else [],
                        }
                    )
                payload: Dict[str, Any] = {
                    "stage": stage,
                    # Compatibility mirror for existing precheck/report readers.
                    "attached": attached,
                    "simulated": simulated,
                    "reason": reason,
                    "stage_truth": stage_truth,
                }
                if cell_state is not None:
                    payload["cell_state"] = cell_state
                return payload

            async def _probe_ue_attached(stage: str) -> Dict[str, Any]:
                """读一次**小区连接状态**判断 DUT 挂上没有。**只报实况, 不推断。**

                判据是 `BSE:STATus:NR5G:<cell>?` 回 `CONNected`（手册枚举
                `OFF|ON|CONNected|IDLE|AGGRegated|ACTivated`），走驱动既有的
                `get_cell_state()`。

                ⚠ 上一版用的是 `query_ue_capability()` —— **判据用错了**
                （2026-08-07 现场实证）：那个查的是"这个 DUT 支持几层、什么调制"
                （能力），不是"现在连上了没有"（状态）。而且 IRAT 方言的 profile 上
                `UE_CAPABILITY_*` 四条命令全是 `None`，一调就崩、恒返回
                `source="unavailable"` → 里程碑恒判 False → 相位必然 FAILED。
                真正的判据就在旁边、attach 流程已经在用、当天还双向验证过：
                17:38:29 读到 `CONN` 判 attach 成功、17:42:29 一直读 `'ON'` 判超时。
                （memory `feedback_effective_end_not_nominal`：不从"能拿到的相似
                属性"取，要从 caller 已经在用的那个源取。）

                mock 驱动 / 无此方法 → attached=None = "没测"，跟 False（"测了
                没挂上"）区分开 —— **别让 mock 跑出绿色里程碑**。mock 那格另带
                `simulated: True`，报告侧据此区分"编的"与"测的"。
                """
                from app.hal.base_station import CellState

                # ⚠ 判据必须问「这是不是真驱动」，**不能**用 `hasattr(...)`
                #   （内审 F6）：`get_cell_state` 在抽象基类 `base_station.py:232`
                #   **和** `MockBaseStation:533` 都有定义 → `hasattr` **恒为真**，
                #   那个 mock 分支是死分支。而 mock 的 attach 实现直接把
                #   `_cell_state = CONNECTED`，于是 mock 下里程碑会报 attached=True
                #   并一路写进 result_payload → 报告 —— 正是本 docstring 下面那句
                #   「别让 mock 跑出绿色里程碑」要防的事，那句话此前是假的。
                #   （memory: mock 回读侧必须标 simulated，且绝不进报告/KPI。）
                if is_mock_driver(base_station):
                    return _attach_milestone(
                        stage,
                        attached=None,
                        simulated=True,
                        reason="BS 是 mock 驱动 — 未测（mock 的小区状态是编的）",
                    )
                if not hasattr(base_station, "get_cell_state"):
                    return _attach_milestone(
                        stage,
                        attached=None,
                        reason="BS 驱动无 get_cell_state — 未测",
                    )
                try:
                    with capture_scpi_exchanges() as attach_probe_exchanges:
                        state = await base_station.get_cell_state()
                except Exception as e:  # noqa: BLE001
                    return _attach_milestone(
                        stage,
                        attached=False,
                        reason=f"小区状态查询抛异常: {type(e).__name__}: {e}",
                    )
                exchange_ids = tuple(
                    item.exchange_id
                    for item in attach_probe_exchanges
                    if item.result_type == "response"
                )
                raw = getattr(state, "value", state)
                if state == CellState.CONNECTED:
                    return _attach_milestone(
                        stage,
                        attached=True,
                        reason="ok",
                        exchange_ids=exchange_ids,
                        cell_state=raw,
                    )
                if state == CellState.ERROR:
                    return _attach_milestone(
                        stage,
                        # 保持 False 让现有安全门中止，不带着未知链路继续测量；
                        # 但 ERROR 只表示回读不可解释，不能写成 confirmed false。
                        attached=False,
                        reason=f"小区状态 {raw!r} 不可解释 — Attach 真值 unknown",
                        exchange_ids=exchange_ids,
                        cell_state=raw,
                        semantic_state_confirmed=False,
                    )
                # ON/IDLE/OFF 是已解析的真实状态，均明确表示 UE 未连接。
                return _attach_milestone(
                    stage,
                    attached=False,
                    reason=f"小区状态 {raw!r} ≠ CONN — DUT 未 attach",
                    exchange_ids=exchange_ids,
                    cell_state=raw,
                )

            if config.f64_bypass_mode is not None and config.f64_fade_after_attach:
                # ① 直通态确认 DUT 已挂上
                milestones["bypass_attach"] = await _probe_ue_attached("bypass")
                logger.info(
                    "[%s] 里程碑 bypass_attach = %s (%s)",
                    context.test_execution.id,
                    milestones["bypass_attach"]["attached"],
                    milestones["bypass_attach"]["reason"],
                )
                if milestones["bypass_attach"]["attached"] is False:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "直通态下 DUT 未 attach —— 不开衰落、不继续测量。"
                            f"原因: {milestones['bypass_attach']['reason']}。"
                            "⚠ 已经用直通扶过仍挂不上，说明问题不在「衰落太深」这一层。"
                            "手册未说明 STATIC 态是否有射频输出；若确认 DUT 侧无信号，"
                            "查 F64 输出电平（`OUTP:LEV:AMP:LIM?` 各口上限）与馈线，"
                            "或把 `f64_bypass_mode` 设回 None 走正常衰落流程对比。"
                        ),
                        measurements={"attach_milestones": milestones},
                    )
                # ② 解直通 + 启动衰落。start_emulation 内建「GO 前无条件 STATIC 0」
                #    (P2-17 ①), 所以这一步同时完成"解 bypass"和"开播"。
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id="f64.output_state",
                    evidence_key="f64.simulation_state",
                    requested="RUNNING",
                    required_evidence_level=EvidenceLevel.APPLIED,
                )
                context.db.commit()
                with capture_scpi_exchanges() as f64_fade_exchanges:
                    faded = await emulator.start_emulation()
                if hasattr(emulator, "build_p0_5_command_evidence"):
                    try:
                        record_f64_command_capture(
                            context.test_execution,
                            requirement_id="f64.output_state",
                            evidence_key="f64.simulation_state",
                            requested="RUNNING",
                            driver=emulator,
                            exchanges=f64_fade_exchanges,
                        )
                        context.db.commit()
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[%s] F64 fading-start P1-47C 证据归档失败；正式判定保持 unknown",
                            context.test_execution.id,
                        )
                if not faded:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "DUT 已 attach 但衰落启动失败 (start_emulation=False) — "
                            "中止, 不在直通态下冒充衰落测量。"
                        ),
                        measurements={"attach_milestones": milestones},
                    )
                # ③ 衰落态再确认一次 —— 衰落一上就掉线是现场常见形态
                milestones["fading_attach"] = await _probe_ue_attached("fading")
                logger.info(
                    "[%s] 里程碑 fading_attach = %s (%s)",
                    context.test_execution.id,
                    milestones["fading_attach"]["attached"],
                    milestones["fading_attach"]["reason"],
                )
                if milestones["fading_attach"]["attached"] is False:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "衰落启动后 DUT 掉线 —— 直通能挂、加衰落掉, 通常是功率余量"
                            "不够或信道模型衰减过大。"
                            f"原因: {milestones['fading_attach']['reason']}。"
                        ),
                        measurements={"attach_milestones": milestones},
                    )

            # --- 标准受控 attach 动态门：在最终测量态统一确认 ---
            # 三种合法路径收敛到同一个判据：
            #   ① 正常流程：本次信道已 GO，确认 fading_attach；
            #   ② Butler 扶持：直通 attach 后已撤梯并 GO，复用上面的确认；
            #   ③ 明确的无衰落基线：最终态就是 bypass，确认 bypass_attach。
            # 这一步必须早于任何 AUTOSET/方位采样，避免 PRECHECK 延后了门却
            # 没有在真实配置生效后补回来。
            managed_rf_attach = bool(
                (context.test_execution.config or {}).get("managed_rf_attach")
            )
            final_attach_key = (
                "bypass_attach"
                if config.f64_bypass_mode is not None
                and not config.f64_fade_after_attach
                else "fading_attach"
            )
            if milestones[final_attach_key] is None:
                milestones[final_attach_key] = await _probe_ue_attached(
                    "bypass" if final_attach_key == "bypass_attach" else "fading"
                )
            final_attach = milestones[final_attach_key]
            logger.info(
                "[%s] 标准受控 attach 最终门 %s = %s (%s)",
                context.test_execution.id,
                final_attach_key,
                final_attach.get("attached"),
                final_attach.get("reason"),
            )

            # PRECHECK 在标准流程中不会碰尚未初始化的 UE 状态；能力与身份
            # 信息必须在本次 RF 配置下 attach 成功后读取。失败只记 unknown，
            # 不用默认值冒充真实协商结果。
            ue_info_snapshot: Optional[Dict[str, Any]] = None
            dynamic_gate_warnings: List[str] = []
            base_station_is_real = not is_mock_driver(base_station)
            if (
                managed_rf_attach
                and base_station_is_real
                and hasattr(base_station, "query_ue_capability")
            ):
                try:
                    queried = await base_station.query_ue_capability()
                    if (
                        isinstance(queried, dict)
                        and queried.get("source") != "unavailable"
                    ):
                        ue_info_snapshot = queried
                    else:
                        dynamic_gate_warnings.append(
                            "受控 attach 后 UE 能力/身份回读不可用；能力交叉核对保持 unknown"
                        )
                except Exception as exc:  # noqa: BLE001 — 回读失败不伪造结果
                    dynamic_gate_warnings.append(
                        f"受控 attach 后 UE 能力/身份查询失败: "
                        f"{type(exc).__name__}: {exc}"
                    )

            # 自动把本次“配置后 attach”的事实写回 execution；若操作员此前登记
            # 了 IMSI/车型则保留那些元数据，只更新本次实时连接事实。不能拿
            # SIMProfile 的声明 IMSI 填成“实测 IMSI”，那会形成自证假通过。
            execution_measurements = dict(
                context.test_execution.measurements or {}
            )
            controlled_attach = dict(
                execution_measurements.get("dut_attach") or {}
            )
            # 每次执行先清掉旧的验真时间；本轮只有真实 UXM 明确回 CONN 才会
            # 重新写入。mock / False / unknown 只能证明“检查过”，不能证明通过。
            controlled_attach.pop("verified_at", None)
            if ue_info_snapshot is not None:
                controlled_attach["ue_info_snapshot"] = ue_info_snapshot
            else:
                # 旧快照可能来自初始化前的人工登记/上一轮执行。动态回读失败时
                # 必须删掉它，不能配上本轮 verified_at 后伪装成本轮观测；IMSI、
                # DUT 型号等人工元数据仍由 controlled_attach 保留。
                controlled_attach.pop("ue_info_snapshot", None)
            attach_checked_at = datetime.now(timezone.utc).isoformat()
            controlled_attach.update(
                {
                    "rrc_connected": final_attach.get("attached"),
                    "attach_stage_truth": final_attach.get("stage_truth"),
                    "controlled_attach": True,
                    "attach_stage": final_attach.get("stage"),
                    "checked_at": attach_checked_at,
                    "simulated": bool(final_attach.get("simulated")),
                    "verification_reason": final_attach.get("reason"),
                    "rf_configuration": {
                        "pcell_frequency_hz": pcell.frequency_hz,
                        "pcell_bandwidth_mhz": pcell.bandwidth_mhz,
                        "pcell_band": pcell.band,
                        "component_carriers": len(ccs),
                        "engine_mode": config.engine_mode,
                        "channel_asset_id": config.channel_asset_id,
                        "channel_model": config.cdl_model_name,
                        "switch_mode_id": config.switch_mode_id,
                        "f64_bypass_mode": config.f64_bypass_mode,
                        "f64_fade_after_attach": config.f64_fade_after_attach,
                    },
                }
            )
            if base_station_is_real and final_attach.get("attached") is True:
                controlled_attach["verified_at"] = attach_checked_at
            # SIM 身份门：优先使用 UXM 实测 IMSI；仪器方言未提供时才使用
            # 操作员提前登记的 IMSI。绝不能拿 SIMProfile 的声明 IMSI 回填成
            # “实测值”再跟自身比较，那会制造防插错卡假通过。
            sim_identity_failure: Optional[str] = None
            if managed_rf_attach and config.sim_profile_id:
                from uuid import UUID as _UUID

                from app.models.sim_profile import SIMProfile
                from app.services.mimo_ota.sim_identity_check import (
                    check_sim_identity,
                )

                try:
                    sim_profile_uuid = _UUID(str(config.sim_profile_id))
                except (ValueError, TypeError, AttributeError):
                    sim_profile_uuid = None
                sim_profile = (
                    context.db.query(SIMProfile)
                    .filter(SIMProfile.id == sim_profile_uuid)
                    .first()
                    if sim_profile_uuid is not None
                    else None
                )
                observed_imsi = (ue_info_snapshot or {}).get("imsi")
                registered_imsi = controlled_attach.get("imsi")
                identity_imsi = observed_imsi or registered_imsi
                imsi_source = "observed" if observed_imsi else "declared"
                unverified_failure = _managed_sim_identity_unverified_failure(
                    managed=managed_rf_attach,
                    strict=config.precheck_strict_sim_identity,
                    sim_profile_id=str(config.sim_profile_id),
                    sim_profile_exists=sim_profile is not None,
                    declared_imsi=(sim_profile.imsi if sim_profile is not None else None),
                    observed_imsi=observed_imsi,
                )
                if unverified_failure is not None:
                    sim_identity_failure = unverified_failure
                if sim_profile is None:
                    dynamic_gate_warnings.append(
                        f"sim_profile_id={config.sim_profile_id} 不存在；SIM 身份保持 unknown"
                    )
                elif sim_profile.imsi and identity_imsi:
                    sim_identity = check_sim_identity(
                        declared_imsi=sim_profile.imsi,
                        attached_imsi=identity_imsi,
                    )
                    sim_identity_payload = {
                        "sim_profile": sim_profile.name,
                        "consistent": sim_identity.consistent,
                        "verified": imsi_source == "observed",
                        "imsi_source": imsi_source,
                        "declared_imsi": sim_identity.declared_imsi_masked,
                        "attached_imsi": sim_identity.attached_imsi_masked,
                    }
                    controlled_attach["sim_identity_check"] = sim_identity_payload
                    if (
                        not sim_identity.consistent
                        and config.precheck_strict_sim_identity
                    ):
                        sim_identity_failure = (
                            f"SIM 身份不符：TestCase 选择的卡 '{sim_profile.name}' "
                            f"({sim_identity.declared_imsi_masked}) 与受控 attach 后的 "
                            f"{imsi_source} IMSI ({sim_identity.attached_imsi_masked}) 不一致"
                        )
                    elif imsi_source != "observed":
                        dynamic_gate_warnings.append(
                            "SIM IMSI 仅来自操作员登记，未由 UXM/UE 实测；"
                            "该比对只作未验证审计"
                        )
                else:
                    dynamic_gate_warnings.append(
                        "受控 attach 后没有可核对的 IMSI；SIM 身份保持 unknown"
                    )

            # DUT 声明 vs 本次 attach 后实测能力仍是 audit-only，不覆盖声明、
            # 不单独判失败；吞吐所需层数/调制硬门由后面的 cell config 一致性负责。
            if managed_rf_attach and config.dut_profile_id:
                from app.models.dut_profile import DUTProfile
                from app.services.mimo_ota.dut_capability_crosscheck import (
                    canonical_modulation,
                    check_dut_capability_mismatch,
                )
                from uuid import UUID as _UUID

                try:
                    dut_profile_uuid = _UUID(str(config.dut_profile_id))
                except (ValueError, TypeError, AttributeError):
                    dut_profile_uuid = None
                dut_profile = (
                    context.db.query(DUTProfile)
                    .filter(DUTProfile.id == dut_profile_uuid)
                    .first()
                    if dut_profile_uuid is not None
                    else None
                )
                if dut_profile is not None:
                    cap = ue_info_snapshot or {}
                    observed_source = cap.get("source")
                    obs_mod_dl = canonical_modulation(cap.get("max_modulation_dl"))
                    obs_mod_ul = canonical_modulation(cap.get("max_modulation_ul"))
                    mismatch = check_dut_capability_mismatch(
                        declared_max_dl_layers=dut_profile.max_dl_layers,
                        declared_max_ul_layers=dut_profile.max_ul_layers,
                        declared_max_modulation_dl=dut_profile.max_modulation_dl,
                        declared_max_modulation_ul=dut_profile.max_modulation_ul,
                        observed_max_dl_layers=cap.get("max_dl_layers"),
                        observed_max_ul_layers=cap.get("max_ul_layers"),
                        observed_max_modulation_dl=obs_mod_dl,
                        observed_max_modulation_ul=obs_mod_ul,
                        observed_available=(observed_source == "real_ue"),
                    )
                    controlled_attach["dut_capability_observed"] = {
                        "dut_profile_id": str(dut_profile.id),
                        "dut_profile_name": dut_profile.name,
                        "source": observed_source,
                        "max_dl_layers": cap.get("max_dl_layers"),
                        "max_ul_layers": cap.get("max_ul_layers"),
                        "max_modulation_dl": obs_mod_dl,
                        "max_modulation_ul": obs_mod_ul,
                    }
                    controlled_attach[
                        "dut_capability_mismatch"
                    ] = mismatch.to_payload()
            if dynamic_gate_warnings:
                controlled_attach["warnings"] = [
                    *(controlled_attach.get("warnings") or []),
                    *dynamic_gate_warnings,
                ]
            execution_measurements["dut_attach"] = controlled_attach
            context.test_execution.measurements = execution_measurements
            flag_modified(context.test_execution, "measurements")
            context.db.commit()

            attach_failure = _managed_attach_failure(
                managed=managed_rf_attach,
                strict=config.precheck_strict_dut,
                base_station_is_real=base_station_is_real,
                milestone=final_attach,
            )
            dynamic_failure = attach_failure or sim_identity_failure
            if dynamic_failure is not None:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=dynamic_failure,
                    measurements={
                        "attach_milestones": milestones,
                        "controlled_dut_attach": controlled_attach,
                    },
                    warnings=dynamic_gate_warnings,
                )

            # --- P2-11 Phase 6: UXM cell config 下发后一致性 (吞吐链版频率校验) ---
            # set_cell_config + RRC reconfig 后, 拿 **UE 协商能力** (max_dl_layers /
            # max_modulation_dl) 跟 TestCase 请求比 —— 请求超 UE 能力 (4 层但 UE 只 2 /
            # 256QAM 但 UE 只 64QAM) → UXM 静默 clamp, 吞吐其实更低却当请求值测 (跟频率
            # 错配同等危害)。Codex on PR #114: 读 UE 能力而非 CONF:...:LAY? 配置旋钮
            # (后者回读只原样返回配置值, 抓不到 clamp)。UE 未 attach / firmware 不支持
            # (mock / dry-run) → skipped 跳过 (同 Phase 1)。
            if hasattr(base_station, "get_applied_cell_config"):
                from app.services.mimo_ota.cell_config_consistency import (
                    check_cell_config_consistency,
                )
                cc_result = check_cell_config_consistency(
                    requested_mimo_layers=config.mimo_layers,
                    requested_modulation=config.modulation,
                    applied=await base_station.get_applied_cell_config(),
                )
                if not cc_result.consistent:
                    if config.precheck_strict_cell_config:
                        return StepExecutionResult(
                            status=StepExecutionStatus.FAILED,
                            error_message=(
                                "P2-11 Phase 6 cell config 一致性校验失败: "
                                + (cc_result.failure_reason() or "")
                            ),
                            measurements={
                                "cell_config_consistency": cc_result.to_payload()
                            },
                        )
                    logger.warning(
                        "[%s] P2-11 Phase 6 cell config 不一致 "
                        "(precheck_strict_cell_config=False, 继续): %s",
                        context.test_execution.id, cc_result.failure_reason(),
                    )

            # --- P0-8 Step 2 Phase 2b: attach 后 AUTOSET（仅未显式给工作点）---
            # 显式 f64_input_ref_dbm/crest 已在 RF 冷启动初始化中下发；这里不得
            # 再写一次。未给定时才用已建立的真实下行信号跑 AUTOSET 闭环。
            if config.f64_input_ref_dbm is None:
                # CE 原子接口 + BS 显式 opt-in capability；任一方不支持时只记录
                # Warning/UNKNOWN 并跳过，不影响诊断流程，也不把未开放能力当正式证据。
                input_level_payload = await self._run_input_level_closed_loop(
                    emulator=emulator,
                    base_station=base_station,
                    config=config,
                    execution_id=context.test_execution.id,
                    plan=base_station_attempt.execution_plan.input_level_control,
                )
            assert input_level_payload is not None
            if (
                not input_level_payload.get("skipped")
                and not input_level_payload.get("success")
                and config.precheck_strict_input_level
            ):
                # strict 模式: 操作点未确定 → 后续 RSRP/吞吐都是 garbage, fail-loud。
                # finally 块仍会做 cleanup (UXM stop / F64 stop / 转台 home)。
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    measurements={"input_level_calibration": input_level_payload},
                    error_message=(
                        f"Input-level closed loop did not converge: "
                        f"{input_level_payload.get('failure_reason')}. "
                        "操作点未确定 → 跳过 azimuth 测量 (后续 RSRP/吞吐失去物理意义)。"
                        " 现场调试可临时设 precheck_strict_input_level=False 降级为 warning。"
                    ),
                )

            # --- Per-azimuth measurement loop (Phase 2d windowed sampling) ---
            azimuth_results: List[Dict[str, Any]] = []
            # P2-11 Phase 6 (MCS index 线): 跨所有 az/window 收集实测 mcs_dl, 循环后校验
            # AMC off 下是否被 UE clamp (实测众数 < 请求)。
            mcs_samples: List[Any] = []
            # P0: ce_base_rsrp is now per-azimuth (computed inside loop) since
            # path-loss varies by chain. avg_path_loss_db is the fallback.
            # One sample per stat window (≈ stat_count subframes × 1ms);
            # cap aggressively in dev so smoke tests don't wait minutes.
            num_windows = min(config.num_samples_per_azimuth, _DEV_SAMPLE_WINDOWS)
            frozen_mac_profile = base_station_attempt.mac_profile
            if frozen_mac_profile is None:
                raise RuntimeError(
                    "execution-frozen BaseStation MAC profile is missing"
                )
            frozen_stat_count = _frozen_mac_measurement_basis(
                frozen_mac_profile
            )
            window_s = max(
                frozen_stat_count / 1000.0,
                _MOCK_WINDOW_FLOOR_S,
            )

            loop = asyncio.get_event_loop()
            t_start = loop.time()

            # Phase 2f / P0: pre-resolve per-azimuth probe + pattern gain +
            # per-chain path-loss so the inner sample loop doesn't hammer the
            # DB. Chain lookup uses "V" by default — current measurement
            # synthesis is also V-pol; H-pol gets the same value (acceptable
            # until per-azimuth pol switching is wired).
            nominal_probe_gain_dbi = float(chamber.probe_gain_dbi or 0.0)
            azimuth_probe_gains: Dict[float, Dict[str, Any]] = {}
            rf_chain_probe_id_base = _rf_chain_probe_id_base(
                num_probes=chamber.num_probes,
                chain_pl_by_probe_pol=chain_pl_by_probe_pol,
            )
            for az_target in config.azimuths_deg:
                pattern_probe_id = select_active_probe_id(
                    chamber.num_probes, az_target
                )
                rf_chain_probe_id = (
                    select_active_rf_chain_probe_id(
                        chamber.num_probes,
                        az_target,
                        probe_id_base=rf_chain_probe_id_base,
                    )
                    if rf_chain_probe_id_base is not None
                    else None
                )
                pattern_gain_v = get_probe_gain_at_azimuth(
                    context.db, chamber.num_probes, az_target, pcell.frequency_hz / 1e6, "V",
                    chamber_id=chamber.id,
                )
                chain_pl_db = chain_pl_by_probe_pol.get((rf_chain_probe_id, "V"))
                azimuth_probe_gains[az_target] = {
                    "probe_id": rf_chain_probe_id,
                    "probe_pattern_id": pattern_probe_id,
                    "pattern_gain_dbi": pattern_gain_v,
                    "gain_offset_db": (
                        pattern_gain_v - nominal_probe_gain_dbi
                        if pattern_gain_v is not None else None
                    ),
                    # Per-chain path-loss; None falls back to chamber avg in loop.
                    "path_loss_db": chain_pl_db,
                }
            patterns_used = sum(
                1 for v in azimuth_probe_gains.values() if v["pattern_gain_dbi"] is not None
            )
            chains_used = sum(
                1 for v in azimuth_probe_gains.values() if v["path_loss_db"] is not None
            )
            if per_chain_pl and chains_used != len(config.azimuths_deg):
                missing = _missing_rf_chain_path_loss_azimuths(
                    num_probes=chamber.num_probes,
                    azimuths_deg=list(config.azimuths_deg),
                    chain_pl_by_probe_pol=chain_pl_by_probe_pol,
                )
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    measurements={
                        "path_loss_compensation": {
                            "source": "rf_chain",
                            "complete": False,
                            "missing": missing,
                        }
                    },
                    error_message=(
                        "逐 RF-chain 路损证书不完整，禁止与暗室平均路损混合采样；"
                        f"缺失方位/物理探头: {missing}"
                    ),
                )
            if chains_used:
                logger.info(
                    "[%s] P0: per-RFChain path-loss applied for %d/%d azimuths",
                    context.test_execution.id, chains_used, len(config.azimuths_deg),
                )
            elif per_chain_pl:
                logger.warning(
                    "[%s] P0: cert has %d chain entries but none matched any "
                    "azimuth's active probe (V) — falling back to avg path-loss",
                    context.test_execution.id, len(per_chain_pl),
                )
            if patterns_used == 0:
                logger.warning(
                    "[%s] Phase 2f: no ProbePattern data for any azimuth — RSRP/SINR "
                    "synthesis falls back to position-aware approximation",
                    context.test_execution.id,
                )
            else:
                logger.info(
                    "[%s] Phase 2f: ProbePattern available for %d/%d azimuths",
                    context.test_execution.id, patterns_used, len(config.azimuths_deg),
                )

            dut_disconnect_warnings: List[str] = []
            for az_idx, azimuth in enumerate(config.azimuths_deg):
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id=f"positioner.azimuth.{az_idx:03d}",
                    evidence_key="positioner.angle",
                    requested={"angle_deg": azimuth},
                    required_evidence_level=EvidenceLevel.APPLIED,
                )
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id=f"base_station.throughput.azimuth.{az_idx:03d}",
                    evidence_key="base_station.dl_throughput",
                    requested={"azimuth_deg": azimuth, "window_s": window_s},
                    required_evidence_level=EvidenceLevel.OUTCOME,
                )
            context.db.commit()
            for az_idx, azimuth in enumerate(config.azimuths_deg):
                # --- Phase 2m: DUT health check before each azimuth ---
                if az_idx % _DUT_HEALTH_CHECK_EVERY_N_AZIMUTHS == 0 and hasattr(
                    base_station, "get_ue_info"
                ):
                    try:
                        ue_info = await base_station.get_ue_info()
                        if not ue_info.get("connected", True):
                            msg = (
                                f"DUT disconnected before azimuth {azimuth:.0f}° "
                                f"(az_idx={az_idx}/{len(config.azimuths_deg)}); "
                                "aborting measurement loop"
                            )
                            logger.error("[%s] %s", context.test_execution.id, msg)
                            dut_disconnect_warnings.append(msg)
                            break  # stop loop; finally cleans up
                    except Exception as e:  # noqa: BLE001
                        logger.debug(
                            "[%s] DUT health check skipped: %s",
                            context.test_execution.id, e,
                        )

                logger.info(
                    "[%s] Phase 3: positioner -> azimuth %.1f° (%d windows × %.2fs)",
                    context.test_execution.id,
                    azimuth,
                    num_windows,
                    window_s,
                )
                with capture_scpi_exchanges() as position_exchanges:
                    moved = await positioner.move_to(
                        azimuth,
                        0.0,
                        **motion_stop_kwargs,
                    )
                if hasattr(positioner, "build_p0_5_position_evidence"):
                    try:
                        record_positioner_capture(
                            context.test_execution,
                            requirement_id=f"positioner.azimuth.{az_idx:03d}",
                            requested_angle_deg=azimuth,
                            frozen_positioner=frozen_positioner,
                            driver=positioner,
                            exchanges=position_exchanges,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[%s] 转台 %.1f° P1-47C 证据归档失败；正式判定将保持 unknown",
                            context.test_execution.id,
                            azimuth,
                        )
                if not moved:
                    # RealAerotechDriver / ETS 驱动都用 False 表达设备拒绝或移动
                    # 失败；继续在旧角度采吞吐会污染结果。必需项已预登记，当前
                    # capture 也先落库，正式证据保持 fail-closed。
                    context.db.commit()
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            f"转台移动到 {azimuth:.1f}° 失败；中止该方位及后续测量，"
                            "防止在旧角度采集并归档错误吞吐。"
                        ),
                    )
                await asyncio.sleep(config.settling_time_s)

                samples_rsrp: List[float] = []
                samples_sinr: List[float] = []
                samples_tput: List[float] = []
                samples_ri: List[float] = []
                # 同一方位的 formal requirement 只保留最终统计窗。旧实现每个窗口都
                # 覆写同一 JSONB 摘要并 commit，窗口数增大时会造成不必要的整行写放大；
                # 必需项已经在动作前落库，因此中途异常仍会安全地保持 missing/unknown。
                latest_throughput_exchanges = []

                az_meta = azimuth_probe_gains.get(azimuth, {})
                # P0: per-chain path-loss when available; falls back to avg.
                az_path_loss_db = az_meta.get("path_loss_db")
                if az_path_loss_db is None:
                    az_path_loss_db = avg_path_loss_db

                try:
                    resolved_binding = base_station_attempt.frozen_adapter.get(
                        "resolved_binding"
                    )
                    raw_manifest = (
                        resolved_binding.get("manifest")
                        if isinstance(resolved_binding, dict)
                        else None
                    )
                    if raw_manifest is not None:
                        measurement_manifest = (
                            BaseStationAdapterManifest.model_validate(raw_manifest)
                        )
                    elif base_station_attempt.attempt_id is not None:
                        raise RuntimeError(
                            "BaseStation current attempt is missing its frozen manifest"
                        )
                    else:
                        # diagnostic_unbound 仍不在 execution freeze 里写入
                        # adapter/manifest；但 P2-64 后唯一 Mock 是 manifest-scoped，
                        # 诊断命令与窗口形状必须从当前已注册
                        # Mock 的 manifest 派生。simulated provenance 仍由
                        # frozen resolution 决定，不会因此进入正式 KPI。
                        measurement_manifest = getattr(
                            base_station, "adapter_manifest", None
                        )
                    base_station_samples = await self._measure_base_station_samples(
                        base_station,
                        window_s=window_s,
                        throughput_scope=throughput_scope,
                        requested_sample_count=num_windows,
                        manifest=measurement_manifest,
                        simulated_diagnostic=(
                            base_station_attempt.simulated_diagnostic
                        ),
                        # P1-74：TestCase 的统计基随 execution 冻结进窗口请求。
                        # window_s 仍只是「等多久」，它不是统计基，也证明不了
                        # 仪器统计了多少子帧。
                        statistical_basis_subframes=frozen_stat_count,
                    )
                except _BaseStationWindowBlocked as exc:
                    # A rejected native window has no authoritative connected
                    # link envelope.  Keep its raw SCPI capture in the driver
                    # log, but do not persist a fabricated "connected" row.
                    raise
                for sample in base_station_samples:
                    metrics = sample.metrics
                    latest_throughput_exchanges = list(sample.exchanges)
                    if sample.window is not None:
                        pending_base_station_windows.append(
                            (float(azimuth), sample.window)
                        )

                    # P1-63: target power / path loss / probe gain describe the
                    # requested setup; they are not UE RF measurements. Only
                    # the driver's explicit per-field validity can admit a
                    # finite value into the formal result.
                    trusted_rsrp = self._trusted_rf_kpi_value(
                        metrics,
                        key="rsrp_dbm",
                        attribute="rsrp_dbm",
                    )
                    trusted_sinr = self._trusted_rf_kpi_value(
                        metrics,
                        key="sinr_db",
                        attribute="sinr_db",
                    )
                    trusted_ri = self._trusted_rf_kpi_value(
                        metrics,
                        key="rank_indicator",
                        attribute="rank_indicator",
                    )
                    if trusted_rsrp is not None:
                        samples_rsrp.append(trusted_rsrp)
                    if trusted_sinr is not None:
                        samples_sinr.append(trusted_sinr)
                    if trusted_ri is not None:
                        samples_ri.append(trusted_ri)
                    trusted_tput = self._trusted_throughput_value(
                        metrics,
                        required_scope=throughput_scope,
                    )
                    if trusted_tput is not None:
                        samples_tput.append(trusted_tput)
                    # P1 (Codex #126): ThroughputMetrics.mcs_dl 默认 0 —— 真 UXM 不报
                    # DL_MCS 时保持 0, 不能当有效样本 (否则众数 0 < 请求 → 误判 clamp 把
                    # 整组有效测量 abort)。只收真实报告的 (>0); 0/None 都视作"未报" skip。
                    if frozen_mac_profile.profile.kind == "nr_throughput":
                        _mcs = getattr(metrics, "mcs_dl", None)
                        mcs_samples.append(
                            _mcs if (_mcs and _mcs > 0) else None
                        )

                if (
                    latest_throughput_exchanges
                    and hasattr(base_station, "build_p0_5_throughput_evidence")
                ):
                    try:
                        record_base_station_throughput_capture(
                            context.test_execution,
                            requirement_id=f"base_station.throughput.azimuth.{az_idx:03d}",
                            requested={
                                "azimuth_deg": azimuth,
                                "window_s": window_s,
                            },
                            driver=base_station,
                            exchanges=latest_throughput_exchanges,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[%s] BaseStation %.1f° E4 证据归档失败；正式判定将保持 unknown",
                            context.test_execution.id,
                            azimuth,
                        )
                # 每个方位只提交一次：同时持久化转台与最终吞吐窗证据，避免同一
                # TestExecution.config JSONB 在一个角度内被重复整块改写。
                context.db.commit()

                az = {
                    "azimuth_deg": azimuth,
                    # Mock values remain useful while stepping through the
                    # loop, but must not enter formal measurement/KPI/report
                    # fields. Provenance is carried at phase and row level.
                    "rsrp_dbm": (
                        None if measurement_simulated or not samples_rsrp
                        else sum(samples_rsrp) / len(samples_rsrp)
                    ),
                    "rsrp_valid": not measurement_simulated and bool(samples_rsrp),
                    "rsrp_sample_count": len(samples_rsrp),
                    "sinr_db": (
                        None if measurement_simulated or not samples_sinr
                        else sum(samples_sinr) / len(samples_sinr)
                    ),
                    "sinr_valid": not measurement_simulated and bool(samples_sinr),
                    "sinr_sample_count": len(samples_sinr),
                    "throughput_mbps": (
                        None if measurement_simulated or not samples_tput
                        else sum(samples_tput) / len(samples_tput)
                    ),
                    "throughput_valid": (
                        not measurement_simulated and bool(samples_tput)
                    ),
                    "throughput_scope": (
                        throughput_scope
                        if samples_tput
                        else ThroughputMetrics.SCOPE_UNKNOWN
                    ),
                    "throughput_sample_count": len(samples_tput),
                    "rank_indicator": (
                        None if measurement_simulated or not samples_ri
                        else sum(samples_ri) / len(samples_ri)
                    ),
                    "rank_indicator_valid": (
                        not measurement_simulated and bool(samples_ri)
                    ),
                    "rank_indicator_sample_count": len(samples_ri),
                    "num_samples": len(samples_rsrp),
                    "rsrp_std_db": (
                        None if measurement_simulated or not samples_rsrp
                        else stddev(samples_rsrp)
                    ),
                    "sinr_std_db": (
                        None if measurement_simulated or not samples_sinr
                        else stddev(samples_sinr)
                    ),
                    "throughput_std_mbps": (
                        None
                        if measurement_simulated or not samples_tput
                        else stddev(samples_tput)
                    ),
                    "measurement_source": "simulated" if measurement_simulated else "instrument",
                    "measurement_verified": not measurement_simulated,
                    "active_probe_id": az_meta.get("probe_id"),
                    "probe_pattern_id": az_meta.get("probe_pattern_id"),
                    "probe_pattern_gain_dbi": az_meta.get("pattern_gain_dbi"),
                    "path_loss_compensation_db": az_path_loss_db,
                    "path_loss_source": (
                        "rf_chain" if az_meta.get("path_loss_db") is not None else "chamber_avg"
                    ),
                }
                azimuth_results.append(az)

                if measurement_simulated:
                    logger.info(
                        "  azimuth=%.0f°: KPI=N/A (simulated sources=%s)",
                        azimuth,
                        ",".join(simulated_sources),
                    )
                elif az["throughput_mbps"] is None:
                    logger.warning(
                        "  azimuth=%.0f°: Tput=N/A（本方位没有显式有效的吞吐 KPI 窗口）",
                        azimuth,
                    )
                elif not all(
                    az.get(flag) is True
                    for flag in (
                        "rsrp_valid",
                        "sinr_valid",
                        "rank_indicator_valid",
                    )
                ):
                    logger.warning(
                        "  azimuth=%.0f°: Tput=%.0f Mbps, "
                        "RF KPI=N/A（缺逐指标真实读数）",
                        azimuth,
                        az["throughput_mbps"],
                    )
                else:
                    logger.info(
                        "  azimuth=%.0f°: RSRP=%.1f, SINR=%.1f, Tput=%.0f Mbps, RI=%.2f",
                        azimuth,
                        az["rsrp_dbm"],
                        az["sinr_db"],
                        az["throughput_mbps"],
                        az["rank_indicator"],
                    )

            total_duration = loop.time() - t_start

            # 三里程碑的 throughput 那一格用它。**从实测样本算, 不是流程走到就算数** ——
            # 方位扫描不会因为吞吐为 0 而中止, 所以"跑完了"跟"跑出数了"是两件事。
            # ⚠ `throughput_mbps` 可能是 **None**（驱动没读到 / mock 路径 / KPI 查询
            #   失败时那一格就是 None）—— 直接 `sum()` 会抛
            #   `TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'`，
            #   把整个 measure 相位炸掉。2026-08-07 实证：本行是我加三里程碑时写的，
            #   `test_analysis_reads_what_measure_wrote` 当场红（值形态没枚举 None）。
            # ⚠ None **不能当 0 算进平均** —— 那会把"没测到"伪装成"测到了但是 0"，
            #   拉低均值、制造假的低吞吐读数。只对**真有数**的样本求平均；
            #   一个有效样本都没有时 mean=None，里程碑 throughput 那格保持 unknown。
            _tput_samples = [
                a["throughput_mbps"] for a in azimuth_results
                if a.get("throughput_mbps") is not None
            ]
            _mean_tput_mbps = (
                sum(_tput_samples) / len(_tput_samples) if _tput_samples else None
            )
            throughput_verified = self._all_requested_throughput_is_valid(
                config.azimuths_deg,
                azimuth_results,
                required_scope=throughput_scope,
            )
            rf_kpi_trust = build_rf_kpi_trust(
                requested_azimuths=config.azimuths_deg,
                azimuth_results=azimuth_results,
                source=("simulated" if measurement_simulated else "explicit_real"),
            )
            formal_rf_kpi_verified = rf_kpi_trust_is_formally_verified(
                rf_kpi_trust
            )

            # --- P2-11 Phase 6 (MCS index 线): AMC off 时实测生效 mcs_dl vs 请求 mcs ---
            # UE 撑不住请求 MCS → 静默 clamp (吞吐反映 clamp 后 MCS 却当请求 MCS 测)。是
            # throughput **实际生效回读** (区别于 layers/modulation 的 attach 后 UE
            # capability 核对)。AMC on / 无样本 → skip。strict 复用 precheck_strict_cell_config。
            from app.services.mimo_ota.cell_config_consistency import (
                check_mcs_consistency,
            )
            from app.services.instrument_hal_service import is_mock_driver
            mcs_request = _frozen_mcs_consistency_request(frozen_mac_profile)
            if mcs_request is not None:
                requested_mcs, enable_amc = mcs_request
            else:
                # LTE RMC has no NR MCS truth.  Deliberately select the existing
                # AMC-skip branch without reading the legacy NR fields.
                requested_mcs = 0
                enable_amc = True
            mcs_result = check_mcs_consistency(
                requested_mcs=requested_mcs,
                enable_amc=enable_amc,
                measured_mcs_samples=mcs_samples,
                bs_is_real=(
                    base_station is not None and not is_mock_driver(base_station)
                ),
            )
            if not mcs_result.consistent and config.precheck_strict_cell_config:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "P2-11 Phase 6 MCS 一致性校验失败: " + (mcs_result.reason or "")
                    ),
                    measurements={"mcs_consistency": mcs_result.to_payload()},
                )
            if not mcs_result.consistent:
                logger.warning(
                    "[%s] P2-11 Phase 6 MCS 不一致 (precheck_strict_cell_config=False, "
                    "继续): %s",
                    context.test_execution.id,
                    mcs_result.reason,
                )

            result_payload: Dict[str, Any] = {
                "cdl_model_name": config.cdl_model_name,
                "frequency_ghz": pcell.frequency_hz / 1e9,
                "mimo_config": f"{config.mimo_layers}x{config.mimo_layers}",
                "azimuth_results": azimuth_results,
                "measurement_source": "simulated" if measurement_simulated else "instrument",
                "measurement_verified": not measurement_simulated,
                "throughput_verified": throughput_verified,
                "throughput_scope": throughput_scope,
                "rf_kpi_trust": rf_kpi_trust,
                "formal_rf_kpi_verified": formal_rf_kpi_verified,
                "simulated_sources": simulated_sources,
                "total_duration_s": total_duration,
                "engine_mode": config.engine_mode,
                "calibration_entries_used": len(calibration_entries) if calibration_entries else 0,
                "path_loss_compensation_db": avg_path_loss_db,
                "path_loss_certificate_id": (
                    str(path_loss_cert.id) if path_loss_cert is not None else None
                ),
                "path_loss_calibration_use_mock": selected_path_loss_use_mock,
                "path_loss_rejected_certificate_id": (
                    str(selected_path_loss_cert.id)
                    if selected_path_loss_cert is not None
                    and path_loss_cert is None
                    else None
                ),
                "path_loss_application": path_loss_application,
                "path_loss_per_chain_used": chains_used,
                "path_loss_per_chain_available": len(per_chain_pl),
                # P1-12 audit (sibling QZ #79 / TRP #80): no path-loss cert →
                # avg_path_loss_db=0.0, RSRP baseline UNcompensated. The RSRP /
                # throughput numbers then aren't calibrated — flag explicitly so
                # report/GUI mark 未验证(无路损校准) rather than presenting them as
                # calibrated. (Real mode is already gated by P1-8 precheck cal
                # gate; this marks the mock/bypass path + carries provenance.)
                "path_loss_verified": (
                    path_loss_cert is not None
                    and _is_path_loss_certificate_verified(
                        selected_path_loss_use_mock
                    )
                ),
                "switch_topology": topology_result.to_payload(),
                "mcs_consistency": mcs_result.to_payload(),
                "sampling": {
                    "num_windows_per_azimuth": num_windows,
                    "window_duration_s": window_s,
                    "stat_count_subframes": frozen_stat_count,
                    "mac_profile_digest": frozen_mac_profile.profile_digest,
                },
                "carrier_aggregation": {
                    "num_component_carriers": len(ccs),
                    "pcell": {
                        "frequency_ghz": pcell.frequency_hz / 1e9,
                        "bandwidth_mhz": pcell.bandwidth_mhz,
                        "band": pcell.band,
                    },
                    "scells": scells_added,
                },
                "dut_disconnect_warnings": dut_disconnect_warnings,
                "azimuths_completed": len(azimuth_results),
                "azimuths_requested": len(config.azimuths_deg),
                # Phase 2b: input-level closed-loop telemetry (success/skipped/
                # opt-out audit). strict-fail 路径不会到这里 — 早期 return 时
                # input_level_calibration 已经塞进 measurements。
                "input_level_calibration": input_level_payload,
                # P2-11 Phase 1: 多方频率一致性校验 (一致/opt-out 路径留 audit;
                # strict-fail 路径早期 return 时已塞进 measurements)。
                "frequency_consistency": frequency_consistency_payload,
                # 2026-08-07 现场三里程碑。⚠ throughput 这一格**从实际扫出来的
                # 平均吞吐派生**, 不是"跑到这儿了就算成功" —— 全 0 吞吐照样会
                # 走到这里(方位扫描不因 0 吞吐中止), 那种情况必须显示 False。
                "attach_milestones": {
                    **milestones,
                    "throughput": (
                        None
                        if not azimuth_results
                        else {
                            "stage": "throughput",
                            "ok": (
                                None
                                if _mean_tput_mbps is None
                                else _mean_tput_mbps > 0.0
                            ),
                            "mean_mbps": _mean_tput_mbps,
                            "azimuths_completed": len(azimuth_results),
                            "reason": (
                                "吞吐 KPI 未读到显式有效样本"
                                if _mean_tput_mbps is None
                                else (
                                    "ok" if _mean_tput_mbps > 0.0 else
                                    "各方位平均吞吐为 0 —— 链路通但没数据流过"
                                )
                            ),
                        }
                    ),
                },
                "controlled_dut_attach": controlled_attach,
            }

            # ``asc_files_loaded`` is ASC-specific (ExternalWaveformStrategy /
            # ExternalAscPathStrategy): GCM mode (NativeModelStrategy) doesn't
            # consume .asc files at all — the channel is generated inside
            # Keysight GCM Studio's native runtime. Audit 2026-05-17 Y2 (PR #53)
            # established the omit-in-GCM rule; 2026-05-18 P0-7 extended it to
            # also cover the new EXTERNAL_ASC mode (still ASC-based, so the
            # diagnostic signal "emulator loaded waveforms" remains meaningful).
            # In EXTERNAL_ASC mode we additionally stamp the operator-provided
            # source path for audit-trail traceability.
            if engine_mode != EngineMode.GCM_NATIVE:
                result_payload["asc_files_loaded"] = True
                if engine_mode == EngineMode.EXTERNAL_ASC:
                    result_payload["asc_source"] = "external"
                    result_payload["external_asc_source_path"] = config.asc_source_path
                else:
                    result_payload["asc_source"] = "channel_engine_service"
            else:
                # P2-11 Phase 2: GCM .smu 来源 audit (TestCase 驱动 vs 驱动默认 fallback)
                result_payload["emulation_file"] = config.emulation_file
                result_payload["emulation_file_source"] = (
                    "testcase" if config.emulation_file else "driver_default"
                )
        except _CaSetupBlocked as exc:
            ca_setup_blocker = str(exc)
        finally:
            if base_station_config_capture_manager is not None:
                base_station_config_capture_manager.__exit__(None, None, None)
            cleanup_result = await cleanup_chamber_instruments(
                hal,
                context.test_execution.id,
                expected_operator_stop_generation=motion_stop_generation,
            )
            cleanup_warnings = list(cleanup_result.warnings)
            if (
                pending_base_station_windows
                and base_station_attempt.attempt_id is not None
            ):
                from app.services.execution_scpi_evidence import (
                    append_base_station_measurement_window,
                )

                for azimuth, window in pending_base_station_windows:
                    append_base_station_measurement_window(
                        context.db,
                        context.test_execution.id,
                        attempt_id=base_station_attempt.attempt_id,
                        lease_identity=base_station_attempt.lease_identity,
                        position={
                            "azimuth_deg": azimuth,
                            "elevation_deg": 0.0,
                        },
                        ue_link_state="connected",
                        window=window,
                        cleanup=cleanup_result.base_station,
                    )
                context.db.commit()

        if ca_setup_blocker is not None:
            error_message = ca_setup_blocker
            if cleanup_warnings:
                error_message = (
                    f"{error_message} 清理未完整确认："
                    f"{'; '.join(cleanup_warnings)}"
                )
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                measurements=(
                    {"cleanup_warnings": cleanup_warnings}
                    if cleanup_warnings
                    else {}
                ),
                warnings=cleanup_warnings or None,
                error_message=error_message,
            )

        if cleanup_warnings:
            result_payload["cleanup_warnings"] = cleanup_warnings

        # Surface the uncalibrated-path-loss case as a result warning (not just
        # a server-side log) so it rides into the report / operator view.
        measure_warnings: List[str] = list(cleanup_warnings or [])
        if not result_payload.get("measurement_verified"):
            measure_warnings.insert(
                0,
                "⚠️ Mock/缺失仪器参与本次测量：KPI 与报告数值保持 N/A，"
                "不得作为正式测试结论。",
            )
        if (
            path_loss_application["status"] != "applied"
            or path_loss_application["provenance"] != "real"
        ):
            measure_warnings.insert(
                0,
                "⚠️ " + path_loss_application_message(path_loss_application),
            )
        if not result_payload.get("throughput_verified"):
            measure_warnings.insert(
                0,
                "⚠️ 至少一个方位没有显式有效的吞吐 KPI 样本：吞吐结论保持 N/A，"
                "不得将缺测默认值当作 0 Mbps 进入正式判定。",
            )
        if not result_payload.get("formal_rf_kpi_verified"):
            measure_warnings.insert(
                0,
                "⚠️ RSRP/SINR/RI 缺少逐指标、逐方位的显式真实读数："
                "RF KPI 结论保持 N/A，不得由目标配置、默认值或合成值替代。",
            )
        if not (
            result_payload.get("frequency_consistency") or {}
        ).get("fully_verified", False):
            measure_warnings.insert(
                0,
                "⚠️ F64 频率身份未完整闭环：中心频率按仪表实时回读，"
                "但当前场景带宽缺少已登记 ChannelAsset/SCD 声明或仍为 unknown。"
                "本结果不能作为 P0-5 完整闭环证据。",
            )

        write_phase_result(context.test_execution, "measure", result_payload)
        context.db.commit()

        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
            warnings=measure_warnings or None,
        )

    # ---------------------------------------------------------------------
    # 开关 3 块 2: 手动定标 — 显式输入参考 (+crest), 跳过 AUTOSET 闭环
    # ---------------------------------------------------------------------
    async def _apply_output_gain(
        self, *, emulator, gain_db: float, execution_id: str,
    ) -> Optional[str]:
        """把 `f64_output_gain_db` 下发到**当前仿真真实占用的每个物理输出口**。

        返回 None = 成功; 返回字符串 = 失败原因 (调用方据此把步骤判 FAILED)。
        抽成独立方法与 `_apply_manual_input_reference` 同族 —— 也是为了能直接测
        "拓扑未知就拒发、且一条 SCPI 都不发"这个分支 (埋在 execute() 里测不到)。

        F64R-2: 遍历的是驱动**回读**的输出口号列表 (`get_active_output_ports`), 不是
        `min(tx*rx, channel_count)`:
          · `tx×rx` 是**逻辑通道**口径 —— MPAC OTA 下 4 输入 × 32 探头 = 128 通道而输出
            口只有 32, 拿 tx×rx(=16) 当上界会让 32 个探头**只配到前 16**, 17-32 留工程
            默认 (门审 #217 F1 当时收敛到"活跃通道"方向对, 但口径仍是逻辑通道不是物理口);
          · 端口号也不假定 1..N —— 仿真可能占用非连续口 (如 {2,4})。
        读不到 → fail-loud, **不回退猜口数** (用户 2026-07-24 拍板: 配错口比不配更伤)。
        """
        # 先让驱动按需补回读 (正常步骤里 load 刚跑过是热的; 但操作员单点这一步、或后端
        # 重启后接着跑时缓存是空的 —— 那时硬拒等于逼人重 load, 而 load 会打断跑着的仿真)
        _ensure = getattr(emulator, "ensure_topology", None)
        if callable(_ensure):
            try:
                await _ensure()
            except Exception:  # noqa: BLE001 — 补读失败等同"读不到", 下面 fail-loud
                pass
        ports = _read_port_list(emulator, "get_active_output_ports")
        if not ports:
            return (
                f"F64 输出增益下发拒绝 (f64_output_gain_db={gain_db}): 物理输出口未知 "
                f"— 仿真未加载 / 拓扑回读失败 / 驱动无拓扑回读能力。不按猜测的端口号下发增益。"
                f"(本参数**没有** per-step 端口选项 → override 是唯一解) "
                f"{_TOPOLOGY_ESCAPE_HINT}"
            )
        for port in ports:
            if not await emulator.set_output_gain(port, gain_db):
                return (
                    f"F64 输出增益下发失败 (f64_output_gain_db={gain_db}, "
                    f"output={port}) — 明细见驱动日志。"
                )
        logger.info(
            "[%s] F64 输出增益 %.1f dB 已下发到输出口 %s",
            execution_id, gain_db, ports,
        )
        return None

    async def _apply_manual_input_reference(
        self,
        *,
        emulator: Any,
        config: Any,
        execution_id: Any,
    ) -> Dict[str, Any]:
        """f64_input_ref_dbm 显式给定时的手动定标路径。

        直接 set 输入参考 (INP:LEV:AMP × 全输入) + 可选 crest, 然后读回
        (measure_input) 进 payload 作调试反馈; 不跑 AUTOSET 闭环。CE 缺
        能力 (mock / 非 F64) → skipped=True (与闭环的 capability-skip 语义
        一致, mock dry-run 不受影响; 真 F64 驱动必有这些方法)。下发被拒 →
        success=False, 由上层 strict 门 fail-loud。
        """
        ref = float(config.f64_input_ref_dbm)
        crest = (
            float(config.f64_crest_db)
            if config.f64_crest_db is not None else None
        )
        payload: Dict[str, Any] = {
            "mode": "manual",
            "requested_ref_dbm": ref,
            "requested_crest_db": crest,
            "skipped": False,
            "success": False,
            "readback": [],
            "failure_reason": None,
        }
        if not hasattr(emulator, "set_baseband_power") or (
            crest is not None and not hasattr(emulator, "set_crest_factor")
        ):
            payload["skipped"] = True
            payload["failure_reason"] = (
                "CE 驱动无输入参考/crest 设置能力 — 手动定标跳过 (mock/非 F64)"
            )
            logger.info(
                "[%s] 手动定标跳过: CE 缺 set_baseband_power/set_crest_factor",
                execution_id,
            )
            return payload
        if not await emulator.set_baseband_power(ref):
            payload["failure_reason"] = f"输入参考下发被拒 ({ref} dBm)"
            logger.error("[%s] 手动定标: %s", execution_id, payload["failure_reason"])
            return payload
        # F64R-2: crest 是**逐输入口**下发, 端口号问驱动回读的真实拓扑 (GROUP:INPUTS:GET?),
        # 不再读 _tx_antennas 也不假定 1..N —— 前者冷重启/手动加载 4x4 .smu 后会停在构造
        # 默认 2 只覆盖输入 1/2, 后者在非连续端口分配下会误配。
        in_ports = _read_port_list(emulator, "get_active_input_ports") or []
        if crest is not None and not in_ports:
            # ⚠ 要下发 crest 却不知道发给谁 → **fail-loud, 不静默零下发报成功**。
            # 旧代码用 _tx_antennas (实例默认 2, 永不为 0) 一定会发几条; 换成回读后
            # 才可能"一条都没发", 此时若仍 success=True 就是本项目一直在抓的零下发
            # 假成功 (操作员以为 crest 配上了)。
            payload["failure_reason"] = (
                f"crest 下发拒绝 ({crest} dB): 物理输入口未知 (仿真未加载 / 拓扑回读失败)"
                f" — 不按猜测的端口号下发"
            )
            logger.error("[%s] 手动定标: %s", execution_id, payload["failure_reason"])
            return payload
        if crest is not None:
            for i in in_ports:
                if not await emulator.set_crest_factor(i, crest):
                    payload["failure_reason"] = f"crest 下发被拒 (input {i}, {crest} dB)"
                    logger.error(
                        "[%s] 手动定标: %s", execution_id, payload["failure_reason"]
                    )
                    return payload
        # 读回反馈 (只读; 单口读不到不判定标失败 — 无信号态 measure 会 None)
        if hasattr(emulator, "measure_input"):
            for i in in_ports:
                m = await emulator.measure_input(i, 1.0)
                payload["readback"].append({
                    "input_num": i,
                    "avg_dbm": m[0] if m else None,
                    "crest_db": m[1] if m else None,
                })
        payload["success"] = True
        logger.info(
            "[%s] 手动定标完成: ref=%.1f dBm crest=%s × %d 输入 (readback=%s)",
            execution_id, ref, crest, len(in_ports),
            [r["avg_dbm"] for r in payload["readback"]],
        )
        return payload

    # ---------------------------------------------------------------------
    # P0-8 Step 2 Phase 2b: F64 输入操作点闭环 wiring
    # ---------------------------------------------------------------------
    async def _run_input_level_closed_loop(
        self,
        *,
        emulator: Any,
        base_station: Any,
        config: Any,
        execution_id: Any,
        plan: BaseStationExecutionPlanItem,
    ) -> Dict[str, Any]:
        """跑 InputLevelController + 落遥测。返回 input_level_calibration payload。

        CE 按原子接口检测；BS 侧判据只来自 execution-frozen 计划项（P2-50）：
        计划未 planned → 跳过闭环（沿用既有 Warning/UNKNOWN 语义）；计划
        planned 但 adapter 缺 ``set_downlink_power`` → 计划/实现漂移，
        fail-loud。跑过 controller 后无论成败都返回结构化 payload, 上层据
        success/skipped + strict flag 决定 phase verdict。
        """
        def _power_fields(value: Optional[float]) -> Dict[str, Any]:
            fields: Dict[str, Any] = {"base_station_dl_power_dbm": value}
            legacy_field = getattr(
                base_station, "input_level_legacy_power_field", None
            )
            if isinstance(legacy_field, str) and legacy_field:
                fields[legacy_field] = value
            return fields

        required_ce_methods = (
            "autoset_inputs",
            "measure_input",
            "get_input_level_limits",
            "set_input_measurement_mode",
            "set_burst_trigger_level",
            "get_group_clipping",
            "get_system_status",
        )
        ce_caps = {m: hasattr(emulator, m) for m in required_ce_methods}
        ce_supports = all(ce_caps.values())
        bs_supports = plan.planned is True
        bs_power_method = getattr(base_station, "set_downlink_power", None)
        if bs_supports and not callable(bs_power_method):
            raise RuntimeError(
                "执行计划声明输入电平闭环能力，但 adapter 缺 set_downlink_power"
                "（计划与实现漂移）"
            )

        if not ce_supports or not bs_supports:
            reason_parts: List[str] = []
            missing_ce = [m for m, ok in ce_caps.items() if not ok]
            if missing_ce:
                reason_parts.append(f"CE 缺接口: {missing_ce}")
            if not bs_supports:
                # 计划项的 reason 已在冻结时吸收 input_level_unavailable_reason
                # （声明层的解释），这里不再另行探测 adapter。
                reason_parts.append(plan.reason)
            skip_reason = (
                "; ".join(reason_parts)
                + " — 至少一方缺 capability (e.g. mock driver / 未实现 atomic 的 vendor), "
                "跳过闭环 (不影响 mock dry-run)"
            )
            logger.info(
                "[%s] Phase 2b: input-level closed loop SKIPPED — %s",
                execution_id, skip_reason,
            )
            return {
                "skipped": True,
                "formal_eligible": False,
                "reason": skip_reason,
            }

        # active_inputs 推导 (Codex on PR #98): **跟 BS 实际驱动的 layer 数 1:1**,
        # 不是 CE 的 _tx_antennas。execute() 早期已经 set_cell_config(mimo_layers=
        # config.mimo_layers), BS 只发 config.mimo_layers 路 → F64 也只有这几路
        # input 有信号; 多 autoset 一路 = 在 unconnected 端口上 autoset, no-signal
        # fail-loud, strict 模式把 measure phase 早死在 azimuth loop 之前。
        # CE 的**物理输入口数** (.smu 实际暴露的输入端口) 只用作 sanity bound:
        # BS layers 超过它 = 物理上跑不了 (e.g. 2 输入口的 .smu 上 BS 想发 4 layer)。
        # F64R-2: 口数问驱动回读的真实拓扑 (MODEL:INFO? 的 inputs), 不再读
        # _tx_antennas 缓存 —— 后者冷重启 / 操作员手动加载后会 stale 在构造默认 2,
        # 把本来跑得了的 4 layer 误判成"物理上跑不了"。读不到 → 跳过这道 sanity 检查
        # (与旧 ce_tx is None 的降级一致): 拓扑未知不该拦住测量, 真配错口时由下游
        # 写操作的 fail-loud 兜底。
        n_layers = int(config.mimo_layers)
        # ⚠ 补读必须在**读判定值之前** (F64R-2 复审 P2, 我上一轮把它放在门之后引入的 bug):
        # 门读冷值 None → 直接跳过; 紧接着补读回 2 个口 → 下面的 `[:n_layers]` 把
        # mimo_layers=4 静默截成 2 个口 → BS 发 4 层只定标 2 路、另 2 路留工程默认,
        # 而闭环报 success=True。判定与下发必须同源, 否则门形同虚设。
        _ensure = getattr(emulator, "ensure_topology", None)
        if callable(_ensure):
            try:
                await _ensure()
            except Exception:  # noqa: BLE001 — 补读失败等同读不到, 走下面的降级
                pass
        ce_inputs = _read_port_count(emulator, "get_active_input_count")
        if ce_inputs is not None and n_layers > ce_inputs:
            msg = (
                f"拓扑不匹配: config.mimo_layers={n_layers} > CE 物理输入口数={ce_inputs} "
                f"(BS 想发的 layer 数超过当前 .smu 输入端口数, 物理上跑不了)。"
                f" 操作员应调整 config.mimo_layers 或换 .smu "
                f"(默认 3600M 是 4x4, set_mimo_config 可改)。"
            )
            logger.error("[%s] Phase 2b: %s", execution_id, msg)
            return {
                "success": False,
                "failure_reason": msg,
                "topology_mismatch": True,
                # F64R-2 改名: 装的是**物理输入口数** (回读真值), 旧名 ce_tx_antennas
                # 是 tx 天线口径 —— 名实不符正是本 PR 要治的病。
                "ce_input_ports": ce_inputs,
                "config_mimo_layers": n_layers,
                "iterations": 0,
                **_power_fields(None),
                "clipping_per_mille": None,
                "system_warnings": [],
                "operating_point": [],
                "active_inputs": list(range(1, n_layers + 1)),
                "strict": bool(config.precheck_strict_input_level),
            }
        # F64R-2: 闭环要 autoset / measure 的是**物理输入口号**, 优先用驱动回读的真实
        # 口号 (取前 n_layers 个 —— BS 只驱动这么多 layer, 多 autoset 一路 = 在无信号口
        # 上 autoset 会 fail-loud)。回读不到才退回旧的 1..n_layers 推导。
        # ⚠ 不修的话同一个 TestCase 换个开关就走两套口号: 给了 f64_input_ref_dbm 走
        # 手动定标路 (已用回读口号), 不给走这条闭环 —— 非连续口 {3,5} 下闭环会打到
        # 口 1、2 → 无信号 → measure phase 在 azimuth loop 之前早死。
        # (补读已在上面的 sanity 门之前做过 —— 判定与下发同源, 别在这里再补)
        _real_in = _read_port_list(emulator, "get_active_input_ports")
        if _real_in:
            if len(_real_in) < n_layers:
                # 口号比 layer 少 → **不静默截断**。截断 = BS 发 n 层却只定标前几路,
                # 剩下的留工程默认 (输入不平衡), 而闭环照报 success —— 正是本 PR 要杀的
                # "还回 ok=true"。上面的 sanity 门已经拦了口数已知的情形, 这里兜住
                # "口数读到了但口号列表更短"的不一致。
                msg = (
                    f"拓扑不匹配: config.mimo_layers={n_layers} > 回读到的物理输入口号"
                    f" {_real_in} (共 {len(_real_in)} 个) — 不静默只定标前几路。"
                )
                logger.error("[%s] Phase 2b: %s", execution_id, msg)
                return {
                    "success": False,
                    "failure_reason": msg,
                    "topology_mismatch": True,
                    "ce_input_ports": len(_real_in),
                    "config_mimo_layers": n_layers,
                    "iterations": 0,
                    **_power_fields(None),
                    "clipping_per_mille": None,
                    "system_warnings": [],
                    "operating_point": [],
                    "active_inputs": list(_real_in),
                    "strict": bool(config.precheck_strict_input_level),
                }
            active_inputs = tuple(_real_in[:n_layers])
        elif callable(getattr(emulator, "get_active_input_ports", None)):
            # Codex #224 P1: 驱动**有**拓扑能力 (真 F64) 但补读后口号仍未知 (正是
            # GROUP:*/MODEL:INFO? 真机不支持的形态) → **fail-loud, 不许退回猜 1..n**。
            # 这里推出的口号会被 controller 当**显式端口**传给 autoset_inputs /
            # set_input_measurement_mode / measure_input, 而显式端口按契约**绕过**
            # 驱动侧的 fail-loud 门 (显式优先) —— 猜的口号畅通无阻, 在错误的输入口上
            # 定标/读数。猜 1..n 只留给**无拓扑能力**的驱动 (下一分支)。
            msg = (
                f"拓扑不匹配: F64 物理输入口号未知 (仿真未加载 / 拓扑回读失败) — "
                f"不按猜测的 1..{n_layers} 定标输入。"
                f"(真机若不支持 GROUP:*/MODEL:INFO?, 可在仪器 connection_params 配 "
                f"topology_override 声明口号)"
            )
            logger.error("[%s] Phase 2b: %s", execution_id, msg)
            return {
                "success": False,
                "failure_reason": msg,
                "topology_mismatch": True,
                "ce_input_ports": None,
                "config_mimo_layers": n_layers,
                "iterations": 0,
                **_power_fields(None),
                "clipping_per_mille": None,
                "system_warnings": [],
                "operating_point": [],
                "active_inputs": [],
                "strict": bool(config.precheck_strict_input_level),
            }
        else:
            # 无拓扑能力的驱动 (mock / 非 F64, 连 getter 都没有): 保留旧的 1..n 推导,
            # mock dry-run 不受影响 (capability-based 降级, 与全仓 hasattr 门同族)。
            active_inputs = tuple(range(1, n_layers + 1))

        from app.services.input_level_controller import InputLevelController

        # 开关 3 块 2: 闭环起点功率参数化 — None 用 controller 默认 (-10 dBm,
        # 比 EMQuest -46 基线热 36 dB, 门审 #216 F3 披露的雷); 现场可显式给
        # 温和起点 (如 -46) 免大功率起步冲 F64 输入。
        # getattr: 本方法被测试以迷你 config 对象直调 (duck-typed), 新字段
        # 用 getattr 兜底 — 缺属性视同 None (用 controller 默认)
        _ctrl_kwargs: Dict[str, Any] = {}
        _initial = getattr(config, "input_loop_initial_dl_power_dbm", None)
        if _initial is not None:
            _ctrl_kwargs["initial_base_station_dl_power_dbm"] = _initial
        controller = InputLevelController(
            ce_driver=emulator,
            bs_driver=base_station,
            active_inputs=active_inputs,
            **_ctrl_kwargs,
        )
        logger.info(
            "[%s] Phase 2b: input-level closed loop START — active_inputs=%s",
            execution_id, active_inputs,
        )
        il_result = await controller.establish()

        payload: Dict[str, Any] = {
            "success": il_result.success,
            **_power_fields(il_result.base_station_dl_power_dbm),
            "clipping_per_mille": il_result.clipping_per_mille,
            "iterations": il_result.iterations,
            "system_warnings": il_result.system_warnings,
            "operating_point": [
                {
                    "input_num": op.input_num,
                    "avg_dbm": op.avg_dbm,
                    "crest_db": op.crest_db,
                }
                for op in il_result.operating_point
            ],
            "failure_reason": il_result.failure_reason,
            "imbalance_db": il_result.imbalance_db,        # #2001(1): 多端口不平衡 max-min
            "imbalance_status": il_result.imbalance_status,  # ok/marginal/excessive/None
            "active_inputs": list(active_inputs),
            "strict": config.precheck_strict_input_level,
        }

        if il_result.success:
            logger.info(
                "[%s] Phase 2b: input-level closed loop CONVERGED "
                "(iter=%d, BaseStation=%.1f dBm, clipping=%s‰)",
                execution_id,
                il_result.iterations,
                il_result.base_station_dl_power_dbm,
                il_result.clipping_per_mille,
            )
        elif config.precheck_strict_input_level:
            # strict-fail: 这里只 log, 上层根据 success 字段触发早期 FAILED return。
            logger.error(
                "[%s] Phase 2b: input-level closed loop FAILED (strict) — %s",
                execution_id, il_result.failure_reason,
            )
        else:
            # opt-out: 降级为 warning, 继续 azimuth 扫描 (audit-only)
            logger.warning(
                "[%s] Phase 2b: input-level closed loop FAILED "
                "(precheck_strict_input_level=False, audit-only) — %s",
                execution_id, il_result.failure_reason,
            )
        return payload
