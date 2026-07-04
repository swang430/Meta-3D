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
from enum import Enum
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
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
UXM_DEFAULT_TOPOLOGY_PROFILE_ID = "caict_n78_3600_4x4"

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

        Background: ``UxmLteNrIratProfile`` deliberately sets many command
        templates to ``None`` for commands that exist in pure 5G_NR_Test
        but aren't surfaced by LTE_NR_IRAT (e.g. ``CELL_SCS``,
        ``MIMO_DL_LAYERS``, ``TDD_PATTERN`` — the IRAT app routes those
        through different paths or hard-codes them). Driver methods that
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
        if template is None:
            logger.info(
                f"[UXM/{self._cmds.PROFILE_NAME}] {name} not exposed by this "
                f"Test App; skipping (set it in the profile if your firmware "
                f"supports a vendor alias)"
            )
            return None
        return template.format(**fmt) if fmt else template

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
            explicit_non_inst0 = bool(self.visa_resource) and (
                "inst0" not in (self.visa_resource or "")
            )
            on_platform_endpoint = (
                "E7515B Platform" in idn
                and ("SOCKET" in resource_str or "hislip0" in resource_str
                     or "inst0" in resource_str)
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
            if self._cell_state != CellState.OFF:
                await self.stop_signaling()

            if self._visa_session:
                self._visa_session.close()
                self._visa_session = None
            if self._visa_rm:
                self._visa_rm.close()
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

            # ---- 12. TDD 时隙格式 ----
            if "tdd_pattern" in config:
                if (q := self._cmd("TDD_PATTERN", cell=cell)) is not None:
                    self._write(f"{q} {config['tdd_pattern'].upper()}")
            if "tdd_period" in config:
                if (q := self._cmd("TDD_PERIOD", cell=cell)) is not None:
                    self._write(f"{q} {config['tdd_period']}")

            # ---- 13. PDSCH 调度算法 (Full Buffer) ----
            if "sched_algo" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                if (q := self._cmd("PDSCH_SCHED_ALGO", cell=cell, bwp=bwp)) is not None:
                    self._write(f"{q} {config['sched_algo'].upper()}")

            # ---- 14. AMC 开关 (关闭以固定 MCS) ----
            if "enable_amc" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                amc_val = "ON" if config["enable_amc"] else "OFF"
                dl_amc = self._cmd("PDSCH_AMC_ENABLE", cell=cell, bwp=bwp)
                ul_amc = self._cmd("PUSCH_AMC_ENABLE", cell=cell, bwp=bwp)
                if dl_amc is not None:
                    self._write(f"{dl_amc} {amc_val}")
                if ul_amc is not None:
                    self._write(f"{ul_amc} {amc_val}")
                if dl_amc is not None or ul_amc is not None:
                    logger.info(f"[UXM] AMC: {amc_val}")

            # ---- 15. HARQ 配置 ----
            if "harq_max_trans" in config:
                if (q := self._cmd("HARQ_MAX_TRANS", cell=cell)) is not None:
                    self._write(f"{q} {config['harq_max_trans']}")
            if "harq_processes" in config:
                if (q := self._cmd("HARQ_PROCESSES", cell=cell)) is not None:
                    self._write(f"{q} {config['harq_processes']}")

            # ---- 16. CSI-RS 端口数 (与 MIMO 层数对齐) ----
            if "csi_rs_ports" in config:
                if (q := self._cmd("CSIRS_PORTS", cell=cell)) is not None:
                    self._write(f"{q} {config['csi_rs_ports']}")
            elif "mimo_layers" in config:
                # 自动推断: 1L→2ports, 2L→4ports, 4L→8ports
                auto_ports = max(2, config["mimo_layers"] * 2)
                if (q := self._cmd("CSIRS_PORTS", cell=cell)) is not None:
                    self._write(f"{q} {auto_ports}")

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

            # 同步等待
            self._query("*OPC?")

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
    ) -> bool:
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
            True if all parameters configured successfully
        """
        cell = cell or self._cell_id
        bwp = self._bwp_id
        success = True

        try:
            logger.info(
                f"[UXM] Configuring MAC throughput test: "
                f"MIMO={mimo_layers}L, MCS={mcs}, AMC={'ON' if enable_amc else 'OFF'}, "
                f"TDD={tdd_pattern}, stat_count={stat_count}"
            )

            # 1. Full Buffer 调度
            self._write(
                self._cmds.PDSCH_SCHED_ALGO.format(cell=cell, bwp=bwp)
                + " FULLBUFFER"
            )

            # 2. AMC 开关
            amc_val = "ON" if enable_amc else "OFF"
            self._write(
                self._cmds.PDSCH_AMC_ENABLE.format(cell=cell, bwp=bwp)
                + f" {amc_val}"
            )
            self._write(
                self._cmds.PUSCH_AMC_ENABLE.format(cell=cell, bwp=bwp)
                + f" {amc_val}"
            )

            # 3. 固定 MCS (当 AMC=OFF 时生效)
            self._write(
                self._cmds.PDSCH_MCS.format(cell=cell, bwp=bwp)
                + f" {mcs}"
            )

            # 4. 全 RB 分配
            self._write(
                self._cmds.PDSCH_RB_ALLOC.format(cell=cell, bwp=bwp)
                + f" {rb_alloc}"
            )

            # 5. TDD 时隙格式
            self._write(
                self._cmds.TDD_PATTERN.format(cell=cell)
                + f" {tdd_pattern}"
            )
            self._write(
                self._cmds.TDD_PERIOD.format(cell=cell)
                + f" {tdd_period}"
            )

            # 6. HARQ
            self._write(
                self._cmds.HARQ_MAX_TRANS.format(cell=cell)
                + f" {harq_max_trans}"
            )
            self._write(
                self._cmds.HARQ_PROCESSES.format(cell=cell)
                + f" {harq_processes}"
            )

            # 7. CSI-RS 端口数 (1L→2ports, 2L→4ports, 4L→8ports)
            csi_rs_ports = max(2, mimo_layers * 2)
            self._write(
                self._cmds.CSIRS_PORTS.format(cell=cell)
                + f" {csi_rs_ports}"
            )

            # 8. 统计窗口
            self._write(
                self._cmds.MEAS_TPUT_STAT_COUNT.format(cell=cell)
                + f" {stat_count}"
            )

            # 同步等待所有配置生效
            self._query("*OPC?")

            logger.info(
                f"[UXM] MAC throughput test configured: "
                f"Full Buffer ON, AMC {amc_val}, MCS={mcs}, RB={rb_alloc}, "
                f"TDD={tdd_pattern}/{tdd_period}, "
                f"HARQ={harq_max_trans}x/{harq_processes}proc, "
                f"CSI-RS={csi_rs_ports}ports, stat={stat_count}subframes"
            )
            return True

        except Exception as e:
            logger.error(f"[UXM] configure_mac_throughput_test failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

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

            # 激活小区
            self._write(self._cmds.CELL_STATE_ON.format(cell=cell))
            self._query("*OPC?")
            self._cell_state = CellState.ON

            # 恢复超时并等待 UE Attach
            self._visa_session.timeout = VISA_TIMEOUT_ATTACH

            elapsed = 0.0
            poll_interval = 2.0
            while elapsed < timeout_s:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # 查询连接状态
                # UXM 返回: "IDLE" / "ATT" / "CONN" / "OFF"
                state_str = self._query(
                    self._cmds.CELL_STATE_QUERY.format(cell=cell)
                ).strip().upper()

                if "CONN" in state_str or "ATT" in state_str:
                    self._cell_state = CellState.CONNECTED
                    logger.info(
                        f"[UXM] UE attached after {elapsed:.1f}s"
                    )
                    break

            # 恢复默认超时
            self._visa_session.timeout = old_timeout

            if self._cell_state == CellState.CONNECTED:
                return True
            else:
                logger.warning(
                    f"[UXM] UE attach timeout after {timeout_s}s"
                )
                self._cell_state = CellState.IDLE
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

    async def get_cell_state(self) -> CellState:
        """查询小区当前状态"""
        try:
            state = self._query(
                self._cmds.CELL_STATE_QUERY.format(cell=self._cell_id)
            ).strip().upper()
            if "OFF" in state:
                return CellState.OFF
            elif "CONN" in state or "ATT" in state:
                return CellState.CONNECTED
            elif "ON" in state or "IDLE" in state:
                return CellState.IDLE
            return CellState.ERROR
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

            # 加载前先安全关闭小区
            if self._cell_state != CellState.OFF:
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

    async def get_throughput_metrics(self) -> ThroughputMetrics:
        """
        轮询读取 MAC 层 DL+UL 吞吐量指标。

        包含:
          - DL 吞吐量 / BLER      (PDSCH MAC 层统计)
          - UL 吞吐量 / BLER      (PUSCH MAC 层统计)
          - CQI / RI             (CSI 反馈统计)

        调用时机:
          UE 连接后，在 configure_mac_throughput_test() 设定的统计窗口
          (stat_count 子帧) 完成后读取，确保统计稳定。
        """
        import json as _json
        cell = self._cell_id
        metrics = ThroughputMetrics()

        try:
            # ── DL 吞吐量 (JSON 格式，包含 Mbps / 子帧数 / 传输块统计) ──
            tput_json = self._query(
                self._cmds.MEAS_BTHROUGHPUT_DL_JSON.format(cell=cell)
            )
            if tput_json and tput_json.strip():
                try:
                    tput_data = _json.loads(tput_json)
                    # UXM JSON 键名可能为 "DL_Throughput_Mbps" 或 "throughput"
                    metrics.dl_throughput_mbps = (
                        tput_data.get("DL_Throughput_Mbps")
                        or tput_data.get("throughput", 0.0)
                    )
                    # 顺带取 MCS (如果 JSON 有)
                    if "DL_MCS" in tput_data:
                        metrics.mcs_dl = int(tput_data["DL_MCS"])
                except _json.JSONDecodeError:
                    # fallback: 直接数值解析
                    try:
                        metrics.dl_throughput_mbps = float(
                            tput_json.strip().split()[0]
                        )
                    except (ValueError, IndexError):
                        pass

            # ── DL BLER (格式: "mean,min,max" 或单值) ──
            bler_str = self._query(
                self._cmds.MEAS_BTHROUGHPUT_DL_BLER.format(cell=cell)
            )
            if bler_str and bler_str.strip():
                try:
                    metrics.dl_bler = float(bler_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # ── UL 吞吐量 ──
            ul_json = self._query(
                self._cmds.MEAS_TPUT_UL_JSON.format(cell=cell)
            )
            if ul_json and ul_json.strip():
                try:
                    ul_data = _json.loads(ul_json)
                    metrics.ul_throughput_mbps = (
                        ul_data.get("UL_Throughput_Mbps")
                        or ul_data.get("throughput", 0.0)
                    )
                    if "UL_MCS" in ul_data:
                        metrics.mcs_ul = int(ul_data["UL_MCS"])
                except _json.JSONDecodeError:
                    try:
                        metrics.ul_throughput_mbps = float(
                            ul_json.strip().split()[0]
                        )
                    except (ValueError, IndexError):
                        pass

            # ── UL BLER ──
            ul_bler_str = self._query(
                self._cmds.MEAS_TPUT_UL_BLER.format(cell=cell)
            )
            if ul_bler_str and ul_bler_str.strip():
                try:
                    metrics.ul_bler = float(ul_bler_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # ── CQI (均值, 格式: "mean,std,min,max,...") ──
            cqi_str = self._query(
                self._cmds.MEAS_CSI_CQI.format(cell=cell)
            )
            if cqi_str and cqi_str.strip():
                try:
                    metrics.cqi = int(float(cqi_str.split(",")[0]))
                except (ValueError, IndexError):
                    pass

            # ── RI (均值, 直方图第一个值) ──
            ri_str = self._query(
                self._cmds.MEAS_CSI_RI.format(cell=cell)
            )
            if ri_str and ri_str.strip():
                try:
                    # RI 直方图: "count_ri1, count_ri2, count_ri3, count_ri4"
                    # 计算加权均值
                    ri_counts = [
                        float(x) for x in ri_str.split(",") if x.strip()
                    ]
                    total = sum(ri_counts)
                    if total > 0:
                        metrics.rank_indicator = int(
                            sum((i + 1) * c for i, c in enumerate(ri_counts))
                            / total
                        )
                    else:
                        metrics.rank_indicator = int(
                            float(ri_str.split(",")[0])
                        )
                except (ValueError, IndexError):
                    pass

            # ── RSRP (UE 测量上报, 格式: "mean,min,max") ──
            rsrp_str = self._query(
                self._cmds.MEAS_UE_RSRP.format(cell=cell)
            )
            if rsrp_str and rsrp_str.strip():
                try:
                    metrics.rsrp_dbm = float(rsrp_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # ── SINR (UE 测量上报, 格式: "mean,min,max") ──
            sinr_str = self._query(
                self._cmds.MEAS_UE_SINR.format(cell=cell)
            )
            if sinr_str and sinr_str.strip():
                try:
                    metrics.sinr_db = float(sinr_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

        except Exception as e:
            logger.warning(f"[UXM] get_throughput_metrics partial fail: {e}")

        # ── 测量数据归档 → measurement.log ──
        # 每次 KPI 快照独立记录，供报告生成和数据分析使用
        meas_logger = logging.getLogger("app.measurement.throughput")
        meas_logger.info(
            f"[KPI] DL={metrics.dl_throughput_mbps:.1f}Mbps "
            f"BLER={metrics.dl_bler:.4f} CQI={metrics.cqi} RI={metrics.rank_indicator} "
            f"RSRP={metrics.rsrp_dbm:.1f}dBm SINR={metrics.sinr_db:.1f}dB",
            extra={
                "instrument_id": self.instrument_id,
                "dl_throughput_mbps": metrics.dl_throughput_mbps,
                "dl_bler": metrics.dl_bler,
                "ul_throughput_mbps": getattr(metrics, "ul_throughput_mbps", 0.0),
                "ul_bler": getattr(metrics, "ul_bler", 0.0),
                "cqi": metrics.cqi,
                "rank_indicator": metrics.rank_indicator,
                "mcs_dl": getattr(metrics, "mcs_dl", None),
                "mcs_ul": getattr(metrics, "mcs_ul", None),
                "rsrp_dbm": metrics.rsrp_dbm,
                "sinr_db": metrics.sinr_db,
                "band": self._band,
                "bandwidth_mhz": self._bandwidth_mhz,
                "dl_power_dbm": self._dl_power_dbm,
            },
        )

        return metrics

    async def measure_throughput_window(self, window_s: float) -> ThroughputMetrics:
        """Phase 2d: drive START → wait → query → STOP for an i.i.d. sample.

        UXM exposes BTHRoughput:DL:TSTatistics:STARt/STOP which gates a
        statistics window cleanly — without this, multiple back-to-back
        get_throughput_metrics() calls inside one stat_count window read the
        same accumulated value, making per-sample std/mean meaningless.

        STOP failures are swallowed; the next START will overwrite anyway.
        """
        cell = self._cell_id
        try:
            self._write(self._cmds.MEAS_BTHROUGHPUT_DL_START.format(cell=cell))
        except Exception as e:  # noqa: BLE001
            logger.warning("[UXM] BTHR:DL:START failed (%s) — falling back to plain query", e)
            return await self.get_throughput_metrics()

        try:
            await asyncio.sleep(max(window_s, 0.0))
            metrics = await self.get_throughput_metrics()
        finally:
            try:
                self._write(self._cmds.MEAS_BTHROUGHPUT_DL_STOP.format(cell=cell))
            except Exception as e:  # noqa: BLE001
                logger.debug("[UXM] BTHR:DL:STOP failed (%s); ignored", e)
        return metrics

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
        for attempt in (0, 1):
            if not self._visa_session:
                raise ConnectionError("[UXM] Not connected")
            try:
                self._visa_session.write(cmd)
                return
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[UXM] VISA connection lost on write '{cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if self._silent_reconnect_visa():
                        continue
                raise

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        for attempt in (0, 1):
            if not self._visa_session:
                raise ConnectionError("[UXM] Not connected")
            try:
                return self._visa_session.query(cmd)
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[UXM] VISA connection lost on query '{cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if self._silent_reconnect_visa():
                        continue
                raise
        # Unreachable.
        return ""

    def _check_errors(self) -> None:
        """检查并清除错误队列"""
        while True:
            err = self._query(self._cmds.ERR).strip()
            if err.startswith("0,") or err.startswith("+0,"):
                break
            logger.warning(f"[UXM] Instrument error: {err}")

