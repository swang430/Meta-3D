"""Test Plan and Test Case Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from ._datetime import UTCDateTime
from uuid import UUID


# ==================== Test Plan Schemas ====================

# ==================== Test Case Schemas ====================

class TestCaseCreate(BaseModel):
    """Request to create a test case"""
    name: str = Field(..., min_length=1, max_length=255, description="Test case name")
    description: Optional[str] = None
    test_type: str = Field(..., description="TRP | TIS | Throughput | Handover | MIMO | ChannelModel | VirtualRoadTest | Custom")
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
    created_at: UTCDateTime
    updated_at: UTCDateTime
    version: str
    parent_id: Optional[UUID]
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


class TestCaseSummary(BaseModel):
    """Simplified test case summary for lists"""
    id: UUID
    name: str
    description: Optional[str] = None
    test_type: str
    template_category: Optional[str] = None
    channel_model: Optional[str] = None
    frequency_mhz: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    test_duration_sec: Optional[float] = None
    is_template: bool
    pass_criteria: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    created_by: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


# ==================== Test Execution Schemas ====================

# ARCH-1 S4b: TestExecutionResponse 删除 —— 传递闭包多留了一个 (内审 F8),
# 它零消费方 (下面 ExecutionHistoryItem 的注释里提了一句而已)。

# ==================== Test Plan Execution History Schemas ====================

# ==================== Execution History Schemas (ARCH-1 S2) ====================


class ExecutionHistoryItem(BaseModel):
    """执行历史行 — 数据源是 test_executions 本表 (mode IS NULL 排除 VRT)。

    专为历史列表新建, 不复用 TestExecutionResponse: 那个 schema 把
    test_plan_id / test_case_id / execution_order 声明成必填, 而用例执行
    这三个字段是 NULL, 直接复用会 500 (设计稿 §5.3)。

    三态字段语义 (别把 None 渲染成 False):
    - phases_*: None = 该执行链不记相位进度 (commissioning / plan-runner 行),
      GUI 显示 "—"; 只有 case-runner 行有数值。
    - validation_pass: None = 未判定 (执行中 / 未做判定), 不是"失败"。
    """
    id: UUID
    case_name: Optional[str] = None  # 快照 TestCase 名; join 不到 (快照被删) 时 None
    source_test_case_id: Optional[str] = None  # case-runner 行才有, 徽标挂回原用例用
    status: str
    phases_total: Optional[int] = None
    phases_done: Optional[int] = None
    phases_failed: Optional[int] = None
    duration_sec: Optional[float] = None
    started_at: Optional[UTCDateTime] = None
    completed_at: Optional[UTCDateTime] = None
    executed_by: Optional[str] = None  # 来源列: test_case_runner / test_plan_runner / commissioning_*
    error_message: Optional[str] = None
    validation_pass: Optional[bool] = None


class ExecutionHistoryListResponse(BaseModel):
    """执行历史列表响应 (ARCH-1 S2)"""
    total: int
    items: List[ExecutionHistoryItem]


# ==================== Test Queue Schemas ====================

# ==================== Control Schemas ====================

# ==================== Test Step Schemas ====================

# ==================== Sequence Schemas ====================

# ==================== List/Summary Schemas ====================

class TestCaseListResponse(BaseModel):
    """List of test cases with pagination"""
    total: int
    items: List[TestCaseSummary]


class TestCaseGroupedResponse(BaseModel):
    """Test cases grouped by template_category"""
    categories: List[str]
    groups: Dict[str, List[TestCaseSummary]]

