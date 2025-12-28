"""Test Execution History API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.db.database import get_db
from app.schemas.test_plan import (
    TestPlanExecutionResponse,
    TestPlanExecutionListResponse,
)
from app.models.test_plan import TestPlanExecution

router = APIRouter(prefix="/test-executions", tags=["Test Execution History"])


# Schema for recent tests (matches frontend RecentTest type)
from pydantic import BaseModel
from typing import List


class RecentTestItem(BaseModel):
    id: str
    name: str
    dut: str
    result: str
    date: str


class RecentTestsResponse(BaseModel):
    recentTests: List[RecentTestItem]


@router.get("/recent", response_model=RecentTestsResponse)
def get_recent_tests(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get recent test executions for dashboard display

    Returns a simplified list of recent test executions.
    """
    try:
        executions = db.query(TestPlanExecution).order_by(
            TestPlanExecution.completed_at.desc()
        ).limit(limit).all()

        recent_tests = []
        for exe in executions:
            recent_tests.append(RecentTestItem(
                id=str(exe.id),
                name=exe.test_plan_name or "Unknown Plan",
                dut="DUT-001",  # Placeholder - could be extended to include actual DUT info
                result=exe.status or "unknown",
                date=exe.completed_at.strftime("%Y-%m-%d %H:%M") if exe.completed_at else "N/A"
            ))

        return RecentTestsResponse(recentTests=recent_tests)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error fetching recent tests: {e}")
        return RecentTestsResponse(recentTests=[])


@router.get("", response_model=TestPlanExecutionListResponse)
def get_execution_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    test_plan_id: Optional[UUID] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    Get test plan execution history with filters

    Filters:
    - test_plan_id: Filter by test plan ID
    - status: Filter by execution status (completed, failed, cancelled)
    - start_date: Filter executions after this date
    - end_date: Filter executions before this date
    """
    try:
        query = db.query(TestPlanExecution)

        # Apply filters
        if test_plan_id:
            query = query.filter(TestPlanExecution.test_plan_id == test_plan_id)
        if status:
            query = query.filter(TestPlanExecution.status == status)
        if start_date:
            query = query.filter(TestPlanExecution.completed_at >= start_date)
        if end_date:
            query = query.filter(TestPlanExecution.completed_at <= end_date)

        # Get total count before pagination
        total = query.count()

        # Apply pagination and order
        executions = query.order_by(
            TestPlanExecution.completed_at.desc()
        ).offset(skip).limit(limit).all()

        return TestPlanExecutionListResponse(
            total=total,
            items=[TestPlanExecutionResponse.model_validate(exe) for exe in executions]
        )
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for execution history: {e}")
        return TestPlanExecutionListResponse(
            total=0,
            items=[]
        )


@router.get("/{record_id}", response_model=TestPlanExecutionResponse)
def get_execution_record(
    record_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a single test plan execution record by ID"""
    execution = db.query(TestPlanExecution).filter(
        TestPlanExecution.id == record_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution record not found")

    return execution


@router.delete("/{record_id}", status_code=204)
def delete_execution_record(
    record_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a test plan execution record"""
    execution = db.query(TestPlanExecution).filter(
        TestPlanExecution.id == record_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution record not found")

    db.delete(execution)
    db.commit()

    return None
