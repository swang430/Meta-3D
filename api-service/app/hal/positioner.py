"""
Positioner Driver HAL

Provides abstract interface and mock implementation for 3D/2D OTA positioners (turntables).
"""

import asyncio
import logging
import random
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional, Tuple
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


# One operation-lifecycle baseline.  Formal background tasks set this before
# task creation; commissioning owners set it before waiting for the instrument
# lease.  Later MEASURE/cleanup work therefore cannot adopt an intervening
# operator stop as a new baseline.
current_positioner_operation_stop_generation: ContextVar[Optional[int]] = (
    ContextVar("positioner_operation_stop_generation", default=None)
)


@contextmanager
def retain_positioner_stop_generation(
    positioner: Any,
) -> Iterator[Optional[int]]:
    """Retain one operation's stop generation across awaits and phases."""
    reader = getattr(positioner, "operator_stop_generation", None)
    generation = reader() if callable(reader) else None
    token = current_positioner_operation_stop_generation.set(generation)
    try:
        yield generation
    finally:
        current_positioner_operation_stop_generation.reset(token)


class EtsPositionerScpi:
    """Legacy representative strings; real EMCenter motion must not send them.

    The checked-in EMCenter manual documents the RF-switch platform, not a
    positioner motion protocol.  These constants remain only for the mock
    driver's synthetic exchange trace until vendor evidence is available.
    """

    IDN = "*IDN?"
    RST = "*RST"
    GET_POS = "SOURce:POSition? 1"
    SET_POS = "SOURce:POSition 1,{angle}"
    STOP = "ABORt 1"
    WAIT = "*OPC?"


class PositionerDriver(InstrumentDriver):
    """
    Abstract interface for multi-axis positioners (HAL Layer 2)
    Typically used to rotate the DUT (azimuth) and test antennas (elevation).
    """

    def note_operator_stop(self) -> None:
        """Publish operator emergency-stop intent to every multi-step consumer.

        Internal safety cleanup calls ``stop()`` directly and deliberately does
        not advance this generation.  A new operation snapshots the generation,
        so a historical stop request does not permanently disable the driver.
        """
        self._operator_stop_generation = self.operator_stop_generation() + 1

    def operator_stop_generation(self) -> int:
        """Return the process-local operator-stop generation for this driver."""
        return int(getattr(self, "_operator_stop_generation", 0))

    async def move_to(
        self,
        azimuth: float,
        elevation: float,
        *,
        expected_operator_stop_generation: Optional[int] = None,
    ) -> bool:
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

    async def reset(
        self,
        *,
        expected_operator_stop_generation: Optional[int] = None,
    ) -> bool:
        """Home while honoring the caller's operator-stop generation."""
        raise NotImplementedError


class MockPositioner(PositionerDriver):
    """Fallback Mock implementation"""

    driver_source = "mock"
    simulated = True

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

    async def reset(
        self,
        *,
        expected_operator_stop_generation: Optional[int] = None,
    ) -> bool:
        return await self.move_to(
            0,
            0,
            expected_operator_stop_generation=expected_operator_stop_generation,
        )

    async def move_to(
        self,
        azimuth: float,
        elevation: float,
        *,
        expected_operator_stop_generation: Optional[int] = None,
    ) -> bool:
        if (
            expected_operator_stop_generation is not None
            and self.operator_stop_generation()
            != expected_operator_stop_generation
        ):
            return False
        self._set_status(InstrumentStatus.BUSY)
        await asyncio.sleep(min(abs(self._azimuth - azimuth) / 10.0, 5.0))
        self._azimuth = azimuth
        self._elevation = elevation
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_position(self) -> Tuple[float, float]:
        self._simulate_scpi_query(
            EtsPositionerScpi.GET_POS,
            f"{self._azimuth}",
        )
        return (self._azimuth, self._elevation)

    async def stop(self) -> bool:
        self._set_status(InstrumentStatus.READY)
        return True
