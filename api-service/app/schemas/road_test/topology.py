"""
Network Topology Schemas

Data models for conducted test mode topology configuration
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime
from enum import Enum


class TopologyType(str, Enum):
    """Topology type"""
    SISO = "SISO"
    MIMO_2X2 = "MIMO_2x2"
    MIMO_4X4 = "MIMO_4x4"
    MIMO_8X8 = "MIMO_8x8"


class DeviceType(str, Enum):
    """Device type"""
    BASE_STATION = "base_station"
    CHANNEL_EMULATOR = "channel_emulator"
    DUT = "dut"
    SIGNAL_ANALYZER = "signal_analyzer"


class InterfaceType(str, Enum):
    """DUT control interface"""
    ADB = "adb"
    USB = "usb"
    ETHERNET = "ethernet"
    SERIAL = "serial"


class CableType(str, Enum):
    """RF cable type"""
    RG58 = "RG-58"
    LMR400 = "LMR-400"
    LMR600 = "LMR-600"
    CUSTOM = "custom"


# ===== Device Configuration =====

class DeviceConfig(BaseModel):
    """Base device configuration"""
    device_id: Optional[str] = Field(None, description="Device unique ID")
    device_type: DeviceType = Field(description="Device type")
    model: str = Field(description="Device model")
    ip_address: Optional[str] = Field(None, description="IP address")
    control_port: Optional[int] = Field(None, description="Control port")


class BaseStationDevice(DeviceConfig):
    """Base station emulator configuration"""
    device_type: DeviceType = Field(default=DeviceType.BASE_STATION)
    name: Optional[str] = Field(None, description="Device friendly name")
    tx_ports: int = Field(description="Number of TX ports")
    max_bandwidth_mhz: float = Field(description="Maximum bandwidth")
    frequency_range_ghz: Optional[tuple[float, float]] = Field(None, description="Frequency range")
    power_range_dbm: Optional[tuple[float, float]] = Field(None, description="Power range")

    # Common models: CMX500, 8820C, 8821C
    capabilities: Dict[str, bool] = Field(
        default_factory=lambda: {
            "supports_5g_nr": True,
            "supports_lte": True,
            "supports_fading": False
        }
    )


class ChannelEmulatorDevice(DeviceConfig):
    """Channel emulator configuration"""
    device_type: DeviceType = Field(default=DeviceType.CHANNEL_EMULATOR)
    name: Optional[str] = Field(None, description="Device friendly name")
    input_ports: int = Field(description="Number of input ports")
    output_ports: int = Field(description="Number of output ports")
    max_taps: Optional[int] = Field(None, description="Maximum channel taps")
    max_doppler_hz: Optional[float] = Field(None, description="Maximum Doppler frequency")

    # Common models: PropsIM F64, Vertex, KSW-WNS02B
    capabilities: Dict[str, bool] = Field(
        default_factory=lambda: {
            "supports_3gpp_models": True,
            "supports_custom_taps": True,
            "supports_mimo": True
        }
    )


class DUTDevice(DeviceConfig):
    """Device Under Test configuration"""
    device_type: DeviceType = Field(default=DeviceType.DUT)
    name: Optional[str] = Field(None, description="Device friendly name")
    antenna_ports: int = Field(description="Number of antenna ports")
    control_interface: Optional[InterfaceType] = Field(None, description="Control interface type")
    platform: Optional[str] = Field(None, description="Platform (e.g., Qualcomm X55, MediaTek T750)")

    # Control interface specific configuration
    interface_config: Dict[str, str] = Field(
        default_factory=dict,
        description="Interface configuration (e.g., {'adb_serial': 'ABC123'})"
    )


# ===== RF Connection =====

class RFConnection(BaseModel):
    """RF cable connection"""
    connection_id: str = Field(description="Connection ID")
    source_device_id: str = Field(description="Source device ID")
    source_port: int = Field(description="Source port number")
    target_device_id: str = Field(description="Target device ID")
    target_port: int = Field(description="Target port number")

    # Cable properties
    cable_type: CableType = Field(description="Cable type")
    cable_length_m: float = Field(description="Cable length in meters")
    loss_db: float = Field(description="Cable loss in dB")

    # Compensation
    compensate_loss: bool = Field(default=True, description="Compensate cable loss")


# ===== Network Topology =====

class NetworkTopology(BaseModel):
    """Complete network topology"""
    id: str = Field(description="Topology ID")
    name: str = Field(description="Topology name")
    topology_type: TopologyType = Field(description="Topology type")
    description: Optional[str] = Field(None, description="Topology description")

    # Devices
    base_station: BaseStationDevice = Field(description="Base station emulator")
    channel_emulator: ChannelEmulatorDevice = Field(description="Channel emulator")
    dut: DUTDevice = Field(description="Device under test")

    # Connections
    connections: List[RFConnection] = Field(description="RF cable connections")

    # Validation status
    is_validated: bool = Field(default=False, description="Topology validated")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors")

    # Metadata
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    author: Optional[str] = Field(None, description="Author")


class TopologyCreate(BaseModel):
    """Create topology request"""
    name: str = Field(description="Topology name")
    topology_type: TopologyType = Field(description="Topology type")
    description: Optional[str] = None

    base_station: BaseStationDevice
    channel_emulator: ChannelEmulatorDevice
    dut: DUTDevice
    connections: List[RFConnection]


class TopologyUpdate(BaseModel):
    """Update topology request"""
    name: Optional[str] = None
    topology_type: Optional[TopologyType] = None
    description: Optional[str] = None

    base_station: Optional[BaseStationDevice] = None
    channel_emulator: Optional[ChannelEmulatorDevice] = None
    dut: Optional[DUTDevice] = None
    connections: Optional[List[RFConnection]] = None


class TopologySummary(BaseModel):
    """Topology summary for list view"""
    id: str
    name: str
    topology_type: TopologyType
    description: Optional[str]
    is_validated: bool
    devices_count: int
    connections_count: int
    created_at: Optional[datetime]
    author: Optional[str]


class TopologyValidationRequest(BaseModel):
    """Topology validation request"""
    topology_id: str = Field(description="Topology ID to validate")


class TopologyValidationResult(BaseModel):
    """Topology validation result"""
    is_valid: bool = Field(description="Validation passed")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    details: Dict[str, Any] = Field(default_factory=dict, description="Validation details")
