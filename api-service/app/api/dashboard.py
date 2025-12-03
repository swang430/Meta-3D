"""Dashboard API endpoints"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

from app.db.database import get_db
from app.models.probe import Probe
from app.models.test_plan import TestPlan, TestPlanStatus, TestExecution
from app.schemas.dashboard import (
    DashboardResponse,
    DashboardSummary,
    LiveMetric,
    ActiveAlert,
    RecentTest
)

router = APIRouter()
logger = logging.getLogger(__name__)


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
        active_test_plans = db.query(TestPlan).filter(
            TestPlan.status.in_([TestPlanStatus.RUNNING, TestPlanStatus.QUEUED])
        ).count()

        summary = DashboardSummary(
            probe_count=probe_count,
            active_test_plans=active_test_plans,
            active_alerts=0,  # TODO: Implement alert system
            comparisons_selected=0  # TODO: Track from user selection
        )

        # Live metrics (mock data for now)
        live_metrics = [
            LiveMetric(label="吞吐量", value="150 Mbps", trend="up"),
            LiveMetric(label="信噪比", value="25.3 dB", trend="stable"),
            LiveMetric(label="静区均匀性", value="±0.8 dB", trend="stable"),
        ]

        # Active alerts (empty for now, TODO: implement alert system)
        active_alerts = []

        # Recent tests (last 10 executions)
        recent_executions = db.query(TestExecution).order_by(
            TestExecution.executed_at.desc()
        ).limit(10).all()

        recent_tests = []
        for execution in recent_executions:
            test_plan = db.query(TestPlan).filter(
                TestPlan.id == execution.test_plan_id
            ).first()

            if test_plan:
                recent_tests.append(RecentTest(
                    id=str(execution.id),
                    plan_name=test_plan.name,
                    status=execution.status,
                    executed_at=execution.executed_at,
                    duration_minutes=execution.duration_sec / 60 if execution.duration_sec else None
                ))

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
                active_test_plans=0,
                active_alerts=0,
                comparisons_selected=0
            ),
            live_metrics=[],
            active_alerts=[],
            recent_tests=[]
        )
