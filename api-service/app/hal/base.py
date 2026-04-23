"""
Base classes for Hardware Abstraction Layer (HAL)

Defines abstract interfaces that all instrument drivers must implement.

SCPI 日志架构:
  base 类提供 _write() / _query() 模板方法，自动记录到 scpi.log。
  子类只需覆盖 _do_write() / _do_query() 实现具体的 I/O 操作。
"""

from abc import ABC, abstractmethod
from enum import Enum
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class InstrumentStatus(str, Enum):
    """Instrument connection and operational status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    UNKNOWN = "unknown"


class InstrumentCapability(BaseModel):
    """Instrument capability description"""
    name: str
    description: str
    supported: bool
    parameters: Optional[Dict[str, Any]] = None


class InstrumentMetrics(BaseModel):
    """Real-time metrics from instrument"""
    timestamp: datetime
    metrics: Dict[str, Any]
    status: str = "normal"  # normal, warning, critical


class InstrumentDriver(ABC):
    """
    Abstract base class for all instrument drivers

    Provides standard interface for:
    - Connection management
    - Configuration
    - Data acquisition
    - Status monitoring

    SCPI 日志:
      子类不要直接覆盖 _write() / _query()，
      而是覆盖 _do_write() / _do_query()。
      基类的 _write() / _query() 会自动记录 SCPI 通信到 scpi.log。
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        """
        Initialize instrument driver

        Args:
            instrument_id: Unique identifier for this instrument
            config: Configuration parameters (IP, port, model, etc.)
        """
        self.instrument_id = instrument_id
        self.config = config
        self._status = InstrumentStatus.DISCONNECTED
        self._last_error: Optional[str] = None

        # SCPI 通信专用 logger — 命名空间 app.hal.scpi.{id}
        # 被 logging_config 中的 SCPI handler 独立捕获到 scpi.log
        self._scpi_logger = logging.getLogger(f"app.hal.scpi.{instrument_id}")

    # ── SCPI 日志记录 (内部使用) ───────────────────────────────

    def _log_scpi_write(self, cmd: str) -> None:
        """记录 SCPI 写命令到 scpi.log"""
        self._scpi_logger.debug(
            f"TX: {cmd}",
            extra={"instrument_id": self.instrument_id, "direction": "TX"},
        )

    def _log_scpi_response(self, cmd: str, response: str) -> None:
        """记录 SCPI 查询及其响应到 scpi.log"""
        self._scpi_logger.debug(
            f"RX: {response.strip()[:200]}",
            extra={
                "instrument_id": self.instrument_id,
                "direction": "RX",
                "query": cmd,
            },
        )

    # ── SCPI 模板方法 (子类覆盖 _do_write / _do_query) ────────

    def _write(self, cmd: str, **kwargs) -> None:
        """
        发送 SCPI 写命令（模板方法）。
        
        自动记录到 scpi.log，然后调用子类的 _do_write() 实现。
        子类应覆盖 _do_write() 而非本方法。
        """
        self._log_scpi_write(cmd)
        return self._do_write(cmd, **kwargs)

    def _query(self, cmd: str, **kwargs) -> str:
        """
        发送 SCPI 查询命令并返回响应（模板方法）。
        
        自动记录 TX/RX 到 scpi.log，然后调用子类的 _do_query() 实现。
        子类应覆盖 _do_query() 而非本方法。
        """
        self._log_scpi_write(cmd)
        response = self._do_query(cmd, **kwargs)
        self._log_scpi_response(cmd, response)
        return response

    def _do_write(self, cmd: str, **kwargs) -> None:
        """
        子类实现: 实际的 SCPI 写操作。
        
        默认实现为 no-op（Mock 模式安全）。
        真实驱动应覆盖此方法调用 visa_session.write()。
        """
        pass

    def _do_query(self, cmd: str, **kwargs) -> str:
        """
        子类实现: 实际的 SCPI 查询操作。
        
        默认实现返回空字符串（Mock 模式安全）。
        真实驱动应覆盖此方法调用 visa_session.query()。
        """
        return ""

    # ── 状态与属性 ────────────────────────────────────────────

    @property
    def status(self) -> InstrumentStatus:
        """Get current instrument status"""
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        """Get last error message"""
        return self._last_error

    # ── 抽象接口 ──────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to instrument

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close connection to instrument

        Returns:
            True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    async def configure(self, config: Dict[str, Any]) -> bool:
        """
        Configure instrument parameters

        Args:
            config: Configuration parameters to apply

        Returns:
            True if configuration successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_capabilities(self) -> list[InstrumentCapability]:
        """
        Get instrument capabilities

        Returns:
            List of supported capabilities
        """
        pass

    @abstractmethod
    async def get_metrics(self) -> InstrumentMetrics:
        """
        Get current instrument metrics

        Returns:
            Current metrics data
        """
        pass

    @abstractmethod
    async def reset(self) -> bool:
        """
        Reset instrument to default state

        Returns:
            True if reset successful, False otherwise
        """
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on instrument

        Returns:
            Health status information
        """
        return {
            "instrument_id": self.instrument_id,
            "status": self.status.value,
            "last_error": self.last_error,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _set_status(self, status: InstrumentStatus, error: Optional[str] = None):
        """Internal method to update status with lifecycle logging"""
        old_status = self._status
        self._status = status
        # VISA 连接生命周期日志 — 记录每次状态变更
        if old_status != status:
            logger.info(
                f"[{self.instrument_id}] status: {old_status.value} → {status.value}",
                extra={"instrument_id": self.instrument_id},
            )
        if error:
            self._last_error = error
            logger.error(
                f"[{self.instrument_id}] error: {error}",
                extra={"instrument_id": self.instrument_id},
            )

    def _clear_error(self):
        """Internal method to clear error"""
        self._last_error = None
