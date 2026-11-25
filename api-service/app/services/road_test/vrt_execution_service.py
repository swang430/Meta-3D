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

import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.road_test.measurement_evidence import calibrated_setup, confirmed_throughput_scope, measured_item, real_driver_pair
from app.core.logging_config import current_execution_id
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
from app.schemas.road_test.execution import PhaseResult, RunnerObservation

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
        twin_input: Optional[Dict[str, Any]] = None,
        conducted_setup: Optional[Dict[str, Any]] = None,
        ota_setup: Optional[Dict[str, Any]] = None,
    ) -> TestExecutionORM:
        """Create a new VRT execution row in IDLE state."""
        row = TestExecutionORM(
            status=ExecutionStatus.IDLE.value,
            mode=mode.value,
            scenario_id=scenario_id,
            topology_id=topology_id,
            config=config or {},
            vrt_twin_input=twin_input,
            vrt_conducted_setup=conducted_setup,
            vrt_ota_setup=ota_setup,
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
        # P1-36: 从这一刻起，本次请求内的日志都归属这次 VRT 执行。
        current_execution_id.set(str(row.id))
        self.append_log(db, row.id, level="INFO", message="Execution created", source="System")
        logger.info("Created VRT execution %s (mode=%s, scenario=%s)", row.id, mode.value, scenario_id)
        return row

    def get(self, db: Session, execution_id: str) -> Optional[TestExecutionORM]:
        uid = _resolve_uuid(execution_id)
        if uid is None:
            return None
        row = db.query(TestExecutionORM).filter(TestExecutionORM.id == uid).first()
        if row is not None:
            # P1-36: VRT 没有可包住的运行作用域 —— start / pause / resume / stop /
            # complete / fail 各是一次**独立请求**，所以没法像 test_case_runner
            # 那样"入口 set 一次管到底"。
            #
            # `get()` 是**唯一的解析点**（`_transition` 与 `fail` 都走它），
            # 在这里 set 就等于给每一次状态跃迁都盖上执行身份 —— 用户要的
            # 「至少开始和结束要标记」由此自动满足，且读操作也一并归属。
            #
            # ⚠ 在 getter 里设 contextvar 看着奇怪，但语义是准的：
            # "本次请求是关于这个执行的"。这是本文件里唯一的 choke point，
            # 分散到 7 个跃迁方法里反而会漏（新增一个方法就少一处）。
            current_execution_id.set(str(row.id))
        return row

    def list(
        self,
        db: Session,
        mode: Optional[TestMode] = None,
        status: Optional[ExecutionStatus] = None,
        limit: int = 1000,
        scenario_id: Optional[str] = None,
    ) -> List[TestExecutionORM]:
        """List VRT executions. Filters out non-VRT TestExecution rows by requiring `mode IS NOT NULL`."""
        query = db.query(TestExecutionORM).filter(TestExecutionORM.mode.isnot(None))
        if scenario_id is not None:
            query = query.filter(TestExecutionORM.scenario_id == scenario_id)
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
        expected_status: ExecutionStatus,
        log_message: str,
        set_started_at: bool = False,
        set_completed_at: bool = False,
        progress_percent: Optional[float] = None,
    ) -> Optional[TestExecutionORM]:
        row = self.get(db, execution_id)
        if row is None:
            return None
        values: Dict[str, Any] = {"status": target_status.value}
        if set_started_at and row.started_at is None:
            values["started_at"] = _utcnow()
        if set_completed_at:
            completed_at = _utcnow()
            values["completed_at"] = completed_at
            if row.started_at is not None:
                values["duration_sec"] = (completed_at - row.started_at).total_seconds()
        if progress_percent is not None:
            runtime_status = dict(row.vrt_runtime_status or {})
            runtime_status["progress_percent"] = progress_percent
            values["vrt_runtime_status"] = runtime_status

        if row.vrt_twin_input:
            from app.services.road_test.twin_playback import elapsed
            now = _utcnow()
            runtime = dict(values.get("vrt_runtime_status", row.vrt_runtime_status) or {})
            runtime["twin_elapsed_s"] = elapsed(row, now)
            runtime["twin_running_since"] = now.isoformat() if target_status == ExecutionStatus.RUNNING else None
            values["vrt_runtime_status"] = runtime

        updated = db.query(TestExecutionORM).filter(
            TestExecutionORM.id == row.id,
            TestExecutionORM.status == expected_status.value,
        ).update(values, synchronize_session=False)
        if updated != 1:
            db.rollback()
            return None

        db.commit()
        db.expire_all()
        transitioned_row = self.get(db, execution_id)
        if transitioned_row is not None:
            self.append_log(
                db,
                transitioned_row.id,
                level="INFO",
                message=log_message,
                source="System",
            )
        return transitioned_row

    def start(
        self,
        db: Session,
        execution_id: str,
        *,
        expected_status: ExecutionStatus = ExecutionStatus.IDLE,
    ) -> Optional[TestExecutionORM]:
        return self._transition(
            db, execution_id, ExecutionStatus.RUNNING,
            expected_status=expected_status,
            log_message="Execution started",
            set_started_at=True,
        )

    def pause(
        self,
        db: Session,
        execution_id: str,
        *,
        expected_status: ExecutionStatus = ExecutionStatus.RUNNING,
    ) -> Optional[TestExecutionORM]:
        return self._transition(
            db,
            execution_id,
            ExecutionStatus.PAUSED,
            expected_status=expected_status,
            log_message="Execution paused",
        )

    def resume(
        self,
        db: Session,
        execution_id: str,
        *,
        expected_status: ExecutionStatus = ExecutionStatus.PAUSED,
    ) -> Optional[TestExecutionORM]:
        return self._transition(
            db,
            execution_id,
            ExecutionStatus.RUNNING,
            expected_status=expected_status,
            log_message="Execution resumed",
        )

    def _terminal_transition(
        self,
        db: Session,
        execution_id: str,
        target_status: ExecutionStatus,
        *,
        expected_status: ExecutionStatus,
        log_message: str,
        progress_percent: Optional[float] = None,
    ) -> Optional[TestExecutionORM]:
        """Atomically choose the sole terminal action/archive owner."""
        row = self.get(db, execution_id)
        if row is None:
            return None

        completed_at = _utcnow()
        values: Dict[str, Any] = {
            "status": target_status.value,
            "completed_at": completed_at,
        }
        if row.started_at is not None:
            values["duration_sec"] = (completed_at - row.started_at).total_seconds()
        if progress_percent is not None:
            runtime_status = dict(row.vrt_runtime_status or {})
            runtime_status["progress_percent"] = progress_percent
            values["vrt_runtime_status"] = runtime_status

        if row.vrt_twin_input:
            from app.services.road_test.twin_playback import elapsed
            runtime = dict(values.get("vrt_runtime_status", row.vrt_runtime_status) or {})
            runtime["twin_elapsed_s"] = elapsed(row, completed_at)
            if target_status == ExecutionStatus.COMPLETED and row.started_at:
                runtime["twin_elapsed_s"] = row.vrt_twin_input["scenario_snapshot"]["route"]["duration_s"]
            runtime["twin_running_since"] = None
            values["vrt_runtime_status"] = runtime

        updated = db.query(TestExecutionORM).filter(
            TestExecutionORM.id == row.id,
            TestExecutionORM.status == expected_status.value,
        ).update(values, synchronize_session=False)
        if updated != 1:
            db.rollback()
            return None

        db.commit()
        db.expire_all()
        terminal_row = self.get(db, execution_id)
        if terminal_row is not None:
            self.append_log(
                db,
                terminal_row.id,
                level="INFO",
                message=log_message,
                source="System",
            )
        return terminal_row

    def stop(
        self,
        db: Session,
        execution_id: str,
        *,
        expected_status: ExecutionStatus = ExecutionStatus.RUNNING,
    ) -> Optional[TestExecutionORM]:
        return self._terminal_transition(
            db,
            execution_id,
            ExecutionStatus.STOPPED,
            expected_status=expected_status,
            log_message="Execution stopped",
        )

    def complete(
        self,
        db: Session,
        execution_id: str,
        *,
        expected_status: ExecutionStatus = ExecutionStatus.RUNNING,
    ) -> Optional[TestExecutionORM]:
        return self._terminal_transition(
            db,
            execution_id,
            ExecutionStatus.COMPLETED,
            expected_status=expected_status,
            log_message="Execution completed",
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

    def record_observation(
        self, db: Session, execution_id: str, *, metric: str, value, driver,
        time_s: float, source_frame_time_s=None, device_playback_time_s=None,
        sampled_at=None, throughput_readback=None, current_throughput=False,
    ) -> RunnerObservation:
        """运行器在一次回读后调用。time_s 是执行经过时间，缺测传 None。"""
        from app.hal.propsim_f64 import RealPropsimF64Driver
        from app.hal.uxm_base_station import RealUxmDriver
        from app.services.instrument_hal_service import get_hal_service, is_mock_driver

        row = (
            db.query(TestExecutionORM).filter_by(id=_resolve_uuid(execution_id))
            .with_for_update().populate_existing().one_or_none()
        )
        if row is None or row.status != ExecutionStatus.RUNNING.value:
            raise ValueError("只有运行中的执行可以记录设备回读。")
        units = {"connection_state": "", "dl_throughput_mbps": "Mbps",
                 "ul_throughput_mbps": "Mbps", "playback_position_s": "s"}
        if metric not in units:
            raise ValueError("无法识别采样项目。")
        if metric != "connection_state" and value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("吞吐量和播放位置必须是有限的非负数。")
        expected_driver = RealPropsimF64Driver if metric == "playback_position_s" else RealUxmDriver
        scope = confirmed_throughput_scope(metric, value, throughput_readback, current=current_throughput)
        provenance = "unverified"
        setup = (row.vrt_ota_setup if row.mode == "ota" else row.vrt_conducted_setup) or {}
        binding = setup.get("binding") or {}
        mock_only = (setup.get("asset") or {}).get("mock_only") is True or binding.get("mock_only") is True
        simulated_driver = is_mock_driver(driver)
        if mock_only and driver is not None and not simulated_driver:
            raise ValueError("模拟专用资产只接受模拟驱动的回读。")
        simulated_run = row.mode == TestMode.DIGITAL_TWIN.value or binding.get("execution_mode") == "simulated"
        if (mock_only or simulated_run or simulated_driver
                or (metric.endswith("_throughput_mbps") and getattr(throughput_readback, "throughput_scope", None) == "simulated")):
            provenance = "simulated"
        elif calibrated_setup(row.mode, setup) and type(driver) is expected_driver and value is not None:
            drivers = get_hal_service().drivers
            role = "channelEmulator" if metric == "playback_position_s" else "baseStation"
            if (real_driver_pair(drivers) and drivers.get(role) is driver
                    and (not metric.endswith("_throughput_mbps") or scope is not None)):
                provenance = "server_measured"
        observation = RunnerObservation(
            metric=metric, value=value, unit=units[metric], time_s=time_s,
            source=type(driver).__name__ if driver is not None else "无设备",
            provenance=provenance, throughput_scope=scope if provenance == "server_measured" else None, sampled_at=sampled_at or _utcnow(),
            source_frame_time_s=source_frame_time_s, device_playback_time_s=device_playback_time_s,
        )
        db.add(VrtKpiSample(execution_id=row.id, time_s=time_s,
                            observation=observation.model_dump(mode="json")))
        db.commit()
        return observation

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
        query = query.order_by(VrtKpiSample.time_s, VrtKpiSample.id)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    # ── Pydantic projections (ORM → API schema) ──────────────────────────

    @staticmethod
    def to_test_execution(orm: TestExecutionORM) -> TestExecutionSchema:
        config = dict(orm.config or {})
        config.pop("digital_twin", None)
        if orm.mode == "digital_twin" and orm.vrt_twin_input:
            config["digital_twin"] = orm.vrt_twin_input
        config.pop("ota", None)
        if orm.mode == "ota" and orm.vrt_ota_setup is not None:
            config["ota"] = orm.vrt_ota_setup
        config.pop("conducted", None)
        if orm.mode == "conducted" and orm.vrt_conducted_setup is not None:
            config["conducted"] = orm.vrt_conducted_setup
        return TestExecutionSchema(
            execution_id=str(orm.id),
            mode=TestMode(orm.mode) if orm.mode else TestMode.DIGITAL_TWIN,
            status=ExecutionStatus(orm.status),
            scenario_id=orm.scenario_id or "",
            topology_id=orm.topology_id,
            config=config,
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
        if getattr(orm, "vrt_twin_input", None):
            from app.services.road_test.twin_playback import elapsed
            cursor = elapsed(orm, _utcnow())
            duration = orm.vrt_twin_input["scenario_snapshot"]["route"]["duration_s"]
            runtime = {**runtime, "current_time_s": cursor, "progress_percent": 100 * cursor / duration,
                       "remaining_time_s": (duration - cursor) / orm.vrt_twin_input["acceleration_factor"]}
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
            conducted_stop_pending=orm.mode == TestMode.CONDUCTED.value and "conducted_shutdown_ports" in hw,
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
        observations = [s.observation for s in kpi_samples if getattr(s, "observation", None)]
        trusted_setup = calibrated_setup(getattr(orm, "mode", None), getattr(orm, "vrt_conducted_setup", None))
        observations = [
            {**item, "provenance": "unverified"}
            if item.get("provenance") == "server_measured" and not (trusted_setup and measured_item(item))
            else item for item in observations
        ]
        kpi_samples = [s for s in kpi_samples if not getattr(s, "observation", None)]
        return TestMetrics(
            observations=observations,
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
            summary={
                name: {**stats, "passed": None, "provenance": "client_simulated"}
                for name, stats in (orm.measurements or {}).items() if isinstance(stats, dict)
            },
            events=[{**event, "provenance": "client_simulated"} for event in (orm.execution_events or [])
                    if isinstance(event, dict)],
            kpi_results={},
            provenance="client_simulated" if kpi_samples else None,
        )

    @staticmethod
    def to_phase_results(orm: TestExecutionORM) -> List[PhaseResult]:
        return [PhaseResult.model_validate(p) for p in (orm.phase_results or [])]

    @staticmethod
    def to_summary(orm: TestExecutionORM, scenario_name: str) -> ExecutionSummary:
        runtime = orm.vrt_runtime_status or {}
        return ExecutionSummary(
            conducted=orm.vrt_conducted_setup if orm.mode == "conducted" else None,
            ota=orm.vrt_ota_setup if orm.mode == "ota" else None,
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
