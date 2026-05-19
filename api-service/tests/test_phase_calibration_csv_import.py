"""P1-5 local half — offline CSV import for probe phase calibration.

Pins the four kinds of contract the new endpoint must hold:

1. **Happy path** — valid 4-column CSV + Form metadata → 201 + DB row + sane response shape.
2. **CSV validation** — missing column, non-numeric cell, empty body, unwrapped-phase guard.
3. **Probe-identifier validation** — out-of-range probe_id, self-reference, bad polarization.
4. **Replace-existing semantics** — second import of same (probe_id, polarization) invalidates the prior VALID row; round-trip via GET /phase/{probe_id} returns the *new* cert's data.

These tests use an in-memory SQLite for isolation (per project precedent in
test_probe_calibration_api.py); the contract being pinned is dialect-agnostic.
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePhaseCalibration,
)
from app.services.probe_calibration_service import PROBE_ID_MAX


CSV_ENDPOINT = "/api/v1/calibration/probe/phase/import-csv"


# ---------------------------------------------------------------------------
# Fixtures — fresh in-memory SQLite per test for clean isolation
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db, SessionLocal
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    db, SessionLocal = db_session

    def _override():
        local = SessionLocal()
        try:
            yield local
        finally:
            local.close()

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior


def _valid_csv(num_rows: int = 5) -> bytes:
    """Build a syntactically + physically valid CSV body."""
    header = "frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
    body = "\n".join(
        f"{3400 + i * 25},{(-12.5 + i * 0.1):.3f},{(0.85 + i * 0.01):.3f},{2.0:.2f}"
        for i in range(num_rows)
    )
    return (header + body).encode("utf-8")


def _post_csv(client, csv_bytes: bytes, **form_overrides):
    """POST helper with sensible defaults so each test only overrides what matters."""
    form = {
        "probe_id": "5",
        "polarization": "V",
        "reference_probe_id": "0",
        "vna_model": "Keysight P9374A",
        "vna_serial": "MY12345678",
        "calibrated_by": "pytest",
    }
    form.update({k: str(v) for k, v in form_overrides.items()})
    return client.post(
        CSV_ENDPOINT,
        files={"file": ("phase_cal.csv", io.BytesIO(csv_bytes), "text/csv")},
        data=form,
    )


# ---------------------------------------------------------------------------
# (1) Happy path
# ---------------------------------------------------------------------------

class TestImportHappyPath:
    def test_201_returns_calibration_id_and_freq_count(self, client):
        r = _post_csv(client, _valid_csv(num_rows=10))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["success"] is True
        assert uuid.UUID(body["calibration_id"])  # well-formed UUID
        assert body["num_frequency_points"] == 10
        assert body["invalidated_id"] is None  # nothing to replace on first import
        assert body["error"] is None

    def test_row_actually_persisted(self, client, db_session):
        _post_csv(client, _valid_csv(num_rows=5))
        db, _ = db_session
        rows = (
            db.query(ProbePhaseCalibration)
            .filter(ProbePhaseCalibration.probe_id == 5)
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.polarization == "V"
        assert row.reference_probe_id == 0
        assert len(row.frequency_points_mhz) == 5
        assert len(row.phase_offset_deg) == 5
        assert len(row.group_delay_ns) == 5
        assert len(row.phase_uncertainty_deg) == 5
        assert row.status == CalibrationStatus.VALID.value
        assert row.vna_model == "Keysight P9374A"
        assert row.calibrated_by == "pytest"


# ---------------------------------------------------------------------------
# (2) CSV validation
# ---------------------------------------------------------------------------

class TestCSVValidation:
    def test_empty_body_rejected_400(self, client):
        r = client.post(
            CSV_ENDPOINT,
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
            data={"probe_id": "5", "polarization": "V"},
        )
        assert r.status_code == 400
        assert "empty" in r.json()["detail"].lower()

    def test_missing_required_column_400(self, client):
        # Drop the group_delay_ns column entirely
        csv = (
            b"frequency_mhz,phase_offset_deg,phase_uncertainty_deg\n"
            b"3400,-12.5,2.1\n"
        )
        r = _post_csv(client, csv)
        assert r.status_code == 400
        assert "missing required column" in r.json()["detail"].lower()
        assert "group_delay_ns" in r.json()["detail"]

    def test_non_numeric_cell_400_with_row_number(self, client):
        csv = (
            b"frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
            b"3400,-12.5,0.85,2.1\n"
            b"3500,not-a-number,0.86,2.0\n"
        )
        r = _post_csv(client, csv)
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "row 3" in detail.lower() or "row=3" in detail.lower()

    def test_phase_out_of_wrap_bounds_rejected_by_default(self, client):
        """Default behavior: ±180° wrap-bound enforced (catches unit / unwrap mistakes)."""
        csv = (
            b"frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
            b"3400,200.0,0.85,2.1\n"  # 200° beyond [-180, 180]
        )
        r = _post_csv(client, csv)
        assert r.status_code == 400
        assert "outside" in r.json()["detail"].lower()
        assert "allow_unwrapped_phase" in r.json()["detail"]

    def test_phase_out_of_wrap_bounds_accepted_with_unwrap_flag(self, client):
        """Operator opt-in to unwrapped data via allow_unwrapped_phase=true."""
        csv = (
            b"frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
            b"3400,200.0,0.85,2.1\n"
            b"3500,210.0,0.85,2.1\n"
        )
        r = _post_csv(client, csv, allow_unwrapped_phase="true")
        assert r.status_code == 201, r.text

    def test_negative_group_delay_rejected(self, client):
        csv = (
            b"frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
            b"3400,-12.5,-0.5,2.1\n"  # negative group delay is unphysical
        )
        r = _post_csv(client, csv)
        assert r.status_code == 400
        assert "group_delay_ns" in r.json()["detail"]

    @pytest.mark.parametrize(
        "bad_token,column",
        [
            ("NaN", "frequency_mhz"),
            ("NaN", "phase_offset_deg"),
            ("NaN", "group_delay_ns"),
            ("NaN", "phase_uncertainty_deg"),
            ("Inf", "frequency_mhz"),
            ("Inf", "group_delay_ns"),
            ("Inf", "phase_uncertainty_deg"),
            ("-Inf", "phase_offset_deg"),
        ],
    )
    def test_non_finite_value_rejected(self, client, bad_token, column):
        """Codex P2 on PR #57: float() accepts NaN/Inf tokens, and the
        physical-bound checks (`<=`, `<`) silently return False against NaN.
        Without an explicit `math.isfinite` guard, these would land in the
        JSONB array and corrupt downstream averaging/interpolation."""
        cols = ["frequency_mhz", "phase_offset_deg", "group_delay_ns",
                "phase_uncertainty_deg"]
        good_vals = {
            "frequency_mhz": "3400",
            "phase_offset_deg": "-12.5",
            "group_delay_ns": "0.85",
            "phase_uncertainty_deg": "2.1",
        }
        good_vals[column] = bad_token
        csv = (
            ",".join(cols).encode("utf-8") + b"\n"
            + ",".join(good_vals[c] for c in cols).encode("utf-8") + b"\n"
        )
        r = _post_csv(client, csv)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert "finite" in detail.lower() or "nan" in detail.lower() or "inf" in detail.lower()
        assert column in detail

    def test_non_monotonic_frequency_accepted_with_warning(self, client):
        """Non-monotonic frequency is a soft issue — accept + warn so operators
        with interleaved test plans aren't blocked; downstream consumers sort."""
        csv = (
            b"frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
            b"3500,-12.5,0.85,2.1\n"
            b"3400,-12.6,0.86,2.1\n"  # 3400 < 3500 — out of order
        )
        r = _post_csv(client, csv)
        assert r.status_code == 201, r.text
        warnings = r.json()["warnings"]
        assert any("monotonic" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# (3) Probe-identifier validation
# ---------------------------------------------------------------------------

class TestProbeIdentifierValidation:
    def test_probe_id_above_max_rejected(self, client):
        r = _post_csv(client, _valid_csv(), probe_id=PROBE_ID_MAX + 1)
        assert r.status_code == 400
        assert "probe_id" in r.json()["detail"]

    def test_reference_probe_equals_probe_id_rejected(self, client):
        """A probe can't be its own phase reference — would always measure 0."""
        r = _post_csv(client, _valid_csv(), probe_id=5, reference_probe_id=5)
        assert r.status_code == 400
        assert "reference" in r.json()["detail"].lower()

    def test_unknown_polarization_rejected(self, client):
        r = _post_csv(client, _valid_csv(), polarization="X")
        assert r.status_code == 400
        # Pydantic-side rejection by service (not FastAPI Form validator,
        # which would surface 422); we accept either since both are
        # actionable for the operator.
        assert (
            "polarization" in r.json()["detail"].lower()
            or "X" in r.json()["detail"]
        )


# ---------------------------------------------------------------------------
# (4) Replace-existing semantics
# ---------------------------------------------------------------------------

class TestReplaceExistingSemantics:
    def test_second_import_invalidates_prior_cert(self, client, db_session):
        first = _post_csv(client, _valid_csv())
        assert first.status_code == 201, first.text
        first_id = first.json()["calibration_id"]

        second = _post_csv(client, _valid_csv())
        assert second.status_code == 201, second.text
        second_body = second.json()
        assert second_body["invalidated_id"] == first_id
        assert second_body["calibration_id"] != first_id

        # DB sanity: 2 rows total, only one VALID
        db, _ = db_session
        rows = (
            db.query(ProbePhaseCalibration)
            .filter(ProbePhaseCalibration.probe_id == 5)
            .all()
        )
        assert len(rows) == 2
        valid_rows = [r for r in rows if r.status == CalibrationStatus.VALID.value]
        invalidated_rows = [
            r for r in rows if r.status == CalibrationStatus.INVALIDATED.value
        ]
        assert len(valid_rows) == 1
        assert len(invalidated_rows) == 1
        assert str(invalidated_rows[0].id) == first_id

    def test_replace_existing_false_keeps_both_valid(self, client, db_session):
        """Used only for cross-cert comparison — risky in production but supported."""
        _post_csv(client, _valid_csv())
        r = _post_csv(client, _valid_csv(), replace_existing="false")
        assert r.status_code == 201, r.text
        assert r.json()["invalidated_id"] is None

        db, _ = db_session
        valid_rows = (
            db.query(ProbePhaseCalibration)
            .filter(
                ProbePhaseCalibration.probe_id == 5,
                ProbePhaseCalibration.status == CalibrationStatus.VALID.value,
            )
            .all()
        )
        assert len(valid_rows) == 2

    def test_round_trip_get_after_import(self, client):
        """Confirm GET /phase/{probe_id} returns the newly imported cert."""
        csv = _valid_csv(num_rows=3)
        post = _post_csv(client, csv)
        assert post.status_code == 201, post.text
        new_id = post.json()["calibration_id"]

        # The mock get_phase_calibration filters by probe_id + (optional) polarization
        # and returns most recent — newly imported cert should be the one returned.
        get = client.get("/api/v1/calibration/probe/phase/5", params={"polarization": "V"})
        assert get.status_code == 200, get.text
        body = get.json()
        # Round-trip: same length + same first/last freq values
        assert len(body["frequency_points_mhz"]) == 3
        assert body["frequency_points_mhz"][0] == 3400.0
        assert body["frequency_points_mhz"][-1] == 3450.0
        # Newly created cert is what came back
        assert body.get("id") == new_id or str(body.get("id")) == new_id
