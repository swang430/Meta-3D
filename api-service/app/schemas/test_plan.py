"""Test Plan and Test Case Pydantic schemas"""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from ._datetime import UTCDateTime
from uuid import UUID

from app.services.execution_qualification import TestCaseExecutionPolicy


# ==================== Test Plan Schemas ====================

# ==================== Test Case Schemas ====================

def _freq_bw_from_configuration(cfg, cur_freq, cur_bw):
    """P3-14 换源单一实现: 行级 frequency_mhz / bandwidth_mhz 是保存链不回写的
    stale 派生列 (GUI 只 PATCH configuration) — 显示/响应值从 configuration 派生,
    行列只当无 configuration 值时的历史兜底。bool/非正数/字符串形态不接管。

    取值顺序 = **与执行同源** (Codex #262 R1 P1): 执行侧权威 PCell 是
    component_carriers[0]。P1-55 起 schema/service 会拒绝显式镜像分叉并补齐缺失
    镜像；这里仍保持 CC[0] > 顶层 > 行列，以便旧只读数据也从同一真值显示。"""
    if isinstance(cfg, dict):
        source = cfg
        ccs = cfg.get("component_carriers")
        if isinstance(ccs, list) and ccs and isinstance(ccs[0], dict):
            source = ccs[0]
        fh = source.get("frequency_hz")
        if isinstance(fh, (int, float)) and not isinstance(fh, bool) and fh > 0:
            cur_freq = round(fh / 1e6, 3)
        bw = source.get("bandwidth_mhz")
        if isinstance(bw, (int, float)) and not isinstance(bw, bool) and bw > 0:
            cur_bw = float(bw)
    return cur_freq, cur_bw


class TestCaseCreate(BaseModel):
    """Request to create a test case"""
    name: str = Field(..., min_length=1, max_length=255, description="Test case name")
    description: Optional[str] = None
    # P3-14: 描述与 TestCaseType 枚举对齐 (曾漏 MIMO_OTA — 这段进 OpenAPI, 是
    # 外部调用方唯一会读的契约文本); 门 G-A (test_rule_gates) 断言描述 ⊇ 枚举全员。
    test_type: str = Field(..., description="TRP | TIS | Throughput | Handover | MIMO | MIMO_OTA | ChannelModel | VirtualRoadTest | Custom")
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
    lab_profile_id: Optional[UUID] = Field(
        None,
        description=(
            "LabProfile targeted by this TestCase; null keeps the case deployment-agnostic "
            "and requires a unique active LabProfile at execution time"
        ),
    )
    is_template: Optional[bool] = False
    template_category: Optional[str] = Field(None, max_length=100)  # 列 String(100), 超长 PG 500 (P3-14)
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
    lab_profile_id: Optional[UUID] = Field(
        None,
        description="LabProfile targeted by this TestCase; explicit null clears the binding",
    )
    tags: Optional[List[str]] = None


class TestCaseExecutionPolicyUpdate(BaseModel):
    """Dedicated server-owned Diagnostic/Formal policy update."""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(pattern="^(formal|diagnostic)$")
    reason: str
    updated_by: str

    @field_validator("reason", "updated_by")
    @classmethod
    def _non_blank_audit_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("execution policy audit fields must be non-blank")
        return normalized


class TestCaseExecutionPolicyResponse(BaseModel):
    test_case_id: UUID
    policy: TestCaseExecutionPolicy


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
    lab_profile_id: Optional[UUID]
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

    @model_validator(mode="after")
    def _derive_freq_from_configuration(self):
        """P3-14 (内审 F1): 换源母题的 detail 半 — 列表侧已换源, detail 响应
        (POST/GET/PATCH 三端点) 不同源会让两个端点对同一用例报两个频率。
        响应自带 configuration, validator 派生, 未来新构造点自动覆盖。"""
        self.frequency_mhz, self.bandwidth_mhz = _freq_bw_from_configuration(
            self.configuration, self.frequency_mhz, self.bandwidth_mhz)
        return self


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

    @classmethod
    def from_case_row(cls, tc: Any) -> "TestCaseSummary":
        """P3-14 换源: 行级 frequency_mhz / bandwidth_mhz 是保存链不回写的
        stale 派生列 (GUI 只 PATCH configuration, 改频后卡片显示旧频率) ——
        显示值从 configuration 派生, 行列只当无 configuration 值时的历史兜底。
        修法是换源不是加同步机制 (P2-11 内审 F1 定的方向)。"""
        obj = cls.model_validate(tc)
        obj.frequency_mhz, obj.bandwidth_mhz = _freq_bw_from_configuration(
            getattr(tc, "configuration", None), obj.frequency_mhz, obj.bandwidth_mhz)
        return obj


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
    - failure_alert_outcome (P2-34): published | duplicate | failed;
      None = 未记录 (P2-34 之前的历史行 / 记录写入失败 / 非失败或非正式行)
      —— None 不是"告警已发布", 读方只能显示"未记录"。
    """
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

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
    failure_alert_outcome: Optional[str] = None


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
