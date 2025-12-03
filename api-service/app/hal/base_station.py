"""
Base Station Emulator HAL

Provides interface and mock implementation for base station emulators.
"""

import asyncio
import random
from typing import Dict, Any
from datetime import datetime

from app.hal.base import InstrumentDriver, InstrumentStatus, InstrumentCapability, InstrumentMetrics


class BaseStationDriver(InstrumentDriver):
    """Abstract interface for Base Station Emulator"""

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """Configure cell parameters (frequency, bandwidth, etc.)"""
        raise NotImplementedError

    async def start_cell(self) -> bool:
        """Start base station transmission"""
        raise NotImplementedError

    async def stop_cell(self) -> bool:
        """Stop base station transmission"""
        raise NotImplementedError


class MockBaseStation(BaseStationDriver):
    """Mock Base Station Emulator for development"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._cell_running = False
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.3)
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        if self._cell_running:
            await self.stop_cell()
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        if "frequency_mhz" in config:
            self._frequency_mhz = config["frequency_mhz"]
        if "bandwidth_mhz" in config:
            self._bandwidth_mhz = config["bandwidth_mhz"]
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="5g_nr",
                description="5G NR support",
                supported=True,
                parameters={"frequency_range": [450, 6000], "max_bandwidth_mhz": 100}
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        tx_power = 43.0 + random.uniform(-2, 2)
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "cell_running": self._cell_running,
                "frequency_mhz": self._frequency_mhz,
                "bandwidth_mhz": self._bandwidth_mhz,
                "tx_power_dbm": round(tx_power, 2),
                "connected_ues": random.randint(0, 5) if self._cell_running else 0
            }
        )

    async def reset(self) -> bool:
        if self._cell_running:
            await self.stop_cell()
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        return await self.configure(config)

    async def start_cell(self) -> bool:
        self._set_status(InstrumentStatus.BUSY)
        self._cell_running = True
        await asyncio.sleep(0.2)
        return True

    async def stop_cell(self) -> bool:
        self._cell_running = False
        self._set_status(InstrumentStatus.READY)
        return True
