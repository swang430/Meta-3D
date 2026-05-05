"""Pydantic schemas for LabProfile (Phase 0)."""
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._datetime import UTCDateTime


class InstrumentBinding(BaseModel):
    """One row of LabProfile.instrument_bindings."""

    category_id: UUID
    instrument_model_id: Optional[UUID] = None
    connection_endpoint: Optional[str] = Field(
        None, description='e.g. "192.168.1.10:5025" or "TCPIP0::INSTR"'
    )
    driver_mode: Optional[str] = Field(
        None, description="auto | mock | real (per-instrument override of HAL_MODE)"
    )
    role: Optional[str] = Field(
        None, description='Free-form role label, e.g. "primary_channel_emulator"'
    )


class LabProfileBase(BaseModel):
    name: str
    description: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    chamber_config_id: Optional[UUID] = None
    active_calibration_certificate_id: Optional[UUID] = None
    instrument_bindings: Optional[List[InstrumentBinding]] = None
    network_config: Optional[Dict[str, Any]] = None
    extra_metadata: Optional[Dict[str, Any]] = None
    is_active: bool = True


class LabProfileCreate(LabProfileBase):
    created_by: Optional[str] = None


class LabProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    chamber_config_id: Optional[UUID] = None
    active_calibration_certificate_id: Optional[UUID] = None
    instrument_bindings: Optional[List[InstrumentBinding]] = None
    network_config: Optional[Dict[str, Any]] = None
    extra_metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class LabProfileResponse(LabProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: UTCDateTime
    updated_at: Optional[UTCDateTime] = None
    created_by: Optional[str] = None
