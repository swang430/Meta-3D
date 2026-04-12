"""
Workflow API Schemas

Pydantic models for workflow execution API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


# ==================== Enums ====================

class WorkflowStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class StepStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class StepTypeEnum(str, Enum):
    PROBE_CALIBRATION = "probe_calibration"
    CHANNEL_CALIBRATION = "channel_calibration"
    WAIT = "wait"
    CONDITION = "condition"
    NOTIFY = "notify"


class OnFailureActionEnum(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"
    RETRY = "retry"
    SKIP = "skip"


# ==================== Step Schemas ====================

class WorkflowStepSchema(BaseModel):
    """Workflow step definition"""
    id: str = Field(..., description="Step unique identifier")
    type: StepTypeEnum = Field(..., description="Step type")
    calibration_type: Optional[str] = Field(None, description="Calibration type for calibration steps")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Step parameters")
    depends_on: List[str] = Field(default_factory=list, description="IDs of steps this step depends on")
    parallel_with: List[str] = Field(default_factory=list, description="IDs of steps to run in parallel")
    on_failure: OnFailureActionEnum = Field(OnFailureActionEnum.STOP, description="Action on failure")
    retry_count: Optional[int] = Field(None, description="Override retry count")
    timeout_seconds: Optional[int] = Field(None, description="Step timeout in seconds")
    description: Optional[str] = Field(None, description="Step description")


class StepResultSchema(BaseModel):
    """Result of a step execution"""
    step_id: str
    status: StepStatusEnum
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    calibration_id: Optional[str] = None
    validation_pass: Optional[bool] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    output: Dict[str, Any] = Field(default_factory=dict)


# ==================== Workflow Schemas ====================

class WorkflowSettingsSchema(BaseModel):
    """Workflow settings"""
    retry_count: int = Field(3, description="Default retry count")
    retry_delay_seconds: int = Field(5, description="Delay between retries")
    stop_on_failure: bool = Field(True, description="Stop workflow on first failure")
    notification: Optional[Dict[str, Any]] = Field(None, description="Notification settings")


class WorkflowDefinitionSchema(BaseModel):
    """Complete workflow definition"""
    name: str = Field(..., description="Workflow name")
    version: str = Field("1.0", description="Workflow version")
    description: Optional[str] = Field(None, description="Workflow description")
    settings: WorkflowSettingsSchema = Field(default_factory=WorkflowSettingsSchema)
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Global workflow parameters")
    steps: List[WorkflowStepSchema] = Field(..., description="Workflow steps")


class WorkflowExecutionResponse(BaseModel):
    """Workflow execution status response"""
    id: str = Field(..., description="Execution ID")
    workflow_name: str = Field(..., description="Workflow name")
    status: WorkflowStatusEnum = Field(..., description="Execution status")
    progress_percent: float = Field(..., description="Progress percentage")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step_index: int = 0
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    session_id: Optional[str] = None
    error_message: Optional[str] = None
    step_results: Dict[str, StepResultSchema] = Field(default_factory=dict)


# ==================== Request Schemas ====================

class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow"""
    workflow_id: Optional[str] = Field(
        None,
        description="Predefined workflow ID (e.g., 'full_channel_calibration')"
    )
    yaml_content: Optional[str] = Field(
        None,
        description="Custom workflow YAML content"
    )
    parameter_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Override workflow parameters"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "full_channel_calibration",
                "parameter_overrides": {
                    "fc_ghz": 3.5,
                    "calibrated_by": "operator"
                }
            }
        }


class ParseWorkflowRequest(BaseModel):
    """Request to parse/validate a workflow YAML"""
    yaml_content: str = Field(..., description="Workflow YAML content to validate")


class ParseWorkflowResponse(BaseModel):
    """Response from workflow parsing"""
    valid: bool = Field(..., description="Whether the YAML is valid")
    workflow: Optional[WorkflowDefinitionSchema] = Field(None, description="Parsed workflow if valid")
    error_message: Optional[str] = Field(None, description="Error message if invalid")


# ==================== List Schemas ====================

class PredefinedWorkflowInfo(BaseModel):
    """Info about a predefined workflow"""
    id: str = Field(..., description="Workflow identifier")
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    version: str = Field(..., description="Workflow version")
    step_count: int = Field(..., description="Number of steps")
    estimated_duration_minutes: Optional[float] = Field(None, description="Estimated duration")


class PredefinedWorkflowListResponse(BaseModel):
    """List of predefined workflows"""
    workflows: List[PredefinedWorkflowInfo]
    total: int


class WorkflowExecutionListItem(BaseModel):
    """Workflow execution list item"""
    id: str
    workflow_name: str
    status: WorkflowStatusEnum
    progress_percent: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    passed_steps: int
    failed_steps: int
    total_steps: int


class WorkflowExecutionListResponse(BaseModel):
    """List of workflow executions"""
    executions: List[WorkflowExecutionListItem]
    total: int
