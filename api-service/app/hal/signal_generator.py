"""
Signal Generator HAL

Provides abstract interface for standard/vector signal generators.
"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


class SignalGeneratorDriver(InstrumentDriver):
    """
    Abstract interface for Vector/Analog Signal Generators (HAL Layer 2)
    """

    async def set_cw(self, frequency_hz: float, power_dbm: float) -> bool:
        """
        Configure CW (Continuous Wave) output.
        """
        raise NotImplementedError

    async def load_iq_waveform(self, waveform_name: str) -> bool:
        """
        Load an arbitrary waveform (ARB) for playback.
        """
        raise NotImplementedError

    async def start_tx(self) -> bool:
        """
        Turn RF output ON.
        """
        raise NotImplementedError

    async def stop_tx(self) -> bool:
        """
        Turn RF output OFF.
        """
        raise NotImplementedError


class MockSignalGenerator(SignalGeneratorDriver):
    """Fallback Mock implementation"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._freq_hz = 1e9
        self._power_dbm = -50.0
        self._rf_on = False

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
            InstrumentCapability(name="cw", description="Continuous Wave", supported=True, parameters={}),
            InstrumentCapability(name="arb", description="ARB Playback", supported=True, parameters={})
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={"rf_on": self._rf_on, "frequency_hz": self._freq_hz, "power_dbm": self._power_dbm}
        )

    async def reset(self) -> bool:
        await self.stop_tx()
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_cw(self, frequency_hz: float, power_dbm: float) -> bool:
        self._freq_hz = frequency_hz
        self._power_dbm = power_dbm
        return True

    async def load_iq_waveform(self, waveform_name: str) -> bool:
        return True

    async def start_tx(self) -> bool:
        self._rf_on = True
        return True

    async def stop_tx(self) -> bool:
        self._rf_on = False
        return True
