"""
Positioner (Turntable) HAL definitions
"""
from abc import abstractmethod
from typing import Dict, Any, Tuple
import asyncio
import logging

from app.hal.base import InstrumentDriver

logger = logging.getLogger(__name__)


class PositionerDriver(InstrumentDriver):
    """
    Abstract base class for Positioner (Turntable/Mast) drivers.
    """

    @abstractmethod
    async def move_to_azimuth(self, angle_deg: float) -> None:
        """Move turntable to specified azimuth angle."""
        pass

    @abstractmethod
    async def get_current_azimuth(self) -> float:
        """Get current azimuth angle."""
        pass

    @abstractmethod
    async def wait_until_settled(self, timeout_s: float = 30.0) -> bool:
        """Wait until turntable stops moving."""
        pass


class MockPositioner(PositionerDriver):
    """Mock implementation of PositionerDriver."""

    def __init__(self, resource_manager, address: str):
        super().__init__(instrument_id=address, config={})
        self.address = address
        self.connected = False
        self._current_azimuth = 0.0
        self._is_moving = False

    async def connect(self) -> bool:
        self.connected = True
        logger.info(f"Mock Positioner connected at {self.address}")
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        logger.info("Mock Positioner disconnected")
        return True
        
    async def configure(self, config: Dict[str, Any]) -> bool:
        return True
        
    async def get_capabilities(self) -> list:
        return []
        
    async def get_metrics(self) -> Any:
        # Mocking InstrumentMetrics shape approximately
        return {"timestamp": "2026", "metrics": {}, "status": "normal"}
        
    async def reset(self) -> bool:
        self._current_azimuth = 0.0
        return True

    async def initialize(self) -> bool:
        return await self.connect()

    async def health_check(self) -> Dict[str, Any]:
        return {
            "status": "ok" if self.connected else "error",
            "model": "Mock-Turntable-3000",
            "current_azimuth": self._current_azimuth
        }

    def _check_connected(self):
        if not self.connected:
            raise RuntimeError("Positioner is not connected")

    async def move_to_azimuth(self, angle_deg: float) -> None:
        self._check_connected()
        logger.info(f"Mock Positioner moving to {angle_deg}°")
        self._is_moving = True
        # Simulate movement delay
        await asyncio.sleep(0.5)
        self._current_azimuth = float(angle_deg)
        self._is_moving = False

    async def get_current_azimuth(self) -> float:
        self._check_connected()
        return self._current_azimuth

    async def wait_until_settled(self, timeout_s: float = 30.0) -> bool:
        self._check_connected()
        while self._is_moving:
            await asyncio.sleep(0.1)
        return True
