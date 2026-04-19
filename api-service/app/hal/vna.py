"""
Vector Network Analyzer (VNA) HAL

Provides abstract interface and mock implementation for VNAs.
Primarily used for path loss calibration and S-parameter network measurements.
"""

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime
import numpy as np

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


class VNADriver(InstrumentDriver):
    """
    Abstract interface for Vector Network Analyzers (HAL Layer 2)
    """

    async def setup_sweep(self, start_freq_hz: float, stop_freq_hz: float, points: int) -> bool:
        """
        Configure frequency sweep parameters.
        """
        raise NotImplementedError

    async def measure_s_param(self, measurement: str = "S21") -> bool:
        """
        Setup and initiate an S-parameter measurement (e.g., S11, S21).
        """
        raise NotImplementedError

    async def get_trace_data(self) -> List[complex]:
        """
        Fetch the complex trace data (Real + Imaginary) from the latest sweep.
        """
        raise NotImplementedError


class MockVNA(VNADriver):
    """Fallback Mock implementation"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._start_freq = 1e9
        self._stop_freq = 6e9
        self._points = 201

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
            InstrumentCapability(
                name="s_parameters",
                description="S11, S21, S12, S22",
                supported=True,
                parameters={"max_ports": 2}
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={"start_freq": self._start_freq, "points": self._points}
        )

    async def reset(self) -> bool:
        self._set_status(InstrumentStatus.READY)
        return True

    async def setup_sweep(self, start_freq_hz: float, stop_freq_hz: float, points: int) -> bool:
        self._start_freq = start_freq_hz
        self._stop_freq = stop_freq_hz
        self._points = points
        return True

    async def measure_s_param(self, measurement: str = "S21") -> bool:
        self._set_status(InstrumentStatus.BUSY)
        await asyncio.sleep(0.5)
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_trace_data(self) -> List[complex]:
        # Generate dummy path loss shape (-40dB to -60dB)
        mags = np.linspace(-40, -60, self._points) + np.random.normal(0, 1, self._points)
        phases = np.random.uniform(-np.pi, np.pi, self._points)
        linear_mags = 10 ** (mags / 20)
        complex_data = linear_mags * np.exp(1j * phases)
        return complex_data.tolist()
