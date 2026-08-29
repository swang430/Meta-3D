"""R&S CMW500 LTE 2x2 routing and Extended BLER command profile.

Only commands whose response contracts are cited from the vendor manual live
here.  The same builders are used by real and diagnostic transports.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class CmwCommandSpec:
    template: str
    source_reference: str
    purpose: str
    minimum_firmware: str | None = None
    required_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class CmwNx2Route:
    pcc_bb_board: str
    rx_connector: str
    rx_converter: str
    tx1_connector: str
    tx1_converter: str
    tx2_connector: str
    tx2_converter: str


@dataclass(frozen=True)
class CmwNx2RouteReadback:
    scenario: str
    # User Manual 1173.9628.02-41, printed p.459-460: this field is reserved
    # for future use and its returned value is not relevant.  It is not the
    # configured PCC baseband board.
    controller: str
    rx_connector: str
    rx_converter: str
    tx1_connector: str
    tx1_converter: str
    tx2_connector: str
    tx2_converter: str


@dataclass(frozen=True)
class CmwRmcSelection:
    """One manual-cited RMC parameter row: number of RBs, modulation, TBS index.

    Token vocabulary: R&S CMW LTE UE User Manual 1173.9628.02-41, printed
    pp.799-801 (`RMC:DL<s>` / `RMC:UL` parameter enums).
    """

    number_rb: str
    modulation: str
    tbs_index: str

    def encoded(self) -> str:
        return f"{self.number_rb},{self.modulation},{self.tbs_index}"


@dataclass(frozen=True)
class CmwLteFullRbRmcPlan:
    """Full-RB-allocation DL/UL RMC rows for one LTE cell bandwidth."""

    downlink: CmwRmcSelection
    uplink: CmwRmcSelection


# P2-51: full-allocation RMC rows per bandwidth token, copied row-by-row from
# the vendor manual and visually re-checked against the PDF original:
#   · DL: Table 2-38 "DL RMCs for FDD, multiple TX antennas" (§2.2.19.4,
#     printed p.78) — per bandwidth the full-RB row with the highest
#     modulation that needs no option (DL 256-QAM needs KS504/KS554 and
#     1024-QAM needs KS505/KS555, printed p.800 — deliberately not used).
#   · UL: Table 2-33 "UL RMCs for FDD and TDD, contiguous" (§2.2.19.1,
#     printed p.70-71) — QPSK column (UL 64/256-QAM need KS504/KS554,
#     printed p.70); 15 RB carries the table note "6 for 3 MHz, else 5".
# ⚠ FDD only.  The TDD rows (Table 2-39, printed p.78-79) additionally need
#   the RMC version selector for ambiguous RMCs (printed p.803); the TDD
#   formal path is not implemented in P2-51 and callers must fail loudly.
CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH: dict[str, CmwLteFullRbRmcPlan] = {
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


@dataclass(frozen=True)
class CmwExtendedBlerAbsolute:
    reliability: int
    ack_count: int
    nack_count: int
    subframe_count: int
    throughput_average_kbit_per_s: float
    throughput_minimum_kbit_per_s: float
    throughput_maximum_kbit_per_s: float
    dtx_count: int
    scheduled_count: int
    median_cqi: int


@dataclass(frozen=True)
class CmwExtendedBlerRelative:
    reliability: int
    ack_percent: float
    nack_percent: float
    bler_percent: float
    throughput_average_percent: float
    dtx_percent: float


_LTE_MANUAL = "R&S CMW LTE UE User Manual 1173.9628.02-41"

# 查询形通则（P2-51）：手册 §1.2.4, printed p.15 —— "Most commands have a
# command form and a query form. Exceptions are marked by 'Setting only',
# 'Query only' or 'Event'."  下方 mac_* 查询形所引用的命令均无 Setting only
# 标记；查询**响应**的字面形态手册未逐条给出 → 解析器按严格白名单 + 错误
# 队列核对处理（同 rs_fsva 的「⚠ 推断」形态），真机复验见取证清单 §7。
_QUERY_FORM_RULE = f"{_LTE_MANUAL}, §1.2.4, printed p.15 (query-form rule)"

# Every literal below is adjacent to an auditable vendor-manual reference.
CMW500_LTE_COMMANDS: dict[str, CmwCommandSpec] = {
    "route_nx2": CmwCommandSpec(
        template="ROUTe:LTE:SIGN{i}:SCENario:TRO:FLEXible",
        source_reference=f"{_LTE_MANUAL}, §2.6.8.1, printed p.630-631",
        purpose="Select the LTE 1CC-nx2 internal signal route",
        minimum_firmware="V3.5.40",
        required_options=("KS520",),
    ),
    "route_nx2_query": CmwCommandSpec(
        template="ROUTe:LTE:SIGN{i}:SCENario:TRO:FLEXible?",
        source_reference=(
            f"{_LTE_MANUAL}, §2.6.8.1, printed p.630-631; "
            "R&S Remote Control via SCPI 1179.4592.02-04, §3.6, "
            "printed p.22"
        ),
        purpose="Read all seven configured LTE 1CC-nx2 route parameters",
        minimum_firmware="V3.5.40",
        required_options=("KS520",),
    ),
    "route_query": CmwCommandSpec(
        template="ROUTe:LTE:SIGN{i}?",
        source_reference=f"{_LTE_MANUAL}, §2.6.2.2, printed p.459-460",
        purpose="Read the active LTE scenario and its relevant RX/TX paths",
    ),
    "ebler_absolute_query": CmwCommandSpec(
        template="FETCh:LTE:SIGN{i}:EBLer:PCC:ABSolute?",
        source_reference=f"{_LTE_MANUAL}, §3.4.4, printed p.957-958",
        purpose="Read absolute PCC Extended BLER counts and throughput in kbit/s",
        minimum_firmware="V3.0.10",
    ),
    "ebler_relative_query": CmwCommandSpec(
        template="FETCh:LTE:SIGN{i}:EBLer:PCC:RELative?",
        source_reference=f"{_LTE_MANUAL}, §3.4.4, printed p.959",
        purpose="Read relative PCC BLER and throughput percentages",
        minimum_firmware="V3.0.30",
    ),
    "ebler_init": CmwCommandSpec(
        template="INITiate:LTE:SIGN{i}:EBLer",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.950",
        purpose="Start or restart Extended BLER and enter RUN",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_stop": CmwCommandSpec(
        template="STOP:LTE:SIGN{i}:EBLer",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.950",
        purpose="Stop Extended BLER in RDY while retaining results",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_abort": CmwCommandSpec(
        template="ABORt:LTE:SIGN{i}:EBLer",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.950",
        purpose="Abort Extended BLER to OFF, clear values, and release resources",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_state_query": CmwCommandSpec(
        template="FETCh:LTE:SIGN{i}:EBLer:STATe?",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.951",
        purpose="Read the Extended BLER OFF, RUN, or RDY state",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_timeout": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:EBLer:TOUT",
        source_reference=f"{_LTE_MANUAL}, §3.4.3, printed p.952",
        purpose="Disable a retained early timeout before a bounded continuous window",
        minimum_firmware="V2.0.10",
    ),
    "ebler_repetition": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:EBLer:REPetition",
        source_reference=f"{_LTE_MANUAL}, §3.3.3 and §3.4.3, printed p.941, 953",
        purpose="Select continuous repetition so STOP owns the requested window end",
        minimum_firmware="V3.0.30",
    ),
    "ebler_stop_condition": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:EBLer:SCONdition",
        source_reference=f"{_LTE_MANUAL}, §3.3.3 and §3.4.3, printed p.941, 953",
        purpose="Disable retained confidence-level early termination",
        minimum_firmware="V3.0.30",
    ),
    # ------------------------------------------------------------------
    # P2-51: LTE MAC/调度配置（正式 throughput/BLER 前置）。
    # 取证清单：docs/plans/2026-08-30-p2-51-cmw500-mac-scheduling-evidence.md
    # ------------------------------------------------------------------
    "mac_sched_type": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:STYPe",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.743",
        purpose=(
            "Select the RMC scheduling type; RMC carries no option note while "
            "UDCH/UDTT/SPS/CQI need KS510(/KS512) and stay diagnostic"
        ),
        minimum_firmware="V3.0.10",
    ),
    "mac_sched_type_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:STYPe?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.743; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the configured scheduling type",
        minimum_firmware="V3.0.10",
    ),
    "mac_rmc_dl": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:DL{s}",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.799-800",
        purpose=(
            "Configure the DL RMC (#RB, modulation, TBS index); DL QPSK/Q16/Q64 "
            "need no option (256/1024-QAM would need KS504/KS505 families)"
        ),
        minimum_firmware="V3.0.20",
    ),
    "mac_rmc_dl_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:DL{s}?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.799-800; "
            f"{_QUERY_FORM_RULE}"
        ),
        purpose="Read back the configured DL RMC per stream",
        minimum_firmware="V3.0.20",
    ),
    "mac_rmc_ul": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:UL",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.800-801",
        purpose=(
            "Configure the contiguous UL RMC; UL QPSK/Q16 need no option "
            "(UL 64/256-QAM would need KS504/KS554)"
        ),
        minimum_firmware="V3.0.20",
    ),
    "mac_rmc_ul_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:UL?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.800-801; "
            f"{_QUERY_FORM_RULE}"
        ),
        purpose="Read back the configured UL RMC",
        minimum_firmware="V3.0.20",
    ),
    "mac_rmc_rbpos_dl": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:RBPosition:DL{s}",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.801-802",
        purpose="Select the DL RB start position (same value for both streams)",
        minimum_firmware="V3.2.50",
    ),
    "mac_rmc_rbpos_dl_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:RBPosition:DL{s}?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.801-802; "
            f"{_QUERY_FORM_RULE}"
        ),
        purpose="Read back the DL RB start position",
        minimum_firmware="V3.2.50",
    ),
    "mac_rmc_rbpos_ul": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:RBPosition:UL",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.802",
        purpose="Select the UL RB start position for contiguous allocation",
        minimum_firmware="V3.0.20",
    ),
    "mac_rmc_rbpos_ul_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:RBPosition:UL?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.802; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the UL RB start position",
        minimum_firmware="V3.0.20",
    ),
    "mac_dl_stream_coupling": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:DLEQual",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.794",
        purpose=(
            "Couple all MIMO DL streams so the stream-1 RMC settings apply to "
            "all DL streams"
        ),
        minimum_firmware="V3.2.60",
    ),
    "mac_dl_stream_coupling_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:DLEQual?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.794; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the DL stream coupling state",
        minimum_firmware="V3.2.60",
    ),
    "mac_dl_padding": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:DLPadding",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.742; BLER prerequisite "
            "§3.1 printed p.921 and §3.3.1 printed p.940"
        ),
        purpose=(
            "Activate DL MAC padding — the manual-explicit Extended BLER "
            "prerequisite in test mode"
        ),
        minimum_firmware="V1.0.15.20",
    ),
    "mac_dl_padding_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:DLPadding?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.742; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the DL MAC padding state",
        minimum_firmware="V1.0.15.20",
    ),
    # ⚠ 只查询不写：multi-cluster 特性本身选件门控（KS510/KS512, printed
    #   pp.743-744），写 OFF 也属于选件域盲写；查询仅作 contiguous 前提确认，
    #   查询被拒时调用方 fail-closed（真机复验项，见取证清单 §7）。
    "mac_ul_multicluster_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:MCLuster:UL?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.743-744 "
            "(feature option-gated by KS510/KS512; read-only probe here); "
            f"{_QUERY_FORM_RULE}"
        ),
        purpose=(
            "Confirm contiguous UL allocation (OFF) before trusting the "
            "contiguous UL RMC write"
        ),
        minimum_firmware="V3.5.20",
    ),
    # ⚠ 只探测不写。手册明文只在 HARQ:DL:ENABle（p.783-784）挂 Options
    #   KS510/KS512；NHT（p.784）条目无 Options 行 ——「配置组整体选件门控」
    #   是 ⚠ 推断（ENABle 不开则 NHT 无意义），非手册原文。探测失败只记档，
    #   不影响配置判定。
    "mac_harq_dl_enable_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:HARQ:DL:ENABle?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.783-784 "
            "(DL HARQ group option-gated by KS510/KS512; read-only probe); "
            f"{_QUERY_FORM_RULE}"
        ),
        purpose="Record the observed DL HARQ enable state without driving it",
        minimum_firmware="V3.0.50",
    ),
}


def _channel(value: int) -> int:
    if value not in (1, 2):
        raise ValueError("CMW LTE signaling channel must be 1 or 2")
    return value


def _dl_stream(value: int) -> int:
    # Manual pp.799-802: the DL stream suffix <s> is exactly 1..2.
    if value not in (1, 2):
        raise ValueError("CMW LTE DL RMC stream suffix must be 1 or 2")
    return value


# P2-51 readback token vocabularies — copied verbatim from the manual enums.
# NumberRB: printed p.799 (DL) / p.800 (UL share the same list).
RMC_NUMBER_RB_TOKENS = frozenset(
    {"ZERO"}
    | {
        f"N{n}"
        for n in (
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 16, 17, 18, 20, 21, 24,
            25, 27, 30, 32, 36, 40, 42, 45, 48, 50, 54, 60, 64, 72, 75, 80,
            81, 83, 90, 92, 96, 100,
        )
    }
)
# Modulation: DL printed p.799 (QPSK|Q16|Q64|Q256|Q1024), UL printed p.800
# (QPSK|Q16|Q64|Q256).
RMC_DL_MODULATION_TOKENS = frozenset({"QPSK", "Q16", "Q64", "Q256", "Q1024"})
RMC_UL_MODULATION_TOKENS = frozenset({"QPSK", "Q16", "Q64", "Q256"})
# TBS index: printed p.799-800 (ZERO|T1..T37; KEEP is a write-side helper
# and must never come back on a readback).
RMC_TBS_INDEX_TOKENS = frozenset({"ZERO"} | {f"T{n}" for n in range(1, 38)})
# RB positions: DL printed p.801 closed enum; UL printed p.802 long enum —
# the parser accepts the documented shapes, the driver only ever sends LOW.
RMC_RB_POSITION_DL_TOKENS = frozenset(
    {"LOW", "HIGH", "P5", "P10", "P23", "P35", "P48"}
)
_RB_POSITION_UL_RE = re.compile(r"(LOW|HIGH|MID|P\d{1,2})\Z")


_ROUTE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")


def normalize_cmw_route_token(value: str, name: str) -> str:
    """Accept only the manual's bare alphanumeric signal-path enum tokens.

    R&S CMW LTE UE User Manual 1173.9628.02-41, §2.6.1.4,
    printed p.363-365 lists the path-selection values as unquoted
    alphanumeric enumerations.  Rejecting every other character prevents a
    persisted route field from becoming an additional SCPI program unit.
    """

    token = value.strip()
    if not _ROUTE_TOKEN_RE.fullmatch(token) or token.upper() == "NAV":
        raise ValueError(f"invalid CMW route token: {name}")
    return token


def _csv(response: str, count: int) -> list[str]:
    values = [value.strip() for value in response.strip().split(",")]
    if len(values) != count or any(not value for value in values):
        raise ValueError(f"expected exactly {count} CMW response fields")
    return values


def _finite(value: str, name: str) -> float:
    if value.upper() == "NAV":
        raise ValueError(f"CMW returned NAV for {name}")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"CMW returned non-numeric {name}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"CMW returned non-finite {name}")
    return parsed


def _integer(value: str, name: str) -> int:
    parsed = _finite(value, name)
    if not parsed.is_integer():
        raise ValueError(f"CMW returned non-integer {name}")
    return int(parsed)


def _reliability(value: str) -> int:
    reliability = _integer(value, "reliability")
    # Manual pp.945-949: 0 is the only "no error" value.  Every other code
    # describes incomplete, impaired, unavailable, or otherwise invalid data.
    if reliability != 0:
        raise ValueError(f"CMW measurement reliability is {reliability}, not 0")
    return reliability


def _percent(value: str, name: str) -> float:
    parsed = _finite(value, name)
    if parsed < 0.0 or parsed > 100.0:
        raise ValueError(f"CMW returned out-of-range {name}")
    return parsed


class Cmw500LteCommandProfile:
    """Builders and strict response parsers for the sourced command subset."""

    @staticmethod
    def _format(name: str, sign_channel: int) -> str:
        return CMW500_LTE_COMMANDS[name].template.format(i=_channel(sign_channel))

    @classmethod
    def build_route_nx2(cls, sign_channel: int, route: CmwNx2Route) -> str:
        values = (
            (route.pcc_bb_board, "pcc_bb_board"),
            (route.rx_connector, "rx_connector"),
            (route.rx_converter, "rx_converter"),
            (route.tx1_connector, "tx1_connector"),
            (route.tx1_converter, "tx1_converter"),
            (route.tx2_connector, "tx2_connector"),
            (route.tx2_converter, "tx2_converter"),
        )
        encoded = ",".join(
            normalize_cmw_route_token(value, name) for value, name in values
        )
        return f"{cls._format('route_nx2', sign_channel)} {encoded}"

    @classmethod
    def route_query(cls, sign_channel: int) -> str:
        return cls._format("route_query", sign_channel)

    @classmethod
    def route_nx2_query(cls, sign_channel: int) -> str:
        return cls._format("route_nx2_query", sign_channel)

    @classmethod
    def ebler_absolute_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_absolute_query", sign_channel)

    @classmethod
    def ebler_relative_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_relative_query", sign_channel)

    @classmethod
    def ebler_init(cls, sign_channel: int) -> str:
        return cls._format("ebler_init", sign_channel)

    @classmethod
    def ebler_stop(cls, sign_channel: int) -> str:
        return cls._format("ebler_stop", sign_channel)

    @classmethod
    def ebler_abort(cls, sign_channel: int) -> str:
        return cls._format("ebler_abort", sign_channel)

    @classmethod
    def ebler_state_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_state_query", sign_channel)

    @classmethod
    def ebler_timeout_disabled(cls, sign_channel: int) -> str:
        return f"{cls._format('ebler_timeout', sign_channel)} 0"

    @classmethod
    def ebler_repetition_continuous(cls, sign_channel: int) -> str:
        return f"{cls._format('ebler_repetition', sign_channel)} CONTinuous"

    @classmethod
    def ebler_stop_condition_none(cls, sign_channel: int) -> str:
        return f"{cls._format('ebler_stop_condition', sign_channel)} NONE"

    # ------------------------------------------------------------------
    # P2-51: LTE MAC/调度配置 builder（wire 形态唯一出口，白名单式）
    # ------------------------------------------------------------------

    @staticmethod
    def _format_stream(name: str, sign_channel: int, stream: int) -> str:
        return CMW500_LTE_COMMANDS[name].template.format(
            i=_channel(sign_channel), s=_dl_stream(stream)
        )

    @classmethod
    def mac_scheduling_type_rmc(cls, sign_channel: int) -> str:
        # p.743: Type=RMC is the option-free 3GPP reference measurement channel.
        return f"{cls._format('mac_sched_type', sign_channel)} RMC"

    @classmethod
    def mac_scheduling_type_query(cls, sign_channel: int) -> str:
        return cls._format("mac_sched_type_query", sign_channel)

    @classmethod
    def build_mac_rmc_dl(
        cls, sign_channel: int, stream: int, selection: CmwRmcSelection
    ) -> str:
        if selection.number_rb not in RMC_NUMBER_RB_TOKENS:
            raise ValueError("CMW DL RMC number-RB token is not documented")
        if selection.modulation not in RMC_DL_MODULATION_TOKENS:
            raise ValueError("CMW DL RMC modulation token is not documented")
        if selection.tbs_index not in RMC_TBS_INDEX_TOKENS:
            raise ValueError("CMW DL RMC TBS token is not documented")
        return (
            f"{cls._format_stream('mac_rmc_dl', sign_channel, stream)} "
            f"{selection.encoded()}"
        )

    @classmethod
    def mac_rmc_dl_query(cls, sign_channel: int, stream: int) -> str:
        return cls._format_stream("mac_rmc_dl_query", sign_channel, stream)

    @classmethod
    def build_mac_rmc_ul(
        cls, sign_channel: int, selection: CmwRmcSelection
    ) -> str:
        if selection.number_rb not in RMC_NUMBER_RB_TOKENS:
            raise ValueError("CMW UL RMC number-RB token is not documented")
        if selection.modulation not in RMC_UL_MODULATION_TOKENS:
            raise ValueError("CMW UL RMC modulation token is not documented")
        if selection.tbs_index not in RMC_TBS_INDEX_TOKENS:
            raise ValueError("CMW UL RMC TBS token is not documented")
        return (
            f"{cls._format('mac_rmc_ul', sign_channel)} {selection.encoded()}"
        )

    @classmethod
    def mac_rmc_ul_query(cls, sign_channel: int) -> str:
        return cls._format("mac_rmc_ul_query", sign_channel)

    @classmethod
    def mac_rbposition_dl_low(cls, sign_channel: int, stream: int) -> str:
        # p.72: LOW/HIGH are always allowed; with a full-RB allocation the
        # position is degenerate and LOW is the deterministic choice.
        return f"{cls._format_stream('mac_rmc_rbpos_dl', sign_channel, stream)} LOW"

    @classmethod
    def mac_rbposition_dl_query(cls, sign_channel: int, stream: int) -> str:
        return cls._format_stream("mac_rmc_rbpos_dl_query", sign_channel, stream)

    @classmethod
    def mac_rbposition_ul_low(cls, sign_channel: int) -> str:
        return f"{cls._format('mac_rmc_rbpos_ul', sign_channel)} LOW"

    @classmethod
    def mac_rbposition_ul_query(cls, sign_channel: int) -> str:
        return cls._format("mac_rmc_rbpos_ul_query", sign_channel)

    @classmethod
    def mac_dl_stream_coupling_on(cls, sign_channel: int) -> str:
        return f"{cls._format('mac_dl_stream_coupling', sign_channel)} ON"

    @classmethod
    def mac_dl_stream_coupling_query(cls, sign_channel: int) -> str:
        return cls._format("mac_dl_stream_coupling_query", sign_channel)

    @classmethod
    def mac_dl_padding_on(cls, sign_channel: int) -> str:
        return f"{cls._format('mac_dl_padding', sign_channel)} ON"

    @classmethod
    def mac_dl_padding_query(cls, sign_channel: int) -> str:
        return cls._format("mac_dl_padding_query", sign_channel)

    @classmethod
    def mac_ul_multicluster_query(cls, sign_channel: int) -> str:
        return cls._format("mac_ul_multicluster_query", sign_channel)

    @classmethod
    def mac_harq_dl_enable_query(cls, sign_channel: int) -> str:
        return cls._format("mac_harq_dl_enable_query", sign_channel)

    @staticmethod
    def parse_route_readback(response: str) -> CmwNx2RouteReadback:
        values = _csv(response, 8)
        if values[0].upper() != "TRO":
            raise ValueError("CMW route is not the LTE 1CC-nx2 TRO scenario")
        for index, name in enumerate(
            ("rx_connector", "rx_converter", "tx1_connector", "tx1_converter",
             "tx2_connector", "tx2_converter"),
            start=2,
        ):
            normalize_cmw_route_token(values[index], name)
        return CmwNx2RouteReadback(*values)

    @staticmethod
    def parse_route_nx2_readback(response: str) -> CmwNx2Route:
        names = (
            "pcc_bb_board",
            "rx_connector",
            "rx_converter",
            "tx1_connector",
            "tx1_converter",
            "tx2_connector",
            "tx2_converter",
        )
        values = _csv(response, len(names))
        normalized = [
            normalize_cmw_route_token(value, name)
            for value, name in zip(values, names, strict=True)
        ]
        return CmwNx2Route(*normalized)

    @staticmethod
    def parse_ebler_absolute(response: str) -> CmwExtendedBlerAbsolute:
        values = _csv(response, 10)
        return CmwExtendedBlerAbsolute(
            reliability=_reliability(values[0]),
            ack_count=_integer(values[1], "ACK count"),
            nack_count=_integer(values[2], "NACK count"),
            subframe_count=_integer(values[3], "subframe count"),
            throughput_average_kbit_per_s=_finite(values[4], "average throughput"),
            throughput_minimum_kbit_per_s=_finite(values[5], "minimum throughput"),
            throughput_maximum_kbit_per_s=_finite(values[6], "maximum throughput"),
            dtx_count=_integer(values[7], "DTX count"),
            scheduled_count=_integer(values[8], "scheduled count"),
            median_cqi=_integer(values[9], "median CQI"),
        )

    @staticmethod
    def parse_ebler_relative(response: str) -> CmwExtendedBlerRelative:
        values = _csv(response, 6)
        return CmwExtendedBlerRelative(
            reliability=_reliability(values[0]),
            ack_percent=_percent(values[1], "ACK percent"),
            nack_percent=_percent(values[2], "NACK percent"),
            bler_percent=_percent(values[3], "BLER percent"),
            throughput_average_percent=_percent(values[4], "throughput percent"),
            dtx_percent=_percent(values[5], "DTX percent"),
        )

    @staticmethod
    def parse_ebler_state(response: str) -> str:
        state = response.strip()
        if state not in {"OFF", "RUN", "RDY"}:
            raise ValueError(f"unknown CMW Extended BLER state: {state!r}")
        return state

    # ------------------------------------------------------------------
    # P2-51: MAC/调度回读解析（严格白名单；响应字面形态属 ⚠ 推断域，
    # 不在白名单内一律抛错让调用方 fail-loud，真机复验见取证清单 §7）
    # ------------------------------------------------------------------

    @staticmethod
    def parse_mac_scheduling_type(response: str) -> str:
        """Return the scheduling-type token (first CSV field, p.743 enum).

        The query may echo the optional CQI mode as a second field; only the
        first field carries the type.  Anything outside the documented type
        enum is rejected.
        """

        first = response.strip().split(",")[0].strip().upper()
        documented = {
            "RMC", "UDCH", "UDCHANNELS", "UDTT", "UDTTIBASED",
            "CQI", "SPS", "EMAM", "EMAMODE", "EMCS", "EMCSCHED",
        }
        if first not in documented:
            raise ValueError(f"unknown CMW scheduling type readback: {response!r}")
        return first

    @staticmethod
    def parse_mac_rmc_readback(response: str, *, direction: str) -> CmwRmcSelection:
        values = _csv(response, 3)
        number_rb = values[0].strip().upper()
        modulation = values[1].strip().upper()
        tbs_index = values[2].strip().upper()
        modulation_tokens = (
            RMC_DL_MODULATION_TOKENS
            if direction == "dl"
            else RMC_UL_MODULATION_TOKENS
        )
        if direction not in {"dl", "ul"}:
            raise ValueError("RMC readback direction must be dl or ul")
        if number_rb not in RMC_NUMBER_RB_TOKENS:
            raise ValueError(f"undocumented CMW RMC number-RB readback: {response!r}")
        if modulation not in modulation_tokens:
            raise ValueError(f"undocumented CMW RMC modulation readback: {response!r}")
        if tbs_index not in RMC_TBS_INDEX_TOKENS:
            raise ValueError(f"undocumented CMW RMC TBS readback: {response!r}")
        return CmwRmcSelection(number_rb, modulation, tbs_index)

    @staticmethod
    def parse_mac_rb_position(response: str, *, direction: str) -> str:
        token = response.strip().upper()
        if direction == "dl":
            if token not in RMC_RB_POSITION_DL_TOKENS:
                raise ValueError(
                    f"undocumented CMW DL RB position readback: {response!r}"
                )
        elif direction == "ul":
            if not _RB_POSITION_UL_RE.fullmatch(token):
                raise ValueError(
                    f"undocumented CMW UL RB position readback: {response!r}"
                )
        else:
            raise ValueError("RB position direction must be dl or ul")
        return token

    @staticmethod
    def parse_mac_on_off(response: str) -> str:
        """Normalize a boolean-enum readback to ON/OFF.

        The manual documents the parameter enum as OFF|ON; SCPI instruments
        commonly echo booleans as 1/0 as well, so both spellings are accepted
        and anything else is rejected (⚠ 推断域, on-site re-verification item).
        """

        token = response.strip().upper()
        if token in {"ON", "1"}:
            return "ON"
        if token in {"OFF", "0"}:
            return "OFF"
        raise ValueError(f"undocumented CMW ON/OFF readback: {response!r}")
