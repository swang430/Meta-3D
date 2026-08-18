"""P2-28: diagnostic sequence raw evidence survives beyond the live response."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.main import app as _app  # noqa: F401  # import every mapped model
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun
from app.services.diagnostic_context import DiagnosticContext


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _empty_context() -> DiagnosticContext:
    return DiagnosticContext(
        lab_profile_id=None,
        lab_profile_name=None,
        chamber_id=None,
        chamber_name=None,
    )


def test_sequence_evidence_is_persisted_without_truncating_structured_raw():
    db = _session()
    evidence = {
        "schema_version": 1,
        "summary": "full evidence",
        "duration_ms": 42,
        "log": ["line one", "line two"],
        "steps": [
            {
                "label": "quoted reply",
                "success": True,
                "detail": "kept separately",
                "duration_ms": 7,
                "raw": '  "READY"\nsecond line  ',
            },
            {
                "label": "empty reply",
                "success": False,
                "detail": "empty is observed evidence",
                "duration_ms": None,
                "raw": "",
            },
        ],
        "extra": {"nested": {"values": [1, None, "x"]}},
    }
    try:
        run = _empty_context().record_run(
            db,
            kind=DiagnosticKind.SCPI_SEQUENCE,
            target_name="raw_stub",
            success=False,
            output="A" * 5000,
            sequence_evidence=evidence,
        )

        persisted = db.query(DiagnosticRun).filter(DiagnosticRun.id == run.id).one()
        assert persisted.sequence_evidence == evidence
        assert persisted.sequence_evidence["steps"][1]["raw"] == ""
        assert "truncated" in (persisted.output_excerpt or "")
    finally:
        db.close()


def test_non_sequence_audits_do_not_invent_sequence_evidence():
    db = _session()
    try:
        run = _empty_context().record_run(
            db,
            kind=DiagnosticKind.SCPI_COMMAND,
            target_name="*IDN?",
            success=True,
            output="vendor,model,serial",
        )

        persisted = db.query(DiagnosticRun).filter(DiagnosticRun.id == run.id).one()
        assert persisted.sequence_evidence is None
    finally:
        db.close()
