"""Dashboard Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import List, Optional
from ._datetime import UTCDateTime
from uuid import UUID


class DashboardSummary(BaseModel):
    """Dashboard summary statistics.

    ARCH-1 S4b: 删掉 active_test_plans / total_executions —— 计划链已拆除,
    这两个字段只能永远是 0, 留着就是在假装。checked-in 契约
    (api/openapi.yaml 的 DashboardResponse) 只声明 systemStatus /
    activeAlerts / liveMetrics, **不含**这两个字段, 所以删它们不触发
    契约同步四步。
    """
    probe_count: int
    active_alerts: int
    comparisons_selected: int


class LiveMetric(BaseModel):
    """Live metric card"""
    label: str
    value: str
    trend: Optional[str] = None  # "up" | "down" | "stable"


class ActiveAlert(BaseModel):
    """Active alert item"""
    id: str
    title: str
    severity: str  # "info" | "warning" | "error" | "critical"
    timestamp: str


class RecentTest(BaseModel):
    """Recent test record"""
    id: str
    plan_name: str
    status: str
    executed_at: UTCDateTime
    duration_minutes: Optional[float]


class DashboardResponse(BaseModel):
    """Complete dashboard response"""
    summary: DashboardSummary
    live_metrics: List[LiveMetric]
    active_alerts: List[ActiveAlert]
    recent_tests: List[RecentTest]


class ComparisonSelectionRequest(BaseModel):
    """Request to track comparison selections"""
    selected_items: List[UUID] = Field(..., min_length=1, description="List of selected item UUIDs")
    comparison_type: str = Field(..., description="Type of comparison (execution_results, reports, etc.)")


class ComparisonSelectionResponse(BaseModel):
    """Response for comparison selection tracking"""
    id: UUID
    selected_items: List[UUID]
    comparison_type: str
    created_at: UTCDateTime
