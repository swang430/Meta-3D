"""
Base classes for Hardware Abstraction Layer (HAL)

Defines abstract interfaces that all instrument drivers must implement.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel


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

    @property
    def status(self) -> InstrumentStatus:
        """Get current instrument status"""
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        """Get last error message"""
        return self._last_error

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
        """Internal method to update status"""
        self._status = status
        if error:
            self._last_error = error

    def _clear_error(self):
        """Internal method to clear error"""
        self._last_error = None
