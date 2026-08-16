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
    resolve_configured_instrument_host,
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
    # E5071C native trace-readback syntax (verified on A.09.60). The
    # PNA-style "CALC1:DATA? SDATA" form errors -113 "Undefined header"
    # on E5071C firmware; the selected-trace SDAT query works cleanly.
    READ_DATA = "CALC1:SEL:DATA:SDAT?"


class RealKeysightEnaDriver(VNADriver):
    """Real HAL for Keysight ENA"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = resolve_configured_instrument_host(config)
        self._visa_rm = None
        self._visa_session = None

    async def connect(self) -> bool:
        if not self.ip_address:
            return self._fail_missing_connection_address()
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
            # ⚠ **不调** `self._visa_rm.close()`: RM 是**进程级共享单例**, 关它会连带
            # 关掉其它仪表的会话 (权威说明见 `app/hal/_visa_reconnect.py` 的
            # 「ResourceManager 所有权」一节)。自己的 session 上面已经关了, 这里只丢引用。
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

    # ── VISA conn-lost silent reconnect (same as F64/FS16/UXM) ─────
    # The ENA was NOT exercised at CAICT 2026-05-13, so unlike F64 we
    # don't have field evidence that idle close happens here. The
    # reconnect path is added for uniformity — same Codex P2 lesson:
    # VI_ERROR_CONN_LOST / VI_ERROR_INV_OBJECT trigger one retry,
    # VI_ERROR_TMO propagates.

    @staticmethod
    def _is_visa_conn_lost(exc: BaseException) -> bool:
        from app.hal._visa_reconnect import is_visa_conn_lost
        return is_visa_conn_lost(exc)

    def _silent_reconnect_visa(self) -> bool:
        if self._visa_rm is None or not self.ip_address:
            return False
        try:
            if self._visa_session is not None:
                self._visa_session.close()
        except Exception:
            pass
        self._visa_session = None
        try:
            self._visa_session = self._visa_rm.open_resource(
                f"TCPIP::{self.ip_address}::INSTR",
                timeout=10000,
            )
            logger.info(f"[ENA] silent reconnect succeeded — {self.ip_address}")
            return True
        except Exception as e:
            logger.error(f"[ENA] silent reconnect failed: {e}")
            self._visa_session = None
            return False

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        for attempt in (0, 1):
            if not self._visa_session:
                return  # legacy contract: silent no-op when not connected
            try:
                self._visa_session.write(cmd)
                return
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[ENA] VISA connection lost on write '{cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if self._silent_reconnect_visa():
                        continue
                raise

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        for attempt in (0, 1):
            if not self._visa_session:
                return ""  # legacy contract
            try:
                return self._visa_session.query(cmd)
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[ENA] VISA connection lost on query '{cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if self._silent_reconnect_visa():
                        continue
                raise
        return ""
