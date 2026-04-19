"""
R&S FSW Signal Analyzer Driver
==============================

Real HAL Driver for R&S FSW series Signal Analyzers.
"""

import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.signal_analyzer import SignalAnalyzerDriver

logger = logging.getLogger(__name__)


class FswScpi:
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"

    SET_FREQ = "SENSe:FREQuency:CENTer {freq}"
    SET_SPAN = "SENSe:FREQuency:SPAN {span}"
    SET_RBW = "SENSe:BANDwidth:RESolution {rbw}"
    
    INIT_CONT_OFF = "INIT:CONT OFF"
    TRIG = "INIT:IMM; *OPC?"
    READ_TRAC = "TRACe:DATA? TRACE1"


class RealRsFswDriver(SignalAnalyzerDriver):
    """Real HAL for R&S FSW Signal Analyzer"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = config.get("ip", "192.168.100.80")
        self._visa_rm = None
        self._visa_session = None

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()
            self._visa_session = self._visa_rm.open_resource(
                f"TCPIP::{self.ip_address}::INSTR", timeout=10000
            )
            idn = self._query(FswScpi.IDN).strip()
            logger.info(f"[FSW] Connected to {idn}")
            
            self._write(FswScpi.INIT_CONT_OFF)
            self._write("FORMAT ASC")
            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[FSW] Connection failed: {e}")
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
        except Exception:
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        return True

    async def setup_spectrum(self, center_freq_hz: float, span_hz: float, rbw_hz: float) -> bool:
        try:
            self._write(FswScpi.SET_FREQ.format(freq=center_freq_hz))
            self._write(FswScpi.SET_SPAN.format(span=span_hz))
            self._write(FswScpi.SET_RBW.format(rbw=rbw_hz))
            self._query(FswScpi.OPC)
            return True
        except Exception as e:
            logger.error(f"[FSW] Setup failed: {e}")
            return False

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._query(FswScpi.TRIG)
            data = await self.get_trace()
            self._set_status(InstrumentStatus.READY)
            return sum(data) / len(data) if data else -100.0
        except Exception:
            return -100.0

    async def get_trace(self) -> List[float]:
        try:
            data_str = self._query(FswScpi.READ_TRAC)
            vals = list(map(float, data_str.strip().split(',')))
            return vals
        except Exception:
            return []

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [InstrumentCapability("spectrum", "Spectrum Analyzer", True, {})]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(timestamp=datetime.utcnow(), metrics={})

    async def reset(self) -> bool:
        try:
            self._write(FswScpi.RST)
            self._query(FswScpi.OPC)
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
