"""Alert Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertCreate(BaseModel):
    """Request to create an alert"""
    title: Optional[str] = Field(None, max_length=255, description="Alert title")
    message: str = Field(..., description="Alert message")
    type: Optional[str] = Field("warning", description="Alert type (warning, error, info, critical)")
    source: Optional[str] = Field(None, description="Source system/component")
    related_entity_type: Optional[str] = Field(None, description="Related entity type")
    related_entity_id: Optional[UUID] = Field(None, description="Related entity UUID")


class AlertUpdate(BaseModel):
    """Request to update an alert"""
    status: Optional[AlertStatus] = None
    is_read: Optional[bool] = None


class AlertResponse(BaseModel):
    """Alert response"""
    id: UUID
    title: str
    message: Optional[str]
    severity: str
    alert_type: Optional[str]
    source: Optional[str]
    status: str
    is_read: bool
    related_entity_type: Optional[str]
    related_entity_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    created_by: Optional[str]
    acknowledged_by: Optional[str]

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    """List of alerts response"""
    total: int
    alerts: List[AlertResponse]


class AlertSummary(BaseModel):
    """Alert summary for dashboard"""
    total_active: int
    info_count: int
    warning_count: int
    error_count: int
    critical_count: int
