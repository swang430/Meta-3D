"""Vendor-neutral logical port projection for MIMO OTA topology.

Logical topology is stable (DL1..DLN/UL1). Physical connector names are
optional display/audit evidence supplied by the selected driver/profile;
missing readback is a warning and never guessed from adapter/model names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional


PortRole = Literal["dl", "ul"]


@dataclass(frozen=True)
class BaseStationLogicalPort:
    logical_port: str
    role: PortRole
    physical_port: Optional[str] = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "logical_port": self.logical_port,
            "role": self.role,
            "physical_port": self.physical_port,
        }


@dataclass(frozen=True)
class BaseStationPortMapping:
    adapter_id: str
    mimo_port_preset: Optional[str]
    ports: tuple[BaseStationLogicalPort, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_runtime_blocker(self) -> bool:
        """P1-73A：物理 connector 缺回读只告警，不升级为运行硬门。"""

        return False

    @property
    def active_logical_ports(self) -> frozenset[str]:
        return frozenset(port.logical_port for port in self.ports)

    def to_payload(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "mimo_port_preset": self.mimo_port_preset,
            "ports": [port.to_payload() for port in self.ports],
            "warnings": list(self.warnings),
            "is_runtime_blocker": self.is_runtime_blocker,
        }


def _read_indexed_port(mapping: Any, index: int) -> Optional[str]:
    if not isinstance(mapping, Mapping):
        return None
    raw = mapping.get(index, mapping.get(str(index)))
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def resolve_base_station_port_mapping(
    *,
    adapter_id: str,
    mimo_port_preset: Optional[str],
    mimo_layers: int,
    route_snapshot: Optional[Mapping[str, Any]],
) -> BaseStationPortMapping:
    """Project one applied route snapshot onto logical MIMO OTA ports.

    The resolver never derives connector names from adapter id or preset.
    `mimo_port_preset` is audit identity only; physical names must be present
    in `route_snapshot` supplied by the selected driver's active profile or
    readback.
    """

    if isinstance(mimo_layers, bool) or not isinstance(mimo_layers, int):
        raise TypeError("mimo_layers must be an integer")
    if mimo_layers < 1 or mimo_layers > 8:
        raise ValueError("mimo_layers must be in 1..8")

    snapshot = route_snapshot if isinstance(route_snapshot, Mapping) else {}
    tx = snapshot.get("tx")
    uplink = snapshot.get("ota_uplink")
    if not isinstance(uplink, str) or not uplink.strip():
        uplink = None
    else:
        uplink = uplink.strip()

    ports: list[BaseStationLogicalPort] = []
    warnings: list[str] = []
    for index in range(1, mimo_layers + 1):
        physical = _read_indexed_port(tx, index)
        ports.append(
            BaseStationLogicalPort(
                logical_port=f"DL{index}", role="dl", physical_port=physical
            )
        )
        if physical is None:
            warnings.append(
                f"Warning: {adapter_id} DL{index} physical connector is unknown"
            )

    ports.append(
        BaseStationLogicalPort(
            logical_port="UL1", role="ul", physical_port=uplink
        )
    )
    if uplink is None:
        warnings.append(
            f"Warning: {adapter_id} UL1 physical connector is unknown"
        )

    return BaseStationPortMapping(
        adapter_id=str(adapter_id),
        mimo_port_preset=mimo_port_preset,
        ports=tuple(ports),
        warnings=tuple(warnings),
    )
