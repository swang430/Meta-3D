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
    # SCS 值编码: 旧 5G_NR_Test 使用裸 kHz；BSE/IRAT 使用 numerology
    # token（15/30/60/120 kHz → MU0/MU1/MU2/MU3）。
    SCS_VALUE_FORM: str = "raw"

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
    CELL_FREQ_RANGE: Optional[str] = None

    # --- SSB ---
    SSB_ARFCN: Optional[str] = None
    SSB_SCS: Optional[str] = None
    SSB_CORESET0: Optional[str] = None

    # --- Downlink power ---
    # ⚠️ **两条命令、两种口径，别混**（NotebookLM 2026-08-07 手册原文核对）：
    #   DL_POWER         → `...:DL:POWer[:EPRE]`   Unit `dBm/SCS`  Range `-200 .. 10`
    #                      "Changes DL Power - energy per resource element"
    #   DL_POWER_CHANNEL → `...:DL:POWer:CHANnel`  整带宽总功率 dBm  Range `-168 .. 42`
    #                      "the power integrated over the whole cell bandwidth"
    # 同一个 cell 上**只该写其中一条** —— 两条都写会互相覆盖，最后生效哪个不确定。
    DL_POWER: Optional[str] = None
    DL_POWER_CHANNEL: Optional[str] = None
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
    MIMO_DL_CONFIG: Optional[str] = None

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
    MEAS_TPUT_DL_OTA_ALL: Optional[str] = None
    MEAS_TPUT_UL_OTA_ALL: Optional[str] = None
    # DL BLER: 10 doubles {progress, ack-count, ack-ratio, nack-count, nack-ratio,
    #   statdtx-count, statdtx-ratio, pdschBlerCount, pdschBlerRatio, pdschTputRatio}
    MEAS_BLER_DL: Optional[str] = None
    # UL BLER: 6 doubles {progress, ack-count, ack-ratio, nack-count, nack-ratio}
    MEAS_BLER_UL: Optional[str] = None
    # UE L3 测量报告 (RSRP / RSRQ / SINR 的真值源) —— 需先开 REPORT_STATE
    MEAS_UE_REPORT_STATE: Optional[str] = None
    MEAS_UE_REPORT_CLEAR: Optional[str] = None
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
    # P1-33：手册没有"pattern 字符串"这种命令，TDD 是**六个数**下发的
    #   （`DDDSU` 数得出 D/U 整槽数，数不出 S 槽里的符号数 —— 那两个由
    #   TestCase 的 tdd_dl_symbols / tdd_ul_symbols 给，默认取手册默认 6/4）。
    TDD_PATTERN_STATE: Optional[str] = None
    TDD_SCS: Optional[str] = None
    TDD_DL_SLOTS: Optional[str] = None
    TDD_DL_SYMBOLS: Optional[str] = None
    TDD_UL_SLOTS: Optional[str] = None
    TDD_UL_SYMBOLS: Optional[str] = None
    # 手册：小区 ON 时多数配置改动**不发 APPLY 就不进协议栈**
    #   （"This is not needed if the Cell if Off"）。
    QCONFIG_APPLY_ALL: Optional[str] = None
    # 查本 BWP 配了多少 PRB —— "ALL" 时问仪器，不敲 38.104 表
    PHY_DL_BWP_NUM_PRBS: Optional[str] = None

    # --- PDSCH scheduling / AMC ---
    PDSCH_SCHED_ALGO: Optional[str] = None
    PDSCH_AMC_ENABLE: Optional[str] = None
    PUSCH_AMC_ENABLE: Optional[str] = None
    # slot 级 AMC 命令的**只读探测**模板（configure_mac 里逐条 query+对账，
    # 不作为写路径）。None = 本方言不探。
    AMC_SLOT_DL_APOLICY_PROBE: Optional[str] = None
    AMC_SLOT_UL_IMCS_FIXED_PROBE: Optional[str] = None

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

    PDSCH_MCS = None          # 原 ...{bwp}:PDSCH:MCS（手册 0 命中，见下方 ⛔ 段）
    PDSCH_RB_ALLOC = None     # 原 ...{bwp}:PDSCH:RB:ALLocation（手册 0 命中）
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

    TDD_PATTERN = None        # 原 CONFig:NR5G:{cell}:TDD:PATTern（手册 0 命中）
    TDD_PERIOD = None         # 原 CONFig:NR5G:{cell}:TDD:PERiod（手册 0 命中）

    # ⛔ P1-33（2026-08-04）：下面这批**曾经是编出来的** —— 逐条 grep 厂商手册
    #    原件（`Instrument_API_Doc/Keysight UXM NR SCPI/*.md`），**9 条 0 命中**，
    #    连 `SchedAlgoritm` 的拼写都是错的。它们从来没在任何真机上工作过：
    #    IRAT 上是 `None` 直接崩（P1-32 前），这里则是发出去等 -113。
    #
    #    按「禁盲试」置 `None` —— **不留编的，也不拿未经查证的形式去替**。
    #    手册里那批 `BSE:` 形式已补在 `UxmLteNrIratProfile`（现场在用的方言，
    #    本来就是 BSE: 根）；本 Test App 用无前缀 `CONFig:` 根，
    #    **它认不认 `BSE:` 形式未经查证**，所以不在这里猜。
    #    要用这个 TAP 跑 MAC 吞吐量测试，先用 `uxm_scpi_compatibility` 普查。
    PDSCH_SCHED_ALGO = None   # 原 CONFig:NR5G:{cell}:{bwp}:PDSCH:SchedAlgoritm（手册 0 命中）
    PDSCH_AMC_ENABLE = None   # 原 ...PDSCH:AMC:ENABle（手册 0 命中）
    PUSCH_AMC_ENABLE = None   # 原 ...PUSCH:AMC:ENABle（手册 0 命中）

    HARQ_MAX_TRANS = None     # 原 CONFig:NR5G:{cell}:HARQ:MaxTrans（手册 0 命中）
    HARQ_PROCESSES = None     # 原 CONFig:NR5G:{cell}:HARQ:PROCesses（手册 0 命中）

    CSIRS_PORTS = None        # 原 CONFig:NR5G:{cell}:CSIRS:PORTs（手册 0 命中）

    # ⛔ 统计窗口：手册里带 `BTHRoughput:...:LENGth` 的只有 `LTE:<cell>:` /
    #    `NBIot:<cell>:` / `NR5G:SLINk:`（V2X 边链路）三种 ——
    #    **普通 NR 小区根本没有这条命令**。原值同样是编的（0 命中）。
    MEAS_TPUT_STAT_COUNT = None
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
    SCS_VALUE_FORM = "mu"

    # Note: app selection on E7515B Test App Framework is GUI-driven —
    # SCPI write to change app isn't safe to send unprompted.
    APP_SELECT = None

    # === Live-verified at CAICT 2026-05-13 ===
    CELL_BAND = "BSE:CONFig:NR5G:{cell}:BAND"
    CELL_DL_ARFCN = "BSE:CONFig:NR5G:{cell}:DL:ARFCN"
    CELL_DL_BW = "BSE:CONFig:NR5G:{cell}:DL:BW"        # value form "BW40"
    CELL_UL_BW = "BSE:CONFig:NR5G:{cell}:UL:BW"
    # 2026-08-07 现场手工拼写探针已在 LTE_NR_IRAT / CELL1 上直接回读成功；
    # 写值形态同时由仓库内 Keysight SCPI Reference 的 Type/Range 确认。
    CELL_SCS = "BSE:CONFig:NR5G:{cell}:SUBCarrier:SPACing:COMMon"
    CELL_DUPLEX = "BSE:CONFig:NR5G:{cell}:DUPLEX:MODe"
    CELL_DL_POINTA = "BSE:CONFig:NR5G:{cell}:DL:POINta"
    CELL_FREQ_RANGE = "BSE:CONFig:NR5G:{cell}:FREQuency:RANGe"
    SSB_ARFCN = "BSE:CONFig:NR5G:{cell}:SSB:ARFCN"
    SSB_SCS = "BSE:CONFig:NR5G:{cell}:SSB:SUBCarrier:SPACing"
    SSB_CORESET0 = "BSE:CONFig:NR5G:{cell}:SSB:COReset0"
    # 现场仪表为 NR5G_R15。BWP 级 ``PDSCh:MMIMolayers`` 虽然可查询/
    # 写入，但在 APPLY 时会被 R16 license 门拒绝；R15 对应的是
    # serving-cell 级 ``PDSCh:MAX:MIMOlayers``（手册 + 2026-08-07 实机查询）。
    MIMO_DL_LAYERS = "BSE:CONFig:NR5G:{cell}:PHY:PDSCh:MAX:MIMOlayers"
    MIMO_DL_CONFIG = "BSE:CONFig:NR5G:{cell}:DL:MIMO:CONFig"
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
    # Keysight UXM SCPI Reference:
    #   UXM5G_SCPI_02_NR_PHY_Measurements.md
    #   NR BLER/Tput > DL/UL OTA > "DL/UL OTA all NR Results"。
    # 两条均返回 6 doubles，原文明确为所有 NR cells 结果之和；Application
    # Mode 为 NSA | SA。其他 profile 保持 None，禁止按相似方言猜命令。
    MEAS_TPUT_DL_OTA_ALL = (
        "BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:ALL?"
    )
    MEAS_TPUT_UL_OTA_ALL = (
        "BSE:MEASure:NR5G:BTHRoughput:UL:THRoughput:OTA:ALL?"
    )
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
    # ⚠ 队列**必须能清**：`FETCh?` 不带 <Integer> 时手册原文「If not specified
    #   **all the available reports are returned**」—— 不清就把开测以来的历史
    #   报告一起取回，而拿历史报告去跟**当下**的面板读数比对，结论无效。
    #   手册（NotebookLM 2026-08-04 三问）：Imm Action / No query，**无 <cell> 绑定**
    #   = 全局。另两问手册**未说明**：① 带 <Integer> 取的是最新还是最旧、
    #   多份时的排列顺序；② FETCh 是不是消费式（取完即移除）——
    #   旁证：手册对 RAR / UAI 报告都明写 "Querying the results will remove
    #   items from storage"，唯独 UE 测量报告只字未提。所以**不能假设取完就空**。
    MEAS_UE_REPORT_CLEAR = "BSE:CONFig:MEASurement:REPort:CLEAr"

    # ── P1-33（2026-08-04）：MAC 吞吐量配置命令，**逐条取自厂商手册原件**
    #    `Instrument_API_Doc/Keysight UXM NR SCPI/*.md`（块内精确抽取 SCPI/Type/
    #    Range/Default）。禁盲试：没有一条是编的。
    #
    #    ⚠️ 唯一的未知量是「LTE_NR_IRAT 这个 TAP 认不认」——
    #    手册的 `Application Mode` 字段**答不了**（本 profile 已定义、现场在用的
    #    `CELL_BAND`/`CELL_DL_ARFCN`/`CELL_DL_BW` 同样标 `NSA | SA` 不含 IRAT）。
    #    所以下发后**逐组查 `SYST:ERR?`**，被拒的记名 —— 现场一跑即知，不靠推断。
    #
    #    值形态跟旧的无前缀写法**完全不同**，转换在驱动里做：
    #      FULLBUFFER → FULL_TPUT ｜ AMC ON/OFF → APOLicy CQI/FIXed
    #      "ALL" → PRB 整数 ｜ "5MS" → MS5 ｜ 4/16 → N4/N16 ｜ 4 → P4
    # Enum: BASIc | FULL_TPUT | DL_RMC | UL_RMC | APC_RMC | EVM_RMC（默认 BASIc）
    PDSCH_SCHED_ALGO = "BSE:CONFig:NR5G:SCHeduling:QCONFig:SCENario"
    # ⛔ slot 级 AMC 两条盲写**已去掉**（2026-08-07 现场两轮实测：作为写下发时
    #    恰有一条 -113 Undefined header，组级对账定位不了是哪条）。
    #    「关 AMC / 固定 MCS」的意图由 QCONFig 组承担，依据（手册原文）：
    #      · SCENario FULL_TPUT: "maximizes the throughput achieved given the
    #        selected TDD Pattern, RB count and MCS" —— MCS 是**输入**不是自适应量
    #      · QCONFig:DL:MCS: "The MCS that will be applied to all DL slots"
    #      · DL:RRESource:APOLicy 的 Default 本身就是 FIXed；CQI 自适应
    #        "Only allowed when [policy] is CQI ... and some CSI Report is enabled"
    #    ⚠ FULL_TPUT 重建后 APOLicy 的生效值手册**未说明** —— 由下面的
    #    只读探测回读定案（能读到非 FIXed 时驱动仍然致命拦）。
    PDSCH_AMC_ENABLE = None
    PUSCH_AMC_ENABLE = None
    # 探测（只读，手册原文形式）：定位到底哪条 header 不被本 Test App 认，
    # 顺带回读 FULL_TPUT 重建后的生效策略。
    AMC_SLOT_DL_APOLICY_PROBE = (
        "BSE:CONFig:NR5G:{cell}:SCHeduling:{bwp}:FC0:SC0:DL:RRESource:APOLicy")
    AMC_SLOT_UL_IMCS_FIXED_PROBE = (
        "BSE:CONFig:NR5G:{cell}:SCHeduling:{bwp}:FC0:SC0:UL:IMCS:FIXed")
    PDSCH_MCS = "BSE:CONFig:NR5G:SCHeduling:QCONFig:DL:MCS"        # Integer 0..28
    PDSCH_RB_ALLOC = "BSE:CONFig:NR5G:SCHeduling:QCONFig:DL:NUM:PRBs"  # Integer 1..273

    # TDD：手册没有 pattern 字符串，是**六个数**
    TDD_PATTERN_STATE = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:STATE"
    TDD_PERIOD = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:PERiod"   # Enum MS0P5..MS10
    # ⭐ TDD pattern **就是按这个 SCS 评估的** —— 校验必须打在它上面，
    #   不能用 TestCase 的请求值（那是标称端；IRAT 上 CELL_SCS 未定义、
    #   inherit 模式还整段跳过下发，仪器实际可能在别的 SCS 上）。
    #   Enum MU0|MU1|MU2|MU3 → 15/30/60/120 kHz。
    TDD_SCS = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:SUBCarrier:SPACing"
    TDD_DL_SLOTS = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:DLSLots"    # Int 0..160
    TDD_DL_SYMBOLS = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:DLSYmbols"  # Int 0..14
    TDD_UL_SLOTS = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:ULSLots"    # Int 0..160
    TDD_UL_SYMBOLS = "BSE:CONFig:NR5G:{cell}:SCHeduling:TDDPATtern:ULSYmbols"  # Int 0..14
    # ⚠️ TDD_PATTERN（pattern 字符串）**手册里不存在**，保持 None ——
    #    驱动把 TestCase 的 "DDDSU" 展开成上面六条。
    TDD_PATTERN = None

    HARQ_MAX_TRANS = "BSE:CONFig:NR5G:{cell}:PHY:DL:HARQ:MAXTrans"   # Enum N1..N28
    HARQ_PROCESSES = "BSE:CONFig:NR5G:{cell}:PHY:DL:HARQ:PROCesses"  # Enum N1..N32
    # Enum P1|P2|P4|P8|P12|P16|P24|P32（默认 P1），带 <cri> 资源索引维度
    CSIRS_PORTS = (
        "BSE:CONFig:NR5G:{cell}:CSI:RESource:CONFig:NZP:CRI0:RM:NPORts")
    # 小区 ON 时不发它，上面这些改动**不进协议栈**（手册原文）
    # ⚠ Quick Config 有**自己的** apply（Imm Action）——
    #   `BSE:CONFig:NR5G:APPLY` 是 General 段的「把小区缓存配置推进协议栈」，
    #   **管不着** Quick Config 的三条输入参数。不发这条，SCENario / MCS /
    #   NUM:PRBs 永远只是暂存值（内审 F2）。
    #   ⚠ 手册：应用场景会把当前 scheduler 配置**完全抹掉并替换** ——
    #   所以它必须发在 slot 级 AMC 写入**之前**，否则把刚配好的 AMC 抹了。
    QCONFIG_APPLY_ALL = "BSE:CONFig:NR5G:SCHeduling:QCONFig:APPLy:ALL"
    # ⛔ 复用既有的 `CONFIG_APPLY`（同一条命令别起第二个名，内审 F9）
    PHY_DL_BWP_NUM_PRBS = "BSE:CONFig:NR5G:{cell}:PHY:DL:{bwp}:NUM:PRBS"
    # ⛔ 统计窗口：普通 NR 小区手册里**没有**这条命令（只有 LTE / NBIot /
    #    NR5G:SLINk 三种）。保持 None，由驱动归入「已知无对应命令」显式清单。
    MEAS_TPUT_STAT_COUNT = None
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
    # 整带宽口径（2026-08-07 NotebookLM 手册原文）。手册推荐用 :CHANnel
    # （TA v15.26.6 起引入，为跟 LTE 接口对齐）；旧别名 :DBmBw 行为相同。
    # ⚠ 手册标 `Application Mode : NSA | SA`，**未覆盖 LTE_NR_IRAT** ——
    #   跟本 profile 其它命令同一处境，下发后查 SYST:ERR? 才知道认不认。
    DL_POWER_CHANNEL = "BSE:CONFig:NR5G:{cell}:DL:POWer:CHANnel"
    SSB_POWER = "BSE:CONFig:NR5G:{cell}:SSB:POWer:ADVertised"
    SCELL_CONF_BAND = "BSE:CONFig:LTE:{cell}:CAGGregation:AGGRegate:SCC:LIST"
    SCELL_ADD = "BSE:CONFig:LTE:{cell}:CAGGregation:ACTivate:SCC:LIST"
    SCELL_LIST_QUERY = "BSE:CONFig:LTE:{cell}:CAGGregation:AGGRegate:SCC:LIST?"

    # === 本 profile 未定义（留 None）—— ⚠️ **不是「已验证不支持」** ===
    #
    # ⚠️ 这行原文写的是 "Verified unsupported in this app"，**那个断言没有依据**
    #    （P1-32 / 2026-08-04 查证后改）：
    #    · 手册原件实查：这些命令标 `Application Mode : NSA | SA`（不含 `IRAT`），
    #      **但本 profile 已定义、现场在用的 `CELL_BAND` / `CELL_DL_ARFCN` /
    #      `CELL_DL_BW` 同样标 `NSA | SA`** —— 该字段答不了 TAP 可用性；
    #    · 真机普查也没覆盖过它们 —— `uxm_scpi_compatibility` 的模板遍历
    #      **显式跳过 `None` 属性**，所以 2026-05-13 那次现场普查探的是"已定义的"，
    #      这批从头到尾没被问过。
    #    结论：**未经查证**，两个方向都不下。出发前普查确认（要先临时补进去才探得到）。
    #
    # ⚠️ 下面这份清单**本身也会 stale** —— 例如 `MEAS_CSI_*` 已由 #275/P1-31
    #    补进本 profile（`MEAS_CSI_CQI/RI/START/STOP/STATE`），却仍列在这里。
    #    **以类里的实际赋值为准，别信这份清单。**
    # MIMO_DL_CODEBOOK, MIMO_TX/RX_ANT_PORT*,
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
