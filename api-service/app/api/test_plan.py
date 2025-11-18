"""Test Plan Management API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.schemas.test_plan import (
    # Test Plan
    TestPlanCreate,
    TestPlanUpdate,
    TestPlanResponse,
    TestPlanSummary,
    TestPlanListResponse,
    # Test Case
    TestCaseCreate,
    TestCaseUpdate,
    TestCaseResponse,
    TestCaseSummary,
    TestCaseListResponse,
    # Test Execution
    TestExecutionResponse,
    TestExecutionListResponse,
    # Queue
    QueueTestPlanRequest,
    TestQueueResponse,
    TestQueueSummary,
    TestQueueListResponse,
    # Control
    StartTestPlanRequest,
    PauseTestPlanRequest,
    ResumeTestPlanRequest,
    CancelTestPlanRequest,
)
from app.services.test_plan_service import (
    TestPlanService,
    TestCaseService,
    TestQueueService,
    TestExecutionService,
)
from app.models.test_plan import TestPlan, TestCase

router = APIRouter(prefix="/test-plans", tags=["Test Plan Management"])


# ==================== Test Plan Endpoints ====================

@router.post("", response_model=TestPlanResponse, status_code=201)
def create_test_plan(
    request: TestPlanCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new test plan

    A test plan is a collection of test cases that will be executed in order.
    """
    service = TestPlanService()
    test_plan = service.create_test_plan(
        db=db,
        name=request.name,
        description=request.description,
        version=request.version,
        created_by=request.created_by,
        dut_info=request.dut_info,
        test_environment=request.test_environment,
        test_case_ids=request.test_case_ids,
        priority=request.priority,
        notes=request.notes,
        tags=request.tags,
    )
    return test_plan


@router.get("", response_model=TestPlanListResponse)
def list_test_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    created_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all test plans with optional filters"""
    try:
        service = TestPlanService()
        test_plans = service.list_test_plans(
            db=db,
            skip=skip,
            limit=limit,
            status=status,
            created_by=created_by
        )

        return TestPlanListResponse(
            total=len(test_plans),
            items=[TestPlanSummary.from_orm(tp) for tp in test_plans]
        )
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for test plans list: {e}")
        return TestPlanListResponse(
            total=0,
            items=[]
        )


# ==================== Queue Management Endpoints ====================

@router.post("/queue", response_model=TestQueueResponse, status_code=201)
def queue_test_plan(
    request: QueueTestPlanRequest,
    db: Session = Depends(get_db)
):
    """
    Add a test plan to the execution queue

    The test plan will be queued for execution based on its priority
    and dependencies.
    """
    service = TestQueueService()

    try:
        queue_item = service.queue_test_plan(
            db=db,
            test_plan_id=request.test_plan_id,
            queued_by=request.queued_by,
            priority=request.priority,
            scheduled_start_time=request.scheduled_start_time,
            dependencies=request.dependencies,
            notes=request.notes,
        )
        return queue_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/queue", response_model=TestQueueListResponse)
def get_test_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get the current test execution queue"""
    try:
        queue_service = TestQueueService()
        plan_service = TestPlanService()

        queue_items = queue_service.get_queue(db, skip, limit)

        # Build response with test plan details
        items = []
        for queue_item in queue_items:
            test_plan = plan_service.get_test_plan(db, queue_item.test_plan_id)
            if test_plan:
                items.append(TestQueueSummary(
                    queue_item=TestQueueResponse.from_orm(queue_item),
                    test_plan=TestPlanSummary.from_orm(test_plan)
                ))

        return TestQueueListResponse(
            total=len(items),
            items=items
        )
    except Exception as e:
        # Database unavailable - return empty queue
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for test queue: {e}")
        return TestQueueListResponse(
            total=0,
            items=[]
        )


@router.delete("/queue/{test_plan_id}", status_code=204)
def remove_from_queue(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Remove a test plan from the execution queue"""
    service = TestQueueService()
    success = service.remove_from_queue(db, test_plan_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Test plan not found in queue"
        )

    return None



@router.get("/{test_plan_id}", response_model=TestPlanResponse)
def get_test_plan(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific test plan by ID"""
    service = TestPlanService()
    test_plan = service.get_test_plan(db, test_plan_id)

    if not test_plan:
        raise HTTPException(status_code=404, detail="Test plan not found")

    return test_plan


@router.patch("/{test_plan_id}", response_model=TestPlanResponse)
def update_test_plan(
    test_plan_id: UUID,
    request: TestPlanUpdate,
    db: Session = Depends(get_db)
):
    """Update a test plan"""
    service = TestPlanService()

    update_data = request.dict(exclude_unset=True)
    test_plan = service.update_test_plan(db, test_plan_id, **update_data)

    if not test_plan:
        raise HTTPException(status_code=404, detail="Test plan not found")

    return test_plan


@router.delete("/{test_plan_id}", status_code=204)
def delete_test_plan(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a test plan"""
    service = TestPlanService()
    success = service.delete_test_plan(db, test_plan_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete test plan (not found or in invalid status)"
        )

    return None


@router.post("/{test_plan_id}/mark-ready", response_model=TestPlanResponse)
def mark_test_plan_ready(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Mark a test plan as ready for execution"""
    service = TestPlanService()

    try:
        test_plan = service.mark_ready(db, test_plan_id)
        if not test_plan:
            raise HTTPException(status_code=404, detail="Test plan not found")
        return test_plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Test Case Endpoints ====================

@router.post("/cases", response_model=TestCaseResponse, status_code=201)
def create_test_case(
    request: TestCaseCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new test case

    Test cases define the configuration for a single test and can be reused
    across multiple test plans.
    """
    service = TestCaseService()
    test_case = service.create_test_case(
        db=db,
        name=request.name,
        description=request.description,
        test_type=request.test_type,
        configuration=request.configuration,
        created_by=request.created_by,
        pass_criteria=request.pass_criteria,
        expected_results=request.expected_results,
        probe_selection=request.probe_selection,
        instrument_config=request.instrument_config,
        channel_model=request.channel_model,
        channel_parameters=request.channel_parameters,
        frequency_mhz=request.frequency_mhz,
        tx_power_dbm=request.tx_power_dbm,
        bandwidth_mhz=request.bandwidth_mhz,
        test_duration_sec=request.test_duration_sec,
        is_template=request.is_template,
        template_category=request.template_category,
        tags=request.tags,
    )
    return test_case


@router.get("/cases", response_model=TestCaseListResponse)
def list_test_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    test_type: Optional[str] = None,
    is_template: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """List all test cases with optional filters"""
    try:
        service = TestCaseService()
        test_cases = service.list_test_cases(
            db=db,
            skip=skip,
            limit=limit,
            test_type=test_type,
            is_template=is_template
        )

        return TestCaseListResponse(
            total=len(test_cases),
            items=[TestCaseSummary.from_orm(tc) for tc in test_cases]
        )
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for test cases list: {e}")
        return TestCaseListResponse(
            total=0,
            items=[]
        )


@router.get("/cases/{test_case_id}", response_model=TestCaseResponse)
def get_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific test case by ID"""
    service = TestCaseService()
    test_case = service.get_test_case(db, test_case_id)

    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")

    return test_case


@router.patch("/cases/{test_case_id}", response_model=TestCaseResponse)
def update_test_case(
    test_case_id: UUID,
    request: TestCaseUpdate,
    db: Session = Depends(get_db)
):
    """Update a test case"""
    service = TestCaseService()

    update_data = request.dict(exclude_unset=True)
    test_case = service.update_test_case(db, test_case_id, **update_data)

    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")

    return test_case


@router.delete("/cases/{test_case_id}", status_code=204)
def delete_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a test case"""
    service = TestCaseService()
    success = service.delete_test_case(db, test_case_id)

    if not success:
        raise HTTPException(status_code=404, detail="Test case not found")

    return None


# ==================== Execution Control Endpoints ====================

@router.post("/{test_plan_id}/start", response_model=TestPlanResponse)
def start_test_plan(
    test_plan_id: UUID,
    request: StartTestPlanRequest,
    db: Session = Depends(get_db)
):
    """
    Start executing a test plan

    This will begin sequential execution of all test cases in the plan.
    """
    service = TestExecutionService()

    try:
        test_plan = service.start_test_plan(
            db=db,
            test_plan_id=test_plan_id,
            started_by=request.started_by
        )
        return test_plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{test_plan_id}/pause", response_model=TestPlanResponse)
def pause_test_plan(
    test_plan_id: UUID,
    request: PauseTestPlanRequest,
    db: Session = Depends(get_db)
):
    """Pause a running test plan"""
    service = TestExecutionService()

    try:
        test_plan = service.pause_test_plan(db, test_plan_id)
        return test_plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{test_plan_id}/resume", response_model=TestPlanResponse)
def resume_test_plan(
    test_plan_id: UUID,
    request: ResumeTestPlanRequest,
    db: Session = Depends(get_db)
):
    """Resume a paused test plan"""
    service = TestExecutionService()

    try:
        test_plan = service.resume_test_plan(db, test_plan_id)
        return test_plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{test_plan_id}/cancel", response_model=TestPlanResponse)
def cancel_test_plan(
    test_plan_id: UUID,
    request: CancelTestPlanRequest,
    db: Session = Depends(get_db)
):
    """Cancel a test plan"""
    service = TestExecutionService()

    try:
        test_plan = service.cancel_test_plan(db, test_plan_id)
        return test_plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{test_plan_id}/complete", response_model=TestPlanResponse)
def complete_test_plan(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Mark a test plan as completed"""
    service = TestExecutionService()

    try:
        test_plan = service.complete_test_plan(db, test_plan_id)
        return test_plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
