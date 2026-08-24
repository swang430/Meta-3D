"""
Keysight X-Series Signal Analyzer Driver
========================================

Real HAL Driver for Keysight X-Series Signal Analyzers.

⚠ P1-70 注记（信道验证第一激活批的实施对象纠偏）：
现场 SA 实测是 R&S FSVA3000（docs/site-debug/2026-05-27-onsite-playbook.md:68，
"SCPI 是 R&S FSW/FSVA 命令族，不是 Keysight X-Series"），P0-4 起绑
`RealRsFsvaDriver`。且本地 Instrument_API_Doc 里 Keysight X 系列的两份"手册"
均系假文件（一份内容是 N6700 电源手册、一份是 HTML 网页）——按禁盲试铁律，
无真手册不实现 SCPI。故 measure_pdp / measure_doppler_spectrum 在本驱动保持
未实现并指路 FSVA；将来要启用 X 系列，先补真手册再实现。
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

    # ── P1-70：信道验证采集在 X 系列上显式未实现（见文件头注记） ──────

    _P1_70_NOT_IMPLEMENTED = (
        "Keysight X 系列的 {method} 未实现：现场 SA 系 R&S FSVA3000"
        "（RealRsFsvaDriver 已实现该测量，P1-70）；X 系列本地手册系假文件"
        "（一份是 N6700 电源手册、一份是 HTML 网页），按禁盲试铁律，"
        "实现前须先补真手册。"
    )

    async def measure_pdp(
        self,
        center_freq_hz: float,
        max_delay_ns: float = 2000.0,
        resolution_ns: float = 10.0,
    ):
        raise NotImplementedError(
            self._P1_70_NOT_IMPLEMENTED.format(method="measure_pdp")
        )

    async def measure_doppler_spectrum(
        self,
        center_freq_hz: float,
        max_doppler_hz: float = 500.0,
        num_bins: int = 256,
    ):
        raise NotImplementedError(
            self._P1_70_NOT_IMPLEMENTED.format(method="measure_doppler_spectrum")
        )

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        if self._visa_session:
            self._visa_session.write(cmd)

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        if self._visa_session:
            return self._visa_session.query(cmd)
        return ""
