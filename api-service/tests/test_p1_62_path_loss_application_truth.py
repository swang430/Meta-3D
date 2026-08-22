"""P1-62：路损证书的“是否应用”与“是否可信”必须分开表达。"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePathLossCalibration,
)
from app.services.path_loss_calibration_service import (
    ProbePathLossCalibrationService,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed(
    db,
    chamber_id,
    *,
    frequency_mhz: float = 3500.0,
    operating_mode: str | None = "mimo_ota",
    use_mock: bool | None = False,
    status: str = CalibrationStatus.VALID.value,
    expired: bool = False,
) -> ProbePathLossCalibration:
    now = datetime.utcnow()
    calibration = ProbePathLossCalibration(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        operating_mode=operating_mode,
        use_mock=use_mock,
        probe_path_losses={"1": {"path_loss_db": 56.77}},
        sgh_model="test-sgh",
        sgh_gain_dbi=8.0,
        avg_path_loss_db=56.77,
        calibrated_at=now - timedelta(hours=1),
        valid_until=now - timedelta(seconds=1) if expired else now + timedelta(days=1),
        status=status,
    )
    db.add(calibration)
    db.commit()
    db.refresh(calibration)
    return calibration


def _service(db) -> ProbePathLossCalibrationService:
    return ProbePathLossCalibrationService(db, use_mock=False)


@pytest.mark.parametrize(
    "seed_kwargs, expected_reason",
    [
        ({"expired": True}, "expired"),
        ({"frequency_mhz": 700.0}, "frequency_mismatch"),
        ({"operating_mode": "2x2"}, "operating_mode_mismatch"),
    ],
    ids=["expired", "frequency-mismatch", "operating-mode-mismatch"],
)
def test_selection_explains_why_no_certificate_was_selected(
    db, seed_kwargs, expected_reason,
):
    chamber_id = uuid4()
    _seed(db, chamber_id, **seed_kwargs)

    selection = _service(db).resolve_latest_calibration(
        chamber_id,
        frequency_mhz=3500.0,
        operating_mode="mimo_ota",
    )

    assert selection.certificate is None
    assert selection.reason == expected_reason


def test_selection_distinguishes_missing_from_selected(db):
    chamber_id = uuid4()

    missing = _service(db).resolve_latest_calibration(
        chamber_id,
        frequency_mhz=3500.0,
        operating_mode="mimo_ota",
    )
    assert missing.certificate is None
    assert missing.reason == "missing"

    certificate = _seed(db, chamber_id, use_mock=None)
    selected = _service(db).resolve_latest_calibration(
        chamber_id,
        frequency_mhz=3500.0,
        operating_mode="mimo_ota",
    )
    assert selected.certificate is certificate
    assert selected.reason == "selected"


def _application_module():
    return importlib.import_module("app.services.mimo_ota.path_loss_application")


def test_applied_legacy_certificate_is_not_described_as_uncompensated(db):
    certificate = _seed(db, uuid4(), use_mock=None)

    truth = _application_module().build_path_loss_application(
        selected_certificate=certificate,
        applied_certificate=certificate,
        selection_reason="selected",
        gate_mode="mock_not_applicable",
    )

    assert truth == {
        "schema_version": 1,
        "status": "applied",
        "provenance": "unknown",
        "reason": "selected",
        "gate_mode": "mock_not_applicable",
        "certificate_id": str(certificate.id),
        "value_disclosure": "hidden_unverified",
    }
    message = _application_module().path_loss_application_message(truth)
    assert "已应用路损补偿" in message
    assert "来源未知" in message
    assert "未补偿" not in message
    assert "56.77" not in message


@pytest.mark.parametrize(
    "use_mock, expected_provenance, expected_disclosure",
    [
        (False, "real", "verified"),
        (True, "simulated", "hidden_unverified"),
    ],
)
def test_applied_certificate_disclosure_follows_explicit_provenance(
    db, use_mock, expected_provenance, expected_disclosure,
):
    certificate = _seed(db, uuid4(), use_mock=use_mock)

    truth = _application_module().build_path_loss_application(
        selected_certificate=certificate,
        applied_certificate=certificate,
        selection_reason="selected",
        gate_mode="mock_not_applicable",
    )

    assert truth["status"] == "applied"
    assert truth["provenance"] == expected_provenance
    assert truth["value_disclosure"] == expected_disclosure


@pytest.mark.parametrize(
    "selection_reason",
    ["missing", "expired", "frequency_mismatch", "operating_mode_mismatch"],
)
def test_not_applied_missing_candidates_keep_the_exact_selection_reason(
    selection_reason,
):
    truth = _application_module().build_path_loss_application(
        selected_certificate=None,
        applied_certificate=None,
        selection_reason=selection_reason,
        gate_mode="operator_bypass",
    )

    assert truth["status"] == "not_applied"
    assert truth["provenance"] == "missing"
    assert truth["reason"] == selection_reason
    assert truth["certificate_id"] is None
    assert truth["value_disclosure"] == "none"


def test_untrusted_selected_certificate_can_be_rejected_without_losing_identity(db):
    certificate = _seed(db, uuid4(), use_mock=None)

    truth = _application_module().build_path_loss_application(
        selected_certificate=certificate,
        applied_certificate=None,
        selection_reason="selected",
        gate_mode="operator_bypass",
    )

    assert truth["status"] == "not_applied"
    assert truth["provenance"] == "unknown"
    assert truth["reason"] == "rejected_untrusted"
    assert truth["certificate_id"] == str(certificate.id)
    assert truth["value_disclosure"] == "none"


@pytest.mark.parametrize(
    "stored_value",
    [
        None,
        {},
        {"schema_version": 1, "status": "applied", "provenance": "invented"},
        {"schema_version": 1, "status": "applied", "provenance": "real"},
        {
            "schema_version": True,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "legacy-certificate",
            "value_disclosure": "verified",
        },
    ],
)
def test_missing_or_malformed_history_never_guesses_application_state(stored_value):
    parsed = _application_module().parse_path_loss_application(stored_value)

    assert parsed == {
        "schema_version": 1,
        "status": "unknown",
        "provenance": "unknown",
        "reason": "legacy_unclassified",
        "gate_mode": "strict",
        "certificate_id": None,
        "value_disclosure": "none",
    }
