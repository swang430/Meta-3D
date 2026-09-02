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


def cmw500_lte_formal_options(duplex: str) -> frozenset[str]:
    """一次 LTE **正式**执行所需的整机选件全集（**唯一真值源**）。

    在 P2-56 ② 之前，这套映射在三处各写了一份：驱动的
    `evaluate_lte_2x2_formal_capability`、正式 KPI 准入门
    `base_station_execution_evidence`，以及能力矩阵的
    `satisfying_options` / `required_options`。三份里前两份**都漏了 KS510**
    —— 而 ② 让 TDD 变成可达路径之后，那个漏项会让一台没装 KS510 的机器
    通过准入、跑到 `CELL_ULDL` 那一组才被仪器拒（方向安全，代价是一次上机
    时间）。这里把前两处收敛成一处；矩阵那一份是**声明**，由门与它对账。

    逐项出处（印刷页）：
      · `KS520` —— 2x2 天线配置：p.753 Options 原文「TWO (2x2): R&S CMW-KS520」
      · `KS500` / `KS550` —— 双工：p.366 Options 原文
        「R&S CMW-KS500/-KS550 for FDD/TDD」
      · `KS510` —— **仅 TDD**：`CELL[:PCC]:ULDL` 的 Options 原文是
        「R&S CMW-KS550 **and** R&S CMW-KS510」（pp.687-688），两个都要装。
        `SSUBframe`（p.688）只要 KS550，已被上一行覆盖。
    """

    normalized = duplex.strip().lower() if isinstance(duplex, str) else ""
    if normalized == "fdd":
        return frozenset({"KS520", "KS500"})
    if normalized == "tdd":
        return frozenset({"KS520", "KS550", "KS510"})
    raise ValueError(f"unsupported LTE duplex for formal options: {duplex!r}")


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
    #: P2-56 ②：该带宽在 **TDD** 下选中同一行时，是否必须显式下发
    #: `RMC:VERSion:DL<s>`（p.803）。
    #:
    #: 存的是**要不要指定**，不是**指定成几** —— 表 2-39 的 20 MHz 那行
    #: `0: R.30` 与 `1: R.30-1` **两个都合法**，选哪个是用户意图，由 profile 的
    #: `rmc_version` 携带。把版本值也存进这里会让同一个值有两个源
    #: （计划表与 profile），那正是本片在治的形态。
    tdd_dl_version_required: bool = False


# P2-51: full-allocation RMC rows per bandwidth token, copied row-by-row from
# the vendor manual and visually re-checked against the PDF original:
#   · DL: Table 2-38 "DL RMCs for FDD, multiple TX antennas" (§2.2.19.4,
#     printed p.78) — per bandwidth the full-RB row with the highest
#     modulation that needs no option (DL 256-QAM needs KS504/KS554 and
#     1024-QAM needs KS505/KS555, printed p.800 — deliberately not used).
#   · UL: Table 2-33 "UL RMCs for FDD and TDD, contiguous" (§2.2.19.1,
#     printed p.70-71) — QPSK column (UL 64/256-QAM need KS504/KS554,
#     printed p.70); 15 RB carries the table note "6 for 3 MHz, else 5".
# P2-56 ②: the same rows also serve TDD.  Table 2-39 "DL RMCs for TDD,
#   multiple TX antennas" (printed pp.78-79) was read row by row from the
#   rendered PDF pages (not from a text extraction — `pdftotext` scrambles
#   these tables) and the same selection rule yields the identical DL row for
#   all six bandwidths.
# ⚠ **That identity is a coincidence, not a rule.**  The tables differ in
#   shape: FDD 5 MHz/25 RB has two rows (QPSK/5 and 16-QAM/12) while TDD has
#   only one (16-QAM/12).  Do not restate this as "TDD equals FDD".
# ⚠ Only 20 MHz needs the RMC version selector: in Table 2-39 exactly two rows
#   carry a Version value — 10 MHz/50/16-QAM/13 (`0: R.11` / `1: R.11-1`) and
#   20 MHz/100/16-QAM/13 (`0: R.30` / `1: R.30-1`) — and of those only the
#   20 MHz one is the row this plan selects (10 MHz selects 64-QAM/18, which
#   carries `-`).  See `tdd_dl_version_required`.
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
        # 表 2-39 的 20 MHz/100/16-QAM/13 行带 `0: R.30` / `1: R.30-1`
        tdd_dl_version_required=True,
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
# 'Query only' or 'Event'."  下方引用本通则的查询形（mac_* 与 P1-74 的
# ebler_subframes_query）所对应的命令块均无这些例外标记；查询**响应**的字面
# 形态手册未逐条给出 → 解析器按严格白名单 + 错误队列核对处理（同 rs_fsva 的
# 「⚠ 推断」形态），真机复验见取证清单 §7。
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
    # P1-74：统计基（每 measurement cycle 处理的子帧数）。p.937 的 SCONdition
    # "None" 定义直说「测量按 Repetition 模式与指定的 No. of Subframes 执行」，
    # p.938 与 §3.3.1 示例 p.940 也把它放在 continuous 配置里；p.953 的
    # 「只影响 trace 长度」一句**限定 confidence 模式**（SCONdition CLEVel），
    # 不适用于正式窗口。
    "ebler_subframes": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:EBLer:SFRames",
        source_reference=(
            f"{_LTE_MANUAL}, §3.2.4 printed p.937-938, §3.3.1 printed p.940, "
            f"§3.4.3 printed p.953"
        ),
        purpose=(
            "Drive the number of subframes processed per measurement cycle so "
            "the statistical basis comes from the TestCase, not retained state"
        ),
        minimum_firmware="V3.0.30",
    ),
    "ebler_subframes_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:EBLer:SFRames?",
        source_reference=(
            f"{_LTE_MANUAL}, §3.4.3, printed p.953; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the statistical basis that is actually in effect",
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
    # ── P2-56 ②：LTE TDD 专属命令 ─────────────────────────────────────
    # 属性块逐条本地核对（① 声明半已核过一遍，此处复用同一份取证）。
    # 各行 Firmware 里限定 `SCC<c>` 变体的半句不计：本驱动走 `[:PCC]`。
    "mac_cell_uldl": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CELL:PCC:ULDL",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.687-688",
        purpose="Select the TDD uplink-downlink subframe configuration (0..6)",
        # 手册 Firmware 行 `V3.0.10, V3.0.50 value 0, 2, 3, 4, 6` —— 逐值下限
        # 在能力矩阵里逐格声明；这里取**命令级**下限（能发这条命令的最低固件）。
        minimum_firmware="V3.0.10",
        # Options 原文「R&S CMW-KS550 **and** R&S CMW-KS510」——两个都要
        required_options=("KS510", "KS550"),
    ),
    "mac_cell_uldl_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CELL:PCC:ULDL?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.687-688; "
            f"{_QUERY_FORM_RULE}"
        ),
        purpose="Read back the TDD uplink-downlink subframe configuration",
        minimum_firmware="V3.0.10",
        required_options=("KS510", "KS550"),
    ),
    "mac_cell_ssubframe": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CELL:PCC:SSUBframe",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.688",
        purpose="Select the TDD special subframe configuration (0..9)",
        minimum_firmware="V2.1.20",
        # Options 基线只有 KS550；KS512 只在「value 7 plus extended cyclic
        # prefix / value 9 / carrier-specific」时另需，本驱动放开的是 0..7
        # 且无 cyclic prefix 维度，故不列 KS512。
        required_options=("KS550",),
    ),
    "mac_cell_ssubframe_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CELL:PCC:SSUBframe?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.688; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the TDD special subframe configuration",
        minimum_firmware="V2.1.20",
        required_options=("KS550",),
    ),
    "mac_rmc_version_dl": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:VERSion:DL{s}",
        source_reference=f"{_LTE_MANUAL}, command reference, printed p.803",
        purpose="Disambiguate TDD DL RMCs that share bandwidth/RB/modulation/TBS",
        minimum_firmware="V3.2.70",
        # p.803 该条目**没有** Options 行
    ),
    "mac_rmc_version_dl_query": CmwCommandSpec(
        template="CONFigure:LTE:SIGN{i}:CONNection:PCC:RMC:VERSion:DL{s}?",
        source_reference=(
            f"{_LTE_MANUAL}, command reference, printed p.803; {_QUERY_FORM_RULE}"
        ),
        purpose="Read back the TDD DL RMC version selector",
        minimum_firmware="V3.2.70",
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


# P1-74: `CONFigure:LTE:SIGN<i>:EBLer:SFRames <Subframes>` parameter block,
# printed p.953 — integer, Range 100 to 400E+3, *RST 10E+3.  The reset value is
# recorded so the driver can name the retained-state hazard it is closing; it is
# never used as a fallback (a defaulted statistical basis is the very failure
# P1-74 removes).
EBLER_SUBFRAMES_MIN = 100
EBLER_SUBFRAMES_MAX = 400_000
EBLER_SUBFRAMES_RESET = 10_000


def validate_ebler_subframes(value: object) -> int:
    """Accept only the manual's documented statistical basis; never clamp.

    Clamping an out-of-range request would silently substitute a different
    statistical basis — the exact class of silent KPI corruption this command
    exists to remove.  Out-of-domain requests are rejected so the window can
    fail closed with the requested number still visible in its evidence.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            "CMW Extended BLER subframes must be an integer number of subframes"
        )
    if not EBLER_SUBFRAMES_MIN <= value <= EBLER_SUBFRAMES_MAX:
        raise ValueError(
            f"CMW Extended BLER subframes {value} is outside the documented "
            f"range {EBLER_SUBFRAMES_MIN}..{EBLER_SUBFRAMES_MAX} "
            f"({_LTE_MANUAL}, printed p.953)"
        )
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
# P2-56 ②：整数型回读（ULDL / SSUBframe / RMC:VERSion:DL）。允许可选正号
# 与前后空白，不允许小数、指数、十六进制 —— 手册这三个参数都是 `integer`。
_INTEGER_READBACK_RE = re.compile(r"^[+-]?\d+$")


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

    @classmethod
    def build_ebler_subframes(cls, sign_channel: int, subframes: object) -> str:
        """Encode the execution-frozen statistical basis (printed p.953)."""

        validated = validate_ebler_subframes(subframes)
        return f"{cls._format('ebler_subframes', sign_channel)} {validated}"

    @classmethod
    def ebler_subframes_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_subframes_query", sign_channel)

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

    # ── P2-56 ②：LTE TDD 专属 builder / query ─────────────────────────
    @classmethod
    def build_mac_cell_uldl(cls, sign_channel: int, configuration: int) -> str:
        # pp.687-688: `<UplinkDownlink>` 是 integer，Range `0 to 6`。
        # 这里再挡一次是 fail-closed：profile 的 Literal 已挡过一层，但本
        # builder 也可能被诊断序列直接调用（那条路径不过 profile 校验）。
        if type(configuration) is not int or not 0 <= configuration <= 6:
            raise ValueError("CMW TDD uplink-downlink configuration is out of range")
        return f"{cls._format('mac_cell_uldl', sign_channel)} {configuration}"

    @classmethod
    def mac_cell_uldl_query(cls, sign_channel: int) -> str:
        return cls._format("mac_cell_uldl_query", sign_channel)

    @classmethod
    def build_mac_cell_ssubframe(cls, sign_channel: int, configuration: int) -> str:
        # p.688: `<SpecialSubframe>` 是 integer，Range `0 to 9`。
        # ⚠️ 本 builder 按**手册全域** 0..9 校验，不按 profile 放开的 0..7：
        #    值 8/9 的限制是「只能配 normal cyclic prefix」，那是**调用方**要
        #    保证的前置条件，不是命令本身的取值域。把 profile 的收窄抄进
        #    builder 会让两处对同一个域各存一份，而它们的收窄理由并不相同。
        if type(configuration) is not int or not 0 <= configuration <= 9:
            raise ValueError("CMW TDD special subframe configuration is out of range")
        return f"{cls._format('mac_cell_ssubframe', sign_channel)} {configuration}"

    @classmethod
    def mac_cell_ssubframe_query(cls, sign_channel: int) -> str:
        return cls._format("mac_cell_ssubframe_query", sign_channel)

    @classmethod
    def build_mac_rmc_version_dl(
        cls, sign_channel: int, stream: int, version: int
    ) -> str:
        # p.803: `<Version>` 是 integer，Range `0 to 1`，*RST 0。
        if type(version) is not int or version not in (0, 1):
            raise ValueError("CMW TDD DL RMC version is out of range")
        return (
            f"{cls._format_stream('mac_rmc_version_dl', sign_channel, stream)}"
            f" {version}"
        )

    @classmethod
    def mac_rmc_version_dl_query(cls, sign_channel: int, stream: int) -> str:
        return cls._format_stream("mac_rmc_version_dl_query", sign_channel, stream)

    @staticmethod
    def parse_mac_integer(response: str, *, low: int, high: int, label: str) -> int:
        """把整数型回读解析成 int，域外/非整数一律拒。

        刻意**返回 int 而不是字符串**：`_confirm` 的比对是严格相等，而仪器
        可能回 `1`、`+1` 或带空白 —— 用字符串比会把同一个值判成不符
        （假阴性），用 int 比才是打在真实生效端上。
        """

        token = response.strip()
        if not _INTEGER_READBACK_RE.fullmatch(token):
            raise ValueError(f"undocumented CMW {label} readback: {response!r}")
        value = int(token)
        if not low <= value <= high:
            raise ValueError(f"CMW {label} readback out of range: {response!r}")
        return value

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
    def parse_ebler_subframes(response: str) -> int:
        """Parse the SFRames readback strictly against the manual's domain.

        The manual gives the parameter domain (integer, 100..400E+3, printed
        p.953) but not the literal response spelling, so the numeric forms SCPI
        instruments commonly echo (``5000`` / ``+5000`` / ``5.0E+03``) are all
        accepted and everything outside the documented domain is rejected —
        an out-of-domain readback proves the statistical basis is not the one
        that was requested, which must fail closed rather than be interpreted.
        """

        parsed = _integer(response.strip(), "Extended BLER subframes")
        return validate_ebler_subframes(parsed)

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
