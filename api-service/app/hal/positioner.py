"""
Positioner Driver HAL

Provides abstract interface and mock implementation for 3D/2D OTA positioners (turntables).
"""

import asyncio
import logging
import random
from typing import Dict, Any, Tuple
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


class PositionerDriver(InstrumentDriver):
    """
    Abstract interface for multi-axis positioners (HAL Layer 2)
    Typically used to rotate the DUT (azimuth) and test antennas (elevation).
    """

    async def move_to(self, azimuth: float, elevation: float) -> bool:
        """
        Command the positioner to move to absolute coordinates.
        Args:
            azimuth (float): Azimuth angle in degrees (0 to 360)
            elevation (float): Elevation angle in degrees (-90 to +90)
        Returns:
            bool: True if movement successful
        """
        raise NotImplementedError

    async def get_position(self) -> Tuple[float, float]:
        """
        Get current (azimuth, elevation)
        """
        raise NotImplementedError

    async def stop(self) -> bool:
        """
        Immediately stop all axis motion.
        """
        raise NotImplementedError


class MockPositioner(PositionerDriver):
    """Fallback Mock implementation"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._azimuth = 0.0
        self._elevation = 0.0

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
                name="3d_positioning",
                description="Azimuth and Elevation control",
                supported=True,
                parameters={"azimuth_range": [0, 360], "elevation_range": [-90, 90]}
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "azimuth": self._azimuth,
                "elevation": self._elevation,
            }
        )

    async def reset(self) -> bool:
        await self.move_to(0, 0)
        return True

    async def move_to(self, azimuth: float, elevation: float) -> bool:
        self._set_status(InstrumentStatus.BUSY)
        await asyncio.sleep(min(abs(self._azimuth - azimuth) / 10.0, 5.0))
        self._azimuth = azimuth
        self._elevation = elevation
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_position(self) -> Tuple[float, float]:
        return (self._azimuth, self._elevation)

    async def stop(self) -> bool:
        self._set_status(InstrumentStatus.READY)
        return True
