"""Pydantic schemas for API request/response models"""
from app.schemas.report import (
    # Report
    ReportCreate,
    ReportUpdate,
    ReportResponse,
    ReportSummary,
    ReportDownloadResponse,
    ReportListResponse,
    # Template
    ReportTemplateCreate,
    ReportTemplateUpdate,
    ReportTemplateResponse,
    ReportTemplateSummary,
    TemplateListResponse,
    # Comparison
    ReportComparisonCreate,
    ReportComparisonResponse,
    ComparisonListResponse,
    # Schedule
    ReportScheduleCreate,
    ReportScheduleUpdate,
    ReportScheduleResponse,
    ScheduleListResponse,
)

__all__ = [
    # Report
    "ReportCreate",
    "ReportUpdate",
    "ReportResponse",
    "ReportSummary",
    "ReportDownloadResponse",
    "ReportListResponse",
    # Template
    "ReportTemplateCreate",
    "ReportTemplateUpdate",
    "ReportTemplateResponse",
    "ReportTemplateSummary",
    "TemplateListResponse",
    # Comparison
    "ReportComparisonCreate",
    "ReportComparisonResponse",
    "ComparisonListResponse",
    # Schedule
    "ReportScheduleCreate",
    "ReportScheduleUpdate",
    "ReportScheduleResponse",
    "ScheduleListResponse",
]
