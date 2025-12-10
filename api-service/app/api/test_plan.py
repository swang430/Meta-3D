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
    # Test Step
    TestStepCreate,
    TestStepCreateFromSequence,
    TestStepUpdate,
    TestStepResponse,
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
    TestStepService,
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
        scenario_id=request.scenario_id,
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


# ==================== Test Step Endpoints ====================

def _build_step_dict(step):
    """Build step dictionary with all model fields"""
    return {
        "id": step.id,
        "test_plan_id": step.test_plan_id,
        "sequence_library_id": step.sequence_library_id,
        "step_number": step.step_number,
        "order": step.order,
        "name": step.name,
        "description": step.description,
        "type": step.type,
        "parameters": step.parameters,
        "timeout_seconds": step.timeout_seconds,
        "retry_count": step.retry_count,
        "continue_on_failure": step.continue_on_failure,
        "status": step.status,
        "expected_duration_minutes": step.expected_duration_minutes,
        "actual_duration_minutes": step.actual_duration_minutes,
        "started_at": step.started_at,
        "completed_at": step.completed_at,
        "result": step.result,
        "validation_criteria": step.validation_criteria,
        "error_message": step.error_message,
        "notes": step.notes,
        "tags": step.tags,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }


@router.get("/{test_plan_id}/steps", response_model=List[TestStepResponse])
def get_test_steps(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Get all steps for a test plan"""
    from app.models.test_plan import TestSequence

    service = TestStepService()
    steps = service.get_test_steps(db, test_plan_id)

    # Enrich steps with sequence library information
    enriched_steps = []
    for step in steps:
        step_dict = _build_step_dict(step)

        # If step references a sequence library, populate title and category
        if step.sequence_library_id:
            sequence = db.query(TestSequence).filter(
                TestSequence.id == step.sequence_library_id
            ).first()
            if sequence:
                step_dict["title"] = sequence.name
                step_dict["category"] = sequence.category
                if not step.description and sequence.description:
                    step_dict["description"] = sequence.description
        else:
            step_dict["title"] = step.name or f"Step {step.order}"
            step_dict["category"] = step.type or "Unknown"

        enriched_steps.append(step_dict)

    return enriched_steps


@router.post("/{test_plan_id}/steps", response_model=TestStepResponse, status_code=201)
def add_test_step(
    test_plan_id: UUID,
    request: TestStepCreateFromSequence,
    db: Session = Depends(get_db)
):
    """
    Add a test step from sequence library to a test plan

    The step will be created with default parameters from the sequence library,
    which can be customized later.
    """
    from app.models.test_plan import TestSequence

    service = TestStepService()

    try:
        step = service.create_test_step_from_sequence(
            db=db,
            test_plan_id=test_plan_id,
            sequence_library_id=request.sequence_library_id,
            order=request.order,
            parameters=request.parameters,
            timeout_seconds=request.timeout_seconds or 300,
            retry_count=request.retry_count or 0,
            continue_on_failure=request.continue_on_failure or False,
        )

        # Build enriched response
        step_dict = _build_step_dict(step)

        # Populate title and category from sequence
        if step.sequence_library_id:
            sequence = db.query(TestSequence).filter(
                TestSequence.id == step.sequence_library_id
            ).first()
            if sequence:
                step_dict["title"] = sequence.name
                step_dict["category"] = sequence.category

        return step_dict

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{test_plan_id}/steps/{step_id}", response_model=TestStepResponse)
def update_test_step(
    test_plan_id: UUID,
    step_id: UUID,
    request: TestStepUpdate,
    db: Session = Depends(get_db)
):
    """Update a test step"""
    from app.models.test_plan import TestSequence

    service = TestStepService()

    update_data = request.dict(exclude_unset=True)
    step = service.update_test_step(db, step_id, **update_data)

    if not step:
        raise HTTPException(status_code=404, detail="Test step not found")

    # Build enriched response
    step_dict = _build_step_dict(step)

    # Populate title and category from sequence
    if step.sequence_library_id:
        sequence = db.query(TestSequence).filter(
            TestSequence.id == step.sequence_library_id
        ).first()
        if sequence:
            step_dict["title"] = sequence.name
            step_dict["category"] = sequence.category

    return step_dict


@router.delete("/{test_plan_id}/steps/{step_id}", status_code=204)
def delete_test_step(
    test_plan_id: UUID,
    step_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a test step"""
    service = TestStepService()
    success = service.delete_test_step(db, step_id)

    if not success:
        raise HTTPException(status_code=404, detail="Test step not found")

    return None


@router.post("/{test_plan_id}/steps/reorder", status_code=204)
def reorder_test_steps(
    test_plan_id: UUID,
    step_ids: List[UUID],
    db: Session = Depends(get_db)
):
    """Reorder test steps in a plan"""
    service = TestStepService()

    try:
        service.reorder_steps(db, test_plan_id, step_ids)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{test_plan_id}/steps/{step_id}/duplicate", response_model=TestStepResponse, status_code=201)
def duplicate_test_step(
    test_plan_id: UUID,
    step_id: UUID,
    db: Session = Depends(get_db)
):
    """Duplicate a test step"""
    from app.models.test_plan import TestSequence

    service = TestStepService()

    try:
        step = service.duplicate_step(db, step_id)

        # Build enriched response
        step_dict = _build_step_dict(step)

        # Populate title and category from sequence
        if step.sequence_library_id:
            sequence = db.query(TestSequence).filter(
                TestSequence.id == step.sequence_library_id
            ).first()
            if sequence:
                step_dict["title"] = sequence.name
                step_dict["category"] = sequence.category

        return step_dict

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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


# ==================== Test Execution Endpoints ====================

@router.get("/{test_plan_id}/executions", response_model=TestExecutionListResponse)
def get_test_executions(
    test_plan_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Get all test executions for a specific test plan.

    Returns execution records including status, duration, and measurement data.
    Useful for report generation and historical analysis.
    """
    from app.models.test_plan import TestExecution

    try:
        # Verify test plan exists
        plan_service = TestPlanService()
        test_plan = plan_service.get_test_plan(db, test_plan_id)
        if not test_plan:
            raise HTTPException(status_code=404, detail="Test plan not found")

        # Query executions for this test plan
        executions = db.query(TestExecution).filter(
            TestExecution.test_plan_id == test_plan_id
        ).order_by(TestExecution.execution_order.asc()).offset(skip).limit(limit).all()

        return TestExecutionListResponse(
            total=len(executions),
            items=[TestExecutionResponse.model_validate(e) for e in executions]
        )
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error fetching executions for plan {test_plan_id}: {e}")
        return TestExecutionListResponse(total=0, items=[])
