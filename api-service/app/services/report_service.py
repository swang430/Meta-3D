"""Report Generation Services"""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import os
import logging
import json
import math

from sqlalchemy import String, cast

from app.models.report import (
    TestReport,
    ReportTemplate,
    ReportComparison,
    ReportSchedule,
    ReportStatus,
    ReportType,
    ReportFormat,
)
from app.models.test_plan import TestPlan, TestCase, TestExecution
from app.services.pdf_generator import PDFGenerator
from app.services.report_data_collector import ReportDataCollector
from app.services.mimo_ota.path_loss_application import (
    parse_path_loss_application,
    path_loss_application_is_formally_verified,
)
from app.services.mimo_ota.rf_kpi_trust import (
    RF_KPI_TRUST_SCHEMA_VERSION,
    parse_rf_kpi_trust,
    rf_kpi_trust_is_formally_verified,
    trusted_rf_kpi_values,
)
from app.services.mimo_ota.quiet_zone_evidence import (
    QUIET_ZONE_EVIDENCE_SCHEMA_VERSION,
    parse_quiet_zone_evidence,
    quiet_zone_evidence_is_formally_verified,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    BASE_STATION_EXECUTION_EVIDENCE_FIELD,
    MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD,
    _LEGACY_METRIC_UNITS,
    BaseStationExecutionEvidence,
    FormalMetricTrust,
    PositionSnapshot,
    base_station_expected_scope_from_evidence,
    base_station_metric_projection_required,
    canonical_snapshot_digest,
    project_base_station_metrics_by_position,
)
from app.services.execution_evidence_outcome import (
    execution_evidence_blocks_formal_outputs,
    project_execution_evidence_outcome,
)

logger = logging.getLogger(__name__)


class ReportGenerationConflict(ValueError):
    """Another request already owns generation for this report."""


class LegacyMimoRegenerationRejected(ValueError):
    """A legacy MIMO report cannot be regenerated safely."""


class LegacyVrtArchiveRejected(ValueError):
    """A historical VRT row lacks server-owned archive provenance."""


class RoadTestReportConflict(ValueError):
    """A VRT execution already has its single report artifact."""


_SERVER_OWNED_REPORT_TRUST_FIELDS = frozenset({
    "report_family",
    "calibration_trust_schema_version",
    "formal_path_loss_verified",
    "path_loss_application",
    "throughput_trust_schema_version",
    "formal_throughput_verified",
    "throughput_scope",
    "rf_kpi_trust_schema_version",
    "rf_kpi_trust",
    "formal_rf_kpi_verified",
    "quiet_zone_evidence_schema_version",
    "quiet_zone_evidence",
    "formal_quiet_zone_verified",
    "base_station_metric_trust_schema_version",
    "base_station_metric_projection",
    "base_station_metric_projection_attestation",
    "vrt_archive_trust_schema_version",
})

THROUGHPUT_TRUST_SCHEMA_VERSION = 2
THROUGHPUT_TRUST_FIELD = "throughput_trust_schema_version"
VRT_ARCHIVE_TRUST_SCHEMA_VERSION = 1
VRT_ARCHIVE_TRUST_FIELD = "vrt_archive_trust_schema_version"
BASE_STATION_METRIC_TRUST_SCHEMA_VERSION = 1
_UNCONDITIONAL_REPORT_SNAPSHOT = object()


def build_base_station_metric_projection_attestation(
    evidence: Any,
    projection: Any,
) -> dict[str, Any] | None:
    """Bind a server-written generic projection to its frozen evidence."""

    if not isinstance(evidence, dict):
        return None
    parsed = BaseStationExecutionEvidence.model_validate(evidence)
    registry = parsed.metric_registry
    if registry is not None:
        capabilities = {item.key: item for item in registry.metrics}
        if not isinstance(projection, list):
            raise ValueError("base-station metric projection must be a list")
        for row in projection:
            raw_metrics = row.get("metrics") if isinstance(row, dict) else None
            if not isinstance(raw_metrics, dict) or set(raw_metrics) != set(
                capabilities
            ):
                raise ValueError(
                    "base-station metric projection disagrees with frozen registry"
                )
            for key, raw_metric in raw_metrics.items():
                metric = FormalMetricTrust.model_validate(raw_metric)
                capability = capabilities[key]
                if metric.unit not in {None, capability.unit} or (
                    metric.status == "trusted"
                    and capability.evidence != "authoritative"
                ):
                    raise ValueError(
                        "base-station metric projection semantics drifted"
                    )
    else:
        if not isinstance(projection, list):
            raise ValueError("base-station metric projection must be a list")
        for row in projection:
            raw_metrics = row.get("metrics") if isinstance(row, dict) else None
            if not isinstance(raw_metrics, dict) or set(raw_metrics) != set(
                _LEGACY_METRIC_UNITS
            ):
                raise ValueError(
                    "legacy base-station projection has unexpected metrics"
                )
            for key, raw_metric in raw_metrics.items():
                metric = FormalMetricTrust.model_validate(raw_metric)
                if metric.unit not in {None, _LEGACY_METRIC_UNITS[key]}:
                    raise ValueError(
                        "legacy base-station projection semantics drifted"
                    )
    evidence_payload = parsed.model_dump(mode="json")
    evidence_digest = canonical_snapshot_digest(evidence_payload)
    registry_digest = (
        parsed.metric_registry.digest
        if parsed.metric_registry_contract_version == 1
        and parsed.metric_registry is not None
        else None
    )
    projection_digest = canonical_snapshot_digest(
        {
            "evidence_digest": evidence_digest,
            "metric_registry_digest": registry_digest,
            "projection": projection,
        }
    )
    return {
        "schema_version": 1,
        "evidence_digest": evidence_digest,
        "metric_registry_digest": registry_digest,
        "projection_digest": projection_digest,
    }


def _strip_untrusted_report_attestation(
    content_data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Creation payloads cannot self-attest provenance-aware generation.

    The MIMO builder writes these fields only after rebuilding content from the
    linked TestExecution. Keeping them out of pending report rows makes the
    read/download allowlist a server-owned transition rather than client JSON.
    """
    if not isinstance(content_data, dict):
        return content_data
    return {
        key: value
        for key, value in content_data.items()
        if key not in _SERVER_OWNED_REPORT_TRUST_FIELDS
    }


def report_has_provenance_trust(content_data: Any) -> bool:
    """Accept only a complete, internally consistent server trust envelope."""
    if not isinstance(content_data, dict):
        return False
    calibration_marker = content_data.get("calibration_trust_schema_version")
    throughput_marker = content_data.get(THROUGHPUT_TRUST_FIELD)
    raw_application = content_data.get("path_loss_application")
    formal_path_loss_verified = content_data.get("formal_path_loss_verified")
    rf_kpi_marker = content_data.get("rf_kpi_trust_schema_version")
    raw_rf_kpi_trust = content_data.get("rf_kpi_trust")
    formal_rf_kpi_verified = content_data.get("formal_rf_kpi_verified")
    quiet_zone_marker = content_data.get("quiet_zone_evidence_schema_version")
    raw_quiet_zone_evidence = content_data.get("quiet_zone_evidence")
    formal_quiet_zone_verified = content_data.get("formal_quiet_zone_verified")
    base_station_marker = content_data.get(
        "base_station_metric_trust_schema_version"
    )
    base_station_projection = content_data.get("base_station_metric_projection")
    base_station_attestation = content_data.get(
        "base_station_metric_projection_attestation"
    )
    application_is_well_formed = (
        isinstance(raw_application, dict)
        and parse_path_loss_application(raw_application) == raw_application
    )
    return (
        type(calibration_marker) is int
        and calibration_marker == 1
        and type(throughput_marker) is int
        and throughput_marker == THROUGHPUT_TRUST_SCHEMA_VERSION
        and application_is_well_formed
        and type(formal_path_loss_verified) is bool
        and (
            formal_path_loss_verified
            is path_loss_application_is_formally_verified(raw_application)
        )
        and type(rf_kpi_marker) is int
        and rf_kpi_marker == RF_KPI_TRUST_SCHEMA_VERSION
        and isinstance(raw_rf_kpi_trust, dict)
        and parse_rf_kpi_trust(raw_rf_kpi_trust) == raw_rf_kpi_trust
        and type(formal_rf_kpi_verified) is bool
        and (
            formal_rf_kpi_verified
            is rf_kpi_trust_is_formally_verified(raw_rf_kpi_trust)
        )
        and type(quiet_zone_marker) is int
        and quiet_zone_marker == QUIET_ZONE_EVIDENCE_SCHEMA_VERSION
        and isinstance(raw_quiet_zone_evidence, dict)
        and parse_quiet_zone_evidence(raw_quiet_zone_evidence)
        == raw_quiet_zone_evidence
        and type(formal_quiet_zone_verified) is bool
        and (
            formal_quiet_zone_verified
            is quiet_zone_evidence_is_formally_verified(raw_quiet_zone_evidence)
        )
        and type(base_station_marker) is int
        and base_station_marker == BASE_STATION_METRIC_TRUST_SCHEMA_VERSION
        and _base_station_projection_is_sanitized(
            base_station_projection,
            base_station_attestation,
        )
    )


def _base_station_projection_is_sanitized(
    value: Any,
    attestation: Any = None,
) -> bool:
    """Validate the exact server-written formal/diagnostic projection shape."""

    def compatibility_mirror_matches(
        metrics: dict[str, FormalMetricTrust],
        key: str,
        mirror: FormalMetricTrust,
    ) -> bool:
        registered = metrics.get(key)
        if registered is not None:
            return registered == mirror
        return (
            mirror.status == "unknown"
            and mirror.formal_value is None
            and mirror.diagnostic_value is None
            and mirror.unit is None
            and mirror.exchange_ids == ()
        )

    if not isinstance(value, list):
        return False
    generic_projection = False
    for row in value:
        if not isinstance(row, dict) or set(row) not in (
            {"position", "dl_throughput_mbps", "dl_bler_percent"},
            {
                "position",
                "metrics",
                "dl_throughput_mbps",
                "dl_bler_percent",
            },
        ):
            return False
        try:
            position = PositionSnapshot.model_validate(row["position"])
            throughput = FormalMetricTrust.model_validate(
                row["dl_throughput_mbps"]
            )
            bler = FormalMetricTrust.model_validate(row["dl_bler_percent"])
        except Exception:
            return False
        raw_metrics = row.get("metrics")
        parsed_metrics: dict[str, FormalMetricTrust] | None = None
        if raw_metrics is not None:
            generic_projection = True
            if not isinstance(raw_metrics, dict) or not raw_metrics:
                return False
            try:
                parsed_metrics = {
                    key: FormalMetricTrust.model_validate(metric)
                    for key, metric in raw_metrics.items()
                    if isinstance(key, str) and key
                }
            except Exception:
                return False
            if (
                len(parsed_metrics) != len(raw_metrics)
                or any(
                    parsed_metrics[key].model_dump(mode="json") != metric
                    for key, metric in raw_metrics.items()
                )
                or not compatibility_mirror_matches(
                    parsed_metrics, "dl_throughput_mbps", throughput
                )
                or not compatibility_mirror_matches(
                    parsed_metrics, "dl_bler_percent", bler
                )
            ):
                return False
        if (
            position.model_dump(mode="json") != row["position"]
            or throughput.model_dump(mode="json") != row["dl_throughput_mbps"]
            or bler.model_dump(mode="json") != row["dl_bler_percent"]
        ):
            return False
    if generic_projection:
        if not isinstance(attestation, dict) or set(attestation) != {
            "schema_version",
            "evidence_digest",
            "metric_registry_digest",
            "projection_digest",
        }:
            return False
        evidence_digest = attestation.get("evidence_digest")
        registry_digest = attestation.get("metric_registry_digest")
        projection_digest = attestation.get("projection_digest")
        if (
            type(attestation.get("schema_version")) is not int
            or attestation["schema_version"] != 1
            or not _is_sha256_digest(evidence_digest)
            or not (
                registry_digest is None
                or _is_sha256_digest(registry_digest)
            )
            or not _is_sha256_digest(projection_digest)
        ):
            return False
        expected_digest = canonical_snapshot_digest(
            {
                "evidence_digest": evidence_digest,
                "metric_registry_digest": registry_digest,
                "projection": value,
            }
        )
        if projection_digest != expected_digest:
            return False
    return True


def _is_sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def report_has_vrt_archive_trust(content_data: Any) -> bool:
    """Accept only the exact server-written JSON integer VRT marker."""
    if not isinstance(content_data, dict):
        return False
    marker = content_data.get(VRT_ARCHIVE_TRUST_FIELD)
    return type(marker) is int and marker == VRT_ARCHIVE_TRUST_SCHEMA_VERSION


def _parse_report_execution_ids(report: TestReport) -> tuple[List[UUID], bool]:
    """Parse the complete historical link set without dropping bad siblings."""
    raw_execution_ids = getattr(report, "test_execution_ids", None)
    if raw_execution_ids is None:
        return [], True
    if not isinstance(raw_execution_ids, list):
        return [], False
    execution_ids = []
    for raw_execution_id in raw_execution_ids:
        try:
            execution_ids.append(UUID(str(raw_execution_id)))
        except (TypeError, ValueError):
            return [], False
    return execution_ids, True


def normalized_report_execution_ids(report: TestReport) -> List[UUID]:
    """Return the full UUID link set, or none when any item is malformed."""
    execution_ids, well_formed = _parse_report_execution_ids(report)
    return execution_ids if well_formed else []


def is_mimo_ota_execution(db: Session, execution: TestExecution) -> bool:
    """Classify from the execution's server-side type truth, not report text."""
    config = execution.config if isinstance(execution.config, dict) else {}
    raw_descriptors = config.get("step_descriptors")
    descriptors = raw_descriptors if isinstance(raw_descriptors, list) else []
    if any(
        str(descriptor.get("type") or "").startswith("MIMO_OTA_")
        for descriptor in descriptors
        if isinstance(descriptor, dict)
    ):
        return True
    if execution.test_case_id is None:
        return False
    test_type = db.query(TestCase.test_type).filter(
        TestCase.id == execution.test_case_id
    ).scalar()
    return test_type == "MIMO_OTA"


def report_references_mimo_ota_execution(db: Session, report: TestReport) -> bool:
    """Conservatively identify any authoritative MIMO link in a JSON array.

    This is candidate classification, not a regeneration allowlist: a bad
    sibling ID must not erase positive MIMO evidence from another item.
    """
    raw_execution_ids = getattr(report, "test_execution_ids", None)
    if not isinstance(raw_execution_ids, list):
        return False
    for raw_execution_id in raw_execution_ids:
        try:
            execution_id = UUID(str(raw_execution_id))
        except (TypeError, ValueError):
            continue
        execution = db.get(TestExecution, execution_id)
        if execution is not None and is_mimo_ota_execution(db, execution):
            return True
    return False


def report_is_mimo_ota_report(db: Session, report: TestReport) -> bool:
    """Identify a MIMO candidate; linked execution remains the trust source."""
    raw_content = getattr(report, "content_data", None)
    content = raw_content if isinstance(raw_content, dict) else {}
    return (
        content.get("report_family") == "mimo_ota"
        or getattr(report, "generated_by", None) == "mimo_ota.executors.report"
        or report_references_mimo_ota_execution(db, report)
    )


def legacy_mimo_regeneration_error(
    db: Session,
    report: TestReport,
    *,
    allow_active_execution: bool = False,
) -> Optional[str]:
    """Return why a legacy MIMO report cannot be rebuilt without false trust.

    This is the shared source for list metadata and the generation gate.  The
    current trusted builder can only replace a single-execution PDF; accepting
    any wider shape would stamp new provenance onto an old, untouched file.
    """
    raw_content = getattr(report, "content_data", None)
    content = raw_content if isinstance(raw_content, dict) else {}
    if (
        not report_is_mimo_ota_report(db, report)
        or report_has_provenance_trust(content)
    ):
        return None

    report_status = getattr(report, "status", None)
    report_status = getattr(report_status, "value", report_status)
    if report_status == ReportStatus.GENERATING.value:
        return "Safe regeneration is already in progress."

    report_type = getattr(report, "report_type", None)
    report_type = getattr(report_type, "value", report_type)
    if report_type != ReportType.SINGLE_EXECUTION.value:
        return "Safe regeneration requires a single-execution report."
    if getattr(report, "road_test_execution_id", None):
        return "Road-test reports cannot use the MIMO execution recovery path."

    report_format = getattr(report, "format", None)
    report_format = getattr(report_format, "value", report_format)
    if report_format != ReportFormat.PDF.value:
        return "Safe regeneration is currently available only for PDF reports."

    execution_ids = normalized_report_execution_ids(report)
    if len(execution_ids) != 1:
        return (
            "Multi-execution MIMO OTA reports cannot be safely regenerated; "
            "safe regeneration requires a single linked TestExecution."
        )
    try:
        execution_id = UUID(str(execution_ids[0]))
    except (TypeError, ValueError):
        return "The linked TestExecution identifier is invalid."
    execution = db.get(TestExecution, execution_id)
    if execution is None:
        return (
            "The linked TestExecution is unavailable; regeneration cannot "
            "be performed safely."
        )
    if not is_mimo_ota_execution(db, execution):
        return (
            "The linked TestExecution is not an authoritative MIMO OTA "
            "execution; regeneration cannot be performed safely."
        )
    raw_execution_status = getattr(execution, "status", None)
    execution_status = getattr(raw_execution_status, "value", raw_execution_status)
    if (
        not allow_active_execution
        and execution_status not in {"completed", "failed", "cancelled", "skipped"}
    ):
        return (
            "Safe public regeneration requires the linked TestExecution to be "
            "in a terminal state."
        )
    return None


def claim_report_generation(
    db: Session,
    report_id: UUID,
    *,
    expected_content_data: Any = _UNCONDITIONAL_REPORT_SNAPSHOT,
) -> None:
    """Atomically acquire the single writer slot for a report artifact."""
    claim_query = db.query(TestReport).filter(
        TestReport.id == report_id,
        TestReport.status != ReportStatus.GENERATING.value,
    )
    if expected_content_data is not _UNCONDITIONAL_REPORT_SNAPSHOT:
        # A historical VRT rebuild must claim the exact untrusted snapshot it
        # inspected. A late request cannot re-claim a row after another writer
        # has published the server-owned payload.
        claim_query = claim_query.filter(
            cast(TestReport.content_data, String)
            == json.dumps(expected_content_data)
        )
    claimed = claim_query.update(
        {
            TestReport.status: ReportStatus.GENERATING.value,
            TestReport.generation_started_at: datetime.now(timezone.utc),
            TestReport.progress_percent: 0,
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        raise ReportGenerationConflict("Report generation is already in progress")
    db.commit()


class ReportService:
    """Service for managing test reports"""

    def create_report(
        self,
        db: Session,
        title: str,
        report_type: str,
        format: str,
        generated_by: str,
        test_plan_id: Optional[UUID] = None,
        test_execution_ids: Optional[List[UUID]] = None,
        template_id: Optional[UUID] = None,
        **kwargs
    ) -> TestReport:
        """Create a new report"""
        road_test_execution_id = kwargs.get("road_test_execution_id")
        if road_test_execution_id is not None:
            raise RoadTestReportConflict(
                "VRT reports must be created by the authoritative terminal archive path."
            )
        if "content_data" in kwargs:
            kwargs["content_data"] = _strip_untrusted_report_attestation(
                kwargs["content_data"]
            )
        # Convert UUID to string for JSON serialization
        execution_ids_str = [str(eid) for eid in (test_execution_ids or [])]
        comparison_ids = kwargs.pop('comparison_plan_ids', None)
        comparison_ids_str = [str(cid) for cid in (comparison_ids or [])] if comparison_ids else []

        report = TestReport(
            title=title,
            report_type=report_type,
            format=format,
            generated_by=generated_by,
            test_plan_id=test_plan_id,
            test_execution_ids=execution_ids_str,
            comparison_plan_ids=comparison_ids_str,
            template_id=template_id,
            status=ReportStatus.PENDING,
            progress_percent=0,
            **kwargs
        )

        db.add(report)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise
        db.refresh(report)

        logger.info(f"Created report: {report.id} - {title}")
        return report

    def get_report(self, db: Session, report_id: UUID) -> Optional[TestReport]:
        """Get a report by ID"""
        return db.query(TestReport).filter(TestReport.id == report_id).first()

    def list_reports(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        format: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> List[TestReport]:
        """List reports with filters"""
        query = db.query(TestReport)

        if report_type:
            query = query.filter(TestReport.report_type == report_type)
        if status:
            query = query.filter(TestReport.status == status)
        if format:
            query = query.filter(TestReport.format == format)
        if generated_by:
            query = query.filter(TestReport.generated_by == generated_by)

        query = query.order_by(TestReport.generated_at.desc())
        return query.offset(skip).limit(limit).all()

    def count_reports(
        self,
        db: Session,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        format: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> int:
        """Count reports with filters"""
        query = db.query(TestReport)

        if report_type:
            query = query.filter(TestReport.report_type == report_type)
        if status:
            query = query.filter(TestReport.status == status)
        if format:
            query = query.filter(TestReport.format == format)
        if generated_by:
            query = query.filter(TestReport.generated_by == generated_by)

        return query.count()

    def update_report(
        self,
        db: Session,
        report_id: UUID,
        **kwargs
    ) -> Optional[TestReport]:
        """Update a report"""
        report = self.get_report(db, report_id)
        if not report:
            return None

        for key, value in kwargs.items():
            if hasattr(report, key) and value is not None:
                setattr(report, key, value)

        db.commit()
        db.refresh(report)

        logger.info(f"Updated report: {report_id}")
        return report

    def delete_report(self, db: Session, report_id: UUID) -> bool:
        """Delete a report"""
        report = self.get_report(db, report_id)
        if not report:
            return False

        db.delete(report)
        db.commit()

        logger.info(f"Deleted report: {report_id}")
        return True

    def generate_report(
        self,
        db: Session,
        report_id: UUID,
        content_data_override: Optional[Dict[str, Any]] = None,
        *,
        expected_content_data: Any = _UNCONDITIONAL_REPORT_SNAPSHOT,
        vrt_archive_metadata_override: Optional[Dict[str, Any]] = None,
        execution_lifecycle_projection: Any = None,
        execution_lifecycle_resolver: Any = None,
    ) -> Optional[TestReport]:
        """
        Trigger report generation
        
        Args:
            db: Database session
            report_id: Report ID
            content_data_override: Optional direct data to use, bypassing DB fetch
        """
        report = self.get_report(db, report_id)
        if not report:
            return None

        execution_ids, execution_ids_well_formed = _parse_report_execution_ids(
            report
        )
        if not execution_ids_well_formed:
            raise ValueError("Report TestExecution identifiers are malformed")

        if (
            execution_lifecycle_resolver is not None
            and not callable(execution_lifecycle_resolver)
        ):
            raise ValueError("MIMO lifecycle resolver must be callable")

        allow_active_execution = False
        if execution_lifecycle_resolver is not None:
            # 运行中 execution 的报告只能由 REPORT executor 的完整内部契约
            # 生成。必须在取得 writer claim 前验证全部条件；不能让调用方仅靠
            # 传入任意 callable 绕过公开恢复的终态门。
            from app.services.mimo_ota.executors.report import (
                ReportLifecycleProjection,
            )

            if (
                not isinstance(
                    execution_lifecycle_projection,
                    ReportLifecycleProjection,
                )
                or report.report_type not in (ReportType.SINGLE_EXECUTION, "single_execution")
                or report.format not in (ReportFormat.PDF, "pdf")
                or report.road_test_execution_id is not None
                or len(execution_ids) != 1
            ):
                raise ValueError(
                    "Deferred lifecycle publication is only valid for an "
                    "internally projected single-execution MIMO PDF"
                )
            try:
                internal_execution_id = UUID(str(execution_ids[0]))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(
                    "Deferred lifecycle publication requires one valid "
                    "TestExecution identifier"
                ) from exc
            internal_execution = db.query(TestExecution).filter(
                TestExecution.id == internal_execution_id
            ).first()
            if internal_execution is None or not is_mimo_ota_execution(
                db,
                internal_execution,
            ):
                raise ValueError(
                    "Deferred lifecycle publication requires an authoritative "
                    "MIMO OTA TestExecution"
                )
            allow_active_execution = True

        regeneration_error = legacy_mimo_regeneration_error(
            db,
            report,
            # 只有 REPORT executor 持有的内部 resolver 可以在 execution
            # 仍 running 时生成 staging；公开恢复入口必须等待权威终态。
            allow_active_execution=allow_active_execution,
        )
        if regeneration_error:
            raise LegacyMimoRegenerationRejected(regeneration_error)

        if report.road_test_execution_id:
            vrt_source = (
                content_data_override
                if isinstance(content_data_override, dict)
                else report.content_data
            )
            if not report_has_vrt_archive_trust(vrt_source):
                raise LegacyVrtArchiveRejected(
                    "Historical VRT report content is not server-owned; rebuild it "
                    "through the terminal execution archive endpoint."
                )

        # A read-then-write status check permits two clients to generate the
        # same path concurrently; the database decides the single winner.
        claim_report_generation(
            db,
            report_id,
            expected_content_data=expected_content_data,
        )
        db.refresh(report)

        if vrt_archive_metadata_override is not None:
            if not report.road_test_execution_id:
                raise LegacyVrtArchiveRejected(
                    "VRT archive metadata can be normalized only for a VRT report."
                )
            # The claim owns the entire formal artifact, not just its JSON.
            # Discard the client-selected legacy envelope before producing the
            # authoritative PDF.
            report.title = vrt_archive_metadata_override["title"]
            report.description = vrt_archive_metadata_override.get("description")
            report.report_type = ReportType.SINGLE_EXECUTION.value
            report.format = ReportFormat.PDF.value
            report.generated_by = "System (Auto-Archive)"
            report.template_id = None
            report.notes = vrt_archive_metadata_override.get("notes")
            report.tags = vrt_archive_metadata_override.get("tags")
            report.file_path = None
            report.file_size_bytes = None
            report.file_hash = None
            report.page_count = None
            report.section_count = None
            report.chart_count = None
            report.table_count = None
            report.generation_completed_at = None
            report.generation_duration_sec = None
            report.error_message = None
            report.error_details = None
            db.commit()
            db.refresh(report)

        logger.info(f"Starting report generation: {report_id}")
        staging_output_path: Optional[str] = None

        try:
            # Get template
            template = None
            if report.template_id:
                # User explicitly specified a template
                template = db.query(ReportTemplate).filter(
                    ReportTemplate.id == report.template_id
                ).first()
                logger.info(f"Using user-specified template: {template.name if template else 'NOT FOUND'}")

            if not template:
                # Try to find appropriate template based on report type
                if report.report_type == ReportType.SINGLE_EXECUTION and report.road_test_execution_id:
                    # VRT report - try to find VRT-specific template by name pattern
                    template = db.query(ReportTemplate).filter(
                        ReportTemplate.is_active == True,
                        ReportTemplate.name.ilike("%Virtual Road Test%")
                    ).first()
                    if template:
                        logger.info(f"Using VRT template: {template.name}")

                if not template and report.report_type != ReportType.SINGLE_EXECUTION:
                    # Get default template for other report types
                    template = db.query(ReportTemplate).filter(
                        ReportTemplate.is_default == True,
                        ReportTemplate.is_active == True
                    ).first()
                    if template:
                        logger.info(f"Using default template: {template.name}")

            # Log template status
            if template:
                logger.info(f"Report {report_id} will use template '{template.name}' (sections: {len(template.sections or [])})")
            else:
                logger.info(f"Report {report_id} will use auto-generated layout (no template)")

            # Update progress
            report.progress_percent = 10
            db.commit()

            # Gather report data
            report_data_dict = {}
            
            # Use overrides if available (critical for VRT immediate generation)
            raw_source_data = content_data_override or report.content_data
            source_data = (
                raw_source_data if isinstance(raw_source_data, dict) else {}
            )

            declared_mimo_report = (
                (source_data or {}).get("report_family") == "mimo_ota"
                or report.generated_by == "mimo_ota.executors.report"
            )
            linked_mimo_execution = report_references_mimo_ota_execution(
                db, report
            )
            mimo_report = declared_mimo_report or linked_mimo_execution
            if mimo_report and len(execution_ids) != 1:
                raise ValueError(
                    "Multi-execution MIMO OTA reports cannot be safely "
                    "regenerated with calibration provenance; rerun as "
                    "separate single-execution reports"
                )

            linked_execution = None
            if (
                report.report_type == ReportType.SINGLE_EXECUTION
                and not report.road_test_execution_id
                and len(execution_ids) == 1
            ):
                execution_id = UUID(str(execution_ids[0]))
                linked_execution = db.query(TestExecution).filter(
                    TestExecution.id == execution_id
                ).first()
            is_mimo_single_execution = (
                linked_execution is not None
                and is_mimo_ota_execution(db, linked_execution)
            )
            deferred_mimo_publication = execution_lifecycle_resolver is not None
            if deferred_mimo_publication and (
                not is_mimo_single_execution
                or execution_lifecycle_projection is None
                or report.format not in (ReportFormat.PDF, "pdf")
            ):
                raise ValueError(
                    "Deferred lifecycle publication is only valid for an "
                    "internally projected single-execution MIMO PDF"
                )
            if mimo_report and linked_execution is None:
                raise ValueError(
                    "MIMO OTA report cannot be safely regenerated because its "
                    "linked TestExecution is unavailable"
                )
            if mimo_report and not is_mimo_single_execution:
                raise ValueError(
                    "MIMO OTA report cannot be safely regenerated because its "
                    "linked TestExecution is not authoritatively MIMO OTA"
                )
            if is_mimo_single_execution:
                execution = linked_execution
                # Legacy report JSON is not an authoritative regeneration
                # source: it may contain pre-P1-27 mock/unknown calibration
                # KPIs. Rebuild the whole payload from the execution using the
                # current provenance-aware builder instead of patching only its
                # summary fields.
                from app.services.mimo_ota.executors.report import (
                    ReportLifecycleProjection,
                    _build_mimo_ota_content_data,
                )
                from app.services.test_case_runner import (
                    _finalize_scpi_acceptance,
                )

                _finalize_scpi_acceptance(execution)
                if (
                    execution_lifecycle_projection is not None
                    and not isinstance(
                        execution_lifecycle_projection,
                        ReportLifecycleProjection,
                    )
                ):
                    raise ValueError(
                        "MIMO lifecycle projection is an internal typed value"
                    )
                case_name = report.title.split("—", 1)[-1].strip()
                report_data_dict = _build_mimo_ota_content_data(
                    execution,
                    datetime.utcnow(),
                    case_name,
                    lifecycle_projection=execution_lifecycle_projection,
                )
            elif report.report_type == ReportType.SINGLE_EXECUTION and source_data:
                # For VRT/Single Execution, use the data directly
                report_data_dict = source_data.copy() if hasattr(source_data, 'copy') else dict(source_data)
                
                # Ensure it has basic metadata if missing
                if 'title' not in report_data_dict:
                    report_data_dict['title'] = report.title
                if 'generated_by' not in report_data_dict:
                    report_data_dict['generated_by'] = report.generated_by
                if 'generated_at' not in report_data_dict:
                    report_data_dict['generated_at'] = datetime.now(timezone.utc).isoformat()
                # P1-22 (Codex #256 R2): 封面按 report_type 分流用例/计划口径,
                # VRT 归档 override (ExecutionReport.model_dump) 没有该键 — 从
                # TestReport 行补齐, 与上面三个缺失补齐同构。
                if 'report_type' not in report_data_dict and report.report_type:
                    report_data_dict['report_type'] = (
                        report.report_type.value
                        if hasattr(report.report_type, 'value')
                        else str(report.report_type)
                    )

                # Transform VRT data structure to PDF Generator expected structure
                # Debug logging
                logger.info(f"Preparing VRT report data. Keys available: {list(report_data_dict.keys())}")
                if 'logs' in report_data_dict:
                     logger.info(f"Logs count: {len(report_data_dict['logs'])}")
                else:
                     logger.warning("No 'logs' key in report_data_dict")
                
                # 1. Execution Summary
                
                # 1. Execution Summary
                if 'execution_summary' not in report_data_dict:
                    _result = report_data_dict.get('overall_result')
                    report_data_dict['execution_summary'] = {
                        'total_executions': 1,
                        'passed': 1 if _result == 'passed' else 0,
                        'failed': 1 if _result == 'failed' else 0,
                        'pending': 0,
                        # P1-48: 四态里的后两态在这里不属于 passed/failed/pending。
                        # 不显式记的话，PDF 那边 total=1 而三类全 0，
                        # 分布图会画出满宽灰条、图例却写 Pending(0)，自相矛盾。
                        #
                        # ⚠️ 两者**分开记**（外审 P2）：上一版把 incomplete 也算进
                        # undetermined，被 stop 掉的执行会在 PDF 上印成「未判定」——
                        # 那等于说「测完了但结果不可信」，而它其实是**根本没测完**。
                        # 这两个状态前几轮才刚区分开，别在摘要这层又合回去。
                        'undetermined': 1 if _result == 'undetermined' else 0,
                        'incomplete': 1 if _result == 'incomplete' else 0,
                        # 默认值不能是 0 —— 0 会被读成「一条都没过」（P1-48）
                        'pass_rate': report_data_dict.get('pass_rate'),
                        'total_duration_sec': report_data_dict.get('duration_s', 0),
                        'first_execution': report_data_dict.get('start_time'),
                        'last_execution': report_data_dict.get('end_time')
                    }

                # 2. Statistics (Map kpi_summary -> statistics)
                if 'statistics' not in report_data_dict and 'kpi_summary' in report_data_dict:
                    stats = {}
                    for kpi in report_data_dict.get('kpi_summary', []):
                        name = kpi.get('name')
                        if name:
                            stats[name] = {
                                'metric_name': name,
                                'mean': kpi.get('mean', 0),
                                'median': kpi.get('median', kpi.get('mean', 0)),  # Use median if available, fallback to mean
                                'std': kpi.get('std', 0),
                                'min': kpi.get('min', 0),
                                'max': kpi.get('max', 0),
                                'count': kpi.get('count', 0)
                            }
                    report_data_dict['statistics'] = stats

                # 3. Chart Data (Map time_series -> chart_data)
                if 'chart_data' not in report_data_dict and 'time_series' in report_data_dict:
                    ts_data = report_data_dict.get('time_series', [])
                    if ts_data:
                        timestamps = []
                        metrics_series = {}
                        
                        for point in ts_data:
                            t_val = point.get('time_s', 0)
                            timestamps.append(t_val)
                            
                            for k, v in point.items():
                                if k not in ['time_s', 'position', 'event'] and isinstance(v, (int, float)):
                                    if k not in metrics_series:
                                        metrics_series[k] = []
                                    metrics_series[k].append(v)
                        
                        chart_data = {}
                        for metric, values in metrics_series.items():
                             chart_data[f"time_series_{metric}"] = {
                                 "timestamps": timestamps,
                                 "values": values,
                                 "anomaly_indices": []
                             }
                        report_data_dict['chart_data'] = chart_data

                # P1-47C：关联 TestExecution 的结论字段只能来自服务端执行行。
                # MIMO_OTA 仍可用 override 携带专用图表/相位内容，但公开 API 可写的
                # content_data 不能覆盖 SCPI 证据或把 AND 门失败伪装成 PASS。VRT 使用
                # 独立 road_test_execution_id 数据链，不套用 TestExecution 证据契约。
                if execution_ids and not report.road_test_execution_id:
                    authoritative = ReportDataCollector().collect(
                        db, report, strict_execution_ids=True
                    ).to_dict()
                    summary = authoritative.get('execution_summary')
                    if not summary:
                        raise ValueError(
                            f"No TestExecution rows found for report {report_id}"
                        )
                    report_data_dict['scpi_evidence'] = authoritative.get(
                        'scpi_evidence', {}
                    )
                    if execution_lifecycle_projection is None:
                        report_data_dict['execution_summary'] = summary
                        report_data_dict['pass_rate'] = summary.get('pass_rate')
                        if summary.get('passed') == summary.get('total_executions'):
                            report_data_dict['overall_result'] = 'passed'
                        elif summary.get('failed', 0) > 0:
                            report_data_dict['overall_result'] = 'failed'
                        else:
                            report_data_dict['overall_result'] = 'pending'
            else:
                # For standard reports, collect data from DB
                data_collector = ReportDataCollector()
                report_data = data_collector.collect(
                    db,
                    report,
                    strict_execution_ids=bool(execution_ids),
                )
                if report_data is None:
                    raise ValueError(f"Failed to collect report data for report {report_id}")
                report_data_dict = report_data.to_dict()

            # 普通路径沿用即时持久化。MIMO 最终相位必须等数据库生命周期
            # 裁决完成后再一次性公开，避免 completed 投影短暂可见/可下载。
            if not deferred_mimo_publication:
                report.content_data = report_data_dict

            # Update progress
            report.progress_percent = 50
            db.commit()

            # Generate PDF
            if report.format == ReportFormat.PDF or report.format == "pdf":
                output_dir = os.path.join('data', 'reports', str(report.id))
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f'report_{report.id}.pdf')

                pdf_generator = PDFGenerator()

                # Convert template model to dict (if template exists)
                template_dict = None
                if template:
                    template_dict = {
                        'sections': template.sections,
                        'chart_configs': template.chart_configs or {},
                        'table_configs': template.table_configs or {},
                        'page_size': template.page_size or 'A4',
                        'page_orientation': template.page_orientation or 'portrait',
                        'margins': template.margins or {},
                        'logo_path': template.logo_path,
                        'color_scheme': template.color_scheme or {}
                    }

                generation_output_path = output_path
                if deferred_mimo_publication:
                    staging_output_path = f"{output_path}.staging"
                    generation_output_path = staging_output_path

                # 先在不可下载的 staging 路径生成。生成期间仍允许取消方通过
                # TestExecution CAS 赢得终态；只有赢家内容会发布到正式路径。
                pdf_generator.generate_report(
                    report_data_dict,
                    template_dict,
                    generation_output_path,
                )

                if deferred_mimo_publication:
                    settled_projection = execution_lifecycle_resolver(
                        execution_lifecycle_projection
                    )
                    if not isinstance(settled_projection, ReportLifecycleProjection):
                        raise ValueError(
                            "MIMO lifecycle resolver returned an invalid projection"
                        )
                    if settled_projection != execution_lifecycle_projection:
                        _finalize_scpi_acceptance(execution)
                        report_data_dict = _build_mimo_ota_content_data(
                            execution,
                            datetime.utcnow(),
                            case_name,
                            lifecycle_projection=settled_projection,
                        )
                        pdf_generator.generate_report(
                            report_data_dict,
                            template_dict,
                            generation_output_path,
                        )
                    os.replace(generation_output_path, output_path)
                    staging_output_path = None

                # PDF、报告详情 API 与 GUI 在同一提交里共享最终赢家结论。
                report.content_data = report_data_dict

                # Update report with file path and metadata
                report.file_path = output_path
                report.file_size_bytes = os.path.getsize(output_path)
                
                # Check if specific result directory exists (User preference)
                import shutil
                # Assumption: running from api-service/ or root
                legacy_result_dir = os.path.abspath(os.path.join(os.getcwd(), '..', 'Result_Report'))
                if not os.path.exists(legacy_result_dir):
                    # Try current directory
                    legacy_result_dir = os.path.abspath(os.path.join(os.getcwd(), 'Result_Report'))
                
                if os.path.exists(legacy_result_dir):
                    try:
                        target_path = os.path.join(legacy_result_dir, f'report_{report.id}.pdf')
                        shutil.copy2(output_path, target_path)
                        logger.info(f"Copied report to legacy path: {target_path}")
                    except Exception as e:
                        logger.warning(f"Failed to copy report to Result_Report: {e}")

                # Extract stats for metadata
                
                # Extract stats for metadata
                if 'chart_data' in report_data_dict:
                    report.chart_count = len(report_data_dict['chart_data'])
                if 'table_data' in report_data_dict:
                    report.table_count = len(report_data_dict['table_data'])

            # Update status to completed
            report.status = ReportStatus.COMPLETED
            report.generation_completed_at = datetime.now(timezone.utc)
            report.progress_percent = 100

            db.commit()
            db.refresh(report)

            logger.info(f"Report generation completed: {report_id}")
            return report

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error generating report {report_id}: {e}\n{error_details}")

            if staging_output_path and os.path.exists(staging_output_path):
                try:
                    os.unlink(staging_output_path)
                except OSError:
                    logger.warning(
                        "Failed to remove staged report artifact: %s",
                        staging_output_path,
                        exc_info=True,
                    )

            # Update status to failed with detailed error info
            report.status = ReportStatus.FAILED
            report.error_message = str(e)
            report.error_details = error_details  # Save full traceback for debugging
            report.progress_percent = 0
            db.commit()

            raise

class ReportTemplateService:
    """Service for managing report templates"""

    def create_template(
        self,
        db: Session,
        name: str,
        template_type: str,
        sections: List[Dict[str, Any]],
        created_by: str,
        **kwargs
    ) -> ReportTemplate:
        """Create a new report template"""
        template = ReportTemplate(
            name=name,
            template_type=template_type,
            sections=sections,
            created_by=created_by,
            **kwargs
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        logger.info(f"Created report template: {template.id} - {name}")
        return template

    def get_template(self, db: Session, template_id: UUID) -> Optional[ReportTemplate]:
        """Get a template by ID"""
        return db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()

    def list_templates(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        template_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[ReportTemplate]:
        """List templates with filters"""
        query = db.query(ReportTemplate)

        if template_type:
            query = query.filter(ReportTemplate.template_type == template_type)
        if is_active is not None:
            query = query.filter(ReportTemplate.is_active == is_active)

        query = query.order_by(ReportTemplate.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_template(
        self,
        db: Session,
        template_id: UUID,
        **kwargs
    ) -> Optional[ReportTemplate]:
        """Update a template"""
        template = self.get_template(db, template_id)
        if not template:
            return None

        for key, value in kwargs.items():
            if hasattr(template, key) and value is not None:
                setattr(template, key, value)

        db.commit()
        db.refresh(template)

        logger.info(f"Updated template: {template_id}")
        return template

    def delete_template(self, db: Session, template_id: UUID) -> bool:
        """Delete a template"""
        template = self.get_template(db, template_id)
        if not template:
            return False

        db.delete(template)
        db.commit()

        logger.info(f"Deleted template: {template_id}")
        return True


# P1-72 对比指标集：取自 execution.measurements.phases.analysis 的真实落库键
# （2026-08-25 生产库 45 条 completed 行实查所得，不是设计臆断）
COMPARISON_METRIC_KEYS = (
    "avg_throughput_mbps",
    "throughput_ratio",
    "rsrp_variance_db",
    "avg_sinr_db",
)


class ReportComparisonService:
    """Service for managing report comparisons

    P1-72 对比换源：新建与分析一律 execution 级（TestExecution 是正式测试的
    执行记录层）；plan 级历史行只读（计划链已封存）。全部参与 execution 同属
    一个 TestCase 时，分析同时落一行 repeatability_tests 对齐记录（设计稿 §5）。
    """

    def create_comparison(
        self,
        db: Session,
        name: str,
        baseline_execution_id: UUID,
        comparison_execution_ids: List[UUID],
        created_by: str,
        **kwargs
    ) -> ReportComparison:
        """Create a new execution-level comparison（P1-72 换源）。

        fail-loud：任何参与 execution 不存在即拒建，不留悬空对比。
        """
        all_ids = [baseline_execution_id, *comparison_execution_ids]
        # 内审 F2：自比/重复 execution 会落出 spread=0 的假"完美重复性"——
        # 比造显著性更隐蔽的假数据，拒建
        if len(set(all_ids)) != len(all_ids):
            raise ValueError(
                "参与 execution 有重复（baseline 不得出现在对比列表、"
                "列表内不得重复）—— 自比会产出 spread=0 的假重复性记录"
            )
        found = {
            row.id
            for row in db.query(TestExecution)
            .filter(TestExecution.id.in_(all_ids))
            .all()
        }
        missing = [str(i) for i in all_ids if i not in found]
        if missing:
            raise ValueError(
                f"TestExecution 不存在: {missing} —— 不建悬空对比"
            )

        comparison = ReportComparison(
            name=name,
            baseline_execution_id=baseline_execution_id,
            comparison_execution_ids=[str(i) for i in comparison_execution_ids],
            # 封存列 NOT NULL —— 新行恒写空数组，见模型注释
            comparison_plan_ids=[],
            created_by=created_by,
            **kwargs
        )

        db.add(comparison)
        db.commit()
        db.refresh(comparison)

        logger.info(f"Created comparison: {comparison.id} - {name}")
        return comparison

    def get_comparison(self, db: Session, comparison_id: UUID) -> Optional[ReportComparison]:
        """Get a comparison by ID"""
        return db.query(ReportComparison).filter(ReportComparison.id == comparison_id).first()

    def list_comparisons(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        created_by: Optional[str] = None
    ) -> List[ReportComparison]:
        """List comparisons with filters"""
        query = db.query(ReportComparison)

        if created_by:
            query = query.filter(ReportComparison.created_by == created_by)

        query = query.order_by(ReportComparison.created_at.desc())
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def _extract_execution_metrics(execution: TestExecution) -> Dict[str, Any]:
        """从 execution.measurements.phases.analysis 提对比指标 + provenance。

        fail-loud：无 analysis 数据的 execution 不可对比（不猜、不补零）。
        """
        measurements = execution.measurements or {}
        phases = measurements.get("phases") or {}
        analysis = phases.get("analysis") or {}
        measure = phases.get("measure") or {}
        outcome = project_execution_evidence_outcome(execution)
        diagnostic = execution_evidence_blocks_formal_outputs(execution)
        execution_config = execution.config if isinstance(execution.config, dict) else {}
        evidence = execution_config.get(BASE_STATION_EXECUTION_EVIDENCE_FIELD)
        evidence_required = base_station_metric_projection_required(
            execution_config
        )
        # 内审 F5：analysis 存在但 4 个对比指标键全缺 → 同样无可比数据，
        # 不产出"formal 却零指标"的空壳对比
        if not evidence_required and (not analysis or all(
            analysis.get(k) is None for k in COMPARISON_METRIC_KEYS
        )):
            raise ValueError(
                f"execution {execution.id} 无 measurements.phases.analysis "
                f"对比指标（status={execution.status}）—— 无指标可对比，"
                f"不生成对比结果"
            )
        metrics = {
            k: None if diagnostic else analysis.get(k)
            for k in COMPARISON_METRIC_KEYS
        }
        if diagnostic:
            metric_trust = {key: False for key in COMPARISON_METRIC_KEYS}
        elif evidence_required:
            expected_config, expected_positions = (
                base_station_expected_scope_from_evidence(evidence)
            )
            projection = (
                project_base_station_metrics_by_position(
                    evidence,
                    expected_config=expected_config,
                    expected_positions=expected_positions,
                    execution_config=execution_config,
                )
                if expected_config is not None and expected_positions
                else []
            )
            throughput_values = [
                row["dl_throughput_mbps"].formal_value for row in projection
            ]
            throughput_trusted = bool(projection) and all(
                row["dl_throughput_mbps"].status == "trusted"
                and row["dl_throughput_mbps"].formal_value is not None
                for row in projection
            )
            avg_throughput = (
                sum(throughput_values) / len(throughput_values)
                if throughput_trusted
                else None
            )
            peak = execution_config.get(MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD)
            peak_trusted = (
                not isinstance(peak, bool)
                and isinstance(peak, (int, float))
                and math.isfinite(float(peak))
                and float(peak) > 0.0
            )
            metrics["avg_throughput_mbps"] = avg_throughput
            metrics["throughput_ratio"] = (
                avg_throughput / float(peak)
                if avg_throughput is not None and peak_trusted
                else None
            )
            rsrp_values = trusted_rf_kpi_values(measure, "rsrp_dbm")
            sinr_values = trusted_rf_kpi_values(measure, "sinr_db")
            metrics["rsrp_variance_db"] = (
                max(rsrp_values) - min(rsrp_values) if rsrp_values else None
            )
            metrics["avg_sinr_db"] = (
                sum(sinr_values) / len(sinr_values) if sinr_values else None
            )
            metric_trust = {
                "avg_throughput_mbps": throughput_trusted,
                "throughput_ratio": throughput_trusted and peak_trusted,
                "rsrp_variance_db": rsrp_values is not None,
                "avg_sinr_db": sinr_values is not None,
            }
        else:
            measurement_trusted = analysis.get("measurement_verified") is True
            metric_trust = {
                "avg_throughput_mbps": measurement_trusted
                and analysis.get("throughput_verified") is True,
                "throughput_ratio": measurement_trusted
                and analysis.get("throughput_verified") is True,
                "rsrp_variance_db": measurement_trusted
                and analysis.get("rf_kpi_verified") is True,
                "avg_sinr_db": measurement_trusted
                and analysis.get("rf_kpi_verified") is True,
            }
        return {
            "execution_id": str(execution.id),
            "test_case_id": (
                str(execution.test_case_id) if execution.test_case_id else None
            ),
            "status": execution.status,
            "started_at": (
                execution.started_at.isoformat() if execution.started_at else None
            ),
            "metrics": metrics,
            "provenance": {
                "execution_classification": (
                    outcome.compatibility_classification
                ),
                "verdict": analysis.get("verdict"),
                "measurement_verified": analysis.get("measurement_verified"),
                "throughput_verified": analysis.get("throughput_verified"),
                "rf_kpi_verified": analysis.get("rf_kpi_verified"),
                "metric_trust": metric_trust,
            },
        }

    def perform_comparison_analysis(
        self,
        db: Session,
        comparison_id: UUID
    ) -> Optional[ReportComparison]:
        """execution 级对比分析（P1-72 实现，原占位符）。

        产出：comparison_results（baseline/逐项指标/差分/formal 判定）+
        summary_statistics（各指标 mean/min/max/spread）。
        significant_differences **不写** —— 每个 execution 是单次运行，
        没有分布，t-test/ANOVA 会制造假显著性（P1-64 同母题：不造数）。
        全部参与 execution 同属一个 TestCase 时，落一行 repeatability_tests
        对齐记录（设计稿 §5）。
        """
        comparison = self.get_comparison(db, comparison_id)
        if not comparison:
            return None
        if comparison.baseline_execution_id is None:
            raise ValueError(
                "plan 级历史对比不可分析：计划链已封存（ARCH-1 S4），"
                "请新建 execution 级对比（P1-72）"
            )

        # 内审 F3：重分析（重试/双击）不许增殖对齐行 —— 记住上一轮落的行并
        # 立即清理（外审 #396 R1 high：清理若挂在"本轮也满足同 case"分支里，
        # 本轮不满足时旧行成孤儿且指针随 comparison_results 覆盖永失）。
        # 本轮后续 fail-loud raise 时由调用方 rollback 撤销此删除，无害。
        previous_repeatability_id = (comparison.comparison_results or {}).get(
            "repeatability_test_id"
        )
        if previous_repeatability_id is not None:
            from app.models.calibration import RepeatabilityTest

            stale = db.get(RepeatabilityTest, UUID(previous_repeatability_id))
            if stale is not None:
                db.delete(stale)

        ordered_ids = [comparison.baseline_execution_id] + [
            UUID(str(i)) for i in (comparison.comparison_execution_ids or [])
        ]
        rows = {
            row.id: row
            for row in db.query(TestExecution)
            .filter(TestExecution.id.in_(ordered_ids))
            .all()
        }
        missing = [str(i) for i in ordered_ids if i not in rows]
        if missing:
            raise ValueError(f"TestExecution 不存在: {missing} —— 对比无法分析")

        entries = [
            self._extract_execution_metrics(rows[i]) for i in ordered_ids
        ]
        baseline_entry, compare_entries = entries[0], entries[1:]

        deltas = []
        for entry in compare_entries:
            per_metric = {}
            for key in COMPARISON_METRIC_KEYS:
                base_v = baseline_entry["metrics"].get(key)
                comp_v = entry["metrics"].get(key)
                per_metric[key] = (
                    comp_v - base_v
                    if isinstance(base_v, (int, float))
                    and isinstance(comp_v, (int, float))
                    and not isinstance(base_v, bool)
                    and not isinstance(comp_v, bool)
                    and baseline_entry["provenance"]["metric_trust"].get(key)
                    is True
                    and entry["provenance"]["metric_trust"].get(key) is True
                    else None
                )
            deltas.append(
                {"execution_id": entry["execution_id"], "deltas": per_metric}
            )

        formal = all(
            entry["provenance"]["metric_trust"].get(key) is True
            for entry in entries
            for key in COMPARISON_METRIC_KEYS
        )

        comparison.comparison_results = {
            "mode": "execution",
            "baseline": baseline_entry,
            "comparisons": compare_entries,
            "deltas": deltas,
            "formal": formal,
            "formal_note": (
                None if formal else
                "至少一个 execution 的测量含模拟仪器 provenance 或缺少"
                "逐指标正式证据 —— 本对比不构成正式结论"
            ),
        }

        summary: Dict[str, Any] = {}
        for key in COMPARISON_METRIC_KEYS:
            values = [
                entry["metrics"].get(key)
                for entry in entries
                if entry["provenance"]["metric_trust"].get(key) is True
                and isinstance(entry["metrics"].get(key), (int, float))
                and not isinstance(entry["metrics"].get(key), bool)
            ]
            if values:
                summary[key] = {
                    "n": len(values),
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "spread": max(values) - min(values),
                }
        comparison.summary_statistics = summary

        case_ids = {entry["test_case_id"] for entry in entries}
        repeatability_id = None
        if len(case_ids) == 1 and None not in case_ids:
            from app.models.calibration import RepeatabilityTest

            repeatability = RepeatabilityTest(
                test_type="execution_metrics",
                measurements=[
                    {
                        "run_number": index + 1,
                        "execution_id": entry["execution_id"],
                        "metrics": entry["metrics"],
                    }
                    for index, entry in enumerate(entries)
                ],
                num_runs=len(entries),
                test_case_id=UUID(baseline_entry["test_case_id"]),
                execution_ids=[entry["execution_id"] for entry in entries],
                metric_deltas={
                    "baseline_execution_id": baseline_entry["execution_id"],
                    "deltas": deltas,
                    "formal": formal,
                },
                tested_by=comparison.created_by,
            )
            db.add(repeatability)
            db.flush()
            repeatability_id = str(repeatability.id)
            # 重新赋值而非原地加键：flush 已清脏标记，普通 JSON 列不追踪
            # 原地变更，原地加键会在 refresh 后静默丢失（门测试抓出）
            comparison.comparison_results = {
                **comparison.comparison_results,
                "repeatability_test_id": repeatability_id,
            }

        db.commit()
        db.refresh(comparison)
        logger.info(
            "Comparison analysis %s: %d executions, formal=%s, repeatability=%s",
            comparison_id, len(entries), formal, repeatability_id,
        )
        return comparison


class ReportScheduleService:
    """Service for managing report schedules"""

    def create_schedule(
        self,
        db: Session,
        name: str,
        template_id: UUID,
        report_type: str,
        schedule_type: str,
        created_by: str,
        **kwargs
    ) -> ReportSchedule:
        """Create a new report schedule"""
        schedule = ReportSchedule(
            name=name,
            template_id=template_id,
            report_type=report_type,
            schedule_type=schedule_type,
            created_by=created_by,
            **kwargs
        )

        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        logger.info(f"Created report schedule: {schedule.id} - {name}")
        return schedule

    def get_schedule(self, db: Session, schedule_id: UUID) -> Optional[ReportSchedule]:
        """Get a schedule by ID"""
        return db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()

    def list_schedules(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[ReportSchedule]:
        """List schedules with filters"""
        query = db.query(ReportSchedule)

        if is_active is not None:
            query = query.filter(ReportSchedule.is_active == is_active)

        query = query.order_by(ReportSchedule.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_schedule(
        self,
        db: Session,
        schedule_id: UUID,
        **kwargs
    ) -> Optional[ReportSchedule]:
        """Update a schedule"""
        schedule = self.get_schedule(db, schedule_id)
        if not schedule:
            return None

        for key, value in kwargs.items():
            if hasattr(schedule, key) and value is not None:
                setattr(schedule, key, value)

        db.commit()
        db.refresh(schedule)

        logger.info(f"Updated schedule: {schedule_id}")
        return schedule

    def delete_schedule(self, db: Session, schedule_id: UUID) -> bool:
        """Delete a schedule"""
        schedule = self.get_schedule(db, schedule_id)
        if not schedule:
            return False

        db.delete(schedule)
        db.commit()

        logger.info(f"Deleted schedule: {schedule_id}")
        return True
