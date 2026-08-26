"""
Rohde & Schwarz CMW500 — HAL Driver (LTE Signaling)
=====================================================

型号专用驱动，实现 BaseStationDriver 抽象接口。
基于 PyVISA 通过 HiSLIP (端口 4880) 或 TCP Socket (端口 5025) 与 CMW500 通信。

SCPI 子系统参考 (从 CMW_LTE_UE_UserManual_V4-0-250 提取):
  - CONFigure:LTE:SIGN<i>:*       — 信令模式小区配置 (493 commands)
  - SOURce:LTE:SIGN<i>:CELL:STATe — 小区开/关
  - FETCh:LTE:SIGN<i>:*           — 信令测量结果 (68 commands)
  - SENSe:LTE:SIGN<i>:*           — 连接监控 / 吞吐量 (271 commands)
  - CALL:LTE:SIGN<i>:*            — PS/CS 呼叫控制
  - INITiate:LTE:SIGN<i>          — 启动信令测量
  - ROUTe:LTE:SIGN:*              — RF 路由配置

R&S 命名约定:
  <i> = 1 | 2  (CMW 最多 2 个信令通道)
  SIGN = 信令模式 (vs MEAS = 测量模式)

文档来源:
  R&S®CMW500 LTE UE User Manual V4.0.250
  R&S Remote Control via SCPI Getting Started V04
"""

import logging
import asyncio
import re
from uuid import uuid4
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
    resolve_configured_tcpip_connection,
)
from app.hal.base_station import (
    BaseStationControlReleaseResult,
    BaseStationIdentity,
    BaseStationDriver,
    BaseStationMeasurementWindow,
    BaseStationRemoteSessionResult,
    BaseStationRequestedConfig,
    RadioTechnology,
    CellState,
    ThroughputMetrics,
)
from app.hal.lte_earfcn import validate_lte_band_options
from app.hal.cmw500_command_profile import (
    CMW500_LTE_COMMANDS,
    Cmw500LteCommandProfile,
    CmwNx2Route,
)
from app.hal.base_station_adapter_profile import BaseStationAdapterProfile
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEvidenceItem,
    capture_scpi_exchanges,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BaseStationRouteResult:
    requested: dict[str, str] | None
    applied: dict[str, str] | None
    source_reference: str
    confirmed: bool
    reason: str
    exchange_ids: list[str]


@dataclass(frozen=True)
class Cmw500FormalCapabilityDecision:
    """Read-only admission result; it never mutates the instrument or DB."""

    ready: bool
    status: str
    reason: str


# ===========================================================================
# CMW500 SCPI 命令映射表
# ===========================================================================

class CmwScpiCommands:
    """R&S CMW500 LTE 信令模式 SCPI 命令速查表

    命名约定:
      <i>     = 1 (默认信令通道)
      SIGN<i> = 信令模式通道
      PCC     = 主载波 (Primary Component Carrier)
      SCC1-3  = 二级载波 (Secondary Component Carriers)
    """

    # --- 系统 ---
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    CLS = "*CLS"
    ERR = "SYSTem:ERRor:ALL?"
    # R&S CMW500 Base Software User Manual 1173.9463.02-06,
    # §6.3.4, printed p.205: SYSTem:ERRor:ALL? returns and deletes the
    # complete error queue; an empty queue is reported as 0,"No error".
    PRESET = "SYSTem:PRESet"
    # R&S CMW500 Base Software User Manual 1173.9463.02-06,
    # §6.3.10.3, printed p.242: SYSTem:BASE:OPTion:LIST? accepts
    # SWOPtion/HWOPtion and VALid/FUNCtional filters. Query only the usable
    # software and hardware sets; an unfiltered list also contains unusable
    # entries and must not authorize an option-gated band.
    OPTION_LIST_VALID_SOFTWARE = (
        "SYSTem:BASE:OPTion:LIST? SWOPtion,VALid"
    )
    OPTION_LIST_FUNCTIONAL_HARDWARE = (
        "SYSTem:BASE:OPTion:LIST? HWOPtion,FUNCtional"
    )

    # --- RF 路由 ---
    # 信令模式单小区, 使用内部 RF 前端
    ROUTE_SIGN = "ROUTe:LTE:SIGN{i}:SCENario:SCELl:FLEXible"
    ROUTE_SIGN_CAFF = "ROUTe:LTE:SIGN{i}:SCENario:CAFF:FLEXible:INTernal"

    # --- 小区配置 (CONFigure:LTE:SIGN) ---
    CELL_BAND = "CONFigure:LTE:SIGN{i}:CELL:BAND"              # e.g., "OB78"
    CELL_DL_FREQ = "CONFigure:LTE:SIGN{i}:RFSettings:CHANnel:DL"  # EARFCN
    CELL_DL_BW = "CONFigure:LTE:SIGN{i}:CELL:BANDwidth:DL"     # 带宽 (MHz)
    CELL_DUPLEX = "CONFigure:LTE:SIGN{i}:CELL:DMOD"             # TDD/FDD
    CELL_PCI = "CONFigure:LTE:SIGN{i}:CELL:PCI"                 # 物理小区 ID

    # --- 下行功率 ---
    DL_POWER_RS = "CONFigure:LTE:SIGN{i}:DL:RSEPre:LEVel"      # RS-EPRE 功率
    DL_POWER_EIRP = "CONFigure:LTE:SIGN{i}:DL:LATTenuation"    # 下行附加衰减

    # --- PDSCH/PUSCH 传输配置 ---
    DL_MCS = "CONFigure:LTE:SIGN{i}:CONNection:PCC:UDCH:DL:MCS"
    DL_RB = "CONFigure:LTE:SIGN{i}:CONNection:PCC:UDCH:DL:NRB"
    DL_RB_POS = "CONFigure:LTE:SIGN{i}:CONNection:PCC:UDCH:DL:RBPStart"
    UL_MCS = "CONFigure:LTE:SIGN{i}:CONNection:PCC:UDCH:UL:MCS"
    UL_RB = "CONFigure:LTE:SIGN{i}:CONNection:PCC:UDCH:UL:NRB"
    UL_RB_POS = "CONFigure:LTE:SIGN{i}:CONNection:PCC:UDCH:UL:RBPStart"

    # --- MIMO ---
    MIMO_MODE = "CONFigure:LTE:SIGN{i}:CONNection:PCC:MIMO"
    TM_MODE = "CONFigure:LTE:SIGN{i}:CONNection:PCC:TMODe"     # TM1-TM10

    # --- FRC / 测试配置 ---
    FRC_STATE = "CONFigure:LTE:SIGN{i}:CONNection:PCC:FRC:STATe"
    FRC_DL = "CONFigure:LTE:SIGN{i}:CONNection:PCC:FRC:DL"
    FRC_UL = "CONFigure:LTE:SIGN{i}:CONNection:PCC:FRC:UL"

    # --- 信令控制 ---
    CELL_STATE_SET = "SOURce:LTE:SIGN{i}:CELL:STATe"          # ON/OFF
    CELL_STATE_QUERY = "SOURce:LTE:SIGN{i}:CELL:STATe?"
    CELL_STATE_ALL = "SOURce:LTE:SIGN{i}:CELL:STATe:ALL?"     # 详细状态

    # PS 数据连接
    # LTE UE User Manual 1173.9628.02-41, §2.6.3.8.1, printed p.372:
    # the documented packet-switched actions are CONNect and DISConnect.
    PS_ACTION = "CALL:LTE:SIGN{i}:PSWitched:ACTion"
    PS_STATE = "FETCh:LTE:SIGN{i}:PSWitched:STATe?"

    # RRC 状态
    RRC_STATE = "SENSe:LTE:SIGN{i}:RRCState?"

    # --- 吞吐量测量 (SENSe 子系统) ---
    ETPUT_DL_ALL = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:DL:ALL?"
    ETPUT_DL_PCC = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:DL:PCC?"
    ETPUT_UL_ALL = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:UL:ALL?"
    ETPUT_UL_PCC = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:UL:PCC?"

    # --- BLER 测量 (FETCh 子系统) ---
    EBLER_PCC = CMW500_LTE_COMMANDS["ebler_absolute_query"].template
    EBLER_RELATIVE_PCC = CMW500_LTE_COMMANDS["ebler_relative_query"].template
    EBLER_CQI = "FETCh:LTE:SIGN{i}:EBLer:PCC:CQIReporting:STReam1?"

    # --- UE 测量上报 (RSRP / SINR) ---
    # CMW500 通过 FETCh 子系统获取 UE 上报的 L3 RSRP 和 SINR
    # 返回格式: "<value>" (dBm / dB)
    UE_RSRP = "SENSe:LTE:SIGN{i}:UEReport:RSRP?"
    UE_SINR = "SENSe:LTE:SIGN{i}:UEReport:SINR?"

    # --- 信令 BLER (Extended BLER) ---
    INIT_EBLER = CMW500_LTE_COMMANDS["ebler_init"].template
    EBLER_REPS = "CONFigure:LTE:SIGN{i}:EBLer:REPetition"
    EBLER_STAT = CMW500_LTE_COMMANDS["ebler_absolute_query"].template

    # --- AWGN (加性白高斯噪声) ---
    AWGN_STATE = "CONFigure:LTE:SIGN{i}:DL:AWGN:STATe"
    AWGN_POWER = "CONFigure:LTE:SIGN{i}:DL:AWGN:POWer"


# VISA 超时常量
VISA_TIMEOUT_DEFAULT = 5000  # ms
VISA_TIMEOUT_CELL = 30000
VISA_TIMEOUT_ATTACH = 120000  # LTE attach 可能需要更长时间

# LTE 频段 → EARFCN 映射
LTE_BAND_EARFCN_MAP = {
    "OB78": 6300,    # TDD Band 42/43 (3.5 GHz)
    "OB3": 1575,     # FDD Band 3 (1800 MHz)
    "OB7": 2850,     # FDD Band 7 (2600 MHz)
    "OB1": 300,      # FDD Band 1 (2100 MHz)
    "OB40": 38950,   # TDD Band 40 (2300 MHz)
    "OB41": 40340,   # TDD Band 41 (2500 MHz)
}


class RealCmw500Driver(BaseStationDriver):
    """
    R&S CMW500 LTE 信令模式真实 SCPI 驱动 (HAL Layer 3)
    ─────────────────────────────────────────────────────
    继承链: InstrumentDriver → BaseStationDriver → RealCmw500Driver

    基于 CMW_LTE_UE_UserManual V4.0.250 实现。
    通过 PyVISA → HiSLIP (推荐) 或 TCP Socket 通信。

    核心工作流:
      1. connect() → 只读识别型号、版本和选件
      2. 执行期显式配置 route 与小区工作点
      3. set_cell_config() → Band/BW/DL Freq
      4. set_downlink_power() → RS-EPRE 功率
      5. start_signaling() → Cell ON → PS Establish → 等待连接
      6. get_throughput_metrics() → 诊断回读（正式窗口由独立方法负责）
      7. stop_signaling() → PS Release → Cell OFF
    """

    adapter_id = "cmw500"
    max_bandwidth_mhz = 20.0
    max_mimo_layers = 4
    # User Manual §2.6.12.1, p.680: <Bandwidth> is exactly
    # B014/B030/B050/B100/B150/B200 for 1.4/3/5/10/15/20 MHz.
    bandwidth_token_by_mhz = {
        1.4: "B014",
        3.0: "B030",
        5.0: "B050",
        10.0: "B100",
        15.0: "B150",
        20.0: "B200",
    }
    supported_bandwidths_mhz = frozenset(bandwidth_token_by_mhz)
    supported_mimo_layers = frozenset({1, 2, 4})

    def evaluate_lte_2x2_formal_capability(
        self,
        frozen_adapter: dict[str, Any],
        *,
        duplex: str,
        config_mode: str = "dispatch",
    ) -> Cmw500FormalCapabilityDecision:
        """Evaluate only a frozen approval and this read-only session snapshot.

        Option semantics: R&S CMW500 LTE UE User Manual 1173.9628.02-41,
        §2.2.1, printed pp.17-19: LTE FDD signaling uses KS500, LTE TDD
        signaling uses KS550, and LTE MIMO signaling requires KS520.
        """

        if config_mode == "inherit":
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="diagnostic",
                reason="inherit is diagnostic-only and cannot grant formal acceptance",
            )
        if config_mode != "dispatch":
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="base-station configuration mode is invalid",
            )
        resolution = frozen_adapter.get("resolution")
        approval = frozen_adapter.get("cmw500_lte_2x2_formal_capability")
        if not isinstance(resolution, dict) or not isinstance(approval, dict):
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="execution-frozen CMW500 approval is missing",
            )
        if (
            resolution.get("adapter") != "cmw500"
            or resolution.get("status") != "configured"
            or resolution.get("execution_mode") != "real"
        ):
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="execution-frozen CMW500 real adapter is not configured",
            )
        if approval.get("enabled") is not True:
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="disabled",
                reason="CMW500 LTE 2x2 formal capability is not explicitly enabled",
            )
        if (
            approval.get("schema_version") != 1
            or not isinstance(approval.get("instrument_connection_id"), str)
            or not approval.get("instrument_connection_id")
            or approval.get("instrument_connection_id")
            != frozen_adapter.get("instrument_connection_id")
            or not isinstance(approval.get("updated_at"), str)
            or not approval.get("updated_at")
        ):
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="execution-frozen CMW500 approval is malformed",
            )
        normalized_duplex = duplex.strip().lower() if isinstance(duplex, str) else ""
        if normalized_duplex not in {"fdd", "tdd"}:
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="LTE duplex is missing or invalid",
            )
        if not self.identity_snapshot_verified or self._identity_model != "CMW":
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="CMW500 model, firmware, or option snapshot is unverified",
            )
        if not self._firmware_at_least(self._firmware_version, "3.5.40"):
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason="CMW500 firmware does not satisfy the LTE 2x2 minimum",
            )
        installed = {option.strip().upper() for option in self._installed_options}
        duplex_option = "CMW-KS500" if normalized_duplex == "fdd" else "CMW-KS550"
        missing = sorted({"CMW-KS520", duplex_option} - installed)
        if missing:
            return Cmw500FormalCapabilityDecision(
                ready=False,
                status="unknown",
                reason=f"CMW500 LTE 2x2 options are missing: {', '.join(missing)}",
            )
        return Cmw500FormalCapabilityDecision(
            ready=True,
            status="ready",
            reason="CMW500 LTE 2x2 formal capability is explicitly admitted",
        )

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        # 连接参数
        (
            self.ip_address,
            configured_port,
            self.visa_resource,
            self._connection_config_error,
        ) = resolve_configured_tcpip_connection(config)
        self.port: int = configured_port if configured_port is not None else 5025
        # VISA session
        self._visa_rm = None
        self._visa_session = None
        self._session_token: str | None = None
        # CMW 信令通道编号 (默认 1)
        self._sign_channel: int = config.get("sign_channel", 1)
        # 小区配置状态
        self._band: str = "OB3"
        self._earfcn: int = 1575
        self._frequency_mhz: float = 1842.5
        self._bandwidth_mhz: float = 20.0
        self._dl_power_dbm: float = -50.0
        self._cell_state: CellState = CellState.OFF
        self._identity_model: str = ""
        self._firmware_version: str | None = None
        self._identity_model_verified = False
        self._options_snapshot_verified = False

    @property
    def _i(self) -> str:
        """格式化的信令通道编号"""
        return str(self._sign_channel)

    def _fmt(self, template: str) -> str:
        """将命令模板中的 {i} 替换为通道编号"""
        return template.format(i=self._i)

    @staticmethod
    def _error_queue_is_empty(response: str) -> bool:
        return re.fullmatch(r'\+?0\s*,\s*"[^"]*"', response.strip()) is not None

    def _write_group_confirmed(self) -> bool:
        """Confirm completion and independently reject any device error."""

        if self._query(CmwScpiCommands.OPC).strip() != "1":
            return False
        return self._error_queue_is_empty(self._query(CmwScpiCommands.ERR))

    @staticmethod
    def _parse_cell_all(response: str) -> tuple[str, str] | None:
        # LTE UE User Manual 1173.9628.02-41, §2.6.3.8.1, printed p.371:
        # CELL:STATe:ALL? returns MainState OFF/ON/RFHandover and
        # SyncState PENDing/ADJusted. Accept only their exact SCPI forms.
        fields = [field.strip().upper() for field in response.split(",")]
        if len(fields) != 2:
            return None
        main_aliases = {
            "OFF": "OFF",
            "ON": "ON",
            "RFH": "RFHANDOVER",
            "RFHANDOVER": "RFHANDOVER",
        }
        sync_aliases = {
            "PEND": "PENDING",
            "PENDING": "PENDING",
            "ADJ": "ADJUSTED",
            "ADJUSTED": "ADJUSTED",
        }
        main = main_aliases.get(fields[0])
        sync = sync_aliases.get(fields[1])
        return (main, sync) if main is not None and sync is not None else None

    @staticmethod
    def _parse_ps_state(response: str) -> str | None:
        # LTE UE User Manual 1173.9628.02-41, §2.6.3.8.1, printed p.374:
        # FETCh:...:PSWitched:STATe? has a closed enum. In particular ATTached
        # and CESTablished are different states and must never be substring-matched.
        aliases = {
            "OFF": "OFF",
            "ON": "ON",
            "ATT": "ATTACHED",
            "ATTACHED": "ATTACHED",
            "CEST": "CONNECTED",
            "CESTABLISHED": "CONNECTED",
            "DISC": "DISCONNECT",
            "DISCONNECT": "DISCONNECT",
            "CONN": "CONNECTING",
            "CONNECTING": "CONNECTING",
            "SIGN": "SIGNALING",
            "SIGNALING": "SIGNALING",
            "SMES": "SMS_SEND",
            "SMESSAGE": "SMS_SEND",
            "RMES": "SMS_RECEIVE",
            "RMESSAGE": "SMS_RECEIVE",
            "IHAN": "IN_HANDOVER",
            "IHANDOVER": "IN_HANDOVER",
            "OHAN": "OUT_HANDOVER",
            "OHANDOVER": "OUT_HANDOVER",
        }
        return aliases.get(response.strip().upper())

    async def ensure_safe_idle(self) -> bool:
        """Confirm Cell OFF before any configuration or internal-route write."""

        try:
            state = self._parse_cell_all(
                self._query(self._fmt(CmwScpiCommands.CELL_STATE_ALL))
            )
            if state == ("OFF", "ADJUSTED"):
                self._cell_state = CellState.OFF
                return True
            if state is None or state[0] not in {"ON", "RFHANDOVER"}:
                return False
            self._write(self._fmt(CmwScpiCommands.CELL_STATE_SET) + " OFF")
            if not self._write_group_confirmed():
                return False
            confirmed = self._parse_cell_all(
                self._query(self._fmt(CmwScpiCommands.CELL_STATE_ALL))
            )
            if confirmed != ("OFF", "ADJUSTED"):
                return False
            self._cell_state = CellState.OFF
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[CMW500] SAFE_IDLE confirmation failed: %s", exc)
            return False

    @staticmethod
    def _firmware_at_least(actual: str | None, required: str) -> bool:
        def _parts(value: str | None) -> tuple[int, ...] | None:
            token = (value or "").removeprefix("V")
            if not re.fullmatch(r"\d+(?:\.\d+)+", token):
                return None
            return tuple(int(part) for part in token.split("."))

        actual_parts = _parts(actual)
        required_parts = _parts(required)
        if actual_parts is None or required_parts is None:
            return False
        width = max(len(actual_parts), len(required_parts))
        return actual_parts + (0,) * (width - len(actual_parts)) >= (
            required_parts + (0,) * (width - len(required_parts))
        )

    async def apply_internal_lte_2x2_route(
        self,
        frozen_adapter: dict[str, Any],
    ) -> BaseStationRouteResult:
        """Apply only the execution-frozen internal route and confirm readback."""

        spec = CMW500_LTE_COMMANDS["route_nx2"]

        def _result(
            *,
            requested: dict[str, str] | None = None,
            applied: dict[str, str] | None = None,
            confirmed: bool = False,
            reason: str,
            exchanges=(),
        ) -> BaseStationRouteResult:
            return BaseStationRouteResult(
                requested=requested,
                applied=applied,
                source_reference=spec.source_reference,
                confirmed=confirmed,
                reason=reason,
                exchange_ids=[exchange.exchange_id for exchange in exchanges],
            )

        resolution = frozen_adapter.get("resolution")
        if not isinstance(resolution, dict):
            return _result(reason="execution-frozen adapter resolution is missing")
        if (
            resolution.get("adapter") != "cmw500"
            or resolution.get("status") != "configured"
            or resolution.get("execution_mode") != "real"
        ):
            return _result(reason="execution-frozen CMW500 real route is not configured")
        raw_profile = resolution.get("profile")
        raw_route = (
            raw_profile.get("lte_2x2_internal_route")
            if isinstance(raw_profile, dict)
            else None
        )
        if not isinstance(raw_route, dict):
            return _result(reason="execution-frozen CMW500 route is missing")
        if raw_route.get("tx1_connector") == raw_route.get("tx2_connector"):
            return _result(reason="CMW500 TX connector paths must be distinct")
        if raw_route.get("tx1_converter") == raw_route.get("tx2_converter"):
            return _result(reason="CMW500 TX converter paths must be distinct")
        try:
            profile = BaseStationAdapterProfile.model_validate(raw_profile)
        except ValueError as exc:
            return _result(reason=f"invalid execution-frozen CMW500 route: {exc}")
        route = CmwNx2Route(**profile.lte_2x2_internal_route.model_dump())
        requested = asdict(route)

        if not self._firmware_at_least(
            self._firmware_version,
            spec.minimum_firmware or "",
        ):
            return _result(
                requested=requested,
                reason=(
                    "CMW500 firmware does not satisfy route minimum "
                    f"{spec.minimum_firmware}"
                ),
            )
        installed = {option.upper() for option in self._installed_options}
        missing_options = [
            option for option in spec.required_options if option.upper() not in installed
        ]
        if missing_options:
            return _result(
                requested=requested,
                reason=f"CMW500 route requires {', '.join(missing_options)}",
            )

        if not await self.ensure_safe_idle():
            return _result(
                requested=requested,
                reason="CMW500 SAFE_IDLE is not confirmed before route apply",
            )

        with capture_scpi_exchanges() as exchanges:
            try:
                self._write(
                    Cmw500LteCommandProfile.build_route_nx2(
                        self._sign_channel,
                        route,
                    )
                )
                queue_result = self._query(CmwScpiCommands.ERR).strip()
                if re.fullmatch(r'\+?0\s*,\s*"[^"]*"', queue_result) is None:
                    return _result(
                        requested=requested,
                        reason=f"CMW500 error queue rejected route: {queue_result}",
                        exchanges=exchanges,
                    )
                readback = Cmw500LteCommandProfile.parse_route_readback(
                    self._query(
                        Cmw500LteCommandProfile.route_query(self._sign_channel)
                    )
                )
            except Exception as exc:
                return _result(
                    requested=requested,
                    reason=f"CMW500 route apply/readback failed: {exc}",
                    exchanges=exchanges,
                )

            applied = {
                "pcc_bb_board": readback.controller,
                "rx_connector": readback.rx_connector,
                "rx_converter": readback.rx_converter,
                "tx1_connector": readback.tx1_connector,
                "tx1_converter": readback.tx1_converter,
                "tx2_connector": readback.tx2_connector,
                "tx2_converter": readback.tx2_converter,
            }
            if applied != requested:
                return _result(
                    requested=requested,
                    applied=applied,
                    reason="CMW500 route readback does not match requested route",
                    exchanges=exchanges,
                )
            return _result(
                requested=requested,
                applied=applied,
                confirmed=True,
                reason="CMW500 internal LTE 2x2 route confirmed",
                exchanges=exchanges,
            )

    async def apply_requested_config(
        self, requested: BaseStationRequestedConfig,
    ) -> bool:
        """Reject lossy CMW translations and unverified option-gated bands."""

        if requested.radio_technology == "lte":
            if requested.bandwidth_mhz not in self.supported_bandwidths_mhz:
                logger.error(
                    "[CMW500] Rejecting unsupported exact LTE bandwidth %.3f MHz",
                    requested.bandwidth_mhz,
                )
                return False
            if requested.mimo_layers not in self.supported_mimo_layers:
                logger.error(
                    "[CMW500] Rejecting unsupported exact MIMO layer count %d",
                    requested.mimo_layers,
                )
                return False
            try:
                validate_lte_band_options(requested.band, self._installed_options)
            except ValueError as exc:
                logger.error("[CMW500] Rejecting LTE band options: %s", exc)
                return False
        return await super().apply_requested_config(requested)

    # ===================================================================
    # 1. 连接生命周期
    # ===================================================================

    async def _probe_installed_options(self) -> List[str]:
        """Read the CMW-specific usable option snapshot, fail-closed."""

        self._options_snapshot_verified = False
        try:
            software = self._parse_options_response(
                self._query(CmwScpiCommands.OPTION_LIST_VALID_SOFTWARE)
            )
            hardware = self._parse_options_response(
                self._query(CmwScpiCommands.OPTION_LIST_FUNCTIONAL_HARDWARE)
            )
        except Exception as exc:
            logger.warning("[CMW500] Option snapshot unavailable: %s", exc)
            self._installed_options = []
            return []

        self._installed_options = software + hardware
        self._options_snapshot_verified = True
        logger.info(
            "[CMW500] Installed usable options: %s",
            self._installed_options or "(none)",
        )
        return self._installed_options

    @staticmethod
    def _parse_identity_response(idn: str) -> tuple[str, str | None]:
        """Parse the four-field *IDN? form shown in Base Software manual p.119."""

        fields = [field.strip() for field in idn.split(",")]
        if len(fields) != 4:
            raise ValueError("CMW *IDN? response must contain four fields")
        vendor, model, _serial, version = fields
        if vendor.casefold() != "rohde&schwarz" or model.upper() != "CMW":
            raise ValueError(f"connected instrument is not an R&S CMW: {idn}")
        parsed_version = (
            version
            if re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version)
            else None
        )
        return model.upper(), parsed_version

    @property
    def identity_snapshot_verified(self) -> bool:
        """Only a verified model, version, and complete option query authorize use."""

        return (
            self._identity_model_verified
            and self._firmware_version is not None
            and self._options_snapshot_verified
        )

    def get_base_station_identity(self) -> BaseStationIdentity:
        return BaseStationIdentity(
            adapter_id="cmw500",
            model=self._identity_model,
            firmware_version=self._firmware_version,
            options=tuple(self._installed_options),
        )

    def _close_failed_connect_session(self) -> None:
        """Close only this driver's session after a failed connection attempt."""

        if self._visa_session is not None:
            try:
                self._visa_session.close()
            except Exception as exc:
                logger.warning("[CMW500] Failed to close rejected session: %s", exc)
            self._visa_session = None
        self._visa_rm = None

    async def connect(self) -> bool:
        """通过 PyVISA 建立与 CMW500 的连接"""
        session_present = self._visa_session is not None
        token_present = self._session_token is not None
        if session_present and token_present:
            return True
        if session_present != token_present:
            logger.error(
                "[CMW500] Refusing connect with incomplete transport/session identity"
            )
            return False
        if self._connection_config_error:
            return self._fail_connection_configuration(self._connection_config_error)
        if not self.ip_address:
            return self._fail_missing_connection_address()
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()

            if self.visa_resource:
                resource_str = self.visa_resource
            else:
                # CMW500 推荐 HiSLIP (端口 4880)
                resource_str = (
                    f"TCPIP::{self.ip_address}::hislip0::INSTR"
                )

            logger.info(f"[CMW500] Connecting: {resource_str}")
            self._visa_session = self._visa_rm.open_resource(
                resource_str,
                timeout=VISA_TIMEOUT_DEFAULT,
            )

            # Base Software User Manual 1173.9463.02-06, §5.1.2,
            # printed p.119 gives the exact four-field *IDN? example.
            idn = self._query("*IDN?").strip()
            logger.info(f"[CMW500] Connected: {idn}")
            self._identity_model, self._firmware_version = (
                self._parse_identity_response(idn)
            )
            self._identity_model_verified = True

            await self._probe_installed_options()

            # Server-owned identity for exactly this newly opened transport.
            # It is intentionally unrelated to resource strings or object shape.
            self._session_token = uuid4().hex

            self._set_status(InstrumentStatus.CONNECTED)
            self._clear_error()
            return True

        except Exception as e:
            self._session_token = None
            self._identity_model_verified = False
            self._options_snapshot_verified = False
            self._installed_options = []
            self._close_failed_connect_session()
            error_msg = f"[CMW500] Connection failed: {e}"
            logger.error(error_msg)
            self._set_status(InstrumentStatus.ERROR, error_msg)
            return False

    async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
        """Return the opaque identity of the currently active real transport.

        The CMW manuals available to this project do not define a front-panel
        Remote confirmation command, so this confirms transport ownership only.
        """

        warnings: list[str] = []
        session_present = self._visa_session is not None
        token_present = self._session_token is not None
        if session_present != token_present:
            return BaseStationRemoteSessionResult(
                adapter_id="cmw500",
                session_token=self._session_token or "",
                acquired_confirmed=False,
                warnings=(
                    "CMW500 transport/session token identity is incomplete; reconnect refused",
                ),
            )
        if not session_present:
            connected = await self.connect()
            if not connected:
                return BaseStationRemoteSessionResult(
                    adapter_id="cmw500",
                    session_token="",
                    acquired_confirmed=False,
                    warnings=("CMW500 transport session was not acquired",),
                )
        warnings.append(
            "CMW500 transport session acquired; front-panel Remote is unconfirmed"
        )
        return BaseStationRemoteSessionResult(
            adapter_id="cmw500",
            session_token=self._session_token or "",
            acquired_confirmed=bool(self._visa_session and self._session_token),
            warnings=tuple(warnings),
        )

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        """Close the active transport without claiming front-panel Local."""

        current_session = self._visa_session
        current_token = self._session_token or ""
        token_matches = bool(
            current_session
            and current_token
            and expected_session_token == current_token
        )
        warnings: list[str] = []
        close_confirmed = False
        if not token_matches:
            warnings.append("CMW500 session token missing or mismatched")
        if current_session is None:
            warnings.append("CMW500 transport session is missing")
        else:
            try:
                current_session.close()
                close_confirmed = True
                self._visa_session = None
                self._visa_rm = None
                self._session_token = None
                self._set_status(InstrumentStatus.DISCONNECTED)
            except Exception as exc:
                warnings.append(f"CMW500 transport close failed: {exc}")
        warnings.append(
            "CMW500 front-panel Local state has no documented confirmation and remains unknown"
        )
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id="cmw500",
            session_token=current_token,
            remote_session_acquired_confirmed=token_matches,
            transport_session_released_confirmed=token_matches and close_confirmed,
            front_panel_local_confirmed=None,
            warnings=tuple(warnings),
        )

    async def disconnect(self) -> bool:
        """断开 VISA 连接"""
        try:
            cleanup_confirmed = True
            if self._visa_session is not None:
                cleanup_confirmed = await self.ensure_safe_idle() is True

            if self._visa_session:
                self._visa_session.close()
                self._visa_session = None
            self._session_token = None
            # ⚠ **不调** `self._visa_rm.close()`: RM 是**进程级共享单例**, 关它会连带
            # 关掉其它仪表的会话 (权威说明见 `app/hal/_visa_reconnect.py` 的
            # 「ResourceManager 所有权」一节)。自己的 session 上面已经关了, 这里只丢引用。
            self._visa_rm = None

            self._set_status(InstrumentStatus.DISCONNECTED)
            logger.info("[CMW500] Disconnected")
            if not cleanup_confirmed:
                logger.error(
                    "[CMW500] Transport closed, but signaling SAFE cleanup was unconfirmed"
                )
            return cleanup_confirmed
        except Exception as e:
            logger.error(f"[CMW500] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        return await self.set_cell_config(config)

    # ===================================================================
    # 2. 小区配置
    # ===================================================================

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置 CMW500 LTE 物理小区参数。

        SCPI 序列:
          CONFigure:LTE:SIGN1:CELL:BAND OB3
          CONFigure:LTE:SIGN1:CELL:BANDwidth:DL B200
          CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL 1575
          CONFigure:LTE:SIGN1:CELL:DMOD FDD
        """
        try:
            band = self._band
            if "band" in config:
                band = str(config["band"]).upper()
                if band.startswith("B"):
                    band = f"O{band}"
                elif not band.startswith("OB"):
                    band = f"OB{band}"
            bandwidth_mhz = self._bandwidth_mhz
            bandwidth_token = None
            if "bandwidth_mhz" in config:
                bandwidth_mhz = float(config["bandwidth_mhz"])
                bandwidth_token = self.bandwidth_token_by_mhz[bandwidth_mhz]
            if "earfcn" in config:
                earfcn = int(config["earfcn"])
            elif "arfcn" in config:
                earfcn = int(config["arfcn"])
            else:
                earfcn = LTE_BAND_EARFCN_MAP.get(band, 1575)
            frequency_mhz = float(
                config.get("frequency_mhz", self._frequency_mhz)
            )

            if not await self.ensure_safe_idle():
                logger.error("[CMW500] Cell config blocked: SAFE_IDLE unconfirmed")
                return False

            if "band" in config:
                self._write(self._fmt(CmwScpiCommands.CELL_BAND) + f" {band}")

            # User Manual §2.6.12.1, p.680: PCC DL bandwidth also applies
            # to UL; there is no separate PCC CELL:BANDwidth:UL write.
            if bandwidth_token is not None:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_DL_BW)
                    + f" {bandwidth_token}"
                )

            if "duplex" in config:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_DUPLEX)
                    + f" {config['duplex'].upper()}"
                )

            self._write(
                self._fmt(CmwScpiCommands.CELL_DL_FREQ) + f" {earfcn}"
            )

            # 物理小区 ID
            if "cell_id" in config:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_PCI)
                    + f" {config['cell_id']}"
                )

            # MIMO 模式 (TM1-TM10)
            if "tm_mode" in config:
                self._write(
                    self._fmt(CmwScpiCommands.TM_MODE)
                    + f" {config['tm_mode']}"
                )
            if "mimo_layers" in config:
                layers = config["mimo_layers"]
                mimo_map = {1: "TX1", 2: "TX2", 4: "TX4"}
                mimo_str = mimo_map.get(layers, "TX2")
                self._write(
                    self._fmt(CmwScpiCommands.MIMO_MODE)
                    + f" {mimo_str}"
                )

            if not self._write_group_confirmed():
                logger.error("[CMW500] Cell config rejected by completion/error check")
                return False

            self._band = band
            self._bandwidth_mhz = bandwidth_mhz
            self._earfcn = earfcn
            self._frequency_mhz = frequency_mhz
            self._set_status(InstrumentStatus.READY)
            logger.info(
                f"[CMW500] Cell config: band={self._band}, "
                f"BW={self._bandwidth_mhz}MHz, EARFCN={self._earfcn}"
            )
            return True

        except Exception as e:
            logger.error(f"[CMW500] set_cell_config failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def set_frc_config(
        self,
        frc_reference: str,
        modulation: Optional[str] = None,
        target_coding_rate: Optional[float] = None,
    ) -> bool:
        """
        配置 CMW500 FRC (固定参考信道)。

        SCPI:
          CONFigure:LTE:SIGN1:CONNection:PCC:FRC:STATe ON
          CONFigure:LTE:SIGN1:CONNection:PCC:FRC:DL R0    (e.g., "R.0")
        """
        try:
            if not await self.ensure_safe_idle():
                return False
            # 开启 FRC 模式
            self._write(
                self._fmt(CmwScpiCommands.FRC_STATE) + " ON"
            )

            # 设置 DL FRC 参考
            # CMW 使用如 "R0", "R31" 等格式
            dl_frc = frc_reference.replace(".", "")  # "R.0" → "R0"
            self._write(
                self._fmt(CmwScpiCommands.FRC_DL) + f" {dl_frc}"
            )

            if not self._write_group_confirmed():
                return False
            logger.info(f"[CMW500] FRC config: {frc_reference}")
            return True

        except Exception as e:
            logger.error(f"[CMW500] set_frc_config failed: {e}")
            return False

    async def set_downlink_power(self, power_dbm: float) -> bool:
        """
        设置 CMW500 下行发射功率 (RS-EPRE)。

        SCPI: CONFigure:LTE:SIGN1:DL:RSEPre:LEVel <power_dbm>
        """
        try:
            if not await self.ensure_safe_idle():
                return False
            self._write(
                self._fmt(CmwScpiCommands.DL_POWER_RS)
                + f" {power_dbm:.1f}"
            )
            if not self._write_group_confirmed():
                return False
            self._dl_power_dbm = power_dbm
            logger.info(f"[CMW500] DL RS-EPRE power: {power_dbm} dBm")
            return True
        except Exception as e:
            logger.error(f"[CMW500] set_downlink_power failed: {e}")
            return False

    # ===================================================================
    # 3. 信令控制
    # ===================================================================

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        """
        激活小区、等待 UE Attach 并建立 PS 数据连接。

        SCPI 序列引用 LTE UE User Manual 1173.9628.02-41：
          printed p.371 CELL ON/OFF 与 CELL:STATe:ALL?；
          printed p.372 PSWitched:ACTion CONNect；
          printed p.374 PSWitched:STATe? 的 ATTached/CESTablished 枚举。
        """
        old_timeout = None
        cell_on_attempted = False
        signaling_confirmed = False
        try:
            if self._visa_session is None:
                return False
            logger.info("[CMW500] Starting LTE signaling")
            self._set_status(InstrumentStatus.BUSY)

            old_timeout = self._visa_session.timeout
            self._visa_session.timeout = VISA_TIMEOUT_CELL

            cell_on_attempted = True
            self._write(self._fmt(CmwScpiCommands.CELL_STATE_SET) + " ON")
            if not self._write_group_confirmed():
                return False
            cell_elapsed = 0.0
            while cell_elapsed <= timeout_s:
                cell = self._parse_cell_all(
                    self._query(self._fmt(CmwScpiCommands.CELL_STATE_ALL))
                )
                if cell == ("ON", "ADJUSTED"):
                    break
                if cell != ("ON", "PENDING") or cell_elapsed >= timeout_s:
                    return False
                wait_s = min(3.0, timeout_s - cell_elapsed)
                await asyncio.sleep(wait_s)
                cell_elapsed += wait_s
            else:
                return False
            self._cell_state = CellState.IDLE
            logger.info("[CMW500] Cell ON, waiting for UE attach...")

            self._visa_session.timeout = VISA_TIMEOUT_ATTACH
            elapsed = 0.0
            poll_interval = 3.0
            attached = False

            while elapsed < timeout_s:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                ps_state = self._parse_ps_state(
                    self._query(self._fmt(CmwScpiCommands.PS_STATE))
                )
                if ps_state == "ATTACHED":
                    attached = True
                    logger.info("[CMW500] UE attached after %.1fs", elapsed)
                    break
                if ps_state is None:
                    logger.warning("[CMW500] Unknown PS state while attaching")
                    return False

            if attached:
                self._write(
                    self._fmt(CmwScpiCommands.PS_ACTION) + " CONNect"
                )
                if not self._error_queue_is_empty(
                    self._query(CmwScpiCommands.ERR)
                ):
                    return False

                connection_elapsed = 0.0
                while connection_elapsed <= timeout_s:
                    ps_state = self._parse_ps_state(
                        self._query(self._fmt(CmwScpiCommands.PS_STATE))
                    )
                    if ps_state == "CONNECTED":
                        self._cell_state = CellState.CONNECTED
                        signaling_confirmed = True
                        logger.info("[CMW500] PS connection established")
                        break
                    # LTE UE User Manual 1173.9628.02-41, §2.2.9.1
                    # printed p.39-40 and §2.6.3.1 printed p.374 define
                    # CONNecting / SIGNaling as transitory PS states.  Poll
                    # them within a finite window without repeating CONNect.
                    if ps_state not in {"CONNECTING", "SIGNALING"}:
                        logger.warning(
                            "[CMW500] PS connection not confirmed: %s", ps_state
                        )
                        break
                    if connection_elapsed >= timeout_s:
                        logger.warning(
                            "[CMW500] PS connection timeout after %.1fs", timeout_s
                        )
                        break
                    wait_s = min(poll_interval, timeout_s - connection_elapsed)
                    await asyncio.sleep(wait_s)
                    connection_elapsed += wait_s
                if not signaling_confirmed:
                    self._cell_state = CellState.IDLE
            else:
                logger.warning(
                    f"[CMW500] UE attach timeout after {timeout_s}s"
                )
                self._cell_state = CellState.IDLE
            return signaling_confirmed

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[CMW500] start_signaling failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False
        finally:
            if cell_on_attempted and not signaling_confirmed:
                cleanup_confirmed = await asyncio.shield(self.stop_signaling())
                if not cleanup_confirmed:
                    logger.error(
                        "[CMW500] start_signaling failed and SAFE cleanup was not confirmed"
                    )
            if self._visa_session is not None and old_timeout is not None:
                self._visa_session.timeout = old_timeout

    async def stop_signaling(self) -> bool:
        """
        释放 PS 连接并关闭小区。

        SCPI 引用 LTE UE User Manual 1173.9628.02-41 printed p.371-374：
          CALL:...:PSWitched:ACTion DISConnect；Cell OFF 后精确回读 OFF,ADJ。
        """
        failures: list[str] = []
        if self._visa_session is None:
            return False
        if self._cell_state == CellState.CONNECTED:
            try:
                self._write(
                    self._fmt(CmwScpiCommands.PS_ACTION) + " DISConnect"
                )
                if not self._error_queue_is_empty(self._query(CmwScpiCommands.ERR)):
                    failures.append("PS disconnect error queue is not empty")
            except Exception as exc:
                failures.append(f"PS disconnect failed: {exc}")
        try:
            self._write(self._fmt(CmwScpiCommands.CELL_STATE_SET) + " OFF")
            if not self._write_group_confirmed():
                failures.append("Cell OFF completion/error confirmation failed")
            elif self._parse_cell_all(
                self._query(self._fmt(CmwScpiCommands.CELL_STATE_ALL))
            ) != ("OFF", "ADJUSTED"):
                failures.append("Cell OFF readback is not confirmed")
            else:
                self._cell_state = CellState.OFF
        except Exception as exc:
            failures.append(f"Cell OFF failed: {exc}")
        if failures:
            logger.error("[CMW500] stop_signaling failures: %s", "; ".join(failures))
            return False
        self._set_status(InstrumentStatus.READY)
        logger.info("[CMW500] Signaling stopped")
        return True

    async def get_cell_state(self) -> CellState:
        """查询小区当前状态"""
        try:
            state = self._parse_cell_all(
                self._query(self._fmt(CmwScpiCommands.CELL_STATE_ALL))
            )
            if state == ("OFF", "ADJUSTED"):
                return CellState.OFF
            if state == ("ON", "ADJUSTED"):
                ps = self._parse_ps_state(
                    self._query(self._fmt(CmwScpiCommands.PS_STATE))
                )
                if ps == "CONNECTED":
                    return CellState.CONNECTED
                return CellState.IDLE
            return CellState.ERROR
        except Exception as exc:
            logger.warning("[CMW500] Cell state query failed: %s", exc)
            return CellState.ERROR

    # ===================================================================
    # 4. 吞吐量与 BLER 测量
    # ===================================================================

    async def measure_base_station_window(
        self,
        window_s: float,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> BaseStationMeasurementWindow:
        """采集同一 Extended BLER 生命周期内的 DL throughput 与 BLER。

        生命周期与命令取自 R&S CMW LTE UE User Manual 1173.9628.02-41：
        §3.4.2 printed p.950-951（ABORT/OFF、INIT/RUN、STOP/RDY）以及
        §3.4.4 printed p.957-959（Absolute/Relative 字段与单位）。
        """

        if throughput_scope != ThroughputMetrics.SCOPE_PCELL:
            raise ValueError("CMW500 Extended BLER window supports pcell scope only")

        started_at = datetime.now(timezone.utc)
        window_id = uuid4().hex
        preclear_off_confirmed = False
        window_configuration_confirmed = False
        running_confirmed = False
        ready_confirmed = False
        closed_off_confirmed = False
        stop_attempted = False
        ended_before_stop = False
        lifecycle_failures: list[str] = []
        metric_failures: list[str] = []
        absolute_raw: str | None = None
        relative_raw: str | None = None
        throughput_mbps: float | None = None
        bler_percent: float | None = None
        cancelled: asyncio.CancelledError | None = None

        def _write_and_confirm_state(
            command: str,
            expected_state: str,
            label: str,
        ) -> bool:
            try:
                self._write(command)
                if not self._write_group_confirmed():
                    lifecycle_failures.append(
                        f"{label}: completion/error confirmation failed"
                    )
                    return False
                state = Cmw500LteCommandProfile.parse_ebler_state(
                    self._query(
                        Cmw500LteCommandProfile.ebler_state_query(
                            self._sign_channel
                        )
                    )
                )
                if state != expected_state:
                    lifecycle_failures.append(
                        f"{label}: expected {expected_state}, got {state}"
                    )
                    return False
                return True
            except Exception as exc:
                lifecycle_failures.append(f"{label}: {exc}")
                return False

        def _write_and_confirm(command: str, label: str) -> bool:
            try:
                self._write(command)
                if not self._write_group_confirmed():
                    lifecycle_failures.append(
                        f"{label}: completion/error confirmation failed"
                    )
                    return False
                return True
            except Exception as exc:
                lifecycle_failures.append(f"{label}: {exc}")
                return False

        with capture_scpi_exchanges() as exchanges:
            try:
                preclear_off_confirmed = _write_and_confirm_state(
                    Cmw500LteCommandProfile.ebler_abort(self._sign_channel),
                    "OFF",
                    "pre-clear ABORT/OFF",
                )
                if preclear_off_confirmed:
                    window_configuration_confirmed = all(
                        _write_and_confirm(command, label)
                        for command, label in (
                            (
                                Cmw500LteCommandProfile.ebler_timeout_disabled(
                                    self._sign_channel
                                ),
                                "continuous window timeout",
                            ),
                            (
                                Cmw500LteCommandProfile.ebler_repetition_continuous(
                                    self._sign_channel
                                ),
                                "continuous window repetition",
                            ),
                            (
                                Cmw500LteCommandProfile.ebler_stop_condition_none(
                                    self._sign_channel
                                ),
                                "continuous window stop condition",
                            ),
                        )
                    )
                if window_configuration_confirmed:
                    running_confirmed = _write_and_confirm_state(
                        Cmw500LteCommandProfile.ebler_init(self._sign_channel),
                        "RUN",
                        "INIT/RUN",
                    )
                if running_confirmed:
                    await asyncio.sleep(max(float(window_s), 0.0))
                    try:
                        state = Cmw500LteCommandProfile.parse_ebler_state(
                            self._query(
                                Cmw500LteCommandProfile.ebler_state_query(
                                    self._sign_channel
                                )
                            )
                        )
                    except Exception as exc:
                        lifecycle_failures.append(f"window state: {exc}")
                    else:
                        if state == "RUN":
                            stop_attempted = True
                            ready_confirmed = _write_and_confirm_state(
                                Cmw500LteCommandProfile.ebler_stop(
                                    self._sign_channel
                                ),
                                "RDY",
                                "STOP/RDY",
                            )
                        elif state == "RDY":
                            ended_before_stop = True
                            lifecycle_failures.append(
                                "window state: continuous measurement ended before requested STOP"
                            )
                        else:
                            lifecycle_failures.append(
                                f"window state: expected RUN or RDY, got {state}"
                            )

                if ready_confirmed:
                    try:
                        absolute_raw = self._query(
                            Cmw500LteCommandProfile.ebler_absolute_query(
                                self._sign_channel
                            )
                        )
                        absolute = Cmw500LteCommandProfile.parse_ebler_absolute(
                            absolute_raw
                        )
                        throughput_mbps = (
                            absolute.throughput_average_kbit_per_s / 1000.0
                        )
                    except Exception as exc:
                        metric_failures.append(f"DL throughput unavailable: {exc}")
                    try:
                        relative_raw = self._query(
                            Cmw500LteCommandProfile.ebler_relative_query(
                                self._sign_channel
                            )
                        )
                        relative = Cmw500LteCommandProfile.parse_ebler_relative(
                            relative_raw
                        )
                        bler_percent = relative.bler_percent
                    except Exception as exc:
                        metric_failures.append(f"DL BLER unavailable: {exc}")
            except asyncio.CancelledError as exc:
                cancelled = exc
                lifecycle_failures.append("measurement window cancelled")
            except Exception as exc:
                lifecycle_failures.append(f"measurement window failed: {exc}")
            finally:
                if (
                    running_confirmed
                    and not ready_confirmed
                    and not stop_attempted
                    and not ended_before_stop
                ):
                    stop_attempted = True
                    ready_confirmed = _write_and_confirm_state(
                        Cmw500LteCommandProfile.ebler_stop(self._sign_channel),
                        "RDY",
                        "cleanup STOP/RDY",
                    )
                closed_off_confirmed = _write_and_confirm_state(
                    Cmw500LteCommandProfile.ebler_abort(self._sign_channel),
                    "OFF",
                    "final ABORT/OFF",
                )

        lifecycle_confirmed = all(
            (
                preclear_off_confirmed,
                window_configuration_confirmed,
                running_confirmed,
                ready_confirmed,
                closed_off_confirmed,
            )
        )
        if not lifecycle_confirmed:
            throughput_mbps = None
            bler_percent = None

        metrics = ThroughputMetrics(
            dl_throughput_mbps=throughput_mbps,
            dl_bler=bler_percent,
            throughput_scope=throughput_scope,
            kpi_valid={
                "dl_throughput": lifecycle_confirmed
                and throughput_mbps is not None,
                "dl_bler": lifecycle_confirmed and bler_percent is not None,
            },
        )
        exchange_ids = [exchange.exchange_id for exchange in exchanges]
        details = (*lifecycle_failures, *metric_failures)
        reason = (
            "; ".join(details)
            if details
            else "Extended BLER lifecycle and KPI fetch confirmed"
        )
        evidence = InstrumentEvidenceItem(
            instrument="cmw500",
            evidence_key="cmw500.extended_bler.window",
            requested={"window_s": window_s, "throughput_scope": throughput_scope},
            command_sent=Cmw500LteCommandProfile.ebler_init(self._sign_channel),
            readback={
                "absolute": absolute_raw,
                "relative": relative_raw,
                "preclear_off_confirmed": preclear_off_confirmed,
                "window_configuration_confirmed": window_configuration_confirmed,
                "running_confirmed": running_confirmed,
                "ready_confirmed": ready_confirmed,
                "closed_off_confirmed": closed_off_confirmed,
            },
            exchange_ids=exchange_ids,
            evidence_level=(
                EvidenceLevel.OUTCOME
                if lifecycle_confirmed
                else EvidenceLevel.TRANSPORT
            ),
            source_reference=(
                "R&S CMW LTE UE User Manual 1173.9628.02-41 "
                "§3.4.2 printed p.950-951; §3.4.4 printed p.957-959"
            ),
            verdict=(
                EvidenceVerdict.PASSED
                if lifecycle_confirmed
                else EvidenceVerdict.UNKNOWN
            ),
            reason=reason,
        )
        completed_at = datetime.now(timezone.utc)
        if cancelled is not None:
            raise cancelled
        return BaseStationMeasurementWindow(
            window_id=window_id,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            preclear_off_confirmed=preclear_off_confirmed,
            running_confirmed=running_confirmed,
            ready_confirmed=ready_confirmed,
            closed_off_confirmed=closed_off_confirmed,
            evidence=(evidence,),
            confirmed=lifecycle_confirmed,
            reason=reason,
        )

    async def get_throughput_metrics(
        self,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> ThroughputMetrics:
        """
        轮询读取 MAC 层吞吐量指标。

        SCPI:
          SENSe:LTE:SIGN1:CONNection:ETHRoughput:DL:PCC?
          SENSe:LTE:SIGN1:CONNection:ETHRoughput:UL:PCC?
          FETCh:LTE:SIGN1:EBLer:PCC:ABSolute?
          FETCh:LTE:SIGN1:EBLer:PCC:CQIReporting:STReam1?

        当前仓库没有可核对的厂商手册章节来证明 ETHRoughput 响应的字段顺序、
        单位与不可用 sentinel。响应仅保留为诊断证据；四个正式吞吐字段均保持
        ``None`` / ``kpi_valid=False``，直到该契约有厂商出处后再接线。
        """
        metrics = ThroughputMetrics(
            throughput_scope=ThroughputMetrics.SCOPE_UNKNOWN,
        )
        valid: Dict[str, bool] = {
            "dl_throughput": False,
            "ul_throughput": False,
            "dl_throughput_current": False,
            "ul_throughput_current": False,
        }

        dl_str = ""
        ul_str = ""
        try:
            # 仍回读并通过 SCPI/measurement 日志保留原始证据，但没有手册
            # 契约前不得解释字段位置、物理单位或 sentinel。
            dl_str = self._query(
                self._fmt(CmwScpiCommands.ETPUT_DL_PCC)
            )
            ul_str = self._query(
                self._fmt(CmwScpiCommands.ETPUT_UL_PCC)
            )

            # The sourced Extended BLER responses are parsed only as
            # diagnostic evidence here.  Task 10 owns the independent formal
            # measurement window; this legacy poll must not publish its
            # reliability field (field 1) as BLER or promote the values to KPI.
            absolute = self._query(
                Cmw500LteCommandProfile.ebler_absolute_query(self._sign_channel)
            )
            relative = self._query(
                Cmw500LteCommandProfile.ebler_relative_query(self._sign_channel)
            )
            if absolute and relative:
                try:
                    parsed_absolute = Cmw500LteCommandProfile.parse_ebler_absolute(
                        absolute
                    )
                    parsed_relative = Cmw500LteCommandProfile.parse_ebler_relative(
                        relative
                    )
                    logger.debug(
                        "[CMW500] Diagnostic Extended BLER: avg=%s kbit/s, BLER=%s%%",
                        parsed_absolute.throughput_average_kbit_per_s,
                        parsed_relative.bler_percent,
                    )
                except ValueError as exc:
                    logger.warning("[CMW500] Invalid Extended BLER response: %s", exc)

            # CQI
            cqi_str = self._query(
                self._fmt(CmwScpiCommands.EBLER_CQI)
            )
            if cqi_str:
                try:
                    metrics.cqi = int(float(cqi_str.strip().split(",")[0]))
                except (ValueError, IndexError):
                    pass

        except Exception as e:
            logger.warning(
                f"[CMW500] get_throughput_metrics partial fail: {e}"
            )

        # ── RSRP (UE 测量上报) ──
        try:
            rsrp_str = self._query(self._fmt(CmwScpiCommands.UE_RSRP))
            if rsrp_str and rsrp_str.strip():
                metrics.rsrp_dbm = float(rsrp_str.strip().split(",")[0])
        except Exception:
            pass

        # ── SINR (UE 测量上报) ──
        try:
            sinr_str = self._query(self._fmt(CmwScpiCommands.UE_SINR))
            if sinr_str and sinr_str.strip():
                metrics.sinr_db = float(sinr_str.strip().split(",")[0])
        except Exception:
            pass

        # ── 测量数据归档 → measurement.log ──
        metrics.kpi_valid.update(valid)
        meas_logger = logging.getLogger("app.measurement.throughput")

        def _throughput_text(value: Optional[float]) -> str:
            return "N/A" if value is None else f"{value:.1f}Mbps"

        bler_text = "N/A" if metrics.dl_bler is None else f"{metrics.dl_bler:.4f}"

        meas_logger.info(
            f"[KPI] DL={_throughput_text(metrics.dl_throughput_mbps)} "
            f"BLER={bler_text} CQI={metrics.cqi} "
            f"RSRP={metrics.rsrp_dbm:.1f}dBm SINR={metrics.sinr_db:.1f}dB",
            extra={
                "instrument_id": self.instrument_id,
                "dl_throughput_mbps": metrics.dl_throughput_mbps,
                "dl_bler": metrics.dl_bler,
                "ul_throughput_mbps": metrics.ul_throughput_mbps,
                "ul_bler": metrics.ul_bler,
                "cqi": metrics.cqi,
                "rsrp_dbm": metrics.rsrp_dbm,
                "sinr_db": metrics.sinr_db,
                "kpi_valid": dict(metrics.kpi_valid),
                "kpi_raw_unverified": {
                    "dl_ethroughput_pcc": dl_str or None,
                    "ul_ethroughput_pcc": ul_str or None,
                },
                "band": self._band,
                "bandwidth_mhz": self._bandwidth_mhz,
                "dl_power_dbm": self._dl_power_dbm,
            },
        )

        return metrics

    async def get_ue_info(self) -> Dict[str, Any]:
        """获取已连接 UE 的信息"""
        info = {
            "connected": self._cell_state == CellState.CONNECTED,
            "sign_channel": self._sign_channel,
        }
        try:
            rrc = self._query(
                self._fmt(CmwScpiCommands.RRC_STATE)
            ).strip()
            info["rrc_state"] = rrc
        except Exception:
            pass
        return info

    # ===================================================================
    # 5. 标准 InstrumentDriver 接口
    # ===================================================================

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="lte",
                description="LTE Signaling (Rel-8 to Rel-17)",
                supported=True,
                parameters={
                    "bands": list(LTE_BAND_EARFCN_MAP.keys()),
                    "max_bandwidth_mhz": self.max_bandwidth_mhz,
                    "max_mimo_layers": self.max_mimo_layers,
                    "tm_modes": [
                        "TM1", "TM2", "TM3", "TM4", "TM6", "TM7",
                        "TM8", "TM9", "TM10",
                    ],
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
                "earfcn": self._earfcn,
                "frequency_mhz": self._frequency_mhz,
                "bandwidth_mhz": self._bandwidth_mhz,
                "dl_power_dbm": self._dl_power_dbm,
                **tput.to_dict(),
            },
        )

    async def reset(self) -> bool:
        """复位仪器"""
        try:
            await self.stop_signaling()
            self._write(CmwScpiCommands.PRESET)
            self._query("*OPC?")
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception as e:
            logger.error(f"[CMW500] reset failed: {e}")
            return False

    def get_supported_technologies(self) -> List[RadioTechnology]:
        return [RadioTechnology.LTE]

    # ===================================================================
    # 内部 VISA 工具方法 (SCPI 日志由基类 _write/_query 自动处理)
    # ===================================================================

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        if not self._visa_session:
            raise ConnectionError("[CMW500] Not connected")
        self._visa_session.write(cmd)

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        if not self._visa_session:
            raise ConnectionError("[CMW500] Not connected")
        return self._visa_session.query(cmd)

    def _check_errors(self) -> None:
        """检查并清除错误队列"""
        while True:
            err = self._query(CmwScpiCommands.ERR).strip()
            if err.startswith("0,") or err.startswith("+0,"):
                break
            logger.warning(f"[CMW500] Instrument error: {err}")
