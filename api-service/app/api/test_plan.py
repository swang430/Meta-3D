"""Test Plan Management API endpoints"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.schemas.test_plan import (
    TestCaseCreate,
    TestCaseUpdate,
    TestCaseResponse,
    TestCaseSummary,
    TestCaseListResponse,
    TestCaseGroupedResponse,
    TestCaseExecutionPolicyResponse,
    TestCaseExecutionPolicyUpdate,
)
from app.services.test_plan_service import MIMOOTACarrierTruthError, TestCaseService
from app.services.lab_resolution import resolve_lab_profile
from app.models.test_plan import TestCase
from app.services.execution_scpi_evidence import ExecutionScpiEvidence
from app.services.execution_qualification import TestCaseExecutionPolicy

router = APIRouter(prefix="/test-plans", tags=["Test Plan Management"])


def _validate_explicit_lab_profile(db: Session, lab_profile_id: UUID) -> None:
    """新建/换绑只能指向当前活动实验室，避免保存成功后执行才失败。"""
    try:
        resolve_lab_profile(db, lab_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



# ARCH-1 S4b: 计划链已拆除。本文件自此**只服务 /test-plans/cases***
# (用例库 CRUD + S1 的执行正门)。删掉的 28 条计划路由 —— plan CRUD 7 /
# queue 7 / steps 6 / 生命周期 5 / preflight 1 / topology-profile 1 /
# {id}/executions 1 —— 由 test_rule_gates 的 G6 门逐条断言不在路由表里。
#
# ⚠️ 文件名与 router prefix 自此名不副实 (叫 test_plan 却只服务 cases)。
# 改前缀到 /test-cases 要动契约同步四步 + GUI 全量改调用, 是独立工单,
# 不夹带进拆除片 (设计稿 §6)。
# ==================== Test Case Endpoints ====================
# NOTE: /cases routes MUST be registered BEFORE /{test_plan_id}
# to prevent FastAPI from matching "cases" as a UUID path parameter.


@router.put(
    "/cases/{test_case_id}/execution-policy",
    response_model=TestCaseExecutionPolicyResponse,
)
def update_test_case_execution_policy(
    test_case_id: UUID,
    request: TestCaseExecutionPolicyUpdate,
    db: Session = Depends(get_db),
):
    """Audit an explicit Diagnostic/Formal policy without touching case config."""

    test_case = (
        db.query(TestCase)
        .filter(TestCase.id == test_case_id)
        .with_for_update()
        .one_or_none()
    )
    if test_case is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode=request.mode,
        reason=request.reason,
        updated_by=request.updated_by,
        updated_at=datetime.now(timezone.utc),
    )
    test_case.execution_policy = policy.model_dump(mode="json")
    db.commit()
    db.refresh(test_case)
    return TestCaseExecutionPolicyResponse(
        test_case_id=test_case.id,
        policy=policy,
    )

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
    if request.lab_profile_id is not None:
        _validate_explicit_lab_profile(db, request.lab_profile_id)

    service = TestCaseService()
    try:
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
            lab_profile_id=request.lab_profile_id,
            is_template=request.is_template,
            template_category=request.template_category,
            tags=request.tags,
        )
    except MIMOOTACarrierTruthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
            items=[TestCaseSummary.from_case_row(tc) for tc in test_cases]
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
            groups[cat].append(TestCaseSummary.from_case_row(tc))

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
    if "lab_profile_id" in update_data and update_data["lab_profile_id"] is not None:
        current = service.get_test_case(db, test_case_id)
        if not current:
            raise HTTPException(status_code=404, detail="Test case not found")
        if update_data["lab_profile_id"] != current.lab_profile_id:
            _validate_explicit_lab_profile(db, update_data["lab_profile_id"])

    try:
        test_case = service.update_test_case(db, test_case_id, **update_data)
    except MIMOOTACarrierTruthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
    phase_progress: List[dict] = Field(default_factory=list)
    failed_phase: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # P1-47C：仅返回严格模型校验后的脱敏摘要；原始响应仍在 scpi.log。
    scpi_evidence: Optional[
        "ExecutionScpiEvidence"
    ] = None


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

    409 = 已有执行在跑 (全局单飞: 进程内任务表 + DB running 行双判据);
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

    注: 不挂 /test-executions/{id} —— 那条路由查的是计划级历史表
    (TestPlanExecution), 已随 ARCH-1 S4b 删除 (它与列表端点读的不是同一张
    表, id 空间不相交, 是一颗零调用方的雷)。
    """
    from app.models.test_plan import TestExecution

    execution = (
        db.query(TestExecution).filter(TestExecution.id == execution_id).first()
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    cfg = execution.config or {}
    from app.services.execution_scpi_evidence import (
        public_execution_scpi_evidence,
    )

    return CaseExecutionStatusResponse(
        execution_id=execution.id,
        status=execution.status or "unknown",
        source_test_case_id=cfg.get("source_test_case_id"),
        phase_progress=list(cfg.get("phase_progress") or []),
        failed_phase=cfg.get("failed_phase"),
        # 内审 F4: error_message 三个读方同一规则 (列优先 config 兜底,
        # 兜底非串当没有) — 此前本处只读 config, 拿 adhoc 行 (列有值
        # config 无键) 查会返回 null
        error_message=execution.error_message or (
            cfg.get("error_message")
            if isinstance(cfg.get("error_message"), str) else None),
        started_at=execution.started_at.isoformat() if execution.started_at else None,
        completed_at=(
            execution.completed_at.isoformat() if execution.completed_at else None
        ),
        scpi_evidence=public_execution_scpi_evidence(execution),
    )
