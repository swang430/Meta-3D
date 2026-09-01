"""Report API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.models.test_plan import TestExecution
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
    LegacyVrtArchiveRejected,
    ReportGenerationConflict,
    RoadTestReportConflict,
    ReportService,
    ReportTemplateService,
    ReportComparisonService,
    ReportScheduleService,
    _parse_report_execution_ids,
    legacy_mimo_regeneration_error,
    normalized_report_execution_ids,
    report_has_provenance_trust,
    report_has_vrt_archive_trust,
    report_is_mimo_ota_report,
)
from app.services.execution_evidence_outcome import (
    ExecutionEvidenceOutcome,
    project_execution_evidence_outcome,
)
from app.hal.base_station_compatibility import canonical_payload_digest

router = APIRouter(prefix="/reports", tags=["reports"])

# Service instances
report_service = ReportService()
template_service = ReportTemplateService()
comparison_service = ReportComparisonService()
schedule_service = ReportScheduleService()


def _is_mimo_report(db: Session, report) -> bool:
    return report_is_mimo_ota_report(db, report)


def _invalid_report_outcome(expected, reason: str) -> ExecutionEvidenceOutcome:
    completion = (
        "not_completed"
        if expected.pipeline_status != "completed"
        else "pipeline_completed"
    )
    return expected.model_copy(
        update={
            "compatibility_classification": "invalid",
            "completion_semantic": completion,
            "formal_eligible": False,
            "reasons": tuple(dict.fromkeys((*expected.reasons, reason))),
        }
    )


def _invalid_report_source_shape(report, reason: str) -> ExecutionEvidenceOutcome:
    raw_status = getattr(report, "status", None)
    pipeline_status = str(getattr(raw_status, "value", raw_status) or "unknown")
    return ExecutionEvidenceOutcome(
        compatibility_classification="invalid",
        completion_semantic=(
            "pipeline_completed"
            if pipeline_status == "completed"
            else "not_completed"
        ),
        formal_eligible=False,
        compatibility_digest=canonical_payload_digest({
            "report_execution_sources": "invalid",
            "reason": reason,
        }),
        qualification_classification="legacy",
        reasons=(reason,),
        pipeline_status=pipeline_status,
    )


def _aggregate_report_execution_outcomes(
    execution_ids: list[UUID],
    executions: list[TestExecution | None],
) -> ExecutionEvidenceOutcome:
    """Project every linked execution into one conservative report outcome."""

    projected: list[tuple[UUID, ExecutionEvidenceOutcome]] = []
    missing_ids: list[UUID] = []
    for execution_id, execution in zip(execution_ids, executions, strict=True):
        if execution is None:
            missing_ids.append(execution_id)
        else:
            projected.append(
                (execution_id, project_execution_evidence_outcome(execution))
            )

    outcomes = [outcome for _, outcome in projected]
    classifications = {outcome.compatibility_classification for outcome in outcomes}
    if missing_ids or "invalid" in classifications:
        classification = "invalid"
    elif "diagnostic" in classifications:
        classification = "diagnostic"
    elif "legacy" in classifications:
        classification = "legacy"
    else:
        classification = "compatible"

    qualification_classifications = {
        outcome.qualification_classification for outcome in outcomes
    }
    if "diagnostic" in qualification_classifications:
        qualification = "diagnostic"
    elif outcomes and qualification_classifications == {"formal"}:
        qualification = "formal"
    else:
        qualification = "legacy"

    statuses = [outcome.pipeline_status for outcome in outcomes]
    all_completed = (
        not missing_ids
        and len(outcomes) == len(execution_ids)
        and all(status == "completed" for status in statuses)
    )
    formal_eligible = (
        all_completed
        and classification == "compatible"
        and all(outcome.formal_eligible for outcome in outcomes)
    )
    if not all_completed:
        completion = "not_completed"
    elif formal_eligible:
        completion = "valid_test_completed"
    elif classification == "diagnostic":
        completion = "diagnostic_completed"
    else:
        completion = "pipeline_completed"

    reasons = [
        f"execution {execution_id}: {reason}"
        for execution_id, outcome in projected
        for reason in outcome.reasons
    ]
    reasons.extend(
        f"execution {execution_id}: source execution is unavailable"
        for execution_id in missing_ids
    )
    aggregate_payload = [
        {
            "execution_id": str(execution_id),
            "outcome": outcome.model_dump(mode="json"),
        }
        for execution_id, outcome in projected
    ]
    aggregate_payload.extend(
        {"execution_id": str(execution_id), "outcome": None}
        for execution_id in missing_ids
    )
    pipeline_status = (
        statuses[0]
        if statuses and len(set(statuses)) == 1 and not missing_ids
        else "mixed"
    )
    return ExecutionEvidenceOutcome(
        compatibility_classification=classification,
        completion_semantic=completion,
        formal_eligible=formal_eligible,
        compatibility_digest=canonical_payload_digest(aggregate_payload),
        qualification_classification=qualification,
        reasons=tuple(dict.fromkeys(reasons)),
        pipeline_status=pipeline_status,
    )


def _report_execution_outcome_state(
    db: Session,
    report,
) -> tuple[ExecutionEvidenceOutcome | None, bool]:
    """Compare stored frozen evidence with its authoritative source execution."""

    content = report.content_data if isinstance(report.content_data, dict) else {}
    raw = content.get("execution_evidence_outcome")
    try:
        stored = (
            ExecutionEvidenceOutcome.model_validate(raw)
            if raw is not None
            else None
        )
    except (ValueError, TypeError):
        stored = None

    execution_ids, execution_ids_well_formed = _parse_report_execution_ids(report)
    query = getattr(db, "query", None)
    get = getattr(db, "get", None)
    if not callable(query) and not callable(get):
        return stored, raw is None or stored is not None
    if not execution_ids_well_formed:
        return (
            _invalid_report_source_shape(
                report,
                "report TestExecution identifiers are malformed",
            ),
            False,
        )
    if len(set(execution_ids)) != len(execution_ids):
        return (
            _invalid_report_source_shape(
                report,
                "report TestExecution identifiers are not unique",
            ),
            False,
        )
    if not execution_ids and _is_mimo_report(db, report):
        return (
            _invalid_report_source_shape(
                report,
                "MIMO report has no linked TestExecution",
            ),
            False,
        )
    if len(execution_ids) > 1:
        executions = [
            (
                get(TestExecution, execution_id)
                if callable(get)
                else query(TestExecution)
                .filter(TestExecution.id == execution_id)
                .first()
            )
            for execution_id in execution_ids
        ]
        aggregate = _aggregate_report_execution_outcomes(
            execution_ids,
            executions,
        )
        if raw is None:
            return aggregate, False
        if stored == aggregate and aggregate.formal_eligible:
            return aggregate, True
        return (
            _invalid_report_outcome(
                aggregate,
                "stored report outcome does not match all source executions",
            ),
            False,
        )
    if len(execution_ids) != 1:
        if raw is None:
            return None, True
        if stored is None:
            return None, False
        return (
            _invalid_report_outcome(
                stored,
                "stored report outcome has no unique source execution",
            ),
            False,
        )
    execution = (
        get(TestExecution, execution_ids[0])
        if callable(get)
        else query(TestExecution)
        .filter(TestExecution.id == execution_ids[0])
        .first()
    )
    if execution is None:
        if _is_mimo_report(db, report):
            return (
                _invalid_report_source_shape(
                    report,
                    "MIMO report source execution is unavailable",
                ),
                False,
            )
        if raw is None:
            return None, True
        if stored is None:
            return None, False
        return (
            _invalid_report_outcome(
                stored,
                "stored report outcome source execution is missing",
            ),
            False,
        )

    expected = project_execution_evidence_outcome(execution)
    if raw is None:
        if expected.compatibility_classification == "legacy":
            return expected, True
        return (
            _invalid_report_outcome(
                expected,
                "stored report execution evidence outcome is missing",
            ),
            False,
        )
    if stored is None:
        return (
            _invalid_report_outcome(
                expected,
                "stored report execution evidence outcome is malformed",
            ),
            False,
        )
    # REPORT runs while the execution row is still ``running``; the case
    # runner publishes the terminal status only after REPORT succeeds.  The
    # compatibility and qualification evidence is already frozen at that
    # point, but the three lifecycle-derived fields legitimately change once
    # from running -> terminal.  Compare only the immutable evidence identity
    # and always return the current source projection.  Any evidence/digest
    # drift remains fail-closed.
    stored_evidence = (
        stored.compatibility_classification,
        stored.compatibility_digest,
        stored.qualification_classification,
        stored.reasons,
    )
    expected_evidence = (
        expected.compatibility_classification,
        expected.compatibility_digest,
        expected.qualification_classification,
        expected.reasons,
    )
    if stored_evidence != expected_evidence:
        return (
            _invalid_report_outcome(
                expected,
                "stored report execution evidence outcome drifted",
            ),
            False,
        )
    if stored == expected:
        return expected, True
    expected_terminal_transition = (
        stored.pipeline_status == "running"
        and stored.completion_semantic == "not_completed"
        and stored.formal_eligible is False
        and expected.pipeline_status == "completed"
    )
    if expected_terminal_transition:
        return expected, True
    return (
        _invalid_report_outcome(
            expected,
            "stored report execution lifecycle drifted unexpectedly",
        ),
        False,
    )


def _mimo_report_is_provenance_sanitized(db: Session, report) -> bool:
    """Legacy MIMO artifacts are inaccessible until rebuilt safely.

    New/rebuilt reports stamp a trust schema version and either preserve formal
    KPI data (explicit-real calibration) or replace it with UNKNOWN/N/A. Old
    artifacts lack that proof and therefore fail closed.
    """
    content = report.content_data if isinstance(report.content_data, dict) else {}
    if not _is_mimo_report(db, report):
        return True
    _, outcome_matches = _report_execution_outcome_state(db, report)
    return report_has_provenance_trust(content) and outcome_matches


def _reject_untrusted_mimo_report(db: Session, report) -> None:
    if _mimo_report_is_provenance_sanitized(db, report):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Legacy MIMO OTA report cannot be viewed or downloaded until its "
            "path-loss, throughput, and RF-KPI provenance are sanitized. Regenerate the report to "
            "produce an UNKNOWN/N/A audit record, or re-run the measurement "
            "with a real calibration and valid throughput/RF-KPI samples for a formal result."
        ),
    )


def _reject_untrusted_vrt_report(report) -> None:
    if getattr(report, "road_test_execution_id", None) is None:
        return
    if report_has_vrt_archive_trust(report.content_data):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Historical VRT report content is not server-owned. Rebuild it from "
            "the terminal execution before viewing or downloading the artifact."
        ),
    )


def _report_summary(db: Session, report) -> ReportSummary:
    """Build list metadata from the same MIMO trust truth as detail/download."""
    evidence_outcome, _ = _report_execution_outcome_state(db, report)
    summary = ReportSummary.model_validate({
        "id": report.id,
        "title": report.title,
        "report_type": report.report_type,
        "format": report.format,
        "status": report.status,
        "progress_percent": report.progress_percent,
        "file_size_bytes": report.file_size_bytes,
        "generated_by": report.generated_by,
        "generated_at": report.generated_at,
        "test_execution_ids": normalized_report_execution_ids(report),
        "road_test_execution_id": report.road_test_execution_id,
        "vrt_archive_trusted": (
            report.road_test_execution_id is None
            or report_has_vrt_archive_trust(report.content_data)
        ),
        "execution_evidence_outcome": evidence_outcome,
    })
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


def _report_with_current_execution_outcome(db: Session, report):
    """Attach the source execution's current server-owned projection."""

    outcome, _ = _report_execution_outcome_state(db, report)
    # SQLAlchemy model instances accept non-mapped response-only attributes;
    # they are never persisted and Pydantic reads them via from_attributes.
    setattr(report, "execution_evidence_outcome", outcome)
    return report


# ==================== Report Endpoints ====================

@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    report: ReportCreate,
    db: Session = Depends(get_db)
):
    """Create a new test report"""
    if (
        isinstance(report.content_data, dict)
        and "execution_evidence_outcome" in report.content_data
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "execution_evidence_outcome is server-owned and cannot be "
                "submitted in report content"
            ),
        )
    if report.road_test_execution_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "VRT reports are created from the authoritative terminal archive; "
                "the generic report endpoint cannot claim a road-test execution."
            ),
        )
    try:
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
    except RoadTestReportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    except (
        ReportGenerationConflict,
        LegacyMimoRegenerationRejected,
        LegacyVrtArchiveRejected,
    ) as exc:
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
    _reject_untrusted_vrt_report(report)
    return _report_with_current_execution_outcome(db, report)


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
    """Create a new execution-level comparison（P1-72 对比换源）。

    参与 execution 必须全部存在，否则 422 fail-loud。
    """
    try:
        return comparison_service.create_comparison(
            db=db,
            name=comparison.name,
            baseline_execution_id=comparison.baseline_execution_id,
            comparison_execution_ids=comparison.comparison_execution_ids,
            created_by=comparison.created_by,
            **comparison.model_dump(
                exclude={
                    "name", "baseline_execution_id",
                    "comparison_execution_ids", "created_by",
                },
                exclude_unset=True,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
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
    """Perform execution-level comparison analysis（P1-72 实现）。

    产出指标差分 + provenance formal 判定；全部 execution 同属一个 TestCase
    时同步落 repeatability_tests 对齐记录。plan 级历史对比 / 缺指标的
    execution → 422 fail-loud。
    """
    try:
        comparison = comparison_service.perform_comparison_analysis(db, comparison_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
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
    _reject_untrusted_vrt_report(report)
    return _report_with_current_execution_outcome(db, report)


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
    _reject_untrusted_vrt_report(report)

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
