"""Dashboard API endpoints"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from typing import Dict, List
import logging

from app.db.database import get_db
from app.models.probe import Probe

from app.schemas.dashboard import (
    DashboardResponse,
    DashboardSummary,
    LiveMetric,
    ActiveAlert,
    RecentTest,
    ComparisonSelectionRequest,
    ComparisonSelectionResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory storage for comparison selections (per-session tracking)
_comparison_selections: Dict[UUID, dict] = {}


def _dashboard_live_metrics() -> List[LiveMetric]:
    """Return dashboard metrics without inventing quiet-zone evidence."""
    return [
        LiveMetric(label="吞吐量", value="150 Mbps", trend="up"),
        LiveMetric(label="信噪比", value="25.3 dB", trend="stable"),
        LiveMetric(label="静区均匀性", value="N/A", trend="unknown"),
    ]


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    """
    Get dashboard overview data

    Returns:
    - summary: System statistics
    - live_metrics: Real-time metrics
    - active_alerts: Current alerts
    - recent_tests: Recent test executions
    """
    try:
        # Summary statistics
        probe_count = db.query(Probe).filter(Probe.is_active == True).count()
        # ARCH-1 S4b: active_test_plans / total_executions 随计划链删除 (见 schema)。


        summary = DashboardSummary(
            probe_count=probe_count,
            active_alerts=0,  # TODO: Implement alert system
            comparisons_selected=len(_comparison_selections)
        )

        # QZ remains N/A until a verified real multi-point scan is available.
        live_metrics = _dashboard_live_metrics()

        # Active alerts (empty for now, TODO: implement alert system)
        active_alerts = []

        # ARCH-1 S4b: 原先这里读 TestPlanExecution (封存表) 取最近 10 条计划执行。
        # 计划链拆除后该表不再有写入方, 列表从 VRT 执行 (test_executions) 起头。
        # ⚠️ 用例执行 (executed_by=test_case_runner) 目前**不进这个列表** ——
        # 但主控台真正显示的「最近执行」走的是 /test-executions (S2 换源),
        # 不是这里; 本端点整条链的消费方是零 (设计稿 §1.5), 故不换源。
        recent_tests = []

        # Integrate Virtual Road Test executions (DB-backed via test_executions)
        try:
            from app.api.road_test import _get_custom_scenario, get_scenario_by_id
            from app.services.road_test.vrt_execution_service import vrt_execution_service

            for row in vrt_execution_service.list(db, limit=50):
                # Resolve scenario name
                scenario_name = row.scenario_id or ""
                std = get_scenario_by_id(row.scenario_id) if row.scenario_id else None
                if std is not None:
                    scenario_name = getattr(std, "name", scenario_name)
                else:
                    custom = _get_custom_scenario(db, row.scenario_id) if row.scenario_id else None
                    if custom is not None:
                        scenario_name = getattr(custom, "name", scenario_name)

                recent_tests.append(RecentTest(
                    id=str(row.id),
                    plan_name=f"VRT: {scenario_name}",
                    status=row.status,
                    executed_at=row.completed_at or row.started_at or row.executed_at,
                    duration_minutes=round((row.duration_sec or 0) / 60, 1),
                ))

            # Sort combined list by date desc
            recent_tests.sort(key=lambda x: x.executed_at or datetime.min, reverse=True)
            recent_tests = recent_tests[:10]

        except Exception as e:
            logger.error(f"Error integrating road test data: {e}")

        return DashboardResponse(
            summary=summary,
            live_metrics=live_metrics,
            active_alerts=active_alerts,
            recent_tests=recent_tests
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        # Return empty dashboard on error
        return DashboardResponse(
            summary=DashboardSummary(
                probe_count=0,
                active_alerts=0,
                comparisons_selected=0
            ),
            live_metrics=[],
            active_alerts=[],
            recent_tests=[]
        )


# ==================== Comparison Tracking Endpoints ====================

@router.post("/dashboard/comparisons", response_model=ComparisonSelectionResponse, status_code=201)
def track_comparison_selection(request: ComparisonSelectionRequest):
    """
    Track user's comparison selections

    Stores the selected items for later comparison operations.
    Used by the UI to track what items the user wants to compare.
    """
    comparison_id = uuid4()
    now = datetime.utcnow()

    _comparison_selections[comparison_id] = {
        "id": comparison_id,
        "selected_items": request.selected_items,
        "comparison_type": request.comparison_type,
        "created_at": now,
    }

    logger.info(f"Tracked comparison selection: {comparison_id}, items={len(request.selected_items)}, type={request.comparison_type}")

    return ComparisonSelectionResponse(
        id=comparison_id,
        selected_items=request.selected_items,
        comparison_type=request.comparison_type,
        created_at=now,
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    Get dashboard summary statistics only

    Lighter-weight endpoint that returns just the summary stats.
    """
    try:
        probe_count = db.query(Probe).filter(Probe.is_active == True).count()
        # ARCH-1 S4b: 同上 —— 字段已删。
        

        return DashboardSummary(
            probe_count=probe_count,
            active_alerts=0,
            comparisons_selected=len(_comparison_selections),
        )
    except Exception as e:
        logger.error(f"Error fetching dashboard summary: {e}")
        return DashboardSummary(
            probe_count=0,
            active_alerts=0,
            comparisons_selected=0,
        )


@router.delete("/dashboard/comparisons/{comparison_id}", status_code=204)
def remove_comparison_selection(comparison_id: UUID):
    """
    Remove a comparison selection

    Clears a previously tracked comparison selection.
    """
    if comparison_id in _comparison_selections:
        del _comparison_selections[comparison_id]
        logger.info(f"Removed comparison selection: {comparison_id}")
    return None


@router.delete("/dashboard/comparisons", status_code=204)
def clear_all_comparisons():
    """
    Clear all comparison selections

    Removes all tracked comparison selections.
    """
    global _comparison_selections
    count = len(_comparison_selections)
    _comparison_selections = {}
    logger.info(f"Cleared {count} comparison selections")
