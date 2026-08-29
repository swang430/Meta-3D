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
import math
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
    BaseStationAttachReceipt,
    BaseStationAttachStageReceipt,
    BaseStationApplyReceipt,
    BaseStationControlReleaseResult,
    BaseStationFieldReceipt,
    BaseStationIdentity,
    BaseStationDriver,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindow,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
    BaseStationRemoteSessionResult,
    BaseStationRequestedConfig,
    LTE_TRANSMISSION_MODES,
    CellState,
    ThroughputMetrics,
)
from app.hal.lte_earfcn import validate_lte_band_options
from app.hal.cmw500_command_profile import (
    CMW500_LTE_COMMANDS,
    CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH,
    Cmw500LteCommandProfile,
    CmwLteFullRbRmcPlan,
    CmwNx2Route,
)
# P2-51：共享 SPI 结果类型（P1-32 起的既有契约）。定义仍在 uxm_base_station
# —— vendor-neutral 归位（挪 base_station.py）已记 Discovered，本片不动定义站点。
from app.hal.uxm_base_station import MacThroughputConfigResult
from app.hal.base_station_adapter_profile import BaseStationAdapterProfile
from app.hal.base_station_manifest import (
    BaseStationAdapterManifest,
    BaseStationAttachStageCapability,
    BaseStationConfigFieldCapability,
    BaseStationMeasurementCapability,
    BaseStationMetricCapability,
    BaseStationProfileFieldManifest,
    BaseStationRatCapability,
)
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
    # R&S CMW500 LTE UE User Manual 1173.9628.02-41,
    # printed pp.636-637: PCC band and downlink EARFCN are writable/queryable
    # with CONFigure:LTE:SIGN<i>[:PCC]:BAND and
    # CONFigure:LTE:SIGN<i>:RFSettings[:PCC]:CHANnel:DL.
    CELL_BAND = "CONFigure:LTE:SIGN{i}:BAND"                   # e.g., "OB3"
    CELL_DL_FREQ = "CONFigure:LTE:SIGN{i}:RFSettings:CHANnel:DL"  # EARFCN
    # Same manual, printed p.680: PCC DL bandwidth is writable/queryable with
    # CONFigure:LTE:SIGN<i>:CELL:BANDwidth[:PCC]:DL.
    CELL_DL_BW = "CONFigure:LTE:SIGN{i}:CELL:BANDwidth:DL"     # 带宽 (MHz)
    # Same manual, printed p.366: duplex mode is writable/queryable with
    # CONFigure:LTE:SIGN<i>[:PCC]:DMODe.
    CELL_DUPLEX = "CONFigure:LTE:SIGN{i}:DMODe"                # TDD/FDD
    CELL_PCI = "CONFigure:LTE:SIGN{i}:CELL:PCI"                 # 物理小区 ID

    # --- 下行功率 ---
    # R&S CMW500 LTE UE User Manual 1173.9628.02-41, §2.6.10,
    # printed p.656: PCC RS EPRE is writable/queryable as a numeric value
    # with default unit dBm/15kHz.  Its allowed range is configuration-
    # dependent, so the instrument error queue and exact readback are the gate.
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
    # R&S CMW500 LTE UE User Manual 1173.9628.02-41, command reference,
    # printed p.753: NENBantennas is writable/queryable and returns the exact
    # ONE | TWO | FOUR downlink TX-antenna configuration.
    MIMO_MODE = "CONFigure:LTE:SIGN{i}:CONNection:PCC:NENBantennas"
    # Same manual, GUI reference printed p.211 and command reference printed
    # p.754: TRANsmission is writable/queryable and accepts TM1/TM2/TM3/TM4/
    # TM6/TM7/TM8/TM9.  TMODe is a different ON/OFF "activate UE test mode"
    # command (printed p.739) and must not be used as LTE transmission mode.
    TRANSMISSION_MODE = (
        "CONFigure:LTE:SIGN{i}:CONNection:PCC:TRANsmission"
    )

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

    # --- UE 诊断上报 (仅保留现场已响应的 RSRP) ---
    # SINR 查询在当前 CMW500 上返回 -113 Undefined header，不在这里猜方言。
    UE_RSRP = "SENSe:LTE:SIGN{i}:UEReport:RSRP?"

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
      3. set_cell_config() → Band/BW/DL Freq 与请求的 RS-EPRE
      4. set_downlink_power() → 可选的独立 RS-EPRE 调整
      5. start_signaling() → Cell ON → PS Establish → 等待连接
      6. get_throughput_metrics() → 诊断回读（正式窗口由独立方法负责）
      7. stop_signaling() → PS Release → Cell OFF
    """

    adapter_id = "cmw500"
    metric_registry_profile_id = "cmw500_lte"
    adapter_profile_model = BaseStationAdapterProfile
    adapter_manifest = BaseStationAdapterManifest(
        schema_version=2,
        adapter_id=adapter_id,
        model_name="CMW500",
        vendor="Rohde & Schwarz",
        rat_capabilities=(
            BaseStationRatCapability(
                rat="lte",
                source_reference=(
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41"
                ),
            ),
        ),
        operations=(
            "identity",
            "config",
            "internal_route",
            "cell_attach",
            "measurement_window",
            "safe_idle_release",
            # P2-51: manual-evidenced LTE MAC/scheduling configuration
            # (STYPe RMC + full-RB RMC + DLPadding, see
            # docs/plans/2026-08-30-p2-51-cmw500-mac-scheduling-evidence.md).
            # Mirrored by the mac_throughput_configuration_supported ClassVar
            # (validate_base_station_adapter_registrations operation mirror).
            "mac_throughput_config",
        ),
        config_fields=tuple(
            BaseStationConfigFieldCapability(
                field=name,
                support=support,
                readback=readback,
                reason=reason,
                source_reference=source_reference,
            )
            for name, support, readback, reason, source_reference in (
                (
                    "radio_technology",
                    "diagnostic_only",
                    "unavailable",
                    "LTE is selected by the adapter manifest, not independently read back",
                    None,
                ),
                (
                    "channel_kind",
                    "diagnostic_only",
                    "unavailable",
                    "LTE EARFCN request shape is application-owned and has no device field readback",
                    None,
                ),
                (
                    "frequency_mhz",
                    "diagnostic_only",
                    "unavailable",
                    "frequency is derived from the LTE band/EARFCN request and is not independently written",
                    None,
                ),
                (
                    "bandwidth_mhz",
                    "authoritative",
                    "authoritative",
                    "PCC bandwidth is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.680",
                ),
                (
                    "band",
                    "authoritative",
                    "authoritative",
                    "PCC band is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed pp.636-637",
                ),
                (
                    "duplex",
                    "authoritative",
                    "authoritative",
                    "LTE duplex is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.366",
                ),
                (
                    "nr_arfcn",
                    "not_applicable",
                    "not_applicable",
                    "NR ARFCN is outside the LTE adapter contract",
                    None,
                ),
                (
                    "lte_dl_earfcn",
                    "authoritative",
                    "authoritative",
                    "PCC LTE downlink EARFCN is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed pp.636-637",
                ),
                (
                    "lte_transmission_mode",
                    "authoritative",
                    "authoritative",
                    "PCC LTE transmission mode is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.754",
                ),
                (
                    "subcarrier_spacing_khz",
                    "not_applicable",
                    "not_applicable",
                    "NR subcarrier spacing is outside the LTE adapter contract",
                    None,
                ),
                (
                    "mimo_layers",
                    "authoritative",
                    "authoritative",
                    "PCC antenna count is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.753",
                ),
                (
                    "downlink_power_dbm",
                    "authoritative",
                    "authoritative",
                    "PCC RS-EPRE is written and read back",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.656",
                ),
                (
                    "downlink_power_dbm_per_bandwidth",
                    "not_applicable",
                    "not_applicable",
                    "whole-band UXM power is outside the CMW500 RS-EPRE contract",
                    None,
                ),
                (
                    "port_preset",
                    "not_applicable",
                    "not_applicable",
                    "CMW500 routing is supplied by the dedicated internal-route profile",
                    None,
                ),
                (
                    "scheduler_algorithm",
                    "not_applicable",
                    "not_applicable",
                    # P2-51: scheduling is driven by the dedicated MAC
                    # throughput operation (STYPe RMC, manual printed p.743),
                    # not by the generic config request field.
                    "scheduling type is owned by the dedicated MAC throughput "
                    "operation (STYPe RMC), not by the generic config request",
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.743",
                ),
                (
                    "csi_rs_ports",
                    "not_applicable",
                    "not_applicable",
                    "NR CSI-RS configuration is outside the LTE adapter contract",
                    None,
                ),
            )
        ),
        attach_stages=(
            BaseStationAttachStageCapability(
                stage="cell_ready",
                evidence="authoritative",
                reason="CELL ON,ADJUSTED is read from the instrument",
                source_reference=(
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.371"
                ),
            ),
            BaseStationAttachStageCapability(
                stage="ue_registered",
                evidence="authoritative",
                reason="PS ATTACHED is read from the instrument",
                source_reference=(
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed p.374"
                ),
            ),
            BaseStationAttachStageCapability(
                stage="rrc_connected",
                evidence="unavailable",
                reason="the adapter does not expose an independent RRC milestone",
                source_reference=None,
            ),
            BaseStationAttachStageCapability(
                stage="data_bearer_established",
                evidence="authoritative",
                reason="PS CONNECTED is read after the explicit connect action",
                source_reference=(
                    "R&S CMW500 LTE UE User Manual 1173.9628.02-41 printed pp.372-374"
                ),
            ),
        ),
        measurement=BaseStationMeasurementCapability(
            cardinality="single",
            scopes=("pcell",),
            lifecycle="authoritative_closed",
            metrics=(
                BaseStationMetricCapability(
                    key="dl_throughput_mbps",
                    direction="downlink",
                    unit="mbps",
                    scopes=("pcell",),
                    evidence="authoritative",
                    source_reference=(
                        "R&S CMW500 LTE UE User Manual 1173.9628.02-41 §3.4.4 "
                        "printed pp.957-959"
                    ),
                ),
                BaseStationMetricCapability(
                    key="dl_bler_percent",
                    direction="downlink",
                    unit="percent",
                    scopes=("pcell",),
                    evidence="authoritative",
                    source_reference=(
                        "R&S CMW500 LTE UE User Manual 1173.9628.02-41 §3.4.4 "
                        "printed pp.957-959"
                    ),
                ),
            ),
            source_reference=(
                "R&S CMW500 LTE UE User Manual 1173.9628.02-41 §3.4.2 "
                "printed pp.950-951"
            ),
        ),
        profile_requirement="required",
        profile_schema_version=1,
        profile_fields=tuple(
            BaseStationProfileFieldManifest(
                path=f"lte_2x2_internal_route.{name}",
                label=name,
                required=True,
                placeholder="VALUE",
                description="Laboratory-configured CMW500 LTE 2x2 internal route field",
            )
            for name in (
                "pcc_bb_board",
                "rx_connector",
                "rx_converter",
                "tx1_connector",
                "tx1_converter",
                "tx2_connector",
                "tx2_converter",
            )
        ),
        manual_sources=(
            "Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf",
        ),
        diagnostic_supported=True,
        formal_gate="site_certification",
    )
    measurement_window_cardinality = "single"
    # P2-51：正式 MAC/调度配置能力（manifest operations 的
    # "mac_throughput_config" token 镜像；镜像门 =
    # validate_base_station_adapter_registrations 的 operation_mirrors）。
    mac_throughput_configuration_supported = True
    # P2-51：configure_mac_throughput_test 的组名。missing_mandatory 语义与
    # UXM 相同（mandatory ∩ skipped）；本驱动 skipped 只用于「没轮到发/选件域
    # 不发」，被仪器拒/回读不符走 rejected。
    MAC_CFG_MANDATORY: tuple = (
        "SCHED_TYPE_RMC",
        "DL_STREAM_COUPLING",
        "RMC_DL",
        "RMC_RBPOS_DL",
        "RMC_UL",
        "RMC_RBPOS_UL",
        "DL_PADDING",
    )
    # P2-51：手册无对应命令 / 不可如实翻译的 SPI 维度（取证清单 §4 逐条）。
    # ⚠ 两个方向都不补真：不从 UXM 方言抄、不从请求值/旧状态猜。
    MAC_CFG_NO_EQUIVALENT: Dict[str, str] = {
        "NR_MCS_INDEX": (
            "LTE RMC 由 #RB/调制/TBS 三元组描述（手册 §2.2.19 p.69、pp.799-801），"
            "无「MCS 索引」命令；不发明 36.213 映射，实配组合见 receipt 的 rmc_dl/rmc_ul"
        ),
        "TDD_SLOT_PATTERN": (
            "FDD 无子帧配比维度；LTE TDD 配比是 CELL[:PCC]:ULDL 0..6（p.687），"
            "NR slot 字符串不可如实翻译 —— TDD duplex 下本方法整体 fail-loud"
        ),
        "HARQ_PROCESSES": (
            "LTE DL HARQ 进程数无手册命令（HARQ 组 pp.783-785 仅 "
            "ENABle/NHT/RVCSequence/UDSequence）"
        ),
        "MEAS_TPUT_STAT_COUNT": (
            "EBLer:SFRames（p.953）有对应命令：p.953『只影响 trace 长度』"
            "限定 confidence 模式（SCONdition CLEVel），而正式窗口是"
            "continuous（SCONdition NONE，P1-73B）——该模式下 SFRames ="
            "每周期统计子帧数（§3.3.1 p.940 示例明示）。命令归窗口层所有、"
            "当前全仓未驱动：统计基继承仪器旧状态是已登记缺口"
            "（Discovered：窗口层驱动 SFRames），不在 MAC 配置层越权下发"
        ),
        "NR_SCS": "LTE 子载波间隔固定 15 kHz，手册无配置命令",
        "CSI_RS_PORTS": "NR 概念；本驱动 LTE 正式路径 TM3 2x2，无对应命令",
    }
    # P2-51：本方法所用命令集的最低固件下限 = 各 mac_* 规格 minimum_firmware
    # 的最大值（MCLuster:UL 探测 V3.5.20 > DLEQual V3.2.60）。
    # 门测试断言该常量与规格表派生值一致，防单边改动漂移。
    MAC_CFG_MIN_FIRMWARE = "V3.5.20"
    input_level_unavailable_reason = (
        "Warning: CMW500 input-level/power capability remains disabled in P1-73A"
    )
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
        # CMW500 option-list replies use bare product codes (for example
        # ``KS520``/``KS550``).  The manual's display names add ``CMW-``;
        # that catalog prefix is not part of the instrument-owned token.
        installed = {
            option.strip().upper().removeprefix("CMW-")
            for option in self._installed_options
        }
        duplex_option = "KS500" if normalized_duplex == "fdd" else "KS550"
        missing = sorted({"KS520", duplex_option} - installed)
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
        readback_specs = (
            CMW500_LTE_COMMANDS["route_nx2_query"],
            CMW500_LTE_COMMANDS["route_query"],
        )

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
                source_reference="; ".join(
                    (
                        spec.source_reference,
                        *(item.source_reference for item in readback_specs),
                    )
                ),
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
        installed = {
            option.strip().upper().removeprefix("CMW-")
            for option in self._installed_options
        }
        missing_options = [
            option
            for option in spec.required_options
            if option.strip().upper().removeprefix("CMW-") not in installed
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
            nx2_applied: dict[str, str] | None = None
            nx2_readback_error: str | None = None
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
                try:
                    nx2_readback = (
                        Cmw500LteCommandProfile.parse_route_nx2_readback(
                            self._query(
                                Cmw500LteCommandProfile.route_nx2_query(
                                    self._sign_channel
                                )
                            )
                        )
                    )
                    nx2_applied = asdict(nx2_readback)
                except Exception as exc:
                    # The generic query remains a sourced, useful physical-path
                    # diagnostic when a particular CMW firmware rejects the
                    # setting query.  The write queue was proven empty just
                    # before this query, so archive and drain the query-owned
                    # error before any later CELL ON write can consume it.
                    probe_queue_result = self._query(CmwScpiCommands.ERR).strip()
                    if not probe_queue_result:
                        raise RuntimeError(
                            "CMW500 nx2 query error queue could not be read"
                        ) from exc
                    nx2_readback_error = (
                        f"{type(exc).__name__}: {exc}; "
                        f"query error queue: {probe_queue_result}"
                    )
                physical_readback = (
                    Cmw500LteCommandProfile.parse_route_readback(
                        self._query(
                            Cmw500LteCommandProfile.route_query(
                                self._sign_channel
                            )
                        )
                    )
                )
                readback_queue_result = self._query(CmwScpiCommands.ERR).strip()
                if (
                    re.fullmatch(
                        r'\+?0\s*,\s*"[^"]*"', readback_queue_result
                    )
                    is None
                ):
                    return _result(
                        requested=requested,
                        reason=(
                            "CMW500 readback error queue rejected route "
                            f"confirmation: {readback_queue_result}"
                        ),
                        exchanges=exchanges,
                    )
            except Exception as exc:
                return _result(
                    requested=requested,
                    reason=f"CMW500 route apply/readback failed: {exc}",
                    exchanges=exchanges,
                )

            generic_physical = {
                # LTE UE Manual pp.459-460: the generic query's Controller
                # field is reserved and irrelevant, so it is never used as
                # PCCBBBoard evidence.  It independently confirms only these
                # six active physical paths.
                "rx_connector": physical_readback.rx_connector,
                "rx_converter": physical_readback.rx_converter,
                "tx1_connector": physical_readback.tx1_connector,
                "tx1_converter": physical_readback.tx1_converter,
                "tx2_connector": physical_readback.tx2_connector,
                "tx2_converter": physical_readback.tx2_converter,
            }
            requested_physical = {
                key: value
                for key, value in requested.items()
                if key != "pcc_bb_board"
            }
            if nx2_readback_error is not None:
                if generic_physical != requested_physical:
                    return _result(
                        requested=requested,
                        applied=generic_physical,
                        reason=(
                            "CMW500 nx2 route readback unavailable and generic "
                            "physical readback does not match requested route: "
                            f"{nx2_readback_error}"
                        ),
                        exchanges=exchanges,
                    )
                return _result(
                    requested=requested,
                    applied=generic_physical,
                    confirmed=False,
                    reason=(
                        "CMW500 nx2 route readback unavailable; generic physical "
                        "paths confirmed for diagnostic execution only: "
                        f"{nx2_readback_error}"
                    ),
                    exchanges=exchanges,
                )
            if nx2_applied is None:
                return _result(
                    requested=requested,
                    reason="CMW500 nx2 route readback produced no trusted value",
                    exchanges=exchanges,
                )
            if nx2_applied != requested:
                return _result(
                    requested=requested,
                    applied=nx2_applied,
                    reason=(
                        "CMW500 nx2 route readback does not match requested route"
                    ),
                    exchanges=exchanges,
                )
            nx2_physical = {
                key: value
                for key, value in nx2_applied.items()
                if key != "pcc_bb_board"
            }
            if generic_physical != nx2_physical:
                return _result(
                    requested=requested,
                    reason=(
                        "CMW500 generic physical route readback does not match "
                        "the nx2 route readback"
                    ),
                    exchanges=exchanges,
                )
            return _result(
                requested=requested,
                applied=nx2_applied,
                confirmed=True,
                reason="CMW500 route write and both readbacks confirmed",
                exchanges=exchanges,
            )

    async def apply_route(
        self,
        frozen_adapter: dict[str, Any],
    ) -> BaseStationApplyReceipt:
        """Translate existing sourced CMW route truth into the common receipt."""

        result = await self.apply_internal_lte_2x2_route(frozen_adapter)
        exchange_ids = tuple(result.exchange_ids)
        if result.requested is None:
            return BaseStationApplyReceipt(
                schema_version=1,
                operation="route",
                fields=(
                    BaseStationFieldReceipt(
                        field="route",
                        requested=None,
                        applied=None,
                        status="unknown",
                        reason=result.reason,
                        exchange_ids=exchange_ids,
                    ),
                ),
                reason=result.reason,
                simulated=False,
            )

        applied = result.applied if isinstance(result.applied, dict) else {}
        fields = tuple(
            BaseStationFieldReceipt(
                field=name,
                requested=requested_value,
                applied=(
                    applied[name]
                    if name in applied and applied[name] == requested_value
                    else None
                ),
                status=(
                    "confirmed"
                    if name in applied and applied[name] == requested_value
                    else "unknown"
                ),
                reason=(
                    "authoritative CMW500 route readback matched"
                    if name in applied and applied[name] == requested_value
                    else result.reason
                ),
                exchange_ids=exchange_ids,
            )
            for name, requested_value in result.requested.items()
        )
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="route",
            fields=fields,
            reason=result.reason,
            simulated=False,
        )

    def route_allows_diagnostic_execution(
        self,
        receipt: BaseStationApplyReceipt,
    ) -> bool:
        """Require every physical CMW path even when PCC readback is unavailable."""

        if not isinstance(receipt, BaseStationApplyReceipt):
            return False
        by_name = {field.field: field for field in receipt.fields}
        physical_fields = {
            "rx_connector",
            "rx_converter",
            "tx1_connector",
            "tx1_converter",
            "tx2_connector",
            "tx2_converter",
        }
        return receipt.operation == "route" and all(
            name in by_name and by_name[name].status == "confirmed"
            for name in physical_fields
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

    async def apply_config(
        self,
        requested: BaseStationRequestedConfig,
    ) -> BaseStationApplyReceipt:
        """Apply CMW config and expose only existing authoritative readbacks."""

        if not isinstance(requested, BaseStationRequestedConfig):
            raise TypeError("requested must be BaseStationRequestedConfig")
        self._last_common_config_readback = None
        with capture_scpi_exchanges() as exchanges:
            operation_succeeded = await self.apply_requested_config(requested)
        exchange_ids = tuple(item.exchange_id for item in exchanges)
        readback = (
            self._last_common_config_readback
            if isinstance(self._last_common_config_readback, dict)
            else {}
        )
        requested_fields = tuple(requested.receipt_payload().items())
        fields = tuple(
            BaseStationFieldReceipt(
                field=name,
                requested=value,
                applied=(
                    readback[name]
                    if name in readback and readback[name] == value
                    else None
                ),
                status=(
                    "confirmed"
                    if name in readback and readback[name] == value
                    else "unknown"
                ),
                reason=(
                    "authoritative CMW500 configuration readback matched"
                    if name in readback and readback[name] == value
                    else "CMW500 configuration field was not authoritatively confirmed"
                ),
                exchange_ids=exchange_ids,
            )
            for name, value in requested_fields
        )
        receipt = BaseStationApplyReceipt(
            schema_version=1,
            operation="config",
            fields=fields,
            reason=(
                "CMW500 configuration readback confirmed"
                if fields and all(field.status == "confirmed" for field in fields)
                else "CMW500 configuration readback is partial or unavailable"
            ),
            simulated=False,
            operation_succeeded=operation_succeeded is True,
        )
        return receipt

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

    async def release_to_local_control(self) -> bool:
        """Safely release an idle transport without claiming front-panel Local."""

        if self._visa_session is None and self._session_token is None:
            return True
        released = await self.release_remote_session(self._session_token or "")
        return released.transport_session_released_confirmed is True

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        """Close the transport only after the live cell is confirmed safe idle."""

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
                safe_idle_confirmed = await self.ensure_safe_idle()
            except Exception as exc:
                safe_idle_confirmed = False
                warnings.append(f"CMW500 SAFE_IDLE confirmation failed: {exc}")
            if safe_idle_confirmed is not True:
                warnings.append(
                    "CMW500 SAFE_IDLE is unconfirmed; transport remains open for safe recovery"
                )
                return BaseStationControlReleaseResult(
                    measurement_attempt_id=measurement_attempt_id,
                    lease_id=lease_id,
                    adapter_id="cmw500",
                    session_token=current_token,
                    remote_session_acquired_confirmed=token_matches,
                    transport_session_released_confirmed=False,
                    front_panel_local_confirmed=None,
                    warnings=tuple(warnings),
                )
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
            if self._visa_session is not None:
                cleanup_confirmed = await self.ensure_safe_idle() is True
                if not cleanup_confirmed:
                    logger.error(
                        "[CMW500] SAFE_IDLE unconfirmed; transport remains open "
                        "for safe recovery"
                    )
                    return False

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
            return True
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
          CONFigure:LTE:SIGN1:DMODe FDD
          CONFigure:LTE:SIGN1:BAND OB3
          CONFigure:LTE:SIGN1:CELL:BANDwidth:DL B200
          CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL 1575
          CONFigure:LTE:SIGN1:DL:RSEPre:LEVel -65.25
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
            transmission_mode = None
            if "lte_transmission_mode" in config:
                transmission_mode = str(
                    config["lte_transmission_mode"]
                ).upper()
                if transmission_mode not in LTE_TRANSMISSION_MODES:
                    logger.error(
                        "[CMW500] Rejecting invalid LTE transmission mode %r",
                        config["lte_transmission_mode"],
                    )
                    return False
            downlink_power_dbm = None
            if "dl_power_dbm" in config:
                raw_power = config["dl_power_dbm"]
                if isinstance(raw_power, bool):
                    logger.error("[CMW500] Rejecting boolean DL RS-EPRE")
                    return False
                downlink_power_dbm = float(raw_power)
                if not math.isfinite(downlink_power_dbm):
                    logger.error("[CMW500] Rejecting non-finite DL RS-EPRE")
                    return False

            if not await self.ensure_safe_idle():
                logger.error("[CMW500] Cell config blocked: SAFE_IDLE unconfirmed")
                return False

            # SYSTem:ERRor:ALL? 是设备级队列且读取后清空。先丢弃本次配置
            # 之前已经存在的错误，避免后台诊断或上一次人工命令被误认成
            # 当前配置失败；配置写完后仍由 _write_group_confirmed() 独立验错。
            stale_errors = self._query(CmwScpiCommands.ERR)
            if not self._error_queue_is_empty(stale_errors):
                logger.warning(
                    "[CMW500] Discarded pre-existing error queue before cell config: %s",
                    stale_errors.strip(),
                )

            # The instrument rejects a TDD-only band while the cell is still
            # in its previous duplex mode.  Select the requested duplex before
            # applying the band and its EARFCN.
            if "duplex" in config:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_DUPLEX)
                    + f" {config['duplex'].upper()}"
                )

            if "band" in config:
                self._write(self._fmt(CmwScpiCommands.CELL_BAND) + f" {band}")

            # User Manual §2.6.12.1, p.680: PCC DL bandwidth also applies
            # to UL; there is no separate PCC CELL:BANDwidth:UL write.
            if bandwidth_token is not None:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_DL_BW)
                    + f" {bandwidth_token}"
                )

            self._write(
                self._fmt(CmwScpiCommands.CELL_DL_FREQ) + f" {earfcn}"
            )

            if downlink_power_dbm is not None:
                self._write(
                    self._fmt(CmwScpiCommands.DL_POWER_RS)
                    + f" {downlink_power_dbm:.12g}"
                )

            # 物理小区 ID
            if "cell_id" in config:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_PCI)
                    + f" {config['cell_id']}"
                )

            if transmission_mode is not None:
                self._write(
                    self._fmt(CmwScpiCommands.TRANSMISSION_MODE)
                    + f" {transmission_mode}"
                )
            if "mimo_layers" in config:
                layers = config["mimo_layers"]
                mimo_map = {1: "ONE", 2: "TWO", 4: "FOUR"}
                mimo_str = mimo_map[layers]
                self._write(
                    self._fmt(CmwScpiCommands.MIMO_MODE)
                    + f" {mimo_str}"
                )

            if not self._write_group_confirmed():
                logger.error("[CMW500] Cell config rejected by completion/error check")
                return False

            # OPC only confirms completion and the error queue only confirms
            # the absence of a reported command error.  Formal execution also
            # requires the instrument's applied PCC configuration to match the
            # request exactly before the cached state may be updated.
            expected_duplex = (
                str(config["duplex"]).upper() if "duplex" in config else None
            )
            band_readback = (
                self._query(self._fmt(CmwScpiCommands.CELL_BAND) + "?")
                .strip()
                .upper()
                if "band" in config
                else None
            )
            bandwidth_readback = (
                self._query(self._fmt(CmwScpiCommands.CELL_DL_BW) + "?")
                .strip()
                .upper()
                if "bandwidth_mhz" in config
                else None
            )
            earfcn_readback = int(
                self._query(
                    self._fmt(CmwScpiCommands.CELL_DL_FREQ) + "?"
                ).strip()
            )
            duplex_readback = (
                self._query(self._fmt(CmwScpiCommands.CELL_DUPLEX) + "?")
                .strip()
                .upper()
                if expected_duplex is not None
                else None
            )
            expected_mimo = (
                {1: "ONE", 2: "TWO", 4: "FOUR"}[config["mimo_layers"]]
                if "mimo_layers" in config
                else None
            )
            mimo_readback = (
                self._query(self._fmt(CmwScpiCommands.MIMO_MODE) + "?")
                .strip()
                .upper()
                if expected_mimo is not None
                else None
            )
            transmission_mode_readback = (
                self._query(
                    self._fmt(CmwScpiCommands.TRANSMISSION_MODE) + "?"
                ).strip().upper()
                if transmission_mode is not None
                else None
            )
            downlink_power_readback = (
                float(
                    self._query(
                        self._fmt(CmwScpiCommands.DL_POWER_RS) + "?"
                    ).strip()
                )
                if downlink_power_dbm is not None
                else None
            )
            expected_bandwidth = (
                bandwidth_token
                if bandwidth_token is not None
                else self.bandwidth_token_by_mhz[bandwidth_mhz]
            )
            normalized_band = (
                f"B{band_readback[2:]}"
                if isinstance(band_readback, str) and band_readback.startswith("OB")
                else band_readback
            )
            bandwidth_by_token = {
                token: mhz for mhz, token in self.bandwidth_token_by_mhz.items()
            }
            normalized_mimo = {
                "ONE": 1,
                "TWO": 2,
                "FOUR": 4,
            }.get(mimo_readback)
            self._last_common_config_readback = {
                **({"band": normalized_band} if band_readback is not None else {}),
                **(
                    {"bandwidth_mhz": bandwidth_by_token.get(bandwidth_readback)}
                    if bandwidth_readback is not None
                    else {}
                ),
                "lte_dl_earfcn": earfcn_readback,
                **(
                    {"duplex": duplex_readback.lower()}
                    if duplex_readback is not None
                    else {}
                ),
                **(
                    {"mimo_layers": normalized_mimo}
                    if mimo_readback is not None
                    else {}
                ),
                **(
                    {"lte_transmission_mode": transmission_mode_readback}
                    if transmission_mode_readback is not None
                    else {}
                ),
                **(
                    {"downlink_power_dbm": downlink_power_readback}
                    if downlink_power_readback is not None
                    else {}
                ),
            }
            if (
                (band_readback is not None and band_readback != band)
                or (
                    bandwidth_readback is not None
                    and bandwidth_readback != expected_bandwidth
                )
                or earfcn_readback != earfcn
                or (
                    duplex_readback is not None
                    and duplex_readback != expected_duplex
                )
                or (mimo_readback is not None and mimo_readback != expected_mimo)
                or (
                    transmission_mode_readback is not None
                    and transmission_mode_readback != transmission_mode
                )
                or (
                    downlink_power_readback is not None
                    and downlink_power_readback != downlink_power_dbm
                )
            ):
                logger.error(
                    "[CMW500] Cell config readback mismatch: "
                    "requested=(%s,%s,%s,%s,%s,%s,%s), "
                    "applied=(%s,%s,%s,%s,%s,%s,%s)",
                    band,
                    expected_bandwidth,
                    earfcn,
                    expected_duplex,
                    expected_mimo,
                    transmission_mode,
                    downlink_power_dbm,
                    band_readback,
                    bandwidth_readback,
                    earfcn_readback,
                    duplex_readback,
                    mimo_readback,
                    transmission_mode_readback,
                    downlink_power_readback,
                )
                return False

            self._band = band
            self._bandwidth_mhz = bandwidth_mhz
            self._earfcn = earfcn
            self._frequency_mhz = frequency_mhz
            if downlink_power_dbm is not None:
                self._dl_power_dbm = downlink_power_dbm
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

    async def configure_mac_throughput_test(
        self,
        mimo_layers: int = 2,
        mcs: int = 28,
        rb_alloc: str = "ALL",
        enable_amc: bool = False,
        tdd_pattern: str = "DDDDDDDSUU",
        tdd_period: str = "5MS",
        harq_max_trans: int = 4,
        harq_processes: int = 16,
        stat_count: int = 5000,
        scs_khz: Optional[int] = None,
        csi_rs_ports: Optional[int] = None,
    ) -> MacThroughputConfigResult:
        """P2-51：LTE 正式 throughput/BLER 的 MAC/调度配置（手册逐条取证）。

        取证清单（命令→页码→设置/查询→选件依赖）：
        docs/plans/2026-08-30-p2-51-cmw500-mac-scheduling-evidence.md

        写序（每组独立 `*OPC?` + `SYSTem:ERRor:ALL?` 验错 + 查询回读比对）：
        STYPe RMC（p.743）→ MCLuster:UL 探测（pp.743-744，仅查询）→
        DLEQual ON（p.794）→ RMC:DL1 满配行（表 2-38 p.78）+ RBPosition:DL1 LOW
        （2 层再回读 DL2 验证耦合）→ RMC:UL 满配行（表 2-33 pp.70-71）+
        RBPosition:UL LOW → DLPadding ON（p.742，BLER 前置 §3.1 p.921）→
        HARQ:DL:ENABle 探测记档（pp.783-784 选件域，不驱动）。

        ⚠ 不可如实翻译的 SPI 维度（NR MCS 索引 / NR TDD pattern / HARQ 进程数 /
        stat_count / SCS / CSI-RS）见类常量 ``MAC_CFG_NO_EQUIVALENT`` —— 不从
        UXM 方言抄命令、不从请求值或旧状态补真；TDD duplex 整体 fail-loud。
        """

        applied: List[str] = []
        skipped: List[str] = []
        rejected: List[str] = []
        # (field, requested, applied_value, status, reason) —— 统一在结尾装配
        # BaseStationFieldReceipt（exchange_ids 取整段 capture，与 apply_config
        # / apply_route 的既有证据形态一致）。
        field_rows: List[tuple] = []
        no_equivalent = tuple(self.MAC_CFG_NO_EQUIVALENT)
        sign = self._sign_channel
        profile = Cmw500LteCommandProfile

        def _result(
            error: Optional[str],
            exchanges=(),
            *,
            reason: str,
        ) -> MacThroughputConfigResult:
            exchange_ids = tuple(item.exchange_id for item in exchanges)
            receipt_fields = tuple(
                BaseStationFieldReceipt(
                    field=name,
                    requested=requested,
                    applied=applied_value,
                    status=status,
                    reason=field_reason,
                    exchange_ids=exchange_ids,
                )
                for name, requested, applied_value, status, field_reason in field_rows
            ) or (
                BaseStationFieldReceipt(
                    field="mac_throughput_config",
                    requested=None,
                    applied=None,
                    status="not_applicable",
                    reason=reason,
                    exchange_ids=exchange_ids,
                ),
            )
            missing = tuple(n for n in self.MAC_CFG_MANDATORY if n in skipped)
            receipt = BaseStationApplyReceipt(
                schema_version=1,
                operation="mac_throughput_config",
                fields=receipt_fields,
                reason=reason,
                simulated=False,
                operation_succeeded=(
                    error is None and not rejected and not missing
                ),
            )
            return MacThroughputConfigResult(
                applied=tuple(applied),
                skipped=tuple(skipped),
                missing_mandatory=missing,
                undefined_on_profile=(),
                error=error,
                rejected=tuple(rejected),
                no_equivalent=no_equivalent,
                receipt=receipt,
            )

        # ---- 无副作用前置（不碰仪器）--------------------------------------
        if enable_amc:
            return _result(
                "enable_amc=True 在 CMW500 上无正式路径：AMC 对应 CQI 调度类型"
                "（follow wideband CQI），STYPe=CQI 非 TTIB 需 KS510/KS512 选件"
                "（手册 p.743 Options）；选件依赖类型保持 diagnostic，固定传输"
                "格式请用 enable_amc=False 的 RMC 路径。",
                reason="enable_amc 选件依赖拒绝",
            )
        # 内审 F2：满配 DL 行取自手册表 2-38（multiple TX antennas，TM2-6
        # 专用）；单天线表 2-37 同带宽行无本表的 16-QAM/TBS 组合 —— mimo=1
        # 下发即为适用域外的行。收窄到 =2（与 manifest 声明的 TM3 2x2 一致）。
        if mimo_layers != 2:
            return _result(
                f"mimo_layers={mimo_layers} 无手册证据路径：满配 DL 行取自"
                "表 2-38（TM2-6 多天线专用，§2.2.19.4）；单天线表 2-37 同带宽"
                "行是另一组调制/TBS，4 流无 RMC 表 —— 只取证了 2 流，不猜。",
                reason="mimo_layers 超出手册 RMC 证据范围（仅 2 流取证）",
            )
        if str(rb_alloc).strip().upper() != "ALL":
            return _result(
                f"rb_alloc={rb_alloc!r} 不支持：本片只取证了满 RB 分配行"
                "（表 2-33/2-38 满配行）；部分分配不猜。",
                reason="rb_alloc 非满配拒绝",
            )
        if not self._firmware_at_least(
            self._firmware_version, self.MAC_CFG_MIN_FIRMWARE
        ):
            return _result(
                f"CMW500 固件 {self._firmware_version!r} 低于 MAC 配置命令集"
                f"下限 {self.MAC_CFG_MIN_FIRMWARE}（MCLuster:UL 探测 V3.5.20，"
                "见取证清单 §1），拒绝下发。",
                reason="固件低于命令集下限",
            )

        try:
            if not await self.ensure_safe_idle():
                return _result(
                    "SAFE_IDLE 未确认（Cell 非 OFF,ADJUSTED），不下发 MAC 配置。",
                    reason="SAFE_IDLE 未确认",
                )

            with capture_scpi_exchanges() as exchanges:
                # 归属隔离：丢弃进入本方法前已存在的错误队列（同 set_cell_config）
                stale_errors = self._query(CmwScpiCommands.ERR)
                if not self._error_queue_is_empty(stale_errors):
                    logger.warning(
                        "[CMW500] Discarded pre-existing error queue before "
                        "MAC config: %s",
                        stale_errors.strip(),
                    )

                def _group_gate() -> Optional[str]:
                    """OPC + 错误队列独立验错；被拒返回队列文本。"""
                    if self._query(CmwScpiCommands.OPC).strip() != "1":
                        return "operation-complete gate failed"
                    queue = self._query(CmwScpiCommands.ERR).strip()
                    if not self._error_queue_is_empty(queue):
                        return queue
                    return None

                # ---- 活体工作点（不用缓存值，不从旧状态补真）----------------
                live_duplex = (
                    self._query(self._fmt(CmwScpiCommands.CELL_DUPLEX) + "?")
                    .strip()
                    .upper()
                )
                live_bw_token = (
                    self._query(self._fmt(CmwScpiCommands.CELL_DL_BW) + "?")
                    .strip()
                    .upper()
                )
                live_gate = _group_gate()
                if live_gate is not None:
                    return _result(
                        f"活体 duplex/带宽查询被拒（{live_gate}），"
                        "无法确定 RMC 满配行 —— fail-loud。",
                        exchanges,
                        reason="活体工作点查询被拒",
                    )
                if live_duplex != "FDD":
                    return _result(
                        f"活体 duplex={live_duplex!r}：LTE TDD 配比是 "
                        "CELL[:PCC]:ULDL 0..6（p.687）+ 特殊子帧，NR 形态 "
                        f"tdd_pattern={tdd_pattern!r} 不可如实翻译，TDD 歧义 RMC "
                        "还需 VERSion:DL<s>（p.803）——TDD 正式 MAC 配置为平台"
                        "缺口（Discovered），本次 fail-loud。",
                        exchanges,
                        reason="TDD duplex 无正式取证路径",
                    )
                rmc_plan: Optional[CmwLteFullRbRmcPlan] = (
                    CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH.get(live_bw_token)
                )
                if rmc_plan is None:
                    return _result(
                        f"活体带宽回读 {live_bw_token!r} 不在手册满配 RMC 表"
                        "（表 2-33 pp.70-71 / 表 2-38 p.78）里 —— 不猜。",
                        exchanges,
                        reason="活体带宽无满配 RMC 行",
                    )

                def _confirm(
                    group: str,
                    field: str,
                    write_command: Optional[str],
                    query_command: str,
                    expected,
                    parse,
                ) -> None:
                    """一组：可选写 → OPC/错误队列门 → 查询回读严格比对。"""
                    if write_command is not None:
                        self._write(write_command)
                        gate = _group_gate()
                        if gate is not None:
                            rejected.append(group)
                            field_rows.append(
                                (field, expected, None, "unknown",
                                 f"仪器拒绝写入: {gate}")
                            )
                            return
                    try:
                        raw = self._query(query_command)
                    except Exception as exc:  # noqa: BLE001 — 单组失败逐组记账
                        rejected.append(f"{group}(回读不可用)")
                        field_rows.append(
                            (field, expected, None, "unknown",
                             f"回读查询失败: {exc}")
                        )
                        return
                    query_gate = _group_gate()
                    if query_gate is not None:
                        rejected.append(f"{group}(回读被拒)")
                        field_rows.append(
                            (field, expected, None, "unknown",
                             f"回读被仪器拒绝: {query_gate}")
                        )
                        return
                    try:
                        observed = parse(raw)
                    except ValueError as exc:
                        rejected.append(f"{group}(回读不可解析)")
                        field_rows.append(
                            (field, expected, None, "unknown", str(exc))
                        )
                        return
                    if observed != expected:
                        rejected.append(f"{group}(回读={observed}≠{expected})")
                        field_rows.append(
                            (field, expected, None, "unknown",
                             f"回读 {observed!r} 与请求 {expected!r} 不一致")
                        )
                        return
                    if write_command is not None:
                        applied.append(group)
                    field_rows.append(
                        (field, expected, observed, "confirmed",
                         "authoritative CMW500 readback matched")
                    )

                def _parse_rmc(direction: str):
                    def _inner(raw: str) -> str:
                        return profile.parse_mac_rmc_readback(
                            raw, direction=direction
                        ).encoded()
                    return _inner

                # 1. 调度类型 RMC（p.743；RMC 无选件标注）
                _confirm(
                    "SCHED_TYPE_RMC",
                    "scheduling_type",
                    profile.mac_scheduling_type_rmc(sign),
                    profile.mac_scheduling_type_query(sign),
                    "RMC",
                    profile.parse_mac_scheduling_type,
                )
                # 2. UL contiguous 前提探测（pp.743-744；multi-cluster 特性
                #    KS510/KS512 选件门控 → 只查询确认 OFF，被拒即 fail-closed）
                _confirm(
                    "UL_MULTICLUSTER_PROBE",
                    "ul_multicluster",
                    None,
                    profile.mac_ul_multicluster_query(sign),
                    "OFF",
                    profile.parse_mac_on_off,
                )
                # 3. DL 流耦合（p.794：stream-1 设置应用到全部 DL 流）
                _confirm(
                    "DL_STREAM_COUPLING",
                    "dl_stream_coupling",
                    profile.mac_dl_stream_coupling_on(sign),
                    profile.mac_dl_stream_coupling_query(sign),
                    "ON",
                    profile.parse_mac_on_off,
                )
                # 4. DL RMC 满配行（表 2-38 p.78）
                dl_encoded = rmc_plan.downlink.encoded()
                _confirm(
                    "RMC_DL",
                    "rmc_dl",
                    profile.build_mac_rmc_dl(sign, 1, rmc_plan.downlink),
                    profile.mac_rmc_dl_query(sign, 1),
                    dl_encoded,
                    _parse_rmc("dl"),
                )
                if mimo_layers == 2:
                    # DLEQual 耦合的生效端证据：流 2 必须回读到同一行
                    _confirm(
                        "RMC_DL_STREAM2_COUPLED",
                        "rmc_dl_stream2",
                        None,
                        profile.mac_rmc_dl_query(sign, 2),
                        dl_encoded,
                        _parse_rmc("dl"),
                    )
                _confirm(
                    "RMC_RBPOS_DL",
                    "rmc_rb_position_dl",
                    profile.mac_rbposition_dl_low(sign, 1),
                    profile.mac_rbposition_dl_query(sign, 1),
                    "LOW",
                    lambda raw: profile.parse_mac_rb_position(raw, direction="dl"),
                )
                # 5. UL RMC 满配行（表 2-33 pp.70-71，QPSK 列）
                _confirm(
                    "RMC_UL",
                    "rmc_ul",
                    profile.build_mac_rmc_ul(sign, rmc_plan.uplink),
                    profile.mac_rmc_ul_query(sign),
                    rmc_plan.uplink.encoded(),
                    _parse_rmc("ul"),
                )
                _confirm(
                    "RMC_RBPOS_UL",
                    "rmc_rb_position_ul",
                    profile.mac_rbposition_ul_low(sign),
                    profile.mac_rbposition_ul_query(sign),
                    "LOW",
                    lambda raw: profile.parse_mac_rb_position(raw, direction="ul"),
                )
                # 6. DL MAC padding（p.742；Extended BLER 手册明示前置 §3.1 p.921）
                _confirm(
                    "DL_PADDING",
                    "dl_padding",
                    profile.mac_dl_padding_on(sign),
                    profile.mac_dl_padding_query(sign),
                    "ON",
                    profile.parse_mac_on_off,
                )
                # 7. DL HARQ：NHT（p.784）存在但 DL HARQ 组需 KS510/KS512
                #    （pp.783-784 Options）→ 选件域不写，仅探测 ENABle 记档。
                skipped.append("HARQ_DL_NHT")
                harq_note = "探测不可用"
                try:
                    harq_raw = self._query(
                        profile.mac_harq_dl_enable_query(sign)
                    )
                    harq_gate = _group_gate()
                    if harq_gate is None:
                        harq_note = (
                            f"观测 ENABle={profile.parse_mac_on_off(harq_raw)}"
                        )
                    else:
                        harq_note = f"探测被拒: {harq_gate}"
                except Exception as exc:  # noqa: BLE001 — 探测失败≠配置失败
                    harq_note = f"探测异常: {exc}"
                    try:
                        self._query(CmwScpiCommands.ERR)
                    except Exception as drain_exc:  # noqa: BLE001
                        # 排空尽力而为；吞异常不吞信息（G4）
                        logger.warning(
                            "[CMW500] HARQ probe error-queue drain failed: %s",
                            drain_exc,
                        )
                field_rows.append(
                    (
                        "harq_max_trans",
                        harq_max_trans,
                        None,
                        "unknown",
                        "HARQ:DL:NHT（p.784）存在；手册只在 ENABle（p.783-784）"
                        "挂 KS510/KS512 Options，NHT 条目无 Options 行 ——"
                        "『组整体选件门控』为 ⚠ 推断（ENABle 不开则 NHT 无意义），"
                        f"保守不驱动；{harq_note}",
                    )
                )

                summary_error: Optional[str] = None
                if rejected:
                    reason = (
                        f"CMW500 MAC 配置 {len(rejected)} 组被拒/未确认: "
                        + ", ".join(rejected)
                    )
                    logger.error("[CMW500] %s", reason)
                else:
                    reason = (
                        "CMW500 MAC 配置全组写入并经权威回读确认: "
                        f"STYPe=RMC, DL={dl_encoded}@LOW, "
                        f"UL={rmc_plan.uplink.encoded()}@LOW, "
                        f"coupling=ON, padding=ON ({live_bw_token}, FDD)"
                    )
                    logger.info("[CMW500] %s", reason)
                return _result(summary_error, exchanges, reason=reason)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[CMW500] configure_mac_throughput_test failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            # 同 UXM 契约：异常不裸抛也不谎报 —— 已发/已拒如实带回，
            # error 非空使 ok=False；没轮到发的组不冒充 skipped。
            return _result(
                f"下发过程中出错: {e}",
                (),
                reason=f"CMW500 MAC 配置中断: {e}",
            )

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

    def _build_attach_receipt(
        self,
        exchanges: list[Any],
        *,
        operation_succeeded: bool,
    ) -> BaseStationAttachReceipt:
        """Map only this operation's existing CMW readbacks to attach stages."""

        cell_set = self._fmt(CmwScpiCommands.CELL_STATE_SET)
        attach_exchanges: list[Any] = []
        for exchange in exchanges:
            if exchange.command == f"{cell_set} OFF":
                break
            attach_exchanges.append(exchange)

        cell_query = self._fmt(CmwScpiCommands.CELL_STATE_ALL)
        ps_query = self._fmt(CmwScpiCommands.PS_STATE)
        connect_command = f"{self._fmt(CmwScpiCommands.PS_ACTION)} CONNect"
        connect_index = next(
            (
                index
                for index, exchange in enumerate(attach_exchanges)
                if exchange.command == connect_command
            ),
            None,
        )
        before_connect = (
            attach_exchanges
            if connect_index is None
            else attach_exchanges[:connect_index]
        )
        after_connect = (
            [] if connect_index is None else attach_exchanges[connect_index + 1 :]
        )

        def _queries(rows: list[Any], command: str) -> list[Any]:
            return [
                exchange
                for exchange in rows
                if exchange.command == command
                and exchange.result_type == "response"
                and isinstance(exchange.response, str)
            ]

        def _stage(
            stage: str,
            *,
            rows: list[Any],
            parser,
            achieved,
            achieved_reason: str,
            not_achieved_reason: str,
        ) -> BaseStationAttachStageReceipt:
            capability = next(
                item
                for item in self.adapter_manifest.attach_stages
                if item.stage == stage
            )
            if capability.evidence == "unavailable":
                return BaseStationAttachStageReceipt(
                    stage=stage,
                    requested=True,
                    applied=None,
                    status="unknown",
                    evidence="unavailable",
                    reason=capability.reason,
                )
            parsed_rows = [
                (exchange, parser(exchange.response)) for exchange in rows
            ]
            matching = [
                exchange
                for exchange, parsed in parsed_rows
                if parsed is not None and achieved(parsed)
            ]
            if matching:
                exchange = matching[-1]
                return BaseStationAttachStageReceipt(
                    stage=stage,
                    requested=True,
                    applied=True,
                    status="confirmed",
                    evidence=capability.evidence,
                    reason=achieved_reason,
                    exchange_ids=(exchange.exchange_id,),
                )
            known = [
                exchange for exchange, parsed in parsed_rows if parsed is not None
            ]
            if known:
                exchange = known[-1]
                return BaseStationAttachStageReceipt(
                    stage=stage,
                    requested=True,
                    applied=False,
                    status="confirmed",
                    evidence=capability.evidence,
                    reason=not_achieved_reason,
                    exchange_ids=(exchange.exchange_id,),
                )
            return BaseStationAttachStageReceipt(
                stage=stage,
                requested=True,
                applied=None,
                status="unknown",
                evidence=capability.evidence,
                reason=f"{stage} readback was not available in this attach operation",
            )

        stages = (
            _stage(
                "cell_ready",
                rows=_queries(attach_exchanges, cell_query),
                parser=self._parse_cell_all,
                achieved=lambda value: value == ("ON", "ADJUSTED"),
                achieved_reason="CMW500 reported CELL ON,ADJUSTED",
                not_achieved_reason="CMW500 cell state did not reach ON,ADJUSTED",
            ),
            _stage(
                "ue_registered",
                rows=_queries(before_connect, ps_query),
                parser=self._parse_ps_state,
                achieved=lambda value: value == "ATTACHED",
                achieved_reason="CMW500 reported PS ATTACHED",
                not_achieved_reason="CMW500 PS state did not reach ATTACHED",
            ),
            BaseStationAttachStageReceipt(
                stage="rrc_connected",
                requested=True,
                applied=None,
                status="unknown",
                evidence="unavailable",
                reason=next(
                    item.reason
                    for item in self.adapter_manifest.attach_stages
                    if item.stage == "rrc_connected"
                ),
            ),
            _stage(
                "data_bearer_established",
                rows=_queries(after_connect, ps_query),
                parser=self._parse_ps_state,
                achieved=lambda value: value == "CONNECTED",
                achieved_reason="CMW500 reported PS CONNECTED",
                not_achieved_reason=(
                    "CMW500 PS state did not reach CONNECTED after connect action"
                ),
            ),
        )
        return BaseStationAttachReceipt(
            schema_version=1,
            adapter_id=self.adapter_id,
            stages=stages,
            reason=(
                "CMW500 attach terminal stage confirmed"
                if operation_succeeded
                else "CMW500 attach terminal stage was not confirmed"
            ),
            simulated=False,
        )

    async def attach(self, timeout_s: float = 60.0) -> BaseStationAttachReceipt:
        with capture_scpi_exchanges() as exchanges:
            operation_succeeded = await self._run_attach_operation(timeout_s)
        return self._build_attach_receipt(
            exchanges,
            operation_succeeded=operation_succeeded,
        )

    async def _run_attach_operation(self, timeout_s: float = 60.0) -> bool:
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
        request: BaseStationMeasurementWindowRequest,
    ) -> BaseStationMeasurementWindow:
        """采集同一 Extended BLER 生命周期内的 DL throughput 与 BLER。

        生命周期与命令取自 R&S CMW LTE UE User Manual 1173.9628.02-41：
        §3.4.2 printed p.950-951（ABORT/OFF、INIT/RUN、STOP/RDY）以及
        §3.4.4 printed p.957-959（Absolute/Relative 字段与单位）。
        """

        if not isinstance(request, BaseStationMeasurementWindowRequest):
            raise TypeError("CMW500 measurement requires a frozen window request")
        if request.scope != "pcell":
            raise ValueError("CMW500 Extended BLER window supports pcell scope only")
        if (
            request.lifecycle != "authoritative_closed"
            or request.cardinality != "single"
            or request.expected_window_count != 1
        ):
            raise ValueError("CMW500 window request disagrees with its frozen manifest")
        throughput_scope = ThroughputMetrics.SCOPE_PCELL

        started_at = datetime.now(timezone.utc)
        window_id = uuid4().hex
        preclear_off_confirmed = False
        window_configuration_confirmed = False
        running_confirmed = False
        ready_confirmed = False
        closed_off_confirmed = False
        ue_connected_before = False
        ue_connected_after = False
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
                ue_connected_before = (
                    await self.get_cell_state() is CellState.CONNECTED
                )
                if not ue_connected_before:
                    lifecycle_failures.append(
                        "UE link was not CONNECTED before the measurement window"
                    )
                else:
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
                ue_connected_after = (
                    await self.get_cell_state() is CellState.CONNECTED
                )
                if not ue_connected_after:
                    lifecycle_failures.append(
                        "UE link was not CONNECTED after the measurement window"
                    )

        lifecycle_confirmed = all(
            (
                preclear_off_confirmed,
                window_configuration_confirmed,
                running_confirmed,
                ready_confirmed,
                closed_off_confirmed,
                ue_connected_before,
                ue_connected_after,
            )
        )
        if not lifecycle_confirmed:
            throughput_mbps = None
            bler_percent = None

        metrics = ThroughputMetrics(
            dl_throughput_mbps=throughput_mbps,
            dl_bler=bler_percent,
            throughput_scope=throughput_scope,
            registered_values={
                "dl_throughput_mbps": throughput_mbps,
                "dl_bler_percent": bler_percent,
            },
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
                "ue_connected_before": ue_connected_before,
                "ue_connected_after": ue_connected_after,
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
        trust_exchange_ids = tuple(exchange_ids)
        trust = BaseStationMeasurementWindowTrust(
            schema_version=1,
            request=request,
            request_digest=request.digest,
            stages=tuple(
                BaseStationMeasurementStageReceipt(
                    stage=stage,
                    status="confirmed" if confirmed else "unknown",
                    reason=(
                        f"{stage} lifecycle confirmed"
                        if confirmed
                        else f"{stage} lifecycle was not confirmed"
                    ),
                    exchange_ids=trust_exchange_ids if confirmed else (),
                )
                for stage, confirmed in (
                    ("clear", preclear_off_confirmed),
                    ("run", running_confirmed),
                    ("ready", ready_confirmed),
                    ("closed", closed_off_confirmed),
                )
            ),
            simulated=False,
            exchange_ids=trust_exchange_ids,
            reason=reason,
            context_confirmed=lifecycle_confirmed,
        )
        metric_registry = self.resolve_metric_registry()
        metric_observations = self.build_metric_observations(
            registry=metric_registry,
            metrics=metrics,
            scope="pcell",
            exchanges=exchanges,
            query_commands={
                "dl_throughput_mbps": (
                    Cmw500LteCommandProfile.ebler_absolute_query(
                        self._sign_channel
                    )
                ),
                "dl_bler_percent": (
                    Cmw500LteCommandProfile.ebler_relative_query(
                        self._sign_channel
                    )
                ),
            },
            simulated=False,
        )
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
            confirmed=trust.formally_confirmed,
            reason=reason,
            trust=trust,
            metric_registry=metric_registry,
            metric_observations=metric_observations,
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

        # 当前 CMW500 对 UEReport:SINR? 返回 -113 Undefined header，且仓库
        # 没有可核对的厂商手册出处。诊断监控保持 unknown，不向真机猜发命令。

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
        live_state = await self.get_cell_state()
        info = {
            "connected": live_state is CellState.CONNECTED,
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
                        "TM8", "TM9",
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
