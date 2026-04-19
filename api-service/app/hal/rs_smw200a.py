"""
R&S SMW200A / SMU200A Signal Generator Driver
=============================================

Real HAL Driver for R&S SMW/SMU series Signal Generators.
"""

import logging
import asyncio
from typing import Dict, Any
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.signal_generator import SignalGeneratorDriver

logger = logging.getLogger(__name__)


class RssSigGenScpi:
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"

    SET_FREQ = "SOURce1:FREQuency:CW {freq}"
    SET_POW = "SOURce1:POWer:POWer {power}"
    OUTP_ON = "OUTPut1:STATe ON"
    OUTP_OFF = "OUTPut1:STATe OFF"


class RealRsSmw200aDriver(SignalGeneratorDriver):
    """Real HAL for R&S SMU/SMW Signal Generators"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = config.get("ip", "192.168.100.60")
        self._visa_rm = None
        self._visa_session = None

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()
            self._visa_session = self._visa_rm.open_resource(
                f"TCPIP::{self.ip_address}::INSTR", timeout=5000
            )
            idn = self._query(RssSigGenScpi.IDN).strip()
            logger.info(f"[SMW200A] Connected to {idn}")
            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[SMW200A] Connection failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def disconnect(self) -> bool:
        try:
            await self.stop_tx()
            if self._visa_session:
                self._visa_session.close()
                self._visa_session = None
            if self._visa_rm:
                self._visa_rm.close()
                self._visa_rm = None
            self._set_status(InstrumentStatus.DISCONNECTED)
            return True
        except Exception:
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        return True

    async def set_cw(self, frequency_hz: float, power_dbm: float) -> bool:
        try:
            self._write(RssSigGenScpi.SET_FREQ.format(freq=frequency_hz))
            self._write(RssSigGenScpi.SET_POW.format(power=power_dbm))
            self._query(RssSigGenScpi.OPC)
            return True
        except Exception as e:
            logger.error(f"[SMW200A] set cw failed: {e}")
            return False

    async def load_iq_waveform(self, waveform_name: str) -> bool:
        return True

    async def start_tx(self) -> bool:
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._write(RssSigGenScpi.OUTP_ON)
            self._query(RssSigGenScpi.OPC)
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception:
            return False

    async def stop_tx(self) -> bool:
        try:
            self._write(RssSigGenScpi.OUTP_OFF)
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception:
            return False

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [InstrumentCapability("cw", "CW Gen", True, {})]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(timestamp=datetime.utcnow(), metrics={})

    async def reset(self) -> bool:
        try:
            await self.stop_tx()
            self._write(RssSigGenScpi.RST)
            return True
        except Exception:
            return False

    def _write(self, cmd: str) -> None:
        if self._visa_session:
            self._visa_session.write(cmd)

    def _query(self, cmd: str) -> str:
        if self._visa_session:
            return self._visa_session.query(cmd)
        return ""
