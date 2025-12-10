"""Report API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.schemas.report import (
    # Report
    ReportCreate,
    ReportUpdate,
    ReportResponse,
    ReportSummary,
    ReportListResponse,
    # Template
    ReportTemplateCreate,
    ReportTemplateUpdate,
    ReportTemplateResponse,
    ReportTemplateSummary,
    TemplateListResponse,
    # Comparison
    ReportComparisonCreate,
    ReportComparisonResponse,
    ComparisonListResponse,
    # Schedule
    ReportScheduleCreate,
    ReportScheduleUpdate,
    ReportScheduleResponse,
    ScheduleListResponse,
    # Statistics
    StatisticsCompareRequest,
    StatisticsCompareResponse,
    BenchmarkRequest,
    BenchmarkResponse,
    TimeSeriesRequest,
    TimeSeriesResponse,
    MetricStatistics,
    ComparisonResult,
    BenchmarkMetric,
    TimeSeriesPoint,
    TrendAnalysis,
)
from app.services.report_service import (
    ReportService,
    ReportTemplateService,
    ReportComparisonService,
    ReportScheduleService,
)
from app.services.statistics_service import StatisticsService

router = APIRouter(prefix="/reports", tags=["reports"])

# Service instances
report_service = ReportService()
template_service = ReportTemplateService()
comparison_service = ReportComparisonService()
schedule_service = ReportScheduleService()
statistics_service = StatisticsService()


# ==================== Report Endpoints ====================

@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    report: ReportCreate,
    db: Session = Depends(get_db)
):
    """Create a new test report"""
    return report_service.create_report(
        db=db,
        title=report.title,
        report_type=report.report_type,
        format=report.format,
        generated_by=report.generated_by,
        test_plan_id=report.test_plan_id,
        test_execution_ids=report.test_execution_ids,
        template_id=report.template_id,
        description=report.description,
        comparison_plan_ids=report.comparison_plan_ids,
        include_raw_data=report.include_raw_data,
        include_charts=report.include_charts,
        include_statistics=report.include_statistics,
        include_recommendations=report.include_recommendations,
        config=report.config,
        custom_sections=report.custom_sections,
        tags=report.tags,
        category=report.category,
        notes=report.notes,
    )


@router.get("", response_model=ReportListResponse)
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    report_type: Optional[str] = None,
    format: Optional[str] = None,
    generated_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all reports with filters and pagination"""
    reports = report_service.list_reports(
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        report_type=report_type,
        format=format,
        generated_by=generated_by
    )
    total = report_service.count_reports(
        db=db,
        status=status,
        report_type=report_type,
        format=format,
        generated_by=generated_by
    )
    return ReportListResponse(
        reports=[ReportSummary.model_validate(r) for r in reports],
        total=total,
        page=1 + (skip // limit),
        page_size=limit
    )


@router.post("/{report_id}/generate", response_model=ReportResponse)
def generate_report(
    report_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Trigger report generation

    This starts the async report generation process.
    The actual PDF/HTML/Excel generation will be done in a background task.
    """
    report = report_service.generate_report(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )
    return report


# ==================== Template Endpoints ====================

@router.post("/templates", response_model=ReportTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    template: ReportTemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new report template"""
    return template_service.create_template(
        db=db,
        name=template.name,
        template_type=template.template_type,
        sections=template.sections,
        created_by=template.created_by,
        **template.model_dump(exclude={"name", "template_type", "sections", "created_by"}, exclude_unset=True)
    )


@router.get("/templates/{template_id}", response_model=ReportTemplateResponse)
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a template by ID"""
    template = template_service.get_template(db, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found"
        )
    return template


@router.get("/templates", response_model=TemplateListResponse)
def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    template_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """List all report templates with filters"""
    templates = template_service.list_templates(
        db=db,
        skip=skip,
        limit=limit,
        template_type=template_type,
        is_active=is_active
    )
    total = len(templates)
    return TemplateListResponse(
        templates=[ReportTemplateSummary.model_validate(t) for t in templates],
        total=total,
        page=1 + (skip // limit),
        page_size=limit
    )


@router.patch("/templates/{template_id}", response_model=ReportTemplateResponse)
def update_template(
    template_id: UUID,
    template: ReportTemplateUpdate,
    db: Session = Depends(get_db)
):
    """Update a report template"""
    updated_template = template_service.update_template(
        db=db,
        template_id=template_id,
        **template.model_dump(exclude_unset=True)
    )
    if not updated_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found"
        )
    return updated_template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a report template"""
    success = template_service.delete_template(db, template_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found"
        )
    return None


# ==================== Comparison Endpoints ====================

@router.post("/comparisons", response_model=ReportComparisonResponse, status_code=status.HTTP_201_CREATED)
def create_comparison(
    comparison: ReportComparisonCreate,
    db: Session = Depends(get_db)
):
    """Create a new comparison analysis"""
    return comparison_service.create_comparison(
        db=db,
        name=comparison.name,
        baseline_plan_id=comparison.baseline_plan_id,
        comparison_plan_ids=comparison.comparison_plan_ids,
        created_by=comparison.created_by,
        **comparison.model_dump(exclude={"name", "baseline_plan_id", "comparison_plan_ids", "created_by"}, exclude_unset=True)
    )


@router.get("/comparisons/{comparison_id}", response_model=ReportComparisonResponse)
def get_comparison(
    comparison_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a comparison by ID"""
    comparison = comparison_service.get_comparison(db, comparison_id)
    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comparison {comparison_id} not found"
        )
    return comparison


@router.get("/comparisons", response_model=ComparisonListResponse)
def list_comparisons(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    created_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all comparison analyses with filters"""
    comparisons = comparison_service.list_comparisons(
        db=db,
        skip=skip,
        limit=limit,
        created_by=created_by
    )
    total = len(comparisons)
    return ComparisonListResponse(
        comparisons=[ReportComparisonResponse.model_validate(c) for c in comparisons],
        total=total,
        page=1 + (skip // limit),
        page_size=limit
    )


@router.post("/comparisons/{comparison_id}/analyze", response_model=ReportComparisonResponse)
def analyze_comparison(
    comparison_id: UUID,
    db: Session = Depends(get_db)
):
    """Perform statistical comparison analysis"""
    comparison = comparison_service.perform_comparison_analysis(db, comparison_id)
    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comparison {comparison_id} not found"
        )
    return comparison


# ==================== Schedule Endpoints ====================

@router.post("/schedules", response_model=ReportScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    schedule: ReportScheduleCreate,
    db: Session = Depends(get_db)
):
    """Create a new report schedule"""
    return schedule_service.create_schedule(
        db=db,
        name=schedule.name,
        template_id=schedule.template_id,
        report_type=schedule.report_type,
        schedule_type=schedule.schedule_type,
        created_by=schedule.created_by,
        **schedule.model_dump(exclude={"name", "template_id", "report_type", "schedule_type", "created_by"}, exclude_unset=True)
    )


@router.get("/schedules/{schedule_id}", response_model=ReportScheduleResponse)
def get_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a schedule by ID"""
    schedule = schedule_service.get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    return schedule


@router.get("/schedules", response_model=ScheduleListResponse)
def list_schedules(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """List all report schedules with filters"""
    schedules = schedule_service.list_schedules(
        db=db,
        skip=skip,
        limit=limit,
        is_active=is_active
    )
    total = len(schedules)
    return ScheduleListResponse(
        schedules=[ReportScheduleResponse.model_validate(s) for s in schedules],
        total=total,
        page=1 + (skip // limit),
        page_size=limit
    )


@router.patch("/schedules/{schedule_id}", response_model=ReportScheduleResponse)
def update_schedule(
    schedule_id: UUID,
    schedule: ReportScheduleUpdate,
    db: Session = Depends(get_db)
):
    """Update a report schedule"""
    updated_schedule = schedule_service.update_schedule(
        db=db,
        schedule_id=schedule_id,
        **schedule.model_dump(exclude_unset=True)
    )
    if not updated_schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    return updated_schedule


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a report schedule"""
    success = schedule_service.delete_schedule(db, schedule_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    return None


# ==================== Statistics Endpoints ====================

@router.post("/statistics/compare", response_model=StatisticsCompareResponse)
def compare_reports_statistics(
    request: StatisticsCompareRequest,
    db: Session = Depends(get_db)
):
    """
    Compare multiple reports with statistical analysis

    Performs statistical comparison across multiple reports, calculating:
    - Basic statistics (mean, median, std, min, max) for each metric
    - Confidence intervals
    - Coefficient of variation
    - Identifies significant differences between reports

    Returns detailed comparison results for each metric.
    """
    from datetime import datetime

    # Validate all reports exist
    for report_id in request.report_ids:
        report = report_service.get_report(db, report_id)
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report {report_id} not found"
            )

    # Perform comparison analysis
    comparison_data = statistics_service.compare_reports(
        report_ids=[str(rid) for rid in request.report_ids],
        metrics=request.metrics,
        group_by=request.group_by,
        confidence_level=request.confidence_level
    )

    # Build response
    comparison_results = []
    for metric_name, metric_data in comparison_data["metrics"].items():
        # Build report statistics
        report_stats = {}
        for report_id in request.report_ids:
            rid_str = str(report_id)
            if rid_str in metric_data.get("by_report", {}):
                stats = metric_data["by_report"][rid_str]
                report_stats[rid_str] = MetricStatistics(
                    metric_name=metric_name,
                    mean=stats["mean"],
                    median=stats["median"],
                    std=stats["std"],
                    min=stats["min"],
                    max=stats["max"],
                    range=stats["range"],
                    count=stats["count"],
                    percentiles=stats.get("percentiles"),
                    confidence_interval=stats.get("confidence_interval")
                )

        comparison_results.append(ComparisonResult(
            metric_name=metric_name,
            report_statistics=report_stats,
            overall_mean=metric_data["overall"]["mean"],
            overall_std=metric_data["overall"]["std"],
            coefficient_of_variation=metric_data["overall"]["coefficient_of_variation"],
            significant_differences=metric_data.get("significant_differences")
        ))

    return StatisticsCompareResponse(
        report_ids=request.report_ids,
        metrics_compared=list(comparison_data["metrics"].keys()),
        comparison_results=comparison_results,
        summary=comparison_data.get("summary", {}),
        generated_at=datetime.utcnow()
    )


@router.post("/statistics/benchmark", response_model=BenchmarkResponse)
def benchmark_report_performance(
    request: BenchmarkRequest,
    db: Session = Depends(get_db)
):
    """
    Benchmark a report against reference data

    Compares a single report's metrics against reference reports (or all reports
    of the same type), calculating:
    - Percentile rankings for each metric
    - Performance ratings (excellent/good/average/below_average/poor)
    - Z-scores relative to reference data

    This is useful for performance evaluation and quality assessment.
    """
    from datetime import datetime

    # Validate report exists
    report = report_service.get_report(db, request.report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {request.report_id} not found"
        )

    # Validate reference reports if provided
    reference_ids = None
    if request.reference_report_ids:
        for ref_id in request.reference_report_ids:
            ref_report = report_service.get_report(db, ref_id)
            if not ref_report:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Reference report {ref_id} not found"
                )
        reference_ids = [str(rid) for rid in request.reference_report_ids]

    # Perform benchmark analysis
    benchmark_data = statistics_service.benchmark_performance(
        report_id=str(request.report_id),
        reference_report_ids=reference_ids,
        metrics=request.metrics
    )

    # Build benchmark metrics
    benchmark_metrics = []
    for metric in benchmark_data["metrics"]:
        benchmark_metrics.append(BenchmarkMetric(
            metric_name=metric["metric_name"],
            value=metric["value"],
            percentile_rank=metric["percentile_rank"],
            performance_rating=metric["performance_rating"],
            reference_mean=metric["reference_mean"],
            reference_std=metric["reference_std"],
            z_score=metric["z_score"]
        ))

    return BenchmarkResponse(
        report_id=request.report_id,
        reference_count=benchmark_data["reference_count"],
        benchmark_metrics=benchmark_metrics,
        overall_percentile=benchmark_data["overall_percentile"],
        overall_rating=benchmark_data["overall_rating"],
        summary=benchmark_data["summary"],
        generated_at=datetime.utcnow()
    )


@router.post("/statistics/time-series", response_model=TimeSeriesResponse)
def analyze_time_series_metric(
    request: TimeSeriesRequest,
    db: Session = Depends(get_db)
):
    """
    Perform time series analysis on a metric

    Analyzes how a specific metric changes over time across multiple test
    executions of a test plan. Provides:
    - Time series data points with anomaly detection
    - Trend analysis (increasing/decreasing/stable)
    - Rolling mean and standard deviation
    - Statistical summary

    Useful for tracking performance degradation, regression testing, and
    identifying anomalous test results.
    """
    from datetime import datetime

    # Note: For time series we need test execution data, not just report data
    # This would typically query the test_execution table
    # For now, we'll return a mock response structure

    # Perform time series analysis
    time_series_data = statistics_service.analyze_time_series(
        test_plan_id=str(request.test_plan_id),
        metric_name=request.metric_name,
        start_date=request.start_date,
        end_date=request.end_date,
        window_size=request.window_size,
        anomaly_threshold=request.anomaly_threshold
    )

    # Build data points
    data_points = []
    for point in time_series_data["data_points"]:
        data_points.append(TimeSeriesPoint(
            timestamp=point["timestamp"],
            value=point["value"],
            execution_id=UUID(point["execution_id"]),
            is_anomaly=point.get("is_anomaly", False),
            z_score=point.get("z_score")
        ))

    # Build trend analysis
    trend_data = time_series_data["trend"]
    trend = TrendAnalysis(
        direction=trend_data["direction"],
        slope=trend_data["slope"],
        r_squared=trend_data["r_squared"],
        strength=trend_data["strength"]
    )

    # Build statistics
    stats_data = time_series_data["statistics"]
    statistics = MetricStatistics(
        metric_name=request.metric_name,
        mean=stats_data["mean"],
        median=stats_data["median"],
        std=stats_data["std"],
        min=stats_data["min"],
        max=stats_data["max"],
        range=stats_data["range"],
        count=stats_data["count"],
        percentiles=stats_data.get("percentiles"),
        confidence_interval=stats_data.get("confidence_interval")
    )

    return TimeSeriesResponse(
        test_plan_id=request.test_plan_id,
        metric_name=request.metric_name,
        data_points=data_points,
        trend=trend,
        anomalies=time_series_data["anomalies"],
        statistics=statistics,
        rolling_mean=time_series_data["rolling_mean"],
        rolling_std=time_series_data["rolling_std"],
        generated_at=datetime.utcnow()
    )


# ==================== Generic Report Operations (Must be last) ====================

@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a report by ID"""
    report = report_service.get_report(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )
    return report


@router.get("/{report_id}/download")
def download_report(
    report_id: UUID,
    db: Session = Depends(get_db)
):
    """Download a generated report file"""
    from fastapi.responses import FileResponse
    import os

    report = report_service.get_report(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )

    if report.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is not ready for download. Status: {report.status}"
        )

    if not report.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found"
        )

    # file_path is stored as relative path like "data/reports/{id}/report_{id}.pdf"
    # Check if it's absolute or relative
    if os.path.isabs(report.file_path):
        full_path = report.file_path
    else:
        full_path = report.file_path

    if not os.path.exists(full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report file not found on disk: {full_path}"
        )

    # Determine media type based on format
    media_types = {
        "pdf": "application/pdf",
        "html": "text/html",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
    media_type = media_types.get(report.format, "application/octet-stream")

    # Generate filename
    safe_title = "".join(c for c in report.title if c.isalnum() or c in " _-").strip()
    extension = "xlsx" if report.format == "excel" else report.format
    filename = f"{safe_title}_{report_id}.{extension}"

    return FileResponse(
        path=full_path,
        media_type=media_type,
        filename=filename
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a report"""
    success = report_service.delete_report(db, report_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )
    return None

