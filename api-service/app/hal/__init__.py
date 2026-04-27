"""
Hardware Abstraction Layer (HAL) for Instruments

This package provides abstract interfaces and implementations for instrument drivers.
Supports both mock (development) and real (production) drivers.

三层架构:
  Layer 1 (base.py):      InstrumentDriver 抽象基类 + SCPI 日志
  Layer 2 (*_driver.py):  设备类别抽象接口 (ChannelEmulatorDriver, BaseStationDriver, ...)
  Layer 3 (vendor_*.py):  厂商专用真实驱动 (RealPropsimF64Driver, RealUxmDriver, ...)

使用方式:
  from app.hal import get_registry
  registry = get_registry()
  ce = registry.get_channel_emulator()
  await ce.connect()
"""

# --- Layer 1: 基类 ---
from app.hal.base import InstrumentDriver, InstrumentStatus, InstrumentCapability

# --- Layer 2: 抽象接口 + Mock ---
from app.hal.channel_emulator import ChannelEmulatorDriver, MockChannelEmulator, ChannelLoadMode
from app.hal.base_station import BaseStationDriver, MockBaseStation, RadioTechnology, CellState
from app.hal.signal_analyzer import SignalAnalyzerDriver, MockSignalAnalyzer
from app.hal.vna import VNADriver, MockVNA
from app.hal.positioner import PositionerDriver, MockPositioner
from app.hal.signal_generator import SignalGeneratorDriver, MockSignalGenerator
from app.hal.rf_switch import RfSwitchDriver, MockRfSwitch

# --- Layer 3: 真实驱动 ---
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

# --- 驱动注册表 ---
from app.hal.driver_registry import DriverRegistry, get_registry, reset_registry

__all__ = [
    # Base classes
    'InstrumentDriver',
    'InstrumentStatus',
    'InstrumentCapability',

    # Channel Emulator
    'ChannelEmulatorDriver',
    'ChannelLoadMode',
    'MockChannelEmulator',
    'RealPropsimF64Driver',

    # Base Station Emulator
    'BaseStationDriver',
    'RadioTechnology',
    'CellState',
    'MockBaseStation',
    'RealUxmDriver',
    'RealCmw500Driver',

    # Signal Analyzer
    'SignalAnalyzerDriver',
    'MockSignalAnalyzer',
    'RealRsFswDriver',
    'RealRsFsvaDriver',
    'RealKeysightXSeriesSaDriver',

    # VNA
    'VNADriver',
    'MockVNA',
    'RealKeysightEnaDriver',
    'RealRsZnaDriver',

    # Positioner
    'PositionerDriver',
    'MockPositioner',
    'RealAerotechDriver',
    'RealEtsEmcenterDriver',

    # Signal Generator
    'SignalGeneratorDriver',
    'MockSignalGenerator',
    'RealKeysightMxgDriver',
    'RealRsSmw200aDriver',

    # RF Switch
    'RfSwitchDriver',
    'MockRfSwitch',
    'EtslSwitchDriver',

    # Driver Registry
    'DriverRegistry',
    'get_registry',
    'reset_registry',
]
