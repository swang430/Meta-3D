"""Test Report Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ==================== Report Schemas ====================

class ReportCreate(BaseModel):
    """Request to create/generate a test report"""
    title: str = Field(..., min_length=1, max_length=255, description="Report title")
    description: Optional[str] = Field(None, description="Report description")
    report_type: str = Field(
        ...,
        description="single_execution | comparison | summary | compliance | custom"
    )
    format: str = Field(
        "pdf",
        description="pdf | html | excel | json"
    )

    # Associated data
    test_plan_id: Optional[UUID] = Field(None, description="Primary test plan ID")
    test_execution_ids: Optional[List[UUID]] = Field(
        default_factory=list,
        description="Test execution IDs to include"
    )
    comparison_plan_ids: Optional[List[UUID]] = Field(
        default_factory=list,
        description="Test plan IDs for comparison"
    )

    # Template
    template_id: Optional[UUID] = Field(None, description="Report template to use")

    # Content options
    include_raw_data: bool = Field(False, description="Include raw measurement data")
    include_charts: bool = Field(True, description="Include charts and graphs")
    include_statistics: bool = Field(True, description="Include statistical analysis")
    include_recommendations: bool = Field(False, description="Include recommendations")

    # Configuration
    config: Optional[Dict[str, Any]] = Field(None, description="Custom configuration")
    custom_sections: Optional[List[Dict[str, Any]]] = Field(None, description="Custom sections")

    # Metadata
    generated_by: str = Field(..., description="User requesting the report")
    tags: Optional[List[str]] = Field(default_factory=list)
    category: Optional[str] = None
    notes: Optional[str] = None


class ReportUpdate(BaseModel):
    """Request to update report metadata (not regenerate)"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    is_public: Optional[bool] = None
    shared_with: Optional[List[str]] = None


class ReportResponse(BaseModel):
    """Test report response"""
    id: UUID
    title: str
    description: Optional[str]
    report_type: str
    format: str

    # Associated data
    test_plan_id: Optional[UUID]
    test_execution_ids: Optional[List[UUID]]
    comparison_plan_ids: Optional[List[UUID]]

    # Template
    template_id: Optional[UUID]
    template_version: Optional[str]

    # Status
    status: str
    progress_percent: int

    # File info
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    file_hash: Optional[str]

    # Content metadata
    page_count: Optional[int]
    section_count: Optional[int]
    chart_count: Optional[int]
    table_count: Optional[int]

    # Flags
    include_raw_data: bool
    include_charts: bool
    include_statistics: bool
    include_recommendations: bool

    # Configuration
    config: Optional[Dict[str, Any]]
    custom_sections: Optional[List[Dict[str, Any]]]

    # Timing
    generation_started_at: Optional[datetime]
    generation_completed_at: Optional[datetime]
    generation_duration_sec: Optional[float]

    # Error
    error_message: Optional[str]
    error_details: Optional[Dict[str, Any]]

    # Metadata
    generated_by: str
    generated_at: datetime
    version: str
    parent_report_id: Optional[UUID]

    # Access
    is_public: bool
    shared_with: Optional[List[str]]

    # Tags
    tags: Optional[List[str]]
    category: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


class ReportSummary(BaseModel):
    """Simplified report summary for lists"""
    id: UUID
    title: str
    report_type: str
    format: str
    status: str
    progress_percent: int
    file_size_bytes: Optional[int]
    generated_by: str
    generated_at: datetime

    class Config:
        from_attributes = True


class ReportDownloadResponse(BaseModel):
    """Response for report download request"""
    report_id: UUID
    file_path: str
    file_name: str
    file_size_bytes: int
    file_hash: str
    download_url: str
    expires_at: datetime


# ==================== Template Schemas ====================

class ReportTemplateCreate(BaseModel):
    """Request to create a report template"""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = None
    template_type: str = Field(
        ...,
        description="standard | regulatory | performance | comparison | executive | custom"
    )

    # Applicable test types
    applicable_test_types: Optional[List[str]] = Field(
        default_factory=list,
        description="Test types this template supports"
    )

    # Templates (HTML/Jinja2)
    header_template: Optional[str] = None
    footer_template: Optional[str] = None
    cover_template: Optional[str] = None
    body_template: Optional[str] = None

    # Structure
    sections: List[Dict[str, Any]] = Field(..., description="Section definitions")
    chart_configs: Optional[Dict[str, Any]] = None
    table_configs: Optional[Dict[str, Any]] = None

    # Styling
    css_styles: Optional[str] = None
    page_size: str = Field("A4", description="A4, Letter, etc.")
    page_orientation: str = Field("portrait", description="portrait | landscape")
    margins: Optional[Dict[str, float]] = Field(
        None,
        description="Page margins: {top, right, bottom, left} in mm"
    )

    # Branding
    logo_path: Optional[str] = None
    company_info: Optional[Dict[str, Any]] = None
    color_scheme: Optional[Dict[str, str]] = None

    # Data processing
    data_aggregation_rules: Optional[Dict[str, Any]] = None
    calculation_formulas: Optional[Dict[str, Any]] = None

    # Compliance
    regulatory_standard: Optional[str] = None
    compliance_sections: Optional[List[Dict[str, Any]]] = None

    # Metadata
    version: str = Field("1.0")
    created_by: str = Field(..., description="Template creator")
    parent_template_id: Optional[UUID] = None
    is_active: bool = Field(True)
    is_default: bool = Field(False)
    is_public: bool = Field(True)
    tags: Optional[List[str]] = Field(default_factory=list)
    category: Optional[str] = None


class ReportTemplateUpdate(BaseModel):
    """Request to update a report template"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    applicable_test_types: Optional[List[str]] = None
    header_template: Optional[str] = None
    footer_template: Optional[str] = None
    cover_template: Optional[str] = None
    body_template: Optional[str] = None
    sections: Optional[List[Dict[str, Any]]] = None
    chart_configs: Optional[Dict[str, Any]] = None
    table_configs: Optional[Dict[str, Any]] = None
    css_styles: Optional[str] = None
    page_size: Optional[str] = None
    page_orientation: Optional[str] = None
    margins: Optional[Dict[str, float]] = None
    logo_path: Optional[str] = None
    company_info: Optional[Dict[str, Any]] = None
    color_scheme: Optional[Dict[str, str]] = None
    data_aggregation_rules: Optional[Dict[str, Any]] = None
    calculation_formulas: Optional[Dict[str, Any]] = None
    regulatory_standard: Optional[str] = None
    compliance_sections: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class ReportTemplateResponse(BaseModel):
    """Report template response"""
    id: UUID
    name: str
    description: Optional[str]
    template_type: str
    applicable_test_types: Optional[List[str]]

    # Templates
    header_template: Optional[str]
    footer_template: Optional[str]
    cover_template: Optional[str]
    body_template: Optional[str]

    # Structure
    sections: List[Dict[str, Any]]
    chart_configs: Optional[Dict[str, Any]]
    table_configs: Optional[Dict[str, Any]]

    # Styling
    css_styles: Optional[str]
    page_size: str
    page_orientation: str
    margins: Optional[Dict[str, float]]

    # Branding
    logo_path: Optional[str]
    company_info: Optional[Dict[str, Any]]
    color_scheme: Optional[Dict[str, str]]

    # Data processing
    data_aggregation_rules: Optional[Dict[str, Any]]
    calculation_formulas: Optional[Dict[str, Any]]

    # Compliance
    regulatory_standard: Optional[str]
    compliance_sections: Optional[List[Dict[str, Any]]]

    # Version
    version: str
    parent_template_id: Optional[UUID]

    # Usage
    usage_count: int
    last_used_at: Optional[datetime]

    # Status
    is_active: bool
    is_default: bool
    is_public: bool

    # Metadata
    created_by: str
    created_at: datetime
    updated_at: datetime
    tags: Optional[List[str]]
    category: Optional[str]

    class Config:
        from_attributes = True


class ReportTemplateSummary(BaseModel):
    """Simplified template summary for lists"""
    id: UUID
    name: str
    template_type: str
    version: str
    usage_count: int
    is_active: bool
    is_default: bool
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Comparison Schemas ====================

class ReportComparisonCreate(BaseModel):
    """Request to create a comparison analysis"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    baseline_plan_id: UUID = Field(..., description="Baseline test plan")
    comparison_plan_ids: List[UUID] = Field(..., description="Plans to compare against baseline")

    # Configuration
    comparison_metrics: Optional[List[str]] = Field(
        default_factory=list,
        description="Metrics to compare: throughput, latency, etc."
    )
    grouping: Optional[str] = Field(None, description="Group by: frequency, power, test_type")

    # Statistical analysis
    statistical_tests: Optional[List[str]] = Field(
        default_factory=list,
        description="Statistical tests: t-test, ANOVA, etc."
    )
    confidence_level: float = Field(0.95, ge=0.0, le=1.0)

    # Visualization
    chart_types: Optional[List[str]] = Field(
        default_factory=list,
        description="Chart types: bar, line, scatter"
    )

    # Metadata
    created_by: str = Field(..., description="User creating the comparison")
    tags: Optional[List[str]] = Field(default_factory=list)


class ReportComparisonResponse(BaseModel):
    """Comparison analysis response"""
    id: UUID
    name: str
    description: Optional[str]
    baseline_plan_id: UUID
    comparison_plan_ids: List[UUID]
    comparison_metrics: Optional[List[str]]
    grouping: Optional[str]
    statistical_tests: Optional[List[str]]
    confidence_level: float
    chart_types: Optional[List[str]]

    # Results
    comparison_results: Optional[Dict[str, Any]]
    significant_differences: Optional[List[Dict[str, Any]]]
    summary_statistics: Optional[Dict[str, Any]]

    # Report
    report_id: Optional[UUID]

    # Metadata
    created_by: str
    created_at: datetime
    updated_at: datetime
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


# ==================== Schedule Schemas ====================

class ReportScheduleCreate(BaseModel):
    """Request to create a report schedule"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    template_id: UUID = Field(..., description="Template to use")
    report_type: str = Field(..., description="Type of report")
    format: str = Field("pdf", description="Output format")

    # Data filter
    data_filter: Optional[Dict[str, Any]] = Field(
        None,
        description="Filter for selecting test data"
    )

    # Schedule
    schedule_type: str = Field(..., description="daily | weekly | monthly | custom")
    cron_expression: Optional[str] = Field(None, description="Cron expression for custom")
    timezone: str = Field("UTC")

    # Distribution
    recipients: Optional[List[str]] = Field(default_factory=list, description="Email addresses")
    email_subject: Optional[str] = None
    email_body: Optional[str] = None

    # Storage
    auto_archive: bool = Field(True)
    retention_days: int = Field(90, ge=1)

    # Metadata
    created_by: str = Field(..., description="Schedule creator")
    is_active: bool = Field(True)


class ReportScheduleUpdate(BaseModel):
    """Request to update a report schedule"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    data_filter: Optional[Dict[str, Any]] = None
    schedule_type: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    recipients: Optional[List[str]] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    auto_archive: Optional[bool] = None
    retention_days: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None


class ReportScheduleResponse(BaseModel):
    """Report schedule response"""
    id: UUID
    name: str
    description: Optional[str]
    template_id: UUID
    report_type: str
    format: str
    data_filter: Optional[Dict[str, Any]]
    schedule_type: str
    cron_expression: Optional[str]
    timezone: str
    next_execution_time: Optional[datetime]
    last_execution_time: Optional[datetime]
    recipients: Optional[List[str]]
    email_subject: Optional[str]
    email_body: Optional[str]
    auto_archive: bool
    retention_days: int
    is_active: bool
    last_status: Optional[str]
    last_error: Optional[str]
    total_executions: int
    successful_executions: int
    failed_executions: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== List Responses ====================

class ReportListResponse(BaseModel):
    """List of reports"""
    reports: List[ReportSummary]
    total: int
    page: int = 1
    page_size: int = 20


class TemplateListResponse(BaseModel):
    """List of templates"""
    templates: List[ReportTemplateSummary]
    total: int
    page: int = 1
    page_size: int = 20


class ComparisonListResponse(BaseModel):
    """List of comparisons"""
    comparisons: List[ReportComparisonResponse]
    total: int
    page: int = 1
    page_size: int = 20


class ScheduleListResponse(BaseModel):
    """List of schedules"""
    schedules: List[ReportScheduleResponse]
    total: int
    page: int = 1
    page_size: int = 20


# ==================== Statistics Schemas ====================

class StatisticsCompareRequest(BaseModel):
    """Request to compare multiple reports statistically"""
    report_ids: List[UUID] = Field(..., min_length=2, description="At least 2 reports to compare")
    metrics: Optional[List[str]] = Field(
        None,
        description="Specific metrics to compare. If None, compares all common metrics"
    )
    group_by: Optional[str] = Field(
        None,
        description="Group comparison by: frequency, power_level, test_type"
    )
    confidence_level: float = Field(
        0.95,
        ge=0.0,
        le=1.0,
        description="Confidence level for statistical tests"
    )


class MetricStatistics(BaseModel):
    """Statistical summary for a single metric"""
    metric_name: str
    mean: float
    median: float
    std: float
    min: float
    max: float
    range: float
    count: int
    percentiles: Optional[Dict[str, float]] = None
    confidence_interval: Optional[Dict[str, float]] = None


class ComparisonResult(BaseModel):
    """Comparison result for a specific metric across reports"""
    metric_name: str
    report_statistics: Dict[str, MetricStatistics]
    overall_mean: float
    overall_std: float
    coefficient_of_variation: float
    significant_differences: Optional[List[Dict[str, Any]]] = None


class StatisticsCompareResponse(BaseModel):
    """Response with statistical comparison results"""
    report_ids: List[UUID]
    metrics_compared: List[str]
    comparison_results: List[ComparisonResult]
    summary: Dict[str, Any]
    generated_at: datetime


class BenchmarkRequest(BaseModel):
    """Request to benchmark a report against reference data"""
    report_id: UUID = Field(..., description="Report to benchmark")
    reference_report_ids: Optional[List[UUID]] = Field(
        None,
        description="Reference reports. If None, uses all reports of same type"
    )
    metrics: Optional[List[str]] = Field(
        None,
        description="Metrics to benchmark. If None, benchmarks all metrics"
    )


class BenchmarkMetric(BaseModel):
    """Benchmark result for a single metric"""
    metric_name: str
    value: float
    percentile_rank: float
    performance_rating: str  # "excellent" | "good" | "average" | "below_average" | "poor"
    reference_mean: float
    reference_std: float
    z_score: float


class BenchmarkResponse(BaseModel):
    """Response with benchmark results"""
    report_id: UUID
    reference_count: int
    benchmark_metrics: List[BenchmarkMetric]
    overall_percentile: float
    overall_rating: str
    summary: str
    generated_at: datetime


class TimeSeriesRequest(BaseModel):
    """Request for time series analysis"""
    test_plan_id: UUID = Field(..., description="Test plan to analyze")
    metric_name: str = Field(..., description="Metric to analyze over time")
    start_date: Optional[datetime] = Field(None, description="Start of time range")
    end_date: Optional[datetime] = Field(None, description="End of time range")
    window_size: int = Field(
        5,
        ge=2,
        description="Rolling window size for trend analysis"
    )
    anomaly_threshold: float = Field(
        3.0,
        ge=1.0,
        le=10.0,
        description="Z-score threshold for anomaly detection"
    )


class TimeSeriesPoint(BaseModel):
    """Single point in time series"""
    timestamp: datetime
    value: float
    execution_id: UUID
    is_anomaly: bool = False
    z_score: Optional[float] = None


class TrendAnalysis(BaseModel):
    """Trend analysis results"""
    direction: str  # "increasing" | "decreasing" | "stable"
    slope: float
    r_squared: float
    strength: str  # "strong" | "moderate" | "weak"


class TimeSeriesResponse(BaseModel):
    """Response with time series analysis"""
    test_plan_id: UUID
    metric_name: str
    data_points: List[TimeSeriesPoint]
    trend: TrendAnalysis
    anomalies: List[Dict[str, Any]]
    statistics: MetricStatistics
    rolling_mean: List[float]
    rolling_std: List[float]
    generated_at: datetime


# ==================== Simple Compare Schemas ====================

class SimpleCompareRequest(BaseModel):
    """Simple report comparison request"""
    report_ids: List[UUID] = Field(..., min_length=2, description="Report IDs to compare")
    comparison_type: str = Field(
        "kpi_diff",
        description="Comparison type: kpi_diff | trend_analysis | full"
    )
    metrics: Optional[List[str]] = Field(None, description="Specific metrics to compare")


class KPIDifference(BaseModel):
    """KPI difference between reports"""
    metric_name: str
    values: Dict[str, float]  # report_id -> value
    baseline_value: float
    differences: Dict[str, float]  # report_id -> difference from baseline
    percent_changes: Dict[str, float]  # report_id -> percent change


class SimpleCompareResponse(BaseModel):
    """Simple report comparison response"""
    report_ids: List[UUID]
    comparison_type: str
    comparison_result: Dict[str, Any]
    kpi_differences: Optional[List[KPIDifference]] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
