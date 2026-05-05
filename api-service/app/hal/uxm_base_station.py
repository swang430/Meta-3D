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
from typing import Dict, Any, List, Optional
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

logger = logging.getLogger(__name__)


# ===========================================================================
# UXM SCPI 命令映射表
# ===========================================================================

class UxmScpiCommands:
    """UXM 5G NR SCPI 命令速查表 (从官方文档提取)

    命名约定:
      <cell> = CELL0 | CELL1 | CELL2 | CELL3  (最多 4 个 NR 小区)
      <BWP>  = BWP0 | BWP1                      (带宽部分)
    """

    # --- 系统 ---
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    CLS = "*CLS"
    ERR = "SYSTem:ERRor?"

    # --- 应用选择 ---
    APP_SELECT = 'SYSTem:APPLication:NAME "5G_NR_Test"'

    # --- 小区配置 (CONFig:NR5G 子系统) ---
    CELL_BAND = "CONFig:NR5G:{cell}:BAND"                    # e.g., "N78"
    CELL_DL_ARFCN = "CONFig:NR5G:{cell}:DL:ARFCN"            # DL ARFCN
    CELL_DL_BW = "CONFig:NR5G:{cell}:DL:BW"                  # DL 带宽 (MHz)
    CELL_UL_BW = "CONFig:NR5G:{cell}:UL:BW"                  # UL 带宽 (MHz)
    CELL_SCS = "CONFig:NR5G:{cell}:SCS"                       # 子载波间隔 (kHz)
    CELL_DUPLEX = "CONFig:NR5G:{cell}:DUPLex"                 # TDD/FDD
    CELL_ACTIVE = "CONFig:NR5G:{cell}:ACTive:STATe"           # 小区激活
    CELL_DL_POINTA = "CONFig:NR5G:{cell}:DL:POINta"           # Point A (Hz)

    # --- SSB (同步信号块) ---
    SSB_ARFCN = "CONFig:NR5G:{cell}:{bwp}:SSB:NCD:ARFCn"

    # --- 下行功率 ---
    DL_POWER = "CONFig:NR5G:{cell}:PHY:DL:POWer"              # 总下行功率
    PDSCH_POWER = "CONFig:NR5G:{cell}:{bwp}:PDSCH:POWer"      # PDSCH 功率
    SSB_POWER = "CONFig:NR5G:{cell}:SSB:POWer"                # SSB 功率

    # --- PDSCH/PUSCH 传输配置 ---
    PDSCH_MCS = "CONFig:NR5G:{cell}:{bwp}:PDSCH:MCS"
    PDSCH_RB_ALLOC = "CONFig:NR5G:{cell}:{bwp}:PDSCH:RB:ALLocation"
    PUSCH_MCS = "CONFig:NR5G:{cell}:{bwp}:PUSCH:MCS"
    PUSCH_RB_ALLOC = "CONFig:NR5G:{cell}:{bwp}:PUSCH:RB:ALLocation"

    # --- MIMO 逻辑层配置 ---
    MIMO_DL_LAYERS = "CONFig:NR5G:{cell}:PHY:DL:MIMO:LAYers"
    MIMO_DL_CODEBOOK = "CONFig:NR5G:{cell}:PHY:DL:MIMO:CODEbook"

    # --- MIMO 天线到物理端口路由 (Layer 1) ---
    # 将 NR 逻辑天线映射到 UXM 前面板的物理 RF 端口
    # 语法: ROUTe:NR5G:CELL0:HARDware:TX:ANTenna{n}:PORT RF{m}OUT
    #       ROUTe:NR5G:CELL0:HARDware:RX:ANTenna{n}:PORT RF{m}IN
    #
    # 物理端口命名约定 (UXM E7515B 前面板):
    #   RF1OUT / RF1IN  — 第 1 组射频端口
    #   RF2OUT / RF2IN  — 第 2 组射频端口
    #   RF3OUT / RF3IN  — 第 3 组射频端口 (4x4 MIMO 需要)
    #   RF4OUT / RF4IN  — 第 4 组射频端口 (4x4 MIMO 需要)
    MIMO_TX_ANT_PORT = "ROUTe:NR5G:{cell}:HARDware:TX:ANTenna{ant}:PORT"
    MIMO_RX_ANT_PORT = "ROUTe:NR5G:{cell}:HARDware:RX:ANTenna{ant}:PORT"
    MIMO_TX_ANT_PORT_QUERY = "ROUTe:NR5G:{cell}:HARDware:TX:ANTenna{ant}:PORT?"
    MIMO_RX_ANT_PORT_QUERY = "ROUTe:NR5G:{cell}:HARDware:RX:ANTenna{ant}:PORT?"

    # --- 信令 / 连接管理 ---
    CELL_STATE_ON = "CONFig:NR5G:{cell}:ACTive:STATe ON"
    CELL_STATE_OFF = "CONFig:NR5G:{cell}:ACTive:STATe OFF"
    CELL_STATE_QUERY = "CONFig:NR5G:{cell}:ACTive:STATe?"

    # --- 吞吐量测量 (MEASure 子系统) ---
    MEAS_BTHROUGHPUT_DL_START = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STARt"
    MEAS_BTHROUGHPUT_DL_STOP = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STOP"
    MEAS_BTHROUGHPUT_DL_JSON = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:JSON?"
    MEAS_BTHROUGHPUT_DL_BLER = "MEASure:NR5G:{cell}:BTHRoughput:DL:BLER:STATistical:ALL?"

    # --- Phase 2e: UE Capability + RRC reconfiguration ---
    # NOTE: UXM firmware ≥ V12.x exposes UE capability via CALL:NR5G:CELL:UEINFO
    #       subsystem. Older firmware (V10/V11) uses CALL:NR5G:CELL:UE:CAPability.
    #       Operators on different firmware should override the format strings
    #       below in their lab profile config.
    UE_CAPABILITY_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability?"
    UE_MAX_DL_LAYERS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MIMO:DL:LAYers?"
    UE_MAX_UL_LAYERS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MIMO:UL:LAYers?"
    UE_MAX_MODULATION_DL_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:MODulation:DL?"
    UE_SUPPORTED_BANDS_QUERY = "CALL:NR5G:{cell}:UEINFO:CAPability:BANDs?"

    RRC_RECONFIG_LAYERS = "CALL:NR5G:{cell}:RRC:RECon:MIMO:LAYers {layers}"
    RRC_RECONFIG_MODULATION = "CALL:NR5G:{cell}:RRC:RECon:MODulation:DL {mod}"
    RRC_RECONFIG_APPLY = "CALL:NR5G:{cell}:RRC:RECon:APPLy"

    # --- CSI 测量 (CQI, RI, PMI) ---
    MEAS_CSI_START = "MEASure:NR5G:{cell}:CSI:STARt"
    MEAS_CSI_STOP = "MEASure:NR5G:{cell}:CSI:STOP"
    MEAS_CSI_CQI = "MEASure:NR5G:{cell}:CSI:CQI:STATistics?"
    MEAS_CSI_RI = "MEASure:NR5G:{cell}:CSI:RI:HISTogram?"

    # --- UE 测量上报 (RSRP / SINR) ---
    # UXM 通过 UE Measurement Report 子系统获取 L3 滤波后的 RSRP 和 SINR
    # 返回格式: "mean,min,max" (dBm / dB)
    MEAS_UE_RSRP = "MEASure:NR5G:{cell}:UEReport:RSRP:STATistics?"
    MEAS_UE_SINR = "MEASure:NR5G:{cell}:UEReport:SINR:STATistics?"

    # --- EVM (错误向量幅度) ---
    MEAS_EVM_START = "MEASure:NR5G:{cell}:PHY:EVM:STARt"

    # --- 配置文件保存/恢复 (一键配置) ---
    # UXM 支持将完整仪器状态（小区参数、功率、MIMO、RF 路由等）
    # 保存为 .state 文件，之后通过单条 SCPI 命令一次恢复全部配置。
    # 文件存储在 UXM 本机的 D:\User Files\ 目录下。
    STATE_SAVE = 'SYSTem:CONFiguration:SAVE "{filepath}"'
    STATE_LOAD = 'SYSTem:CONFiguration:LOAD "{filepath}"'
    STATE_LIST = 'MMEMory:CATalog? "D:\\User Files"'

    # --- RF 路由 (射频通路配置) ---
    RF_CONNECTOR = "CONFig:NR5G:{cell}:RFSettings:CHANnel"
    RF_PORT_DL = "CONFig:NR5G:{cell}:RFSettings:DL:PORT"
    RF_PORT_UL = "CONFig:NR5G:{cell}:RFSettings:UL:PORT"

    # --- TDD 配置 ---
    TDD_PATTERN = "CONFig:NR5G:{cell}:TDD:PATTern"
    TDD_PERIOD  = "CONFig:NR5G:{cell}:TDD:PERiod"

    # --- PDSCH 调度算法 (Full Buffer 模式) ---
    # Full Buffer = UXM 持续调度 PDSCH，不留空 TTI
    # 这是 3GPP TR 37.977 MAC 吞吐量测试的强制要求
    PDSCH_SCHED_ALGO = "CONFig:NR5G:{cell}:{bwp}:PDSCH:SchedAlgoritm"

    # --- AMC (自适应调制编码) 开关 ---
    # AMC OFF = 固定 MCS，不随 CQI 变化
    # 3GPP 规范要求关闭 AMC，确保吞吐量测试结果可重复
    PDSCH_AMC_ENABLE  = "CONFig:NR5G:{cell}:{bwp}:PDSCH:AMC:ENABle"
    PUSCH_AMC_ENABLE  = "CONFig:NR5G:{cell}:{bwp}:PUSCH:AMC:ENABle"

    # --- HARQ 配置 ---
    HARQ_MAX_TRANS   = "CONFig:NR5G:{cell}:HARQ:MaxTrans"
    HARQ_PROCESSES   = "CONFig:NR5G:{cell}:HARQ:PROCesses"

    # --- CSI-RS 端口数 (须与 MIMO 层数匹配) ---
    # 2x2 MIMO → 4 CSI-RS 端口; 4x4 MIMO → 8 CSI-RS 端口
    CSIRS_PORTS = "CONFig:NR5G:{cell}:CSIRS:PORTs"

    # --- 吞吐量统计窗口 ---
    # 3GPP TR 37.977 建议统计窗口 ≥ 5000 个子帧 (≥ 5 秒)
    MEAS_TPUT_STAT_COUNT  = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:COUNt"
    MEAS_TPUT_UL_JSON     = "MEASure:NR5G:{cell}:BTHRoughput:UL:TSTatistics:JSON?"
    MEAS_TPUT_UL_BLER     = "MEASure:NR5G:{cell}:BTHRoughput:UL:BLER:STATistical:ALL?"

    # --- 状态查询 ---
    STATUS_FAULTY = "STATus:FAULty:RECovery"


# VISA 超时常量
VISA_TIMEOUT_DEFAULT = 5000  # ms
VISA_TIMEOUT_CELL = 30000
VISA_TIMEOUT_ATTACH = 90000
VISA_TIMEOUT_STATE_LOAD = 60000  # 配置文件加载可能需要较长时间

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


def _infer_band_from_freq(freq_mhz: float) -> tuple:
    """从频率推断 NR 频段和双工模式"""
    for min_f, max_f, band, duplex in FREQ_TO_BAND_MAP:
        if min_f <= freq_mhz <= max_f:
            return band, duplex
    return "N78", "TDD"  # 默认 fallback


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
        # VISA session
        self._visa_rm = None
        self._visa_session = None
        # 小区配置状态
        self._cell_id: str = "CELL0"  # 默认使用主小区
        self._bwp_id: str = "BWP0"
        self._band: str = "N78"
        self._frequency_mhz: float = 3500.0
        self._bandwidth_mhz: float = 100.0
        self._scs_khz: int = 30
        self._dl_power_dbm: float = -50.0
        self._cell_state: CellState = CellState.OFF

    # ===================================================================
    # 1. 连接生命周期
    # ===================================================================

    async def connect(self) -> bool:
        """通过 PyVISA 建立与 UXM 的连接"""
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()

            if self.visa_resource:
                resource_str = self.visa_resource
            elif self.protocol.upper() == "HISLIP":
                resource_str = f"TCPIP::{self.ip_address}::hislip0::INSTR"
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
            logger.info(f"[UXM] Connected: {idn}")

            # 清除状态
            self._write("*CLS")

            # 选择 5G NR 测试应用
            self._write(UxmScpiCommands.APP_SELECT)
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

    # ===================================================================
    # 2. 小区配置
    # ===================================================================

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置 UXM NR5G 物理小区参数。

        完整 SCPI 序列:
          CONFig:NR5G:CELL0:BAND N78
          CONFig:NR5G:CELL0:DUPLex TDD         ← 必须在 BAND 之后设置
          CONFig:NR5G:CELL0:DL:BW 100
          CONFig:NR5G:CELL0:UL:BW 100
          CONFig:NR5G:CELL0:SCS 30
          CONFig:NR5G:CELL0:DL:ARFCN 632628
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

        cell = config.get("cell_id", self._cell_id)
        try:
            # ---- 0. 频率 → 频段/双工 自动推断 ----
            if "frequency_mhz" in config:
                self._frequency_mhz = config["frequency_mhz"]
                # 如果用户没有显式给 band 和 duplex，从频率自动推断
                if "band" not in config or "duplex" not in config:
                    inferred_band, inferred_duplex = _infer_band_from_freq(
                        self._frequency_mhz
                    )
                    if "band" not in config:
                        config["band"] = inferred_band
                    if "duplex" not in config:
                        config["duplex"] = inferred_duplex
                    logger.info(
                        f"[UXM] Auto-inferred: {self._frequency_mhz} MHz "
                        f"→ {config.get('band')}/{config.get('duplex')}"
                    )

            # ---- 1. 频段 (Band) ----
            if "band" in config:
                band = config["band"].upper()
                self._band = band
                self._write(
                    UxmScpiCommands.CELL_BAND.format(cell=cell) + f" {band}"
                )

            # ---- 2. 双工模式 (必须紧跟 Band 之后) ----
            if "duplex" in config:
                duplex_mode = config["duplex"].upper()
                self._write(
                    UxmScpiCommands.CELL_DUPLEX.format(cell=cell)
                    + f" {duplex_mode}"
                )
                logger.info(f"[UXM] Duplex: {duplex_mode}")

            # ---- 3. 带宽 (DL + UL 同步设置) ----
            if "bandwidth_mhz" in config:
                bw = config["bandwidth_mhz"]
                self._bandwidth_mhz = bw
                self._write(
                    UxmScpiCommands.CELL_DL_BW.format(cell=cell)
                    + f" {int(bw)}"
                )
                self._write(
                    UxmScpiCommands.CELL_UL_BW.format(cell=cell)
                    + f" {int(bw)}"
                )

            # ---- 4. 子载波间隔 ----
            if "scs_khz" in config:
                scs = config["scs_khz"]
                self._scs_khz = scs
                self._write(
                    UxmScpiCommands.CELL_SCS.format(cell=cell) + f" {scs}"
                )

            # ---- 5. ARFCN (自动查表或手动指定) ----
            if "arfcn" in config:
                arfcn = config["arfcn"]
            else:
                arfcn = NR_BAND_ARFCN_MAP.get(self._band, 632628)
            self._write(
                UxmScpiCommands.CELL_DL_ARFCN.format(cell=cell)
                + f" {arfcn}"
            )

            # ---- 6. MIMO 层数 ----
            if "mimo_layers" in config:
                layers = config["mimo_layers"]
                self._write(
                    UxmScpiCommands.MIMO_DL_LAYERS.format(cell=cell)
                    + f" {layers}"
                )

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
                self._write(
                    UxmScpiCommands.DL_POWER.format(cell=cell)
                    + f" {self._dl_power_dbm:.1f}"
                )

            # ---- 9. SSB 功率 ----
            if "ssb_power_dbm" in config:
                self._write(
                    UxmScpiCommands.SSB_POWER.format(cell=cell)
                    + f" {config['ssb_power_dbm']:.1f}"
                )

            # ---- 10. PDSCH RB 分配 (Full allocation 默认) ----
            if "pdsch_rb_alloc" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                self._write(
                    UxmScpiCommands.PDSCH_RB_ALLOC.format(cell=cell, bwp=bwp)
                    + f" {config['pdsch_rb_alloc']}"
                )

            # ---- 11. RF 通道级端口路由 (Layer 2, 备选) ----
            if "rf_port_dl" in config:
                self._write(
                    UxmScpiCommands.RF_PORT_DL.format(cell=cell)
                    + f" {config['rf_port_dl']}"
                )
            if "rf_port_ul" in config:
                self._write(
                    UxmScpiCommands.RF_PORT_UL.format(cell=cell)
                    + f" {config['rf_port_ul']}"
                )

            # ---- 12. TDD 时隙格式 ----
            if "tdd_pattern" in config:
                self._write(
                    UxmScpiCommands.TDD_PATTERN.format(cell=cell)
                    + f" {config['tdd_pattern'].upper()}"
                )
            if "tdd_period" in config:
                self._write(
                    UxmScpiCommands.TDD_PERIOD.format(cell=cell)
                    + f" {config['tdd_period']}"
                )

            # ---- 13. PDSCH 调度算法 (Full Buffer) ----
            if "sched_algo" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                self._write(
                    UxmScpiCommands.PDSCH_SCHED_ALGO.format(cell=cell, bwp=bwp)
                    + f" {config['sched_algo'].upper()}"
                )

            # ---- 14. AMC 开关 (关闭以固定 MCS) ----
            if "enable_amc" in config:
                bwp = config.get("bwp_id", self._bwp_id)
                amc_val = "ON" if config["enable_amc"] else "OFF"
                self._write(
                    UxmScpiCommands.PDSCH_AMC_ENABLE.format(cell=cell, bwp=bwp)
                    + f" {amc_val}"
                )
                self._write(
                    UxmScpiCommands.PUSCH_AMC_ENABLE.format(cell=cell, bwp=bwp)
                    + f" {amc_val}"
                )
                logger.info(f"[UXM] AMC: {amc_val}")

            # ---- 15. HARQ 配置 ----
            if "harq_max_trans" in config:
                self._write(
                    UxmScpiCommands.HARQ_MAX_TRANS.format(cell=cell)
                    + f" {config['harq_max_trans']}"
                )
            if "harq_processes" in config:
                self._write(
                    UxmScpiCommands.HARQ_PROCESSES.format(cell=cell)
                    + f" {config['harq_processes']}"
                )

            # ---- 16. CSI-RS 端口数 (与 MIMO 层数对齐) ----
            if "csi_rs_ports" in config:
                self._write(
                    UxmScpiCommands.CSIRS_PORTS.format(cell=cell)
                    + f" {config['csi_rs_ports']}"
                )
            elif "mimo_layers" in config:
                # 自动推断: 1L→2ports, 2L→4ports, 4L→8ports
                auto_ports = max(2, config["mimo_layers"] * 2)
                self._write(
                    UxmScpiCommands.CSIRS_PORTS.format(cell=cell)
                    + f" {auto_ports}"
                )

            # ---- 17. 统计窗口 (子帧数) ----
            if "stat_count" in config:
                self._write(
                    UxmScpiCommands.MEAS_TPUT_STAT_COUNT.format(cell=cell)
                    + f" {config['stat_count']}"
                )

            # 同步等待
            self._query("*OPC?")
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
                    UxmScpiCommands.MIMO_TX_ANT_PORT.format(
                        cell=cell, ant=ant_num
                    ) + f" {port_name}"
                )

            # 配置 RX 天线端口
            for ant_num, port_name in rx_map.items():
                self._write(
                    UxmScpiCommands.MIMO_RX_ANT_PORT.format(
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
                    UxmScpiCommands.MIMO_TX_ANT_PORT_QUERY.format(
                        cell=cell, ant=ant_num
                    )
                ).strip()
                if tx_port and "NONE" not in tx_port.upper():
                    result["tx"][ant_num] = tx_port

                # RX
                rx_port = self._query(
                    UxmScpiCommands.MIMO_RX_ANT_PORT_QUERY.format(
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
                    UxmScpiCommands.PDSCH_MCS.format(cell=cell, bwp=bwp)
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
                UxmScpiCommands.PDSCH_SCHED_ALGO.format(cell=cell, bwp=bwp)
                + " FULLBUFFER"
            )

            # 2. AMC 开关
            amc_val = "ON" if enable_amc else "OFF"
            self._write(
                UxmScpiCommands.PDSCH_AMC_ENABLE.format(cell=cell, bwp=bwp)
                + f" {amc_val}"
            )
            self._write(
                UxmScpiCommands.PUSCH_AMC_ENABLE.format(cell=cell, bwp=bwp)
                + f" {amc_val}"
            )

            # 3. 固定 MCS (当 AMC=OFF 时生效)
            self._write(
                UxmScpiCommands.PDSCH_MCS.format(cell=cell, bwp=bwp)
                + f" {mcs}"
            )

            # 4. 全 RB 分配
            self._write(
                UxmScpiCommands.PDSCH_RB_ALLOC.format(cell=cell, bwp=bwp)
                + f" {rb_alloc}"
            )

            # 5. TDD 时隙格式
            self._write(
                UxmScpiCommands.TDD_PATTERN.format(cell=cell)
                + f" {tdd_pattern}"
            )
            self._write(
                UxmScpiCommands.TDD_PERIOD.format(cell=cell)
                + f" {tdd_period}"
            )

            # 6. HARQ
            self._write(
                UxmScpiCommands.HARQ_MAX_TRANS.format(cell=cell)
                + f" {harq_max_trans}"
            )
            self._write(
                UxmScpiCommands.HARQ_PROCESSES.format(cell=cell)
                + f" {harq_processes}"
            )

            # 7. CSI-RS 端口数 (1L→2ports, 2L→4ports, 4L→8ports)
            csi_rs_ports = max(2, mimo_layers * 2)
            self._write(
                UxmScpiCommands.CSIRS_PORTS.format(cell=cell)
                + f" {csi_rs_ports}"
            )

            # 8. 统计窗口
            self._write(
                UxmScpiCommands.MEAS_TPUT_STAT_COUNT.format(cell=cell)
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
                UxmScpiCommands.DL_POWER.format(cell=self._cell_id)
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
            self._write(UxmScpiCommands.CELL_STATE_ON.format(cell=cell))
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
                    UxmScpiCommands.CELL_STATE_QUERY.format(cell=cell)
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
                UxmScpiCommands.CELL_STATE_OFF.format(cell=self._cell_id)
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
                UxmScpiCommands.CELL_STATE_QUERY.format(cell=self._cell_id)
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
                UxmScpiCommands.STATE_LOAD.format(filepath=filepath)
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
                UxmScpiCommands.STATE_SAVE.format(filepath=filepath)
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
            result = self._query(UxmScpiCommands.STATE_LIST)
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
                UxmScpiCommands.CELL_BAND.format(cell=cell) + "?"
            ).strip()
            if band:
                self._band = band.upper()

            # 回读带宽
            bw = self._query(
                UxmScpiCommands.CELL_DL_BW.format(cell=cell) + "?"
            ).strip()
            if bw:
                self._bandwidth_mhz = float(bw)

            # 回读 SCS
            scs = self._query(
                UxmScpiCommands.CELL_SCS.format(cell=cell) + "?"
            ).strip()
            if scs:
                self._scs_khz = int(float(scs))

            # 回读功率
            pwr = self._query(
                UxmScpiCommands.DL_POWER.format(cell=cell) + "?"
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
                UxmScpiCommands.MEAS_BTHROUGHPUT_DL_JSON.format(cell=cell)
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
                UxmScpiCommands.MEAS_BTHROUGHPUT_DL_BLER.format(cell=cell)
            )
            if bler_str and bler_str.strip():
                try:
                    metrics.dl_bler = float(bler_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # ── UL 吞吐量 ──
            ul_json = self._query(
                UxmScpiCommands.MEAS_TPUT_UL_JSON.format(cell=cell)
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
                UxmScpiCommands.MEAS_TPUT_UL_BLER.format(cell=cell)
            )
            if ul_bler_str and ul_bler_str.strip():
                try:
                    metrics.ul_bler = float(ul_bler_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # ── CQI (均值, 格式: "mean,std,min,max,...") ──
            cqi_str = self._query(
                UxmScpiCommands.MEAS_CSI_CQI.format(cell=cell)
            )
            if cqi_str and cqi_str.strip():
                try:
                    metrics.cqi = int(float(cqi_str.split(",")[0]))
                except (ValueError, IndexError):
                    pass

            # ── RI (均值, 直方图第一个值) ──
            ri_str = self._query(
                UxmScpiCommands.MEAS_CSI_RI.format(cell=cell)
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
                UxmScpiCommands.MEAS_UE_RSRP.format(cell=cell)
            )
            if rsrp_str and rsrp_str.strip():
                try:
                    metrics.rsrp_dbm = float(rsrp_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # ── SINR (UE 测量上报, 格式: "mean,min,max") ──
            sinr_str = self._query(
                UxmScpiCommands.MEAS_UE_SINR.format(cell=cell)
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
            self._write(UxmScpiCommands.MEAS_BTHROUGHPUT_DL_START.format(cell=cell))
        except Exception as e:  # noqa: BLE001
            logger.warning("[UXM] BTHR:DL:START failed (%s) — falling back to plain query", e)
            return await self.get_throughput_metrics()

        try:
            await asyncio.sleep(max(window_s, 0.0))
            metrics = await self.get_throughput_metrics()
        finally:
            try:
                self._write(UxmScpiCommands.MEAS_BTHROUGHPUT_DL_STOP.format(cell=cell))
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

        max_dl = _safe_query(UxmScpiCommands.UE_MAX_DL_LAYERS_QUERY, lambda s: int(float(s)))
        max_ul = _safe_query(UxmScpiCommands.UE_MAX_UL_LAYERS_QUERY, lambda s: int(float(s)))
        max_mod = _safe_query(UxmScpiCommands.UE_MAX_MODULATION_DL_QUERY)
        bands_str = _safe_query(UxmScpiCommands.UE_SUPPORTED_BANDS_QUERY)
        bands = (
            [b.strip() for b in bands_str.split(",") if b.strip()]
            if bands_str else []
        )

        source = "real_ue" if max_dl is not None else "unavailable"
        if source == "unavailable":
            logger.warning(
                "[UXM] UE capability unavailable (likely no UE attached or "
                "firmware doesn't support UEINFO subsystem; check operator's "
                "UXM version against UxmScpiCommands.UE_CAPABILITY_* SCPI strings)"
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
                self._write(UxmScpiCommands.RRC_RECONFIG_LAYERS.format(
                    cell=cell, layers=int(mimo_layers)
                ))
            if modulation is not None:
                self._write(UxmScpiCommands.RRC_RECONFIG_MODULATION.format(
                    cell=cell, mod=modulation
                ))
            self._write(UxmScpiCommands.RRC_RECONFIG_APPLY.format(cell=cell))
            self._query(UxmScpiCommands.OPC)
            logger.info(
                "[UXM] RRC reconfigured: layers=%s modulation=%s",
                mimo_layers, modulation,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("[UXM] RRC reconfiguration failed: %s", e)
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

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        if not self._visa_session:
            raise ConnectionError("[UXM] Not connected")
        self._visa_session.write(cmd)

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        if not self._visa_session:
            raise ConnectionError("[UXM] Not connected")
        return self._visa_session.query(cmd)

    def _check_errors(self) -> None:
        """检查并清除错误队列"""
        while True:
            err = self._query(UxmScpiCommands.ERR).strip()
            if err.startswith("0,") or err.startswith("+0,"):
                break
            logger.warning(f"[UXM] Instrument error: {err}")

