"""P3 Phase 2: sequence loader + run endpoint.

The two example sequences (instrument_idn_sweep, baseStation_attach_check)
exercise both branches: parameter-less + parameterised, no required
categories + required categories. We mock the HAL drivers since these
tests run against in-memory SQLite without real instruments.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.diagnostics import loader
from app.main import app
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.diagnostic_run import DiagnosticRun
from app.models.lab_profile import LabProfile


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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Phase 2 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab_with_bs(db, chamber):
    """Lab with a baseStation binding so attach_check sequence can run."""
    from app.models.instrument import InstrumentCategory

    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="baseStation",
        category_name="Base Station",
        is_active=True,
    )
    db.add(cat)
    db.commit()
    lp = LabProfile(
        name="P3-Phase2-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(cat.id),
                "connection_endpoint": "192.168.1.5:5025",
                "driver_mode": "real",
                "role": "primary_base_station",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _patched_hal(monkeypatch, drivers: dict):
    """Replace get_hal_service() with a stub returning the given drivers dict."""
    fake_hal = MagicMock()
    fake_hal.drivers = drivers
    monkeypatch.setattr(
        "app.api.diagnostic_sequence.get_hal_service", lambda: fake_hal
    )
    return fake_hal


class TestListSequences:
    def test_lists_both_examples(self):
        # Reset cache so that any earlier test that didn't import the
        # sequences package doesn't leave a stale entry.
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "instrument_idn_sweep" in keys
        assert "baseStation_attach_check" in keys

    def test_metadata_shape_includes_required_categories(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        body = resp.json()
        attach = next(s for s in body if s["key"] == "baseStation_attach_check")
        assert attach["required_categories"] == ["baseStation"]
        assert any(p["name"] == "frequency_mhz" for p in attach["params_schema"])
        assert attach["safe_during_test"] is False


class TestRunSequence:
    def test_404_on_unknown_sequence(self):
        resp = client.post("/api/v1/diagnostic-sequences/no_such/run", json={})
        assert resp.status_code == 404

    def test_422_when_required_category_not_bound(self, db, chamber):
        """Lab has no baseStation binding — 422 with the offending category."""
        # Empty bindings to trigger the missing-category guard.
        lp = LabProfile(
            name="empty-lab",
            chamber_config_id=chamber.id,
            instrument_bindings=[],
            is_active=True,
        )
        db.add(lp)
        db.commit()

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lp.id)},
        )
        assert resp.status_code == 422
        assert "baseStation" in resp.json()["detail"]

    def test_idn_sweep_records_audit_row_when_no_drivers(self, db, lab_with_bs, monkeypatch):
        """No HAL drivers loaded → sequence runs, marks failure, audit row exists."""
        _patched_hal(monkeypatch, drivers={})
        resp = client.post(
            "/api/v1/diagnostic-sequences/instrument_idn_sweep/run",
            json={"lab_profile_id": str(lab_with_bs.id), "run_by": "pytest"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        # One step (the lab has one binding), and it should report driver missing.
        assert len(body["steps"]) == 1
        assert "No HAL driver" in body["steps"][0]["detail"]
        # Audit row written
        audit = db.query(DiagnosticRun).filter(
            DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"])
        ).first()
        assert audit is not None
        assert audit.success is False
        assert audit.run_by == "pytest"
        assert "driver not loaded" in (audit.output_excerpt or "")

    def test_idn_sweep_succeeds_with_mock_driver(self, db, lab_with_bs, monkeypatch):
        bs_driver = MagicMock()
        bs_driver.get_identity = AsyncMock(return_value="VENDOR,MODEL,SN12345")
        _patched_hal(monkeypatch, drivers={"baseStation": bs_driver})

        resp = client.post(
            "/api/v1/diagnostic-sequences/instrument_idn_sweep/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["steps"]) == 1
        assert "VENDOR" in body["steps"][0]["detail"]

    def test_attach_check_sequence_runs_with_mock_bs(self, db, lab_with_bs, monkeypatch):
        """The sequence does mutate state — verify it walks through cleanly when
        the fake driver returns a happy path."""
        bs = MagicMock()
        bs.connect = AsyncMock(return_value=True)
        bs.set_cell_config = AsyncMock(return_value=True)
        bs.start_signaling = AsyncMock(return_value=True)
        bs.get_ue_info = AsyncMock(return_value={"connected": True, "imsi": "001010..."})
        bs.query_ue_capability = AsyncMock(return_value={"max_layers": 4})
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 2, "frequency_mhz": 3500},
            },
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        labels = [s["label"] for s in body["steps"]]
        assert "connect" in labels
        assert any("set_cell_config" in label for label in labels)
        assert "start_signaling" in labels
        assert body["extra"]["ue_info"]["connected"] is True

    def test_attach_check_marks_failure_on_no_attach(self, db, lab_with_bs, monkeypatch):
        """DUT never attaches within timeout → success=False, but HTTP 200."""
        bs = MagicMock()
        bs.connect = AsyncMock(return_value=True)
        bs.set_cell_config = AsyncMock(return_value=True)
        bs.start_signaling = AsyncMock(return_value=True)
        bs.get_ue_info = AsyncMock(return_value={"connected": False})
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 1},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "did not attach" in body["summary"]
        # Audit row written with success=False
        audit = db.query(DiagnosticRun).filter(
            DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"])
        ).first()
        assert audit.success is False


class TestUxmScpiCompatibilitySequence:
    """Probe sequence that walks every UxmScpiCommands constant and reports
    which are supported by the connected firmware.

    The sequence calls bs._query() for each command + once more for
    SYSTem:ERRor?. We mock _query with a programmable side_effect so each
    test can simulate a specific firmware-error-queue scenario.
    """

    def test_registered_in_loader(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "uxm_scpi_compatibility" in keys

    def test_metadata_requires_base_station(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        entry = next(s for s in resp.json() if s["key"] == "uxm_scpi_compatibility")
        assert entry["required_categories"] == ["baseStation"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "include_supported" for p in entry["params_schema"])

    def _build_bs(self, err_for_cmd):
        """Build a fake baseStation driver whose _query returns canned errs.

        err_for_cmd: callable(last_probed_cmd_str) -> error_queue_response.
        """
        bs = MagicMock()
        bs._write = MagicMock(return_value=None)
        state = {"last_probe": None}

        def fake_query(cmd):
            if cmd == "SYSTem:ERRor?":
                last = state["last_probe"]
                return err_for_cmd(last) if last else '0,"No error"'
            state["last_probe"] = cmd
            return ""

        bs._query = fake_query
        return bs

    def test_all_supported_when_firmware_responds_clean(self, lab_with_bs, monkeypatch):
        bs = self._build_bs(lambda cmd: '0,"No error"')
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id), "params": {"include_supported": False}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "critical" in body["summary"]
        # With include_supported=False and zero unsupported, steps stay empty.
        assert body["steps"] == []
        assert body["extra"]["counts"]["UNSUPPORTED"] == 0

    def test_critical_unsupported_fails_with_blocker(self, lab_with_bs, monkeypatch):
        broken = "CONFig:NR5G:CELL0:BAND?"  # _to_probe_command(CELL_BAND)

        def err_for(probe_cmd):
            if probe_cmd == broken:
                return '-113,"Undefined header"'
            return '0,"No error"'

        bs = self._build_bs(err_for)
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "BLOCKER" in body["summary"]
        assert "CELL_BAND" in body["summary"]
        cell_band_steps = [s for s in body["steps"] if s["label"].startswith("CELL_BAND ")]
        assert len(cell_band_steps) == 1
        assert cell_band_steps[0]["success"] is False
        assert "UNSUPPORTED" in cell_band_steps[0]["detail"]
        assert body["extra"]["critical_unsupported"] == ["CELL_BAND"]

    def test_state_error_categorized_as_ok(self, lab_with_bs, monkeypatch):
        """-200..-299 = header exists, wrong state — not a blocker."""
        bs = self._build_bs(lambda cmd: '-220,"Parameter error;current state"')
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["extra"]["counts"]["SUPPORTED_BUT_STATE"] > 0
        assert body["extra"]["counts"]["UNSUPPORTED"] == 0

    def test_fails_clean_when_no_driver_loaded(self, lab_with_bs, monkeypatch):
        """HAL has the binding but the driver class failed to init."""
        _patched_hal(monkeypatch, drivers={})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "baseStation driver" in body["summary"]
