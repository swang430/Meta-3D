"""
Keysight X-Series Signal Analyzer Driver
========================================

Real HAL Driver for Keysight X-Series Signal Analyzers.
"""

import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
    resolve_configured_instrument_host,
)
from app.hal.signal_analyzer import SignalAnalyzerDriver, XSeriesScpi

logger = logging.getLogger(__name__)


XSaScpi = XSeriesScpi


class RealKeysightXSeriesSaDriver(SignalAnalyzerDriver):
    """Real HAL for Keysight X-Series Signal Analyzer"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._reject_incompatible_visa_resource(allowed_type="INSTR")
        self._reject_plain_endpoint_port(fixed_type="INSTR")
        self._reject_nondefault_metadata_port(default=5025, fixed_type="INSTR")
        self.ip_address: str = self._connection_host
        self._connection_visa_resource = self._resolved_visa_resource(
            f"TCPIP::{self.ip_address}::INSTR",
            socket_prefix="TCPIP",
            explicit_port_to_socket=False,
        )
        self._visa_rm = None
        self._visa_session = None

    async def connect(self) -> bool:
        if self._connection_config_error or not self.ip_address:
            return self._fail_missing_connection_address()
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()
            self._visa_session = self._visa_rm.open_resource(
                self._connection_visa_resource, timeout=10000
            )
            idn = self._query(XSaScpi.IDN).strip()
            logger.info(f"[X-Series SA] Connected to {idn}")
            
            # Put in single sweep mode
            self._write(XSaScpi.INIT_CONT_OFF)
            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[X-Series SA] Connection failed: {e}")
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

    async def setup_spectrum(self, center_freq_hz: float, span_hz: float, rbw_hz: float) -> bool:
        try:
            self._write(XSaScpi.SET_FREQ.format(freq=center_freq_hz))
            self._write(XSaScpi.SET_SPAN.format(span=span_hz))
            self._write(XSaScpi.SET_RBW.format(rbw=rbw_hz))
            self._query(XSaScpi.OPC)
            return True
        except Exception as e:
            logger.error(f"[X-Series SA] Setup failed: {e}")
            return False

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._query(XSaScpi.TRIG)
            # Fetch generic power reading - normally requires setting up CHP mode
            # But we fallback to trace average for basic abstraction
            data = await self.get_trace()
            self._set_status(InstrumentStatus.READY)
            return sum(data) / len(data) if data else -100.0
        except Exception:
            return -100.0

    async def get_trace(self) -> List[float]:
        try:
            data_str = self._query(XSaScpi.READ_MEAS)
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
            self._write(XSaScpi.RST)
            self._query(XSaScpi.OPC)
            return True
        except Exception:
            return False

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        if self._visa_session:
            self._visa_session.write(cmd)

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        if self._visa_session:
            return self._visa_session.query(cmd)
        return ""
