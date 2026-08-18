"""
ETS-Lindgren EMCenter Positioner Driver
=======================================

Real HAL Driver for ETS-Lindgren EMCenter.
Communicates via PyVISA (TCP Socket or Serial over LAN).

References:
  EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf
"""

import logging
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
    resolve_configured_instrument_host,
)
from app.hal.positioner import EtsPositionerScpi, PositionerDriver

logger = logging.getLogger(__name__)


# ===========================================================================
# ETS-L EMCenter SCPI Commands (Generic/Representative)
# ===========================================================================
EtsScpi = EtsPositionerScpi


class RealEtsEmcenterDriver(PositionerDriver):
    """
    ETS-Lindgren EMCenter Real HAL Driver.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._reject_incompatible_visa_resource(allowed_type="SOCKET")
        self.ip_address: str = self._connection_host
        self.port: int = self._resolved_tcp_port(2000)
        self._connection_visa_resource = self._resolved_visa_resource(
            f"TCPIP::{self.ip_address}::{self.port}::SOCKET",
            socket_prefix="TCPIP",
        )
        self._visa_rm = None
        self._visa_session = None
        self._current_azimuth: Optional[float] = None

    def _unsupported_positioner_protocol(self) -> str:
        return (
            "EMCenter positioner control is disabled: no checked-in vendor "
            "evidence defines SET_POS/readback/stop semantics"
        )

    def _reject_unsupported_positioner_operation(self) -> str:
        message = self._unsupported_positioner_protocol()
        logger.error("[ETS-L] %s", message)
        self._set_status(InstrumentStatus.ERROR, message)
        return message

    async def connect(self) -> bool:
        if self._connection_config_error or not self.ip_address:
            return self._fail_missing_connection_address()
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager()
            resource_str = self._connection_visa_resource
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
            # ⚠ **不调** `self._visa_rm.close()`: RM 是**进程级共享单例**, 关它会连带
            # 关掉其它仪表的会话 (权威说明见 `app/hal/_visa_reconnect.py` 的
            # 「ResourceManager 所有权」一节)。自己的 session 上面已经关了, 这里只丢引用。
            self._visa_rm = None
            self._set_status(InstrumentStatus.DISCONNECTED)
            return True
        except Exception as e:
            logger.error(f"[ETS-L] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        return True

    async def move_to(
        self,
        azimuth: float,
        elevation: float,
        *,
        expected_operator_stop_generation: Optional[int] = None,
    ) -> bool:
        # The checked-in EMCenter document covers the RF-switch platform,
        # not a positioner motion protocol.  These historical representative
        # command strings therefore cannot safely drive a real turntable.
        self._reject_unsupported_positioner_operation()
        return False

    async def get_position(self) -> Tuple[float, float]:
        message = self._reject_unsupported_positioner_operation()
        raise RuntimeError(message)

    async def stop(self) -> bool:
        self._reject_unsupported_positioner_operation()
        return False

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                "3d_positioning",
                self._unsupported_positioner_protocol(),
                False,
                {},
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "azimuth": None,
                "position_verified": False,
                "position_unit": "unknown",
                "positioner_protocol_supported": False,
            },
        )

    async def reset(
        self,
        *,
        expected_operator_stop_generation: Optional[int] = None,
    ) -> bool:
        self._reject_unsupported_positioner_operation()
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
