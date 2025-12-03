"""Test Report database models"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class ReportFormat(str, enum.Enum):
    """Report output format"""
    PDF = "pdf"
    HTML = "html"
    EXCEL = "excel"
    JSON = "json"


class ReportType(str, enum.Enum):
    """Report type"""
    SINGLE_EXECUTION = "single_execution"  # 单次测试执行报告
    COMPARISON = "comparison"  # 对比分析报告
    SUMMARY = "summary"  # 汇总报告
    COMPLIANCE = "compliance"  # 合规性报告
    CUSTOM = "custom"  # 自定义报告


class ReportStatus(str, enum.Enum):
    """Report generation status"""
    PENDING = "pending"  # 等待生成
    GENERATING = "generating"  # 生成中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 生成失败
    CANCELLED = "cancelled"  # 已取消


class TemplateType(str, enum.Enum):
    """Report template type"""
    STANDARD = "standard"  # 标准测试报告
    REGULATORY = "regulatory"  # 法规报告（如 FCC/CE）
    PERFORMANCE = "performance"  # 性能分析报告
    COMPARISON = "comparison"  # 对比分析报告
    EXECUTIVE = "executive"  # 管理层摘要
    CUSTOM = "custom"  # 自定义模板


class TestReport(Base):
    """
    Test Report - 测试报告

    存储测试报告的元数据和生成状态，实际报告文件存储在文件系统中。
    """
    __tablename__ = "test_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    title = Column(String(255), nullable=False, comment="Report title")
    description = Column(Text, comment="Report description")

    # Report type and format
    report_type = Column(
        String(50),
        nullable=False,
        default=ReportType.SINGLE_EXECUTION,
        comment="single_execution | comparison | summary | compliance | custom"
    )
    format = Column(
        String(20),
        nullable=False,
        default=ReportFormat.PDF,
        comment="pdf | html | excel | json"
    )

    # Associated data
    test_plan_id = Column(UUID(as_uuid=True), ForeignKey('test_plans.id'), comment="Primary test plan")
    test_execution_ids = Column(JSON, comment="Array of test execution UUIDs included in report")
    comparison_plan_ids = Column(JSON, comment="Array of test plan UUIDs for comparison reports")

    # Template
    template_id = Column(UUID(as_uuid=True), ForeignKey('report_templates.id'), comment="Report template used")
    template_version = Column(String(50), comment="Template version at generation time")

    # Generation status
    status = Column(
        String(50),
        nullable=False,
        default=ReportStatus.PENDING,
        comment="pending | generating | completed | failed | cancelled"
    )
    progress_percent = Column(Integer, default=0, comment="Generation progress (0-100)")

    # File storage
    file_path = Column(String(500), comment="Relative path to generated report file")
    file_size_bytes = Column(Integer, comment="File size in bytes")
    file_hash = Column(String(64), comment="SHA-256 hash for integrity verification")

    # Report content metadata
    page_count = Column(Integer, comment="Number of pages (for PDF)")
    section_count = Column(Integer, comment="Number of sections")
    chart_count = Column(Integer, comment="Number of charts/graphs")
    table_count = Column(Integer, comment="Number of tables")

    # Data included
    include_raw_data = Column(Boolean, default=False, comment="Include raw measurement data")
    include_charts = Column(Boolean, default=True, comment="Include charts and graphs")
    include_statistics = Column(Boolean, default=True, comment="Include statistical analysis")
    include_recommendations = Column(Boolean, default=False, comment="Include recommendations")

    # Configuration
    config = Column(JSON, comment="Report generation configuration")
    custom_sections = Column(JSON, comment="Custom sections added to this report")

    # Timing
    generation_started_at = Column(DateTime, comment="Report generation start time")
    generation_completed_at = Column(DateTime, comment="Report generation completion time")
    generation_duration_sec = Column(Float, comment="Generation duration in seconds")

    # Error handling
    error_message = Column(Text, comment="Error message if generation failed")
    error_details = Column(JSON, comment="Detailed error information")

    # Metadata
    generated_by = Column(String(100), nullable=False, comment="User who requested the report")
    generated_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Version and history
    version = Column(String(50), default="1.0", comment="Report version")
    parent_report_id = Column(UUID(as_uuid=True), comment="Parent report if this is a revision")

    # Access control
    is_public = Column(Boolean, default=False, comment="Public access allowed")
    shared_with = Column(JSON, comment="Array of user IDs with access")

    # Tags and categorization
    tags = Column(JSON, comment="Array of tags")
    category = Column(String(100), comment="Report category")

    # Notes
    notes = Column(Text, comment="Additional notes")


class ReportTemplate(Base):
    """
    Report Template - 报告模板

    定义报告的结构、格式和内容配置。
    """
    __tablename__ = "report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, unique=True, comment="Template name")
    description = Column(Text, comment="Template description")

    # Template type
    template_type = Column(
        String(50),
        nullable=False,
        default=TemplateType.STANDARD,
        comment="standard | regulatory | performance | comparison | executive | custom"
    )

    # Applicable test types
    applicable_test_types = Column(JSON, comment="Array of test types this template supports")

    # Template content (HTML/Jinja2 template or structured config)
    header_template = Column(Text, comment="Header template (HTML/Jinja2)")
    footer_template = Column(Text, comment="Footer template (HTML/Jinja2)")
    cover_template = Column(Text, comment="Cover page template")
    body_template = Column(Text, comment="Main body template")

    # Section definitions
    sections = Column(JSON, nullable=False, comment="Array of section definitions with order and config")
    # Example: [
    #   {
    #     "id": "executive_summary",
    #     "title": "Executive Summary",
    #     "order": 1,
    #     "type": "text",
    #     "required": true,
    #     "template": "sections/executive_summary.html"
    #   },
    #   ...
    # ]

    # Chart and graph configurations
    chart_configs = Column(JSON, comment="Default chart configurations")
    # Example: {
    #   "throughput_chart": {
    #     "type": "line",
    #     "title": "Throughput vs Time",
    #     "x_axis": "time",
    #     "y_axis": "throughput_mbps",
    #     "color_scheme": "blue"
    #   }
    # }

    # Table configurations
    table_configs = Column(JSON, comment="Default table configurations")

    # Style and formatting
    css_styles = Column(Text, comment="Custom CSS styles")
    page_size = Column(String(20), default="A4", comment="Page size: A4, Letter, etc.")
    page_orientation = Column(String(20), default="portrait", comment="portrait | landscape")
    margins = Column(JSON, comment="Page margins: {top, right, bottom, left} in mm")

    # Branding
    logo_path = Column(String(500), comment="Path to company logo")
    company_info = Column(JSON, comment="Company information for footer/header")
    color_scheme = Column(JSON, comment="Color scheme: {primary, secondary, accent, ...}")

    # Data processing
    data_aggregation_rules = Column(JSON, comment="Rules for aggregating test data")
    calculation_formulas = Column(JSON, comment="Custom calculation formulas")

    # Compliance (for regulatory templates)
    regulatory_standard = Column(String(100), comment="Regulatory standard: FCC, CE, 3GPP, etc.")
    compliance_sections = Column(JSON, comment="Required compliance sections")

    # Versioning
    version = Column(String(50), default="1.0", nullable=False)
    parent_template_id = Column(UUID(as_uuid=True), comment="Parent template if this is a variant")

    # Usage tracking
    usage_count = Column(Integer, default=0, comment="Number of reports generated with this template")
    last_used_at = Column(DateTime, comment="Last time template was used")

    # Status
    is_active = Column(Boolean, default=True, comment="Template is active and available")
    is_default = Column(Boolean, default=False, comment="Default template for its type")
    is_public = Column(Boolean, default=True, comment="Available to all users")

    # Metadata
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Tags
    tags = Column(JSON, comment="Array of tags")
    category = Column(String(100), comment="Template category")


class ReportComparison(Base):
    """
    Report Comparison - 报告对比配置

    存储测试对比分析的配置和结果。
    """
    __tablename__ = "report_comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, comment="Comparison name")
    description = Column(Text, comment="Comparison description")

    # Compared items (test plans or executions)
    baseline_plan_id = Column(UUID(as_uuid=True), ForeignKey('test_plans.id'), comment="Baseline test plan")
    comparison_plan_ids = Column(JSON, nullable=False, comment="Array of test plan UUIDs to compare")

    # Comparison configuration
    comparison_metrics = Column(JSON, comment="Metrics to compare: [throughput, latency, ...]")
    grouping = Column(String(100), comment="Group by: frequency, power, test_type, etc.")

    # Statistical analysis
    statistical_tests = Column(JSON, comment="Statistical tests to perform: t-test, ANOVA, etc.")
    confidence_level = Column(Float, default=0.95, comment="Statistical confidence level")

    # Visualization
    chart_types = Column(JSON, comment="Chart types to generate: bar, line, scatter, etc.")

    # Results (calculated during report generation)
    comparison_results = Column(JSON, comment="Comparison analysis results")
    significant_differences = Column(JSON, comment="Statistically significant differences found")
    summary_statistics = Column(JSON, comment="Summary statistics for all compared items")

    # Associated report
    report_id = Column(UUID(as_uuid=True), ForeignKey('test_reports.id'), comment="Generated comparison report")

    # Metadata
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Tags
    tags = Column(JSON, comment="Array of tags")


class ReportSchedule(Base):
    """
    Report Schedule - 定期报告调度

    配置自动生成的定期报告。
    """
    __tablename__ = "report_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, comment="Schedule name")
    description = Column(Text, comment="Schedule description")

    # Template
    template_id = Column(UUID(as_uuid=True), ForeignKey('report_templates.id'), nullable=False)

    # Report configuration
    report_type = Column(String(50), nullable=False, comment="Type of report to generate")
    format = Column(String(20), nullable=False, default=ReportFormat.PDF)

    # Data source (dynamic query for test plans/executions)
    data_filter = Column(JSON, comment="Filter criteria for selecting test data")
    # Example: {"status": "completed", "date_range": "last_7_days", "tags": ["production"]}

    # Schedule configuration (cron-like)
    schedule_type = Column(String(50), nullable=False, comment="daily | weekly | monthly | custom")
    cron_expression = Column(String(100), comment="Cron expression for custom schedules")
    timezone = Column(String(50), default="UTC", comment="Timezone for scheduling")

    # Execution time
    next_execution_time = Column(DateTime, comment="Next scheduled execution")
    last_execution_time = Column(DateTime, comment="Last execution time")

    # Distribution
    recipients = Column(JSON, comment="Array of email addresses to receive report")
    email_subject = Column(String(255), comment="Email subject template")
    email_body = Column(Text, comment="Email body template")

    # Storage
    auto_archive = Column(Boolean, default=True, comment="Automatically archive old reports")
    retention_days = Column(Integer, default=90, comment="Keep reports for N days")

    # Status
    is_active = Column(Boolean, default=True, comment="Schedule is active")
    last_status = Column(String(50), comment="Status of last execution")
    last_error = Column(Text, comment="Error message from last execution if failed")

    # Statistics
    total_executions = Column(Integer, default=0, comment="Total number of executions")
    successful_executions = Column(Integer, default=0, comment="Number of successful executions")
    failed_executions = Column(Integer, default=0, comment="Number of failed executions")

    # Metadata
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
