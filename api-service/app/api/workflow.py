"""
Workflow API Endpoints

REST API for calibration workflow management.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.workflow import (
    ExecuteWorkflowRequest,
    ParseWorkflowRequest,
    ParseWorkflowResponse,
    PredefinedWorkflowInfo,
    PredefinedWorkflowListResponse,
    WorkflowDefinitionSchema,
    WorkflowExecutionResponse,
    WorkflowExecutionListResponse,
    WorkflowExecutionListItem,
    WorkflowStepSchema,
    WorkflowSettingsSchema,
    StepResultSchema,
    StepStatusEnum,
    WorkflowStatusEnum,
)
from app.services.workflow_engine import (
    WorkflowParser,
    WorkflowExecutor,
    get_predefined_workflows,
    WorkflowStatus,
    StepStatus,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])

# In-memory storage for executions (in production, use database)
_executions = {}


def _convert_step_to_schema(step) -> WorkflowStepSchema:
    """Convert internal step to schema"""
    return WorkflowStepSchema(
        id=step.id,
        type=step.type.value,
        calibration_type=step.calibration_type,
        parameters=step.parameters,
        depends_on=step.depends_on,
        parallel_with=step.parallel_with,
        on_failure=step.on_failure.value,
        retry_count=step.retry_count,
        timeout_seconds=step.timeout_seconds,
        description=step.description,
    )


def _convert_result_to_schema(result) -> StepResultSchema:
    """Convert internal step result to schema"""
    return StepResultSchema(
        step_id=result.step_id,
        status=StepStatusEnum(result.status.value),
        started_at=result.started_at,
        completed_at=result.completed_at,
        calibration_id=result.calibration_id,
        validation_pass=result.validation_pass,
        error_message=result.error_message,
        retry_count=result.retry_count,
        output=result.output,
    )


def _execution_to_response(execution) -> WorkflowExecutionResponse:
    """Convert internal execution to response schema"""
    return WorkflowExecutionResponse(
        id=execution.id,
        workflow_name=execution.workflow.name,
        status=WorkflowStatusEnum(execution.status.value),
        progress_percent=execution.progress_percent,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        current_step_index=execution.current_step_index,
        total_steps=len(execution.workflow.steps),
        passed_steps=execution.passed_steps,
        failed_steps=execution.failed_steps,
        session_id=execution.session_id,
        error_message=execution.error_message,
        step_results={
            step_id: _convert_result_to_schema(result)
            for step_id, result in execution.step_results.items()
        },
    )


# ==================== Predefined Workflows ====================

@router.get("/predefined", response_model=PredefinedWorkflowListResponse)
async def list_predefined_workflows():
    """
    列出所有预定义工作流

    返回系统内置的校准工作流列表，包括完整校准和快速验证流程。
    """
    predefined = get_predefined_workflows()

    workflows = []
    for workflow_id, workflow in predefined.items():
        # Estimate duration based on step count
        step_count = len(workflow.steps)
        estimated_duration = step_count * 10.0  # ~10 min per step

        workflows.append(PredefinedWorkflowInfo(
            id=workflow_id,
            name=workflow.name,
            description=workflow.description,
            version=workflow.version,
            step_count=step_count,
            estimated_duration_minutes=estimated_duration,
        ))

    return PredefinedWorkflowListResponse(
        workflows=workflows,
        total=len(workflows),
    )


@router.get("/predefined/{workflow_id}", response_model=WorkflowDefinitionSchema)
async def get_predefined_workflow(workflow_id: str):
    """
    获取预定义工作流详情

    返回指定工作流的完整定义，包括所有步骤和参数。
    """
    predefined = get_predefined_workflows()

    if workflow_id not in predefined:
        raise HTTPException(
            status_code=404,
            detail=f"Predefined workflow not found: {workflow_id}"
        )

    workflow = predefined[workflow_id]

    return WorkflowDefinitionSchema(
        name=workflow.name,
        version=workflow.version,
        description=workflow.description,
        settings=WorkflowSettingsSchema(
            retry_count=workflow.retry_count,
            retry_delay_seconds=workflow.retry_delay_seconds,
            stop_on_failure=workflow.stop_on_failure,
            notification=workflow.settings.get("notification"),
        ),
        parameters=workflow.parameters,
        steps=[_convert_step_to_schema(step) for step in workflow.steps],
    )


@router.get("/predefined/{workflow_id}/yaml")
async def get_predefined_workflow_yaml(workflow_id: str):
    """
    获取预定义工作流的 YAML 内容

    返回工作流的 YAML 格式，可用于自定义修改。
    """
    predefined = get_predefined_workflows()

    if workflow_id not in predefined:
        raise HTTPException(
            status_code=404,
            detail=f"Predefined workflow not found: {workflow_id}"
        )

    workflow = predefined[workflow_id]
    yaml_content = WorkflowParser.to_yaml(workflow)

    return {"workflow_id": workflow_id, "yaml_content": yaml_content}


# ==================== Parse/Validate ====================

@router.post("/parse", response_model=ParseWorkflowResponse)
async def parse_workflow(request: ParseWorkflowRequest):
    """
    解析并验证工作流 YAML

    验证 YAML 语法和工作流结构，返回解析后的工作流定义。
    """
    try:
        workflow = WorkflowParser.parse_string(request.yaml_content)

        return ParseWorkflowResponse(
            valid=True,
            workflow=WorkflowDefinitionSchema(
                name=workflow.name,
                version=workflow.version,
                description=workflow.description,
                settings=WorkflowSettingsSchema(
                    retry_count=workflow.retry_count,
                    retry_delay_seconds=workflow.retry_delay_seconds,
                    stop_on_failure=workflow.stop_on_failure,
                    notification=workflow.settings.get("notification"),
                ),
                parameters=workflow.parameters,
                steps=[_convert_step_to_schema(step) for step in workflow.steps],
            ),
            error_message=None,
        )
    except Exception as e:
        return ParseWorkflowResponse(
            valid=False,
            workflow=None,
            error_message=str(e),
        )


# ==================== Execute Workflows ====================

@router.post("/execute", response_model=WorkflowExecutionResponse, status_code=202)
async def execute_workflow(
    request: ExecuteWorkflowRequest,
    db: Session = Depends(get_db)
):
    """
    执行校准工作流

    **执行方式**:
    1. 使用预定义工作流: 提供 `workflow_id`
    2. 自定义工作流: 提供 `yaml_content`

    **参数覆盖**:
    使用 `parameter_overrides` 覆盖工作流的默认参数。

    **执行过程**:
    - 创建校准会话
    - 按顺序执行工作流步骤
    - 支持依赖关系和重试
    - 返回执行状态和结果
    """
    # Get or parse workflow
    if request.workflow_id:
        predefined = get_predefined_workflows()
        if request.workflow_id not in predefined:
            raise HTTPException(
                status_code=404,
                detail=f"Predefined workflow not found: {request.workflow_id}"
            )
        workflow = predefined[request.workflow_id]
    elif request.yaml_content:
        try:
            workflow = WorkflowParser.parse_string(request.yaml_content)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid workflow YAML: {str(e)}"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either workflow_id or yaml_content"
        )

    # Apply parameter overrides
    if request.parameter_overrides:
        workflow.parameters.update(request.parameter_overrides)

    # Create and run execution
    executor = WorkflowExecutor(db)
    execution = executor.create_execution(workflow)

    # Store for later retrieval
    _executions[execution.id] = execution

    # Run synchronously (in production, use background task)
    execution = executor.run(execution)
    _executions[execution.id] = execution

    return _execution_to_response(execution)


@router.get("/executions", response_model=WorkflowExecutionListResponse)
async def list_executions(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    列出工作流执行记录
    """
    executions = list(_executions.values())

    # Filter by status
    if status:
        executions = [e for e in executions if e.status.value == status]

    # Sort by start time (newest first)
    executions.sort(key=lambda e: e.started_at or "", reverse=True)

    # Paginate
    total = len(executions)
    executions = executions[offset:offset + limit]

    items = [
        WorkflowExecutionListItem(
            id=e.id,
            workflow_name=e.workflow.name,
            status=WorkflowStatusEnum(e.status.value),
            progress_percent=e.progress_percent,
            started_at=e.started_at,
            completed_at=e.completed_at,
            passed_steps=e.passed_steps,
            failed_steps=e.failed_steps,
            total_steps=len(e.workflow.steps),
        )
        for e in executions
    ]

    return WorkflowExecutionListResponse(executions=items, total=total)


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_execution(execution_id: str):
    """
    获取工作流执行详情
    """
    if execution_id not in _executions:
        raise HTTPException(
            status_code=404,
            detail=f"Execution not found: {execution_id}"
        )

    execution = _executions[execution_id]
    return _execution_to_response(execution)


@router.post("/executions/{execution_id}/cancel", response_model=WorkflowExecutionResponse)
async def cancel_execution(execution_id: str):
    """
    取消正在运行的工作流
    """
    if execution_id not in _executions:
        raise HTTPException(
            status_code=404,
            detail=f"Execution not found: {execution_id}"
        )

    execution = _executions[execution_id]

    if execution.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING, WorkflowStatus.PAUSED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel execution in state: {execution.status.value}"
        )

    execution.status = WorkflowStatus.CANCELLED
    return _execution_to_response(execution)
