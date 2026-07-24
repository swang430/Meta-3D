"""Phase 3: Static MIMO throughput measurement (the core of MIMO OTA).

Replaces commissioning_service.phase3_static_mimo_test. The flow:

1. Set base station cell config + 3GPP MAC throughput parameters from the
   bound TestCase.configuration (no longer hard-coded in the service).
2. Generate the CDL channel via ChannelEngineClient and load it into the
   channel emulator (ASC or GCM strategy depending on engine_mode).
3. Walk the turntable through each azimuth in config.azimuths_deg, sample
   throughput from the base station + simulate RSRP/SINR (since the BS does
   not currently report those), and aggregate per-azimuth statistics.

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
import random
from typing import Any, Dict, List, Optional

from app.models.chamber import ChamberConfiguration
from app.services.mimo_ota.executors._helpers import (
    load_mimo_ota_config,
    stddev,
    write_phase_result,
)
from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.schemas.mimo_ota.config import MIMOOTAStepType
from app.hal.propsim_f64 import _TOPOLOGY_ESCAPE_HINT

logger = logging.getLogger(__name__)

# Phase 2d: each "sample" is now an independent UXM stat window (≈ stat_count
# subframes ≈ stat_count ms), not a 20ms poll. Production wants ≥ 5-12 windows
# per azimuth for stable std; dev caps at 3 to keep smoke tests fast.
_DEV_SAMPLE_WINDOWS = 3
# Floor for window duration so mock paths still take a perceptible amount of
# time (helps surface ordering bugs) but don't actually wait 5s in unit tests.
_MOCK_WINDOW_FLOOR_S = 0.05

# Phase 2m: DUT 掉线检测周期 (每 N 个 azimuth 检查一次而非每窗口, 节省 SCPI 流量)
# 单 azimuth 内不检查 (统计窗口本身已 >= 50ms, 中途掉线被 measure_throughput_window
# 内部 retry 兜底). azimuth 间隔检查能在转台移动期间发现, 是最佳折衷.
_DUT_HEALTH_CHECK_EVERY_N_AZIMUTHS = 1


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
    # 可选字段: 仅 TestCase 显式给 (非 None) 才驱动, 否则保持 HAL profile (backward-compat)
    if config.mimo_port_preset is not None:
        cell_cfg["mimo_port_preset"] = config.mimo_port_preset
    if config.sched_algo is not None:
        cell_cfg["sched_algo"] = config.sched_algo
    if config.csi_rs_ports is not None:
        cell_cfg["csi_rs_ports"] = config.csi_rs_ports
    return cell_cfg


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


@register_executor(MIMOOTAStepType.MEASURE.value)
class MeasureExecutor(IStepExecutor):
    """Drive the chamber + base station through the azimuth grid, collect KPIs."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        lab = context.require_lab_profile()
        config = load_mimo_ota_config(context.test_execution)

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
        )
        from app.hal.channel_emulator import ChannelLoadMode
        from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn

        hal = get_hal_service()
        positioner = hal.drivers.get("positioner")
        base_station = hal.drivers.get("baseStation")
        if positioner is None or base_station is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="positioner + baseStation drivers required (HAL)",
            )

        await positioner.connect()
        await base_station.connect()
        # Anything from here through the azimuth loop must be wrapped so an
        # exception (HAL hiccup, channel-gen timeout, DUT drop) doesn't leave
        # UXM signaling, F64 emulating, and the turntable mid-rotation.
        cleanup_warnings: List[str] = []
        try:
            # --- Phase 2g: PCell from component_carriers[0] (always populated
            # by MIMOOTAConfiguration._resolve_component_carriers); SCells
            # added below before start_signaling so RRC reconfig sees full set.
            ccs = list(config.component_carriers or [])
            pcell = ccs[0] if ccs else None
            if pcell is None:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "component_carriers is empty after schema validation — "
                        "this should be impossible; check MIMOOTAConfiguration validator"
                    ),
                )
            scells = ccs[1:]

            # P2-11 (Codex on PR #109 P1): 从 TestCase 中心频推导规范 ARFCN 显式下发。
            # 不传 arfcn 时 RealUxmDriver.set_cell_config 走 band fallback (R6 起 =
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
            # 开关 1 (uxm_config_mode): "inherit" 跳过小区参数下发, 沿用仪器当前
            # 态 (如 EMQuest 基线); 频率核对改走下方一致性网的 live 读回 (知情
            # 继承)。MAC 吞吐配置 / start_signaling / RRC reconfig 不属于小区
            # 参数, 两种模式都执行。
            uxm_inherit = config.uxm_config_mode == "inherit"
            if uxm_inherit:
                logger.info(
                    "[%s] 开关1 uxm_config_mode=inherit: 跳过 UXM 小区级参数下发 "
                    "(set_cell_config + SCell), 沿用仪器当前态; 频率核对走 live "
                    "读回。仍会写: MAC 吞吐配置 / CELL ON / RRC 按 TestCase 推 "
                    "%d 层 (层数未纳入 live 核对) / 输入闭环调 DL 功率",
                    context.test_execution.id, config.mimo_layers,
                )
            # path B 显式驱动端口路由/调度 (见 _build_pcell_cell_config); None 字段不传 →
            # 保持 HAL profile (backward-compat, 旧 case 不被默认值覆盖)。
            if not uxm_inherit:
                cell_cfg = _build_pcell_cell_config(
                    config,
                    frequency_mhz=pcell_freq_mhz,
                    arfcn=freq_mhz_to_nr_arfcn(pcell_freq_mhz),
                    bandwidth_mhz=pcell.bandwidth_mhz,
                    scs_khz=pcell.subcarrier_spacing_khz,
                    band=pcell.band,
                )
                # Codex #195 R5 P1: set_cell_config 布尔契约必须消费 — HAL 层回读对账
                # mismatch / 下发被拒都只 return False (不裸抛), 这里不检查会带着错配
                # 小区配置进测量, 正是回读门要拦的实验污染。
                ok = await base_station.set_cell_config(cell_cfg)
                if not ok:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "PCell set_cell_config 失败 (下发被拒或回读对账 mismatch, "
                            "明细见基站驱动日志) — 中止执行, 防止错配配置进测量。"
                        ),
                    )

            # --- Phase 2g: SCell add + activate for CA scenarios ---
            scells_added: List[Dict[str, Any]] = []
            if scells and uxm_inherit:
                logger.warning(
                    "[%s] 开关1 inherit: %d 个 SCell 声明被跳过 (继承模式不下发"
                    "载波) — CA 场景请用 dispatch 模式",
                    context.test_execution.id, len(scells),
                )
            elif scells and hasattr(base_station, "add_secondary_cell"):
                for cc_idx, scell in enumerate(scells, start=1):
                    # SCell 走 SCELL_CONF_FREQ 直接按 frequency_mhz 程控 (无 ARFCN
                    # band fallback, 见 add_secondary_cell) → 没有 PCell 那个坑, 不需
                    # 显式 arfcn。频率一致性校验也只比 PCell。
                    ok = await base_station.add_secondary_cell(
                        cc_idx,
                        {
                            "frequency_mhz": scell.frequency_hz / 1e6,
                            "bandwidth_mhz": scell.bandwidth_mhz,
                            "scs_khz": scell.subcarrier_spacing_khz,
                            "band": scell.band,
                        },
                    )
                    if ok:
                        scells_added.append({
                            "cc_index": cc_idx,
                            "frequency_ghz": scell.frequency_hz / 1e9,
                            "bandwidth_mhz": scell.bandwidth_mhz,
                            "band": scell.band,
                        })
                    else:
                        logger.warning(
                            "[%s] SCell %d add failed; CA may run with fewer carriers than requested",
                            context.test_execution.id, cc_idx,
                        )
                if scells_added and hasattr(base_station, "activate_secondary_cells"):
                    await base_station.activate_secondary_cells()
                logger.info(
                    "[%s] Phase 2g: PCell %.2fGHz + %d SCell(s)",
                    context.test_execution.id,
                    pcell.frequency_hz / 1e9, len(scells_added),
                )
            elif scells:
                logger.warning(
                    "[%s] Config has %d SCell(s) but baseStation driver lacks "
                    "add_secondary_cell — running PCell-only",
                    context.test_execution.id, len(scells),
                )

            # --- 3GPP MAC throughput config (was hard-coded; now from TestCase) ---
            if hasattr(base_station, "configure_mac_throughput_test"):
                await base_station.configure_mac_throughput_test(
                    mimo_layers=config.mimo_layers,
                    mcs=config.mcs,
                    enable_amc=config.enable_amc,
                    tdd_pattern=config.tdd_pattern,
                    tdd_period=config.tdd_period,
                    harq_max_trans=config.harq_max_trans,
                    harq_processes=config.harq_processes,
                    stat_count=config.stat_count,
                )

            await base_station.start_signaling()

            # --- Phase 2e: RRC reconfig pushes new layer/modulation to attached UE.
            # Some UXM firmware applies cell-config changes via RRC automatically;
            # explicit reconfig is a no-op there but harmless. Old firmware needs it.
            if hasattr(base_station, "reconfigure_rrc"):
                rrc_ok = await base_station.reconfigure_rrc(
                    mimo_layers=config.mimo_layers,
                    modulation=config.modulation,
                )
                if not rrc_ok:
                    logger.warning(
                        "[%s] RRC reconfig returned False; UE may still be on prior layer/modulation",
                        context.test_execution.id,
                    )

            # --- Resolve chamber from LabProfile, then run channel generation ---
            chamber: ChamberConfiguration = lab.chamber_config
            if chamber is None:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=f"LabProfile {lab.name} has no chamber_config",
                )

            ce_client = ChannelEngineClient(context.db)
            emulator = hal.drivers.get("channelEmulator")
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
            topology_result = orchestrate_switch_topology(
                context.db, chamber.id, mode_id=config.switch_mode_id
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
                chamber.id, config.frequency_hz, chamber,
                operating_mode=config.switch_mode_id,
            )

            # --- Phase 2a / P0: path-loss compensation ---
            # Old: chamber-wide avg (`avg_path_loss_db`) applied uniformly.
            # New: per-RFChain `total_insertion_loss_db` looked up by
            #   (active_probe_id, polarization) → connection_id, populated
            #   when the cert was created via /calibration/path-loss/start-for-lab.
            # Falls back to avg when the cert is legacy (no per-chain map) so
            # existing chamber-keyed calibrations still work.
            from app.services.path_loss_calibration_service import (
                ProbePathLossCalibrationService,
            )

            pl_service = ProbePathLossCalibrationService(context.db, use_mock=False)
            # P2-11 Phase 3 (Codex on PR #111): 按 TestCase switch_mode_id 过滤 cert,
            # 让 per-chain 线损来自请求的 RF 通路 (精确优先, 退回 legacy NULL)。
            path_loss_cert = pl_service.get_latest_calibration(
                chamber.id, config.frequency_hz / 1e6,
                operating_mode=config.switch_mode_id,
            )
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
                    config.frequency_hz / 1e6,
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
            # P2-16 S2: ChannelAsset 前置解析 (方案 A: 仅 channel_asset_id 显式给时介入,
            # 翻译成现有 config 字段, 下游 engine dispatch / strategy 不变)。
            from app.services.mimo_ota.channel_asset_resolver import (
                ChannelAssetResolveError,
                resolve_channel_asset,
            )
            try:
                resolved_asset = resolve_channel_asset(context.db, config)
            except ChannelAssetResolveError as e:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED, error_message=str(e))
            if resolved_asset is not None:
                config.engine_mode = resolved_asset.engine_mode  # source_type 派生 engine 覆盖
                # ChannelAsset 是唯一信道源: 清残留 legacy 引用 (Codex #174 P2)。saved TestCase
                # 里残留的 cdl_profile_id/scd_id 否则会让下游 asc custom 分支 / SCD 路误触发
                # (568 门因 channel_asset 派生 engine=ASC 不拦 standard 残留的 cdl_profile_id)。
                config.cdl_profile_id = None
                config.scd_id = None
                if resolved_asset.cdl_model_name:
                    config.cdl_model_name = resolved_asset.cdl_model_name
                # vendor_file authoritative: **无条件**设 emulation_file (含 None) — declared_only
                # (None) 必须清掉 saved TestCase 残留的 legacy .smu, 否则 GCM declared_only strict
                # fail-loud 被旧 stale 文件绕过 (Codex #174 复查 P2)。
                if resolved_asset.engine_mode == EngineMode.GCM_NATIVE.value:
                    config.emulation_file = resolved_asset.emulation_file

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
                "frequency_hz": config.frequency_hz,
                # 2026-07-03 现场热修 → P1-18 已正修: 驱动 Step 4 现在缺省不写 CENT
                # (保留 .smu 工程频率)。此桥接仍保留 —— TestCase 显式驱动频率是路径 B
                # 正路 (下发=配置, _center_freq_programmed 置位, 上报诚实), EMQuest
                # 运行时同时向 UXM+F64 下发频点的行为与此同构。
                # Codex #193 P2: 取归一化 PCell 频率 (与 UXM set_cell_config / 频率一致性网
                # 同源), 不取顶层 legacy frequency_hz —— CA/编辑过的计划两者可能分叉,
                # 用顶层会把 F64 写到过期载频。pcell 变量在上方 Phase 2g 已判空 fail-loud。
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
            gen_ok = await generator.generate_and_load(sim_rules, cdl_model_data)
            if not gen_ok:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=f"Channel generation failed for engine_mode={config.engine_mode}",
                )

            # --- P2-11 Phase 1: 多方频率一致性 fail-loud 校验 ---
            # UXM (set_cell_config 后, _arfcn 已设) + F64 (信道加载后) 都已配置; 把各
            # 仪表归一到 (中心 ARFCN, 带宽) 跟 TestCase 精确比对。不一致 = 静默错配
            # (GCM 模式 F64 默认 .smu 3600 但 TestCase 3500, 或 UXM 没传 arfcn → 实际
            # 下发 band fallback 基线值 ≠ 标称), strict 模式 FAIL。频率错了下面
            # input level / RSRP / 吞吐都不可信, 所以放在 Phase 2b input level 之前。
            from app.hal.nr_arfcn import FrequencyIdentity
            from app.services.mimo_ota.frequency_consistency import (
                check_frequency_consistency,
            )
            # 资产声明频率统一兜底喂一致性网 (Codex 0ea6cca P2: standard_3gpp 走 ASC 路, GCM/B2
            # 分支没设 scd_freq_identity; 补 standard 资产声明载频; GCM/B2 已设则 is None 跳过)
            if (resolved_asset is not None and resolved_asset.scd_freq_identity is not None
                    and scd_freq_identity is None):
                scd_freq_identity = resolved_asset.scd_freq_identity
            # 开关 1 inherit: UXM identity 换源 — 下发记录必 None (没下发过),
            # 改从仪器 live 读回实际 ARFCN/BW (知情继承); 读不回 (mock / 老
            # profile 无查询能力 / 查询失败) → None 走"未报告跳过"+ 显式告警,
            # 操作员知道核对没发生 (不是静默盲信)。
            if uxm_inherit:
                uxm_identity = (
                    await base_station.read_live_frequency_identity()
                    if hasattr(base_station, "read_live_frequency_identity")
                    else None
                )
                if uxm_identity is None:
                    logger.warning(
                        "[%s] 开关1 inherit: 仪器实际频率读不回 (mock/无查询"
                        "能力/失败) — UXM 频率核对未发生, 继承态未经比对",
                        context.test_execution.id,
                    )
            else:
                uxm_identity = (
                    base_station.get_frequency_identity()
                    if hasattr(base_station, "get_frequency_identity") else None
                )
            freq_result = check_frequency_consistency(
                FrequencyIdentity.from_center_freq_mhz(
                    pcell.frequency_hz / 1e6, pcell.bandwidth_mhz
                ),
                {
                    "UXM": uxm_identity,
                    "F64": emulator.get_frequency_identity()
                    if hasattr(emulator, "get_frequency_identity") else None,
                    # slice 4: SCD 声明 ARFCN 进一致性网 (scd_id 给了才非 None; None 时忽略)
                    "SCD": scd_freq_identity,
                },
            )
            if not freq_result.consistent:
                if config.precheck_strict_frequency:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "P2-11 频率一致性校验失败: "
                            + (freq_result.failure_reason() or "")
                        ),
                        measurements={"frequency_consistency": freq_result.to_payload()},
                    )
                logger.warning(
                    "[%s] P2-11 频率不一致 (precheck_strict_frequency=False, 继续): %s",
                    context.test_execution.id, freq_result.failure_reason(),
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

            # --- P2-17 (Codex #201 R3 P1): 信道加载后显式启动仿真播放 ---
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
                _bp_ok = await emulator.set_passthrough_mode(
                    mode=config.f64_bypass_mode
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
                    "[%s] 直通态测量: STATIC %s 已建立 (无衰落基线, 不 GO)",
                    context.test_execution.id, config.f64_bypass_mode,
                )
            else:
                started = await emulator.start_emulation()
                if not started:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "信道仿真启动失败 (start_emulation=False, 明细见仿真器"
                            "驱动日志) — 中止, 不在 STOPPED/直通态下测量。"
                        ),
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

            # --- P0-8 Step 2 Phase 2b: F64 输入操作点 (CE↔BS) ---
            # 开关 3 块 2: f64_input_ref_dbm 显式给定 = **手动定标** — 直接
            # set 输入参考 (+crest), 跳过 AUTOSET 闭环 (调试灵活应变: 现场
            # 已知工作点时不折腾; 07-03 实证工作点 -15/crest12)。读回反馈
            # (measure_input) 进 payload。未给定 = 现行为 AUTOSET 闭环。
            # 设计依据: docs/architecture/f64-input-level-and-dynamic-range.md §4.
            if config.f64_input_ref_dbm is not None:
                input_level_payload = await self._apply_manual_input_reference(
                    emulator=emulator,
                    config=config,
                    execution_id=context.test_execution.id,
                )
            else:
                # capability 检测 (hasattr) 跟项目 pattern 一致 — 任一方缺接口
                # (mock driver / 新 vendor 未实现) 自动跳, 不影响 mock dry-run。
                input_level_payload = await self._run_input_level_closed_loop(
                    emulator=emulator,
                    base_station=base_station,
                    config=config,
                    execution_id=context.test_execution.id,
                )
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
            window_s = max(config.stat_count / 1000.0, _MOCK_WINDOW_FLOOR_S)

            loop = asyncio.get_event_loop()
            t_start = loop.time()

            # Phase 2f / P0: pre-resolve per-azimuth probe + pattern gain +
            # per-chain path-loss so the inner sample loop doesn't hammer the
            # DB. Chain lookup uses "V" by default — current measurement
            # synthesis is also V-pol; H-pol gets the same value (acceptable
            # until per-azimuth pol switching is wired).
            nominal_probe_gain_dbi = float(chamber.probe_gain_dbi or 0.0)
            azimuth_probe_gains: Dict[float, Dict[str, Any]] = {}
            for az_target in config.azimuths_deg:
                pid = select_active_probe_id(chamber.num_probes, az_target)
                pattern_gain_v = get_probe_gain_at_azimuth(
                    context.db, chamber.num_probes, az_target, config.frequency_hz / 1e6, "V",
                    chamber_id=chamber.id,
                )
                chain_pl_db = chain_pl_by_probe_pol.get((pid, "V"))
                azimuth_probe_gains[az_target] = {
                    "probe_id": pid,
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
                await positioner.move_to(azimuth, 0.0)
                await asyncio.sleep(config.settling_time_s)

                samples_rsrp: List[float] = []
                samples_sinr: List[float] = []
                samples_tput: List[float] = []
                samples_ri: List[float] = []

                az_meta = azimuth_probe_gains.get(azimuth, {})
                gain_offset = az_meta.get("gain_offset_db")
                # P0: per-chain path-loss when available; falls back to avg.
                az_path_loss_db = az_meta.get("path_loss_db")
                if az_path_loss_db is None:
                    az_path_loss_db = avg_path_loss_db
                ce_base_rsrp = config.target_rsrp_dbm - az_path_loss_db

                for _ in range(num_windows):
                    metrics = await base_station.measure_throughput_window(window_s)

                    # RF KPIs (RSRP/SINR) are normally UE-reported; until that
                    # path exists we synthesize from target + per-probe pattern
                    # offset (Phase 2f) when available, falling back to a coarse
                    # cos(az) approximation when no pattern is loaded.
                    if gain_offset is not None:
                        rsrp = ce_base_rsrp + gain_offset + random.gauss(0, 0.3)
                        sinr = config.target_snr_db + gain_offset * 0.5 + random.gauss(0, 0.5)
                    else:
                        az_factor = math.cos(math.radians(azimuth)) * 0.1
                        rsrp = ce_base_rsrp + az_factor * 5 + random.gauss(0, 0.5)
                        sinr = config.target_snr_db + az_factor * 3 + random.gauss(0, 0.8)

                    samples_rsrp.append(rsrp)
                    samples_sinr.append(sinr)
                    samples_tput.append(metrics.dl_throughput_mbps)
                    samples_ri.append(float(metrics.rank_indicator))
                    # P1 (Codex #126): ThroughputMetrics.mcs_dl 默认 0 —— 真 UXM 不报
                    # DL_MCS 时保持 0, 不能当有效样本 (否则众数 0 < 请求 → 误判 clamp 把
                    # 整组有效测量 abort)。只收真实报告的 (>0); 0/None 都视作"未报" skip。
                    _mcs = getattr(metrics, "mcs_dl", None)
                    mcs_samples.append(_mcs if (_mcs and _mcs > 0) else None)

                az = {
                    "azimuth_deg": azimuth,
                    "rsrp_dbm": sum(samples_rsrp) / len(samples_rsrp),
                    "sinr_db": sum(samples_sinr) / len(samples_sinr),
                    "throughput_mbps": sum(samples_tput) / len(samples_tput),
                    "rank_indicator": sum(samples_ri) / len(samples_ri),
                    "num_samples": len(samples_rsrp),
                    "rsrp_std_db": stddev(samples_rsrp),
                    "sinr_std_db": stddev(samples_sinr),
                    "throughput_std_mbps": stddev(samples_tput),
                    "active_probe_id": az_meta.get("probe_id"),
                    "probe_pattern_gain_dbi": az_meta.get("pattern_gain_dbi"),
                    "path_loss_compensation_db": az_path_loss_db,
                    "path_loss_source": (
                        "rf_chain" if az_meta.get("path_loss_db") is not None else "chamber_avg"
                    ),
                }
                azimuth_results.append(az)

                logger.info(
                    "  azimuth=%.0f°: RSRP=%.1f, SINR=%.1f, Tput=%.0f Mbps, RI=%.2f",
                    azimuth,
                    az["rsrp_dbm"],
                    az["sinr_db"],
                    az["throughput_mbps"],
                    az["rank_indicator"],
                )

            total_duration = loop.time() - t_start

            # --- P2-11 Phase 6 (MCS index 线): AMC off 时实测生效 mcs_dl vs 请求 mcs ---
            # UE 撑不住请求 MCS → 静默 clamp (吞吐反映 clamp 后 MCS 却当请求 MCS 测)。是
            # throughput **实际生效回读** (区别于 layers/modulation 的 attach 后 UE
            # capability 核对)。AMC on / 无样本 → skip。strict 复用 precheck_strict_cell_config。
            from app.services.mimo_ota.cell_config_consistency import (
                check_mcs_consistency,
            )
            from app.services.instrument_hal_service import is_mock_driver
            mcs_result = check_mcs_consistency(
                requested_mcs=config.mcs,
                enable_amc=config.enable_amc,
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
                "frequency_ghz": config.frequency_hz / 1e9,
                "mimo_config": f"{config.mimo_layers}x{config.mimo_layers}",
                "azimuth_results": azimuth_results,
                "total_duration_s": total_duration,
                "engine_mode": config.engine_mode,
                "calibration_entries_used": len(calibration_entries) if calibration_entries else 0,
                "path_loss_compensation_db": avg_path_loss_db,
                "path_loss_certificate_id": (
                    str(path_loss_cert.id) if path_loss_cert is not None else None
                ),
                "path_loss_per_chain_used": chains_used,
                "path_loss_per_chain_available": len(per_chain_pl),
                # P1-12 audit (sibling QZ #79 / TRP #80): no path-loss cert →
                # avg_path_loss_db=0.0, RSRP baseline UNcompensated. The RSRP /
                # throughput numbers then aren't calibrated — flag explicitly so
                # report/GUI mark 未验证(无路损校准) rather than presenting them as
                # calibrated. (Real mode is already gated by P1-8 precheck cal
                # gate; this marks the mock/bypass path + carries provenance.)
                "path_loss_verified": path_loss_cert is not None,
                "switch_topology": topology_result.to_payload(),
                "mcs_consistency": mcs_result.to_payload(),
                "sampling": {
                    "num_windows_per_azimuth": num_windows,
                    "window_duration_s": window_s,
                    "stat_count_subframes": config.stat_count,
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
                "frequency_consistency": freq_result.to_payload(),
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
        finally:
            cleanup_warnings = await cleanup_chamber_instruments(
                hal, context.test_execution.id
            )

        if cleanup_warnings:
            result_payload["cleanup_warnings"] = cleanup_warnings

        # Surface the uncalibrated-path-loss case as a result warning (not just
        # a server-side log) so it rides into the report / operator view.
        measure_warnings: List[str] = list(cleanup_warnings or [])
        if not result_payload.get("path_loss_verified"):
            measure_warnings.insert(
                0,
                "⚠️ 路损未校准: 无 path-loss certificate, RSRP 基线未补偿 (兜底 0 dB) — "
                "RSRP / 吞吐量为非校准值。运行 CAL-01 路损校准 (P0-3) 后重测。",
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
    ) -> Dict[str, Any]:
        """跑 InputLevelController + 落遥测。返回 input_level_calibration payload。

        capability hasattr 检测 (mock CE / 未实现 atomic 的 vendor 自动跳); 跑过
        controller 后无论成败都返回结构化 payload, 上层据 success/skipped + strict
        flag 决定 phase verdict。
        """
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
        bs_supports = hasattr(base_station, "set_downlink_power")

        if not ce_supports or not bs_supports:
            reason_parts: List[str] = []
            missing_ce = [m for m, ok in ce_caps.items() if not ok]
            if missing_ce:
                reason_parts.append(f"CE 缺接口: {missing_ce}")
            if not bs_supports:
                reason_parts.append("BS 缺 set_downlink_power")
            skip_reason = (
                "; ".join(reason_parts)
                + " — 至少一方缺 capability (e.g. mock driver / 未实现 atomic 的 vendor), "
                "跳过闭环 (不影响 mock dry-run)"
            )
            logger.info(
                "[%s] Phase 2b: input-level closed loop SKIPPED — %s",
                execution_id, skip_reason,
            )
            return {"skipped": True, "reason": skip_reason}

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
                "uxm_dl_power_dbm": None,
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
                    "uxm_dl_power_dbm": None,
                    "clipping_per_mille": None,
                    "system_warnings": [],
                    "operating_point": [],
                    "active_inputs": list(_real_in),
                    "strict": bool(config.precheck_strict_input_level),
                }
            active_inputs = tuple(_real_in[:n_layers])
        else:
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
            _ctrl_kwargs["initial_uxm_dl_power_dbm"] = _initial
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
            "uxm_dl_power_dbm": il_result.uxm_dl_power_dbm,
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
                "(iter=%d, UXM=%.1f dBm, clipping=%s‰)",
                execution_id,
                il_result.iterations,
                il_result.uxm_dl_power_dbm,
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
