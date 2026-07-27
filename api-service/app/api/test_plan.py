"""Test Plan Management API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.auth import require_auth, User
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
    TestCaseGroupedResponse,
    # Test Step
    TestStepCreate,
    TestStepCreateFromTestCase,
    TestStepUpdate,
    TestStepResponse,
    # Test Execution
    TestExecutionResponse,
    TestExecutionListResponse,
    # Queue
    QueueTestPlanRequest,
    QueueItemUpdateRequest,
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
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(require_auth())
):
    """
    Create a new test plan

    A test plan is a collection of test cases that will be executed in order.

    Authentication:
    - If AUTH_MODE=required: Valid JWT token required
    - If AUTH_MODE=optional: Token validated if present, `created_by` field required if no token
    - If AUTH_MODE=disabled: No authentication required
    """
    # Determine created_by: prefer request.created_by, fall back to authenticated user
    created_by = request.created_by
    if created_by is None:
        if current_user is not None:
            created_by = current_user.email
        else:
            raise HTTPException(
                status_code=401,
                detail="Authentication required when created_by is not provided"
            )

    service = TestPlanService()
    test_plan = service.create_test_plan(
        db=db,
        name=request.name,
        description=request.description,
        version=request.version,
        created_by=created_by,
        dut_info=request.dut_info,
        test_environment=request.test_environment,
        scenario_id=request.scenario_id,
        test_case_ids=request.test_case_ids,
        priority=request.priority,
        notes=request.notes,
        tags=request.tags,
        # P2-1 Phase 2.3: optional plan-level UXM topology override.
        topology_profile_id=request.topology_profile_id,
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


# IMPORTANT: Static routes must be defined BEFORE parameterized routes
class ReorderQueueRequest(BaseModel):
    """Request to reorder queue item"""
    planId: str
    direction: str  # 'up' | 'down' | 'top' | 'bottom'


@router.post("/queue/reorder")
def reorder_queue_item(
    request: ReorderQueueRequest,
    db: Session = Depends(get_db)
):
    """
    Reorder a test plan in the execution queue

    - direction: 'up', 'down', 'top', or 'bottom'
    """
    queue_service = TestQueueService()

    try:
        plan_id = UUID(request.planId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plan ID format")

    try:
        if request.direction == 'up':
            queue_item = queue_service.move_queue_item_up(db, plan_id)
        elif request.direction == 'down':
            queue_item = queue_service.move_queue_item_down(db, plan_id)
        elif request.direction == 'top':
            queue_item = queue_service.move_to_top(db, plan_id)
        elif request.direction == 'bottom':
            queue_item = queue_service.move_to_bottom(db, plan_id)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid direction: {request.direction}")

        return {"success": True, "new_position": queue_item.position}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


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


@router.post("/queue/{test_plan_id}/move-up", response_model=TestQueueResponse)
def move_queue_item_up(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Move a test plan up in the execution queue (earlier execution)

    Swaps position with the item above it.
    """
    service = TestQueueService()
    try:
        queue_item = service.move_queue_item_up(db, test_plan_id)
        return queue_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/queue/{test_plan_id}/move-down", response_model=TestQueueResponse)
def move_queue_item_down(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Move a test plan down in the execution queue (later execution)

    Swaps position with the item below it.
    """
    service = TestQueueService()
    try:
        queue_item = service.move_queue_item_down(db, test_plan_id)
        return queue_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/queue/{test_plan_id}", response_model=TestQueueResponse)
def update_queue_item(
    test_plan_id: UUID,
    request: QueueItemUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update a queue item's priority or position

    - priority: Set new priority (1=highest, 10=lowest)
    - position: Move to specific position in queue
    """
    service = TestQueueService()

    # Get the queue item
    queue_item = service.get_queue_item_by_test_plan(db, test_plan_id)
    if not queue_item:
        raise HTTPException(
            status_code=404,
            detail="Test plan not found in queue"
        )

    try:
        # Update priority if provided
        if request.priority is not None:
            queue_item = service.update_queue_priority(db, queue_item.id, request.priority)

        return queue_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Test Case Endpoints ====================
# NOTE: /cases routes MUST be registered BEFORE /{test_plan_id}
# to prevent FastAPI from matching "cases" as a UUID path parameter.

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
    category: Optional[str] = None,
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
            is_template=is_template,
            template_category=category
        )

        return TestCaseListResponse(
            total=len(test_cases),
            items=[TestCaseSummary.from_orm(tc) for tc in test_cases]
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for test cases list: {e}")
        return TestCaseListResponse(
            total=0,
            items=[]
        )


@router.get("/cases/grouped", response_model=TestCaseGroupedResponse)
def list_test_cases_grouped(
    is_template: Optional[bool] = True,
    db: Session = Depends(get_db)
):
    """
    Get test cases grouped by template_category.
    Designed for the TestCaseLibrary UI component.
    """
    try:
        service = TestCaseService()
        test_cases = service.list_test_cases(
            db=db, skip=0, limit=500,
            is_template=is_template
        )

        groups: dict = {}
        for tc in test_cases:
            cat = tc.template_category or "未分类"
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(TestCaseSummary.from_orm(tc))

        return TestCaseGroupedResponse(
            categories=list(groups.keys()),
            groups=groups
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Database unavailable: {e}")
        return TestCaseGroupedResponse(categories=[], groups={})


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


# ==================== ARCH-1 S1: TestCase 直接执行 ====================
# 正式测试执行正门 (设计稿 docs/design/arch-1-testcase-first-simplification.md
# §2.3): 用例库点执行 → case-runner (5 相位链, 与暗室首测同一套 executors)。
# 路径挂在现有 /test-plans/cases 组下 — URL 前缀重构是另一件事 (设计稿 §4)。


class CaseExecuteResponse(BaseModel):
    execution_id: UUID
    snapshot_test_case_id: UUID
    source_test_case_id: UUID
    status: str


class CaseExecutionStatusResponse(BaseModel):
    execution_id: UUID
    status: str
    source_test_case_id: Optional[str] = None
    phase_progress: List[dict] = []
    failed_phase: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.post(
    "/cases/{test_case_id}/execute",
    response_model=CaseExecuteResponse,
    status_code=202,
)
async def execute_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db),
):
    """TestCase 直接执行: 快照参数 → 后台 5 相位链。

    409 = 已有执行在跑 (全局单飞, 含与计划 runner 互斥);
    422 = 用例类型不支持 / 参数无法构成有效配置; 404 = 用例不存在。
    进度轮询 GET /test-plans/cases/executions/{execution_id}。
    """
    from app.services.test_case_runner import (
        CaseNotExecutable,
        CaseRunBusy,
        launch_test_case_execution,
    )

    try:
        execution = launch_test_case_execution(db, test_case_id)
    except CaseRunBusy as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CaseNotExecutable as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return CaseExecuteResponse(
        execution_id=execution.id,
        snapshot_test_case_id=execution.test_case_id,
        source_test_case_id=test_case_id,
        status=execution.status,
    )


@router.get(
    "/cases/executions/{execution_id}",
    response_model=CaseExecutionStatusResponse,
)
def get_case_execution_status(
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """执行状态轮询 (GUI 用)。

    注: 不挂 /test-executions/{id} — 那条现有路由查的是计划级历史表
    (TestPlanExecution), S2 统一历史数据源时一并收口。
    """
    from app.models.test_plan import TestExecution

    execution = (
        db.query(TestExecution).filter(TestExecution.id == execution_id).first()
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    cfg = execution.config or {}
    return CaseExecutionStatusResponse(
        execution_id=execution.id,
        status=execution.status or "unknown",
        source_test_case_id=cfg.get("source_test_case_id"),
        phase_progress=list(cfg.get("phase_progress") or []),
        failed_phase=cfg.get("failed_phase"),
        error_message=cfg.get("error_message"),
        started_at=execution.started_at.isoformat() if execution.started_at else None,
        completed_at=(
            execution.completed_at.isoformat() if execution.completed_at else None
        ),
    )


# ==================== Test Plan Instance Endpoints ====================

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


@router.post("/{test_plan_id}/duplicate", response_model=TestPlanResponse, status_code=201)
def duplicate_test_plan(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Duplicate a test plan with all its steps"""
    service = TestPlanService()

    try:
        new_plan = service.duplicate_test_plan(db, test_plan_id)
        return new_plan
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


# ==================== Pre-flight (P1-1) ====================
#
# Capability gap check the operator runs from the GUI's "预检" button
# (PR B) before kicking off a plan. Reads each step's `needs: List[str]`
# (added in same PR) and compares against the union of capabilities
# exposed by HAL-loaded drivers (from P2-2's `driver.capabilities` set).
#
# Endpoint deliberately requires `lab_profile_id` as a query parameter
# rather than auto-resolving "the single active lab" — the commissioning
# factory's magic auto-resolve produced a 500 storm during P2-2 smoke
# (see roadmap "Discovered during P2-2" backlog entry). This endpoint
# fails loudly with 422 if the caller didn't pass a lab, so the GUI
# is forced to specify one explicitly.

class PreflightGapResponse(BaseModel):
    step_id: UUID
    step_name: str
    step_order: int
    missing_token: str
    reason: str


class DriverMismatchResponse(BaseModel):
    """A bound category has a driver loaded for a DIFFERENT unit than
    this lab binds (different endpoint). Operator remedy is "reload
    HAL with this lab's config" or "fix the binding endpoint" — distinct
    from `not_loaded_categories` ("driver isn't up at all")."""
    category: str
    expected_endpoint: str
    loaded_endpoint: str


class BoundModelDeclarationResponse(BaseModel):
    """P3-3: per-binding STATIC capability declaration read off
    ``DriverClass.model_capabilities`` (P2-3). Independent of HAL load
    state — answers "what does the model claim it CAN expose?" without
    needing to connect. GUI shows alongside live ``lab_capabilities``
    so the operator can decide at binding-edit time."""
    category: str
    model_name: str | None
    model_capabilities: List[str]


class PreflightResultResponse(BaseModel):
    plan_id: UUID
    lab_profile_id: UUID
    ready: bool
    gaps: List[PreflightGapResponse]
    unknown_tokens: List[str]  # tokens in step.needs not in KNOWN_CAPABILITIES (typo warnings)
    lab_capabilities: List[str]  # sorted union of tokens exposed by drivers SCOPED per-binding to this lab (LIVE)
    not_loaded_categories: List[str]  # categories the lab binds but HAL hasn't loaded — usually "reload HAL"
    mismatched_drivers: List[DriverMismatchResponse]  # driver loaded for wrong unit (endpoint mismatch)
    bound_models: List[BoundModelDeclarationResponse]  # P3-3: per-binding STATIC declaration (catalog-time, pre-HAL)


@router.post(
    "/{test_plan_id}/preflight",
    response_model=PreflightResultResponse,
)
def preflight_test_plan(
    test_plan_id: UUID,
    lab_profile_id: UUID = Query(
        ..., description="LabProfile to validate against. Required — no magic auto-resolve.",
    ),
    db: Session = Depends(get_db),
):
    """Validate a plan's step capability requirements against a lab's
    bound drivers. Returns a typed gap list so the GUI can render
    actionable warnings before the operator hits Run.
    """
    from app.models.lab_profile import LabProfile
    from app.services.instrument_hal_service import get_hal_service
    from app.services.preflight import validate_plan

    plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail=f"TestPlan {test_plan_id} not found")

    lab = db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
    if lab is None:
        raise HTTPException(
            status_code=422,
            detail=f"LabProfile {lab_profile_id} not found — check the id "
                   f"passed in the query string.",
        )

    hal = get_hal_service()
    result = validate_plan(plan, lab, db, hal.drivers)

    return PreflightResultResponse(
        plan_id=result.plan_id,
        lab_profile_id=result.lab_profile_id,
        ready=result.ready,
        gaps=[
            PreflightGapResponse(
                step_id=g.step_id,
                step_name=g.step_name,
                step_order=g.step_order,
                missing_token=g.missing_token,
                reason=g.reason,
            )
            for g in result.gaps
        ],
        unknown_tokens=result.unknown_tokens,
        lab_capabilities=result.lab_capabilities,
        not_loaded_categories=result.not_loaded_categories,
        mismatched_drivers=[
            DriverMismatchResponse(
                category=m.category,
                expected_endpoint=m.expected_endpoint,
                loaded_endpoint=m.loaded_endpoint,
            )
            for m in result.mismatched_drivers
        ],
        bound_models=[
            BoundModelDeclarationResponse(
                category=b.category,
                model_name=b.model_name,
                model_capabilities=b.model_capabilities,
            )
            for b in result.bound_models
        ],
    )


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
    request: TestStepCreateFromTestCase,
    db: Session = Depends(get_db)
):
    """
    Add a test step from TestCase to a test plan

    The step will be created with default parameters from the TestCase template,
    which can be customized later.
    """
    from app.models.test_plan import TestCase, TestStep, TestPlan

    try:
        # Verify test plan exists
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise HTTPException(status_code=404, detail="Test plan not found")

        # Get TestCase
        test_case = db.query(TestCase).filter(TestCase.id == request.test_case_id).first()
        if not test_case:
            raise HTTPException(status_code=404, detail="Test case not found")

        # Create step
        step = TestStep(
            test_plan_id=test_plan_id,
            order=request.order,
            name=test_case.name,
            description=test_case.description,
            type=test_case.test_type,
            parameters=request.parameters or test_case.configuration or {},
            timeout_seconds=request.timeout_seconds or int(test_case.test_duration_sec) if test_case.test_duration_sec else 300,
            expected_duration_minutes=(test_case.test_duration_sec / 60.0) if test_case.test_duration_sec else None,
            retry_count=request.retry_count or 0,
            continue_on_failure=request.continue_on_failure or False,
            status="pending"
        )
        
        db.add(step)
        db.commit()
        db.refresh(step)

        # Build response
        step_dict = _build_step_dict(step)
        step_dict["title"] = step.name
        step_dict["category"] = step.type

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
async def start_test_plan(
    test_plan_id: UUID,
    request: StartTestPlanRequest,
    db: Session = Depends(get_db)
):
    """
    Start executing a test plan.

    This transitions the plan to RUNNING and (P2-1 Phase 2.3) applies
    the optional plan-level topology profile to the live baseStation
    driver in a best-effort follow-up step. Topology apply failures are
    logged but don't fail the start — the plan is already RUNNING by
    the time we attempt the apply, and operators may want the run to
    proceed even if the UXM topology can't switch (e.g. testing other
    instruments, mock mode).
    """
    service = TestExecutionService()

    # 门审 #217 F8 + Codex #217 P2: 全局单飞 — 有任一计划在执行, 拒绝再
    # start (双 5 相位链交错打同一套 HAL = 实验互相污染)。双重判据:
    # ① 内存活跃 runner; ② DB 里存在其它 RUNNING 计划 — 堵住"置 RUNNING
    # 后、runner 注册前"的 await 窗口 (topology apply 让出事件循环时, 并发
    # start 只查 ① 会漏)。stale RUNNING 由启动复位清理, 正常运行时
    # DB RUNNING ⇔ 真在执行。
    from app.models.test_plan import TestPlanStatus as _TPS
    from app.services.test_plan_runner import has_active_runner
    _active = has_active_runner()
    if _active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"另一测试计划 ({_active}) 正在执行 — 等它结束或先取消它",
        )
    # ARCH-1 S1 (agent F1): 互斥要双向 — 用例执行在跑时计划同样拒绝,
    # 否则双 5 相位链并发打同一套 HAL (case-runner 只挡了 case→plan 半边)。
    from app.services.test_case_runner import has_active_case_run
    _active_case = has_active_case_run()
    if _active_case is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"已有用例执行在跑 (execution {_active_case}) — "
                "等它结束或先取消它"
            ),
        )
    _running_row = (
        db.query(TestPlan)
        .filter(
            TestPlan.status == _TPS.RUNNING,
            TestPlan.id != test_plan_id,
        )
        .first()
    )
    if _running_row is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"另一测试计划 ({_running_row.id}) 状态为执行中 — "
                "等它结束或先取消它"
            ),
        )

    try:
        test_plan = service.start_test_plan(
            db=db,
            test_plan_id=test_plan_id,
            started_by=request.started_by
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # P2-1 Phase 2.3: apply plan-level topology override if set. Result is
    # logged for operator audit (visible via the audit log + uvicorn
    # stdout) but does NOT shape the response body — the plan IS started
    # regardless. Future GUI work may surface the result via a separate
    # status endpoint; today the operator sees it in the readiness panel
    # after the apply landed.
    await service.apply_plan_topology_profile_if_set(db, test_plan)

    # 开关 3 (2026-07-20): 计划 runner — 此前 start 只翻状态, 步骤永停
    # pending; 现在后台真执行 (逐 MIMO_OTA 步骤跑 5 相位链, 状态实时推进,
    # 收尾自动历史+报告)。立即返回, GUI 轮询步骤/计划状态看进度。
    from app.services.test_plan_runner import launch_test_plan_runner
    launch_test_plan_runner(test_plan_id)
    return test_plan


# P2-1 Phase 2.3: dedicated set/clear endpoint for plan-level topology
# override. Mirrors `PUT /instruments/{cat}/topology-profile` shape
# (binding-level) so the GUI uses the same Pydantic shape for both
# scope levels. Distinct from the generic `PATCH /{id}` update because
# that endpoint's existing `if value is not None` filter blocks the
# clear-by-explicit-null path; touching that filter for one field
# would be opportunistic — out-of-scope for Phase 2.3 per project
# governance rule #4 ("严禁顺手优化").

class SetPlanTopologyProfileRequest(BaseModel):
    """Payload for PUT /test-plans/{id}/topology-profile.

    ``profile_id=null`` clears the override (plan falls back to
    binding-level at next start). ``profile_id="..."`` validates the
    profile exists then persists. Validation source is
    ``topology_profile_service`` (DB) with in-code fallback for
    greenfield first-boot.
    """
    profile_id: Optional[str] = None


class SetPlanTopologyProfileResult(BaseModel):
    """Response for PUT /test-plans/{id}/topology-profile."""
    persisted: bool
    profile_id: Optional[str]


@router.put(
    "/{test_plan_id}/topology-profile",
    response_model=SetPlanTopologyProfileResult,
    responses={
        404: {"description": "Plan or profile_id not found"},
    },
)
def set_plan_topology_profile_endpoint(
    test_plan_id: UUID,
    request: SetPlanTopologyProfileRequest,
    db: Session = Depends(get_db),
) -> SetPlanTopologyProfileResult:
    """P2-1 Phase 2.3: set or clear the plan-level UXM topology override.

    The override is applied to the live baseStation driver in a
    best-effort step inside ``POST /{id}/start`` (not here). This
    endpoint only persists the operator's intent — no driver SCPI is
    issued at the moment of PUT.
    """
    from app.models.test_plan import TestPlan as TestPlanModel

    plan = (
        db.query(TestPlanModel)
        .filter(TestPlanModel.id == test_plan_id)
        .first()
    )
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"Test plan {test_plan_id} not found",
        )

    profile_id = request.profile_id
    if profile_id is not None:
        # Validate it exists somewhere — DB first, then in-code fallback
        # (same precedence as HAL service post-connect + binding-level
        # PUT). Operator-visible 404 with available IDs so they can
        # pick a real one.
        from app.services.topology_profile_service import (
            TopologyProfileNotFound, get_dataclass, list_rows,
        )
        try:
            get_dataclass(db, profile_id)
        except TopologyProfileNotFound:
            from app.hal.uxm_test_profiles import (
                _PROFILE_REGISTRY, _register_builtin_profiles,
            )
            if not _PROFILE_REGISTRY:
                _register_builtin_profiles()
            if profile_id not in _PROFILE_REGISTRY:
                db_ids = [r.profile_id for r in list_rows(db)]
                available = sorted(set(db_ids) | set(_PROFILE_REGISTRY.keys()))
                raise HTTPException(
                    status_code=404,
                    detail=f"Topology profile {profile_id!r} not found. "
                           f"Available: {available}",
                )

    plan.topology_profile_id = profile_id
    db.commit()
    return SetPlanTopologyProfileResult(
        persisted=True, profile_id=profile_id,
    )


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
async def resume_test_plan(
    test_plan_id: UUID,
    request: ResumeTestPlanRequest,
    db: Session = Depends(get_db)
):
    """Resume a paused test plan (开关 3: async — runner 触发需在事件循环内)"""
    service = TestExecutionService()

    # 门审 #217 F8 + Codex #217 P2: 全局单飞 (同 start, 双重判据)
    from app.models.test_plan import TestPlanStatus as _TPS
    from app.services.test_plan_runner import (
        has_active_runner,
        launch_test_plan_runner,
    )
    _active = has_active_runner()
    if _active is not None and _active != str(test_plan_id):
        raise HTTPException(
            status_code=409,
            detail=f"另一测试计划 ({_active}) 正在执行 — 等它结束或先取消它",
        )
    # ARCH-1 S1 (agent F1): 与 start 同 — 用例执行在跑时 resume 也拒绝
    from app.services.test_case_runner import has_active_case_run
    _active_case = has_active_case_run()
    if _active_case is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"已有用例执行在跑 (execution {_active_case}) — "
                "等它结束或先取消它"
            ),
        )
    _running_row = (
        db.query(TestPlan)
        .filter(
            TestPlan.status == _TPS.RUNNING,
            TestPlan.id != test_plan_id,
        )
        .first()
    )
    if _running_row is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"另一测试计划 ({_running_row.id}) 状态为执行中 — "
                "等它结束或先取消它"
            ),
        )

    try:
        test_plan = service.resume_test_plan(db, test_plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 门审 #217 F10: 续跑段测量日志归档精度 — 与 start 路径同样绑定
    # session 上下文 (contextvar 由 create_task 继承)
    from app.core.logging_config import current_session_id
    current_session_id.set(str(test_plan_id))

    # 开关 3: 恢复后重新触发 runner — 续跑跳过非 pending 步骤
    launch_test_plan_runner(test_plan_id)
    return test_plan


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
