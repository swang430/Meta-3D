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

    # --- MIMO ---
    MIMO_DL_LAYERS = "CONFig:NR5G:{cell}:PHY:DL:MIMO:LAYers"
    MIMO_DL_CODEBOOK = "CONFig:NR5G:{cell}:PHY:DL:MIMO:CODEbook"

    # --- 信令 / 连接管理 ---
    CELL_STATE_ON = "CONFig:NR5G:{cell}:ACTive:STATe ON"
    CELL_STATE_OFF = "CONFig:NR5G:{cell}:ACTive:STATe OFF"
    CELL_STATE_QUERY = "CONFig:NR5G:{cell}:ACTive:STATe?"

    # --- 吞吐量测量 (MEASure 子系统) ---
    MEAS_BTHROUGHPUT_DL_START = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STARt"
    MEAS_BTHROUGHPUT_DL_STOP = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:STOP"
    MEAS_BTHROUGHPUT_DL_JSON = "MEASure:NR5G:{cell}:BTHRoughput:DL:TSTatistics:JSON?"
    MEAS_BTHROUGHPUT_DL_BLER = "MEASure:NR5G:{cell}:BTHRoughput:DL:BLER:STATistical:ALL?"

    # --- CSI 测量 (CQI, RI, PMI) ---
    MEAS_CSI_START = "MEASure:NR5G:{cell}:CSI:STARt"
    MEAS_CSI_STOP = "MEASure:NR5G:{cell}:CSI:STOP"
    MEAS_CSI_CQI = "MEASure:NR5G:{cell}:CSI:CQI:STATistics?"
    MEAS_CSI_RI = "MEASure:NR5G:{cell}:CSI:RI:HISTogram?"

    # --- EVM (错误向量幅度) ---
    MEAS_EVM_START = "MEASure:NR5G:{cell}:PHY:EVM:STARt"

    # --- 状态查询 ---
    STATUS_FAULTY = "STATus:FAULty:RECovery"


# VISA 超时常量
VISA_TIMEOUT_DEFAULT = 5000  # ms
VISA_TIMEOUT_CELL = 30000
VISA_TIMEOUT_ATTACH = 90000

# 默认 ARFCN 映射 (NR 频段 → ARFCN)
NR_BAND_ARFCN_MAP = {
    "N78": 632628,  # 3.5 GHz
    "N41": 499200,  # 2.5 GHz
    "N77": 620000,  # C-Band
    "N79": 693334,  # 4.7 GHz
}


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
        """应用配置 (委托给 set_cell_config)"""
        return await self.set_cell_config(config)

    # ===================================================================
    # 2. 小区配置
    # ===================================================================

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置 UXM NR5G 物理小区参数。

        SCPI 序列:
          CONFig:NR5G:CELL0:BAND N78
          CONFig:NR5G:CELL0:DL:BW 100
          CONFig:NR5G:CELL0:SCS 30
          CONFig:NR5G:CELL0:DUPLex TDD
          CONFig:NR5G:CELL0:DL:ARFCN 632628
        """
        cell = config.get("cell_id", self._cell_id)
        try:
            # 频段
            if "band" in config:
                band = config["band"].upper()
                self._band = band
                self._write(
                    UxmScpiCommands.CELL_BAND.format(cell=cell) + f" {band}"
                )

            # 带宽
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

            # 子载波间隔
            if "scs_khz" in config:
                scs = config["scs_khz"]
                self._scs_khz = scs
                self._write(
                    UxmScpiCommands.CELL_SCS.format(cell=cell) + f" {scs}"
                )

            # 双工模式
            if "duplex" in config:
                self._write(
                    UxmScpiCommands.CELL_DUPLEX.format(cell=cell)
                    + f" {config['duplex'].upper()}"
                )

            # ARFCN (自动查表或手动指定)
            if "arfcn" in config:
                arfcn = config["arfcn"]
            else:
                arfcn = NR_BAND_ARFCN_MAP.get(self._band, 632628)
            self._write(
                UxmScpiCommands.CELL_DL_ARFCN.format(cell=cell)
                + f" {arfcn}"
            )

            # 频率 (如果直接指定)
            if "frequency_mhz" in config:
                self._frequency_mhz = config["frequency_mhz"]

            # MIMO 层数
            if "mimo_layers" in config:
                layers = config["mimo_layers"]
                self._write(
                    UxmScpiCommands.MIMO_DL_LAYERS.format(cell=cell)
                    + f" {layers}"
                )

            # 同步等待
            self._query("*OPC?")
            self._set_status(InstrumentStatus.READY)
            logger.info(
                f"[UXM] Cell config: band={self._band}, "
                f"BW={self._bandwidth_mhz}MHz, SCS={self._scs_khz}kHz"
            )
            return True

        except Exception as e:
            logger.error(f"[UXM] set_cell_config failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def set_frc_config(
        self,
        frc_reference: str,
        modulation: Optional[str] = None,
        target_coding_rate: Optional[float] = None,
    ) -> bool:
        """
        配置 FRC (固定参考信道)。

        UXM 通过 PDSCH MCS 和 RB 分配间接配置 FRC。
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
    # 4. 吞吐量与 CSI 测量
    # ===================================================================

    async def get_throughput_metrics(self) -> ThroughputMetrics:
        """
        轮询读取 MAC 吞吐量指标。

        SCPI:
          MEASure:NR5G:CELL0:BTHRoughput:DL:TSTatistics:JSON?
          MEASure:NR5G:CELL0:BTHRoughput:DL:BLER:STATistical:ALL?
          MEASure:NR5G:CELL0:CSI:CQI:STATistics?
          MEASure:NR5G:CELL0:CSI:RI:HISTogram?
        """
        cell = self._cell_id
        metrics = ThroughputMetrics()

        try:
            # DL 吞吐量 (JSON 格式)
            tput_json = self._query(
                UxmScpiCommands.MEAS_BTHROUGHPUT_DL_JSON.format(cell=cell)
            )
            if tput_json and tput_json.strip():
                import json
                try:
                    tput_data = json.loads(tput_json)
                    metrics.dl_throughput_mbps = tput_data.get(
                        "DL_Throughput_Mbps", 0.0
                    )
                except json.JSONDecodeError:
                    # 尝试简单数值解析
                    pass

            # DL BLER
            bler_str = self._query(
                UxmScpiCommands.MEAS_BTHROUGHPUT_DL_BLER.format(cell=cell)
            )
            if bler_str and bler_str.strip():
                try:
                    metrics.dl_bler = float(bler_str.split(",")[0])
                except (ValueError, IndexError):
                    pass

            # CQI
            cqi_str = self._query(
                UxmScpiCommands.MEAS_CSI_CQI.format(cell=cell)
            )
            if cqi_str and cqi_str.strip():
                try:
                    metrics.cqi = int(float(cqi_str.split(",")[0]))
                except (ValueError, IndexError):
                    pass

            # RI
            ri_str = self._query(
                UxmScpiCommands.MEAS_CSI_RI.format(cell=cell)
            )
            if ri_str and ri_str.strip():
                try:
                    metrics.rank_indicator = int(float(ri_str.split(",")[0]))
                except (ValueError, IndexError):
                    pass

        except Exception as e:
            logger.warning(f"[UXM] get_throughput_metrics partial fail: {e}")

        return metrics

    async def get_ue_info(self) -> Dict[str, Any]:
        """获取 UE 信息 (TODO: 从 UXM 查询)"""
        return {
            "connected": self._cell_state == CellState.CONNECTED,
            "cell_id": self._cell_id,
        }

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
    # 内部 VISA 工具方法
    # ===================================================================

    def _write(self, cmd: str) -> None:
        """发送 SCPI 写命令"""
        if not self._visa_session:
            raise ConnectionError("[UXM] Not connected")
        logger.debug(f"[UXM] WRITE: {cmd}")
        self._visa_session.write(cmd)

    def _query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应"""
        if not self._visa_session:
            raise ConnectionError("[UXM] Not connected")
        logger.debug(f"[UXM] QUERY: {cmd}")
        response = self._visa_session.query(cmd)
        logger.debug(f"[UXM] RESP: {response}")
        return response

    def _check_errors(self) -> None:
        """检查并清除错误队列"""
        while True:
            err = self._query(UxmScpiCommands.ERR).strip()
            if err.startswith("0,") or err.startswith("+0,"):
                break
            logger.warning(f"[UXM] Instrument error: {err}")
