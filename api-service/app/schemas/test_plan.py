"""Test Plan and Test Case Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ==================== Test Plan Schemas ====================

class TestPlanCreate(BaseModel):
    """Request to create a test plan"""
    name: str = Field(..., min_length=1, max_length=255, description="Test plan name")
    description: Optional[str] = Field(None, description="Detailed description")
    version: Optional[str] = Field("1.0", description="Version number")
    dut_info: Optional[Dict[str, Any]] = Field(None, description="Device Under Test info")
    test_environment: Optional[Dict[str, Any]] = Field(None, description="Test environment info")
    test_case_ids: List[str] = Field(default_factory=list, description="Array of test case UUIDs")
    priority: Optional[int] = Field(5, ge=1, le=10, description="Priority (1=highest, 10=lowest)")
    created_by: str = Field(..., description="User who created the plan")
    notes: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")


class TestPlanUpdate(BaseModel):
    """Request to update a test plan"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    dut_info: Optional[Dict[str, Any]] = None
    test_environment: Optional[Dict[str, Any]] = None
    test_case_ids: Optional[List[str]] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class TestPlanResponse(BaseModel):
    """Test plan response"""
    id: UUID
    name: str
    description: Optional[str]
    version: str
    status: str
    dut_info: Optional[Dict[str, Any]]
    test_environment: Optional[Dict[str, Any]]
    test_case_ids: Optional[List[str]]
    total_test_cases: int
    current_test_case_index: int
    completed_test_cases: int
    failed_test_cases: int
    estimated_duration_minutes: Optional[float]
    actual_duration_minutes: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    queue_position: Optional[int]
    priority: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    notes: Optional[str]
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


class TestPlanSummary(BaseModel):
    """Simplified test plan summary for lists"""
    id: UUID
    name: str
    status: str
    total_test_cases: int
    completed_test_cases: int
    failed_test_cases: int
    priority: int
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Test Case Schemas ====================

class TestCaseCreate(BaseModel):
    """Request to create a test case"""
    name: str = Field(..., min_length=1, max_length=255, description="Test case name")
    description: Optional[str] = None
    test_type: str = Field(..., description="TRP | TIS | Throughput | Handover | MIMO | ChannelModel | Custom")
    configuration: Dict[str, Any] = Field(..., description="Test-specific configuration")
    pass_criteria: Optional[Dict[str, Any]] = None
    expected_results: Optional[Dict[str, Any]] = None
    probe_selection: Optional[Dict[str, Any]] = None
    instrument_config: Optional[Dict[str, Any]] = None
    channel_model: Optional[str] = None
    channel_parameters: Optional[Dict[str, Any]] = None
    frequency_mhz: Optional[float] = None
    tx_power_dbm: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    test_duration_sec: Optional[float] = None
    is_template: Optional[bool] = False
    template_category: Optional[str] = None
    created_by: str = Field(..., description="User who created the test case")
    tags: Optional[List[str]] = Field(default_factory=list)


class TestCaseUpdate(BaseModel):
    """Request to update a test case"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None
    pass_criteria: Optional[Dict[str, Any]] = None
    expected_results: Optional[Dict[str, Any]] = None
    probe_selection: Optional[Dict[str, Any]] = None
    instrument_config: Optional[Dict[str, Any]] = None
    channel_model: Optional[str] = None
    channel_parameters: Optional[Dict[str, Any]] = None
    frequency_mhz: Optional[float] = None
    tx_power_dbm: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    test_duration_sec: Optional[float] = None
    tags: Optional[List[str]] = None


class TestCaseResponse(BaseModel):
    """Test case response"""
    id: UUID
    name: str
    description: Optional[str]
    test_type: str
    configuration: Dict[str, Any]
    pass_criteria: Optional[Dict[str, Any]]
    expected_results: Optional[Dict[str, Any]]
    probe_selection: Optional[Dict[str, Any]]
    instrument_config: Optional[Dict[str, Any]]
    channel_model: Optional[str]
    channel_parameters: Optional[Dict[str, Any]]
    frequency_mhz: Optional[float]
    tx_power_dbm: Optional[float]
    bandwidth_mhz: Optional[float]
    test_duration_sec: Optional[float]
    is_template: bool
    template_category: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    version: str
    parent_id: Optional[UUID]
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


class TestCaseSummary(BaseModel):
    """Simplified test case summary for lists"""
    id: UUID
    name: str
    test_type: str
    frequency_mhz: Optional[float]
    test_duration_sec: Optional[float]
    is_template: bool
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Test Execution Schemas ====================

class TestExecutionCreate(BaseModel):
    """Request to create a test execution record"""
    test_plan_id: UUID
    test_case_id: UUID
    execution_order: int
    executed_by: str


class TestExecutionUpdate(BaseModel):
    """Request to update a test execution record"""
    status: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    measurements: Optional[Dict[str, Any]] = None
    validation_pass: Optional[bool] = None
    validation_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


class TestExecutionResponse(BaseModel):
    """Test execution response"""
    id: UUID
    test_plan_id: UUID
    test_case_id: UUID
    execution_order: int
    status: str
    test_results: Optional[Dict[str, Any]]
    measurements: Optional[Dict[str, Any]]
    validation_pass: Optional[bool]
    validation_details: Optional[Dict[str, Any]]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_sec: Optional[float]
    error_message: Optional[str]
    error_details: Optional[Dict[str, Any]]
    executed_by: str
    executed_at: datetime

    class Config:
        from_attributes = True


# ==================== Test Queue Schemas ====================

class QueueTestPlanRequest(BaseModel):
    """Request to queue a test plan"""
    test_plan_id: UUID
    priority: Optional[int] = Field(5, ge=1, le=10)
    scheduled_start_time: Optional[datetime] = None
    dependencies: Optional[List[UUID]] = Field(default_factory=list)
    queued_by: str
    notes: Optional[str] = None


class TestQueueResponse(BaseModel):
    """Test queue item response"""
    id: UUID
    test_plan_id: UUID
    position: int
    priority: int
    status: str
    scheduled_start_time: Optional[datetime]
    estimated_start_time: Optional[datetime]
    dependencies: Optional[List[str]]
    blocked_by: Optional[List[str]]
    queued_by: str
    queued_at: datetime
    notes: Optional[str]

    class Config:
        from_attributes = True


class TestQueueSummary(BaseModel):
    """Queue summary with test plan details"""
    queue_item: TestQueueResponse
    test_plan: TestPlanSummary


# ==================== Control Schemas ====================

class StartTestPlanRequest(BaseModel):
    """Request to start executing a test plan"""
    test_plan_id: UUID
    started_by: str
    override_config: Optional[Dict[str, Any]] = None


class PauseTestPlanRequest(BaseModel):
    """Request to pause a running test plan"""
    test_plan_id: UUID
    paused_by: str
    reason: Optional[str] = None


class ResumeTestPlanRequest(BaseModel):
    """Request to resume a paused test plan"""
    test_plan_id: UUID
    resumed_by: str


class CancelTestPlanRequest(BaseModel):
    """Request to cancel a test plan"""
    test_plan_id: UUID
    cancelled_by: str
    reason: Optional[str] = None


# ==================== Sequence Schemas ====================

class TestSequenceCreate(BaseModel):
    """Request to create a test sequence"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(..., description="Array of step objects")
    parameters: Optional[Dict[str, Any]] = None
    default_values: Optional[Dict[str, Any]] = None
    validation_rules: Optional[Dict[str, Any]] = None
    is_public: bool = True
    created_by: str
    tags: Optional[List[str]] = Field(default_factory=list)


class TestSequenceResponse(BaseModel):
    """Test sequence response"""
    id: UUID
    name: str
    description: Optional[str]
    category: Optional[str]
    steps: List[Dict[str, Any]]
    parameters: Optional[Dict[str, Any]]
    default_values: Optional[Dict[str, Any]]
    validation_rules: Optional[Dict[str, Any]]
    is_public: bool
    usage_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


# ==================== List/Summary Schemas ====================

class TestPlanListResponse(BaseModel):
    """List of test plans with pagination"""
    total: int
    items: List[TestPlanSummary]


class TestCaseListResponse(BaseModel):
    """List of test cases with pagination"""
    total: int
    items: List[TestCaseSummary]


class TestExecutionListResponse(BaseModel):
    """List of test executions"""
    total: int
    items: List[TestExecutionResponse]


class TestQueueListResponse(BaseModel):
    """List of queued test plans"""
    total: int
    items: List[TestQueueSummary]
