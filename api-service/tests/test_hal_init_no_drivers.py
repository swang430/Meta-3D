"""Regression: HAL `_initialize_from_db` must complete when zero
drivers connect successfully.

Bug surfaced by operator switching HAL mock → real with four bindings
whose hardware was unreachable (ENA timeout, RF switch refused,
SMW200A timeout, VSG timeout). HAL init crashed with::

    Failed to initialize HAL service: cannot access local variable
    'datetime' where it is not associated with a value

Root cause: ``_initialize_from_db`` had a function-local
``from datetime import datetime`` inside the per-driver success
branch. Python static scoping made ``datetime`` a LOCAL name
throughout the whole function, shadowing the module-level import
at line 14. When zero drivers reached the success branch, the
later ``datetime.utcnow()`` in the readiness-report builder hit
an unassigned local.

This test pins that ``_initialize_from_db`` completes (drivers=0,
readiness report built) even when every binding fails — the same
operator scenario, reduced to a unit test by using a DB with
``selected_model_id=None`` so the loop iterates but takes the
"no model selected, skipping" continue branch (success branch
never entered).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import InstrumentCategory as InstrumentCategoryModel
from app.services.instrument_hal_service import DriverMode, InstrumentHALService


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    Base.metadata.create_all(bind=engine)
    # ``_initialize_from_db`` does ``from app.db.database import SessionLocal``
    # inside the function, so monkeypatch the module attribute itself.
    import app.db.database as dbmod
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _add_unconnectable_category(db, key: str, display_order: int = 1):
    """Insert an active category with no selected_model_id — the loop
    iterates one row but takes the ``no model selected, skipping``
    continue branch (the success branch that assigns the local
    ``datetime`` is never entered)."""
    cat = InstrumentCategoryModel(
        id=uuid.uuid4(),
        category_key=key,
        category_name=key.title(),
        is_active=True,
        display_order=display_order,
        selected_model_id=None,
        driver_mode="real",
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def test_initialize_from_db_completes_when_zero_drivers_connect(db):
    """Reproduces the operator-reported bug. Pre-fix: this raises
    UnboundLocalError on ``datetime`` inside the readiness-report
    builder. Post-fix: completes cleanly with drivers={} and a
    readiness snapshot covering the zero-driver state."""
    # Four bindings, all unconnectable (no model selected) — mirrors
    # the operator's screenshot (rfSwitch / signalAnalyzer / VSG / VNA
    # all timing out / refused).
    _add_unconnectable_category(db, "rfSwitch", 1)
    _add_unconnectable_category(db, "signalAnalyzer", 2)
    _add_unconnectable_category(db, "vectorSignalGenerator", 3)
    _add_unconnectable_category(db, "vna", 4)

    svc = InstrumentHALService(mode=DriverMode.REAL)
    asyncio.run(svc._initialize_from_db())

    assert svc.drivers == {}
    # Readiness snapshot must have been built — generated_at_iso is the
    # field whose ``datetime.utcnow()`` call crashed pre-fix.
    assert svc.last_readiness_report is not None
    assert svc.last_readiness_report.generated_at_iso is not None
    # All four bindings reported as ``skipped`` (no model selected).
    assert len(svc.last_readiness_report.drivers) == 4
    assert all(r.status == "skipped" for r in svc.last_readiness_report.drivers)


def test_initialize_from_db_completes_when_no_categories(db):
    """Even more degenerate: empty DB. Loop iterates zero times,
    falls straight through to the readiness-report builder — also
    hits the ``datetime.utcnow()`` path. Pre-fix: same crash."""
    svc = InstrumentHALService(mode=DriverMode.REAL)
    asyncio.run(svc._initialize_from_db())

    assert svc.drivers == {}
    assert svc.last_readiness_report is not None
    assert svc.last_readiness_report.generated_at_iso is not None
    assert svc.last_readiness_report.drivers == []
