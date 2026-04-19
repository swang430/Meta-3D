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
    PRESET = "SYSTem:PRESet"

    # --- RF 路由 ---
    # 信令模式单小区, 使用内部 RF 前端
    ROUTE_SIGN = "ROUTe:LTE:SIGN{i}:SCENario:SCELl:FLEXible"
    ROUTE_SIGN_CAFF = "ROUTe:LTE:SIGN{i}:SCENario:CAFF:FLEXible:INTernal"

    # --- 小区配置 (CONFigure:LTE:SIGN) ---
    CELL_BAND = "CONFigure:LTE:SIGN{i}:CELL:BAND"              # e.g., "OB78"
    CELL_DL_FREQ = "CONFigure:LTE:SIGN{i}:RFSettings:CHANnel:DL"  # EARFCN
    CELL_DL_BW = "CONFigure:LTE:SIGN{i}:CELL:BANDwidth:DL"     # 带宽 (MHz)
    CELL_UL_BW = "CONFigure:LTE:SIGN{i}:CELL:BANDwidth:UL"
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
    PS_ACTION = "CALL:LTE:SIGN{i}:PSWitched:ACTion"           # ETABlish/RELease
    PS_STATE = "FETCh:LTE:SIGN{i}:PSWitched:STATe?"

    # RRC 状态
    RRC_STATE = "SENSe:LTE:SIGN{i}:RRCState?"

    # --- 吞吐量测量 (SENSe 子系统) ---
    ETPUT_DL_ALL = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:DL:ALL?"
    ETPUT_DL_PCC = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:DL:PCC?"
    ETPUT_UL_ALL = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:UL:ALL?"
    ETPUT_UL_PCC = "SENSe:LTE:SIGN{i}:CONNection:ETHRoughput:UL:PCC?"

    # --- BLER 测量 (FETCh 子系统) ---
    EBLER_PCC = "FETCh:LTE:SIGN{i}:EBLer:PCC:ABSolute?"
    EBLER_CQI = "FETCh:LTE:SIGN{i}:EBLer:PCC:CQIReporting:STReam1?"

    # --- 信令 BLER (Extended BLER) ---
    INIT_EBLER = "INITiate:LTE:SIGN{i}:EBLer"
    EBLER_REPS = "CONFigure:LTE:SIGN{i}:EBLer:REPetition"
    EBLER_STAT = "FETCh:LTE:SIGN{i}:EBLer:PCC:ABSolute?"

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
      1. connect() → *IDN? → PRESET
      2. ROUTe → 配置 RF 路由场景
      3. set_cell_config() → Band/BW/DL Freq
      4. set_downlink_power() → RS-EPRE 功率
      5. start_signaling() → Cell ON → PS Establish → 等待连接
      6. get_throughput_metrics() → ETHRoughput + EBLer
      7. stop_signaling() → PS Release → Cell OFF
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        # 连接参数
        self.ip_address: str = config.get("ip", "192.168.100.20")
        self.port: int = config.get("port", 5025)
        self.visa_resource: Optional[str] = config.get("visa_resource")
        # VISA session
        self._visa_rm = None
        self._visa_session = None
        # CMW 信令通道编号 (默认 1)
        self._sign_channel: int = config.get("sign_channel", 1)
        # 小区配置状态
        self._band: str = "OB3"
        self._earfcn: int = 1575
        self._frequency_mhz: float = 1842.5
        self._bandwidth_mhz: float = 20.0
        self._dl_power_dbm: float = -50.0
        self._cell_state: CellState = CellState.OFF

    @property
    def _i(self) -> str:
        """格式化的信令通道编号"""
        return str(self._sign_channel)

    def _fmt(self, template: str) -> str:
        """将命令模板中的 {i} 替换为通道编号"""
        return template.format(i=self._i)

    # ===================================================================
    # 1. 连接生命周期
    # ===================================================================

    async def connect(self) -> bool:
        """通过 PyVISA 建立与 CMW500 的连接"""
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

            # 验证身份
            idn = self._query("*IDN?").strip()
            logger.info(f"[CMW500] Connected: {idn}")

            if "CMW" not in idn.upper():
                logger.warning(
                    f"[CMW500] Unexpected IDN response: {idn}"
                )

            # 清除状态 + 预设
            self._write("*CLS")
            self._write(CmwScpiCommands.PRESET)
            self._query("*OPC?")

            # 配置 RF 路由 (信令模式单小区)
            self._write(self._fmt(CmwScpiCommands.ROUTE_SIGN))
            self._query("*OPC?")

            self._set_status(InstrumentStatus.CONNECTED)
            self._clear_error()
            return True

        except Exception as e:
            error_msg = f"[CMW500] Connection failed: {e}"
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
          CONFigure:LTE:SIGN1:CELL:BAND OB3
          CONFigure:LTE:SIGN1:CELL:BANDwidth:DL B20
          CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL 1575
          CONFigure:LTE:SIGN1:CELL:DMOD FDD
        """
        try:
            # 频段
            if "band" in config:
                band = config["band"].upper()
                # CMW 使用 "OB" 前缀 (Operating Band)
                if not band.startswith("OB"):
                    band = f"OB{band}"
                self._band = band
                self._write(
                    self._fmt(CmwScpiCommands.CELL_BAND) + f" {band}"
                )

            # 带宽 (CMW 格式: B5, B10, B15, B20)
            if "bandwidth_mhz" in config:
                bw = int(config["bandwidth_mhz"])
                self._bandwidth_mhz = float(bw)
                bw_str = f"B{bw}"
                self._write(
                    self._fmt(CmwScpiCommands.CELL_DL_BW) + f" {bw_str}"
                )
                self._write(
                    self._fmt(CmwScpiCommands.CELL_UL_BW) + f" {bw_str}"
                )

            # 双工模式
            if "duplex" in config:
                self._write(
                    self._fmt(CmwScpiCommands.CELL_DUPLEX)
                    + f" {config['duplex'].upper()}"
                )

            # EARFCN (DL 频点)
            if "earfcn" in config:
                self._earfcn = config["earfcn"]
            elif "arfcn" in config:
                self._earfcn = config["arfcn"]
            else:
                self._earfcn = LTE_BAND_EARFCN_MAP.get(
                    self._band, 1575
                )
            self._write(
                self._fmt(CmwScpiCommands.CELL_DL_FREQ)
                + f" {self._earfcn}"
            )

            # 频率 (如果直接指定)
            if "frequency_mhz" in config:
                self._frequency_mhz = config["frequency_mhz"]

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

            self._query("*OPC?")
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

            self._query("*OPC?")
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
            self._write(
                self._fmt(CmwScpiCommands.DL_POWER_RS)
                + f" {power_dbm:.1f}"
            )
            self._dl_power_dbm = power_dbm
            self._query("*OPC?")
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

        SCPI 序列:
          SOURce:LTE:SIGN1:CELL:STATe ON → *OPC?
          → 轮询 FETCh:LTE:SIGN1:PSWitched:STATe?
          → 等待 "ATT" (Attached)
          → CALL:LTE:SIGN1:PSWitched:ACTion ETABlish
        """
        try:
            logger.info("[CMW500] Starting LTE signaling")
            self._set_status(InstrumentStatus.BUSY)

            old_timeout = self._visa_session.timeout
            self._visa_session.timeout = VISA_TIMEOUT_CELL

            # 激活小区
            self._write(self._fmt(CmwScpiCommands.CELL_STATE_SET) + " ON")
            self._query("*OPC?")
            self._cell_state = CellState.ON
            logger.info("[CMW500] Cell ON, waiting for UE attach...")

            # 等待 UE Attach
            self._visa_session.timeout = VISA_TIMEOUT_ATTACH
            elapsed = 0.0
            poll_interval = 3.0
            attached = False

            while elapsed < timeout_s:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    # 查询 PS 连接状态
                    ps_state = self._query(
                        self._fmt(CmwScpiCommands.PS_STATE)
                    ).strip().upper()

                    # CMW 返回: "OFF" / "ATT" / "REG" / "CONN"
                    if "ATT" in ps_state or "REG" in ps_state:
                        attached = True
                        logger.info(
                            f"[CMW500] UE attached after {elapsed:.1f}s"
                        )
                        break
                except Exception:
                    pass  # UE 可能还在搜网

            if attached:
                # 建立 PS 数据连接
                self._write(
                    self._fmt(CmwScpiCommands.PS_ACTION) + " ETABlish"
                )
                await asyncio.sleep(3.0)

                # 验证 PS 连接
                ps_state = self._query(
                    self._fmt(CmwScpiCommands.PS_STATE)
                ).strip().upper()
                if "CONN" in ps_state or "ATT" in ps_state:
                    self._cell_state = CellState.CONNECTED
                    logger.info("[CMW500] PS connection established")
                else:
                    self._cell_state = CellState.IDLE
                    logger.warning(
                        f"[CMW500] PS state after establish: {ps_state}"
                    )
            else:
                logger.warning(
                    f"[CMW500] UE attach timeout after {timeout_s}s"
                )
                self._cell_state = CellState.IDLE

            # 恢复默认超时
            self._visa_session.timeout = old_timeout

            return self._cell_state == CellState.CONNECTED

        except Exception as e:
            logger.error(f"[CMW500] start_signaling failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def stop_signaling(self) -> bool:
        """
        释放 PS 连接并关闭小区。

        SCPI:
          CALL:LTE:SIGN1:PSWitched:ACTion RELease
          SOURce:LTE:SIGN1:CELL:STATe OFF
        """
        try:
            # 先释放 PS 连接
            if self._cell_state == CellState.CONNECTED:
                self._write(
                    self._fmt(CmwScpiCommands.PS_ACTION) + " RELease"
                )
                await asyncio.sleep(2.0)

            # 关闭小区
            self._write(self._fmt(CmwScpiCommands.CELL_STATE_SET) + " OFF")
            self._query("*OPC?")
            self._cell_state = CellState.OFF
            self._set_status(InstrumentStatus.READY)
            logger.info("[CMW500] Signaling stopped")
            return True
        except Exception as e:
            logger.error(f"[CMW500] stop_signaling failed: {e}")
            return False

    async def get_cell_state(self) -> CellState:
        """查询小区当前状态"""
        try:
            state = self._query(
                self._fmt(CmwScpiCommands.CELL_STATE_QUERY)
            ).strip().upper()
            if "OFF" in state:
                return CellState.OFF
            elif "ON" in state:
                # 检查 PS 状态
                ps = self._query(
                    self._fmt(CmwScpiCommands.PS_STATE)
                ).strip().upper()
                if "CONN" in ps or "ATT" in ps:
                    return CellState.CONNECTED
                return CellState.IDLE
            return CellState.ERROR
        except Exception:
            return CellState.ERROR

    # ===================================================================
    # 4. 吞吐量与 BLER 测量
    # ===================================================================

    async def get_throughput_metrics(self) -> ThroughputMetrics:
        """
        轮询读取 MAC 层吞吐量指标。

        SCPI:
          SENSe:LTE:SIGN1:CONNection:ETHRoughput:DL:PCC?
          SENSe:LTE:SIGN1:CONNection:ETHRoughput:UL:PCC?
          FETCh:LTE:SIGN1:EBLer:PCC:ABSolute?
          FETCh:LTE:SIGN1:EBLer:PCC:CQIReporting:STReam1?

        ETHRoughput 返回格式 (逗号分隔):
          <current_tput_kbps>, <average_tput_kbps>, <max_tput_kbps>
        """
        metrics = ThroughputMetrics()

        try:
            # DL 吞吐量 (SENSe)
            dl_str = self._query(
                self._fmt(CmwScpiCommands.ETPUT_DL_PCC)
            )
            if dl_str:
                parts = dl_str.strip().split(",")
                if len(parts) >= 2:
                    try:
                        # 第二个值: average throughput (kbps)
                        dl_kbps = float(parts[1])
                        metrics.dl_throughput_mbps = dl_kbps / 1000.0
                    except ValueError:
                        pass

            # UL 吞吐量
            ul_str = self._query(
                self._fmt(CmwScpiCommands.ETPUT_UL_PCC)
            )
            if ul_str:
                parts = ul_str.strip().split(",")
                if len(parts) >= 2:
                    try:
                        ul_kbps = float(parts[1])
                        metrics.ul_throughput_mbps = ul_kbps / 1000.0
                    except ValueError:
                        pass

            # BLER
            bler_str = self._query(
                self._fmt(CmwScpiCommands.EBLER_PCC)
            )
            if bler_str:
                try:
                    metrics.dl_bler = float(bler_str.strip().split(",")[0])
                except (ValueError, IndexError):
                    pass

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
                    "max_bandwidth_mhz": 20,
                    "max_mimo_layers": 4,
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
    # 内部 VISA 工具方法
    # ===================================================================

    def _write(self, cmd: str) -> None:
        """发送 SCPI 写命令"""
        if not self._visa_session:
            raise ConnectionError("[CMW500] Not connected")
        logger.debug(f"[CMW500] WRITE: {cmd}")
        self._visa_session.write(cmd)

    def _query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应"""
        if not self._visa_session:
            raise ConnectionError("[CMW500] Not connected")
        logger.debug(f"[CMW500] QUERY: {cmd}")
        response = self._visa_session.query(cmd)
        logger.debug(f"[CMW500] RESP: {response}")
        return response

    def _check_errors(self) -> None:
        """检查并清除错误队列"""
        while True:
            err = self._query(CmwScpiCommands.ERR).strip()
            if err.startswith("0,") or err.startswith("+0,"):
                break
            logger.warning(f"[CMW500] Instrument error: {err}")
