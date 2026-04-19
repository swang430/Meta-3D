"""
Keysight ENA Vector Network Analyzer Driver
===========================================

Real HAL Driver for Keysight E5071C / ENA series VNAs.
Based on E5071C Programmers Guide.
"""

import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime
import numpy as np

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.vna import VNADriver

logger = logging.getLogger(__name__)


class EnaScpi:
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    
    # Sweep configuration
    SET_POINTS = "SENS1:SWE:POIN {points}"
    SET_START_FREQ = "SENS1:FREQ:STAR {freq}"
    SET_STOP_FREQ = "SENS1:FREQ:STOP {freq}"
    
    # Trace/Measurement allocation
    DEF_MEAS = "CALC1:PAR1:DEF {param}"   # e.g., 'S21'
    SEL_MEAS = "CALC1:PAR1:SEL"
    
    # Format and Read
    DATA_FMT = "FORM:DATA ASC"            # ASCII data
    INIT_CONT = "INIT1:CONT OFF"          # Single sweep mode
    TRIG_SING = "INIT1; *OPC?"            # Trigger and wait
    READ_DATA = "CALC1:DATA? SDATA"       # Get Complex pairs


class RealKeysightEnaDriver(VNADriver):
    """Real HAL for Keysight ENA"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = config.get("ip", "192.168.100.40")
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
            idn = self._query(EnaScpi.IDN).strip()
            logger.info(f"[ENA] Connected to {idn}")
            self._write(EnaScpi.DATA_FMT)
            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[ENA] Connection failed: {e}")
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

    async def setup_sweep(self, start_freq_hz: float, stop_freq_hz: float, points: int) -> bool:
        try:
            self._write(EnaScpi.SET_START_FREQ.format(freq=start_freq_hz))
            self._write(EnaScpi.SET_STOP_FREQ.format(freq=stop_freq_hz))
            self._write(EnaScpi.SET_POINTS.format(points=points))
            self._query(EnaScpi.OPC)
            return True
        except Exception as e:
            logger.error(f"[ENA] Setup failed: {e}")
            return False

    async def measure_s_param(self, measurement: str = "S21") -> bool:
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._write(EnaScpi.DEF_MEAS.format(param=measurement))
            self._write(EnaScpi.SEL_MEAS)
            self._write(EnaScpi.INIT_CONT)
            # Blocking trigger with OPC
            self._query(EnaScpi.TRIG_SING)
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception as e:
            logger.error(f"[ENA] Measure failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def get_trace_data(self) -> List[complex]:
        try:
            data_str = self._query(EnaScpi.READ_DATA)
            values = list(map(float, data_str.strip().split(',')))
            # Data comes as Real, Imag, Real, Imag...
            real_parts = values[0::2]
            imag_parts = values[1::2]
            complex_trace = [complex(r, i) for r, i in zip(real_parts, imag_parts)]
            return complex_trace
        except Exception as e:
            logger.error(f"[ENA] Get trace data failed: {e}")
            return []

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [InstrumentCapability("s_parameters", "S11, S21", True, {})]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(timestamp=datetime.utcnow(), metrics={})

    async def reset(self) -> bool:
        try:
            self._write(EnaScpi.RST)
            self._query(EnaScpi.OPC)
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
