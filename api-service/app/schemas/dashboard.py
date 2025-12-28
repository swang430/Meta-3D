"""Dashboard Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID


class DashboardSummary(BaseModel):
    """Dashboard summary statistics"""
    probe_count: int
    active_test_plans: int
    active_alerts: int
    comparisons_selected: int
    total_executions: int


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
    executed_at: datetime
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
    created_at: datetime
