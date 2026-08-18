"""P3 Phase 1: diagnostic_context + diagnostic_runs audit table.

These tests verify the workshop-tier foundation:
- DiagnosticContext resolves LabProfile / chamber / instrument bindings.
- timed_run() records both success and failure paths.
- The audit list/detail endpoints filter and paginate correctly.
- Output excerpts are truncated on write so chatty SCPI doesn't blow rows.
"""
from __future__ import annotations

import time
import uuid

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
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun
from app.models.lab_profile import LabProfile
from app.services.diagnostic_context import (
    build_diagnostic_context,
    timed_run,
)


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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P3 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="P3-Workshop-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(uuid.uuid4()),
                "connection_endpoint": "192.168.1.10:5025",
                "driver_mode": "real",
                "role": "primary_channel_emulator",
            },
            {
                "category_id": str(uuid.uuid4()),
                "connection_endpoint": "192.168.1.20:5025",
                "driver_mode": "real",
                "role": "vna",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


class TestBuildContext:
    def test_resolves_lab_chamber_and_bindings(self, db, lab, chamber):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        assert ctx.lab_profile_id == lab.id
        assert ctx.lab_profile_name == "P3-Workshop-Lab"
        assert ctx.chamber_id == chamber.id
        assert ctx.chamber_name == chamber.name
        assert len(ctx.instrument_bindings) == 2

    def test_endpoint_lookup_by_role(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        assert ctx.endpoint_for("primary_channel_emulator") == "192.168.1.10:5025"
        assert ctx.endpoint_for("vna") == "192.168.1.20:5025"
        assert ctx.endpoint_for("nonexistent") is None

    def test_lab_profile_id_none_returns_empty_context(self, db):
        # SCPI Console's "fire at hardcoded IP" path doesn't pick a lab —
        # the helper should still hand back a usable context (no lookup,
        # but record_run / truncate_excerpt still work).
        ctx = build_diagnostic_context(db, lab_profile_id=None)
        assert ctx.lab_profile_id is None
        assert ctx.instrument_bindings == []
        assert ctx.endpoint_for("anything") is None

    def test_unknown_lab_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            build_diagnostic_context(db, lab_profile_id=uuid.uuid4())

    def test_warnings_when_chamber_missing(self, db):
        # Lab references a chamber that was deleted — context should still
        # build but the warning surfaces upstream so the GUI can flag it.
        orphan = LabProfile(
            name="Orphan",
            chamber_config_id=uuid.uuid4(),  # not in DB
            is_active=True,
        )
        db.add(orphan)
        db.commit()
        ctx = build_diagnostic_context(db, lab_profile_id=orphan.id)
        assert any("missing chamber" in w for w in ctx.warnings)


class TestTimedRunAudit:
    def test_success_path_records_row(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        with timed_run(
            db, ctx,
            kind=DiagnosticKind.SCPI_COMMAND,
            target_name="*IDN?",
            params={"category_key": "channelEmulator"},
            run_by="pytest",
        ) as bag:
            time.sleep(0.01)
            bag["output"] = "ROHDE&SCHWARZ,F64,12345"

        rows = db.query(DiagnosticRun).all()
        assert len(rows) == 1
        r = rows[0]
        assert r.kind == DiagnosticKind.SCPI_COMMAND.value
        assert r.success is True
        assert r.target_name == "*IDN?"
        assert r.lab_profile_id == lab.id
        assert r.duration_ms is not None and r.duration_ms >= 0
        assert "ROHDE" in r.output_excerpt

    def test_failure_path_records_and_reraises(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        with pytest.raises(RuntimeError):
            with timed_run(
                db, ctx,
                kind=DiagnosticKind.SCPI_COMMAND,
                target_name="BAD:CMD?",
                run_by="pytest",
            ) as bag:
                bag["output"] = "partial output"
                raise RuntimeError("instrument refused command")

        rows = db.query(DiagnosticRun).all()
        assert len(rows) == 1
        r = rows[0]
        assert r.success is False
        assert r.error_message == "instrument refused command"
        # Partial output captured before the raise should still be persisted —
        # debugging often hinges on "what came back before it died".
        assert r.output_excerpt == "partial output"

    def test_output_excerpt_truncated_at_2kb(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        big = "A" * 5000
        ctx.record_run(
            db,
            kind=DiagnosticKind.SCPI_SEQUENCE,
            target_name="big_dump",
            success=True,
            output=big,
        )
        r = db.query(DiagnosticRun).first()
        assert r is not None
        assert len(r.output_excerpt) < 2200
        assert r.output_excerpt.startswith("AAAA")
        assert "truncated" in r.output_excerpt


class TestDiagnosticRunListAPI:
    def test_lists_recent_runs_desc_by_default(self, db, lab):
        # Three runs with different kinds — list view should newest-first.
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        for i, kind in enumerate([
            DiagnosticKind.SCPI_COMMAND,
            DiagnosticKind.SCPI_SEQUENCE,
            DiagnosticKind.COMMISSIONING_FULL,
        ]):
            ctx.record_run(
                db,
                kind=kind,
                target_name=f"target-{i}",
                success=True,
                output=f"out-{i}",
            )

        resp = client.get("/api/v1/diagnostic-runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        # newest is the last appended (commissioning_full)
        assert body["items"][0]["kind"] == DiagnosticKind.COMMISSIONING_FULL.value

    def test_filter_by_kind(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        ctx.record_run(db, kind=DiagnosticKind.SCPI_COMMAND, target_name="a", success=True)
        ctx.record_run(db, kind=DiagnosticKind.SCPI_SEQUENCE, target_name="b", success=True)
        ctx.record_run(db, kind=DiagnosticKind.SCPI_SEQUENCE, target_name="c", success=False)

        resp = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": DiagnosticKind.SCPI_SEQUENCE.value},
        )
        body = resp.json()
        assert body["total"] == 2
        assert {it["target_name"] for it in body["items"]} == {"b", "c"}

    def test_filter_by_success_false(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        ctx.record_run(db, kind=DiagnosticKind.SCPI_COMMAND, target_name="ok", success=True)
        ctx.record_run(db, kind=DiagnosticKind.SCPI_COMMAND, target_name="bad", success=False)

        resp = client.get("/api/v1/diagnostic-runs", params={"success": False})
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["target_name"] == "bad"

    def test_unknown_kind_returns_422(self):
        resp = client.get("/api/v1/diagnostic-runs", params={"kind": "not_a_kind"})
        assert resp.status_code == 422

    def test_get_detail_includes_params_and_output(self, db, lab):
        ctx = build_diagnostic_context(db, lab_profile_id=lab.id)
        run = ctx.record_run(
            db,
            kind=DiagnosticKind.SCPI_COMMAND,
            target_name="*IDN?",
            success=True,
            params={"endpoint": "192.168.1.10:5025"},
            output="vendor,model,sn",
        )
        resp = client.get(f"/api/v1/diagnostic-runs/{run.id}")
        body = resp.json()
        assert body["params"]["endpoint"] == "192.168.1.10:5025"
        assert body["output_excerpt"] == "vendor,model,sn"
        assert body["sequence_evidence"] is None

    def test_get_detail_404_for_unknown_id(self):
        resp = client.get(f"/api/v1/diagnostic-runs/{uuid.uuid4()}")
        assert resp.status_code == 404
