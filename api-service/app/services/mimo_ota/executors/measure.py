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
    # 整带宽口径优先（2026-08-07）。给了就由驱动**只走** `:DL:POWer:CHANnel`，
    # 上面那条 dBm/SCS 的 `dl_power_dbm` 在驱动里被跳过 —— 这里仍然照常放进去，
    # 是为了让 payload 保留"如果走 EPRE 口径会是多少"的审计痕迹，
    # **不是**让驱动两条都发（驱动侧是 if/elif，见 uxm_base_station 第 8 节）。
    if config.uxm_dl_power_dbm_per_bw is not None:
        cell_cfg["dl_power_dbm_per_bw"] = config.uxm_dl_power_dbm_per_bw
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
        from app.hal.scpi_evidence import EvidenceLevel, capture_scpi_exchanges
        from app.services.execution_scpi_evidence import (
            record_f64_command_capture,
            record_positioner_capture,
            record_uxm_config_capture,
            record_uxm_throughput_capture,
            register_required_scpi_evidence,
        )

        hal = get_hal_service()
        positioner = hal.drivers.get("positioner")
        base_station = hal.drivers.get("baseStation")
        if positioner is None or base_station is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="positioner + baseStation drivers required (HAL)",
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
        # UXM signaling, F64 emulating, and the turntable mid-rotation.
        cleanup_warnings: List[str] = []
        uxm_config_capture_manager = None
        uxm_config_exchanges = []
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
            pcell_arfcn = freq_mhz_to_nr_arfcn(pcell_freq_mhz)
            # 即使选择 inherit，也必须把“本次 TestCase 期望的 PCell 配置”登记为
            # mandatory。inherit 路径当前没有同事务写入/回读/APPLY 证据，因此应在
            # 正式判定中保持 missing/unknown，不能因跳过控制动作而从证据门消失。
            register_required_scpi_evidence(
                context.test_execution,
                requirement_id="uxm.pcell.config_applied",
                evidence_key="uxm.config_apply",
                requested=pcell_arfcn,
                required_evidence_level=EvidenceLevel.APPLIED,
            )
            context.db.commit()
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
                # 配置事务跨越 set_cell_config 与 start_signaling：CELL 已 ON 时
                # 走 APPLY；初始 OFF 时手册规定后续 CELL ON 自动应用。两条合法
                # recipe 必须留在同一 capture，不能依赖执行前仪器恰好为 ON。
                uxm_config_capture_manager = capture_scpi_exchanges()
                uxm_config_exchanges = uxm_config_capture_manager.__enter__()
                cell_cfg = _build_pcell_cell_config(
                    config,
                    frequency_mhz=pcell_freq_mhz,
                    arfcn=pcell_arfcn,
                    bandwidth_mhz=pcell.bandwidth_mhz,
                    scs_khz=pcell.subcarrier_spacing_khz,
                    band=pcell.band,
                )
                # Codex #195 R5 P1: set_cell_config 布尔契约必须消费 — HAL 层回读对账
                # mismatch / 下发被拒都只 return False (不裸抛), 这里不检查会带着错配
                # 小区配置进测量, 正是回读门要拦的实验污染。
                # 先落“必需项”，即使 HAL 调用随后异常/进程中断，收尾也会显示
                # missing，而不是空集合误绿。
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
            # P1-32: 返回值**必须消费**。上一版丢弃它、然后无条件 start_signaling
            # —— 于是「一条都没配上」与「全配好了」在这里长得一模一样，测试照常
            # 在**没配置过的链路**上跑完，数却当 3GPP 合规结果用。
            # 同构先例见本文件 mimo_port_preset 前置门（driver 静默不生效 →
            # 调用方 fail-loud）；memory: 路径 B 绝不用默认 fallback 静默兜底。
            if hasattr(base_station, "configure_mac_throughput_test"):
                mac_cfg = await base_station.configure_mac_throughput_test(
                    mimo_layers=config.mimo_layers,
                    mcs=config.mcs,
                    enable_amc=config.enable_amc,
                    tdd_pattern=config.tdd_pattern,
                    tdd_period=config.tdd_period,
                    harq_max_trans=config.harq_max_trans,
                    harq_processes=config.harq_processes,
                    stat_count=config.stat_count,
                    # ⭐ SCS 必须传 —— TDD pattern 的含义依赖它（手册把 SCS
                    #   列为 TDDPATtern:STATE 的 Dependencies）。不传则拒发 TDD 组。
                    scs_khz=pcell.subcarrier_spacing_khz,
                    # TestCase 的**显式** CSI-RS 端口数优先（可故意 > 层数）
                    csi_rs_ports=getattr(config, 'csi_rs_ports', None),
                )
                # ⚠ 判定收窄进 `_mac_config_blocker`（内审 F3）—— 内嵌时
                #   只能靠源码文本判，`or`→`and` 那种变异在 138 个用例下全绿。
                _blocker = self._mac_config_blocker(mac_cfg)
                if _blocker:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=_blocker,
                    )

            signaling_started = await base_station.start_signaling()
            if uxm_config_capture_manager is not None:
                uxm_config_capture_manager.__exit__(None, None, None)
                uxm_config_capture_manager = None
            if not uxm_inherit and hasattr(
                base_station, "build_p0_5_config_evidence"
            ):
                try:
                    record_uxm_config_capture(
                        context.test_execution,
                        requirement_id="uxm.pcell.config_applied",
                        requested=cell_cfg.get("arfcn"),
                        driver=base_station,
                        exchanges=uxm_config_exchanges,
                    )
                    context.db.commit()
                except Exception:  # noqa: BLE001 — 证据失败不得伪装业务失败原因
                    logger.exception(
                        "[%s] UXM P1-47C 证据归档失败；正式判定将保持 unknown",
                        context.test_execution.id,
                    )
            if not signaling_started:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "UXM start_signaling 返回 False（CELL ON/UE Attach 未确认）；"
                        "中止测量，防止读取上一轮缓存吞吐造成假绿。"
                        + (
                            # 有的 DUT 在衰落已经打开的情况下挂不上，用直通"扶一把"
                            # 就能进来。这个开关默认关着，所以失败时**由系统提示**，
                            # 不指望操作员记得它存在（2026-08-07 用户定的方向）。
                            "\n💡 若这个 DUT 在衰落下反复挂不上：把 `f64_bypass_mode` "
                            "设成 2（Butler 直通）可先用直通扶它挂上，挂上后自动撤掉"
                            "直通再开衰落测量。撤掉之后还在不在，会记进 "
                            "`attach_milestones.fading_attach`。"
                            if config.f64_bypass_mode is None else
                            "\n⚠ 本次已开直通扶持（f64_bypass_mode="
                            f"{config.f64_bypass_mode}）仍未挂上 —— 说明问题不在"
                            "「衰落太深挂不上」这一层，查 F64 输出电平与 DUT 侧。"
                        )
                    ),
                )

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
            # 三种信道管线都必须证明 F64 已加载本次模型。当前正式 recipe 只对
            # GCM 的 FILE 路径完成绑定；ASC/B2 先保留 missing/unknown，不能因
            # 分支不同而从 mandatory 集合消失后假绿。
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
            if (
                engine_mode == EngineMode.GCM_NATIVE
                and hasattr(emulator, "build_p0_5_command_evidence")
            ):
                try:
                    record_f64_command_capture(
                        context.test_execution,
                        requirement_id="f64.model_loaded",
                        evidence_key="f64.model_load",
                        requested=resolved_emulation_file,
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
                # P0-2 D6 (S5): inherit 此前只核对频率身份, 不核对小区状态。
                # 补一次真值源读取 (get_cell_state 已换 BSE:STATus:NR5G, D1)
                # 当现场证据行: OFF **不算错** (手册: OFF 态缓存的配置在
                # CELL ON 时自动应用, 后续 start_signaling 会拉起); 但读不到
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
                    "[%s] 直通态测量: STATIC %s 已建立 (无衰落基线, 不 GO)",
                    context.test_execution.id, config.f64_bypass_mode,
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
                真正的判据就在旁边、`start_signaling()` 已经在用、当天还双向验证过：
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
                #   那个 mock 分支是死分支。而 mock 的 `start_signaling()` 直接把
                #   `_cell_state = CONNECTED`，于是 mock 下里程碑会报 attached=True
                #   并一路写进 result_payload → 报告 —— 正是本 docstring 下面那句
                #   「别让 mock 跑出绿色里程碑」要防的事，那句话此前是假的。
                #   （memory: mock 回读侧必须标 simulated，且绝不进报告/KPI。）
                if is_mock_driver(base_station):
                    return {"stage": stage, "attached": None, "simulated": True,
                            "reason": "BS 是 mock 驱动 — 未测（mock 的小区状态是编的）"}
                if not hasattr(base_station, "get_cell_state"):
                    return {"stage": stage, "attached": None,
                            "reason": "BS 驱动无 get_cell_state — 未测"}
                try:
                    state = await base_station.get_cell_state()
                except Exception as e:  # noqa: BLE001
                    return {"stage": stage, "attached": False,
                            "reason": f"小区状态查询抛异常: {type(e).__name__}: {e}"}
                raw = getattr(state, "value", state)
                if state == CellState.CONNECTED:
                    return {"stage": stage, "attached": True,
                            "reason": "ok", "cell_state": raw}
                # ON = 小区开着但没 UE 连上；ERROR = 读不到/枚举外。都不算挂上。
                return {"stage": stage, "attached": False,
                        "reason": f"小区状态 {raw!r} ≠ CONN — DUT 未 attach",
                        "cell_state": raw}

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
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id=f"positioner.azimuth.{az_idx:03d}",
                    evidence_key="positioner.angle",
                    requested={"angle_deg": azimuth},
                    required_evidence_level=EvidenceLevel.APPLIED,
                )
                register_required_scpi_evidence(
                    context.test_execution,
                    requirement_id=f"uxm.throughput.azimuth.{az_idx:03d}",
                    evidence_key="uxm.dl_throughput",
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
                    moved = await positioner.move_to(azimuth, 0.0)
                if hasattr(positioner, "build_p0_5_position_evidence"):
                    try:
                        record_positioner_capture(
                            context.test_execution,
                            requirement_id=f"positioner.azimuth.{az_idx:03d}",
                            requested_angle_deg=azimuth,
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
                gain_offset = az_meta.get("gain_offset_db")
                # P0: per-chain path-loss when available; falls back to avg.
                az_path_loss_db = az_meta.get("path_loss_db")
                if az_path_loss_db is None:
                    az_path_loss_db = avg_path_loss_db
                ce_base_rsrp = config.target_rsrp_dbm - az_path_loss_db

                for _ in range(num_windows):
                    with capture_scpi_exchanges() as throughput_exchanges:
                        metrics = await base_station.measure_throughput_window(window_s)
                    latest_throughput_exchanges = throughput_exchanges

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

                if (
                    latest_throughput_exchanges
                    and hasattr(base_station, "build_p0_5_throughput_evidence")
                ):
                    try:
                        record_uxm_throughput_capture(
                            context.test_execution,
                            requirement_id=f"uxm.throughput.azimuth.{az_idx:03d}",
                            requested={
                                "azimuth_deg": azimuth,
                                "window_s": window_s,
                            },
                            driver=base_station,
                            exchanges=latest_throughput_exchanges,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[%s] UXM %.1f° E4 证据归档失败；正式判定将保持 unknown",
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
                        None if measurement_simulated
                        else sum(samples_rsrp) / len(samples_rsrp)
                    ),
                    "sinr_db": (
                        None if measurement_simulated
                        else sum(samples_sinr) / len(samples_sinr)
                    ),
                    "throughput_mbps": (
                        None if measurement_simulated
                        else sum(samples_tput) / len(samples_tput)
                    ),
                    "rank_indicator": (
                        None if measurement_simulated
                        else sum(samples_ri) / len(samples_ri)
                    ),
                    "num_samples": len(samples_rsrp),
                    "rsrp_std_db": None if measurement_simulated else stddev(samples_rsrp),
                    "sinr_std_db": None if measurement_simulated else stddev(samples_sinr),
                    "throughput_std_mbps": (
                        None if measurement_simulated else stddev(samples_tput)
                    ),
                    "measurement_source": "simulated" if measurement_simulated else "instrument",
                    "measurement_verified": not measurement_simulated,
                    "active_probe_id": az_meta.get("probe_id"),
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
            #   一个有效样本都没有时 mean=0.0，里程碑 throughput 那格如实判 False。
            _tput_samples = [
                a["throughput_mbps"] for a in azimuth_results
                if a.get("throughput_mbps") is not None
            ]
            _mean_tput_mbps = (
                sum(_tput_samples) / len(_tput_samples) if _tput_samples else 0.0
            )

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
                "measurement_source": "simulated" if measurement_simulated else "instrument",
                "measurement_verified": not measurement_simulated,
                "simulated_sources": simulated_sources,
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
                            "ok": _mean_tput_mbps > 0.0,
                            "mean_mbps": _mean_tput_mbps,
                            "azimuths_completed": len(azimuth_results),
                            "reason": (
                                "ok" if _mean_tput_mbps > 0.0 else
                                "各方位平均吞吐为 0 —— 链路通但没数据流过"
                            ),
                        }
                    ),
                },
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
            if uxm_config_capture_manager is not None:
                uxm_config_capture_manager.__exit__(None, None, None)
            cleanup_warnings = await cleanup_chamber_instruments(
                hal, context.test_execution.id
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
                "uxm_dl_power_dbm": None,
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
