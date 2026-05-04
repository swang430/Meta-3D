"""VRT execution service — backed by `test_executions` and `vrt_kpi_samples`.

Phase 2.4b of the VRT-into-TestCase consolidation. Replaces the in-memory
state dicts in `app/api/road_test.py` (`_executions`, `_execution_status`,
`_execution_metrics`, `_execution_phases`, `_execution_logs`) with persistent
storage via the existing `TestExecution` ORM (extended in Phase 2.4a) and
the new `VrtKpiSample` table.

Design:
- VRT-specific filterable fields (scenario_id, topology_id, mode) live in
  dedicated columns on `test_executions`.
- Volatile runtime data (progress, position, logs, events, phases) lives in
  JSONB columns on the same row.
- KPI time-series samples (potentially thousands per execution) live in
  `vrt_kpi_samples` for indexed time-range queries.
- The legacy Pydantic `TestExecution` schema's `execution_id` is now the full
  UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000"), not the
  former "exec-xxxxxxxxxxxx" format. Frontend updated alongside.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.test_plan import TestExecution as TestExecutionORM
from app.models.road_test import VrtKpiSample
from app.schemas.road_test import (
    ExecutionStatus,
    ExecutionSummary,
    KPIMetrics,
    TestExecution as TestExecutionSchema,
    TestMetrics,
    TestMode,
    TestStatus,
)
from app.schemas.road_test.execution import PhaseResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _resolve_uuid(execution_id: str) -> Optional[UUID]:
    """Parse a string id as UUID; returns None if malformed."""
    try:
        return UUID(execution_id)
    except (ValueError, AttributeError, TypeError):
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for DB consistency


# ──────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────

class VrtExecutionService:
    """CRUD, state machine, runtime updates, and time-series for VRT executions."""

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create(
        self,
        db: Session,
        *,
        mode: TestMode,
        scenario_id: str,
        topology_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        created_by: str = "api",
    ) -> TestExecutionORM:
        """Create a new VRT execution row in IDLE state."""
        row = TestExecutionORM(
            status=ExecutionStatus.IDLE.value,
            mode=mode.value,
            scenario_id=scenario_id,
            topology_id=topology_id,
            config=config or {},
            notes=notes,
            executed_by=created_by,
            vrt_runtime_status={"progress_percent": 0.0, "elapsed_time_s": 0.0},
            execution_logs=[],
            execution_events=[],
            execution_warnings=[],
            phase_results=[],
            hardware_status={},
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        self.append_log(db, row.id, level="INFO", message="Execution created", source="System")
        logger.info("Created VRT execution %s (mode=%s, scenario=%s)", row.id, mode.value, scenario_id)
        return row

    def get(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        uid = _resolve_uuid(execution_id)
        if uid is None:
            return None
        return db.query(TestExecutionORM).filter(TestExecutionORM.id == uid).first()

    def list(
        self,
        db: Session,
        mode: Optional[TestMode] = None,
        status: Optional[ExecutionStatus] = None,
        limit: int = 1000,
    ) -> List[TestExecutionORM]:
        """List VRT executions. Filters out non-VRT TestExecution rows by requiring `mode IS NOT NULL`."""
        query = db.query(TestExecutionORM).filter(TestExecutionORM.mode.isnot(None))
        if mode is not None:
            query = query.filter(TestExecutionORM.mode == mode.value)
        if status is not None:
            query = query.filter(TestExecutionORM.status == status.value)
        return query.order_by(TestExecutionORM.executed_at.desc()).limit(limit).all()

    # ── State machine ────────────────────────────────────────────────────

    def _transition(
        self,
        db: Session,
        execution_id: str,
        target_status: ExecutionStatus,
        *,
        log_message: str,
        set_started_at: bool = False,
        set_completed_at: bool = False,
        progress_percent: Optional[float] = None,
    ) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None:
            return None
        row.status = target_status.value
        if set_started_at and row.started_at is None:
            row.started_at = _utcnow()
        if set_completed_at:
            row.completed_at = _utcnow()
            if row.started_at is not None:
                row.duration_sec = (row.completed_at - row.started_at).total_seconds()
        if progress_percent is not None:
            self._merge_runtime_status(row, {"progress_percent": progress_percent})
        db.commit()
        db.refresh(row)
        self.append_log(db, row.id, level="INFO", message=log_message, source="System")
        return row

    def start(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        return self._transition(
            db, execution_id, ExecutionStatus.RUNNING,
            log_message="Execution started",
            set_started_at=True,
        )

    def pause(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        return self._transition(db, execution_id, ExecutionStatus.PAUSED, log_message="Execution paused")

    def resume(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        return self._transition(db, execution_id, ExecutionStatus.RUNNING, log_message="Execution resumed")

    def stop(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        return self._transition(
            db, execution_id, ExecutionStatus.STOPPED,
            log_message="Execution stopped",
            set_completed_at=True,
        )

    def complete(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        return self._transition(
            db, execution_id, ExecutionStatus.COMPLETED,
            log_message="Execution completed",
            set_completed_at=True,
            progress_percent=100.0,
        )

    def fail(self, db: Session, execution_id: str, error_message: str) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None:
            return None
        row.status = ExecutionStatus.FAILED.value
        row.error_message = error_message
        row.completed_at = _utcnow()
        if row.started_at is not None:
            row.duration_sec = (row.completed_at - row.started_at).total_seconds()
        db.commit()
        db.refresh(row)
        self.append_log(db, row.id, level="ERROR", message=f"Execution failed: {error_message}", source="System")
        return row

    # ── Runtime updates (JSONB merges) ───────────────────────────────────

    @staticmethod
    def _merge_runtime_status(row: TestExecutionORM, patch: Dict[str, Any]) -> None:
        """In-place merge into vrt_runtime_status; mark the JSON column as dirty."""
        existing = dict(row.vrt_runtime_status or {})
        existing.update(patch)
        row.vrt_runtime_status = existing

    def update_runtime_status(
        self,
        db: Session,
        execution_id: str,
        **fields: Any,
    ) -> Optional[TestExecutionORM]:
        """Patch runtime status fields (progress, position, current_waypoint_index, etc)."""
        row = self.get(db, execution_id)
        if row is None:
            return None
        self._merge_runtime_status(row, fields)
        db.commit()
        db.refresh(row)
        return row

    def append_log(
        self,
        db: Session,
        execution_id,
        *,
        level: str,
        message: str,
        source: str = "System",
    ) -> None:
        """Append one log entry to execution_logs JSONB array."""
        uid = execution_id if isinstance(execution_id, UUID) else _resolve_uuid(execution_id)
        if uid is None:
            return
        row = db.query(TestExecutionORM).filter(TestExecutionORM.id == uid).first()
        if row is None:
            return
        entry = {
            "timestamp": _utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "source": source,
        }
        existing = list(row.execution_logs or [])
        existing.append(entry)
        row.execution_logs = existing
        db.commit()

    def append_events(
        self,
        db: Session,
        execution_id: str,
        events: List[Dict[str, Any]],
    ) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None or not events:
            return row
        existing = list(row.execution_events or [])
        existing.extend(events)
        row.execution_events = existing
        db.commit()
        db.refresh(row)
        return row

    def append_warnings(
        self,
        db: Session,
        execution_id: str,
        warnings: List[str],
    ) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None or not warnings:
            return row
        existing = list(row.execution_warnings or [])
        existing.extend(warnings)
        row.execution_warnings = existing
        db.commit()
        db.refresh(row)
        return row

    def set_phase_results(
        self,
        db: Session,
        execution_id: str,
        phases: List[Dict[str, Any]],
    ) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None:
            return None
        row.phase_results = phases
        db.commit()
        db.refresh(row)
        return row

    def set_hardware_status(
        self,
        db: Session,
        execution_id: str,
        status: Dict[str, Any],
    ) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None:
            return None
        row.hardware_status = status
        db.commit()
        db.refresh(row)
        return row

    def set_summary(
        self,
        db: Session,
        execution_id: str,
        summary: Dict[str, Any],
    ) -> Optional[TestExecutionORM]:
        """Persist KPI summary (mean/min/max/std per metric) into measurements column."""
        row = self.get(db, execution_id)
        if row is None:
            return None
        row.measurements = summary
        db.commit()
        db.refresh(row)
        return row

    def set_kpi_results(
        self,
        db: Session,
        execution_id: str,
        kpi_results: Dict[str, Any],
    ) -> Optional[TestExecutionORM]:
        """Persist per-KPI target achievement into test_results column."""
        row = self.get(db, execution_id)
        if row is None:
            return None
        row.test_results = kpi_results
        db.commit()
        db.refresh(row)
        return row

    # ── KPI time-series ──────────────────────────────────────────────────

    def insert_kpi_samples(
        self,
        db: Session,
        execution_id: str,
        samples: List[KPIMetrics],
    ) -> int:
        """Bulk-insert KPI samples for an execution. Returns inserted count."""
        uid = _resolve_uuid(execution_id)
        if uid is None or not samples:
            return 0
        rows = [
            VrtKpiSample(
                execution_id=uid,
                time_s=s.time_s,
                rsrp_dbm=s.rsrp_dbm,
                rsrq_db=s.rsrq_db,
                sinr_db=s.sinr_db,
                rssi_dbm=s.rssi_dbm,
                dl_throughput_mbps=s.dl_throughput_mbps,
                ul_throughput_mbps=s.ul_throughput_mbps,
                latency_ms=s.latency_ms,
                bler_percent=s.bler_percent,
                cqi=s.cqi,
                ri=s.ri,
                pmi=s.pmi,
                mcs=s.mcs,
                position=s.position,
                velocity_kmh=s.velocity_kmh,
                event_occurred=s.event_occurred,
            )
            for s in samples
        ]
        db.bulk_save_objects(rows)
        db.commit()
        return len(rows)

    def query_kpi_samples(
        self,
        db: Session,
        execution_id: str,
        time_from: Optional[float] = None,
        time_to: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[VrtKpiSample]:
        uid = _resolve_uuid(execution_id)
        if uid is None:
            return []
        query = db.query(VrtKpiSample).filter(VrtKpiSample.execution_id == uid)
        if time_from is not None:
            query = query.filter(VrtKpiSample.time_s >= time_from)
        if time_to is not None:
            query = query.filter(VrtKpiSample.time_s <= time_to)
        query = query.order_by(VrtKpiSample.time_s)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    # ── Pydantic projections (ORM → API schema) ──────────────────────────

    @staticmethod
    def to_test_execution(orm: TestExecutionORM) -> TestExecutionSchema:
        return TestExecutionSchema(
            execution_id=str(orm.id),
            mode=TestMode(orm.mode) if orm.mode else TestMode.DIGITAL_TWIN,
            status=ExecutionStatus(orm.status),
            scenario_id=orm.scenario_id or "",
            topology_id=orm.topology_id,
            config=orm.config or {},
            start_time=orm.started_at,
            end_time=orm.completed_at,
            duration_s=orm.duration_sec,
            created_by=orm.executed_by,
            notes=orm.notes,
            logs=orm.execution_logs or [],
        )

    @staticmethod
    def to_test_status(orm: TestExecutionORM) -> TestStatus:
        runtime = orm.vrt_runtime_status or {}
        # elapsed_time_s preferentially comes from runtime status; fall back to derived
        elapsed = runtime.get("elapsed_time_s")
        if elapsed is None and orm.started_at is not None:
            end = orm.completed_at or _utcnow()
            elapsed = (end - orm.started_at).total_seconds()
        hw = orm.hardware_status or {}
        return TestStatus(
            execution_id=str(orm.id),
            status=ExecutionStatus(orm.status),
            progress_percent=runtime.get("progress_percent", 0.0),
            elapsed_time_s=elapsed or 0.0,
            remaining_time_s=runtime.get("remaining_time_s"),
            cpu_usage_percent=runtime.get("cpu_usage_percent"),
            memory_usage_mb=runtime.get("memory_usage_mb"),
            gpu_usage_percent=runtime.get("gpu_usage_percent"),
            current_waypoint_index=runtime.get("current_waypoint_index"),
            current_time_s=runtime.get("current_time_s"),
            current_position=runtime.get("current_position"),
            instruments_connected=hw.get("instruments_connected"),
            instrument_status=hw.get("instrument_status"),
            last_error=orm.error_message,
            warnings=list(orm.execution_warnings or []),
        )

    @staticmethod
    def to_test_metrics(
        orm: TestExecutionORM,
        kpi_samples: List[VrtKpiSample],
    ) -> TestMetrics:
        return TestMetrics(
            execution_id=str(orm.id),
            kpi_samples=[
                KPIMetrics(
                    time_s=s.time_s,
                    rsrp_dbm=s.rsrp_dbm,
                    rsrq_db=s.rsrq_db,
                    sinr_db=s.sinr_db,
                    rssi_dbm=s.rssi_dbm,
                    dl_throughput_mbps=s.dl_throughput_mbps,
                    ul_throughput_mbps=s.ul_throughput_mbps,
                    latency_ms=s.latency_ms,
                    bler_percent=s.bler_percent,
                    cqi=s.cqi,
                    ri=s.ri,
                    pmi=s.pmi,
                    mcs=s.mcs,
                    position=s.position,
                    velocity_kmh=s.velocity_kmh,
                    event_occurred=s.event_occurred,
                )
                for s in kpi_samples
            ],
            summary=orm.measurements or {},
            events=list(orm.execution_events or []),
            kpi_results=orm.test_results or {},
        )

    @staticmethod
    def to_phase_results(orm: TestExecutionORM) -> List[PhaseResult]:
        return [PhaseResult.model_validate(p) for p in (orm.phase_results or [])]

    @staticmethod
    def to_summary(orm: TestExecutionORM, scenario_name: str) -> ExecutionSummary:
        runtime = orm.vrt_runtime_status or {}
        return ExecutionSummary(
            execution_id=str(orm.id),
            mode=TestMode(orm.mode) if orm.mode else TestMode.DIGITAL_TWIN,
            status=ExecutionStatus(orm.status),
            scenario_name=scenario_name,
            start_time=orm.started_at,
            duration_s=orm.duration_sec,
            progress_percent=runtime.get("progress_percent", 0.0),
            created_by=orm.executed_by,
        )


vrt_execution_service = VrtExecutionService()
