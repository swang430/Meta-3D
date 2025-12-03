"""
Signal Analyzer HAL

Provides interface and mock implementation for signal analyzers.
"""

import asyncio
import random
from typing import Dict, Any
from datetime import datetime

from app.hal.base import InstrumentDriver, InstrumentStatus, InstrumentCapability, InstrumentMetrics


class SignalAnalyzerDriver(InstrumentDriver):
    """Abstract interface for Signal Analyzer"""

    async def set_measurement_config(self, config: Dict[str, Any]) -> bool:
        """Configure measurement parameters"""
        raise NotImplementedError

    async def start_measurement(self) -> bool:
        """Start signal measurement"""
        raise NotImplementedError

    async def stop_measurement(self) -> bool:
        """Stop signal measurement"""
        raise NotImplementedError

    async def get_measurement_results(self) -> Dict[str, Any]:
        """Get measurement results"""
        raise NotImplementedError


class MockSignalAnalyzer(SignalAnalyzerDriver):
    """Mock Signal Analyzer for development"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._measuring = False
        self._center_freq_mhz = 3500.0
        self._span_mhz = 200.0

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.3)
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        if self._measuring:
            await self.stop_measurement()
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        if "center_freq_mhz" in config:
            self._center_freq_mhz = config["center_freq_mhz"]
        if "span_mhz" in config:
            self._span_mhz = config["span_mhz"]
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="spectrum_analysis",
                description="Spectrum analyzer mode",
                supported=True,
                parameters={"frequency_range_mhz": [9, 6000]}
            ),
            InstrumentCapability(
                name="power_measurement",
                description="Power measurement",
                supported=True
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        power = -50.0 + random.uniform(-10, 10)
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "measuring": self._measuring,
                "center_freq_mhz": self._center_freq_mhz,
                "span_mhz": self._span_mhz,
                "measured_power_dbm": round(power, 2),
                "occupied_bandwidth_mhz": round(self._span_mhz * 0.8, 2)
            }
        )

    async def reset(self) -> bool:
        if self._measuring:
            await self.stop_measurement()
        self._center_freq_mhz = 3500.0
        self._span_mhz = 200.0
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_measurement_config(self, config: Dict[str, Any]) -> bool:
        return await self.configure(config)

    async def start_measurement(self) -> bool:
        self._set_status(InstrumentStatus.BUSY)
        self._measuring = True
        await asyncio.sleep(0.1)
        return True

    async def stop_measurement(self) -> bool:
        self._measuring = False
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_measurement_results(self) -> Dict[str, Any]:
        return {
            "power_dbm": round(-50.0 + random.uniform(-10, 10), 2),
            "frequency_error_hz": round(random.uniform(-1000, 1000), 2),
            "evm_percent": round(random.uniform(2, 5), 2),
            "timestamp": datetime.utcnow().isoformat()
        }
