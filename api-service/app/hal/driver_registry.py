"""
HAL Driver Registry (驱动注册与工厂)

根据运行环境和仪器配置自动选择 Mock 或 Real 驱动实例。

架构:
    DriverRegistry 是系统唯一的仪器驱动入口点。
    上层服务通过 registry.get_driver("channel_emulator") 获取驱动,
    而不需要关心底层使用的是 MockChannelEmulator 还是 RealPropsimF64Driver。

    驱动选择策略:
    1. 若 instrument_config 指定了 driver_class → 使用指定的驱动类
    2. 若系统环境变量 HAL_MODE=mock → 全部使用 Mock
    3. 若能通过 PyVISA 探测到仪器 → 使用 Real 驱动
    4. 回退到 Mock 驱动

使用示例:
    registry = DriverRegistry()
    registry.register_from_config({
        "channel_emulator": {
            "driver_class": "RealPropsimF64Driver",
            "ip": "192.168.100.21",
            "port": 3334,  # PROPSIM F64 ATE/SCPI 端口硬件固定 3334 (非 5025)
        },
        "base_station": {
            "driver_class": "auto",  # 自动探测
            "ip": "192.168.100.10",
        },
    })

    ce = registry.get_driver("channel_emulator")
    await ce.connect()
"""

import logging
import os
from typing import Dict, Any, Optional, Type

from app.hal.base import InstrumentDriver, InstrumentStatus

# --- Mock 驱动 ---
from app.hal.channel_emulator import (
    ChannelEmulatorDriver, MockChannelEmulator
)
from app.hal.base_station import BaseStationDriver, MockBaseStation
from app.hal.vna import VNADriver, MockVNA
from app.hal.positioner import PositionerDriver, MockPositioner
from app.hal.signal_analyzer import SignalAnalyzerDriver, MockSignalAnalyzer
from app.hal.signal_generator import SignalGeneratorDriver, MockSignalGenerator
from app.hal.rf_switch import RfSwitchDriver, MockRfSwitch

# --- Real 驱动 ---
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.aerotech_positioner import RealAerotechDriver
from app.hal.ets_positioner import RealEtsEmcenterDriver
from app.hal.rf_switch import EtslSwitchDriver
from app.hal.keysight_ena import RealKeysightEnaDriver
from app.hal.rs_zna import RealRsZnaDriver
from app.hal.keysight_mxg import RealKeysightMxgDriver
from app.hal.rs_smw200a import RealRsSmw200aDriver
from app.hal.rs_fsw import RealRsFswDriver
from app.hal.rs_fsva import RealRsFsvaDriver
from app.hal.keysight_x_series_sa import RealKeysightXSeriesSaDriver

logger = logging.getLogger(__name__)


# ===========================================================================
# 驱动类名 → Python 类 映射表
# ===========================================================================

DRIVER_CLASS_MAP: Dict[str, Type[InstrumentDriver]] = {
    # Channel Emulators
    "MockChannelEmulator": MockChannelEmulator,
    "RealPropsimF64Driver": RealPropsimF64Driver,

    # Base Stations
    "MockBaseStation": MockBaseStation,
    "RealUxmDriver": RealUxmDriver,
    "RealCmw500Driver": RealCmw500Driver,

    # Positioners
    "MockPositioner": MockPositioner,
    "RealAerotechDriver": RealAerotechDriver,
    "RealEtsEmcenterDriver": RealEtsEmcenterDriver,

    # RF Switches
    "MockRfSwitch": MockRfSwitch,
    "EtslSwitchDriver": EtslSwitchDriver,

    # VNA
    "MockVNA": MockVNA,
    "RealKeysightEnaDriver": RealKeysightEnaDriver,
    "RealRsZnaDriver": RealRsZnaDriver,

    # Signal Generators
    "MockSignalGenerator": MockSignalGenerator,
    "RealKeysightMxgDriver": RealKeysightMxgDriver,
    "RealRsSmw200aDriver": RealRsSmw200aDriver,

    # Signal Analyzers
    "MockSignalAnalyzer": MockSignalAnalyzer,
    "RealRsFswDriver": RealRsFswDriver,
    "RealRsFsvaDriver": RealRsFsvaDriver,
    "RealKeysightXSeriesSaDriver": RealKeysightXSeriesSaDriver,
}


# 设备类别 → 默认 Mock 驱动类
DEFAULT_MOCK_MAP: Dict[str, Type[InstrumentDriver]] = {
    "channel_emulator": MockChannelEmulator,
    "base_station": MockBaseStation,
    "positioner": MockPositioner,
    "rf_switch": MockRfSwitch,
    "vna": MockVNA,
    "signal_generator": MockSignalGenerator,
    "signal_analyzer": MockSignalAnalyzer,
}

# 设备类别 → 优先级排序的 Real 驱动 (第一个能连接的就用)
DEFAULT_REAL_MAP: Dict[str, list] = {
    "channel_emulator": [RealPropsimF64Driver],
    "base_station": [RealUxmDriver, RealCmw500Driver],
    "positioner": [RealAerotechDriver, RealEtsEmcenterDriver],
    "rf_switch": [EtslSwitchDriver],
    "vna": [RealKeysightEnaDriver, RealRsZnaDriver],
    "signal_generator": [RealKeysightMxgDriver, RealRsSmw200aDriver],
    "signal_analyzer": [RealRsFswDriver, RealRsFsvaDriver, RealKeysightXSeriesSaDriver],
}


class DriverRegistry:
    """
    HAL 驱动注册表 — 单例工厂

    职责:
    1. 根据配置文件 / 环境变量选择驱动类 (Mock or Real)
    2. 维护已实例化的驱动缓存 (避免重复创建)
    3. 提供批量连接 / 断开 / 健康检查接口
    """

    def __init__(self):
        self._drivers: Dict[str, InstrumentDriver] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._hal_mode: str = os.environ.get("HAL_MODE", "auto").lower()

    @property
    def mode(self) -> str:
        """当前 HAL 模式: 'mock', 'real', 'auto'"""
        return self._hal_mode

    def set_mode(self, mode: str) -> None:
        """设置 HAL 模式 (影响后续 register 调用)"""
        self._hal_mode = mode.lower()
        logger.info(f"[HAL Registry] Mode set to: {self._hal_mode}")

    # ===================================================================
    # 驱动注册
    # ===================================================================

    def register(
        self,
        category: str,
        instrument_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        force_mock: bool = False,
    ) -> InstrumentDriver:
        """
        注册并实例化一个设备驱动。

        Args:
            category: 设备类别 (e.g., "channel_emulator", "base_station")
            instrument_id: 仪器唯一标识符 (默认=category)
            config: 仪器配置 (ip, port, driver_class, etc.)
            force_mock: 强制使用 Mock 驱动

        Returns:
            实例化的 InstrumentDriver
        """
        if config is None:
            config = {}
        if instrument_id is None:
            instrument_id = category

        # 已注册的直接返回
        if instrument_id in self._drivers:
            return self._drivers[instrument_id]

        driver_class = self._resolve_driver_class(
            category, config, force_mock
        )
        driver = driver_class(instrument_id, config)

        self._drivers[instrument_id] = driver
        self._configs[instrument_id] = config
        logger.info(
            f"[HAL Registry] Registered {instrument_id} → "
            f"{driver_class.__name__} (mode={self._hal_mode})"
        )
        return driver

    def register_from_config(
        self,
        instruments_config: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        从配置字典批量注册所有仪器。

        Args:
            instruments_config: {
                "channel_emulator": {"driver_class": "RealPropsimF64Driver", "ip": "192.168.100.21"},
                "base_station": {"driver_class": "auto", "ip": "192.168.100.10"},
                ...
            }
        """
        for category, config in instruments_config.items():
            instrument_id = config.pop("instrument_id", category)
            self.register(category, instrument_id, config)

    # ===================================================================
    # 驱动获取
    # ===================================================================

    def get_driver(
        self,
        instrument_id: str,
        fallback_category: Optional[str] = None,
    ) -> Optional[InstrumentDriver]:
        """
        获取已注册的驱动实例。

        若未注册且 fallback_category 不为空，则自动注册 Mock 驱动。

        Args:
            instrument_id: 仪器标识符
            fallback_category: 若未注册时的回退类别 (自动注册 Mock)

        Returns:
            InstrumentDriver 实例, 或 None
        """
        driver = self._drivers.get(instrument_id)
        if driver is None and fallback_category:
            logger.warning(
                f"[HAL Registry] '{instrument_id}' not registered, "
                f"auto-registering Mock for category '{fallback_category}'"
            )
            driver = self.register(
                fallback_category,
                instrument_id,
                {},
                force_mock=True,
            )
        return driver

    def get_channel_emulator(self) -> ChannelEmulatorDriver:
        """获取信道仿真器驱动 (类型安全快捷方法)"""
        return self.get_driver("channel_emulator", "channel_emulator")

    def get_base_station(self) -> BaseStationDriver:
        """获取综测仪驱动"""
        return self.get_driver("base_station", "base_station")

    def get_positioner(self) -> PositionerDriver:
        """获取转台驱动"""
        return self.get_driver("positioner", "positioner")

    def get_vna(self) -> VNADriver:
        """获取 VNA 驱动"""
        return self.get_driver("vna", "vna")

    def get_rf_switch(self) -> RfSwitchDriver:
        """获取 RF 开关驱动"""
        return self.get_driver("rf_switch", "rf_switch")

    # ===================================================================
    # 生命周期管理
    # ===================================================================

    async def connect_all(self) -> Dict[str, bool]:
        """连接所有已注册的仪器"""
        results = {}
        for iid, driver in self._drivers.items():
            try:
                ok = await driver.connect()
                results[iid] = ok
                if ok:
                    logger.info(f"[HAL Registry] {iid} connected ✓")
                else:
                    logger.warning(f"[HAL Registry] {iid} connect failed")
            except Exception as e:
                results[iid] = False
                logger.error(f"[HAL Registry] {iid} connect error: {e}")
        return results

    async def disconnect_all(self) -> Dict[str, bool]:
        """断开所有仪器"""
        results = {}
        for iid, driver in self._drivers.items():
            try:
                ok = await driver.disconnect()
                results[iid] = ok
            except Exception as e:
                results[iid] = False
                logger.error(f"[HAL Registry] {iid} disconnect error: {e}")
        return results

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """所有仪器健康检查"""
        results = {}
        for iid, driver in self._drivers.items():
            results[iid] = await driver.health_check()
        return results

    def list_drivers(self) -> Dict[str, Dict[str, Any]]:
        """列出所有已注册驱动的状态"""
        return {
            iid: {
                "class": type(driver).__name__,
                "status": driver.status.value,
                "is_mock": "Mock" in type(driver).__name__,
                "config_keys": list(self._configs.get(iid, {}).keys()),
            }
            for iid, driver in self._drivers.items()
        }

    # ===================================================================
    # 内部方法
    # ===================================================================

    def _resolve_driver_class(
        self,
        category: str,
        config: Dict[str, Any],
        force_mock: bool,
    ) -> Type[InstrumentDriver]:
        """
        解析驱动类。

        优先级:
        1. force_mock=True → Mock
        2. config["driver_class"] 显式指定 → 查表
        3. HAL_MODE=mock → Mock
        4. HAL_MODE=real → Real (第一个)
        5. HAL_MODE=auto → 尝试 Real，失败则 Mock
        """
        # 强制 Mock
        if force_mock or self._hal_mode == "mock":
            return DEFAULT_MOCK_MAP.get(category, MockChannelEmulator)

        # 显式指定驱动类名
        driver_class_name = config.get("driver_class")
        if driver_class_name and driver_class_name != "auto":
            cls = DRIVER_CLASS_MAP.get(driver_class_name)
            if cls:
                return cls
            logger.warning(
                f"[HAL Registry] Unknown driver_class '{driver_class_name}', "
                f"falling back to Mock"
            )
            return DEFAULT_MOCK_MAP.get(category, MockChannelEmulator)

        # Real 模式
        if self._hal_mode == "real":
            real_options = DEFAULT_REAL_MAP.get(category, [])
            if real_options:
                return real_options[0]
            return DEFAULT_MOCK_MAP.get(category, MockChannelEmulator)

        # Auto 模式: 有 IP 配置则使用 Real，否则 Mock
        if config.get("ip"):
            real_options = DEFAULT_REAL_MAP.get(category, [])
            if real_options:
                return real_options[0]

        return DEFAULT_MOCK_MAP.get(category, MockChannelEmulator)


# ===========================================================================
# 全局单例
# ===========================================================================

_global_registry: Optional[DriverRegistry] = None


def get_registry() -> DriverRegistry:
    """获取全局 HAL 驱动注册表 (惰性单例)"""
    global _global_registry
    if _global_registry is None:
        _global_registry = DriverRegistry()
    return _global_registry


def reset_registry() -> None:
    """重置全局注册表 (用于测试)"""
    global _global_registry
    _global_registry = None
"""

"""
