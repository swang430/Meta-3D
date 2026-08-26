"""Vendor-neutral base-station adapter profile contracts.

The CMW500 route fields are identifiers configured by the laboratory.  This
module validates their shape only; Task 8 owns instrument writes/readback.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.hal.cmw500_command_profile import normalize_cmw_route_token


class Cmw500Lte2x2InternalRoute(BaseModel):
    """Exact seven-field internal route required by the LTE 2x2 adapter."""

    model_config = ConfigDict(extra="forbid")

    pcc_bb_board: str
    rx_connector: str
    rx_converter: str
    tx1_connector: str
    tx1_converter: str
    tx2_connector: str
    tx2_converter: str

    @field_validator("*")
    @classmethod
    def _non_blank_identifier(cls, value: str) -> str:
        return normalize_cmw_route_token(value, "adapter profile")

    @model_validator(mode="after")
    def _distinct_tx_paths(self):
        if self.tx1_connector == self.tx2_connector:
            raise ValueError("TX1 and TX2 connectors must be distinct")
        if self.tx1_converter == self.tx2_converter:
            raise ValueError("TX1 and TX2 converters must be distinct")
        return self


class BaseStationAdapterProfile(BaseModel):
    """Persisted CMW500 adapter profile stored on InstrumentConnection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    adapter: Literal["cmw500"]
    lte_2x2_internal_route: Cmw500Lte2x2InternalRoute


class BaseStationAdapterProfileResolution(BaseModel):
    """Frozen result of resolving a selected base-station adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    adapter: Literal["uxm", "cmw500"] | None
    status: Literal["configured", "not_applicable", "diagnostic_unbound"]
    execution_mode: Literal["real", "simulated"]
    profile: BaseStationAdapterProfile | None

    @model_validator(mode="after")
    def _valid_combination(self):
        if self.status == "configured":
            if self.adapter != "cmw500" or self.profile is None:
                raise ValueError("configured resolution requires a CMW500 profile")
        elif self.status == "not_applicable":
            if self.adapter != "uxm" or self.profile is not None:
                raise ValueError("not_applicable resolution is UXM-only")
        elif (
            self.adapter is not None
            or self.profile is not None
            or self.execution_mode != "simulated"
        ):
            raise ValueError("diagnostic_unbound is simulated and has no adapter profile")
        return self
