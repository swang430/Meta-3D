"""
Signal Analyzer HAL

Provides abstract interface for Spectrum Analyzers / Signal Analyzers.
"""

import asyncio
import logging
import random
from typing import Dict, Any, List
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


class SignalAnalyzerDriver(InstrumentDriver):
    """
    Abstract interface for Signal Analyzers (HAL Layer 2)
    """

    async def setup_spectrum(self, center_freq_hz: float, span_hz: float, rbw_hz: float) -> bool:
        """
        Configure basic spectrum analysis parameters.
        """
        raise NotImplementedError

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        """
        Measure RMS channel power over a specific bandwidth.
        Returns:
            dbm: Power in dBm
        """
        raise NotImplementedError

    async def get_trace(self) -> List[float]:
        """
        Fetch the current Amplitude trace in dBm.
        """
        raise NotImplementedError


class MockSignalAnalyzer(SignalAnalyzerDriver):
    """Fallback Mock implementation"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._center_freq = 1e9

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(name="spectrum", description="Spectrum sweep", supported=True, parameters={})
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={"center_freq": self._center_freq}
        )

    async def reset(self) -> bool:
        self._set_status(InstrumentStatus.READY)
        return True

    async def setup_spectrum(self, center_freq_hz: float, span_hz: float, rbw_hz: float) -> bool:
        self._center_freq = center_freq_hz
        return True

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        await asyncio.sleep(0.2)
        return -50.0 + random.uniform(-1, 1)

    async def get_trace(self) -> List[float]:
        return [random.uniform(-100, -80) for _ in range(500)]
