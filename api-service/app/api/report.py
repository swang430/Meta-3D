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
    MetricStatistics,
    ComparisonResult,
    BenchmarkMetric,
    TimeSeriesPoint,
    TrendAnalysis,
    KPIDifference,
)
from app.services.report_service import (
    LegacyMimoRegenerationRejected,
    ReportGenerationConflict,
    ReportService,
    ReportTemplateService,
    ReportComparisonService,
    ReportScheduleService,
    legacy_mimo_regeneration_error,
    report_is_mimo_ota_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# Service instances
report_service = ReportService()
template_service = ReportTemplateService()
comparison_service = ReportComparisonService()
schedule_service = ReportScheduleService()


def _is_mimo_report(db: Session, report) -> bool:
    return report_is_mimo_ota_report(db, report)


def _mimo_report_is_provenance_sanitized(db: Session, report) -> bool:
    """Legacy MIMO artifacts are inaccessible until rebuilt safely.

    New/rebuilt reports stamp a trust schema version and either preserve formal
    KPI data (explicit-real calibration) or replace it with UNKNOWN/N/A. Old
    artifacts lack that proof and therefore fail closed.
    """
    content = report.content_data or {}
    if not _is_mimo_report(db, report):
        return True
    return content.get("calibration_trust_schema_version") == 1


def _reject_untrusted_mimo_report(db: Session, report) -> None:
    if _mimo_report_is_provenance_sanitized(db, report):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Legacy MIMO OTA report cannot be viewed or downloaded until its "
            "path-loss provenance is sanitized. Regenerate the report to "
            "produce an UNKNOWN/N/A audit record, or re-run the measurement "
            "with a real calibration for a formal result."
        ),
    )


def _report_summary(db: Session, report) -> ReportSummary:
    """Build list metadata from the same MIMO trust truth as detail/download."""
    summary = ReportSummary.model_validate(report)
    if _mimo_report_is_provenance_sanitized(db, report):
        return summary

    regeneration_error = legacy_mimo_regeneration_error(db, report)
    if regeneration_error:
        return summary.model_copy(update={
            "requires_regeneration": True,
            "regeneration_available": False,
            "regeneration_reason": regeneration_error,
        })

    return summary.model_copy(update={
        "requires_regeneration": True,
        "regeneration_available": True,
        "regeneration_reason": (
            "Regenerate to produce a provenance-sanitized UNKNOWN/N/A audit report."
        ),
    })


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
        # Unified report content
        content_data=report.content_data,
        road_test_execution_id=report.road_test_execution_id,
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
        reports=[_report_summary(db, report) for report in reports],
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
    try:
        report = report_service.generate_report(db, report_id)
    except (ReportGenerationConflict, LegacyMimoRegenerationRejected) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )
    _reject_untrusted_mimo_report(db, report)
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
    _reject_untrusted_mimo_report(db, report)
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

    _reject_untrusted_mimo_report(db, report)

    if not report.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found"
        )

    # file_path is stored as relative path like "data/reports/{id}/report_{id}.pdf"
    # Check if it's absolute or relative and resolve accordingly
    if os.path.isabs(report.file_path):
        full_path = report.file_path
    else:
        # Convert relative path to absolute path based on current working directory
        full_path = os.path.abspath(report.file_path)

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
        filename=filename,
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


# ==================== Simple Compare Endpoint ====================
