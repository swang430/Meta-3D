"""
Channel Emulator HAL

Provides interface and mock implementation for MIMO channel emulators.
Supports vendors like R&S, Keysight, Spirent, etc.
"""

import asyncio
import random
from typing import Dict, Any, Optional
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics
)


class ChannelEmulatorDriver(InstrumentDriver):
    """
    Abstract interface for Channel Emulator instruments

    Core capabilities:
    - MIMO channel modeling (spatial correlation, fading)
    - Path loss and delay configuration
    - Doppler shift simulation
    - Real-time channel updates
    """

    async def set_channel_model(
        self,
        model_type: str,  # e.g., "WINNER_II", "3GPP_38.901"
        scenario: str,  # e.g., "UMi", "UMa", "Indoor"
        parameters: Dict[str, Any]
    ) -> bool:
        """Set channel propagation model"""
        raise NotImplementedError

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: Optional[list[list[float]]] = None
    ) -> bool:
        """Configure MIMO antenna array"""
        raise NotImplementedError

    async def set_path_loss(
        self,
        path_loss_db: float,
        distance_m: Optional[float] = None
    ) -> bool:
        """Set path loss value"""
        raise NotImplementedError

    async def set_doppler(
        self,
        frequency_hz: float,
        velocity_kmh: Optional[float] = None
    ) -> bool:
        """Set Doppler shift parameters"""
        raise NotImplementedError

    async def start_emulation(self) -> bool:
        """Start channel emulation"""
        raise NotImplementedError

    async def stop_emulation(self) -> bool:
        """Stop channel emulation"""
        raise NotImplementedError

    async def get_channel_state(self) -> Dict[str, Any]:
        """Get current channel state"""
        raise NotImplementedError


class MockChannelEmulator(ChannelEmulatorDriver):
    """
    Mock implementation of Channel Emulator for development/testing

    Simulates realistic behavior without requiring actual hardware.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._emulation_running = False
        self._channel_model = "3GPP_38.901"
        self._scenario = "UMi"
        self._tx_antennas = 4
        self._rx_antennas = 4
        self._path_loss_db = 80.0
        self._doppler_hz = 100.0

    async def connect(self) -> bool:
        """Simulate connection to emulator"""
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.5)  # Simulate connection time

        # Simulate 95% success rate
        if random.random() < 0.95:
            self._set_status(InstrumentStatus.CONNECTED)
            self._clear_error()
            return True
        else:
            self._set_status(InstrumentStatus.ERROR, "Connection timeout")
            return False

    async def disconnect(self) -> bool:
        """Simulate disconnection"""
        if self._emulation_running:
            await self.stop_emulation()

        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        """Apply configuration parameters"""
        if self.status != InstrumentStatus.CONNECTED:
            self._set_status(InstrumentStatus.ERROR, "Not connected")
            return False

        # Apply configuration
        if "channel_model" in config:
            self._channel_model = config["channel_model"]
        if "scenario" in config:
            self._scenario = config["scenario"]
        if "tx_antennas" in config:
            self._tx_antennas = config["tx_antennas"]
        if "rx_antennas" in config:
            self._rx_antennas = config["rx_antennas"]

        self._set_status(InstrumentStatus.READY)
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        """Return supported capabilities"""
        return [
            InstrumentCapability(
                name="mimo",
                description="MIMO channel emulation",
                supported=True,
                parameters={"max_tx": 8, "max_rx": 8}
            ),
            InstrumentCapability(
                name="channel_models",
                description="Supported channel models",
                supported=True,
                parameters={
                    "models": ["3GPP_38.901", "WINNER_II", "ITU"],
                    "scenarios": ["UMi", "UMa", "Indoor", "Rural"]
                }
            ),
            InstrumentCapability(
                name="doppler",
                description="Doppler shift simulation",
                supported=True,
                parameters={"max_frequency_hz": 1000}
            ),
            InstrumentCapability(
                name="fading",
                description="Fast/slow fading simulation",
                supported=True
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        """Generate mock metrics"""
        # Simulate realistic metrics with variation
        snr = 25.0 + random.uniform(-5, 5)
        throughput = 150.0 + random.uniform(-30, 50)
        path_loss = self._path_loss_db + random.uniform(-2, 2)

        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "channel_model": self._channel_model,
                "scenario": self._scenario,
                "emulation_running": self._emulation_running,
                "snr_db": round(snr, 2),
                "throughput_mbps": round(throughput, 2),
                "path_loss_db": round(path_loss, 2),
                "doppler_hz": self._doppler_hz,
                "tx_antennas": self._tx_antennas,
                "rx_antennas": self._rx_antennas
            },
            status="normal" if snr > 15 else "warning"
        )

    async def reset(self) -> bool:
        """Reset to default configuration"""
        if self._emulation_running:
            await self.stop_emulation()

        self._channel_model = "3GPP_38.901"
        self._scenario = "UMi"
        self._tx_antennas = 4
        self._rx_antennas = 4
        self._path_loss_db = 80.0
        self._doppler_hz = 100.0

        self._set_status(InstrumentStatus.READY)
        return True

    async def set_channel_model(
        self,
        model_type: str,
        scenario: str,
        parameters: Dict[str, Any]
    ) -> bool:
        """Set channel propagation model"""
        self._channel_model = model_type
        self._scenario = scenario
        return True

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: Optional[list[list[float]]] = None
    ) -> bool:
        """Configure MIMO antenna array"""
        if tx_antennas > 8 or rx_antennas > 8:
            return False

        self._tx_antennas = tx_antennas
        self._rx_antennas = rx_antennas
        return True

    async def set_path_loss(
        self,
        path_loss_db: float,
        distance_m: Optional[float] = None
    ) -> bool:
        """Set path loss value"""
        if path_loss_db < 0 or path_loss_db > 200:
            return False

        self._path_loss_db = path_loss_db
        return True

    async def set_doppler(
        self,
        frequency_hz: float,
        velocity_kmh: Optional[float] = None
    ) -> bool:
        """Set Doppler shift parameters"""
        if frequency_hz < 0 or frequency_hz > 1000:
            return False

        self._doppler_hz = frequency_hz
        return True

    async def start_emulation(self) -> bool:
        """Start channel emulation"""
        if self.status != InstrumentStatus.READY:
            return False

        self._set_status(InstrumentStatus.BUSY)
        self._emulation_running = True
        await asyncio.sleep(0.2)  # Simulate startup time
        return True

    async def stop_emulation(self) -> bool:
        """Stop channel emulation"""
        self._emulation_running = False
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_channel_state(self) -> Dict[str, Any]:
        """Get current channel state"""
        return {
            "model": self._channel_model,
            "scenario": self._scenario,
            "running": self._emulation_running,
            "mimo_config": {
                "tx": self._tx_antennas,
                "rx": self._rx_antennas
            },
            "path_loss_db": self._path_loss_db,
            "doppler_hz": self._doppler_hz
        }
