"""
Base Station Emulator HAL

Provides interface and mock implementation for base station emulators.
Supports both 5G NR (Keysight UXM) and LTE (R&S CMW500) base station emulators.

应用层统一调用 BaseStationDriver 抽象接口，无需关心底层使用哪种仪器。
"""

import asyncio
import logging
import random
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# 基站仿真器通用枚举
# ===========================================================================

class RadioTechnology(str, Enum):
    """基站支持的无线接入技术"""
    NR5G = "NR5G"
    LTE = "LTE"
    LTE_NR_NSA = "LTE_NR_NSA"  # LTE + NR 非独立组网 (EN-DC)


class CellState(str, Enum):
    """小区状态"""
    OFF = "OFF"          # 小区关闭 (未激活)
    ON = "ON"            # 小区已激活 (射频开启)
    IDLE = "IDLE"        # 等待 UE 接入
    CONNECTED = "CONN"   # UE 已连接 (RRC Connected)
    ERROR = "ERROR"


class ThroughputMetrics:
    """吞吐量测量结果"""
    def __init__(
        self,
        dl_throughput_mbps: float = 0.0,
        ul_throughput_mbps: float = 0.0,
        dl_bler: float = 0.0,
        ul_bler: float = 0.0,
        cqi: int = 0,
        rank_indicator: int = 1,
        mcs_dl: int = 0,
        mcs_ul: int = 0,
    ):
        self.dl_throughput_mbps = dl_throughput_mbps
        self.ul_throughput_mbps = ul_throughput_mbps
        self.dl_bler = dl_bler
        self.ul_bler = ul_bler
        self.cqi = cqi
        self.rank_indicator = rank_indicator
        self.mcs_dl = mcs_dl
        self.mcs_ul = mcs_ul

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dl_throughput_mbps": self.dl_throughput_mbps,
            "ul_throughput_mbps": self.ul_throughput_mbps,
            "dl_bler": self.dl_bler,
            "ul_bler": self.ul_bler,
            "cqi": self.cqi,
            "rank_indicator": self.rank_indicator,
            "mcs_dl": self.mcs_dl,
            "mcs_ul": self.mcs_ul,
        }


class BaseStationDriver(InstrumentDriver):
    """
    Abstract interface for Base Station Emulator (HAL Layer 2)

    定义了所有基站仿真器必须实现的标准化操作原语。
    无论底层是 Keysight UXM (5G NR) 还是 R&S CMW500 (LTE),
    应用层通过此接口统一操作。

    核心原语:
      - set_cell_config():     配置物理小区参数 (频率/带宽/SCS)
      - set_frc_config():      配置固定参考信道 (FRC)
      - set_downlink_power():  调节下行发射功率
      - start_signaling():     开启信令，等待 UE Attach
      - stop_signaling():      停止信令
      - get_throughput_metrics(): 轮询读取 MAC 吞吐量 + BLER + CQI
    """

    # ===================================================================
    # 小区配置
    # ===================================================================

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置物理小区参数。

        Args:
            config: 小区配置字典, 支持以下字段:
                - band: str,          NR 频段 (e.g., "n78")
                - frequency_mhz: float, 中心频率
                - bandwidth_mhz: float, 信道带宽 (e.g., 100)
                - scs_khz: int,       子载波间隔 (15/30/60/120 kHz)
                - duplex: str,        双工模式 ("TDD" / "FDD")
                - mimo_layers: int,   MIMO 层数 (1/2/4)
                - cell_id: int,       物理小区 ID

        Returns:
            True if configuration successful
        """
        raise NotImplementedError

    async def set_frc_config(
        self,
        frc_reference: str,
        modulation: Optional[str] = None,
        target_coding_rate: Optional[float] = None,
    ) -> bool:
        """
        配置固定参考信道 (FRC / Fixed Reference Channel)。

        按 3GPP TS 38.521-4 (NR) 或 TS 36.521 (LTE)
        定义的标准FRC进行配置。

        Args:
            frc_reference: FRC 参考名 (e.g., "G-FR1-A1-1", "R.0")
            modulation: 调制方式 (e.g., "256QAM", "64QAM")
            target_coding_rate: 目标编码率

        Returns:
            True if FRC configured successfully
        """
        raise NotImplementedError

    async def set_downlink_power(self, power_dbm: float) -> bool:
        """
        设置下行发射功率。

        Args:
            power_dbm: 下行功率 (dBm), 典型范围 -120 ~ 0

        Returns:
            True if power set successfully
        """
        raise NotImplementedError

    # ===================================================================
    # 信令控制
    # ===================================================================

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        """
        开启物理小区信令, 激活小区并等待 UE Attach。

        等效于 "Cell ON" + 等待 RRC Connection + Attach Complete。

        Args:
            timeout_s: 等待 UE Attach 的超时时间 (秒)

        Returns:
            True if UE successfully attached within timeout
        """
        raise NotImplementedError

    async def stop_signaling(self) -> bool:
        """
        停止物理小区信令, 断开 UE 连接并关闭小区。

        Returns:
            True if signaling stopped successfully
        """
        raise NotImplementedError

    async def start_cell(self) -> bool:
        """Start base station transmission (alias for start_signaling)"""
        return await self.start_signaling()

    async def stop_cell(self) -> bool:
        """Stop base station transmission (alias for stop_signaling)"""
        return await self.stop_signaling()

    async def get_cell_state(self) -> CellState:
        """获取小区当前状态"""
        raise NotImplementedError

    # ===================================================================
    # 测量
    # ===================================================================

    async def get_throughput_metrics(self) -> ThroughputMetrics:
        """
        轮询读取 MAC 层吞吐量指标。

        返回当前的 DL/UL 吞吐量, BLER, CQI, Rank Indicator, MCS。
        建议采样间隔: 200ms。

        Returns:
            ThroughputMetrics 数据对象
        """
        raise NotImplementedError

    async def get_ue_info(self) -> Dict[str, Any]:
        """
        获取已连接 UE 的信息。

        Returns:
            UE 信息字典 (IMSI, IMEI, capabilities, etc.)
        """
        raise NotImplementedError

    # ===================================================================
    # 能力查询
    # ===================================================================

    def get_supported_technologies(self) -> List[RadioTechnology]:
        """
        声明该基站仿真器支持的无线接入技术。

        Returns:
            支持的 RadioTechnology 列表
        """
        return [RadioTechnology.LTE]  # 默认支持 LTE


# ===========================================================================
# Mock 实现 (开发/测试用)
# ===========================================================================

class MockBaseStation(BaseStationDriver):
    """Mock Base Station Emulator for development"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._cell_running = False
        self._cell_state = CellState.OFF
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._scs_khz = 30
        self._dl_power_dbm = -50.0
        self._mimo_layers = 2
        self._frc = ""

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.3)
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        if self._cell_running:
            await self.stop_signaling()
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        return await self.set_cell_config(config)

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="5g_nr",
                description="5G NR support",
                supported=True,
                parameters={
                    "frequency_range": [450, 6000],
                    "max_bandwidth_mhz": 100,
                },
            ),
            InstrumentCapability(
                name="lte",
                description="LTE support",
                supported=True,
                parameters={
                    "frequency_range": [450, 3800],
                    "max_bandwidth_mhz": 20,
                },
            ),
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        tx_power = self._dl_power_dbm + random.uniform(-0.5, 0.5)
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "cell_running": self._cell_running,
                "cell_state": self._cell_state.value,
                "frequency_mhz": self._frequency_mhz,
                "bandwidth_mhz": self._bandwidth_mhz,
                "scs_khz": self._scs_khz,
                "tx_power_dbm": round(tx_power, 2),
                "mimo_layers": self._mimo_layers,
                "connected_ues": (
                    random.randint(0, 1) if self._cell_running else 0
                ),
            },
        )

    async def reset(self) -> bool:
        if self._cell_running:
            await self.stop_signaling()
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._scs_khz = 30
        self._dl_power_dbm = -50.0
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        if "frequency_mhz" in config:
            self._frequency_mhz = config["frequency_mhz"]
        if "bandwidth_mhz" in config:
            self._bandwidth_mhz = config["bandwidth_mhz"]
        if "scs_khz" in config:
            self._scs_khz = config["scs_khz"]
        if "mimo_layers" in config:
            self._mimo_layers = config["mimo_layers"]
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_frc_config(
        self, frc_reference: str, modulation=None, target_coding_rate=None
    ) -> bool:
        self._frc = frc_reference
        return True

    async def set_downlink_power(self, power_dbm: float) -> bool:
        if power_dbm < -120 or power_dbm > 0:
            return False
        self._dl_power_dbm = power_dbm
        return True

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        self._set_status(InstrumentStatus.BUSY)
        self._cell_running = True
        self._cell_state = CellState.CONNECTED
        await asyncio.sleep(0.2)
        return True

    async def stop_signaling(self) -> bool:
        self._cell_running = False
        self._cell_state = CellState.OFF
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_cell_state(self) -> CellState:
        return self._cell_state

    async def get_throughput_metrics(self) -> ThroughputMetrics:
        if not self._cell_running:
            return ThroughputMetrics()
        return ThroughputMetrics(
            dl_throughput_mbps=420.0 + random.gauss(0, 15),
            ul_throughput_mbps=80.0 + random.gauss(0, 5),
            dl_bler=random.uniform(0, 0.05),
            ul_bler=random.uniform(0, 0.08),
            cqi=random.randint(12, 15),
            rank_indicator=min(self._mimo_layers, random.randint(1, 2)),
            mcs_dl=random.randint(24, 27),
            mcs_ul=random.randint(20, 24),
        )

    async def get_ue_info(self) -> Dict[str, Any]:
        return {
            "imsi": "001010000000001",
            "imei": "352099001761481",
            "ue_category": "NR-DC",
            "connected": self._cell_running,
        }

    def get_supported_technologies(self) -> List[RadioTechnology]:
        return [RadioTechnology.NR5G, RadioTechnology.LTE]
