"""P3-5 — composite HAL readiness snapshot.

Pins three layers:

1. ``app/services/readiness.py``: pure DB-only aggregation —
   ``build_lab_profile_readiness`` / ``build_calibration_readiness`` /
   ``build_dut_attach_readiness``. No HAL coupling, so tests synthesise
   ``LabProfile`` + ``CalibrationCertificate`` rows directly and exercise
   the status branches.
2. The dataclass shapes — ``DriverReadinessRow.extras``,
   ``DutAttachReadiness`` defaults — so a future driver-class refactor
   can't silently drop the forward-compat fields.
3. ``GET /api/v1/instruments/hal/readiness``: response shape under
   "HAL not initialised" (``available=false`` placeholder) and "HAL
   has a snapshot" (full payload from ``hal.last_readiness_report``).

Driver-level wiring (F64 ``readiness_metadata`` populating ``extras``)
is covered by hitting ``RealPropsimF64Driver.readiness_metadata`` against
a constructed instance — no live VISA needed because the method just
reads instance attrs P3-4 already populated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.calibration import CalibrationCertificate
from app.models.instrument import InstrumentCategory  # noqa: F401 — registers table
from app.models.lab_profile import LabProfile
from app.services.readiness import (
    CalibrationReadiness,
    DriverReadinessRow,
    DutAttachReadiness,
    LabProfileReadiness,
    ReadinessReport,
    build_calibration_readiness,
    build_dut_attach_readiness,
    build_lab_profile_readiness,
)


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
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


# Pinned "now" so expiry deltas are deterministic across runs — every
# certificate fixture is anchored relative to this value.
NOW = datetime(2026, 5, 17, 12, 0, 0)


def _make_cert(
    db,
    *,
    number: str = "CAL-2026-001",
    valid_until: datetime,
    overall_pass: bool = True,
) -> CalibrationCertificate:
    cert = CalibrationCertificate(
        id=uuid.uuid4(),
        certificate_number=number,
        calibration_date=valid_until - timedelta(days=30),
        valid_until=valid_until,
        overall_pass=overall_pass,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def _make_lab(
    db,
    *,
    name: str = "CAICT-Lab-1",
    is_active: bool = True,
    cert: CalibrationCertificate | None = None,
) -> LabProfile:
    lab = LabProfile(
        id=uuid.uuid4(),
        name=name,
        is_active=is_active,
        active_calibration_certificate_id=cert.id if cert else None,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


class TestLabProfileReadiness:
    """Pin the four status branches: missing / inactive / ok / ambiguous.

    These are the "what stage of operator onboarding are we at?" signals.
    GUI HAL panel will render them as a colored chip so each branch
    needs a stable `status` token."""

    def test_missing_when_no_lab_profiles_at_all(self, db):
        section = build_lab_profile_readiness(db)
        assert section.status == "missing"
        assert section.profile_id is None
        assert section.profile_name is None
        assert section.is_active is False
        # Detail nudges operator toward P0-2 init wizard explicitly so
        # the on-call doesn't have to know to associate "empty lab" with
        # the wizard.
        assert "wizard" in section.detail.lower()

    def test_inactive_when_all_profiles_disabled(self, db):
        _make_lab(db, name="Disabled-Lab-A", is_active=False)
        _make_lab(db, name="Disabled-Lab-B", is_active=False)
        section = build_lab_profile_readiness(db)
        assert section.status == "inactive"
        assert section.is_active is False
        # Detail must mention the profile count so operator knows there
        # ARE profiles, they're just turned off (different remediation
        # vs the missing case).
        assert "2 profile" in section.detail

    def test_ok_when_exactly_one_active(self, db):
        _make_lab(db, name="CAICT-Lab-1", is_active=True)
        section = build_lab_profile_readiness(db)
        assert section.status == "ok"
        assert section.profile_name == "CAICT-Lab-1"
        assert section.is_active is True
        assert section.profile_id is not None

    def test_inactive_profile_present_ok_one_active(self, db):
        # Mix: one active + one inactive → still ok (the active one wins).
        _make_lab(db, name="Inactive-Lab", is_active=False)
        _make_lab(db, name="Active-Lab", is_active=True)
        section = build_lab_profile_readiness(db)
        assert section.status == "ok"
        assert section.profile_name == "Active-Lab"

    def test_ambiguous_when_multiple_active(self, db):
        # Schema allows this (no uniqueness on is_active), but runtime
        # expects one. Flag the ambiguity; pick first deterministically
        # (sorted by name) so repeated readiness calls return the same
        # row rather than racing.
        _make_lab(db, name="Lab-B-second-alpha", is_active=True)
        _make_lab(db, name="Lab-A-first-alpha", is_active=True)
        section = build_lab_profile_readiness(db)
        assert section.status == "ambiguous"
        # Deterministic pick = alphabetically first.
        assert section.profile_name == "Lab-A-first-alpha"
        # Detail enumerates both so the operator can identify which
        # extras to disable.
        assert "Lab-A-first-alpha" in section.detail
        assert "Lab-B-second-alpha" in section.detail

    def test_explicit_active_profile_wins_when_multiple_are_active(self, db):
        _make_lab(db, name="Lab-A", is_active=True)
        chosen = _make_lab(db, name="Lab-B", is_active=True)

        section = build_lab_profile_readiness(db, chosen.id)

        assert section.status == "ok"
        assert section.profile_id == str(chosen.id)
        assert section.profile_name == "Lab-B"
        assert section.is_active is True

    def test_explicit_inactive_profile_is_rejected_without_fallback(self, db):
        _make_lab(db, name="Active-Fallback", is_active=True)
        inactive = _make_lab(db, name="Inactive-Requested", is_active=False)

        with pytest.raises(ValueError, match="inactive"):
            build_lab_profile_readiness(db, inactive.id)

    def test_explicit_missing_profile_is_rejected_without_fallback(self, db):
        _make_lab(db, name="Active-Fallback", is_active=True)
        missing_id = uuid.uuid4()

        with pytest.raises(ValueError, match=str(missing_id)):
            build_lab_profile_readiness(db, missing_id)


class TestCalibrationReadiness:
    """Pin the four status branches: no_lab / missing / valid / expired.

    The "no_lab vs missing" distinction matters operationally: no_lab
    means "set up a lab first", missing means "run calibration". Same
    color chip would lose that difference."""

    def test_no_lab_returns_no_lab_status(self, db):
        # Synthesise a missing-lab section by hand (since this is the
        # combination the caller would build first).
        lab_section = LabProfileReadiness(
            profile_id=None,
            profile_name=None,
            is_active=False,
            status="missing",
            detail="no LabProfile rows",
        )
        cal = build_calibration_readiness(db, lab_section, now=NOW)
        assert cal.status == "no_lab"
        assert cal.certificate_number is None
        assert cal.valid_until_iso is None
        assert cal.days_remaining is None

    def test_missing_when_lab_active_but_no_cert_bound(self, db):
        lab = _make_lab(db, cert=None)
        lab_section = build_lab_profile_readiness(db)
        cal = build_calibration_readiness(db, lab_section, now=NOW)
        assert cal.status == "missing"
        assert cal.certificate_number is None
        # Detail tells operator which lab + nudge toward P0-3.
        assert lab.name in cal.detail
        assert "P0-3" in cal.detail or "calibration" in cal.detail.lower()

    def test_valid_when_cert_within_validity_window(self, db):
        cert = _make_cert(db, valid_until=NOW + timedelta(days=15))
        _make_lab(db, cert=cert)
        lab_section = build_lab_profile_readiness(db)
        cal = build_calibration_readiness(db, lab_section, now=NOW)
        assert cal.status == "valid"
        assert cal.certificate_number == "CAL-2026-001"
        assert cal.days_remaining == 15
        assert cal.valid_until_iso is not None
        assert "15" in cal.detail

    def test_expired_when_cert_past_valid_until(self, db):
        cert = _make_cert(
            db,
            number="CAL-2025-001",
            valid_until=NOW - timedelta(days=12),
        )
        _make_lab(db, cert=cert)
        lab_section = build_lab_profile_readiness(db)
        cal = build_calibration_readiness(db, lab_section, now=NOW)
        assert cal.status == "expired"
        assert cal.certificate_number == "CAL-2025-001"
        # days_remaining is negative when expired — caller's UI can
        # `abs()` if it wants a "days ago" label.
        assert cal.days_remaining is not None and cal.days_remaining < 0
        assert "12" in cal.detail

    def test_inactive_lab_treated_as_no_lab(self, db):
        # If the only lab is inactive, calibration has nothing to bind
        # against — same operator next-step as "no lab at all".
        _make_lab(db, is_active=False)
        lab_section = build_lab_profile_readiness(db)
        assert lab_section.status == "inactive"
        cal = build_calibration_readiness(db, lab_section, now=NOW)
        assert cal.status == "no_lab"


class TestDutAttachReadiness:
    """Placeholder must always report not_implemented — no runtime
    sensing exists in this build (see module docstring in
    ``app/services/readiness.py``)."""

    def test_status_is_not_implemented(self):
        section = build_dut_attach_readiness()
        assert section.status == "not_implemented"

    def test_detail_explains_why(self):
        section = build_dut_attach_readiness()
        # Detail should explicitly acknowledge the deferred-implementation
        # so a reader of the JSON / log doesn't think it's a transient
        # "DUT detached" condition that'll resolve itself.
        assert "not implemented" in section.detail.lower()


class TestDriverReadinessRowExtras:
    """Pin the ``extras`` slot on per-driver rows — this is where F64
    (and future drivers) surface model-specific metadata without the
    readiness builder having to know about each driver class."""

    def test_default_extras_is_empty_dict(self):
        row = DriverReadinessRow(
            category="vna", model="E5071C ENA",
            endpoint="192.168.0.10:5025",
            status="ok", detail="RealKeysightEnaDriver",
        )
        assert row.extras == {}

    def test_extras_carries_arbitrary_keys(self):
        row = DriverReadinessRow(
            category="channelEmulator", model="PROPSIM F64",
            endpoint="192.168.0.100:5025",
            status="ok", detail="RealPropsimF64Driver",
            extras={
                "firmware_version": "v1.0",
                "band_label": "450MHz - 3000MHz",
                "product_family": "PROPSIM F64",
            },
        )
        assert row.extras["firmware_version"] == "v1.0"
        assert row.extras["band_label"] == "450MHz - 3000MHz"

    def test_f64_readiness_metadata_uses_parsed_sys_info(self):
        """End-to-end: a constructed F64 driver instance with sys_info
        populated returns the firmware/band/family triplet from
        ``readiness_metadata()`` — the hook the HAL service calls."""
        from app.hal.propsim_f64 import (
            F64SysInfo,
            RealPropsimF64Driver,
        )
        driver = RealPropsimF64Driver(
            instrument_id="test-f64",
            config={"ip": "10.0.0.1", "port": "5025"},
        )
        # Simulate what connect() does after parsing SYST:INFO?
        driver.sys_info = F64SysInfo(
            raw="PROPSIM F64,64,RF,v1.0,16",
            product_family="PROPSIM F64",
            channel_count=64,
            firmware_version="v1.0",
            band_label="450MHz - 3000MHz",
        )
        driver.firmware_version = "v1.0"
        driver.band_label = "450MHz - 3000MHz"
        driver.product_family = "PROPSIM F64"

        extras = driver.readiness_metadata()
        assert extras == {
            "firmware_version": "v1.0",
            "band_label": "450MHz - 3000MHz",
            "product_family": "PROPSIM F64",
        }

    def test_f64_readiness_metadata_empty_before_sys_info_parsed(self):
        """If connect() hasn't populated sys_info yet, extras must be
        an empty dict — partial keys would force the GUI into a
        per-key null check rather than the simpler "extras present
        or absent" pattern."""
        from app.hal.propsim_f64 import RealPropsimF64Driver
        driver = RealPropsimF64Driver(
            instrument_id="test-f64",
            config={"ip": "10.0.0.1", "port": "5025"},
        )
        # sys_info is None at __init__ time.
        assert driver.readiness_metadata() == {}

    def test_base_driver_returns_empty_extras_by_default(self):
        """Drivers that don't override the hook (FS16, Aerotech, etc.)
        return ``{}`` so the readiness builder doesn't have to special-
        case the absence."""
        from app.hal.propsim_fs16 import RealPropsimFs16Driver
        driver = RealPropsimFs16Driver(
            instrument_id="test-fs16",
            config={"ip": "10.0.0.1", "port": "5025"},
        )
        assert driver.readiness_metadata() == {}


class TestReadinessEndpoint:
    """``GET /api/v1/instruments/hal/readiness`` shape under both
    ``available=true`` (HAL has a snapshot) and ``available=false``
    (HAL not initialised yet) paths.

    These exercise the FastAPI Pydantic serialisation — the dataclass
    types from ``readiness.py`` have to round-trip through the
    response models without losing fields or breaking the openapi
    schema generated TypeScript depends on."""

    def test_endpoint_returns_unavailable_when_hal_not_initialized(self):
        """Fresh process / no HAL init → the endpoint returns a
        shaped placeholder, not a 404. GUI consumers can then render
        a single "HAL not ready" state without branching on field
        presence."""
        # get_hal_service returns whatever was last initialised in
        # this test session — null it out via mock so we exercise
        # the unavailable path deterministically.
        with patch("app.services.instrument_hal_service.get_hal_service", return_value=None):
            resp = client.get("/api/v1/instruments/hal/readiness")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["drivers"] == []
        # Sub-sections still shaped, with placeholder details that name
        # the "HAL not initialised" cause (rather than fake-OK).
        assert body["lab_profile"]["status"] == "missing"
        assert "not initialis" in body["lab_profile"]["detail"].lower()
        assert body["calibration"]["status"] == "no_lab"
        assert body["dut_attach"]["status"] == "not_implemented"
        assert body["generated_at_iso"]  # truthy ISO string

    def test_endpoint_serializes_full_snapshot_when_available(self, db):
        """HAL has been initialised and stored a snapshot → endpoint
        returns the full payload with all sub-sections."""
        cert = _make_cert(db, valid_until=NOW + timedelta(days=10))
        _make_lab(db, cert=cert)

        report = ReadinessReport(
            drivers=[
                DriverReadinessRow(
                    category="channelEmulator", model="PROPSIM F64",
                    endpoint="192.168.0.100:5025",
                    status="ok", detail="RealPropsimF64Driver",
                    extras={
                        "firmware_version": "v1.0",
                        "band_label": "450MHz - 3000MHz",
                        "product_family": "PROPSIM F64",
                    },
                ),
                DriverReadinessRow(
                    category="baseStation", model="(not configured)",
                    endpoint="", status="skipped",
                    detail="no model selected in GUI",
                ),
            ],
            lab_profile=build_lab_profile_readiness(db),
            calibration=build_calibration_readiness(
                db, build_lab_profile_readiness(db), now=NOW
            ),
            dut_attach=build_dut_attach_readiness(),
            generated_at_iso=NOW.isoformat(),
        )

        class StubHal:
            mode = type("M", (), {"value": "mock"})()
            drivers: Dict[str, Any] = {}
            last_readiness_report = report

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=StubHal(),
        ):
            resp = client.get("/api/v1/instruments/hal/readiness")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert len(body["drivers"]) == 2
        f64_row = body["drivers"][0]
        assert f64_row["category"] == "channelEmulator"
        assert f64_row["status"] == "ok"
        assert f64_row["extras"]["firmware_version"] == "v1.0"
        assert f64_row["extras"]["band_label"] == "450MHz - 3000MHz"
        # Skipped row carries empty extras (not null) so the GUI
        # mapping path is uniform.
        assert body["drivers"][1]["extras"] == {}
        # Lab + cal sections reflect the DB state.
        assert body["lab_profile"]["status"] == "ok"
        assert body["lab_profile"]["profile_name"] == "CAICT-Lab-1"
        assert body["calibration"]["status"] == "valid"
        assert body["calibration"]["days_remaining"] == 10
        assert body["dut_attach"]["status"] == "not_implemented"
        assert body["generated_at_iso"] == NOW.isoformat()
        # P1-11: subnets key is always present (empty list here since the
        # report was built without a subnets rollup — default_factory=[]).
        assert "subnets" in body
        assert body["subnets"] == []
        # P1-11: ok / skipped rows carry fail_kind=null (key present).
        assert f64_row.get("fail_kind") is None

    def test_endpoint_omits_optional_fields_with_nulls_not_missing_keys(self, db):
        """When LabProfile / cert are absent, the response keeps the
        field keys with ``null`` values rather than omitting them —
        important for the generated TS types where ``profile_id?: string
        | null`` distinguishes "not set" from "field missing"."""
        report = ReadinessReport(
            drivers=[],
            lab_profile=LabProfileReadiness(
                profile_id=None, profile_name=None, is_active=False,
                status="missing", detail="no LabProfile rows",
            ),
            calibration=CalibrationReadiness(
                certificate_number=None, valid_until_iso=None,
                status="no_lab", days_remaining=None,
                detail="no active lab",
            ),
            dut_attach=DutAttachReadiness(),
            generated_at_iso=NOW.isoformat(),
        )

        class StubHal:
            last_readiness_report = report

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=StubHal(),
        ):
            resp = client.get("/api/v1/instruments/hal/readiness")
        body = resp.json()
        # Keys present, values null — not field-absent.
        assert "profile_id" in body["lab_profile"]
        assert body["lab_profile"]["profile_id"] is None
        assert "certificate_number" in body["calibration"]
        assert body["calibration"]["certificate_number"] is None
        assert "days_remaining" in body["calibration"]
        assert body["calibration"]["days_remaining"] is None
