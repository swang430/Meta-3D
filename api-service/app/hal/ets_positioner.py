"""
ETS-Lindgren EMCenter Positioner Driver
=======================================

Real HAL Driver for ETS-Lindgren EMCenter.
Communicates via PyVISA (TCP Socket or Serial over LAN).

References:
  EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf
"""

import logging
import asyncio
from typing import Dict, Any, Tuple, List
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.positioner import PositionerDriver

logger = logging.getLogger(__name__)


# ===========================================================================
# ETS-L EMCenter SCPI Commands (Generic/Representative)
# ===========================================================================
class EtsScpi:
    IDN = "*IDN?"
    RST = "*RST"
    # Positioner specific (Axis 1 = Turntable)
    GET_POS = "SOURce:POSition? 1"
    SET_POS = "SOURce:POSition 1,{angle}"
    STOP = "ABORt 1"
    WAIT = "*OPC?"


class RealEtsEmcenterDriver(PositionerDriver):
    """
    ETS-Lindgren EMCenter Real HAL Driver.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = config.get("ip", "192.168.100.30")
        self.port: int = config.get("port", 2000)
        self._visa_rm = None
        self._visa_session = None
        self._current_azimuth = 0.0

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()
            resource_str = f"TCPIP::{self.ip_address}::{self.port}::SOCKET"
            self._visa_session = self._visa_rm.open_resource(resource_str)
            self._visa_session.read_termination = '\n'
            self._visa_session.write_termination = '\n'
            
            idn = self._query(EtsScpi.IDN).strip()
            logger.info(f"[ETS-L] Connected: {idn}")
            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[ETS-L] Connection failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def disconnect(self) -> bool:
        try:
            if self._visa_session:
                self._visa_session.close()
                self._visa_session = None
            if self._visa_rm:
                self._visa_rm.close()
                self._visa_rm = None
            self._set_status(InstrumentStatus.DISCONNECTED)
            return True
        except Exception as e:
            logger.error(f"[ETS-L] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        return True

    async def move_to(self, azimuth: float, elevation: float) -> bool:
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._write(EtsScpi.SET_POS.format(angle=azimuth))
            # Wait for physical movement
            while True:
                await asyncio.sleep(0.5)
                # Query if still moving or arrived (simplified logically)
                pos = await self.get_position()
                if abs(pos[0] - azimuth) < 0.5:
                    break
            
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception as e:
            logger.error(f"[ETS-L] Move failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def get_position(self) -> Tuple[float, float]:
        try:
            pos_str = self._query(EtsScpi.GET_POS)
            self._current_azimuth = float(pos_str.strip())
            return (self._current_azimuth, 0.0)  # Elev not strictly mapped in simple TT
        except Exception:
            return (self._current_azimuth, 0.0)

    async def stop(self) -> bool:
        try:
            self._write(EtsScpi.STOP)
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception:
            return False

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [InstrumentCapability("3d_positioning", "Azimuth control", True, {})]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(timestamp=datetime.utcnow(), metrics={"azimuth": self._current_azimuth})

    async def reset(self) -> bool:
        return await self.stop()

    def _write(self, cmd: str) -> None:
        if self._visa_session:
            self._visa_session.write(cmd)

    def _query(self, cmd: str) -> str:
        if self._visa_session:
            return self._visa_session.query(cmd)
        return ""
