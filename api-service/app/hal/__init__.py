"""
Hardware Abstraction Layer (HAL) for Instruments

This package provides abstract interfaces and implementations for instrument drivers.
Supports both mock (development) and real (production) drivers.
"""

from app.hal.base import InstrumentDriver, InstrumentStatus, InstrumentCapability
from app.hal.channel_emulator import ChannelEmulatorDriver, MockChannelEmulator
from app.hal.base_station import BaseStationDriver, MockBaseStation
from app.hal.signal_analyzer import SignalAnalyzerDriver, MockSignalAnalyzer

__all__ = [
    # Base classes
    'InstrumentDriver',
    'InstrumentStatus',
    'InstrumentCapability',

    # Channel Emulator
    'ChannelEmulatorDriver',
    'MockChannelEmulator',

    # Base Station Emulator
    'BaseStationDriver',
    'MockBaseStation',

    # Signal Analyzer
    'SignalAnalyzerDriver',
    'MockSignalAnalyzer',
]
