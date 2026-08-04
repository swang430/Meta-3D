"""
Keysight UXM E7515B — Test Application command profiles
========================================================

E7515B Platform hosts multiple Test Applications, each with its own SCPI
dialect. The platform itself (on hislip0) only exposes IEEE 488.2 core;
real test functionality lives in the Test Application Framework (hislip2)
under the currently-active Test Application.

Discovered at CAICT 2026-05-13 on live UXM:
  - hislip0 → "E7515B Platform"            (IEEE 488.2 only)
  - hislip2 → "Test Application Framework" (BSE:* + app-specific tree)
  - SYSTem:APPLication:NAME? identifies which app is running

Apps observed in the field:
  - "5G_NR_Test"   — pure 5G NR Standalone (SA) test, CONFig:NR5G:* root,
                     cells indexed from CELL0
  - "LTE_NR_IRAT"  — LTE + NR EN-DC / NSA inter-RAT, BSE:CONFig:NR5G:* root,
                     cells indexed from CELL1, BWP value uses BW<N> form
                     (e.g. "BW40" not "40")

Profile attributes mirror UxmScpiCommands; commands not verified to work
in a given app are set to ``None`` so caller methods can skip / log
"unsupported in profile {name}" without raising.
"""

from __future__ import annotations

from typing import Optional, Type


class UxmTestApp:
    """Base profile — IEEE 488.2 minimal set, common to every Test App.

    Subclasses override app-specific format strings. Driver methods read
    via ``self._cmds.X`` after profile is selected in ``connect()``.

    Format-string template variables:
      {cell} = e.g. "CELL0" / "CELL1"
      {bwp}  = e.g. "BWP0" / "BWP1"
      {ant}  = antenna index (1-based on UXM)
      {idx}  = SCC index for carrier aggregation
    """

    # --- Profile identity ---
    PROFILE_NAME: str = "base"
    APP_NAME_MATCH: tuple[str, ...] = ()   # e.g. ("5G_NR_Test",)
    PRIMARY_CELL: str = "CELL0"            # default cell id for set_cell_config
    PRIMARY_BWP: str = "BWP0"
    HISLIP_INDEX: int = 0                  # which hislip endpoint to connect

    # --- P1-19 方言值编码 / 能力标志 (2026-07-03 现场实证) ---
    # 带宽值形式: "raw" = 裸数字 "100"; "prefixed" = 令牌 "BW100" (IRAT 实证,
    # 裸数字被拒)。
    BW_VALUE_FORM: str = "raw"
    # 配置回读对账: IRAT 实证 ARFCN/BW/POWer 回读可用 → True; 老 5G_NR_Test
    # App 2026-05-27 实证配置查询不支持 (超时) → False, 开了只会拖慢并误伤。
    # config["readback_verify"] 可显式双向覆盖。
    SUPPORTS_CONFIG_READBACK: bool = False

    # --- IEEE 488.2 / platform-mandatory ---
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    CLS = "*CLS"
    ERR = "SYSTem:ERRor?"

    # --- App selection (write-only) ---
    APP_SELECT: Optional[str] = None

    # --- Cell config (pre-templated; format with {cell}=CELL0/1/...) ---
    CELL_BAND: Optional[str] = None
    CELL_DL_ARFCN: Optional[str] = None
    CELL_DL_BW: Optional[str] = None
    CELL_UL_BW: Optional[str] = None
    CELL_SCS: Optional[str] = None
    CELL_DUPLEX: Optional[str] = None
    CELL_ACTIVE: Optional[str] = None
    CELL_DL_POINTA: Optional[str] = None

    # --- SSB ---
    SSB_ARFCN: Optional[str] = None

    # --- Downlink power ---
    DL_POWER: Optional[str] = None
    PDSCH_POWER: Optional[str] = None
    SSB_POWER: Optional[str] = None

    # --- PDSCH/PUSCH ---
    PDSCH_MCS: Optional[str] = None
    PDSCH_RB_ALLOC: Optional[str] = None
    PUSCH_MCS: Optional[str] = None
    PUSCH_RB_ALLOC: Optional[str] = None

    # --- MIMO logical layers ---
    MIMO_DL_LAYERS: Optional[str] = None
    MIMO_DL_CODEBOOK: Optional[str] = None

    # --- MIMO antenna → physical RF port routing ---
    MIMO_TX_ANT_PORT: Optional[str] = None
    MIMO_RX_ANT_PORT: Optional[str] = None
    MIMO_TX_ANT_PORT_QUERY: Optional[str] = None
    MIMO_RX_ANT_PORT_QUERY: Optional[str] = None

    # --- Cell signaling / state ---
    CELL_STATE_ON: Optional[str] = None
    CELL_STATE_OFF: Optional[str] = None
    CELL_STATE_QUERY: Optional[str] = None
    # P0-2 D1: **小区状态**查询 (协议栈真实状态, 手册枚举 OFF|ON|CONNected|IDLE|
    # AGGRegated|ACTivated)。与 CELL_STATE_QUERY 严格区分 —— 后者在 IRAT 方言上
    # 是 ACTive:STATe 开关位置回读 (回 "0"/"1", 自己写进去的值的回声), 不是状态。
    # R1 教训: attach 轮询曾用开关查询判 "CONN" ∈ "1", 任何情况都不可能成立。
    CELL_STATUS_QUERY: Optional[str] = None
    # P0-2 D2: 小区 ON 态写配置后让其进协议栈的应用命令 (手册: "most configuration
    # changes won't be applied until this command"; OFF 态写会在开小区时自动应用)。
    CONFIG_APPLY: Optional[str] = None

    # --- Throughput measurement ---
    # ⚠ MEAS_BTHROUGHPUT_DL_START / _STOP: 手册的 SCPI 命令树里**没有**
    #   `BTHRoughput:DL:TSTatistics:STARt|STOP` 这两条 (2026-08-03 NotebookLM
    #   查证)。累积由全局 MEAS_BTHROUGHPUT_STATE 控制、MEAS_BTHROUGHPUT_CLEAR
    #   清零。新方言**不要**再填这两个字段。
    MEAS_BTHROUGHPUT_DL_START: Optional[str] = None
    MEAS_BTHROUGHPUT_DL_STOP: Optional[str] = None
    # ⚠ MEAS_BTHROUGHPUT_DL_JSON 是 **DL 重传统计 (HARQ ACK/NACK/StatDTX 按
    #   传输次序)**, 手册名 "DL Retransmission Stats Query (JSON)" ——
    #   **不是吞吐量**。命令路径里的 BTHRoughput 只是命令树分支名。
    #   读吞吐量一律用 MEAS_TPUT_DL_OTA。(2026-08-03: 我们曾拿它当吞吐量解析,
    #   真机 22,787 条回复全被读成 0.0)
    MEAS_BTHROUGHPUT_DL_JSON: Optional[str] = None
    # ⚠ MEAS_BTHROUGHPUT_DL_BLER 指的是 `BLER:STATistical` = **Early Pass/Fail
    #   算法状态机** (返回 state,result,errors,samples 四元组, 真机实测
    #   "IDLE,UNKN,0,0"), **不是 BLER 数值**。读 BLER 用 MEAS_BLER_DL。
    MEAS_BTHROUGHPUT_DL_BLER: Optional[str] = None

    # --- Throughput / BLER 真值回读 (2026-08-03 按手册补齐) ---
    # 全局累积开关 + 清零 (不带 cell —— 手册明确是技术层全局设置)
    MEAS_BTHROUGHPUT_STATE: Optional[str] = None
    MEAS_BTHROUGHPUT_CLEAR: Optional[str] = None
    # OTA 吞吐量: 6 doubles
    #   {progress-count, current, min, max, average, current-scheduled}, 单位 bps
    MEAS_TPUT_DL_OTA: Optional[str] = None
    MEAS_TPUT_UL_OTA: Optional[str] = None
    # DL BLER: 10 doubles {progress, ack-count, ack-ratio, nack-count, nack-ratio,
    #   statdtx-count, statdtx-ratio, pdschBlerCount, pdschBlerRatio, pdschTputRatio}
    MEAS_BLER_DL: Optional[str] = None
    # UL BLER: 6 doubles {progress, ack-count, ack-ratio, nack-count, nack-ratio}
    MEAS_BLER_UL: Optional[str] = None
    # UE L3 测量报告 (RSRP / RSRQ / SINR 的真值源) —— 需先开 REPORT_STATE
    MEAS_UE_REPORT_STATE: Optional[str] = None
    MEAS_UE_REPORT_JSON: Optional[str] = None

    # --- UE capability / RRC reconfig ---
    UE_CAPABILITY_QUERY: Optional[str] = None
    UE_MAX_DL_LAYERS_QUERY: Optional[str] = None
    UE_MAX_UL_LAYERS_QUERY: Optional[str] = None
    UE_MAX_MODULATION_DL_QUERY: Optional[str] = None
    UE_SUPPORTED_BANDS_QUERY: Optional[str] = None

    RRC_RECONFIG_LAYERS: Optional[str] = None
    RRC_RECONFIG_MODULATION: Optional[str] = None
    RRC_RECONFIG_APPLY: Optional[str] = None

    # --- Carrier aggregation (SCell) ---
    SCELL_CONF_FREQ: Optional[str] = None
    SCELL_CONF_BW: Optional[str] = None
    SCELL_CONF_SCS: Optional[str] = None
    SCELL_CONF_BAND: Optional[str] = None
    SCELL_ADD: Optional[str] = None
    SCELL_ACTIVATE: Optional[str] = None
    SCELL_REMOVE_ALL: Optional[str] = None
    SCELL_LIST_QUERY: Optional[str] = None

    # --- CSI measurements ---
    MEAS_CSI_START: Optional[str] = None
    MEAS_CSI_STOP: Optional[str] = None
    # CSI 测量状态查询 —— 手册 **Query only: True**, 返回 STOP | WAIT | MEAS
    # (STOP=未运行 / WAIT=已启动等开始时刻 / MEAS=正在采集)。
    # ⚠ 必需: `CSI:STARt` 是 Imm Action, 手册明写「已在跑 → 忽略」「小区关闭 → 忽略」——
    #   不回读状态就分不清「开成功了」和「被静默忽略」。
    MEAS_CSI_STATE: Optional[str] = None
    MEAS_CSI_CQI: Optional[str] = None
    MEAS_CSI_RI: Optional[str] = None

    # --- UE Measurement Report (RSRP / SINR) ---
    # ⚠ `UEReport:RSRP|SINR:STATistics?` **手册里没有这两条命令** (2026-08-03
    #   NotebookLM 查证)。真机上各发过 1 次、零回音, 之后再没发过。
    #   UE 上报的 RSRP/RSRQ/SINR 真值源是 MEAS_UE_REPORT_JSON (L3 RRC 测量报告)。
    #   这两个字段保留只为不破坏既有方言, **新代码不要读它们**。
    MEAS_UE_RSRP: Optional[str] = None
    MEAS_UE_SINR: Optional[str] = None

    # --- EVM ---
    MEAS_EVM_START: Optional[str] = None

    # --- State save/load ---
    STATE_SAVE: Optional[str] = None
    STATE_LOAD: Optional[str] = None
    STATE_LIST: Optional[str] = None

    # --- RF routing ---
    RF_CONNECTOR: Optional[str] = None
    RF_PORT_DL: Optional[str] = None
    RF_PORT_UL: Optional[str] = None

    # --- TDD ---
    TDD_PATTERN: Optional[str] = None
    TDD_PERIOD: Optional[str] = None

    # --- PDSCH scheduling / AMC ---
    PDSCH_SCHED_ALGO: Optional[str] = None
    PDSCH_AMC_ENABLE: Optional[str] = None
    PUSCH_AMC_ENABLE: Optional[str] = None

    # --- HARQ ---
    HARQ_MAX_TRANS: Optional[str] = None
    HARQ_PROCESSES: Optional[str] = None

    # --- CSI-RS ports ---
    CSIRS_PORTS: Optional[str] = None

    # --- Throughput stat window ---
    MEAS_TPUT_STAT_COUNT: Optional[str] = None
    MEAS_TPUT_UL_JSON: Optional[str] = None
    MEAS_TPUT_UL_BLER: Optional[str] = None

    # --- Status ---
    STATUS_FAULTY: Optional[str] = None


class Uxm5GNRTestAppProfile(UxmTestApp):
    """Pure 5G NR Test Application — SA mode, CONFig:NR5G:* root.

    Cell indices CELL0..CELL3. This is the dialect the original UxmScpiCommands
    class was authored against (pre-CAICT-2026-05-13).
    """

    PROFILE_NAME = "5G_NR_Test"
    APP_NAME_MATCH = ("5G_NR_Test", "5G NR Test", "5G_NR_TEST")
    PRIMARY_CELL = "CELL0"
    PRIMARY_BWP = "BWP0"
    HISLIP_INDEX = 0   # historically connected via hislip0; works for SA app

    APP_SELECT = 'SYSTem:APPLication:NAME "5G_NR_Test"'

    CELL_BAND = "CONFig:NR5G:{cell}:BAND"
    CELL_DL_ARFCN = "CONFig:NR5G:{cell}:DL:ARFCN"
    CELL_DL_BW = "CONFig:NR5G:{cell}:DL:BW"
    CELL_UL_BW = "CONFig:NR5G:{cell}:UL:BW"
    CELL_SCS = "CONFig:NR5G:{cell}:SCS"
    CELL_DUPLEX = "CONFig:NR5G:{cell}:DUPLex"
    CELL_ACTIVE = "CONFig:NR5G:{cell}:ACTive:STATe"
    CELL_DL_POINTA = "CONFig:NR5G:{cell}:DL:POINta"

    SSB_ARFCN = "CONFig:NR5G:{cell}:{bwp}:SSB:NCD:ARFCn"

    DL_POWER = "CONFig:NR5G:{cell}:PHY:DL:POWer"
    PDSCH_POWER = "CONFig:NR5G:{cell}:{bwp}:PDSCH:POWer"
    SSB_POWER = "CONFig:NR5G:{cell}:SSB:POWer"

    PDSCH_MCS = "CONFig:NR5G:{cell}:{bwp}:PDSCH:MCS"
    PDSCH_RB_ALLOC = "CONFig:NR5G:{cell}:{bwp}:PDSCH:RB:ALLocation"
    PUSCH_MCS = "CONFig:NR5G:{cell}:{bwp}:PUSCH:MCS"
    PUSCH_RB_ALLOC = "CONFig:NR5G:{cell}:{bwp}:PUSCH:RB:ALLocation"

    MIMO_DL_LAYERS = "CONFig:NR5G:{cell}:PHY:DL:MIMO:LAYers"
    MIMO_DL_CODEBOOK = "CONFig:NR5G:{cell}:PHY:DL:MIMO:CODEbook"

    MIMO_TX_ANT_PORT = "ROUTe:NR5G:{cell}:HARDware:TX:ANTenna{ant}:PORT"
    MIMO_RX_ANT_PORT = "ROUTe:NR5G:{cell}:HARDware:RX:ANTenna{ant}:PORT"
    MIMO_TX_ANT_PORT_QUERY = "ROUTe:NR5G:{cell}:HARDware:TX:ANTenna{ant}:PORT?"
    MIMO_RX_ANT_PORT_QUERY = "ROUTe:NR5G:{cell}:HARDware:RX:ANTenna{ant}:PORT?"

    CELL_STATE_ON = "CONFig:NR5G:{cell}:ACTive:STATe ON"
    CELL_STATE_OFF = "CONFig:NR5G:{cell}:ACTive:STATe OFF"
    # 旧代码注释宣称本方言回文本态 (IDLE/ATT/CONN/ON/OFF) — **出处不可考**
    # (git log 无实证 commit; 2026-05 现场那台确认是 IRAT), 待现场核, 别当已证
    # 事实引用 (agent 门 F5)。与 IRAT 回 "0"/"1" 不同。CELL_STATUS_QUERY 在本
    # 方言**手册查不到**故留 None (不照抄 IRAT 写法去猜), 状态轮询 fallback
    # 用本条的文本回复 + 白名单解析 (枚举外不判, 超时带字面值可现场定位)。
    CELL_STATE_QUERY = "CONFig:NR5G:{cell}:ACTive:STATe?"

    MEAS_BTHROUGHPUT_DL_START = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STARt"
    MEAS_BTHROUGHPUT_DL_STOP = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STOP"
    MEAS_BTHROUGHPUT_DL_JSON = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:JSON?"
    MEAS_BTHROUGHPUT_DL_BLER = "MEASure:NR5G:{cell}:BTHRoughput:DL:BLER:STATistical:ALL?"

    UE_CAPABILITY_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability?"
    UE_MAX_DL_LAYERS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MIMO:DL:LAYers?"
    UE_MAX_UL_LAYERS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MIMO:UL:LAYers?"
    UE_MAX_MODULATION_DL_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MODulation:DL?"
    UE_SUPPORTED_BANDS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:BANDs?"

    RRC_RECONFIG_LAYERS = "CALL:NR5G:{cell}:RRC:RECon:MIMO:LAYers {layers}"
    RRC_RECONFIG_MODULATION = "CALL:NR5G:{cell}:RRC:RECon:MODulation:DL {mod}"
    RRC_RECONFIG_APPLY = "CALL:NR5G:{cell}:RRC:RECon:APPLy"

    SCELL_CONF_FREQ = "CALL:NR5G:{cell}:SCEL{idx}:CONF:FREQuency {freq_mhz}MHz"
    SCELL_CONF_BW = "CALL:NR5G:{cell}:SCEL{idx}:CONF:BWIDth {bw_mhz}MHz"
    SCELL_CONF_SCS = "CALL:NR5G:{cell}:SCEL{idx}:CONF:SCS {scs_khz}KHz"
    SCELL_CONF_BAND = "CALL:NR5G:{cell}:SCEL{idx}:CONF:BAND {band}"
    SCELL_ADD = "CALL:NR5G:{cell}:SCEL{idx}:ADD"
    SCELL_ACTIVATE = "CALL:NR5G:{cell}:SCEL{idx}:ACTive ON"
    SCELL_REMOVE_ALL = "CALL:NR5G:{cell}:SCEL:REMove:ALL"
    SCELL_LIST_QUERY = "CALL:NR5G:{cell}:SCEL:LIST?"

    MEAS_CSI_START = "MEASure:NR5G:{cell}:CSI:STARt"
    MEAS_CSI_STOP = "MEASure:NR5G:{cell}:CSI:STOP"
    MEAS_CSI_CQI = "MEASure:NR5G:{cell}:CSI:CQI:STATistics?"
    MEAS_CSI_RI = "MEASure:NR5G:{cell}:CSI:RI:HISTogram?"

    MEAS_UE_RSRP = "MEASure:NR5G:{cell}:UEReport:RSRP:STATistics?"
    MEAS_UE_SINR = "MEASure:NR5G:{cell}:UEReport:SINR:STATistics?"

    MEAS_EVM_START = "MEASure:NR5G:{cell}:PHY:EVM:STARt"

    STATE_SAVE = 'SYSTem:CONFiguration:SAVE "{filepath}"'
    STATE_LOAD = 'SYSTem:CONFiguration:LOAD "{filepath}"'
    STATE_LIST = 'MMEMory:CATalog? "D:\\User Files"'

    RF_CONNECTOR = "CONFig:NR5G:{cell}:RFSettings:CHANnel"
    RF_PORT_DL = "CONFig:NR5G:{cell}:RFSettings:DL:PORT"
    RF_PORT_UL = "CONFig:NR5G:{cell}:RFSettings:UL:PORT"

    TDD_PATTERN = "CONFig:NR5G:{cell}:TDD:PATTern"
    TDD_PERIOD = "CONFig:NR5G:{cell}:TDD:PERiod"

    PDSCH_SCHED_ALGO = "CONFig:NR5G:{cell}:{bwp}:PDSCH:SchedAlgoritm"
    PDSCH_AMC_ENABLE = "CONFig:NR5G:{cell}:{bwp}:PDSCH:AMC:ENABle"
    PUSCH_AMC_ENABLE = "CONFig:NR5G:{cell}:{bwp}:PUSCH:AMC:ENABle"

    HARQ_MAX_TRANS = "CONFig:NR5G:{cell}:HARQ:MaxTrans"
    HARQ_PROCESSES = "CONFig:NR5G:{cell}:HARQ:PROCesses"

    CSIRS_PORTS = "CONFig:NR5G:{cell}:CSIRS:PORTs"

    MEAS_TPUT_STAT_COUNT = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:COUNt"
    MEAS_TPUT_UL_JSON = "MEASure:NR5G:{cell}:BTHRoughput:UL:TSTatistics:JSON?"
    MEAS_TPUT_UL_BLER = "MEASure:NR5G:{cell}:BTHRoughput:UL:BLER:STATistical:ALL?"

    STATUS_FAULTY = "STATus:FAULty:RECovery"


class UxmLteNrIratProfile(UxmTestApp):
    """LTE + NR Inter-RAT (EN-DC / NSA) Test Application.

    Hosted on hislip2 under the Test Application Framework. Commands rooted
    at BSE: (Base Station Emulator) and cells indexed from CELL1.

    Live-verified at CAICT 2026-05-13 against E7515B firmware 28.21.0.32.
    Commands marked ``None`` were probed and returned -113 "Undefined
    header"; driver methods should detect None and skip / log instead of
    sending. Filling them in requires firmware reference cross-check
    (the 110 MB SCPI HTML in Instrument_API_Doc/Keysight UXM NR SCPI/).

    Notable IRAT-specific value encoding:
      - Bandwidth: returns "BW40" (not raw "40"); set with same form
      - First user cell is CELL1; CELL0 doesn't exist in this app
      - Throughput JSON wraps NR cell index inside payload ("CellIndex": 0)
    """

    PROFILE_NAME = "LTE_NR_IRAT"
    APP_NAME_MATCH = ("LTE_NR_IRAT", "LTE+NR", "EN-DC", "LTE_NR")
    PRIMARY_CELL = "CELL1"
    PRIMARY_BWP = "BWP0"
    HISLIP_INDEX = 2   # Test Application Framework lives here

    # P1-19 (2026-07-03 实证): BW 值必须令牌形式 "BW100" (裸 "100" 被拒);
    # ARFCN/BW/POWer/STATe 回读可用且与面板一致 → 回读对账默认开。
    BW_VALUE_FORM = "prefixed"
    SUPPORTS_CONFIG_READBACK = True

    # Note: app selection on E7515B Test App Framework is GUI-driven —
    # SCPI write to change app isn't safe to send unprompted.
    APP_SELECT = None

    # === Live-verified at CAICT 2026-05-13 ===
    CELL_BAND = "BSE:CONFig:NR5G:{cell}:BAND"
    CELL_DL_ARFCN = "BSE:CONFig:NR5G:{cell}:DL:ARFCN"
    CELL_DL_BW = "BSE:CONFig:NR5G:{cell}:DL:BW"        # value form "BW40"
    CELL_UL_BW = "BSE:CONFig:NR5G:{cell}:UL:BW"
    CELL_ACTIVE = "BSE:CONFig:NR5G:{cell}:ACTive:STATe"
    CELL_STATE_ON = "BSE:CONFig:NR5G:{cell}:ACTive:STATe 1"
    CELL_STATE_OFF = "BSE:CONFig:NR5G:{cell}:ACTive:STATe 0"
    # ⚠ 开关位置回读 (回 "0"/"1" — 自己写进去的值的回声), **不是小区状态**。
    # 合法用途只有一种: 判"要不要 OFF→写→ON 环绕"(set_cell_config BW 段)。
    # attach / 状态判定一律用下面的 CELL_STATUS_QUERY (P0-2 R1/R2)。
    CELL_STATE_QUERY = "BSE:CONFig:NR5G:{cell}:ACTive:STATe?"
    # P0-2 D1 (手册 NR Cell > Config "NR Connection Status"):
    #   Range: OFF | ON | CONNected | IDLE | AGGRegated | ACTivated
    # 这才是协议栈的真话 — 现场 07-21 "ACTive=1 但 STATus 持续 OFF" 里,
    # 前者是回声, 后者是仪器实况。
    CELL_STATUS_QUERY = "BSE:STATus:NR5G:{cell}?"
    # P0-2 D2 (手册 General > Miscellaneous "Apply Configured Changes"):
    # ON 态写的配置进缓存, 发本命令才进协议栈; OFF 态写会在开小区时自动应用。
    # 技术层全局动作 (刷**所有** NR 小区的挂起配置; 带小区的 ...:CELLn:APPLY
    # 手册标 deprecated 且行为相同, 不用)。Imm Action / No query — 无完成查询,
    # 不跟 *OPC?, 生效确认靠 CELL_STATUS_QUERY 轮询。
    CONFIG_APPLY = "BSE:CONFig:NR5G:APPLY"

    # === KPI 回读 (2026-08-03 全部按手册重写; 之前 8 个字段没一个是真的) ===
    #
    # 背景: 本 profile 原来只覆盖了下面这条 DL JSON, CQI/RI/RSRP/SINR/UL 全部
    # 继承基类的**无前缀**形式。而 IRAT Test App 的命令**全部根在 BSE: 下** ——
    # 所以那几条一发就是 undefined header, 真机日志里各发 1 次、零回音, 而
    # get_throughput_metrics() 每个字段都是 except: pass, 一句话都不报。
    #
    # ⚠ 这条是 **DL 重传统计**, 不是吞吐量 —— 保留是因为重传统计本身有用
    # (HARQ 质量), 但**不再当吞吐量读**。真机 22,787 条回复形如
    # `{"CellIndex":0,"ProgressCount":1000,"Tx1Info":{"Counts":{"Ack":1240,...`
    MEAS_BTHROUGHPUT_DL_JSON = "BSE:MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:JSON?"
    # ⚠ 手册无此命令 —— 显式置 None, 让驱动跳过而不是盲发。
    MEAS_BTHROUGHPUT_DL_START = None
    MEAS_BTHROUGHPUT_DL_STOP = None
    # ⚠ `BLER:STATistical` 是 Early Pass/Fail 状态机 (真机实测 "IDLE,UNKN,0,0"),
    #   不是 BLER 数值。置 None, BLER 走 MEAS_BLER_DL。
    MEAS_BTHROUGHPUT_DL_BLER = None
    MEAS_TPUT_UL_JSON = None      # 手册无 UL:TSTatistics; UL 吞吐量走 MEAS_TPUT_UL_OTA
    MEAS_TPUT_UL_BLER = None
    MEAS_UE_RSRP = None           # 手册无 UEReport:*:STATistics
    MEAS_UE_SINR = None

    # 全局累积开关 / 清零 (手册: 技术层全局, 不带 cell)
    MEAS_BTHROUGHPUT_STATE = "BSE:MEASure:NR5G:BTHRoughput:STATe"
    MEAS_BTHROUGHPUT_CLEAR = "BSE:MEASure:NR5G:BTHRoughput:CLEar"
    # OTA 吞吐量 — 6 doubles {progress, current, min, max, average, current-scheduled}
    # 单位 **bps** (GUI 显示 Mbps, SCPI 层是 bps)
    MEAS_TPUT_DL_OTA = "BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:{cell}?"
    MEAS_TPUT_UL_OTA = "BSE:MEASure:NR5G:BTHRoughput:UL:THRoughput:OTA:{cell}?"
    # DL BLER — 10 doubles, 取 idx8 = pdschBlerRatio
    MEAS_BLER_DL = "BSE:MEASure:NR5G:BTHRoughput:DL:BLER:{cell}?"
    # UL BLER — 6 doubles, 取 idx4 = nack-ratio
    MEAS_BLER_UL = "BSE:MEASure:NR5G:BTHRoughput:UL:BLER:{cell}?"
    # CSI (CQI/RI) — 命令本身原来就对, 缺的是 BSE: 前缀与 STARt 前置
    MEAS_CSI_START = "BSE:MEASure:NR5G:{cell}:CSI:STARt"
    MEAS_CSI_STOP = "BSE:MEASure:NR5G:{cell}:CSI:STOP"
    MEAS_CSI_STATE = "BSE:MEASure:NR5G:{cell}:CSI:STATe?"
    # 6 doubles {count, min, max, average, median, ...} — 取 idx3 = average
    # ⚠ idx0 是**样本数**不是 CQI。真机回过 7.92E+04 (79200 个样本),
    #   我们曾把它当 CQI 值上报。
    MEAS_CSI_CQI = "BSE:MEASure:NR5G:{cell}:CSI:CQI:STATistics?"
    # 8 doubles = RI **0..7** 各自的累计次数 (直方图)
    # ⚠ 下标即 RI 值, 加权时权重用 i 不是 (i+1)。
    MEAS_CSI_RI = "BSE:MEASure:NR5G:{cell}:CSI:RI:HISTogram?"
    # UE L3 测量报告 (RSRP/RSRQ/SINR 真值源) — 需先把队列开关打开
    MEAS_UE_REPORT_STATE = "BSE:CONFig:MEASurement:REPort"
    MEAS_UE_REPORT_JSON = "BSE:CONFig:NR5G:{cell}:MEASurement:JSON:REPort:FETCh?"

    # === IRAT-extras (not in 5G_NR_Test app) ===
    # PROPSIM channel emulator integration commands
    PROPSIM_IP = "BSE:CONFig:PROPsim:IPADdress"
    PROPSIM_EMULATION_STATE = "BSE:CONFig:PROPsim:EMULation:STATe"
    PROPSIM_EMULATION_RUN = "BSE:CONFig:PROPsim:EMULation:RUN"
    PROPSIM_EMULATION_STOP = "BSE:CONFig:PROPsim:EMULation:STOP"
    PROPSIM_EMULATION_LOAD = "BSE:CONFig:PROPsim:EMULation:LOAD"

    BSE_STATUS = "BSE:STATus?"
    BSE_SELECTED_CELL = "BSE:SELected:CELL?"
    BSE_INFO_LTE_CELL_NUMBER = "BSE:INFO:LTE:CELL:NUMBer?"
    BSE_NR5G_DEFAULT_TYPE = "BSE:CONFig:NR5G:DEFault:TYPE"   # NSA / SA
    BSE_NR5G_CA_MODE = "BSE:CONFig:NR5G:CAGGregation:MODE"
    BSE_LTE_CA_MODE = "BSE:CONFig:LTE:CAGGregation:MODE"

    # LTE side (live-verified for CELL1 BW + ACTive)
    LTE_CELL_DL_BW = "BSE:CONFig:LTE:{cell}:DL:BW"
    LTE_CELL_ACTIVE = "BSE:CONFig:LTE:{cell}:ACTive:STATe"

    # === Power commands — verified at CAICT 2026-05-13 after probe revealed
    # the initial guesses (:PHY:DL:POWer and :SSB:POWer) returned -113. The
    # IRAT app uses different mnemonics:
    #   DL power: BSE:CONFig:NR5G:<cell>:DL:POWer  (no :PHY: segment;
    #             optional [:EPRE] sub-node for EPRE-form value)
    #   SSB power: BSE:CONFig:NR5G:<cell>:SSB:POWer:ADVertised  (advertised
    #             form is the actually-routable one; bare :SSB:POWer is
    #             undefined header on this firmware)
    DL_POWER = "BSE:CONFig:NR5G:{cell}:DL:POWer"
    SSB_POWER = "BSE:CONFig:NR5G:{cell}:SSB:POWer:ADVertised"
    SCELL_CONF_BAND = "BSE:CONFig:LTE:{cell}:CAGGregation:AGGRegate:SCC:LIST"
    SCELL_ADD = "BSE:CONFig:LTE:{cell}:CAGGregation:ACTivate:SCC:LIST"
    SCELL_LIST_QUERY = "BSE:CONFig:LTE:{cell}:CAGGregation:AGGRegate:SCC:LIST?"

    # === Verified unsupported in this app (left as None per base) ===
    # CELL_SCS, CELL_DUPLEX, CELL_DL_POINTA, SSB_ARFCN,
    # MIMO_DL_LAYERS, MIMO_DL_CODEBOOK, MIMO_TX/RX_ANT_PORT*,
    # PDSCH_MCS / RB_ALLOC, PUSCH_MCS / RB_ALLOC,
    # UE_* (CALL: prefix not exposed), RRC_*,
    # MEAS_CSI_*, MEAS_UE_RSRP/SINR, MEAS_EVM_START,
    # STATE_*, RF_*, TDD_*, PDSCH_SCHED_ALGO, *_AMC_ENABLE, HARQ_*, CSIRS_PORTS,
    # MEAS_TPUT_STAT_COUNT, MEAS_TPUT_UL_*, STATUS_FAULTY
    # — driver should check `if cmd is not None` before sending.


# ===========================================================================
# Profile registry + detection
# ===========================================================================

ALL_PROFILES: tuple[Type[UxmTestApp], ...] = (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)


def detect_profile(app_name: str) -> Type[UxmTestApp]:
    """Return the profile class matching ``app_name`` (case-insensitive
    substring match against each profile's APP_NAME_MATCH tuple).

    Falls back to ``Uxm5GNRTestAppProfile`` for unrecognised apps —
    historically that's been the only profile and most existing labs use
    pure 5G NR Test App.
    """
    if not app_name:
        return Uxm5GNRTestAppProfile
    upper = app_name.upper()
    for profile in ALL_PROFILES:
        for tag in profile.APP_NAME_MATCH:
            if tag.upper() in upper:
                return profile
    return Uxm5GNRTestAppProfile


# Backward-compat alias — existing callsites import UxmScpiCommands from
# uxm_base_station; after the refactor, importing from here works too.
UxmScpiCommands = Uxm5GNRTestAppProfile
