"""5-phase MIMO_OTA commissioning smoke test (mock mode).

The on-site CAICT debug uses the same commissioning sandbox flow we run
in mock here. This test exercises the full executor chain end-to-end:
  precheck → reference → mimo_test → analysis → report

It pins:
  - All 5 phases dispatch and return SUCCESS in mock
  - Phase outputs land in TestExecution.measurements['phases'][<key>]
  - AnalysisExecutor populates validation_pass + validation_details
  - ReportExecutor produces a TestReport row + (best-effort) PDF

Why it matters: regressions in phase contract (e.g. MEASURE writes a key
ANALYSIS no longer reads) silently break the on-site flow. This smoke
catches them in CI before we get to a chamber and find out the hard way.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Smoke Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="Smoke-Test-Lab",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def instrument_categories(db):
    """Seed the 3 InstrumentCategory rows the precheck executor expects to
    find. Without these the precheck enumerates 0 instruments online → fails
    the `_CRITICAL_INSTRUMENT_CATEGORIES` gate even though mock drivers exist
    in the HAL service."""
    rows = [
        InstrumentCategory(
            category_key="channelEmulator",
            category_name="信道仿真器",
            driver_mode="mock",
            is_active=True,
            display_order=1,
        ),
        InstrumentCategory(
            category_key="baseStation",
            category_name="基站仿真器",
            driver_mode="mock",
            is_active=True,
            display_order=2,
        ),
        InstrumentCategory(
            category_key="positioner",
            category_name="转台",
            driver_mode="mock",
            is_active=True,
            display_order=3,
        ),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


@pytest.fixture
def hal_with_mocks(instrument_categories):
    """Inject mock drivers into the global HAL service so the MEASURE
    executor's `hal.drivers.get('positioner')` etc. find a driver instead
    of returning None. Cleared after the test to avoid bleed-through.

    Depends on `instrument_categories` so DB rows + HAL drivers are aligned —
    precheck looks them up by category_key in both places.
    """
    from app.services.instrument_hal_service import get_hal_service
    from app.hal import (
        MockChannelEmulator,
        MockBaseStation,
        MockPositioner,
        MockSignalAnalyzer,
    )

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = MockChannelEmulator(
        "mock-ce", {"model": "Mock"}
    )
    hal.drivers["baseStation"] = MockBaseStation(
        "mock-bs", {"model": "Mock"}
    )

    # MockPositioner.move_to sleeps proportional to azimuth delta (capped 5s).
    # That's realistic for prod mock but adds 5s per azimuth in this smoke
    # test. Override to instant — the smoke validates the *contract*, not
    # positioner timing semantics.
    pos = MockPositioner("mock-pos", {"model": "Mock"})

    async def _instant_move_to(azimuth, elevation):
        pos._azimuth = azimuth
        pos._elevation = elevation
        return True

    pos.move_to = _instant_move_to  # type: ignore[assignment]
    hal.drivers["positioner"] = pos

    hal.drivers["signalAnalyzer"] = MockSignalAnalyzer(
        "mock-sa", {"model": "Mock"}
    )
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


# ============================================================================
# Full 5-phase chain
# ============================================================================

class TestFivePhaseCommissioningSmoke:
    """End-to-end CommissioningSandbox flow — same path the on-site debug
    will hit when an operator clicks through 5 phases in the GUI."""

    def _run_phase(self, session_id: str, phase_name: str) -> Dict[str, Any]:
        resp = client.post(
            f"/api/v1/commissioning/sessions/{session_id}/phase/{phase_name}"
        )
        assert resp.status_code == 200, (
            f"phase={phase_name}: {resp.status_code} {resp.text}"
        )
        return resp.json()

    @staticmethod
    def _create_fast_session(lab, db, *, azimuths=(0.0, 90.0, 180.0)) -> str:
        """Create a TestCase + TestExecution with mock-friendly tight timings.

        Bypasses POST /sessions because that endpoint exposes only a subset
        of MIMOOTAConfiguration fields — stat_count, settling_time_s, and
        num_samples_per_azimuth aren't there. Setting them aggressively
        shrinks the test from ~60s to ~1s.

          - stat_count=50      → window_s = max(50/1000, 0.05) = 0.05s
          - num_samples_per_azimuth=1 → 1 window per azimuth
          - settling_time_s=0.05 → 50ms between azimuth moves
          - engine_mode=keysight_gcm → no Channel Engine dependency
          - lax pass_criteria → mock data won't be pass-graded by accident
        """
        from datetime import datetime
        from app.models.test_plan import TestExecution
        from app.services.mimo_ota import build_mimo_ota_test_case

        config_overrides = {
            "frequency_hz": 3.5e9,
            "bandwidth_mhz": 100,
            "mimo_layers": 2,
            "azimuths_deg": list(azimuths),
            "engine_mode": "keysight_gcm",
            "stat_count": 50,
            "settling_time_s": 0.05,
            "num_samples_per_azimuth": 1,
            # P1-8 (2026-05-19): smoke 不灌 ProbePathLossCalibration, 走
            # bypass 维持 5-phase chain 跑通的语义. cal gate 本身由
            # test_mimo_ota_precheck_cal_gate.py 单独覆盖.
            "precheck_strict_cal": False,
            # P1-9 (2026-05-19): smoke 不 POST /attach-dut, 走 bypass 维持
            # 5-phase chain 跑通的语义. DUT gate 本身由
            # test_mimo_ota_precheck_dut_gate.py 单独覆盖.
            "precheck_strict_dut": False,
            "pass_criteria": {
                "min_throughput_ratio": 0.0,
                "min_throughput_mbps": 0.0,
                "max_rsrp_variance_db": 999.0,
                "min_sinr_db": -999.0,
                "min_avg_rank_indicator": 0.0,
                "max_quiet_zone_ripple_db": 999.0,
            },
        }
        test_case, descriptors = build_mimo_ota_test_case(
            db,
            name="Smoke-Test-Session",
            description="5-phase commissioning smoke",
            lab_profile_id=lab.id,
            config_overrides=config_overrides,
            created_by="pytest-smoke",
        )
        execution = TestExecution(
            test_case_id=test_case.id,
            status="pending",
            started_at=datetime.utcnow(),
            config={
                "step_descriptors": [
                    {"id": d.id, "type": d.type, "parameters": d.parameters}
                    for d in descriptors
                ]
            },
            # ARCH-1 S3: 必须用真实 create_session 写的 marker —— 端点现在
            # 按 executed_by 收窄到本链 (内审 F5: 否则能拿别的链的执行行
            # 打 run-all, 并发同一套 HAL 且改写它的终态)。
            # fake 用 "pytest-smoke" 这种不存在的 marker = fake 不忠实。
            executed_by="commissioning_api",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return str(execution.id)

    def test_full_chain_completes_in_mock(self, lab, hal_with_mocks, db):
        # 1. Create session via factory with TIGHT config so the test runs in
        # ~1s instead of 60s+ (CreateSessionRequest doesn't expose stat_count
        # / settling_time_s / num_samples_per_azimuth — bypass the /sessions
        # endpoint and use the factory directly to set them).
        session_id = self._create_fast_session(lab, db)

        # 2. Run 5 phases in order. Each must dispatch & return SUCCESS or
        # at minimum a non-FAILED status (some phases — e.g. precheck — may
        # report soft-warnings which is fine for smoke).
        phase_order = ["precheck", "reference", "mimo_test", "analysis", "report"]
        phase_results: Dict[str, Dict[str, Any]] = {}
        for phase_name in phase_order:
            body = self._run_phase(session_id, phase_name)
            phase_results[phase_name] = body
            # `status` is StepExecutionStatus value: 'success' | 'failed' | 'skipped'
            assert body["status"] != "failed", (
                f"Phase {phase_name} FAILED: {body.get('result')}"
            )
            assert body["result"], f"Phase {phase_name} produced empty result"

        # 3. Verify TestExecution row has all 5 phase outputs nested under
        # measurements.phases — this is the contract ReportExecutor reads.
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        assert execution is not None
        phases = (execution.measurements or {}).get("phases") or {}
        for key in ("precheck", "reference", "measure", "analysis", "report"):
            assert key in phases, (
                f"phases dict missing '{key}' — executor didn't write_phase_result"
            )
            assert phases[key], f"phases['{key}'] is empty"

        # 4. Analysis verdict surfaced on canonical execution-level fields.
        # validation_pass may be False (mock data is random), but it must be
        # set (not None) — that proves AnalysisExecutor wrote it.
        assert execution.validation_pass is not None, (
            "AnalysisExecutor failed to write validation_pass"
        )
        assert execution.validation_details, (
            "AnalysisExecutor failed to write validation_details"
        )
        assert "verdict" in (execution.validation_details or {}), (
            "validation_details missing verdict — analysis executor regressed"
        )

        # 5. Report executor created a TestReport row (or at minimum recorded
        # the attempt — PDF generation is best-effort).
        report_payload = phases["report"]
        assert report_payload.get("report_id"), "report_id missing"
        # PDF generation may have warnings (e.g. template missing in test env)
        # but report_db_id should still be set since the row creation comes
        # before generation. report_file_path is allowed to be None.

        # 6. Execution lifecycle marked completed.
        assert execution.status == "completed", (
            f"execution.status='{execution.status}' (expected 'completed')"
        )

    def test_measure_phase_writes_azimuth_results(self, lab, hal_with_mocks, db):
        """The measure phase contract: azimuth_results must be a list of
        per-azimuth dicts with the KPI keys analysis + report consume."""
        session_id = self._create_fast_session(lab, db, azimuths=(0.0, 180.0))

        # Run up to and including mimo_test
        for phase_name in ("precheck", "reference", "mimo_test"):
            self._run_phase(session_id, phase_name)

        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        measure = (execution.measurements or {}).get("phases", {}).get("measure", {})
        azimuth_results = measure.get("azimuth_results")
        assert isinstance(azimuth_results, list)
        assert len(azimuth_results) == 2  # one per requested azimuth
        for az in azimuth_results:
            for required_key in (
                "azimuth_deg",
                "rsrp_dbm",
                "sinr_db",
                "throughput_mbps",
                "rank_indicator",
            ):
                assert required_key in az, (
                    f"azimuth_results entry missing '{required_key}' — "
                    f"analysis/report executors depend on this key"
                )

    def test_analysis_reads_what_measure_wrote(self, lab, hal_with_mocks, db):
        """Contract test: analysis must see measure's output. If measure
        renames a key without updating analysis, this catches it."""
        session_id = self._create_fast_session(lab, db, azimuths=(0.0,))
        for phase_name in ("precheck", "reference", "mimo_test", "analysis"):
            self._run_phase(session_id, phase_name)

        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        analysis = (execution.measurements or {}).get("phases", {}).get("analysis", {})
        # These keys are what ReportExecutor's content_data builder reads.
        # Missing any of these breaks PDF generation downstream.
        for key in (
            "verdict",
            "details",
            "avg_throughput_mbps",
            "throughput_pass",
            "rsrp_variance_db",
            "rsrp_pass",
            "avg_sinr_db",
            "sinr_pass",
            "avg_rank_indicator",
            "rank_pass",
            "qz_pass",
            "margin_db",
        ):
            assert key in analysis, (
                f"analysis output missing '{key}' — "
                f"AnalysisExecutor regressed or measure changed contract"
            )
