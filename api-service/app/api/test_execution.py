"""Test Execution History API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.db.database import get_db
from app.schemas.test_plan import (
    TestExecutionResponse,
    TestExecutionListResponse,
)
from app.models.test_plan import TestExecution

router = APIRouter(prefix="/test-executions", tags=["Test Execution History"])


@router.get("", response_model=TestExecutionListResponse)
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
    Get execution history with filters

    Filters:
    - test_plan_id: Filter by test plan ID
    - status: Filter by execution status
    - start_date: Filter executions after this date
    - end_date: Filter executions before this date
    """
    try:
        query = db.query(TestExecution)

        # Apply filters
        if test_plan_id:
            query = query.filter(TestExecution.test_plan_id == test_plan_id)
        if status:
            query = query.filter(TestExecution.status == status)
        if start_date:
            query = query.filter(TestExecution.executed_at >= start_date)
        if end_date:
            query = query.filter(TestExecution.executed_at <= end_date)

        # Get total count before pagination
        total = query.count()

        # Apply pagination and order
        executions = query.order_by(
            TestExecution.executed_at.desc()
        ).offset(skip).limit(limit).all()

        return TestExecutionListResponse(
            total=total,
            items=[TestExecutionResponse.from_orm(exe) for exe in executions]
        )
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for execution history: {e}")
        return TestExecutionListResponse(
            total=0,
            items=[]
        )


@router.get("/{record_id}", response_model=TestExecutionResponse)
def get_execution_record(
    record_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a single execution record by ID"""
    execution = db.query(TestExecution).filter(
        TestExecution.id == record_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution record not found")

    return execution


@router.delete("/{record_id}", status_code=204)
def delete_execution_record(
    record_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete an execution record"""
    execution = db.query(TestExecution).filter(
        TestExecution.id == record_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution record not found")

    db.delete(execution)
    db.commit()

    return None
