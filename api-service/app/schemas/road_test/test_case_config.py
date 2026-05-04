"""
TestCase.configuration schema for VRT.

Phase 1 of the VRT-into-TestCase consolidation. When a TestCase has
test_type='VirtualRoadTest', its `configuration` JSON column must conform to
`VirtualRoadTestConfig`. This is the structural bridge that lets VRT live as a
specialized TestCase rather than as a parallel data model.

Fields that already have typed columns on the TestCase table
(frequency_mhz, bandwidth_mhz, channel_model, tx_power_dbm, test_duration_sec,
pass_criteria, probe_selection, instrument_config) stay there. Everything VRT-
specific that doesn't fit those columns lives here.
"""
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from .scenario import (
    BaseStationConfig,
    BeamSwitchEvent,
    Environment,
    HandoverEvent,
    KPIDefinition,
    NetworkConfig,
    RFImpairmentEvent,
    Route,
    ScenarioCategory,
    StepConfiguration,
    TrafficBurstEvent,
    TrafficConfig,
)
from .execution import TestMode


class VirtualRoadTestConfig(BaseModel):
    """Shape of TestCase.configuration when test_type='VirtualRoadTest'."""

    # D4: TestMode (digital_twin/conducted/ota) lives here, not on TestCase
    mode: TestMode = Field(description="Test mode: digital_twin | conducted | ota")

    # Scenario taxonomy (replaces RoadTestScenario.category)
    category: ScenarioCategory = Field(description="Scenario category")

    # D3: optional reference to an independent Topology entity (UUID string).
    # Concrete topology data lives in the `topologies` table, not here.
    topology_id: Optional[str] = Field(
        None,
        description="Reference to Topology entity (UUID string)",
    )

    # Scenario configuration — composed from existing road_test schemas
    network: NetworkConfig
    base_stations: List[BaseStationConfig]
    route: Route
    environment: Environment
    traffic: TrafficConfig
    events: List[
        Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent]
    ] = Field(default_factory=list)
    kpi_definitions: List[KPIDefinition]

    # Optional pre-configured test step parameters
    step_configuration: Optional[StepConfiguration] = None


VRT_TEST_TYPE = "VirtualRoadTest"


def validate_test_case_configuration(test_type: str, configuration: dict) -> dict:
    """Validate `TestCase.configuration` against the schema for the given test_type.

    For VRT, returns the normalized dict (Pydantic-roundtripped) so the caller
    can persist a clean structure. For other test_types this is a pass-through
    today; future test_types can register their own validators here.
    """
    if test_type == VRT_TEST_TYPE:
        validated = VirtualRoadTestConfig.model_validate(configuration)
        return validated.model_dump(mode="json")
    return configuration
