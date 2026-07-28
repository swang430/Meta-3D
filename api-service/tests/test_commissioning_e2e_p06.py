"""P0-6 — Mock-data first-call end-to-end, strict acceptance.

Why a separate file from ``test_commissioning_smoke``:

The existing smoke accepts "no phase FAILED" + best-effort PDF. That's
the right gate for the canary — it ran green even while a real bug
silently nuked the PDF for months
(``AttributeError: 'TestExecution' object has no attribute 'test_plan'``
in ReportExecutor was caught and downgraded to a warning, leaving the
test green with ``report_file_path=None``).

P0-6's acceptance is stricter:
  - One TestExecution runs all 5 phases to completion
  - ``phase_statuses`` ends at ``{precheck/reference/mimo_test/analysis/report: "completed"}``
  - **A PDF report is generated and actually exists on disk**
  - **No silently-swallowed PDF exception** (precheck still warns about
    missing path-loss / topology — those gaps are P0-3/P0-4 territory,
    not in P0-6 scope)
  - Drives the full ``/run-all`` endpoint, not phase-by-phase, so the
    pipeline driver itself is exercised

The existing smoke remains the looser canary — keep it. This file pins
what we mean when we say "mock first-call passes."
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.calibration import CalibrationCertificate
from app.models.chamber import ChamberType, create_chamber_from_preset
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


def _override_get_db():
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
    app.dependency_overrides[get_db] = _override_get_db
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P0-6 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def mock_calibration_certificate(db):
    """A PASS cal cert with valid_until well in the future.

    The precheck executor reads ``context.calibration_certificate`` and
    only warns when it's None — having a present + passing cert pulls
    the precheck output into a clean "no missing-cert warning" state,
    which is the only cal-related precheck behavior P0-6 controls.
    Per-RF-chain path-loss compensation is P0-3 (real measurement);
    the mock cert here intentionally does not claim path-loss numbers.
    """
    now = datetime.utcnow()
    cert = CalibrationCertificate(
        certificate_number=f"MOCK-P06-{uuid.uuid4().hex[:8]}",
        system_name="Meta-3D MPAC (mock)",
        lab_name="P0-6 Mock Lab",
        calibration_date=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        standards=["3GPP TS 34.114", "CTIA OTA Ver. 4.0"],
        trp_pass=True,
        tis_pass=True,
        repeatability_pass=True,
        comparability_pass=True,
        overall_pass=True,
        calibrated_by="pytest-p06",
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@pytest.fixture
def lab(db, chamber, mock_calibration_certificate):
    lp = LabProfile(
        name="P0-6-Lab",
        chamber_config_id=chamber.id,
        active_calibration_certificate_id=mock_calibration_certificate.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def instrument_categories(db):
    """The 3 InstrumentCategory rows precheck enumerates. Without these
    the precheck _CRITICAL_INSTRUMENT_CATEGORIES gate fails even though
    mock drivers are in HAL."""
    rows = [
        InstrumentCategory(category_key="channelEmulator", category_name="信道仿真器",
                           driver_mode="mock", is_active=True, display_order=1),
        InstrumentCategory(category_key="baseStation", category_name="基站仿真器",
                           driver_mode="mock", is_active=True, display_order=2),
        InstrumentCategory(category_key="positioner", category_name="转台",
                           driver_mode="mock", is_active=True, display_order=3),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


@pytest.fixture
def hal_with_mocks(instrument_categories):
    """Mock drivers in HAL with instant positioner moves (no 5s-per-azimuth
    sleep)."""
    from app.services.instrument_hal_service import get_hal_service
    from app.hal import (
        MockBaseStation, MockChannelEmulator, MockPositioner, MockSignalAnalyzer,
    )
    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = MockChannelEmulator("mock-ce", {"model": "Mock"})
    hal.drivers["baseStation"] = MockBaseStation("mock-bs", {"model": "Mock"})
    pos = MockPositioner("mock-pos", {"model": "Mock"})

    async def _instant_move_to(azimuth, elevation):
        pos._azimuth = azimuth
        pos._elevation = elevation
        return True

    pos.move_to = _instant_move_to  # type: ignore[assignment]
    hal.drivers["positioner"] = pos
    hal.drivers["signalAnalyzer"] = MockSignalAnalyzer("mock-sa", {"model": "Mock"})
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


def _create_fast_session(lab: LabProfile, db, *, set_strict_false: bool = True) -> str:
    """Build a TestCase + TestExecution with tight mock timings — same
    factory the looser smoke uses, lifted into this file so the strict
    test is self-contained.

    ``set_strict_false`` (default True): pin precheck_strict_cal/dut=False
    explicitly (the historic smoke path). Pass ``False`` to leave them at the
    schema default (True) and exercise the *operator's actual GUI path* —
    where the mock-aware runtime gate (precheck.py: mock CE/BS → gate N/A)
    is what lets the default-config sandbox flow complete.
    """
    from app.services.mimo_ota import build_mimo_ota_test_case

    overrides: dict = {
        "frequency_hz": 3.5e9,
        "bandwidth_mhz": 100,
        "mimo_layers": 2,
        "azimuths_deg": [0.0, 90.0, 180.0],
        "engine_mode": "keysight_gcm",
        "stat_count": 50,
        "settling_time_s": 0.05,
        "num_samples_per_azimuth": 1,
    }
    if set_strict_false:
        # P1-8/P1-9 (2026-05-19): historic smoke path — pin gates off so the
        # 5-phase chain runs without a real cal/DUT. The gates themselves are
        # covered by test_mimo_ota_precheck_{cal,dut}_gate.py.
        overrides["precheck_strict_cal"] = False
        overrides["precheck_strict_dut"] = False
    test_case, descriptors = build_mimo_ota_test_case(
        db,
        name="P0-6 Strict E2E",
        description="P0-6 acceptance: mock first-call end-to-end",
        lab_profile_id=lab.id,
        config_overrides={
            **overrides,
            "pass_criteria": {
                "min_throughput_ratio": 0.0,
                "min_throughput_mbps": 0.0,
                "max_rsrp_variance_db": 999.0,
                "min_sinr_db": -999.0,
                "min_avg_rank_indicator": 0.0,
                "max_quiet_zone_ripple_db": 999.0,
            },
        },
        created_by="pytest-p06",
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
        # ARCH-1 S3 内审 F5: 端点按 executed_by 收窄到本链, fake 必须用
        # 真实 create_session 写的 marker (不存在的 marker = fake 不忠实)
        executed_by="commissioning_api",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return str(execution.id)


# ---------------------------------------------------------------------------
# P0-6 strict acceptance
# ---------------------------------------------------------------------------

class TestP06MockFirstCall:
    """Pins the four bullets of the P0-6 acceptance section in the
    roadmap — see docs/roadmap-first-call.md."""

    def test_run_all_completes_with_pdf_on_disk(
        self, lab, hal_with_mocks, db,
    ):
        session_id = _create_fast_session(lab, db)

        # Drive the pipeline through `/run-all`, not phase-by-phase. The
        # difference matters: run-all is the endpoint the GUI's "run all
        # phases" button hits, so this test exercises the same dispatcher
        # path operators trigger from the sandbox.
        r = client.post(f"/api/v1/commissioning/sessions/{session_id}/run-all")
        assert r.status_code == 200, r.text
        session = r.json()

        # Acceptance #1: phase_statuses ends with all 5 phases "completed"
        # (the API derives this from each phase's measurement payload).
        # The roadmap's informal "passed" maps to the implementation's
        # "completed" — see _phase_status_from_payload.
        ps = session["phase_statuses"]
        expected_phases = {"precheck", "reference", "mimo_test", "analysis", "report"}
        assert set(ps.keys()) == expected_phases, ps
        for phase, status in ps.items():
            assert status == "completed", (
                f"phase {phase!r} ended at {status!r} (expected 'completed') — "
                f"full statuses: {ps}"
            )

        # The endpoint's commits happened in a different SQLAlchemy
        # session (the dependency-injected one from _override_get_db).
        # Without expiring, this test's `db` session would hand back
        # the cached TestExecution instance from before the request
        # — stale measurements, stale status, stale duration_sec.
        # Empirically the test still passes on SQLite + StaticPool
        # today, but the cached-read pattern is fragile across pool /
        # autoflush / Postgres changes (Codex P2 review on PR #19).
        db.expire_all()

        # Acceptance #2: a PDF report is generated AND the file exists
        # on disk. Pre-fix, ReportExecutor caught the AttributeError on
        # execution.test_plan and downgraded it to a warning, leaving
        # report_file_path=None while still reporting phase status=success.
        # Pinning the file existence is the regression guard.
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        report_payload = (execution.measurements or {}).get("phases", {}).get("report", {})
        assert report_payload.get("report_id"), report_payload
        assert report_payload.get("report_db_id"), (
            "report_db_id missing — ReportService.create_report didn't persist"
        )
        pdf_path = report_payload.get("report_file_path")
        assert pdf_path, (
            f"report_file_path is None — PDF generation silently failed.\n"
            f"warnings: {report_payload.get('warnings')}"
        )
        assert os.path.exists(pdf_path), (
            f"report_file_path={pdf_path!r} but the file does not exist on disk"
        )
        assert os.path.getsize(pdf_path) > 0, (
            f"PDF at {pdf_path} is empty (0 bytes)"
        )

        # Acceptance #3: no PDF-related warnings on the report phase.
        # Other warnings (no SwitchTopology, no per-chain path-loss) are
        # P0-3/P0-4 territory — those will go away when real calibration
        # data arrives. We only police the report executor's own
        # warnings here.
        report_warnings = report_payload.get("warnings") or []
        pdf_related = [
            w for w in report_warnings
            if "pdf" in w.lower() or "generation failed" in w.lower()
        ]
        assert not pdf_related, (
            f"PDF generation surfaced warnings (silent-failure regression?):\n"
            f"  {pdf_related}"
        )

        # Acceptance #4: lifecycle marked completed.
        assert execution.status == "completed", execution.status
        assert execution.duration_sec is not None

        # Audit 2026-05-17 Y2: ``asc_files_loaded`` is ASC-specific
        # (ExternalWaveformStrategy); GCM mode doesn't use .asc files at
        # all. Was hardcoded True in both modes before — semantically
        # misleading. Pin that the field is OMITTED in GCM result so a
        # regression that re-hardcodes it would fail here. This session
        # was created with engine_mode="keysight_gcm".
        # Note: storage key is "measure" (see measure.py:write_phase_result),
        # not "mimo_test" (which is the public API phase alias).
        measure_payload = (
            (execution.measurements or {}).get("phases", {}).get("measure", {})
        )
        assert measure_payload.get("engine_mode") == "keysight_gcm", (
            f"sanity: this test expects GCM mode (got "
            f"{measure_payload.get('engine_mode')!r}); ASC-specific "
            f"assertion below would not be meaningful otherwise. "
            f"Available phases: {list((execution.measurements or {}).get('phases', {}).keys())}"
        )
        assert "asc_files_loaded" not in measure_payload, (
            f"asc_files_loaded should NOT appear in GCM mode result "
            f"(audit Y2 — engine-specific field). Got: "
            f"{measure_payload.get('asc_files_loaded')!r}"
        )

    def test_run_all_default_config_mock_aware_gates(
        self, lab, hal_with_mocks, db,
    ):
        """The operator's ACTUAL GUI path: create a session with DEFAULT config
        (precheck_strict_dut/cal NOT overridden → schema default True), then
        run-all. With mock CE/BS the runtime mock-aware gate (precheck.py 5/5b)
        makes the strict gates N/A, so all 5 phases must still complete + a PDF
        lands — i.e. "mock first-call (full)" works from the sandbox without any
        Lab-smoke toggle or explicit strict override. Distinct from
        test_run_all_completes_with_pdf_on_disk, which pins gates off explicitly.
        """
        session_id = _create_fast_session(lab, db, set_strict_false=False)

        r = client.post(f"/api/v1/commissioning/sessions/{session_id}/run-all")
        assert r.status_code == 200, r.text
        session = r.json()

        ps = session["phase_statuses"]
        expected_phases = {"precheck", "reference", "mimo_test", "analysis", "report"}
        assert set(ps.keys()) == expected_phases, ps
        for phase, status in ps.items():
            assert status == "completed", (
                f"phase {phase!r} ended at {status!r} under default config — "
                f"mock-aware gate should have let it through. statuses: {ps}"
            )

        db.expire_all()
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        phases = (execution.measurements or {}).get("phases", {})

        # First lock that this session really used the DEFAULT *strict* config —
        # otherwise the "gate N/A" assertion below is a false guard: precheck.py
        # emits "gate N/A — baseStation is mock/absent" whenever the BS is mock,
        # REGARDLESS of the flag value (the not-bs_is_real branch fires first).
        # So if the schema default ever flipped to non-strict, the reason string
        # alone wouldn't catch it. Assert the effective flags are True. (Codex
        # on PR #78.)
        from app.services.mimo_ota.executors._helpers import load_mimo_ota_config

        cfg = load_mimo_ota_config(execution)
        assert cfg.precheck_strict_dut is True, (
            "this test must exercise the DEFAULT strict config (schema default "
            f"True), not an override — got precheck_strict_dut={cfg.precheck_strict_dut!r}"
        )
        assert cfg.precheck_strict_cal is True, (
            f"expected default strict_cal=True, got {cfg.precheck_strict_cal!r}"
        )

        # With strict=True confirmed, the precheck still passing + dut_pass=True
        # proves the mock-aware *runtime* bypass (mock BS → gate N/A), not a
        # config opt-out.
        precheck = phases.get("precheck", {})
        assert precheck.get("overall_pass") is True, precheck
        assert precheck.get("dut_pass") is True
        assert "gate N/A" in (precheck.get("dut_pass_reason") or ""), (
            f"expected mock auto-skip reason, got {precheck.get('dut_pass_reason')!r}"
        )

        # And the full chain still produced a PDF on disk.
        report_payload = phases.get("report", {})
        pdf_path = report_payload.get("report_file_path")
        assert pdf_path and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0, (
            f"default-config run-all didn't produce a PDF: report={report_payload}"
        )
        assert execution.status == "completed"

    def test_precheck_no_missing_cert_warning(
        self, lab, hal_with_mocks, db,
    ):
        """The mock_calibration_certificate fixture should be visible to
        the precheck executor (via LabProfile.active_calibration_certificate_id)
        — verifies the wiring instead of just trusting the fixture."""
        session_id = _create_fast_session(lab, db)
        client.post(f"/api/v1/commissioning/sessions/{session_id}/phase/precheck")

        # Endpoint committed in its own session; expire ours so the
        # query below sees the post-precheck row state, not the cached
        # pre-request instance. See test above for the rationale.
        db.expire_all()

        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        precheck = (execution.measurements or {}).get("phases", {}).get("precheck", {})
        assert precheck.get("calibration_certificate_id"), (
            "precheck didn't pick up the mock cert — context resolver may "
            "have skipped LabProfile.active_calibration_certificate_id"
        )
        warnings = precheck.get("warnings") or []
        assert not any(
            "calibration_certificate" in w.lower() for w in warnings
        ), f"unexpected cert warning even with fixture present: {warnings}"

    def test_precheck_payload_carries_path_loss_calibration_valid_key(
        self, lab, hal_with_mocks, db,
    ):
        """Pin the canonical key the GUI Commissioning/Phases.tsx reads
        to render '校准有效性: 有效/已过期'.

        2026-05-19 chore: discovered during P1-5 local-half on-site smoke
        check — GUI was reading ``data.calibration_valid`` (no prefix),
        backend writes ``data.path_loss_calibration_valid``, so the badge
        rendered '已过期' regardless of DB state. Fixed by renaming the
        GUI read to match the canonical backend key. This test pins the
        backend side so any future rename surfaces immediately rather
        than silently re-breaking the GUI badge.
        """
        session_id = _create_fast_session(lab, db)
        client.post(f"/api/v1/commissioning/sessions/{session_id}/phase/precheck")
        db.expire_all()

        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(session_id))
            .first()
        )
        precheck = (execution.measurements or {}).get("phases", {}).get("precheck", {})

        # Key MUST exist (GUI Phases.tsx:38 reads data.path_loss_calibration_valid)
        assert "path_loss_calibration_valid" in precheck, (
            f"precheck result_payload missing 'path_loss_calibration_valid' — "
            f"GUI badge '校准有效性' will always render '已过期'. "
            f"Available keys: {sorted(precheck.keys())}"
        )
        # Value must be a real bool, not None/missing
        assert isinstance(precheck["path_loss_calibration_valid"], bool), (
            f"path_loss_calibration_valid must be bool, got "
            f"{type(precheck['path_loss_calibration_valid']).__name__}: "
            f"{precheck['path_loss_calibration_valid']!r}"
        )
