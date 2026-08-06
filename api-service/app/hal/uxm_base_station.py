"""
Keysight UXM 5G Test Platform — HAL Driver (5G NR Signaling)
=============================================================

型号专用驱动，实现 BaseStationDriver 抽象接口。
基于 PyVISA 通过 HiSLIP/TCP Socket 与 UXM 通信。

SCPI 子系统参考:
  - CONFig:NR5G:<cell>:*     — 物理小区配置 (频段/带宽/SCS/ARFCN)
  - CONFig:NR5G:<cell>:<BWP>:PDSCH/PUSCH — 传输信道配置
  - CONFig:NR5G:<cell>:ACTive — 小区激活/去激活
  - CALL:*                    — 信令控制 (Attach/Detach)
  - MEASure:NR5G:<cell>:BTHRoughput — 吞吐量测量
  - MEASure:NR5G:<cell>:CSI  — CSI (CQI/RI/PMI) 测量

文档来源:
  Keysight UXM 5G NR Test Application SCPI Reference
  (5G_NR_Test_Application_SCPI_Reference.html, ~110MB)
"""

import logging
import asyncio
import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
    redact_instrument_command_text,
)
from app.hal.base_station import (
    BaseStationDriver,
    RadioTechnology,
    CellState,
    ThroughputMetrics,
)
from app.hal.nr_band_baselines import get_band_baseline
from app.hal.uxm_command_profiles import (
    UxmTestApp,
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
    detect_profile,
)

if TYPE_CHECKING:
    # P2-1 Phase 2.1: apply_topology_profile() consumes the dataclass.
    # Import only for type checking — runtime callers pass an already-
    # constructed instance, so we don't need the import at runtime.
    from app.hal.uxm_test_profiles import UxmTopologyProfile  # noqa: F401

logger = logging.getLogger(__name__)


# ── P1-33：值形态。全部取自厂商手册原件的 Range 字段，**不是编的**。
#    旧的无前缀写法发的是裸值（`4` / `16` / `"5MS"` / `"ALL"`），
#    手册要的是枚举 token（`N4` / `N16` / `MS5`）或整数 PRB 数。
_TDD_PERIOD_TOKENS = {          # Enum，默认 MS5
    "0.5MS": "MS0P5", "0.625MS": "MS0P625", "1MS": "MS1", "1.25MS": "MS1P25",
    "2MS": "MS2", "2.5MS": "MS2P5", "3MS": "MS3", "4MS": "MS4",
    "5MS": "MS5", "10MS": "MS10",
}
_HARQ_MAXTRANS_VALUES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 28)
_HARQ_PROCESSES_VALUES = (1, 2, 4, 6, 8, 10, 12, 13, 14, 16, 32)
_CSIRS_NPORTS_VALUES = (1, 2, 4, 8, 12, 16, 24, 32)
_TDD_PERIOD_MS = {
    "MS0P5": 0.5, "MS0P625": 0.625, "MS1": 1.0, "MS1P25": 1.25, "MS2": 2.0,
    "MS2P5": 2.5, "MS3": 3.0, "MS4": 4.0, "MS5": 5.0, "MS10": 10.0,
}


def _slot_ms(scs_khz):
    """NR 一个 slot 多少毫秒：15→1.0 / 30→0.5 / 60→0.25 / 120→0.125。
    对不上表的 SCS 返回 None，由调用处 fail-loud（不猜）。"""
    return {15: 1.0, 30: 0.5, 60: 0.25, 120: 0.125}.get(int(scs_khz or 0))


def _enum_token(prefix, value, allowed):
    """`4` → `N4` / `P4`；**不在手册枚举里就返回 None**（由调用处 fail-loud）。

    ⚠ 不做"就近取一个"的兜底 —— 那是静默改测试条件。
    """
    return f"{prefix}{value}" if value in allowed else None


def _tdd_slots_from_pattern(pattern):
    """`"DDDSU"` → (DL 整槽数, UL 整槽数)。

    ⚠ **数不出 S 槽里的 DL/UL 符号数** —— 那两个要显式给（手册默认 6 / 4）。
      这正是本片立项时标的前置阻塞点。
    ⚠ 只认 D/S/U 三种字符；出现别的返回 None 让调用处 fail-loud，不猜。
    """
    p = (pattern or "").strip().upper()
    if not p or set(p) - set("DSU"):
        return None
    # ⚠ 六个数只能表达 **D…D [S] U…U** 这一种排布（手册：DLSLots 从周期窗口
    #   左侧起算、ULSLots 从右侧起算）。只数个数会把 `DUS` 也放过 ——
    #   翻出来等于 `DSU`，**仪器会接受、STATE 保持 ON，于是静默跑了另一个
    #   pattern**（Codex #281 R2 P1）。所以排布不合规范式就拒。
    if not re.fullmatch(r"D*S?U*", p):
        return None
    return p.count("D"), p.count("U")


@dataclass(frozen=True)
class MacThroughputConfigResult:
    """`configure_mac_throughput_test()` 的结果 —— **不是 bool**（P1-32）。

    上一版返回 `bool` 且调用方**丢弃**它，于是「一条都没配上」与「全配好了」
    在调用点长得一模一样，测试照常在没配置过的链路上跑完。

    ⚠ `applied` 只列**真发出去**的命令 —— 同本文件 `set_cell_config` 的禁令
    「半生效配置不许报 applied」。
    """

    applied: Tuple[str, ...] = ()
    skipped: Tuple[str, ...] = ()
    missing_mandatory: Tuple[str, ...] = ()
    error: Optional[str] = None
    # P1-33：发出去了但**被仪器拒**（`SYST:ERR?` 逐组回读）。
    #   与 `skipped`（profile 没定义）是两回事：这批是"我们发了、它不认"，
    #   正是「IRAT 认不认这些手册命令」这个未知量的**实测答案**。
    rejected: Tuple[str, ...] = ()
    # P1-33：**手册里根本没有对应命令**的设置（如吞吐量统计窗口）。
    #   既不是 profile 缺项、也不是被拒 —— 单列，报告里写明不受控。
    no_equivalent: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """全部**必要**命令都发了、**没被拒**、且没出异常。

        可选命令缺席、以及手册无对应命令的设置，都不影响 `ok`。
        ⚠ `rejected` 必须计入 —— 发出去被拒跟没发是一样的后果
        （配置没生效），只是原因不同（P1-33）。
        """
        return (not self.missing_mandatory and not self.rejected
                and self.error is None)

    def __bool__(self) -> bool:
        # 兼容旧的 `if await configure(...)` 布尔用法；但调用方**应当**看
        # `missing_mandatory`（它能说出到底哪几条没下去）。
        return self.ok


# ===========================================================================
# UXM SCPI 命令映射表
# ===========================================================================
#
# Command profiles moved to app.hal.uxm_command_profiles (CAICT 2026-05-13:
# E7515B platform hosts multiple Test Apps, each with its own SCPI dialect).
# UxmScpiCommands is kept as an alias to the 5G NR Test App profile for
# backward compat with callers that import it directly.

class UxmScpiCommands(Uxm5GNRTestAppProfile):
    """UXM SCPI 命令速查表 — backward-compat alias for the 5G NR Test App profile.

    Historically a flat namespace of class attributes. Now the full attribute
    table lives in :class:`Uxm5GNRTestAppProfile` (see uxm_command_profiles).

    DEPRECATED for new code. Inside :class:`RealUxmDriver` use ``self._cmds.X``
    so the driver auto-switches to LTE_NR_IRAT's BSE: dialect when that's
    the running Test App.
    """
    # Intentionally empty body — inherits everything from Uxm5GNRTestAppProfile.
    pass


# === REMOVED: in-line command constants (now in uxm_command_profiles.py) ===
# The deleted block previously held ~80 SCPI format strings hard-coded for
# the pure 5G NR Test App. Moved verbatim to Uxm5GNRTestAppProfile so a
# parallel UxmLteNrIratProfile can ship the BSE: variants without polluting
# the driver file. See uxm_command_profiles.py.
_LEGACY_UXM_SCPI_COMMANDS_BODY_REMOVED = True


# VISA 超时常量
VISA_TIMEOUT_DEFAULT = 5000  # ms
VISA_TIMEOUT_CELL = 30000
VISA_TIMEOUT_ATTACH = 90000
VISA_TIMEOUT_STATE_LOAD = 60000  # 配置文件加载可能需要较长时间

# P1-17: UXM fresh-start 系统默认 topology profile (对齐 F64 默认 .smu =
# 3GPP_FR1_OTA_CDLC_UMa_3600M, N78 4-input, 3600 MHz)。_initialize_from_db 在
# binding 没显式选 profile 时 fallback 到它, 消除现场"快速路"(手动 PUT 选 profile)。
# 对称 F64_DEFAULT_EMULATION_FILE。操作员可经
# connection_params["default_topology_profile_id"] 覆盖。
# ⚠️ 必须跟 F64 默认 .smu 同频 (3600M) — 否则 BS 发 3600 而 CE 在另一频 = 链路打架。
# 门审 #216 F1: 2026-07-20 起指向 EMQuest 基线 profile (636666/BW40/-46) —
# 旧默认 caict_n78_3600_4x4 的 3600/640000/BW100/-50 是 .smu 文件名标称推出
# 的 stale 值 (工程真值 3549.99)。auto-apply 生效场景 (5G_NR_Test) 重载即对
# 齐基线; IRAT 被 profile 兼容门拒 apply, 重载不动 UXM 小区 (07-03 实录)。
UXM_DEFAULT_TOPOLOGY_PROFILE_ID = "caict_n78_3550_4x4_baseline"

# 默认 ARFCN 映射 (NR 频段 → ARFCN)
NR_BAND_ARFCN_MAP = {
    "N78": 632628,  # 3.5 GHz
    "N41": 499200,  # 2.5 GHz
    "N77": 620000,  # C-Band
    "N79": 693334,  # 4.7 GHz
}

# 频率 → 频段自动推断 (MHz → Band)
# 用于 set_cell_config 中当用户只给了 frequency_mhz 但没给 band 时自动映射
FREQ_TO_BAND_MAP = [
    # (min_mhz, max_mhz, band, duplex)
    (3300, 3800, "N78", "TDD"),
    (2496, 2690, "N41", "TDD"),
    (3300, 4200, "N77", "TDD"),
    (4400, 5000, "N79", "TDD"),
    (1920, 1980, "N1",  "FDD"),
    (1710, 1785, "N3",  "FDD"),
    (2110, 2170, "N1",  "FDD"),
]


def _infer_band_from_freq(
    freq_mhz: float,
    band_map: Optional[List[tuple]] = None,
) -> tuple:
    """从频率推断 NR 频段和双工模式。

    Phase 2h: band_map 由调用方(driver 实例)传入, 让跨实验室部署可以覆盖
    默认映射(在 InstrumentCategory.config["freq_to_band_map"] 配置)。
    """
    table = band_map if band_map is not None else FREQ_TO_BAND_MAP
    for row in table:
        min_f, max_f, band, duplex = row[0], row[1], row[2], row[3]
        if min_f <= freq_mhz <= max_f:
            return band, duplex
    return "N78", "TDD"  # 默认 fallback


@dataclass(frozen=True)
class AppliedCellConfig:
    """P2-11 Phase 6: UXM/UE **实际能用**的 cell config, 供 measure 跟 TestCase 请求值做
    "下发后"一致性校验 (频率一致性 Phase 1 的吞吐链延伸)。

    ⚠️ Codex on PR #114: **不能读 `CONF:...:MIMO:LAYers?`** —— 那是 set_cell_config 写入
    的同一个**配置旋钮**, 回读只会原样返回配置的 4, 抓不到 UE 把 4 层静默 clamp 到 2 的
    降级。改读 **UE 协商能力** (`query_ue_capability().max_dl_layers`): TestCase 请求的 DL
    layers 超过 UE 能力上限 → 必被 clamp → fail-loud (吞吐其实 2 层却当 4 层测)。

    None 字段 = 不可核对 (UE 未 attach / firmware 不支持 UEINFO), 校验跳过该项。

    P2-11 Phase 6 延伸: 加 ue_max_modulation_dl —— 请求调制阶数超 UE 能力同样会被静默
    clamp (TestCase 请求 256QAM 但 UE 只协商到 64QAM → 实际跑 64QAM 却当 256QAM 测),
    跟 layers 同机制 (读 UE 协商能力, 非配置旋钮回读)。调制能力上限是 UE 固有能力, 不受
    AMC 影响 (AMC 只浮动生效 MCS index, 不改 UE 的最高可协商调制)。
    """

    ue_max_dl_layers: Optional[int] = None
    ue_max_modulation_dl: Optional[str] = None


class RealUxmDriver(BaseStationDriver):
    """
    Keysight UXM 5G Test Platform 真实 SCPI 驱动 (HAL Layer 3)
    ──────────────────────────────────────────────────────────
    继承链: InstrumentDriver → BaseStationDriver → RealUxmDriver

    基于 5G NR Test Application SCPI Reference 实现。
    通过 PyVISA → HiSLIP (端口 4880) 或 TCP Socket (端口 5025) 通信。

    核心工作流:
      1. connect() → *IDN? → 选择 5G NR Test App
      2. set_cell_config() → 配置 Band/BW/SCS/ARFCN
      3. set_downlink_power() → 设置 DL 发射功率
      4. start_signaling() → Cell ON → 等待 UE Attach
      5. get_throughput_metrics() → 轮询 BLER/吞吐量/CQI
      6. stop_signaling() → Cell OFF → 断开
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        # 连接参数
        self.ip_address: str = config.get("ip", "192.168.100.10")
        self.port: int = config.get("port", 5025)
        self.protocol: str = config.get("protocol", "TCPIP")  # TCPIP or HiSLIP
        self.visa_resource: Optional[str] = config.get("visa_resource")
        # Test-App command profile (CAICT 2026-05-13: E7515B platform hosts
        # multiple test apps with different SCPI dialects). Default profile
        # is 5G NR Test App for backward compat; auto-detected in connect()
        # by reading SYSTem:APPLication:NAME? on the Test App Framework
        # endpoint. Operators can pre-set via config["uxm_profile"] = "irat"
        # to skip auto-detect when the host doesn't expose hislip0.
        # Store an *instance* of the profile (not the class itself) so any
        # future mutation of profile attrs stays scoped to this driver
        # rather than leaking to every UXM driver via class-level state.
        self._cmds: UxmTestApp = self._resolve_initial_profile(config)()
        # P2-1: Test App actually detected at connect() (via
        # SYSTem:APPLication:NAME?), as opposed to the resolved-from-
        # config initial guess. ``None`` pre-connect / when probe failed
        # — distinguishes "we don't know" from "5G_NR_Test confirmed".
        # Surfaced in readiness_metadata + written to
        # InstrumentConnection.connection_params["detected_test_app"]
        # by the HAL service post-connect for GUI audit / P3-5 readiness
        # panel.
        self.detected_test_app: Optional[str] = None
        # P1-17: fresh-start 系统默认 topology profile id。binding 没显式选
        # profile 时, HAL service _initialize_from_db 读这个 attr 做 fallback
        # (见 UXM_DEFAULT_TOPOLOGY_PROFILE_ID)。operator 经 connection_params
        # ["default_topology_profile_id"] 覆盖 (对称 F64 default_emulation_file)。
        self._default_topology_profile_id: str = config.get(
            "default_topology_profile_id", UXM_DEFAULT_TOPOLOGY_PROFILE_ID
        )
        # VISA session
        self._visa_rm = None
        self._visa_session = None
        # The final resource string that connect() landed on after any
        # Platform → hislip2 auto-redirection. Silent reconnect re-opens
        # this exact string so a half-dead session can be replaced
        # without re-deriving the endpoint (which depends on a runtime
        # *IDN? probe).
        self._active_resource_string: Optional[str] = None
        # 小区配置状态 — primary cell defaults to profile's PRIMARY_CELL
        # ("CELL0" for 5G NR Test App, "CELL1" for LTE_NR_IRAT)
        self._cell_id: str = self._cmds.PRIMARY_CELL
        self._bwp_id: str = self._cmds.PRIMARY_BWP
        self._band: str = "N78"
        self._duplex: Optional[str] = None  # P1-19: 最近一次显式/推断的双工 (TDD 跳 UL:BW 判定用)
        self._duplex_band: Optional[str] = None  # 缓存双工的归属 band — 换 band 后旧值不复用
        self._frequency_mhz: float = 3500.0
        self._bandwidth_mhz: float = 100.0
        # P2-11: 实际下发的中心 ARFCN (set_cell_config 时存)。getter 用它而非
        # _frequency_mhz 标称 → 抓 ARFCN fallback 坑 (标称 3500 但没传 arfcn 时
        # 实际下发 band 查表值, R6 起 = 基线 N78→636666=3549.99 MHz)。None=未配置。
        self._arfcn: Optional[int] = None
        self._scs_khz: int = 30
        self._dl_power_dbm: float = -50.0
        self._cell_state: CellState = CellState.OFF
        # Phase 2h: 跨实验室部署允许覆盖 freq→band 推断表 + ARFCN 映射
        # config["freq_to_band_map"] 形如 [[3300, 3800, "N78", "TDD"], ...]
        # 本地频段不在默认表里(e.g. 印度 n28, 日本 n79 局部频段)的实验室在
        # InstrumentCategory.config 里覆盖; 不传则走 module 默认。
        custom_band_map = config.get("freq_to_band_map")
        self._freq_to_band_map = (
            [tuple(row) for row in custom_band_map]
            if custom_band_map else FREQ_TO_BAND_MAP
        )
        custom_arfcn = config.get("nr_band_arfcn_map")
        # agent R6 复核 F1/F2: custom 判定与 map 赋值同一 truthiness 收敛点
        # (空 dict 不算部署声明, 否则粗值表被当 custom 压过基线) + 键大写归一
        # (3GPP 惯用小写 "n78", self._band 恒大写, 不归一则声明静默失效)
        self._nr_band_arfcn_map = (
            {str(k).upper(): v for k, v in custom_arfcn.items()}
            if custom_arfcn else NR_BAND_ARFCN_MAP
        )
        # agent R6 F3: 部署级 custom 声明要在 ARFCN fallback 里压过自动基线
        # (原实现段 5 直接查模块常量, 本旋钮从未被消费过)
        self._custom_arfcn_provided = bool(custom_arfcn)

    @staticmethod
    def _resolve_initial_profile(config: Dict[str, Any]):
        """Pick command profile before connect() runs.

        Used to set self._cmds in __init__ so PRIMARY_CELL etc are available
        immediately. connect() re-confirms via live SYSTem:APPLication:NAME?
        and overwrites if mismatch.
        """
        hint = (config.get("uxm_profile") or "").lower()
        if hint in ("irat", "lte_nr_irat", "lte+nr"):
            return UxmLteNrIratProfile
        return Uxm5GNRTestAppProfile

    def _cmd(self, name: str, **fmt) -> Optional[str]:
        """Resolve a profile command template, returning ``None`` if the
        active Test App doesn't expose it.

        Background: ``UxmLteNrIratProfile`` leaves many command templates
        as ``None`` (e.g. ``CELL_SCS``, ``MIMO_DL_LAYERS``, ``TDD_PATTERN``).

        ⚠️ **``None`` 只说明「本 profile 没定义」，不是「仪器不支持」** ——
        反过来也不能读成「仪器支持」。手册原件实查（P1-32, 2026-08-04）：
        MAC 吞吐量那 11 条标 ``Application Mode : NSA | SA``（不含 ``IRAT``），
        **但本 profile 已定义、现场在用的 ``CELL_BAND`` / ``CELL_DL_ARFCN`` /
        ``CELL_DL_BW`` 同样标 ``NSA | SA``** —— 该字段**答不了** TAP 可用性。
        且这批命令**从未被真机普查过**（``uxm_scpi_compatibility`` 的模板遍历
        跳过 ``None`` 属性）。**两个方向都没有证据 = 未经查证。**
        把"我们没写"说成"机器不支持"正是 ``uxm_manual_spelling_probe``
        要治的病；反向过冲成"机器支持"会把现场带去补错东西。补齐见 P1-33。 Driver methods that
        used to do ``self._cmds.X.format(...)`` will crash with
        ``AttributeError: 'NoneType' object has no attribute 'format'``
        when X is None.

        This helper centralises the skip-or-format decision:

        * Optional-feature branches (``if "duplex" in config: ...``) call
          ``q = self._cmd("CELL_DUPLEX", cell=cell)`` and check ``if q
          is None: continue`` to gracefully degrade.
        * Mandatory commands (``CELL_BAND``, ``CELL_DL_ARFCN``, etc.)
          should keep using ``self._cmds.X.format(...)`` directly — if
          those are ``None`` the profile is misconfigured and a loud
          crash is the right outcome.

        The skip is logged at INFO so operators see why a feature in
        their lab profile wasn't applied.
        """
        template = getattr(self._cmds, name, None)
        # ⚠ 用 falsy 判不是 `is None` —— 与同文件 `_enable_kpi_measurements`
        #   / `_warn_once_if_profile_has_no_kpi_commands` 同源（内审 F8）。
        #   profile 写成空串时 `"".format()` 返回 ""，会把 ` DDDSU` 这种
        #   残缺串真发出去、还报 ok。
        if not template:
            logger.info(
                f"[UXM/{self._cmds.PROFILE_NAME}] {name} not exposed by this "
                f"Test App; skipping (set it in the profile if your firmware "
                f"supports a vendor alias)"
            )
            return None
        out = template.format(**fmt) if fmt else template
        # ⚠ 零 fmt 时旧实现直接返回模板 —— 模板若含 `{cell}` 就把花括号
        #   **原样发到线上**，还计进 applied、报 ok（内审 F8）。
        #   跟 P1-32 刚堵上的空模板裂缝是同一条缝的另一半：视同未定义。
        if "{" in out:
            logger.info(
                f"[UXM/{self._cmds.PROFILE_NAME}] {name} 模板仍含占位符 "
                f"{out!r} —— 视同未定义，不发。")
            return None
        return out

    # ===================================================================
    # 1. 连接生命周期
    # ===================================================================

    async def connect(self) -> bool:
        """通过 PyVISA 建立与 UXM 的连接。

        E7515B 平台双 SCPI 入口：
          hislip0 → Platform 本身（只 IEEE 488.2）
          hislip2 → Test Application Framework（真测试 App SCPI 在这）

        本方法按以下顺序探测：
          1. config["visa_resource"] 给了，直接用
          2. protocol=HISLIP — 按 self._cmds.HISLIP_INDEX 决定 hislipN（默认 0；
             IRAT profile 默认 2）
          3. 否则走 SOCKET 端口 5025

        连上后 query SYSTem:APPLication:NAME? 决定实际 Test App，按结果切换
        self._cmds。若检测不到（如纯 Platform 模式），保留 __init__ 时的初值。
        """
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()

            if self.visa_resource:
                resource_str = self.visa_resource
            elif self.protocol.upper() == "HISLIP":
                hislip_idx = self._cmds.HISLIP_INDEX
                resource_str = f"TCPIP::{self.ip_address}::hislip{hislip_idx}::INSTR"
            else:
                resource_str = (
                    f"TCPIP::{self.ip_address}::{self.port}::SOCKET"
                )

            logger.info(f"[UXM] Connecting: {resource_str}")
            self._visa_session = self._visa_rm.open_resource(
                resource_str,
                timeout=VISA_TIMEOUT_DEFAULT,
            )
            # Socket 模式需要设置终止符
            if "SOCKET" in resource_str:
                self._visa_session.read_termination = "\n"
                self._visa_session.write_termination = "\n"

            # 验证身份
            idn = self._query("*IDN?").strip()

            # Two-tier auto-detection for E7515B platform (CAICT 2026-05-13):
            #
            # E7515B Platform IDN = "Keysight Technologies,E7515B Platform,..."
            # Hosts Test Applications on separate SCPI endpoints. Real test
            # commands live on hislip2 (Test App Framework), not on hislip0
            # nor on raw SOCKET 5025. If we opened a Platform endpoint and
            # the operator didn't explicitly pick a profile, auto-reconnect
            # to hislip2 to find the running Test App.
            # P1-19 ⑤ + Codex #195 P2: inst0 资源串只可能来自显式
            # config["visa_resource"] (本方法自己只构造 SOCKET/hislipN), 而
            # "显式配置不重定向"的豁免会让 inst0 分支永远不可达。语义上显式
            # 配 inst0::INSTR 不可能是"故意锁定平台" (业务树不在平台) —— 是
            # 常见误配, 照样重定向; 其余显式配置 (如 5125::SOCKET 直连 TAF)
            # 仍然尊重不动。
            # Codex #202 兜底 P2: VISA resource 大小写不敏感 (`INST0`/`SOCKET`
            # 是常见大写形式), token 检查前归一化小写 —— 否则 `TCPIP0::h::
            # INST0::INSTR` 被误判成"显式非 inst0 binding", 平台端点不重定向,
            # 后续 NR/IRAT 命令打到平台 SCPI 树 (错树)。归一化只用于**比较**,
            # redirect 提取 host / 打开 resource 仍用原始 resource_str。
            # (normalize-identifier-compare / grep-protocol-tokens-first 母题)
            _res_lc = (resource_str or "").lower()
            _visa_lc = (self.visa_resource or "").lower()
            explicit_non_inst0 = bool(self.visa_resource) and (
                "inst0" not in _visa_lc
            )
            on_platform_endpoint = (
                "E7515B Platform" in idn
                and ("socket" in _res_lc or "hislip0" in _res_lc
                     or "inst0" in _res_lc)
                and not explicit_non_inst0
            )
            if on_platform_endpoint:
                try:
                    # Codex #195 R4 P2: host 复用刚验证过 IDN 的 resource_str —
                    # 操作员可能只给 visa_resource (config 无 ip / ip=None), 此时
                    # self.ip_address 是默认值/None, 会把重定向指到别的主机。
                    _parts = resource_str.split("::")
                    _host = _parts[1] if len(_parts) > 1 else self.ip_address
                    framework_resource = f"TCPIP::{_host}::hislip2::INSTR"
                    logger.info(
                        f"[UXM] IDN says E7515B Platform; switching session "
                        f"to Test App Framework at {framework_resource}"
                    )
                    self._visa_session.close()
                    self._visa_session = self._visa_rm.open_resource(
                        framework_resource,
                        timeout=VISA_TIMEOUT_DEFAULT,
                    )
                    resource_str = framework_resource
                    idn = self._query("*IDN?").strip()
                    logger.info(f"[UXM] Framework IDN: {idn}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"[UXM] Failed to switch to hislip2 ({type(e).__name__}: "
                        f"{e}); staying on Platform endpoint — only IEEE 488.2 "
                        f"commands will work"
                    )
            # Auto-detect Test App via SYSTem:APPLication:NAME?. Only meaningful
            # if we're on the Test App Framework endpoint (else it just times
            # out — Platform doesn't expose this).
            try:
                app_name = self._query("SYSTem:APPLication:NAME?").strip().strip('"')
                if app_name:
                    # P2-1: store the RAW detected name (not the profile
                    # name we mapped it to) so audit reflects what the
                    # instrument actually reported, even when our
                    # detect_profile() registry didn't recognise it.
                    self.detected_test_app = app_name
                    detected = detect_profile(app_name)
                    if not isinstance(self._cmds, detected):
                        logger.info(
                            f"[UXM] App detected: {app_name!r} — switching "
                            f"command profile {self._cmds.PROFILE_NAME} → {detected.PROFILE_NAME}"
                        )
                        self._cmds = detected()
                        # Re-sync default cell index to new profile's
                        self._cell_id = self._cmds.PRIMARY_CELL
                        self._bwp_id = self._cmds.PRIMARY_BWP
                    else:
                        logger.info(
                            f"[UXM] App detected: {app_name!r} — profile {self._cmds.PROFILE_NAME} confirmed"
                        )
            except Exception as e:  # noqa: BLE001
                logger.info(
                    f"[UXM] SYSTem:APPLication:NAME? not available ({type(e).__name__}); "
                    f"keeping profile {self._cmds.PROFILE_NAME}"
                )
            logger.info(f"[UXM] Connected: {idn}")
            # Remember the endpoint we actually ended up on (post any
            # Platform→hislip2 redirect) for silent reconnect.
            self._active_resource_string = resource_str

            # 清除状态
            self._write("*CLS")

            # Select Test App via SCPI — only for profiles that expose
            # APP_SELECT (pure 5G NR Test App). On LTE_NR_IRAT the app
            # is GUI-launched; APP_SELECT is None so we skip.
            if self._cmds.APP_SELECT:
                self._write(self._cmds.APP_SELECT)
                self._query("*OPC?")

            self._set_status(InstrumentStatus.CONNECTED)
            self._clear_error()
            return True

        except Exception as e:
            error_msg = f"[UXM] Connection failed: {e}"
            logger.error(error_msg)
            self._set_status(InstrumentStatus.ERROR, error_msg)
            return False

    async def disconnect(self) -> bool:
        """断开 VISA 连接"""
        try:
            # P0-2 F1 (agent 门 P1): **无条件**发 stop_signaling, 不看缓存门。
            # D1 之后 _cell_state 只从状态查询解析来 — 轮询零次成功 (会话错位/
            # 未知形态) 时它停在 OFF, 旧门 `!= OFF` 会跳过 stop → 小区带着下行
            # 功率没人关。代价不对称: 对 OFF 小区多发一次 stop 是无害冗余
            # (stop_signaling 自 catch 异常), 漏发是仪器带功率没人管。
            await self.stop_signaling()

            if self._visa_session:
                self._visa_session.close()
                self._visa_session = None
            # ⚠ **不调** `self._visa_rm.close()`: RM 是**进程级共享单例**, 关它会连带
            # 关掉其它仪表的会话 (权威说明见 `app/hal/_visa_reconnect.py` 的
            # 「ResourceManager 所有权」一节)。自己的 session 上面已经关了, 这里只丢引用。
            self._visa_rm = None

            self._set_status(InstrumentStatus.DISCONNECTED)
            logger.info("[UXM] Disconnected")
            return True
        except Exception as e:
            logger.error(f"[UXM] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        """
        应用配置。

        优先使用配置文件 (state_file)，否则逐参数配置。
        """
        state_file = config.get("state_file")
        if state_file:
            return await self.load_state_file(state_file)
        return await self.set_cell_config(config)

    def readiness_metadata(self) -> Dict[str, Any]:
        """P2-1 / P3-5: expose Test App detection state to the readiness
        report so operators see which UXM app is running + which command
        profile / cell-index conventions the driver landed on.

        Distinct from the raw ``detected_test_app`` (= what the
        instrument reported via SYSTem:APPLication:NAME?): also exposes
        ``command_profile`` (the registered ``UxmTestApp``
        subclass name) so the operator can tell when our profile
        detect_profile() fell back to the 5G_NR_Test default for an
        app name we don't yet have a profile for.
        """
        return {
            "detected_test_app": self.detected_test_app,
            "command_profile": self._cmds.PROFILE_NAME,
            "primary_cell": self._cmds.PRIMARY_CELL,
            "hislip_index": self._cmds.HISLIP_INDEX,
        }

    def get_frequency_identity(self):
        """P2-11: 当前配置的频率规范标识 (中心 ARFCN + 带宽), 供多方一致性校验。

        用**实际下发的 `_arfcn`** (不是 `_frequency_mhz` 标称) —— 抓 set_cell_config
        没传 arfcn 时 band fallback 的坑 (标称 3500 但实际下发基线 636666=
        3549.99 MHz; agent R6 F3 前是 632628)。返回 None = 还没 set_cell_config。
        """
        if self._arfcn is None:
            return None
        from app.hal.nr_arfcn import FrequencyIdentity
        return FrequencyIdentity(
            center_arfcn=self._arfcn, bandwidth_mhz=self._bandwidth_mhz
        )

    async def read_live_frequency_identity(self):
        """开关 1 (uxm_config_mode=inherit) 的知情继承核对源: 从仪器**读回**
        当前实际 ARFCN + BW 构造频率标识 — 不是下发记录 (继承模式没下发,
        get_frequency_identity 必 None), 是仪器真实生效态。

        受 SUPPORTS_CONFIG_READBACK 守门 (5G_NR_Test 配置查询实证超时,
        2026-05-27); 查询失败 / 空 / 不可解析 → None (一致性网按"未报告
        跳过"处理, measure 侧对 inherit + None 另行告警)。归一化同
        _readback_verify ("BW40"→40)。
        """
        if not getattr(self._cmds, "SUPPORTS_CONFIG_READBACK", False):
            return None
        cell = self._cell_id
        try:
            arfcn_q = self._cmd("CELL_DL_ARFCN", cell=cell)
            bw_q = self._cmd("CELL_DL_BW", cell=cell)
            if arfcn_q is None or bw_q is None:
                return None
            arfcn_resp = (self._query(arfcn_q.rstrip("?") + "?") or "").strip()
            bw_resp = (self._query(bw_q.rstrip("?") + "?") or "").strip()
            bw_norm = (
                bw_resp.upper().lstrip("BW")
                if bw_resp.upper().startswith("BW") else bw_resp
            )
            if not arfcn_resp or not bw_norm:
                return None
            from app.hal.nr_arfcn import FrequencyIdentity
            return FrequencyIdentity(
                center_arfcn=int(float(arfcn_resp)),
                bandwidth_mhz=float(int(float(bw_norm))),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[UXM] read_live_frequency_identity 失败 ({type(e).__name__})"
                " — 继承模式无法核对仪器实际频率"
            )
            return None

    async def get_applied_cell_config(self) -> Optional[AppliedCellConfig]:
        """P2-11 Phase 6: 读 UXM/UE **实际能用**的 cell config, 供 measure 做下发后一致性
        校验 (吞吐链版的 get_frequency_identity)。

        当前核对 **DL MIMO layers 是否被 UE 能力 clamp**: Codex on PR #114 指出回读
        `CONF:...:LAY?` 配置旋钮只会原样返回配置值 (抓不到降级), 所以这里改读 **UE 协商
        能力** (`query_ue_capability().max_dl_layers`) —— TestCase 请求 4 层但 UE 只支持
        2 → 必被静默 clamp, 吞吐其实 2 层却当 4 层测。consistency helper 判
        `请求 > UE 上限 → fail-loud`。

        UE 未 attach / firmware 不支持 UEINFO (mock / dry-run 无真 DUT) → layers 和
        modulation 能力**都**不可用 → 返回 None (整体跳过, 同 Phase 1 mock-skip)。Codex on
        PR #124: 任一能力可用就返回对象 (per-field None semantics), 不能因 layers 缺失就丢
        掉可用的 modulation 结果 (否则 256QAM 请求在 64QAM UE 上漏检)。DL power 不核对
        (InputLevelController 闭环合法改它); 生效 MCS index 受 AMC 浮动留延伸 —— UE DL 调制
        能力上限 (ue_max_modulation_dl) 这里一并读, 它是 UE 固有能力不受 AMC 影响。
        """
        try:
            cap = await self.query_ue_capability()
        except Exception as e:  # noqa: BLE001
            logger.warning("[UXM] get_applied_cell_config: query_ue_capability 失败: %s", e)
            return None
        max_dl = cap.get("max_dl_layers")
        max_mod = cap.get("max_modulation_dl")
        # Codex on PR #124: 两个能力独立可核对 —— 只有 **都** 不可用 (UE 未 attach /
        # firmware 全不支持) 才整体 None。layers 查询失败但 modulation 成功时仍返回带
        # ue_max_modulation_dl 的对象, 否则 modulation 校验被这个 early return 静默跳过
        # (256QAM 请求在 64QAM UE 上不 fail-loud)。各字段 None → check 独立跳过该项。
        if max_dl is None and max_mod is None:
            return None
        return AppliedCellConfig(
            ue_max_dl_layers=int(max_dl) if max_dl is not None else None,
            ue_max_modulation_dl=max_mod,
        )

    # ===================================================================
    # P2-1 Phase 1: Topology Profile 应用 (operator-managed)
    # ===================================================================

    async def apply_topology_profile(
        self, profile: "UxmTopologyProfile",
    ) -> Dict[str, Any]:
        """P2-1: 把操作员预选的拓扑 profile 应用到当前运行的 Test App.

        分层语义:
        - Test App (``self._cmds.PROFILE_NAME``): UXM 实时硬件状态决定的
          SCPI 命令词汇变体 + cell index 编码。connect() 时 auto-detect.
        - Topology profile (``UxmTopologyProfile``): 操作员在 GUI 选的 cell/
          MIMO/功率/FRC 配置, 在已确定的 Test App 词汇下设置具体值。

        两层 must match: 拓扑里 ``cell_id="CELL0"`` 配 IRAT Test App
        (PRIMARY_CELL=CELL1) 会发到不存在的 cell — refuse 在这里, 而
        不是让操作员事后看 -113 报错。

        P2-1 Phase 2.1: 接受 dataclass 而非 profile_id —— driver 不再
        负责 lookup, 调用方 (HAL service / API endpoint) 从 DB 或
        code-defined registry 拿到 dataclass 再传进来. 这样 HAL 层
        完全摆脱 DB session 依赖.

        Returns:
            ``{"applied": True, "profile_id": ..., "test_app": ...}`` 成功,
            或 ``{"applied": False, "reason": "incompatible_test_app",
            "profile_id": ..., "test_app": ..., "profile_compatible_with":
            [...]}`` 拒绝, 或 ``{"applied": False, "reason":
            "cell_config_failed", ...}`` (set_cell_config 布尔契约 False —
            回读对账 mismatch / 环绕写失败等, agent R6 F1).

            刻意返回 dict 而非 raise: 调用方 (HAL init / API endpoint) 想
            根据"被拒"还是"成功"分别 surface 给操作员, raise 会丢上下文
            (test_app + profile.compatible_test_apps 都要让操作员看到).
        """
        active_test_app = self._cmds.PROFILE_NAME
        if not profile.is_compatible_with(active_test_app):
            logger.warning(
                f"[UXM] Refused to apply topology profile "
                f"{profile.profile_id!r} — declares compatibility with "
                f"{profile.compatible_test_apps}, but UXM is currently "
                f"running Test App {active_test_app!r}. Operator should "
                f"pick a compatible profile or wait until the UXM "
                f"hardware is on a matching Test App."
            )
            return {
                "applied": False,
                "reason": "incompatible_test_app",
                "profile_id": profile.profile_id,
                "test_app": active_test_app,
                "profile_compatible_with": list(profile.compatible_test_apps),
            }

        logger.info(
            f"[UXM] Applying topology profile {profile.profile_id!r} "
            f"(compat: {profile.compatible_test_apps or 'any'}) "
            f"to active Test App {active_test_app!r}"
        )
        # agent R6 F1: set_cell_config 布尔契约必须消费 (回读对账 mismatch /
        # ON→OFF 环绕写失败都以 False 报) — 半生效配置不许报 applied
        if not await self.set_cell_config(profile.to_config_dict()):
            return {
                "applied": False,
                "reason": "cell_config_failed",
                "profile_id": profile.profile_id,
                "test_app": active_test_app,
            }
        return {
            "applied": True,
            "profile_id": profile.profile_id,
            "test_app": active_test_app,
        }

    # ===================================================================
    # 2. 小区配置
    # ===================================================================

    def _format_bw_value(self, bw_mhz: float) -> str:
        """带宽值按方言编码 (P1-19): IRAT 令牌形式 "BW100" (裸数字被拒,
        2026-07-03 实证), 其余方言裸数字。"""
        if getattr(self._cmds, "BW_VALUE_FORM", "raw") == "prefixed":
            return f"BW{int(bw_mhz)}"
        return str(int(bw_mhz))

    def _readback_verify(self, cell: str, config: Dict[str, Any]) -> List[str]:
        """写后回读对账 (P1-19): 对本次下发过的 ARFCN / BW / DL 功率逐项回读比对。

        ⚠ P0-2 D3 定位: 本方法是**一层·配置回读** —— 读 `BSE:CONFig:...?`,
        只证明"命令被接受、值没被拒/钳", **不证明协议栈在用它** (R4: APPLY 前
        这些查询可能返回缓存值 → 假绿闭环)。二层·生效核对 = APPLY 后的
        `BSE:STATus:NR5G:<cell>?` + P2-11 频率一致性网, **判绿只能靠二层**。
        R4 (回读到底是缓存还是生效) 待现场用 uxm_config_truth_probe 序列验一次。

        语义: 回读异常或空响应 → 单项跳过 (方言能力不齐放行, debug 记录);
        回读成功但与下发值不一致 → 记入 mismatch (caller fail-loud)。
        BW 回读归一化 "BW100"→100; 功率浮点容差 0.1 dB。
        """
        mismatches: List[str] = []

        def _read(template_name: str) -> Optional[str]:
            q = self._cmd(template_name, cell=cell)
            if q is None:
                return None
            try:
                resp = self._query(q.rstrip("?") + "?")
                return resp.strip() if resp else None
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[UXM] 回读 {template_name} 异常跳过: {type(e).__name__}")
                return None

        if self._arfcn is not None:
            resp = _read("CELL_DL_ARFCN")
            if resp is not None:
                try:
                    if int(float(resp)) != int(self._arfcn):
                        mismatches.append(f"ARFCN 下发 {self._arfcn} 回读 {resp}")
                except ValueError:
                    mismatches.append(f"ARFCN 回读不可解析: {resp!r}")

        if "bandwidth_mhz" in config:
            resp = _read("CELL_DL_BW")
            if resp is not None:
                norm = resp.upper().lstrip("BW") if resp.upper().startswith("BW") else resp
                try:
                    if int(float(norm)) != int(config["bandwidth_mhz"]):
                        mismatches.append(
                            f"BW 下发 {int(config['bandwidth_mhz'])} 回读 {resp}")
                except ValueError:
                    mismatches.append(f"BW 回读不可解析: {resp!r}")

        if "dl_power_dbm" in config:
            resp = _read("DL_POWER")
            if resp is not None:
                try:
                    if abs(float(resp) - float(config["dl_power_dbm"])) > 0.1:
                        mismatches.append(
                            f"DL 功率下发 {config['dl_power_dbm']} 回读 {resp}")
                except ValueError:
                    mismatches.append(f"DL 功率回读不可解析: {resp!r}")

        return mismatches

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置 UXM NR5G 物理小区参数。

        完整 SCPI 序列:
          CONFig:NR5G:CELL0:BAND N78
          CONFig:NR5G:CELL0:DUPLex TDD         ← 必须在 BAND 之后设置
          CONFig:NR5G:CELL0:DL:BW 100
          CONFig:NR5G:CELL0:UL:BW 100
          CONFig:NR5G:CELL0:SCS 30
          CONFig:NR5G:CELL0:DL:ARFCN 636666
          CONFig:NR5G:CELL0:PHY:DL:MIMO:LAYers 2
          CONFig:NR5G:CELL0:PHY:DL:POWer -50
          CONFig:NR5G:CELL0:SSB:POWer -50
          *OPC?

        频段/双工自动推断:
          若 config 中只有 frequency_mhz 而没有 band/duplex，
          系统会从 FREQ_TO_BAND_MAP 自动推断对应的 NR Band 和双工模式。
          例如 3500 MHz → N78 TDD

        Args:
            config: 支持的字段:
                - band: str             NR 频段 (e.g., "N78")
                - frequency_mhz: float  中心频率 (用于自动推断 band)
                - bandwidth_mhz: float  信道带宽
                - scs_khz: int          子载波间隔 (15/30/60/120)
                - duplex: str           "TDD" / "FDD" (自动推断时可省)
                - arfcn: int            DL ARFCN (自动查表时可省)
                - mimo_layers: int      MIMO 层数 (1/2/4)
                - dl_power_dbm: float   下行发射功率
                - ssb_power_dbm: float  SSB 功率
                - cell_id: str          小区标识 (CELL0~CELL3)
                - state_file: str       配置文件路径 (一键配置)
        """
        # 一键配置文件: 如果指定了 state_file，直接 recall 并跳过后续逐参数配置
        state_file = config.get("state_file")
        if state_file:
            return await self.load_state_file(state_file)

        # P1-19 ① (2026-07-03 现场根因): "键在但值 None" 必须视同缺失 ——
        # measure 曾无条件放 band=None → 下方 .upper() 崩, 整个 set_cell_config
        # 中止且 ARFCN 未下发 (feedback_endpoint_null_field_cartesian)。copy 同时
        # 消除对 caller dict 的推断回写副作用。
        config = {k: v for k, v in config.items() if v is not None}

        cell = config.get("cell_id", self._cell_id)

        # P1-19 ② (2026-07-03 实证 -221): 小区 ACTive 时禁改带宽 —— 改 BW 前探测
        # 当前态, ON 则 OFF→配→ON 环绕 (恢复原态)。探测不可用 (profile 无命令 /
        # 查询异常) 时保持旧行为直写, 不猜。
        cell_was_on = False
        cell_restore_pending = False  # Codex #195 P1: 失败路径也必须恢复 ON

        try:
            # (Codex #195 P2: 探测与 OFF 写必须在 try 内 —— OFF 写失败也要走
            # 布尔契约 return False, 不能向 HAL caller 裸抛。)

            # 出发前 2026-07-20 (BW40 拍板配套): BW 幂等预读 —— 当前生效 BW 已
            # 等于目标值则剔除 bandwidth_mhz 键 (免 BW 写 + 免下方 OFF→配→ON
            # 环绕)。动机: measure 的 cell_cfg 必带 bandwidth_mhz, 无此检查则
            # 小区 ON 时每次 run 都环绕重启, 已 attach 的 DUT 必掉线一次;
            # 重连慢则输入电平闭环在无业务态定标 (07-03 "SSB 态 AUTOSET 钉低
            # 参考 → 满业务 clipping" 大忌)。回读失败 / 无查询模板 / 空 /
            # 不可解析 → 保守保留键走原环绕路径, 不猜。归一化与解析逻辑同
            # _readback_verify 的 BW 段 ("BW40"→40)。
            # 门审 F1 (P2): 预读同 _readback_verify 受 SUPPORTS_CONFIG_READBACK
            # 守门 —— 5G_NR_Test profile 实证配置查询超时 (2026-05-27), 不 gate
            # 会每次白等一次 timeout 且迟到应答会错位后续查询 (07-03 连锁教训)。
            # 门审 F3 (P3 保守化): 仅 TDD 才走幂等捷径 —— FDD 下剔键会连 UL:BW
            # 写一起跳过, 而预读只验了 DL (判定与下发不同源); duplex 判定不出
            # (config 无 + band 基线无) 也不走捷径, 保持原环绕。
            _preread_on = config.get(
                "readback_verify",
                getattr(self._cmds, "SUPPORTS_CONFIG_READBACK", False),
            )
            _duplex_for_preread = (
                config.get("duplex")
                or (get_band_baseline(config.get("band")) or {}).get("duplex")
                or ""
            ).upper()
            # Codex #214 P2: 捷径还须"载波身份未变" —— 同 BW 但本次调用在换
            # band/ARFCN (如 N78→N41 两资产恰同 BW) 时, 跳过环绕会让换载波写
            # 在 ON 态执行 (可能被拒), 且 UXM 换 band 可能把 BW 复位——而 BW
            # 写与对账都被剔掉, 错配置无人发现。判定用驱动上次下发记录
            # (_band/_arfcn/_frequency_mhz): config 显式 band 且与记录一致,
            # arfcn / frequency_mhz 带了也须一致; 记录冷 (None, 重载后首跑)
            # 或 config 无 band → 保守走原环绕。注: BW 本身判定用 live 预读
            # 非记录; 载波记录漂移 (外部写方改了仪器) 不受伤 —— ARFCN 写不受
            # 剔键影响照常下发 + 对账 (ms 级即发即效, 07-03 延迟矩阵)。
            _carrier_unchanged = (
                self._band is not None
                and str(config.get("band") or "").upper()
                == str(self._band).upper()
                and (
                    "arfcn" not in config
                    or (
                        self._arfcn is not None
                        and int(config["arfcn"]) == int(self._arfcn)
                    )
                )
                and (
                    "frequency_mhz" not in config
                    or (
                        self._frequency_mhz is not None
                        and float(config["frequency_mhz"])
                        == float(self._frequency_mhz)
                    )
                )
            )
            if (
                "bandwidth_mhz" in config
                and _preread_on
                and _duplex_for_preread == "TDD"
                and _carrier_unchanged
            ):
                bw_q = self._cmd("CELL_DL_BW", cell=cell)
                if bw_q is not None:
                    try:
                        resp = (self._query(bw_q.rstrip("?") + "?") or "").strip()
                        norm = (
                            resp.upper().lstrip("BW")
                            if resp.upper().startswith("BW") else resp
                        )
                        if norm and int(float(norm)) == int(config["bandwidth_mhz"]):
                            # 写分支 (段 3) 被跳过, 其缓存赋值在此补齐
                            self._bandwidth_mhz = config["bandwidth_mhz"]
                            config = {
                                k: v for k, v in config.items()
                                if k != "bandwidth_mhz"
                            }
                            logger.info(
                                f"[UXM] BW 已是 {int(self._bandwidth_mhz)} MHz"
                                " — 幂等跳过 BW 写与 OFF/ON 环绕 (DUT 不掉线)"
                            )
                    except Exception as e:  # noqa: BLE001
                        logger.debug(
                            f"[UXM] BW 幂等预读异常 ({type(e).__name__}) — "
                            "走原环绕路径"
                        )

            if "bandwidth_mhz" in config:
                state_q = self._cmd("CELL_STATE_QUERY", cell=cell)
                if state_q is not None:
                    try:
                        state_resp = (self._query(state_q) or "").strip().upper()
                        # Codex #195 复扫 P1: 5G_NR_Test 方言回文本态 (IDLE/ATT/
                        # CONN/ON/OFF, 见 get_cell_state 先例), IRAT 回 "0"/"1"。
                        # 非活动 = "0"/空/含 OFF; 其余 (含未知文本) 保守视为活动
                        # —— 漏判会 -221 配置失败, 多环绕只是多一次秒级 OFF/ON。
                        cell_was_on = not (
                            state_resp in ("0", "") or "OFF" in state_resp
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"[UXM] 小区状态探测失败 ({type(e).__name__}); 带宽按"
                            f"直写处理 — ON 态下发会被 -221 拒 (队列可见)"
                        )
                if cell_was_on:
                    logger.info(f"[UXM] {cell} ACTive → OFF (带宽改动需要, 配置后恢复)")
                    self._write(self._cmds.CELL_STATE_OFF.format(cell=cell))
                    cell_restore_pending = True

            # ---- 0. 频率 → 频段 自动推断 ----
            inferred_duplex: Optional[str] = None
            if "frequency_mhz" in config:
                self._frequency_mhz = config["frequency_mhz"]
                # 用户没显式给 band/duplex 时从频率推断 (duplex 推断值只作
                # 0b 收敛的最低优先级候选, 不直接进 config)
                if "band" not in config or "duplex" not in config:
                    inferred_band, inferred_duplex = _infer_band_from_freq(
                        self._frequency_mhz, self._freq_to_band_map
                    )
                    if "band" not in config:
                        config["band"] = inferred_band
                    logger.info(
                        f"[UXM] Auto-inferred: {self._frequency_mhz} MHz "
                        f"→ {config.get('band')}/{inferred_duplex}"
                    )

            # ---- 0b. duplex 单点收敛 (Codex #204 + #202 R4) ----
            # 优先级: 用户显式 (键在, 进门 None 已剔) > band 基线表 > 频率推断
            # fallback。**不限 frequency_mhz 分支**: band 在场 duplex 缺失/null
            # 也要补 — 否则 DUPLex 不下发, 仪器停留在上个 setup 的残留双工
            # (如 N78 的 TDD), 而段 3 判定按基线 FDD 写 UL:BW, 判定与仪器实际
            # 不同源。收敛后 DUPLex 写 / UL:BW 判定 / _duplex 缓存三处同源。
            if "duplex" not in config:
                resolved_duplex = (
                    (get_band_baseline(config.get("band")) or {}).get("duplex")
                    or inferred_duplex
                )
                if resolved_duplex:
                    config["duplex"] = resolved_duplex
                    logger.info(
                        f"[UXM] duplex 收敛: {config.get('band')} → {resolved_duplex}"
                    )

            # ---- 1. 频段 (Band) ----
            if "band" in config:
                band = config["band"].upper()
                self._band = band
                self._write(
                    self._cmds.CELL_BAND.format(cell=cell) + f" {band}"
                )

            # ---- 2. 双工模式 (必须紧跟 Band 之后) ----
            if "duplex" in config:
                duplex_mode = config["duplex"].upper()
                self._duplex = duplex_mode  # P1-19: TDD 跳 UL:BW 判定用
                self._duplex_band = self._band  # band 段已先执行, 此处即生效 band
                if (q := self._cmd("CELL_DUPLEX", cell=cell)) is not None:
                    self._write(f"{q} {duplex_mode}")
                    logger.info(f"[UXM] Duplex: {duplex_mode}")

            # ---- 3. 带宽 (DL + UL 同步设置) ----
            if "bandwidth_mhz" in config:
                bw = config["bandwidth_mhz"]
                self._bandwidth_mhz = bw
                bw_value = self._format_bw_value(bw)  # P1-19: IRAT 令牌形式 "BW100"
                self._write(
                    self._cmds.CELL_DL_BW.format(cell=cell)
                    + f" {bw_value}"
                )
                # P1-19 ③ (2026-07-03 实证): TDD 下 UL 带宽跟随 DL, 单独下发被拒;
                # 双工判定顺序 = 本次 config (源头已收敛: 用户显式或"基线表
                # 优先于推断 fallback", Codex #202 R3 + #204) > band 基线表
                # (config 无 duplex 且未走推断的路径) > 驱动状态缓存 (仅当缓存
                # 归属 band 与本次生效 band 一致)。全未知时保守写 UL:BW。
                cached_duplex = (
                    self._duplex if self._duplex_band == self._band else None
                )
                duplex_now = (
                    config.get("duplex")
                    or (get_band_baseline(config.get("band") or self._band) or {}).get("duplex")
                    or cached_duplex
                    or ""
                ).upper()
                if duplex_now == "TDD":
                    logger.info("[UXM] TDD: UL:BW 跟随 DL, 跳过单独下发")
                else:
                    self._write(
                        self._cmds.CELL_UL_BW.format(cell=cell)
                        + f" {bw_value}"
                    )

            # ---- 4. 子载波间隔 ----
            if "scs_khz" in config:
                scs = config["scs_khz"]
                self._scs_khz = scs
                if (q := self._cmd("CELL_SCS", cell=cell)) is not None:
                    self._write(f"{q} {scs}")

            # ---- 5. ARFCN (自动查表或手动指定) ----
            if "arfcn" in config:
                arfcn = config["arfcn"]
            else:
                # agent R6 F3: fallback 接 P1-19 EMQuest 基线表 — 632628 是
                # 3GPP 例值非现场基线 (N78 实证 attach 用 636666); 优先级:
                # 部署级 custom 显式声明 > 运行基线 > 4-band 粗值。基线命中
                # 时天然满足 5b 的合拍条件 → SSB 三件套自动补齐
                _bl_arfcn = (get_band_baseline(self._band) or {}).get("dl_arfcn")
                if self._custom_arfcn_provided and self._band in self._nr_band_arfcn_map:
                    arfcn = self._nr_band_arfcn_map[self._band]
                elif _bl_arfcn:
                    arfcn = int(_bl_arfcn)
                else:
                    arfcn = self._nr_band_arfcn_map.get(self._band, 632628)
                    if self._band not in self._nr_band_arfcn_map:
                        logger.warning(
                            f"[UXM] band {self._band!r} 无 ARFCN 来源 (显式/"
                            f"custom/基线/粗值表全 miss) — 退化 632628 (N78 "
                            f"例值), 大概率错频; 请显式传 arfcn"
                        )
            self._arfcn = arfcn  # P2-11: 存实际下发的中心 ARFCN (getter / 一致性校验用)
            self._write(
                self._cmds.CELL_DL_ARFCN.format(cell=cell)
                + f" {arfcn}"
            )

            # ---- 5b. SSB / PointA 频率身份 (P1-19 ④, EMQuest 基线) ----
            # 显式给 ssb_arfcn / point_a_arfcn 则下发; 都没给且目标 ARFCN 与该
            # band 的 EMQuest 运行基线一致时自动补齐 (合拍条件严格 —— 自定义
            # 频率不乱补, SSB 是 GSCN 栅格产物不能按比例平移)。profile 无命令
            # (IRAT SSB_ARFCN/CELL_DL_POINTA=None, -113 已探明) 由 _cmd 跳过。
            if "ssb_arfcn" not in config and "point_a_arfcn" not in config:
                _baseline = get_band_baseline(config.get("band") or self._band)
                if _baseline and _baseline.get("dl_arfcn") == arfcn:
                    config["ssb_arfcn"] = _baseline["ssb_arfcn"]
                    config["point_a_arfcn"] = _baseline["point_a_arfcn"]
                    logger.info(
                        f"[UXM] ARFCN {arfcn} 命中 {self._band} EMQuest 基线, "
                        f"自动补 SSB {_baseline['ssb_arfcn']} / "
                        f"PointA {_baseline['point_a_arfcn']}"
                    )
            if "ssb_arfcn" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                if (q := self._cmd("SSB_ARFCN", cell=cell, bwp=bwp)) is not None:
                    self._write(f"{q} {config['ssb_arfcn']}")
            if "point_a_arfcn" in config:
                if (q := self._cmd("CELL_DL_POINTA", cell=cell)) is not None:
                    self._write(f"{q} {config['point_a_arfcn']}")

            # ---- 6. MIMO 层数 ----
            if "mimo_layers" in config:
                layers = config["mimo_layers"]
                if (q := self._cmd("MIMO_DL_LAYERS", cell=cell)) is not None:
                    self._write(f"{q} {layers}")

            # ---- 7. MIMO 天线→物理端口路由 (Layer 1) ----
            # 支持两种方式:
            #   a) mimo_port_preset: "siso" / "2x2" / "4x4" (使用预置映射)
            #   b) mimo_port_map: 自定义映射 dict
            if "mimo_port_preset" in config:
                await self.set_mimo_port_mapping(
                    preset=config["mimo_port_preset"],
                    cell=cell,
                )
            elif "mimo_port_map" in config:
                await self.set_mimo_port_mapping(
                    custom_map=config["mimo_port_map"],
                    cell=cell,
                )

            # ---- 8. 下行功率 ----
            if "dl_power_dbm" in config:
                self._dl_power_dbm = config["dl_power_dbm"]
                if (q := self._cmd("DL_POWER", cell=cell)) is not None:
                    self._write(f"{q} {self._dl_power_dbm:.1f}")

            # ---- 9. SSB 功率 ----
            if "ssb_power_dbm" in config:
                if (q := self._cmd("SSB_POWER", cell=cell)) is not None:
                    self._write(f"{q} {config['ssb_power_dbm']:.1f}")

            # ---- 10. PDSCH RB 分配 (Full allocation 默认) ----
            if "pdsch_rb_alloc" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                if (q := self._cmd("PDSCH_RB_ALLOC", cell=cell, bwp=bwp)) is not None:
                    self._write(f"{q} {config['pdsch_rb_alloc']}")

            # ---- 11. RF 通道级端口路由 (Layer 2, 备选) ----
            if "rf_port_dl" in config:
                if (q := self._cmd("RF_PORT_DL", cell=cell)) is not None:
                    self._write(f"{q} {config['rf_port_dl']}")
            if "rf_port_ul" in config:
                if (q := self._cmd("RF_PORT_UL", cell=cell)) is not None:
                    self._write(f"{q} {config['rf_port_ul']}")

            # ---- 12-16. TDD / 调度 / AMC / HARQ / CSI-RS ----
            # ⛔ P1-33（2026-08-05）：**整段删除**。这些参数的正门是
            #    `configure_mac_throughput_test()` —— `schemas/mimo_ota/config.py`
            #    自己就写着「tdd_pattern/tdd_period 不在这里，已由
            #    configure_mac_throughput_test 驱动」。这里是**重复路径**。
            #
            #    ⚠️ 删它是因为 P1-33 差点造成一个**比原 bug 更糟**的回归：
            #    这批命令在 IRAT 上原本是 `None`（一条不发，仪器用自洽默认）；
            #    P1-33 按手册把它们补进 profile 后，**这条旧路径立刻开始用
            #    旧的裸值形态发出去**（`FULLBUFFER` / `OFF` / `5MS` / `4`），
            #    条条被拒或误配 —— 从"不发"变成"发错"。
            #    爆炸半径 Y > X，违反 CLAUDE.md ⓪① 的契约。
            #
            #    值形态转换只留在 `configure_mac_throughput_test` 一处，
            #    不在这里复制第二份（两份必然漂移）。

            # ---- 17. 统计窗口 (子帧数) ----
            if "stat_count" in config:
                if (q := self._cmd("MEAS_TPUT_STAT_COUNT", cell=cell)) is not None:
                    self._write(f"{q} {config['stat_count']}")

            # P1-19 ②: 恢复小区原 ON 态 (放 *OPC? 前 —— 小区 ON 是秒级重活,
            # OPC 正好当同步点)
            if cell_was_on:
                logger.info(f"[UXM] 配置完成, {cell} 恢复 ACTive ON")
                self._write(self._cmds.CELL_STATE_ON.format(cell=cell))
                cell_restore_pending = False

            # 同步等待 — 2026-07-21 现场实证: OFF→写参→ON 环绕后小区重启
            # 需 10s+ 量级, 默认 5s VISA 超时必炸 (*OPC? TMO → 整个
            # set_cell_config 假失败, 而参数其实已全部下发)。切 CELL 档
            # 超时等完重启, 完了恢复原值 (与 start_signaling 同法)。
            _t = self._visa_session.timeout
            self._visa_session.timeout = VISA_TIMEOUT_CELL
            try:
                self._query("*OPC?")
            finally:
                self._visa_session.timeout = _t

            # ---- P0-2 D2: ON 态直写批次收尾必须 APPLY ----
            # 手册 (General > Misc "Apply Configured Changes"): 小区 ON 时写的
            # 配置只进缓存, "most configuration changes won't be applied until
            # this command"; OFF 态写会在开小区时自动应用 (不需要发)。
            # 写入契约:
            #   OFF 态写配置 → 不发 APPLY (下次 ON 自动应用)
            #   ON  态写配置 → 批次收尾发**一次** BSE:CONFig:NR5G:APPLY
            # 判据 = 此刻开关位置 (BW 环绕路刚恢复 ON, 多发一次 APPLY 是无害
            # no-op — 挂起清单已被重开小区清掉; 换简单判据不值得为省一条命令
            # 追踪每笔写入时的开关态)。
            # ⚠ APPLY 是技术层全局动作, 刷**所有** NR 小区挂起配置 — 当前只用
            # CELL1, 上 SCell 时重审。无完成查询 (Imm Action/No query), 不跟
            # *OPC?; 生效确认 = 下面的回读对账 + 小区状态。
            apply_cmd = self._cmd("CONFIG_APPLY")
            if apply_cmd is not None and config:
                on_now = False
                switch_q = self._cmd("CELL_STATE_QUERY", cell=cell)
                if switch_q is not None:
                    try:
                        # 判据与 BW 环绕探测同源 (agent 门 F3): 未知形态**保守
                        # 视为 ON** — 漏 APPLY = R3"静默不生效"复活 (代价大),
                        # 多 APPLY 手册明示无害。IRAT 实证回裸 "0"/"1"。
                        _resp = (self._query(switch_q) or "").strip().upper()
                        on_now = not (_resp in ("0", "") or "OFF" in _resp)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"[UXM] APPLY 前开关探测失败 ({type(e).__name__}) — "
                            f"保守发 APPLY (OFF 态误发无害, 手册明示)"
                        )
                        on_now = True
                if on_now:
                    self._write(apply_cmd)
                    logger.info(
                        "[UXM] BSE:CONFig:NR5G:APPLY 已发 — ON 态直写的配置"
                        "刷进协议栈 (P0-2 D2; 此前从不发 = 静默不生效)"
                    )
                    # #236 R2 P1a: APPLY 被拒时 VISA write 照常返回, 错误只进
                    # error queue — 旧栈继续跑**旧**配置 (状态非 OFF) + 回读回显
                    # 缓存**新**值 → 状态闸和回读对账双双假绿。写后必查错误
                    # 队列 (F64R-4 同母题: 写完不查队列 = 假成功)。必须复用
                    # profile 的 ERR 命令与 P1-41 的自增殖停止判据；这里曾硬编码
                    # SYST:ERR? 并另写 5 次循环，同一故障有第二个入口。
                    _apply_errs = self._drain_errors(limit=5)
                    if _apply_errs:
                        logger.error(
                            f"[UXM] APPLY 被仪器拒绝/错误队列异常: "
                            f"{_apply_errs} — 配置未进协议栈, 判失败"
                        )
                        self._set_status(InstrumentStatus.ERROR)
                        return False

                    # D3 二层生效核对 (#236 R1 P1: 只记日志不接闸会放行现场
                    # 07-21 的原始故障形态"开关 ON 但协议栈 OFF")。
                    # #236 R2 P1b: 窗口 15s 逐秒轮询 — APPLY 重配活动小区可能
                    # 异步重启, 本方法已实证重启 10s+ 量级, 单次 1s 重试会把
                    # 合法过渡态误判失败; 首个非 OFF 枚举态即放行, 窗口内始终
                    # OFF/枚举外/读不到 → 配置没进协议栈, fail-loud
                    # (通用契约: 读不到如实报, 不当成一致)。
                    sq = self._cmd("CELL_STATUS_QUERY", cell=cell)
                    if sq is not None:
                        _status_after: Optional[str] = None
                        _parsed_after: Optional[CellState] = None
                        _waited = 0.0
                        while True:
                            try:
                                _status_after = (self._query(sq) or "").strip()
                            except Exception as e:  # noqa: BLE001
                                logger.warning(
                                    f"[UXM] APPLY 后状态读取失败 "
                                    f"({type(e).__name__})"
                                )
                                _status_after = None
                            _parsed_after = (
                                self._parse_cell_status(_status_after)
                                if _status_after is not None else None
                            )
                            if (_parsed_after is not None
                                    and _parsed_after != CellState.OFF):
                                break
                            if _waited >= 15.0:
                                break
                            await asyncio.sleep(1.0)
                            _waited += 1.0
                        if (_parsed_after is None
                                or _parsed_after == CellState.OFF):
                            logger.error(
                                f"[UXM] APPLY 后 {_waited:.0f}s 内协议栈状态"
                                f"未离开 OFF/不可读 (最后读到 "
                                f"{_status_after!r}, 开关 ON) — 配置未进"
                                f"协议栈, 判失败 (P0-2 二层生效核对; "
                                f"'ACTive=1 但 STATus OFF' 正是现场故障形态)"
                            )
                            self._set_status(InstrumentStatus.ERROR)
                            return False
                        logger.info(
                            f"[UXM] APPLY 后小区状态: {_status_after!r} ✓"
                        )

            # P1-19 ⑤: 写后回读对账 (2026-07-03 母题 "回读=echo≠生效" 的反面:
            # IRAT 上 ARFCN/BW/POWer 回读实证与面板一致, 有对账价值)。profile
            # 声明不支持 (老 App 查询超时) 或 config 显式关闭时跳过; 回读异常
            # 单项跳过 (能力不齐放行), 回读成功但不一致 → fail-loud。
            readback_on = config.get(
                "readback_verify",
                getattr(self._cmds, "SUPPORTS_CONFIG_READBACK", False),
            )
            if readback_on:
                mismatches = self._readback_verify(cell, config)
                if mismatches:
                    logger.error(
                        f"[UXM] set_cell_config 回读对账失败 (下发≠生效): "
                        f"{'; '.join(mismatches)}"
                    )
                    self._set_status(InstrumentStatus.ERROR)
                    return False

            self._set_status(InstrumentStatus.READY)

            logger.info(
                f"[UXM] Cell config applied: band={self._band}, "
                f"BW={self._bandwidth_mhz}MHz, SCS={self._scs_khz}kHz, "
                f"duplex={config.get('duplex', 'auto')}, "
                f"DL_pwr={self._dl_power_dbm}dBm"
            )
            return True

        except Exception as e:
            logger.error(f"[UXM] set_cell_config failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False
        finally:
            # Codex #195 P1: OFF 之后任何失败路径 (写异常 / 会话超时) 都不能把
            # 原本运行中的小区留在 OFF —— 活动测试会被静默打断。happy path 已
            # 恢复过 (pending 置 False), 这里只兜失败路径; 恢复本身再失败只能
            # 大声记录 (会话已死时无计可施, 操作员按日志人工恢复)。
            if cell_restore_pending:
                try:
                    logger.warning(
                        f"[UXM] set_cell_config 失败路径: 恢复 {cell} ACTive ON"
                    )
                    self._write(self._cmds.CELL_STATE_ON.format(cell=cell))
                except Exception as restore_err:  # noqa: BLE001
                    logger.error(
                        f"[UXM] ⚠ 恢复小区 ON 失败 ({type(restore_err).__name__}) "
                        f"— {cell} 可能停在 OFF, 需人工恢复!"
                    )

    # ===================================================================
    # 2.5 MIMO 天线端口路由
    # ===================================================================

    # 预置端口映射表
    # 键: (逻辑天线编号, 方向)  值: 物理端口名
    MIMO_PORT_PRESETS = {
        "siso": {
            "tx": {1: "RF1OUT"},
            "rx": {1: "RF1IN"},
            "description": "SISO 1x1: RF1 单端口",
        },
        "2x2": {
            "tx": {1: "RF1OUT", 2: "RF2OUT"},
            "rx": {1: "RF1IN",  2: "RF2IN"},
            "description": "2x2 MIMO: RF1 + RF2",
        },
        "4x4": {
            "tx": {1: "RF1OUT", 2: "RF2OUT", 3: "RF3OUT", 4: "RF4OUT"},
            "rx": {1: "RF1IN",  2: "RF2IN",  3: "RF3IN",  4: "RF4IN"},
            "description": "4x4 MIMO: RF1 + RF2 + RF3 + RF4",
        },
        # 交叉验证配置: 仅使用 RF3+RF4 (用于隔离测试)
        "2x2_alt": {
            "tx": {1: "RF3OUT", 2: "RF4OUT"},
            "rx": {1: "RF3IN",  2: "RF4IN"},
            "description": "2x2 MIMO (备用端口): RF3 + RF4",
        },
    }

    async def set_mimo_port_mapping(
        self,
        preset: Optional[str] = None,
        custom_map: Optional[Dict[str, Any]] = None,
        cell: Optional[str] = None,
    ) -> bool:
        """
        配置 MIMO 逻辑天线到 UXM 物理 RF 端口的映射。

        这是 RF 路由的 Layer 1 (天线级)，决定了每个 NR 逻辑天线
        从哪个物理端口发射/接收信号。

        UXM 前面板端口布局:
            ┌─────────────────────────────┐
            │  RF1 OUT ●  ● RF1 IN        │
            │  RF2 OUT ●  ● RF2 IN        │
            │  RF3 OUT ●  ● RF3 IN        │
            │  RF4 OUT ●  ● RF4 IN        │
            └─────────────────────────────┘

        SCPI 序列 (以 2x2 MIMO 为例):
            ROUTe:NR5G:CELL0:HARDware:TX:ANTenna1:PORT RF1OUT
            ROUTe:NR5G:CELL0:HARDware:TX:ANTenna2:PORT RF2OUT
            ROUTe:NR5G:CELL0:HARDware:RX:ANTenna1:PORT RF1IN
            ROUTe:NR5G:CELL0:HARDware:RX:ANTenna2:PORT RF2IN

        Args:
            preset: 预置映射名称 ("siso" / "2x2" / "4x4" / "2x2_alt")
            custom_map: 自定义映射字典, 格式:
                {
                    "tx": {1: "RF1OUT", 2: "RF3OUT"},
                    "rx": {1: "RF1IN",  2: "RF3IN"},
                }
            cell: 小区标识 (默认 CELL0)

        Returns:
            True if port mapping configured successfully
        """
        cell = cell or self._cell_id

        # 解析映射表
        if preset:
            preset_key = preset.lower()
            if preset_key not in self.MIMO_PORT_PRESETS:
                logger.error(
                    f"[UXM] Unknown MIMO port preset: '{preset}'. "
                    f"Available: {list(self.MIMO_PORT_PRESETS.keys())}"
                )
                return False
            mapping = self.MIMO_PORT_PRESETS[preset_key]
            tx_map = mapping["tx"]
            rx_map = mapping["rx"]
            desc = mapping["description"]
            logger.info(f"[UXM] Applying MIMO port preset: {desc}")
        elif custom_map:
            tx_map = custom_map.get("tx", {})
            rx_map = custom_map.get("rx", {})
            desc = "custom"
            logger.info(f"[UXM] Applying custom MIMO port map: TX={tx_map}, RX={rx_map}")
        else:
            logger.warning("[UXM] set_mimo_port_mapping: no preset or custom_map")
            return False

        try:
            # 配置 TX 天线端口
            for ant_num, port_name in tx_map.items():
                self._write(
                    self._cmds.MIMO_TX_ANT_PORT.format(
                        cell=cell, ant=ant_num
                    ) + f" {port_name}"
                )

            # 配置 RX 天线端口
            for ant_num, port_name in rx_map.items():
                self._write(
                    self._cmds.MIMO_RX_ANT_PORT.format(
                        cell=cell, ant=ant_num
                    ) + f" {port_name}"
                )

            self._query("*OPC?")

            logger.info(
                f"[UXM] MIMO port mapping applied ({desc}): "
                f"TX={dict(tx_map)}, RX={dict(rx_map)}"
            )
            return True

        except Exception as e:
            logger.error(f"[UXM] set_mimo_port_mapping failed: {e}")
            return False

    async def query_mimo_port_mapping(
        self, cell: Optional[str] = None
    ) -> Dict[str, Dict[int, str]]:
        """
        查询当前的 MIMO 天线端口映射。

        从 UXM 硬件回读实际配置，用于验证端口映射是否正确。

        Returns:
            {"tx": {1: "RF1OUT", 2: "RF2OUT"}, "rx": {1: "RF1IN", 2: "RF2IN"}}
        """
        cell = cell or self._cell_id
        result: Dict[str, Dict[int, str]] = {"tx": {}, "rx": {}}

        try:
            for ant_num in range(1, 5):
                # TX
                tx_port = self._query(
                    self._cmds.MIMO_TX_ANT_PORT_QUERY.format(
                        cell=cell, ant=ant_num
                    )
                ).strip()
                if tx_port and "NONE" not in tx_port.upper():
                    result["tx"][ant_num] = tx_port

                # RX
                rx_port = self._query(
                    self._cmds.MIMO_RX_ANT_PORT_QUERY.format(
                        cell=cell, ant=ant_num
                    )
                ).strip()
                if rx_port and "NONE" not in rx_port.upper():
                    result["rx"][ant_num] = rx_port

            logger.info(f"[UXM] Current port mapping: {result}")

        except Exception as e:
            logger.warning(f"[UXM] query_mimo_port_mapping: {e}")

        return result

    async def set_frc_config(
        self,
        frc_reference: str,
        modulation: Optional[str] = None,
        target_coding_rate: Optional[float] = None,
    ) -> bool:
        """
        配置 FRC (固定参考信道)。

        UXM 通过 PDSCH MCS 和 RB 分配间接配置 FRC。
        注意：此方法仅设置 MCS，不关闭 AMC。
        如需 3GPP 合规的固定 MCS 配置，请使用 configure_mac_throughput_test()。
        """
        cell = self._cell_id
        bwp = self._bwp_id
        try:
            if modulation:
                mod_map = {
                    "QPSK": 0, "16QAM": 10, "64QAM": 19,
                    "256QAM": 24, "1024QAM": 28,
                }
                mcs = mod_map.get(modulation, 24)
                self._write(
                    self._cmds.PDSCH_MCS.format(cell=cell, bwp=bwp)
                    + f" {mcs}"
                )

            self._query("*OPC?")
            logger.info(f"[UXM] FRC config: {frc_reference}")
            return True

        except Exception as e:
            logger.error(f"[UXM] set_frc_config failed: {e}")
            return False

    async def _enable_kpi_measurements(self, cell: str) -> None:
        """打开 KPI 累积 —— 吞吐量/BLER + CSI + UE 测量报告队列。

        手册 (2026-08-03 NotebookLM 查证) 三条独立前置:
          · `BTHRoughput:STATe ON` —— **全局**开关 (不带 cell), 默认 OFF;
            不开则 OTA 吞吐量与 BLER 查询恒返 9.91E+37。
          · `CSI:STARt` —— per-cell; 不发则 CQI/RI 查询恒返 NaN / 全 0。
          · `CONFig:MEASurement:REPort ON` —— UE 测量报告队列, 不开则
            L3 报告 FETCh 拿不到 RSRP/RSRQ/SINR。

        每条都**先判方言里有没有**再发 (禁盲试); 单条失败只 warning 不中断 ——
        它们互相独立, 一条挂了不该让另外两条也读不到。
        """
        for cmd_tmpl, arg, what in (
            (self._cmds.MEAS_BTHROUGHPUT_STATE, "ON", "吞吐量/BLER 累积"),
            (self._cmds.MEAS_CSI_START, None, "CSI (CQI/RI) 累积"),
            (self._cmds.MEAS_UE_REPORT_STATE, "ON", "UE 测量报告队列"),
        ):
            if not cmd_tmpl:
                logger.debug(f"[UXM] {what}: 本方言未定义该命令, 跳过")
                continue
            try:
                cmd = cmd_tmpl.format(cell=cell)
                self._write(f"{cmd} {arg}" if arg else cmd)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[UXM] 打开{what}失败: {e} — 该组 KPI 可能读不到")

    #: 本方言必须定义、否则 KPI 整组读不到的命令名
    _KPI_COMMAND_NAMES = (
        "MEAS_TPUT_DL_OTA", "MEAS_TPUT_UL_OTA",
        "MEAS_BLER_DL", "MEAS_BLER_UL",
        "MEAS_CSI_CQI", "MEAS_CSI_RI", "MEAS_UE_REPORT_JSON",
    )

    def _warn_once_if_profile_has_no_kpi_commands(self) -> None:
        """方言没定义 KPI 命令时**响亮地**说一次, 而不是静默读出一堆默认值。

        ⚠ 2026-08-03 Codex #275 P1: KPI 回读整批换命令后, 只给现场在用的
        `UxmLteNrIratProfile` 填了新命令名; `Uxm5GNRTestAppProfile`
        (connect 时按 live app 名自动选中, 没有配置兜底) 继承的是基类的
        `None` → 新 reader **逐条跳过 → 整组 KPI 读不到**。

        **不擅自给它编命令形式**(禁盲试): 手册给的两个变体都带 `BSE:` 前缀,
        5G_NR_Test 方言的无前缀形式没有手册依据, 猜一个填进去就是盲试。
        所以这里只保证**它是响的不是哑的** —— 真值待现场用
        `uxm_scpi_compatibility` 普查后按实测补。
        """
        if getattr(self, "_kpi_cmd_warned", False):
            return
        self._kpi_cmd_warned = True
        missing = [n for n in self._KPI_COMMAND_NAMES
                   if not getattr(self._cmds, n, None)]
        if not missing:
            return
        logger.warning(
            "[UXM] 方言 %s 未定义 %d/%d 条 KPI 命令 %s —— 这几组 KPI 本轮"
            "**读不到**(会填默认值并在 measurement.log 标 kpi_valid=false)。"
            "补齐前请先跑 uxm_scpi_compatibility 普查确认真机支持的形式, "
            "不要凭猜填 (禁盲试)。",
            getattr(self._cmds, "PROFILE_NAME", "?"),
            len(missing), len(self._KPI_COMMAND_NAMES), missing,
        )

    @staticmethod
    def _parse_ue_measurement_report(raw: str):
        """从 L3 RRC 测量报告 JSON 里取 (RSRP, SINR)。

        手册给的结构: {"NumberOfReportsExtracted": N, "MeasurementReports":
        [{"CellReports": [{"RSRP": .., "RSRQ": .., "SINR": .., ...}]}]}
        —— 取**最后一份**报告的**第一个** CellReport (最新的服务小区)。
        字段值可能是字符串 "NaN"; 那是没数据, 不是 0。
        返回 (None, None) 表示这一轮没读到。
        """
        import json as _json

        if not raw or not raw.strip():
            return None, None
        text = raw.strip()
        # SCPI 字符串常被整体加引号 + 内部引号双写 (手册明说会转义)
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            text = text[1:-1].replace('""', '"')
        try:
            data = _json.loads(text)
        except (ValueError, TypeError):
            return None, None
        reports = (data or {}).get("MeasurementReports") or []
        if not reports:
            return None, None
        cells = (reports[-1] or {}).get("CellReports") or []
        if not cells:
            return None, None
        cell_rep = cells[0] or {}

        def _num(key):
            v = cell_rep.get(key)
            if v is None:
                return None
            try:
                f = float(v)          # 字符串 "NaN" 会变成 float nan
            except (ValueError, TypeError):
                return None
            return None if f != f else f     # NaN → None

        return _num("RSRP"), _num("SINR")

    # ── P1-32：MAC 吞吐量配置的必要/可选分级 ────────────────────────
    #   **只此一处**。调用方只看 `missing_mandatory`，不自己维护第二份清单
    #   —— 两份清单必然漂移，那是本仓库反复踩过的坑。
    #
    #   必要 = 缺了它，测出来的**就不是那个量**：
    #     · SCHED_ALGO(Full Buffer) 没开 → 测的是打流能力
    #     · AMC 没关 / MCS 不固定     → 测的是 UXM 调度器（见本函数 docstring）
    #     · RB 不满                   → 吞吐随分配缩放
    #     · TDD 比例变                → 绝对值不可比
    #     · CSI-RS 端口不匹配         → 根本跑不到目标层数
    #   可选 = 影响精度/置信区间，**不改量纲**。
    MAC_CFG_MANDATORY: Tuple[str, ...] = (
        "PDSCH_SCHED_ALGO", "PDSCH_AMC_ENABLE", "PUSCH_AMC_ENABLE",
        "PDSCH_MCS", "PDSCH_RB_ALLOC",
        # TDD：手册没有 pattern 字符串命令，是**六个数**（P1-33）
        "TDD_PATTERN_STATE", "TDD_PERIOD",
        "TDD_DL_SLOTS", "TDD_DL_SYMBOLS", "TDD_UL_SLOTS", "TDD_UL_SYMBOLS",
        "CSIRS_PORTS",
        # 小区 ON 时不发 APPLY，上面全部只进缓存、不进协议栈（手册原文）
        "QCONFIG_APPLY_ALL", "CONFIG_APPLY",
    )
    MAC_CFG_OPTIONAL: Tuple[str, ...] = (
        "HARQ_MAX_TRANS", "HARQ_PROCESSES",
    )
    # ⛔ **已知在本仪器手册里没有对应命令**（P1-33 逐条 grep 手册原件确认）——
    #    跟"profile 忘了定义"是两回事，所以单列一档：既不假装配上了，
    #    也不当成 profile 缺项去让人补。结果里显式带出来，报告写明不受控。
    MAC_CFG_NO_EQUIVALENT: Dict[str, str] = {
        "MEAS_TPUT_STAT_COUNT":
            "吞吐量统计窗口：手册里带 `BTHRoughput:…:LENGth` 的只有 "
            "`LTE:<cell>:` / `NBIot:<cell>:` / `NR5G:SLINk:`（V2X 边链路）三种，"
            "**普通 NR 小区没有这条命令** → 统计窗口不受控，stat_count 参数无处下发。",
    }

    def _read_tdd_scs(self, cell):
        """读**仪器生效**的 TDD SCS（kHz）；读不到返回 None（不猜）。

        手册：`…:SCHeduling:TDDPATtern:SUBCarrier:SPACing`，Enum `MU0..MU3`
        —— μ 与 SCS 的关系是 15×2^μ。**TDD pattern 正是按这个 SCS 评估的**，
        所以校验要打在它上面，而不是 TestCase 的请求值（标称端）。
        """
        q = self._cmd("TDD_SCS", cell=cell)
        if not q:
            return None
        try:
            raw = str(self._query(q + "?")).strip().upper()
        except Exception as e:  # noqa: BLE001
            logger.info(f"[UXM] 读生效 TDD SCS 失败（{e}）—— 不猜")
            return None
        m = re.fullmatch(r"MU([0-4])", raw)
        if m:
            return 15 * (2 ** int(m.group(1)))
        return int(raw) if raw.isdigit() else None

    def _resolve_dl_prb_count(self, rb_alloc, cell, bwp):
        """`rb_alloc` → 手册要的**整数 PRB 数**；解析不了返回 None（不猜）。

        `"ALL"`（全带宽）时**问仪器**本 BWP 有多少 PRB —— 而不是在代码里
        敲一张 38.104 的带宽×SCS→PRB 表（那等于编数据，且会随带宽/SCS 漂）。
        ⚠ 该 `?` 形式**手册未标明可查**，所以读不到是**预期内**的一种结果，
          此时返回 None 让调用处 fail-loud，绝不退回默认值 273。
        """
        if isinstance(rb_alloc, int):
            return rb_alloc
        txt = str(rb_alloc or "").strip()
        if txt.isdigit():
            return int(txt)
        if txt.upper() != "ALL":
            return None
        q = self._cmd("PHY_DL_BWP_NUM_PRBS", cell=cell, bwp=bwp)
        if not q:
            return None
        try:
            raw = str(self._query(q + "?")).strip()
        except Exception as e:  # noqa: BLE001
            logger.info(f"[UXM] 读本 BWP 的 PRB 数失败（{e}）—— 不猜")
            return None
        return int(raw) if raw.isdigit() else None

    async def configure_mac_throughput_test(
        self,
        mimo_layers: int = 2,
        mcs: int = 28,
        rb_alloc: str = "ALL",
        enable_amc: bool = False,
        tdd_pattern: str = "DDDSU",
        tdd_period: str = "5MS",
        harq_max_trans: int = 4,
        harq_processes: int = 16,
        stat_count: int = 5000,
        cell: Optional[str] = None,
        tdd_dl_symbols: int = 6,
        tdd_ul_symbols: int = 4,
        scs_khz: Optional[int] = None,
        csi_rs_ports: Optional[int] = None,
    ) -> MacThroughputConfigResult:
        """
        配置 3GPP MIMO OTA MAC 层吞吐量测试所需的完整参数集。

        按照 3GPP TR 37.977 / CTIA OTA Test Plan 的要求，此方法:
          1. 开启 Full Buffer 调度 (PDSCH 持续占满所有时隙)
          2. 关闭 AMC (固定 MCS，结果可重复)
          3. 设置 PDSCH 全 RB 分配
          4. 配置 TDD 时隙格式 (DDDSU，最大化 DL 占比)
          5. 配置 HARQ 重传参数
          6. 设置 CSI-RS 端口数与 MIMO 层数匹配
          7. 设置统计窗口 ≥ 5000 子帧 (≥ 5s)

        为什么要关闭 AMC:
          AMC 开启时，UXM 会根据 DUT 上报的 CQI 动态降低 MCS。
          当信道衰落较重时，CQI 降低，MCS 也跟着降低，
          观测到的吞吐量下降并不代表 DUT 的 MIMO 处理能力不足，
          而只是 UXM 的保守调度策略。
          固定 MCS 后，任何吞吐量损失都来自 HARQ 重传，
          能真实反映 MIMO 空间复用的增益。

        Args:
            mimo_layers:    MIMO 层数 (1/2/4)
            mcs:            PDSCH MCS 索引 (28 = 256QAM CR≈0.93, 3GPP 最高)
            rb_alloc:       RB 分配方式 ("ALL" = 全带宽)
            enable_amc:     是否开启 AMC (3GPP 规范要求 False)
            tdd_pattern:    TDD 时隙格式 ("DDDSU" = DL heavy)
            tdd_period:     TDD 周期 ("5MS" / "2.5MS")
            harq_max_trans: HARQ 最大重传次数 (3GPP 建议 4)
            harq_processes: HARQ 并行进程数 (建议 16)
            stat_count:     统计子帧数 (3GPP 建议 ≥ 5000)
            cell:           小区 ID (默认 CELL0)

        Returns:
            `MacThroughputConfigResult` —— **不是 bool**（P1-32）。
            `applied` / `skipped` / `missing_mandatory` 三份清单；
            `ok` = 全部**必要**命令都发了且无异常。

            ⚠ 方言没定义的命令走 `self._cmd()` **graceful-skip**，不再在第一条
            `.format()` 上抛 `AttributeError`。`UxmLteNrIratProfile` 上这 11 条
            **全是 None**，上一版因此第一行就崩、`except` 吞成 `return False`，
            而调用方丢弃返回值继续跑 —— **整套 MAC 配置从未生效过**。
        """
        cell = cell or self._cell_id
        bwp = self._bwp_id
        applied: List[str] = []
        skipped: List[str] = []
        rejected: List[str] = []

        def _emit(name: str, suffix: str, **fmt) -> None:
            """发一条配置命令；方言没定义就记进 `skipped`，**不抛**。

            ⚠ Quick Config 那几条是**全局**的（模板里没有 `{cell}`/`{bwp}`），
              所以 `fmt` 按模板实际需要的键给 —— 多给会 KeyError，少给同样会。
            """
            tpl = self._cmd(name, **fmt)      # None → 已在 _cmd 里 INFO 记账
            if tpl is None:
                skipped.append(name)
                return
            self._write(tpl + suffix)
            applied.append(name)

        try:
            logger.info(
                f"[UXM] Configuring MAC throughput test: "
                f"MIMO={mimo_layers}L, MCS={mcs}, AMC={'ON' if enable_amc else 'OFF'}, "
                f"TDD={tdd_pattern}, stat_count={stat_count}"
            )

            # 0. 打开测量累积 —— **必须最先发**。
            #    ① 没有这一步, 后面所有 KPI 查询恒返 9.91E+37 (SCPI 的 NaN);
            #       手册明确: 吞吐量/BLER 由全局 BTHRoughput:STATe 控制,
            #       CSI (CQI/RI) 由 per-cell CSI:STARt 控制, UE 测量报告
            #       要先把队列开关打开。2026-08-03 之前这三条一条都没发过。
            #    ② 放在最前而不是最后, 是因为下面 1-8 步在 **IRAT 方言上
            #       11/11 条命令都是 None**。**P1-32 已把它们改成 _cmd()
            #       graceful-skip**(不再抛 AttributeError), 但跳过后 KPI 前置
            #       仍必须先发 —— 前置若排在它后面, #275 的修复就是死的。
            #       有 M10b 变异守着这个顺序, 别挪回末尾。
            await self._enable_kpi_measurements(cell)

            # ⚠ 首组之前先把队列**基线**丢掉（内审 F3）——
            #   不清的话，进函数前残留的错误（`set_cell_config` 刚跑完、
            #   或 `_enable_kpi_measurements` 自己产生的）会全记到第一组
            #   `PDSCH_SCHED_ALGO` 头上，于是本片要产出的「IRAT 认不认」
            #   实测答案，第一条就是伪证，整轮还被 FAILED 掉。
            #   同 `propsim_f64` 的既有做法：门只评估**本次写序列**的错误。
            baseline_errs = self._drain_errors()
            if baseline_errs:
                logger.info(
                    f"[UXM] 进 MAC 配置前队列有 {len(baseline_errs)} 条残留"
                    f"（**不计入本次归属**）: {baseline_errs}")
            if self._error_queue_unusable(baseline_errs):
                # 错误门本身不可判定时继续下发，只会让每组再问一轮并把
                # “门不可用”冒充成“业务命令被拒”。当前流程 fail-closed。
                raise RuntimeError(baseline_errs[-1])

            # ⚠ P1-33：值形态**全部取自手册**，跟旧的裸值写法完全不同。
            #   每组发完查一次 `SYST:ERR?`，被拒的记名 —— 这就是
            #   「IRAT 认不认这些手册命令」的实测答案，不靠推断。
            def _group(label: str) -> None:
                """一组发完，把仪器拒掉的记到**这一组**名下。"""
                errs = self._drain_errors()
                if self._error_queue_unusable(errs):
                    # 排错门本身不可用只说明归属未知，不能把当前业务组
                    # 冒充成“已被仪器拒绝”。
                    raise RuntimeError(errs[-1])
                if errs:
                    rejected.append(label)
                    logger.warning(
                        f"[UXM/{self._cmds.PROFILE_NAME}] {label} 被拒: {errs}")

            # 1. Full Buffer 调度 —— 手册枚举是 FULL_TPUT，不是 "FULLBUFFER"
            _emit("PDSCH_SCHED_ALGO", " FULL_TPUT")
            _emit("PDSCH_MCS", f" {mcs}")
            n_prb = self._resolve_dl_prb_count(rb_alloc, cell, bwp)
            if n_prb is None:
                skipped.append("PDSCH_RB_ALLOC")
                logger.error(
                    f"[UXM/{self._cmds.PROFILE_NAME}] PDSCH_RB_ALLOC 未下发 —— "
                    f"rb_alloc={rb_alloc!r} 要按全带宽发 PRB 数，但**读不到**本 BWP "
                    f"的 PRB 数。**不猜**（退回手册默认 273 会在窄带宽上超上限）。")
            else:
                _emit("PDSCH_RB_ALLOC", f" {n_prb}")
            # ⭐ Quick Config 的三条输入参数发完，要用**它自己的** apply 落地。
            #   手册：应用场景会把当前 scheduler 配置**完全抹掉并替换** ——
            #   所以必须排在下面 slot 级 AMC **之前**（内审 F2）。
            _emit("QCONFIG_APPLY_ALL", "")
            _group("QuickConfig(场景/MCS/PRB)")

            # 2. AMC —— 手册**不是开关**，是资源分配策略枚举：
            #    FIXed = 固定资源/固定 MCS（= 关 AMC），CQI = 按 CQI 自适应。
            _emit("PDSCH_AMC_ENABLE", " CQI" if enable_amc else " FIXed",
                  cell=cell, bwp=bwp)
            #    UL 侧走 `UL:IMCS:FIXed`，语义**反过来**：ON = 固定 MCS = 关 AMC。
            #    ⚠ 措辞收窄（内审 F6）：手册对**这一条**标的是
            #    `Type: Integer / Range: 0..272`，跟"收 ON/OFF"**自相矛盾**；
            #    "不设 True 则固定 IMCS 不生效"那句是**邻近块**的描述。
            #    所以 `ON` 是**按描述推断**，不是手册对该条的原文 ——
            #    现场由 `SYST:ERR?` 定案。另有对称命令 `UL:RRESource:APOLicy`
            #    未纳入（DL 走 APOLicy、UL 走 IMCS:FIXed 这个不对称已记现场待确认）。
            _emit("PUSCH_AMC_ENABLE", " OFF" if enable_amc else " ON",
                  cell=cell, bwp=bwp)
            _group("AMC")

            # 5. TDD —— 手册没有 pattern 字符串，是**六个数**
            slots = _tdd_slots_from_pattern(tdd_pattern)
            period_tok = _TDD_PERIOD_TOKENS.get(str(tdd_period).strip().upper())
            # ⭐ SCS 一致性（Codex #281 P1）—— 手册把 **Subcarrier spacing of
            #   DL and UL BW parts** 列为 `TDDPATtern:STATE` 的 Dependencies。
            #   pattern 字符串的**含义本身依赖 SCS**：`DDDSU` 是 5 个 slot，
            #   15kHz 下 = 5ms、30kHz 下 = **2.5ms**。仓库默认正是
            #   `DDDSU` + `5MS` + `scs=30` —— 30kHz 的 5ms 周期有 10 个 slot，
            #   于是变成「3 DL + 1 UL + **6 个 flexible**」：
            #   **不会被拒，但测的是另一个配置**（DL 占比远低于操作员想要的）。
            #   静默测错的量 > 显式失败，所以对不上就**不发**。
            # ⭐ SCS 必须读**生效端**（Codex #281 R2 P1）——
            #   入参 `scs_khz` 只是 TestCase 的**请求值**：IRAT 上 `CELL_SCS`
            #   未定义（`set_cell_config` 只进缓存不下发），inherit 模式更是
            #   整段跳过。仪器真在别的 SCS 上时，拿请求值算出的 slot 时长
            #   会把错的组合判成"自洽"。
            live_scs = self._read_tdd_scs(cell)
            if live_scs is None:
                eff_scs = None
                scs_note = ("读不到仪器**生效**的 TDD SCS")
            elif scs_khz is not None and int(scs_khz) != live_scs:
                eff_scs = None
                scs_note = (f"TestCase 请求 SCS={scs_khz}kHz，仪器**生效** "
                            f"SCS={live_scs}kHz —— **两方不一致**，"
                            f"不拿任一方去校验（多方一致性 fail-loud）")
            else:
                eff_scs = live_scs
                scs_note = ""
            slot_ms = _slot_ms(eff_scs)
            n_slot = len(str(tdd_pattern or "").strip())
            period_ms = _TDD_PERIOD_MS.get(period_tok or "")
            tdd_mismatch = None
            if slots is not None and period_tok is not None:
                if slot_ms is None:
                    tdd_mismatch = (f"{scs_note or f'无法识别 SCS（{eff_scs!r}）'}"
                                    f" —— pattern 的含义依赖 SCS，**不校验就不发**")
                elif abs(n_slot * slot_ms - period_ms) > 1e-9:
                    tdd_mismatch = (
                        f"pattern `{tdd_pattern}`（{n_slot} slot × {slot_ms}ms "
                        f"@ {eff_scs}kHz(生效值) = **{n_slot * slot_ms}ms**）与 period "
                        f"`{tdd_period}`（{period_ms}ms）**对不上** —— 照发不会被拒，"
                        f"但 DL/UL 比例变成另一个配置，测的不是那个量")
            if tdd_mismatch:
                for n in ("TDD_PATTERN_STATE", "TDD_PERIOD", "TDD_DL_SLOTS",
                          "TDD_DL_SYMBOLS", "TDD_UL_SLOTS", "TDD_UL_SYMBOLS"):
                    skipped.append(n)
                logger.error(f"[UXM/{self._cmds.PROFILE_NAME}] TDD 未下发 —— "
                             f"{tdd_mismatch}。")
            elif slots is None or period_tok is None:
                for n in ("TDD_PATTERN_STATE", "TDD_PERIOD", "TDD_DL_SLOTS",
                          "TDD_DL_SYMBOLS", "TDD_UL_SLOTS", "TDD_UL_SYMBOLS"):
                    skipped.append(n)
                logger.error(
                    f"[UXM/{self._cmds.PROFILE_NAME}] TDD 未下发 —— "
                    f"pattern={tdd_pattern!r}（只认 D/S/U）或 period={tdd_period!r}"
                    f"（手册枚举 {sorted(_TDD_PERIOD_TOKENS)}）无法翻成手册形态。**不猜**。")
            else:
                dl_slots, ul_slots = slots
                _emit("TDD_PERIOD", f" {period_tok}", cell=cell)
                _emit("TDD_DL_SLOTS", f" {dl_slots}", cell=cell)
                _emit("TDD_UL_SLOTS", f" {ul_slots}", cell=cell)
                # S 槽的符号数 `DDDSU` 里没有 —— 由入参给（手册默认 6 / 4）
                _emit("TDD_DL_SYMBOLS", f" {tdd_dl_symbols}", cell=cell)
                _emit("TDD_UL_SYMBOLS", f" {tdd_ul_symbols}", cell=cell)
                _emit("TDD_PATTERN_STATE", " ON", cell=cell)
                _group("TDD")
                # ⚠ 手册原文：pattern 在 enable 时才校验，**无效就不应用、
                #   state 保持 OFF** —— 也就是说它**不产生 SCPI 错误**，
                #   只是静默不生效（内审 F5）。所以必须回读，不能"写了就算配上"。
                st_q = self._cmd("TDD_PATTERN_STATE", cell=cell)
                if st_q:
                    try:
                        st = str(self._query(st_q + "?")).strip()
                    except Exception:  # noqa: BLE001
                        st = ""
                    if not st:
                        # ⚠ Codex #281 P1：读不到 ≠ 没问题。手册说无效组合
                        #   **不报错**、只体现在 STATE 上 —— 回读是**唯一**能
                        #   发现它的手段，这条手段不可用 = 等于没检查过。
                        rejected.append("TDD(STATE 回读失败，无法确认是否生效)")
                        logger.error(
                            "[UXM] TDD STATE 回读不到 —— 而回读是发现"
                            "「pattern 被静默判无效」的唯一手段，不能当没问题。")
                    elif not st.upper().startswith(("1", "ON")):
                        rejected.append("TDD(STATE 回读=%s，pattern 被判无效)" % st)
                        logger.error(
                            f"[UXM] TDD pattern 被仪器判为无效 —— 回读 STATE={st!r}。"
                            f"手册：无效组合不应用且**不报错**。"
                            f"检查 pattern({tdd_pattern}) / period({tdd_period}) / "
                            f"SCS 是否自洽。")

            # 6. HARQ —— 手册是枚举 token（N4 / N16），不是裸整数
            for name, val, allowed in (
                ("HARQ_MAX_TRANS", harq_max_trans, _HARQ_MAXTRANS_VALUES),
                ("HARQ_PROCESSES", harq_processes, _HARQ_PROCESSES_VALUES),
            ):
                tok = _enum_token("N", val, allowed)
                if tok is None:
                    skipped.append(name)
                    logger.warning(
                        f"[UXM/{self._cmds.PROFILE_NAME}] {name} 未下发 —— "
                        f"{val} 不在手册枚举 {allowed} 里。**不就近取一个**"
                        f"（那是静默改测试条件）。")
                else:
                    _emit(name, f" {tok}", cell=cell)
            _group("HARQ")

            # 7. CSI-RS 端口数 —— 手册是 P1|P2|P4|... token（1L→2, 2L→4, 4L→8）
            # ⚠ TestCase 的**显式** csi_rs_ports 优先 —— 端口数可以**故意**
            #   大于层数，按层数推会把显式 8 端口静默降成 P4
            #   （Codex #281 R2 P1：我删 set_cell_config 那段时把这个覆盖丢了）。
            csi_rs_ports = (int(csi_rs_ports) if csi_rs_ports
                            else max(2, mimo_layers * 2))
            port_tok = _enum_token("P", csi_rs_ports, _CSIRS_NPORTS_VALUES)
            if port_tok is None:
                skipped.append("CSIRS_PORTS")
                logger.warning(
                    f"[UXM/{self._cmds.PROFILE_NAME}] CSIRS_PORTS 未下发 —— "
                    f"{csi_rs_ports} 不在手册枚举 {_CSIRS_NPORTS_VALUES} 里。")
            else:
                _emit("CSIRS_PORTS", f" {port_tok}", cell=cell)
                _group("CSIRS_PORTS")

            # 8. 统计窗口 —— **手册里普通 NR 小区没有这条命令**（见类常量注释）
            no_equivalent = tuple(self.MAC_CFG_NO_EQUIVALENT)
            if no_equivalent:
                logger.info(
                    f"[UXM/{self._cmds.PROFILE_NAME}] 以下设置**手册无对应命令**，"
                    f"未下发（不是 profile 缺项）: "
                    + "; ".join(f"{k}: {v}" for k, v in
                                self.MAC_CFG_NO_EQUIVALENT.items()))

            # 9. ⭐ APPLY —— 手册：小区 ON 时不发它，上面全部只进缓存、
            #    **不进协议栈**（"This is not needed if the Cell if Off"）。
            #    调用链上游 `set_cell_config` 收尾恰好把小区恢复 ON。
            # 通用 APPLY：把小区级缓存配置推进协议栈（跟上面 Quick Config
            # 那条 apply 是**两件事**，都要发）
            _emit("CONFIG_APPLY", "")
            _group("CONFIG_APPLY")

            # 同步等待所有配置生效 —— 一条都没发出去时没必要等
            if applied:
                self._query("*OPC?")

            missing = tuple(n for n in self.MAC_CFG_MANDATORY if n in skipped)
            result = MacThroughputConfigResult(
                applied=tuple(applied), skipped=tuple(skipped),
                missing_mandatory=missing, rejected=tuple(rejected),
                no_equivalent=tuple(self.MAC_CFG_NO_EQUIVALENT),
            )
            if missing:
                # ⚠ **不静默** —— 缺任一必要命令，测出来的就不是那个量。
                #   调用方据 `missing_mandatory` 中止（memory:
                #   「路径 B 绝不用默认 fallback 静默兜底」）。
                #
                # ⚠⚠ 措辞两个方向都不许下结论：唯一的事实是**本 profile 没定义**；
                #    该 Test App 支不支持**未经查证**（详见 `_cmd` docstring）。
                logger.error(
                    f"[UXM/{self._cmds.PROFILE_NAME}] MAC throughput config "
                    f"INCOMPLETE — **本 profile 未定义** {len(missing)} 条必要"
                    f"命令: {', '.join(missing)}。已发出 {len(applied)} 条、"
                    f"跳过 {len(skipped)} 条。**此时测得的吞吐量不是 3GPP MAC 层"
                    f"吞吐量结果**（AMC/MCS/RB/TDD 未受控）。"
                    f"⚠ 该 Test App 是否支持这些命令**未经查证** —— "
                    f"出发前用 `uxm_scpi_compatibility` 普查，见 roadmap P1-33。"
                )
            else:
                # ⚠ 只说"已发出"，**不说"已生效"**（内审 F7）——
                #   手册：小区 ON 时多数配置改动要发 `BSE:CONFig:<celltype>:APPLY`
                #   才进协议栈（"This is not needed if the Cell if Off"），
                #   而本函数**不发 APPLY**、且调用链上游 `set_cell_config`
                #   收尾会把小区恢复 ON。补 APPLY 是 P1-33 的显式前置，本片不做。
                logger.info(
                    f"[UXM] MAC throughput commands sent "
                    f"(**not** confirmed applied): "
                    f"scenario=FULL_TPUT, AMC={'CQI' if enable_amc else 'FIXed'}, "
                    f"MCS={mcs}, RB={rb_alloc}, "
                    f"TDD={tdd_pattern}/{tdd_period}"
                    f"(S 槽 {tdd_dl_symbols}DL/{tdd_ul_symbols}UL), "
                    f"HARQ={harq_max_trans}x/{harq_processes}proc, "
                    f"CSI-RS={csi_rs_ports}ports；已发 {len(applied)} 条"
                    + (f"，跳过 {len(skipped)} 条: {', '.join(skipped)}"
                       if skipped else "")
                    + (f"；⚠ 手册无对应命令未发: {', '.join(self.MAC_CFG_NO_EQUIVALENT)}"
                       f"（stat_count={stat_count} 无处下发）"
                       if self.MAC_CFG_NO_EQUIVALENT else "")
                )
            return result

        except Exception as e:
            logger.error(f"[UXM] configure_mac_throughput_test failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            # 仍不裸抛（本文件既有布尔契约禁令）——但**也不谎报成功**：
            # 异常时把已发/已跳如实带回，并让 `ok` 为 False（`error` 非空即可）。
            #
            # ⚠ `missing_mandatory` 与正常路径**同源**（都从 `skipped` 派生），
            #   **不能**写成 `n not in applied`（Codex #279 P2）——
            #   那会把"还没轮到发"的命令也算成"profile 没定义"，于是 VISA
            #   中途断线时，调用方对操作员说"本 profile 未定义 N 条必要命令"、
            #   把人指向 P1-33，而真正的问题是**传输错误**。
            #   没轮到发的命令既不在 `applied` 也不在 `skipped`，
            #   它们的失败由 `error` 表达，不该冒充 profile 缺项。
            return MacThroughputConfigResult(
                applied=tuple(applied), skipped=tuple(skipped),
                missing_mandatory=tuple(
                    n for n in self.MAC_CFG_MANDATORY if n in skipped),
                rejected=tuple(rejected),
                no_equivalent=tuple(self.MAC_CFG_NO_EQUIVALENT),
                error=f"{type(e).__name__}: {e}",
            )

    async def set_downlink_power(self, power_dbm: float) -> bool:
        """
        设置 UXM 下行发射功率。

        SCPI: CONFig:NR5G:CELL0:PHY:DL:POWer <power_dbm>
        """
        try:
            self._write(
                self._cmds.DL_POWER.format(cell=self._cell_id)
                + f" {power_dbm:.1f}"
            )
            self._dl_power_dbm = power_dbm
            self._query("*OPC?")
            logger.info(f"[UXM] DL power set: {power_dbm} dBm")
            return True
        except Exception as e:
            logger.error(f"[UXM] set_downlink_power failed: {e}")
            return False

    # ===================================================================
    # 3. 信令控制
    # ===================================================================

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        """
        激活小区并等待 UE Attach。

        SCPI 序列:
          CONFig:NR5G:CELL0:ACTive:STATe ON → *OPC?
          → 轮询 Cell State 直到 UE Connected 或超时
        """
        cell = self._cell_id
        try:
            logger.info(f"[UXM] Starting signaling on {cell}")
            self._set_status(InstrumentStatus.BUSY)

            # 设置长超时用于小区激活
            old_timeout = self._visa_session.timeout
            self._visa_session.timeout = VISA_TIMEOUT_CELL

            # 激活小区。⚠ P0-2 D1: 这里**不再**写 `self._cell_state = ON` ——
            # 那是"我发了命令"的缓存断言, 不是仪器的话 (F64 `_emulation_running`
            # 同款毛病)。状态只从下面的轮询解析来。
            self._write(self._cmds.CELL_STATE_ON.format(cell=cell))
            self._query("*OPC?")

            # 恢复超时并等待 UE Attach
            self._visa_session.timeout = VISA_TIMEOUT_ATTACH

            # P0-2 R1 正修: 轮询**小区状态** (BSE:STATus:NR5G:<cell>?, 手册枚举
            # OFF|ON|CONNected|IDLE|AGGRegated|ACTivated), 不是 ACTive:STATe?
            # 开关回读 —— 后者在 IRAT 上回 "0"/"1", 旧判据 `"CONN" in "1"`
            # 任何情况都不可能成立, attach 永远只能跑满超时。
            # 5G_NR_Test 方言无 STATUS 命令 (手册查不到) → fallback 旧文本查询
            # (旧注释宣称回 IDLE/ATT/CONN 文本 — 出处不可考待现场核, 白名单收
            #  其长短双形; 枚举外不判, 超时带字面值)。
            status_q = self._cmd("CELL_STATUS_QUERY", cell=cell)
            poll_q = status_q or self._cmds.CELL_STATE_QUERY.format(cell=cell)
            if status_q is None:
                logger.info(
                    "[UXM] 本方言无 CELL_STATUS_QUERY — attach 轮询 fallback "
                    "旧文本状态查询 (仅 5G_NR_Test 实证形态)"
                )

            attached = False
            last_raw = "<未读到>"
            elapsed = 0.0
            poll_interval = 2.0
            while elapsed < timeout_s:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                last_raw = (self._query(poll_q) or "").strip()
                parsed = self._parse_cell_status(last_raw)
                if parsed is None:
                    # 白名单外 (含 IRAT 开关回读误接线时的 "0"/"1") — 不猜,
                    # 记录后继续轮询; 超时报错会带上这个字面值。
                    logger.warning(
                        f"[UXM] 小区状态回复不在手册枚举内: {last_raw!r} — 不判定"
                    )
                    continue
                self._cell_state = parsed
                if parsed == CellState.CONNECTED:
                    attached = True
                    logger.info(f"[UXM] UE attached after {elapsed:.1f}s")
                    break

            # 恢复默认超时
            self._visa_session.timeout = old_timeout

            if attached:
                return True
            # 如实报失败, 带上最后读到的字面值 —— 下次现场排查靠它区分
            # "真没连上" vs "查询/解析不对" (P0-2 验收项)。
            logger.warning(
                f"[UXM] UE attach timeout after {timeout_s}s — "
                f"最后一次状态回复: {last_raw!r} (查询: {poll_q})"
            )
            return False

        except Exception as e:
            logger.error(f"[UXM] start_signaling failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def stop_signaling(self) -> bool:
        """关闭小区信令"""
        try:
            self._write(
                self._cmds.CELL_STATE_OFF.format(cell=self._cell_id)
            )
            self._query("*OPC?")
            self._cell_state = CellState.OFF
            self._set_status(InstrumentStatus.READY)
            logger.info("[UXM] Signaling stopped")
            return True
        except Exception as e:
            logger.error(f"[UXM] stop_signaling failed: {e}")
            return False

    # P0-2 D1: 手册枚举白名单 (照搬 F64R-1 七态白名单的打法 — 它当时正是靠
    # 白名单挡住了会话错位读回的噪声)。**精确 token 匹配**, 不做子串包含 ——
    # 旧代码 `"CONN" in state` 在 IRAT 的 "0"/"1" 回读上永假, 而 `"ON" in
    # "CONNECTED"` 这类子串误中则会反向骗绿。长短形态都收 (SCPI 惯例)。
    _CELL_STATUS_TOKENS = {
        "OFF": CellState.OFF,
        "ON": CellState.IDLE,           # 小区已起, 无 UE — 映射现有 IDLE 语义
        "IDLE": CellState.IDLE,
        "CONN": CellState.CONNECTED,
        "CONNECTED": CellState.CONNECTED,
        # ATT/ATTACHED: 旧代码注释宣称 5G_NR_Test 回此形态 (出处不可考, 无真机
        # 记录 — 2026-05 现场那台是 IRAT), 长短双形都收, 待现场核 (agent 门 F5)
        "ATT": CellState.CONNECTED,
        "ATTACHED": CellState.CONNECTED,
        "AGGR": CellState.CONNECTED,    # AGGRegated: CA 聚合态 (UE 已连)
        "AGGREGATED": CellState.CONNECTED,
        "ACT": CellState.CONNECTED,     # ACTivated: SCell 激活态 (UE 已连)
        "ACTIVATED": CellState.CONNECTED,
    }

    def _parse_cell_status(self, raw: str) -> Optional[CellState]:
        """手册枚举 → CellState; 枚举外返回 None (不猜)。"""
        token = (raw or "").strip().strip('"').upper()
        return self._CELL_STATUS_TOKENS.get(token)

    async def get_cell_state(self) -> CellState:
        """查询小区当前状态 (P0-2 D1: 问协议栈真实状态, 不问开关回读)。"""
        try:
            q = self._cmd("CELL_STATUS_QUERY", cell=self._cell_id)
            if q is None:
                # 5G_NR_Test fallback: 旧文本查询 (实证回 IDLE/ATT/CONN/ON/OFF)
                q = self._cmds.CELL_STATE_QUERY.format(cell=self._cell_id)
            raw = (self._query(q) or "").strip()
            parsed = self._parse_cell_status(raw)
            if parsed is None:
                # 枚举外 (含误接开关回读的 "0"/"1") → 如实报"读不到", 不猜。
                logger.warning(
                    f"[UXM] get_cell_state: 回复不在手册枚举内: {raw!r} (查询: {q})"
                )
                return CellState.ERROR
            self._cell_state = parsed
            return parsed
        except Exception:
            return CellState.ERROR

    # ===================================================================
    # 3.5 配置文件保存/恢复 (一键配置)
    # ===================================================================

    async def load_state_file(self, filepath: str) -> bool:
        """
        从 UXM 本机加载保存的配置文件，一次性恢复全部仪器状态。

        使用场景:
          - 工程师在 UXM 前面板手动调好所有参数后，执行 save_state_file()
            保存为 .state 文件
          - 后续自动化测试时只需 load_state_file() 即可一键恢复
          - 消除逐条 SCPI 配置的潜在顺序依赖和参数遗漏风险

        UXM 配置文件包含:
          - NR5G 小区所有参数 (Band/BW/SCS/ARFCN/MIMO/Power)
          - RF 路由设置 (DL/UL 端口映射)
          - TDD 时隙配置
          - PDSCH/PUSCH 参数
          - 测量配置

        Args:
            filepath: UXM 本机的文件路径
                例: "D:\\User Files\\CAICT_N78_100M_2x2.state"

        Returns:
            True if state loaded successfully
        """
        try:
            logger.info(f"[UXM] Loading state file: {filepath}")
            self._set_status(InstrumentStatus.BUSY)

            # 加载前先安全关闭小区 — P0-2 F1: 无条件, 不看缓存门 (同 disconnect:
            # 缓存 OFF 可能是"读不到"而非真 OFF, 漏关比多关贵)。
            await self.stop_signaling()

            # 设置长超时（配置文件包含大量参数，加载需要时间）
            old_timeout = self._visa_session.timeout
            self._visa_session.timeout = VISA_TIMEOUT_STATE_LOAD

            self._write(
                self._cmds.STATE_LOAD.format(filepath=filepath)
            )
            self._query("*OPC?")

            self._visa_session.timeout = old_timeout

            # 加载后刷新内部状态缓存
            await self._refresh_config_from_instrument()

            self._set_status(InstrumentStatus.READY)
            logger.info(
                f"[UXM] State loaded: {filepath} → "
                f"band={self._band}, BW={self._bandwidth_mhz}MHz"
            )
            return True

        except Exception as e:
            logger.error(f"[UXM] load_state_file failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def save_state_file(self, filepath: str) -> bool:
        """
        将 UXM 当前完整配置保存为 .state 文件。

        用途:
          - 工程师手动调优完成后保存为模板
          - 团队间共享标准化测试配置
          - 回归测试的可重复性保证

        Args:
            filepath: UXM 本机的保存路径
                例: "D:\\User Files\\CAICT_N78_100M_2x2.state"

        Returns:
            True if state saved successfully
        """
        try:
            logger.info(f"[UXM] Saving state: {filepath}")
            self._write(
                self._cmds.STATE_SAVE.format(filepath=filepath)
            )
            self._query("*OPC?")
            logger.info(f"[UXM] State saved: {filepath}")
            return True

        except Exception as e:
            logger.error(f"[UXM] save_state_file failed: {e}")
            return False

    async def list_state_files(self) -> List[str]:
        """
        列出 UXM 本机上已保存的配置文件。

        Returns:
            文件名列表
        """
        try:
            result = self._query(self._cmds.STATE_LIST)
            # 解析 MMEMory:CATalog? 返回格式
            # 典型: '"file1.state","file2.state",...'
            files = []
            if result:
                parts = result.replace('"', '').split(',')
                files = [
                    p.strip() for p in parts
                    if p.strip().endswith('.state')
                ]
            return files
        except Exception as e:
            logger.warning(f"[UXM] list_state_files failed: {e}")
            return []

    async def _refresh_config_from_instrument(self) -> None:
        """
        从 UXM 硬件回读当前配置，刷新驱动内部缓存。

        在 load_state_file() 后调用，确保驱动状态与硬件一致。
        """
        cell = self._cell_id
        try:
            # 回读频段
            band = self._query(
                self._cmds.CELL_BAND.format(cell=cell) + "?"
            ).strip()
            if band:
                self._band = band.upper()

            # 回读带宽
            bw = self._query(
                self._cmds.CELL_DL_BW.format(cell=cell) + "?"
            ).strip()
            if bw:
                self._bandwidth_mhz = float(bw)

            # 回读 SCS
            scs = self._query(
                self._cmds.CELL_SCS.format(cell=cell) + "?"
            ).strip()
            if scs:
                self._scs_khz = int(float(scs))

            # 回读功率
            pwr = self._query(
                self._cmds.DL_POWER.format(cell=cell) + "?"
            ).strip()
            if pwr:
                self._dl_power_dbm = float(pwr)

            # 回读小区状态
            self._cell_state = await self.get_cell_state()

        except Exception as e:
            logger.warning(f"[UXM] _refresh_config_from_instrument: {e}")

    # ===================================================================
    # 4. 吞吐量与 CSI 测量
    # ===================================================================

    # SCPI 的 NaN 表示 —— 手册反复强调: 测量没开 / 刚 reset / 还没收到样本时,
    # 所有 float 型计数与比率都返回 9.91E+37。当成真值算会得到荒谬的数。
    _SCPI_NAN_THRESHOLD = 9.9e37

    @classmethod
    def _is_scpi_nan(cls, v: float) -> bool:
        return v != v or abs(v) >= cls._SCPI_NAN_THRESHOLD

    @classmethod
    def _parse_doubles(cls, raw: str) -> List[Optional[float]]:
        """把逗号分隔的 double 列表解析成 list, SCPI NaN → None。

        返回 list 长度 = 实际收到的元素个数 (**不补齐**) —— 调用方必须自己
        检查下标存在, 否则固件版本差异会静默取到错位的值。
        """
        out: List[Optional[float]] = []
        for tok in (raw or "").split(","):
            tok = tok.strip()
            if not tok:
                # ⚠ 空元素也**占位** —— 丢弃会让后面所有下标左移一位,
                #   正好是本 docstring 要防的"静默取到错位的值"。
                out.append(None)
                continue
            try:
                v = float(tok)
            except ValueError:
                out.append(None)
                continue
            out.append(None if cls._is_scpi_nan(v) else v)
        return out

    @staticmethod
    def _pick(vals: List[Optional[float]], idx: int) -> Optional[float]:
        """按下标取值; 越界或 NaN → None (而不是 0.0)。"""
        return vals[idx] if 0 <= idx < len(vals) else None

    async def get_throughput_metrics(self) -> ThroughputMetrics:
        """
        读取仪表与终端上报的 KPI。

        **口径 (2026-08-03 用户定)**: 记录的是**仪表和终端上报的真实参数**,
        不是我们自己去统计传输了多少数据 —— 吞吐量的"实际结果"由仪表的
        OTA 吞吐量计数器给出。

        每项的命令形式 / 返回元素含义 / 单位 / 前置条件均以 UXM 手册为准
        (2026-08-03 NotebookLM 查证, 见 docs/design/uxm-kpi-readback-fix.md):

          DL/UL 吞吐量  BTHRoughput:<dir>:THRoughput:OTA:<cell>?
                        → 6 doubles {progress, current, min, max, average,
                          current-scheduled}, **单位 bps**
                        → average 进 *_throughput_mbps (测试例结论),
                          current 进 *_throughput_current_mbps (实时值)
          DL BLER       BTHRoughput:DL:BLER:<cell>?   → 10 doubles, idx8 = pdschBlerRatio
          UL BLER       BTHRoughput:UL:BLER:<cell>?   → 6 doubles,  idx4 = nack-ratio
          CQI           CSI:CQI:STATistics?           → 6 doubles, idx3 = average
                        (⚠ idx0 是**样本数**不是 CQI)
          RI            CSI:RI:HISTogram?             → 8 doubles = RI **0..7** 计数
                        (⚠ 下标即 RI 值, 加权权重用 i 不是 i+1)
          RSRP/RSRQ/SINR  CONFig:NR5G:<cell>:MEASurement:JSON:REPort:FETCh?
                        → L3 RRC 测量报告 JSON

        **前置条件由 configure_mac_throughput_test() 负责**
        (BTHRoughput:STATe ON + CSI:STARt + UE 测量报告队列 ON);
        没开时仪表一律回 9.91E+37, 本方法会把它们记成"无数据"而不是 0。

        调用时机: UE 连接后, 统计窗口 (stat_count 子帧) 完成后读取。
        """
        cell = self._cell_id
        metrics = ThroughputMetrics()
        self._warn_once_if_profile_has_no_kpi_commands()
        # 哪些字段这一轮真的拿到了数 —— 进 measurement.log, 让读日志的人
        # 能分辨"测出来是 0"和"根本没测到"(P1-30 同一个母题)。
        valid: Dict[str, bool] = {}
        # 读到了、但**口径未经确认**的原始值 —— 只进证据不进结论字段。
        raw_unverified: Dict[str, float] = {}

        def _read_doubles(cmd_tmpl: Optional[str], what: str
                                ) -> List[Optional[float]]:
            """发一条返回 double 列表的查询; 命令未定义 / 失败 → 空 list。"""
            if not cmd_tmpl:
                # 方言没有这条命令 —— 显式跳过, 不盲发 (F64 禁盲试同源纪律)
                logger.debug(f"[UXM] {what}: 本方言未定义该命令, 跳过")
                return []
            try:
                raw = self._query(cmd_tmpl.format(cell=cell))
            except Exception as e:
                logger.warning(f"[UXM] {what} 查询失败: {e}")
                return []
            return self._parse_doubles(raw)

        # ── DL 吞吐量 (bps → Mbps) ──────────────────────────────
        dl = _read_doubles(self._cmds.MEAS_TPUT_DL_OTA, "DL OTA throughput")
        dl_avg, dl_cur = self._pick(dl, 4), self._pick(dl, 1)
        if dl_avg is not None:
            metrics.dl_throughput_mbps = dl_avg / 1e6
        if dl_cur is not None:
            metrics.dl_throughput_current_mbps = dl_cur / 1e6
        valid["dl_throughput"] = dl_avg is not None

        # ── UL 吞吐量 (bps → Mbps) ──────────────────────────────
        ul = _read_doubles(self._cmds.MEAS_TPUT_UL_OTA, "UL OTA throughput")
        ul_avg, ul_cur = self._pick(ul, 4), self._pick(ul, 1)
        if ul_avg is not None:
            metrics.ul_throughput_mbps = ul_avg / 1e6
        if ul_cur is not None:
            metrics.ul_throughput_current_mbps = ul_cur / 1e6
        valid["ul_throughput"] = ul_avg is not None

        # ── DL BLER (idx8 = pdschBlerRatio) ────────────────────
        dl_bler = _read_doubles(self._cmds.MEAS_BLER_DL, "DL BLER")
        v = self._pick(dl_bler, 8)
        if v is not None:
            metrics.dl_bler = v
        valid["dl_bler"] = v is not None

        # ── UL BLER (idx4 = nack-ratio) ────────────────────────
        ul_bler = _read_doubles(self._cmds.MEAS_BLER_UL, "UL BLER")
        v = self._pick(ul_bler, 4)
        if v is not None:
            metrics.ul_bler = v
        valid["ul_bler"] = v is not None

        # ── CQI ────────────────────────────────────────────────
        # 厂商 SCPI Reference 原文 (UXM5G_SCPI_02_NR_PHY_Measurements.md):
        #   result[0]=abs_nr_subframe_number   result[1]=cqi_total_count
        #   result[2]=cqi_minimum   result[3]=cqi_maximum
        #   result[4]=cqi_average   result[5]=cqi_median
        # ⚠ 取 **idx4 = average**。idx3 是 maximum（取它会系统性乐观）;
        #   idx0 是**首个 CSI 样本的绝对子帧号**——真机那个 7.92E+04 就是它,
        #   既不是 CQI 也不是样本数（样本数在 idx1）。
        cqi_vals = _read_doubles(self._cmds.MEAS_CSI_CQI, "CQI statistics")
        v = self._pick(cqi_vals, 4)
        if v is not None:
            metrics.cqi = int(round(v))
        valid["cqi"] = v is not None

        # ── RI (直方图) ────────────────────────────────────────
        # 8 个 bin = 手册的 "RI value [0..7]" —— 那是 **3GPP 上报码点**不是层数:
        # 手册同处把它与 "CQI value (0..15)" 并列, CQI 0..15 同样是码点。
        # rank = 码点 + 1（rank 0 物理上不存在, 而 rank_indicator 全仓契约是
        # **层数** —— 默认 1、mock 产 1..2、analysis.py 拿它跟
        # min_avg_rank_indicator（默认 1.8）比）。
        # ⚠ 2026-08-03: 我一度把权重从 (i+1) 改成 i，**那是回归** ——
        #   会让真跑 rank 2 的 DUT 报 1.0 而必然 FAIL。已改回。
        ri_hist = _read_doubles(self._cmds.MEAS_CSI_RI, "RI histogram")
        counts = [c for c in ri_hist if c is not None]
        total = sum(counts)
        if counts and total > 0:
            weighted = sum((i + 1) * c for i, c in enumerate(ri_hist) if c is not None)
            metrics.rank_indicator = int(round(weighted / total))
            valid["rank_indicator"] = True
        else:
            valid["rank_indicator"] = False

        # ── UE 上报的 RSRP / RSRQ / SINR (L3 测量报告 JSON) ─────
        valid["rsrp"] = valid["sinr"] = False
        if self._cmds.MEAS_UE_REPORT_JSON:
            try:
                rep_raw = self._query(
                    self._cmds.MEAS_UE_REPORT_JSON.format(cell=cell)
                )
                rsrp, sinr = self._parse_ue_measurement_report(rep_raw)
                # ⚠ **不往 rsrp_dbm / sinr_db 里写**（Codex #275 R2 P2）——
                # 手册**没有说明**这两个值的口径: 是 3GPP RRC 上报的原始码点
                # （rsrp-Result 0..127，需 value-156 换算）还是仪表已换算好的
                # dBm/dB，手册对 JSON 与 legacy 两种 FETCh 都只给了示例
                # （示例里全是 "NaN"），没有单位、范围、换算公式
                # （NotebookLM 三次明确回"手册未说明"，未做推断）。
                #
                # 按 3GPP 通式自己换算 = 盲试，**正是本片要治的病**;
                # 原样写进名为 `_dbm` 的字段 = 假数据冒充真数据，同病。
                # 所以只把**原样值**留进证据（scpi.log 有完整响应，
                # measurement.log 记 *_raw_unverified），字段保持"未读到"。
                # 口径待现场用诊断序列对着面板读数比对后再接线。
                if rsrp is not None:
                    raw_unverified["rsrp_raw"] = rsrp
                if sinr is not None:
                    raw_unverified["sinr_raw"] = sinr
            except Exception as e:
                logger.warning(f"[UXM] UE 测量报告读取失败: {e}")
        else:
            logger.debug("[UXM] UE 测量报告: 本方言未定义该命令, 跳过")

        # ── 测量数据归档 → measurement.log ──
        # 每次 KPI 快照独立记录，供报告生成和数据分析使用
        meas_logger = logging.getLogger("app.measurement.throughput")
        # ⚠ 每个 KPI 都带一个 *_valid 标志 —— 没有它, "DL=0.0Mbps" 与
        # "这一项根本没读到" 在日志里长得一模一样 (P1-30 同一个母题)。
        missing = [k for k, ok in valid.items() if not ok]
        meas_logger.info(
            f"[KPI] DL={metrics.dl_throughput_mbps:.1f}Mbps"
            f"(cur {metrics.dl_throughput_current_mbps:.1f}) "
            f"UL={metrics.ul_throughput_mbps:.1f}Mbps "
            f"BLER={metrics.dl_bler:.4f} CQI={metrics.cqi} RI={metrics.rank_indicator} "
            f"RSRP={metrics.rsrp_dbm:.1f}dBm SINR={metrics.sinr_db:.1f}dB"
            + (f"  ⚠未读到: {','.join(missing)}" if missing else ""),
            extra={
                "instrument_id": self.instrument_id,
                "dl_throughput_mbps": metrics.dl_throughput_mbps,
                "dl_throughput_current_mbps": metrics.dl_throughput_current_mbps,
                "ul_throughput_mbps": metrics.ul_throughput_mbps,
                "ul_throughput_current_mbps": metrics.ul_throughput_current_mbps,
                "dl_bler": metrics.dl_bler,
                "ul_bler": metrics.ul_bler,
                "cqi": metrics.cqi,
                "rank_indicator": metrics.rank_indicator,
                "mcs_dl": getattr(metrics, "mcs_dl", None),
                "mcs_ul": getattr(metrics, "mcs_ul", None),
                "rsrp_dbm": metrics.rsrp_dbm,
                "sinr_db": metrics.sinr_db,
                "kpi_valid": valid,
                "kpi_missing": missing,
                # 口径未确认的原始上报值（手册未说明单位）——
                # 只作证据，**不要**当 dBm/dB 用。
                "kpi_raw_unverified": raw_unverified,
                "band": self._band,
                "bandwidth_mhz": self._bandwidth_mhz,
                "dl_power_dbm": self._dl_power_dbm,
            },
        )

        return metrics

    async def measure_throughput_window(self, window_s: float) -> ThroughputMetrics:
        """Phase 2d: 清零 → 等一个窗口 → 读, 取一个 i.i.d. 样本。

        不这么做的话, 同一个 stat_count 窗口里连着调 get_throughput_metrics()
        读到的是同一份累积值, per-sample std/mean 没有意义。

        ⚠ 2026-08-03 改写: 原实现用 `BTHRoughput:DL:TSTatistics:STARt|STOP`
        圈窗口 —— **手册的 SCPI 命令树里没有这两条命令** (NotebookLM 查证),
        真机上一直在失败, 只是那句 warning 没人看。手册给的做法是发
        `BTHRoughput:CLEar`: 它清空当前累积, **测量在跑时会自动重新开始** ——
        正好就是"重新起一个窗口"的语义, 且只需一条命令。
        """
        clear_cmd = self._cmds.MEAS_BTHROUGHPUT_CLEAR
        if not clear_cmd:
            # 方言没有清零命令 —— 退化成直接读累积值, 并**明说**这一点,
            # 否则调用方会把"整段累积"当成"这个窗口的样本"。
            logger.warning(
                "[UXM] 本方言无 BTHRoughput:CLEar — 无法圈窗口, "
                "读到的是自测量开始以来的累积值, 不是 %.1fs 窗口样本", window_s
            )
            await asyncio.sleep(max(window_s, 0.0))
            return await self.get_throughput_metrics()

        try:
            self._write(clear_cmd)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[UXM] BTHRoughput:CLEar 失败 (%s) — 本次读到的是累积值不是窗口样本", e
            )
        await asyncio.sleep(max(window_s, 0.0))
        return await self.get_throughput_metrics()

    async def get_ue_info(self) -> Dict[str, Any]:
        """获取 UE 信息 (TODO: 从 UXM 查询)"""
        return {
            "connected": self._cell_state == CellState.CONNECTED,
            "cell_id": self._cell_id,
        }

    async def query_ue_capability(self) -> Dict[str, Any]:
        """Phase 2e: 查询已 attach UE 的 3GPP 能力。

        4x4 测试前必须确认 DUT 真支持 4 layer DL。如果 UE 没 attach 或
        UXM 返回错误, 标 source='unavailable' + 让 caller 决定是否硬 fail。
        """
        cell = self._cell_id

        def _safe_query(scpi: str, parser=str) -> Any:
            try:
                resp = self._query(scpi.format(cell=cell))
                if resp is None:
                    return None
                return parser(resp.strip())
            except Exception as e:  # noqa: BLE001
                logger.debug("[UXM] capability query %s failed: %s", scpi, e)
                return None

        max_dl = _safe_query(self._cmds.UE_MAX_DL_LAYERS_QUERY, lambda s: int(float(s)))
        max_ul = _safe_query(self._cmds.UE_MAX_UL_LAYERS_QUERY, lambda s: int(float(s)))
        max_mod = _safe_query(self._cmds.UE_MAX_MODULATION_DL_QUERY)
        bands_str = _safe_query(self._cmds.UE_SUPPORTED_BANDS_QUERY)
        bands = (
            [b.strip() for b in bands_str.split(",") if b.strip()]
            if bands_str else []
        )

        source = "real_ue" if max_dl is not None else "unavailable"
        if source == "unavailable":
            logger.warning(
                "[UXM] UE capability unavailable (likely no UE attached or "
                "firmware doesn't support UEINFO subsystem; check operator's "
                "UXM version against self._cmds.UE_CAPABILITY_* SCPI strings)"
            )

        return {
            "max_dl_layers": max_dl,
            "max_ul_layers": max_ul,
            "max_modulation_dl": max_mod,
            "max_modulation_ul": None,  # not all firmware exposes UL modulation
            "supported_bands": bands,
            "ca_combinations": [],  # CA combo query is firmware-specific; TODO Phase 2g
            "source": source,
        }

    async def reconfigure_rrc(
        self,
        *,
        mimo_layers: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> bool:
        """Phase 2e: trigger RRC reconfiguration.

        Some UXM firmware applies cell config changes via RRC reconfig
        automatically; on those firmwares this is a no-op + APPLY. On
        older firmware the explicit RRC:RECon SCPI sequence is required.
        """
        cell = self._cell_id
        try:
            if mimo_layers is not None:
                self._write(self._cmds.RRC_RECONFIG_LAYERS.format(
                    cell=cell, layers=int(mimo_layers)
                ))
            if modulation is not None:
                self._write(self._cmds.RRC_RECONFIG_MODULATION.format(
                    cell=cell, mod=modulation
                ))
            self._write(self._cmds.RRC_RECONFIG_APPLY.format(cell=cell))
            self._query(self._cmds.OPC)
            logger.info(
                "[UXM] RRC reconfigured: layers=%s modulation=%s",
                mimo_layers, modulation,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("[UXM] RRC reconfiguration failed: %s", e)
            return False

    async def add_secondary_cell(
        self,
        cc_index: int,
        cc_config: Dict[str, Any],
    ) -> bool:
        """Phase 2g: configure + add an SCell.

        Lifecycle: CONF:FREQ/BW/SCS/BAND → ADD. Activation is separate
        (call activate_secondary_cells after all SCells added).
        """
        if cc_index < 1:
            logger.error("[UXM] add_secondary_cell: cc_index must be ≥ 1 (PCell is 0)")
            return False
        cell = self._cell_id
        try:
            freq_mhz = float(cc_config.get("frequency_mhz", 0))
            bw_mhz = float(cc_config.get("bandwidth_mhz", 100))
            scs_khz = int(cc_config.get("scs_khz", 30))
            band = cc_config.get("band")

            self._write(self._cmds.SCELL_CONF_FREQ.format(
                cell=cell, idx=cc_index, freq_mhz=freq_mhz
            ))
            self._write(self._cmds.SCELL_CONF_BW.format(
                cell=cell, idx=cc_index, bw_mhz=bw_mhz
            ))
            self._write(self._cmds.SCELL_CONF_SCS.format(
                cell=cell, idx=cc_index, scs_khz=scs_khz
            ))
            if band:
                self._write(self._cmds.SCELL_CONF_BAND.format(
                    cell=cell, idx=cc_index, band=band
                ))
            self._write(self._cmds.SCELL_ADD.format(
                cell=cell, idx=cc_index
            ))
            self._query(self._cmds.OPC)
            logger.info(
                "[UXM] SCell %d added: freq=%.1f MHz BW=%.0f MHz scs=%dkHz band=%s",
                cc_index, freq_mhz, bw_mhz, scs_khz, band or "auto",
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("[UXM] SCell %d add failed: %s", cc_index, e)
            return False

    async def activate_secondary_cells(self) -> bool:
        """Phase 2g: query SCell list, activate each one. UE receives
        SCellActivation MAC CE on the next subframe.
        """
        cell = self._cell_id
        try:
            scell_resp = self._query(
                self._cmds.SCELL_LIST_QUERY.format(cell=cell)
            )
            if not scell_resp or not scell_resp.strip():
                logger.warning("[UXM] No SCells configured to activate")
                return True
            indices = [int(s) for s in scell_resp.strip().split(",") if s.strip().isdigit()]
            for idx in indices:
                self._write(self._cmds.SCELL_ACTIVATE.format(cell=cell, idx=idx))
            self._query(self._cmds.OPC)
            logger.info("[UXM] Activated %d SCell(s): %s", len(indices), indices)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("[UXM] SCell activation failed: %s", e)
            return False

    async def remove_all_secondary_cells(self) -> bool:
        """Phase 2g: cleanup helper — remove every SCell on this PCell."""
        cell = self._cell_id
        try:
            self._write(self._cmds.SCELL_REMOVE_ALL.format(cell=cell))
            self._query(self._cmds.OPC)
            logger.info("[UXM] All SCells removed for cell %s", cell)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("[UXM] SCell remove-all failed: %s", e)
            return False

    # ===================================================================
    # 5. 标准 InstrumentDriver 接口
    # ===================================================================

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="5g_nr",
                description="5G NR Signaling (SA/NSA)",
                supported=True,
                parameters={
                    "bands": ["N78", "N41", "N77", "N79"],
                    "max_bandwidth_mhz": 100,
                    "max_mimo_layers": 4,
                    "scs_options_khz": [15, 30, 60, 120],
                },
            ),
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        tput = await self.get_throughput_metrics()
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "cell_state": self._cell_state.value,
                "band": self._band,
                "frequency_mhz": self._frequency_mhz,
                "bandwidth_mhz": self._bandwidth_mhz,
                "scs_khz": self._scs_khz,
                "dl_power_dbm": self._dl_power_dbm,
                **tput.to_dict(),
            },
        )

    async def reset(self) -> bool:
        """复位仪器"""
        try:
            await self.stop_signaling()
            self._write("*RST")
            self._query("*OPC?")
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception as e:
            logger.error(f"[UXM] reset failed: {e}")
            return False

    def get_supported_technologies(self) -> List[RadioTechnology]:
        return [RadioTechnology.NR5G]

    # ===================================================================
    # 内部 VISA 工具方法 (SCPI 日志由基类 _write/_query 自动处理)
    # ===================================================================

    # ── Connection-loss-aware retry (sync flavour — F64/FS16 are async) ─
    # Same Codex P2 lesson: only VI_ERROR_CONN_LOST / VI_ERROR_INV_OBJECT
    # trigger reconnect; VI_ERROR_TMO propagates (let timeout be a
    # timeout). UXM's _do_* are sync (PyVISA call without to_thread)
    # because the base ``_query`` template handles both shapes — sync
    # _do_query just returns str directly.

    @staticmethod
    def _is_visa_conn_lost(exc: BaseException) -> bool:
        from app.hal._visa_reconnect import is_visa_conn_lost
        return is_visa_conn_lost(exc)

    def _silent_reconnect_visa(self) -> bool:
        """Sync reopen of the UXM VISA session — reuses the resource
        string captured by connect() so we don't re-run the Platform/
        hislip2 auto-detection."""
        if self._visa_rm is None or not self._active_resource_string:
            return False
        try:
            if self._visa_session is not None:
                self._visa_session.close()
        except Exception:
            pass
        self._visa_session = None
        try:
            self._visa_session = self._visa_rm.open_resource(
                self._active_resource_string,
                timeout=VISA_TIMEOUT_DEFAULT,
            )
            if "SOCKET" in self._active_resource_string:
                self._visa_session.read_termination = "\n"
                self._visa_session.write_termination = "\n"
            logger.info(
                f"[UXM] silent reconnect succeeded — reopened "
                f"{self._active_resource_string}"
            )
            return True
        except Exception as e:
            logger.error(f"[UXM] silent reconnect failed: {e}")
            self._visa_session = None
            return False

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        safe_cmd = redact_instrument_command_text(cmd)
        for attempt in (0, 1):
            if not self._visa_session:
                raise ConnectionError("[UXM] Not connected")
            try:
                self._visa_session.write(cmd)
                return
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[UXM] VISA connection lost on write '{safe_cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if self._silent_reconnect_visa():
                        continue
                raise

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        safe_cmd = redact_instrument_command_text(cmd)
        for attempt in (0, 1):
            if not self._visa_session:
                raise ConnectionError("[UXM] Not connected")
            try:
                return self._visa_session.query(cmd)
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[UXM] VISA connection lost on query '{safe_cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if self._silent_reconnect_visa():
                        continue
                raise
        # Unreachable.
        return ""

    def _drain_errors(self, limit: int = 16) -> List[str]:
        """排空错误队列并**返回**取到的真错误（P1-33）。

        ⚠ 换源自 `_check_errors()` —— 那个只 log 不返回，错误被吞掉，
          调用方没法把它**归属到产生它的那条命令**上。而 P1-33 要答的正是
          「哪几条被 IRAT 拒了」。
        ⚠ P1-41 根因机制：该 helper 的前身原来是 `while True`；当前虽有通用上界，
          但错误查询自身若不受 Test App 支持，每问一次都会再制造一条
          ``-113,Undefined header``，而 MAC 每组又会重新排一次，仍会放大日志。
          连续两次收到**相同**的 -113/Undefined header 时无法区分“队列里恰有
          两条相同旧错误”和“查询自身在补充错误”；按代价不对称保守停止并
          返回显式标记，由业务流程 fail-closed，不猜另一条 SCPI。

        NotebookLM/厂商手册只明确 ``SYSTem:ERRor[:NEXT]?`` 会弹出最旧错误、
        clean 回 ``+0,No error``；没有明确它适用于 5G_NR_Test / LTE_NR_IRAT，
        也没有定义查询自身报 -113 时的终止语义。因此保留 profile 命令并限制
        风险，绝不把缩写或别名升级成 confirmed。
        """
        out: List[str] = []
        previous_undefined: Optional[str] = None
        for _ in range(limit):
            err = self._query(self._cmds.ERR).strip()
            try:
                code = int(err.split(",", 1)[0])
            except ValueError:
                code = None
            # 保留 APPLY 原有契约：既接受手册形态 +0,"No error"，也接受
            # 现场/既有 fake 的裸 0。统一 helper 不能把原先明确 clean 的形态
            # 收窄成错误。
            if code == 0:
                return out
            out.append(err)
            if code is None:
                out.append(
                    f"<错误查询回复不可解析: {err!r}；已停止排队；"
                    "当前流程不得据此判成功>"
                )
                return out
            is_undefined = code == -113 and "UNDEFINED HEADER" in err.upper()
            if is_undefined and err == previous_undefined:
                out.append(
                    "<错误查询疑似不受支持: 连续两次返回相同 -113/Undefined "
                    "header，已停止排队；当前流程不得据此判成功>"
                )
                return out
            previous_undefined = err if is_undefined else None
        out.append(f"<队列未排空: 已读 {limit} 条仍未见 No error>")
        return out

    @staticmethod
    def _error_queue_unusable(errors: List[str]) -> bool:
        """P1-41：识别 `_drain_errors` 的 fail-closed 标记。"""
        return bool(errors and errors[-1].startswith((
            "<错误查询疑似不受支持:",
            "<错误查询回复不可解析:",
            "<队列未排空:",
        )))
