"""Test Plan and Test Case database models"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum


from app.db.database import Base


class TestPlanStatus(str, enum.Enum):
    """Test Plan Status"""
    DRAFT = "draft"  # 草稿
    READY = "ready"  # 就绪，可执行
    QUEUED = "queued"  # 已排队
    RUNNING = "running"  # 执行中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class TestCaseType(str, enum.Enum):
    """Test Case Type"""
    TRP = "TRP"  # Total Radiated Power
    TIS = "TIS"  # Total Isotropic Sensitivity
    THROUGHPUT = "Throughput"  # 吞吐量测试
    HANDOVER = "Handover"  # 切换测试
    MIMO = "MIMO"  # MIMO 性能测试
    CHANNEL_MODEL = "ChannelModel"  # 信道模型测试
    CUSTOM = "Custom"  # 自定义测试


class TestPlan(Base):
    """
    Test Plan - 测试计划

    测试计划是测试用例的集合，定义了一组要执行的测试及其执行顺序。
    """
    __tablename__ = "test_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, comment="Test plan name")
    description = Column(Text, comment="Detailed description")
    version = Column(String(50), default="1.0", comment="Version number")

    # Status
    status = Column(
        String(50),
        nullable=False,
        default=TestPlanStatus.DRAFT,
        comment="draft | ready | queued | running | paused | completed | failed | cancelled"
    )

    # Test configuration
    dut_info = Column(JSON, comment="Device Under Test info: {model, serial, imei, ...}")
    test_environment = Column(JSON, comment="Environment: {temperature, humidity, chamber_id, ...}")

    # Test cases (ordered list of test case IDs)
    test_case_ids = Column(JSON, comment="Array of test case UUIDs in execution order")
    total_test_cases = Column(Integer, default=0, comment="Total number of test cases")

    # Execution tracking
    current_test_case_index = Column(Integer, default=0, comment="Index of currently executing test case")
    completed_test_cases = Column(Integer, default=0, comment="Number of completed test cases")
    failed_test_cases = Column(Integer, default=0, comment="Number of failed test cases")

    # Timing
    estimated_duration_minutes = Column(Float, comment="Estimated total duration")
    actual_duration_minutes = Column(Float, comment="Actual duration")
    started_at = Column(DateTime, comment="Execution start time")
    completed_at = Column(DateTime, comment="Execution completion time")

    # Queue management
    queue_position = Column(Integer, comment="Position in execution queue")
    priority = Column(Integer, default=5, comment="Priority (1=highest, 10=lowest)")

    # Metadata
    created_by = Column(String(100), nullable=False, comment="User who created the plan")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Notes and tags
    notes = Column(Text, comment="Additional notes")
    tags = Column(JSON, comment="Array of tags for categorization")


class TestCase(Base):
    """
    Test Case - 测试用例

    测试用例定义了单个测试的配置参数，可以被多个测试计划重用。
    """
    __tablename__ = "test_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, comment="Test case name")
    description = Column(Text, comment="Test case description")
    test_type = Column(
        String(50),
        nullable=False,
        comment="TRP | TIS | Throughput | Handover | MIMO | ChannelModel | Custom"
    )

    # Test configuration (JSON structure varies by test_type)
    configuration = Column(JSON, nullable=False, comment="Test-specific configuration parameters")

    # Expected results and pass criteria
    pass_criteria = Column(JSON, comment="Pass/fail criteria: {metric, operator, threshold, ...}")
    expected_results = Column(JSON, comment="Expected results for comparison")

    # Probe and instrument configuration
    probe_selection = Column(JSON, comment="Probe selection config")
    instrument_config = Column(JSON, comment="Instrument settings")

    # Channel model (for MIMO/Throughput tests)
    channel_model = Column(String(100), comment="3GPP channel model (e.g., CDL-A, TDL-C)")
    channel_parameters = Column(JSON, comment="Channel model parameters")

    # Frequency and power
    frequency_mhz = Column(Float, comment="Test frequency in MHz")
    tx_power_dbm = Column(Float, comment="Transmit power in dBm")
    bandwidth_mhz = Column(Float, comment="Channel bandwidth")

    # Duration
    test_duration_sec = Column(Float, comment="Test duration in seconds")

    # Reusability
    is_template = Column(Boolean, default=False, comment="Can be used as a template")
    template_category = Column(String(100), comment="Template category for organization")

    # Metadata
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Version control
    version = Column(String(50), default="1.0")
    parent_id = Column(UUID(as_uuid=True), comment="Parent test case ID if this is a variant")

    # Tags
    tags = Column(JSON, comment="Array of tags")


class TestExecution(Base):
    """
    Test Execution - 测试执行记录

    记录测试计划或测试用例的每次执行结果。
    """
    __tablename__ = "test_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Association
    test_plan_id = Column(UUID(as_uuid=True), ForeignKey('test_plans.id'), nullable=False)
    test_case_id = Column(UUID(as_uuid=True), ForeignKey('test_cases.id'), nullable=False)

    # Execution order
    execution_order = Column(Integer, comment="Order in test plan")

    # Status
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending | running | completed | failed | skipped"
    )

    # Results
    test_results = Column(JSON, comment="Detailed test results")
    measurements = Column(JSON, comment="Raw measurement data")

    # Pass/fail
    validation_pass = Column(Boolean, comment="Overall pass/fail")
    validation_details = Column(JSON, comment="Detailed validation results per criterion")

    # Timing
    started_at = Column(DateTime, comment="Test start time")
    completed_at = Column(DateTime, comment="Test completion time")
    duration_sec = Column(Float, comment="Actual test duration")

    # Error handling
    error_message = Column(Text, comment="Error message if failed")
    error_details = Column(JSON, comment="Detailed error information")

    # Metadata
    executed_by = Column(String(100), comment="User who executed the test")
    executed_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    # test_plan = relationship("TestPlan", back_populates="executions")
    # test_case = relationship("TestCase", back_populates="executions")


class TestSequence(Base):
    """
    Test Sequence - 测试序列

    可重用的测试步骤序列，用于构建复杂的测试用例。
    """
    __tablename__ = "test_sequences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, comment="Sequence name")
    description = Column(Text, comment="Sequence description")
    category = Column(String(100), comment="Category for organization")

    # Steps (array of step definitions)
    steps = Column(JSON, nullable=False, comment="Array of step objects")

    # Parameters (can be overridden when using sequence)
    parameters = Column(JSON, comment="Configurable parameters")
    default_values = Column(JSON, comment="Default parameter values")

    # Validation
    validation_rules = Column(JSON, comment="Validation rules for this sequence")

    # Reusability
    is_public = Column(Boolean, default=True, comment="Available to all users")
    usage_count = Column(Integer, default=0, comment="Number of times used")

    # Metadata
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Tags
    tags = Column(JSON, comment="Array of tags")


class TestStep(Base):
    """
    Test Step - 测试步骤

    测试计划中的单个步骤，支持灵活的参数配置。
    """
    __tablename__ = "test_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Association
    test_plan_id = Column(UUID(as_uuid=True), ForeignKey('test_plans.id'), nullable=False)
    sequence_library_id = Column(UUID(as_uuid=True), ForeignKey('test_sequences.id'), nullable=True, comment="Reference to sequence library template")

    # Step info (nullable when using sequence_library_id)
    step_number = Column(Integer, nullable=True, comment="Step number in sequence")
    name = Column(String(255), nullable=True, comment="Step name")
    description = Column(Text, comment="Step description")
    type = Column(String(100), nullable=True, comment="Step type: configure_instrument, run_measurement, etc.")

    # Parameters (flexible JSON structure)
    parameters = Column(JSON, nullable=False, default={}, comment="Step parameters with types and values")

    # Execution config
    timeout_seconds = Column(Integer, default=300, comment="Step timeout in seconds")
    retry_count = Column(Integer, default=0, comment="Number of retries on failure")
    continue_on_failure = Column(Boolean, default=False, comment="Continue execution if step fails")

    # Execution status
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending | running | completed | failed | skipped"
    )
    order = Column(Integer, nullable=False, comment="Execution order")

    # Timing
    expected_duration_minutes = Column(Float, comment="Expected duration")
    actual_duration_minutes = Column(Float, comment="Actual duration")
    started_at = Column(DateTime, comment="Step start time")
    completed_at = Column(DateTime, comment="Step completion time")

    # Results
    result = Column(Text, comment="Step execution result description")

    # Validation
    validation_criteria = Column(JSON, comment="Validation criteria for this step")

    # Error handling
    error_message = Column(Text, comment="Error message if failed")

    # Metadata
    notes = Column(Text, comment="Additional notes")
    tags = Column(JSON, comment="Array of tags")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TestQueue(Base):
    """
    Test Queue - 测试队列

    管理测试计划的执行队列，支持优先级调度。
    """
    __tablename__ = "test_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Test plan reference
    test_plan_id = Column(UUID(as_uuid=True), ForeignKey('test_plans.id'), nullable=False, unique=True)

    # Queue management
    position = Column(Integer, nullable=False, comment="Position in queue (1 = next)")
    priority = Column(Integer, default=5, comment="Priority (1=highest, 10=lowest)")

    # Status
    status = Column(
        String(50),
        nullable=False,
        default="queued",
        comment="queued | ready | blocked | cancelled"
    )

    # Scheduling
    scheduled_start_time = Column(DateTime, comment="Scheduled start time")
    estimated_start_time = Column(DateTime, comment="Estimated start time based on queue")

    # Dependencies
    dependencies = Column(JSON, comment="Array of test plan IDs that must complete first")
    blocked_by = Column(JSON, comment="Array of test plan IDs blocking this one")

    # Metadata
    queued_by = Column(String(100), nullable=False, comment="User who queued the test")
    queued_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Notes
    notes = Column(Text, comment="Queue-specific notes")
