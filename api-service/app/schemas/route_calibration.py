"""保存拓扑的完整固定通路声明；不是实物接通或正式校准资格。"""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, JsonValue


class RoutePort(BaseModel):
    model_config = ConfigDict(extra='forbid')
    connection_id: str
    source: str
    source_pin: str
    target: str
    target_pin: str


class RouteSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lab_profile_id: UUID
    chamber_id: UUID
    topology_id: UUID
    operating_mode: str
    chain_id: str
    ce_port: str
    probe_id: int
    polarization: str
    node_ids: list[str]
    connection_ids: list[str]
    ports: list[RoutePort]
    nodes: list[dict[str, JsonValue]]
    connections: list[dict[str, JsonValue]]
    calibration_node_ids: list[str]
    calibration_connection_ids: list[str]
    calibration_nodes: list[dict[str, JsonValue]]
    calibration_connections: list[dict[str, JsonValue]]
    reference_antenna_id: str | None = None
    analyzer_category_id: str | None = None
    route_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    configuration_digest: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
