"""P1-11 — multi-subnet instrument reachability diagnostics.

CAICT's instruments sit on two /24 subnets (F64 on ``192.168.0.x``,
UXM + SA on ``192.168.1.x``) and the single-NIC control Mac can only be
on one subnet at a time. Before this work an unreachable subnet produced
one opaque VISA error (``-1073807339``) per instrument with no hint that
the *subnet* (not the instrument) was the problem.

This module pins the two halves of the software-side fix:

1. **fail_kind classification** — ``_initialize_from_db`` must tag a
   ``status=="fail"`` driver row with *why* it failed:
   - ``"network"`` when TCP preflight can't reach the host (wrong subnet)
   - ``"scpi"`` when TCP reached the host but ``driver.connect()`` failed
     (instrument/session problem, not routing)
   The existing ``test_hal_tcp_preflight.py`` covers ``tcp_preflight``
   in isolation but never the SCPI-vs-network *separation* in the
   readiness rows — that's the gap this file fills.

2. **/24 subnet aggregation** — ``build_subnet_reachability`` /
   ``parse_subnet_cidr``: group rows by subnet, mark a subnet
   unreachable iff it has a ``network``-fail row, and emit an actionable
   runbook hint for unreachable subnets only.

The aggregation half is pure (no DB / HAL), tested directly. The
classification half drives the real ``_initialize_from_db`` with a fake
real-driver class + monkeypatched ``tcp_preflight`` so the two fail
paths (preflight-fail / connect-fail) are exercised exactly as
production hits them.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import (
    InstrumentCategory as InstrumentCategoryModel,
    InstrumentConnection as InstrumentConnectionDB,
    InstrumentModel as InstrumentModelDB,
)
from app.services import instrument_hal_service as hal_mod
from app.services.instrument_hal_service import DriverMode, InstrumentHALService
from app.services.readiness import (
    DriverReadinessRow,
    build_subnet_reachability,
    parse_subnet_cidr,
)


# ──────────────────────────────────────────────────────────────────
# 1. parse_subnet_cidr — pull /24 out of both endpoint shapes
# ──────────────────────────────────────────────────────────────────
class TestParseSubnetCidr:
    def test_controller_ip_port_shape(self):
        assert parse_subnet_cidr("192.168.0.132:5025") == "192.168.0.0/24"

    def test_visa_resource_string_shape(self):
        assert (
            parse_subnet_cidr("TCPIP0::192.168.1.40::hislip0::INSTR")
            == "192.168.1.0/24"
        )

    def test_bare_ip(self):
        assert parse_subnet_cidr("10.0.5.7") == "10.0.5.0/24"

    def test_empty_returns_none(self):
        assert parse_subnet_cidr("") is None

    def test_hostname_only_returns_none(self):
        # No DNS resolution in the readiness path — a hostname-only
        # endpoint has no parseable IPv4 host, so it buckets as unknown.
        assert parse_subnet_cidr("TCPIP0::myinstrument.lab::inst0::INSTR") is None


# ──────────────────────────────────────────────────────────────────
# 2. build_subnet_reachability — /24 rollup
# ──────────────────────────────────────────────────────────────────
def _row(category, endpoint, status="ok", fail_kind=None):
    return DriverReadinessRow(
        category=category,
        model="X",
        endpoint=endpoint,
        status=status,
        detail="",
        fail_kind=fail_kind,
    )


class TestBuildSubnetReachability:
    def test_two_subnets_one_network_fail(self):
        """Core P1-11 case: two subnets, one has a network-fail driver.

        That subnet is reachable=False + non-empty hint; the other is
        reachable=True + hint=None. Mirrors CAICT (control PC on .0.x,
        so the whole .1.x subnet is unreachable)."""
        rows = [
            _row("channelEmulator", "192.168.0.132:5025", status="ok"),
            _row(
                "baseStation",
                "TCPIP0::192.168.1.40::hislip0::INSTR",
                status="fail",
                fail_kind="network",
            ),
        ]
        subnets = build_subnet_reachability(rows)
        by_cidr = {s.cidr: s for s in subnets}

        assert by_cidr["192.168.0.0/24"].reachable is True
        assert by_cidr["192.168.0.0/24"].hint is None
        assert by_cidr["192.168.0.0/24"].instrument_count == 1
        assert by_cidr["192.168.0.0/24"].unreachable_count == 0

        bad = by_cidr["192.168.1.0/24"]
        assert bad.reachable is False
        assert bad.unreachable_count == 1
        assert bad.hint is not None
        # Hint must point at the runbook + name the subnet so the
        # operator knows exactly what to fix.
        assert "192.168.1.0/24" in bad.hint
        assert "multi-subnet-instrument-network.md" in bad.hint

    def test_scpi_fail_does_not_make_subnet_unreachable(self):
        """A subnet with only an SCPI-fail row is still network-reachable
        — the problem is the instrument, not the route. This is the
        crux of the network/scpi distinction."""
        rows = [
            _row(
                "channelEmulator",
                "192.168.0.132:5025",
                status="fail",
                fail_kind="scpi",
            ),
        ]
        subnets = build_subnet_reachability(rows)
        assert len(subnets) == 1
        assert subnets[0].cidr == "192.168.0.0/24"
        assert subnets[0].reachable is True
        assert subnets[0].hint is None
        # The fail is still counted as an instrument on the subnet, but
        # not as an unreachable one.
        assert subnets[0].instrument_count == 1
        assert subnets[0].unreachable_count == 0

    def test_two_instruments_same_subnet_ok_and_skipped(self):
        """UXM (ok) + N9042B (skipped) on the same /24 → one reachable
        subnet, instrument_count=2. Matches the GUI mock fixture so the
        mock can't drift from what the backend computes."""
        rows = [
            _row("baseStation", "TCPIP0::192.168.1.40::hislip0::INSTR", status="ok"),
            _row(
                "signalAnalyzer",
                "TCPIP0::192.168.1.55::inst0::INSTR",
                status="skipped",
            ),
        ]
        subnets = build_subnet_reachability(rows)
        assert len(subnets) == 1
        assert subnets[0].cidr == "192.168.1.0/24"
        assert subnets[0].instrument_count == 2
        assert subnets[0].reachable is True

    def test_unparseable_endpoint_buckets_unknown_not_unreachable(self):
        """A row with no parseable IP goes to the 'unknown' bucket and
        is never claimed unreachable — we can't assert a routing problem
        we can't locate (honesty principle)."""
        rows = [_row("baseStation", "", status="fail", fail_kind="network")]
        subnets = build_subnet_reachability(rows)
        assert len(subnets) == 1
        assert subnets[0].cidr == "unknown"
        # network-fail in the unknown bucket does NOT flip reachable —
        # the bucket has no hint and is reported as-is.
        assert subnets[0].reachable is True
        assert subnets[0].hint is None

    def test_output_sorted_unknown_last(self):
        rows = [
            _row("a", "", status="ok"),  # unknown
            _row("b", "192.168.1.5:5025", status="ok"),
            _row("c", "192.168.0.5:5025", status="ok"),
        ]
        cidrs = [s.cidr for s in build_subnet_reachability(rows)]
        assert cidrs == ["192.168.0.0/24", "192.168.1.0/24", "unknown"]


# ──────────────────────────────────────────────────────────────────
# 3. fail_kind classification through _initialize_from_db
# ──────────────────────────────────────────────────────────────────
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


class _FakeRealDriver:
    """Minimal real-driver stand-in. NOT a MockChannelEmulator subclass,
    so the preflight branch in ``_initialize_from_db`` actually runs
    (preflight is skipped for mock drivers). ``connect()`` returns a
    configurable success flag so the connect-fail path is exercised."""

    connect_result = True

    def __init__(self, instrument_id, config):
        self.instrument_id = instrument_id
        self.config = config
        self._last_error = "fake connect() refused by stub"

    async def connect(self):
        return type(self).connect_result

    def readiness_metadata(self):
        return {}


def _seed_category_with_model(db, *, category_key, ip, port=5025, model_name="FAKE-1"):
    cat = InstrumentCategoryModel(
        id=uuid.uuid4(),
        category_key=category_key,
        category_name=category_key.title(),
        is_active=True,
        display_order=1,
        driver_mode="real",
    )
    db.add(cat)
    db.flush()
    model = InstrumentModelDB(
        id=uuid.uuid4(),
        category_id=cat.id,
        vendor="FakeVendor",
        model=model_name,
        full_name="Fake Instrument",
        capabilities={},
    )
    db.add(model)
    db.flush()
    cat.selected_model_id = model.id
    conn = InstrumentConnectionDB(
        id=uuid.uuid4(),
        category_id=cat.id,
        endpoint=f"TCPIP0::{ip}::inst0::INSTR",
        controller_ip=ip,
        port=port,
        protocol="vxi11",
    )
    db.add(conn)
    db.commit()
    return cat, model


def _run_init_with_fake_driver(monkeypatch, *, category_key, model_name):
    """Patch the real-driver registry so ``category_key`` resolves to
    ``_FakeRealDriver`` for ``model_name``, then run init."""
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {category_key: {model_name: _FakeRealDriver}},
    )
    svc = InstrumentHALService(mode=DriverMode.REAL)
    asyncio.run(svc._initialize_from_db())
    return svc


class TestFailKindClassification:
    def test_preflight_failure_tagged_network(self, monkeypatch, db):
        """TCP preflight returns (False, reason) → the driver row is
        status=fail, fail_kind='network'. connect() must NOT be called."""
        _seed_category_with_model(
            db, category_key="channelEmulator", ip="192.168.9.50", model_name="FAKE-1"
        )

        async def fake_preflight(host, port, timeout_s=1.0):
            return (False, f"SYN timeout to {host}:{port} after {timeout_s}s")

        monkeypatch.setattr(hal_mod, "tcp_preflight", fake_preflight)
        _FakeRealDriver.connect_result = True  # would succeed — must be skipped

        svc = _run_init_with_fake_driver(
            monkeypatch, category_key="channelEmulator", model_name="FAKE-1"
        )

        rows = svc.last_readiness_report.drivers
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "fail"
        assert row.fail_kind == "network"
        assert "preflight" in row.detail
        # No driver landed in the live set (connect was skipped).
        assert svc.drivers == {}

    def test_connect_failure_tagged_scpi(self, monkeypatch, db):
        """Preflight passes (host reachable) but connect() returns False
        → status=fail, fail_kind='scpi'. This is the path the existing
        preflight test never covered."""
        _seed_category_with_model(
            db, category_key="channelEmulator", ip="192.168.9.50", model_name="FAKE-1"
        )

        async def fake_preflight(host, port, timeout_s=1.0):
            return (True, None)

        monkeypatch.setattr(hal_mod, "tcp_preflight", fake_preflight)
        _FakeRealDriver.connect_result = False  # TCP up, session handshake fails

        svc = _run_init_with_fake_driver(
            monkeypatch, category_key="channelEmulator", model_name="FAKE-1"
        )

        rows = svc.last_readiness_report.drivers
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "fail"
        assert row.fail_kind == "scpi"
        # The subnet rollup must NOT mark this subnet unreachable —
        # the route is fine, the instrument isn't responding.
        subnets = {s.cidr: s for s in svc.last_readiness_report.subnets}
        assert subnets["192.168.9.0/24"].reachable is True
        assert subnets["192.168.9.0/24"].hint is None

    def test_subnet_rollup_present_in_report(self, monkeypatch, db):
        """End-to-end: a network-fail subnet shows up as unreachable in
        the report's subnet rollup with a runbook hint."""
        _seed_category_with_model(
            db, category_key="channelEmulator", ip="192.168.9.50", model_name="FAKE-1"
        )

        async def fake_preflight(host, port, timeout_s=1.0):
            return (False, "no route")

        monkeypatch.setattr(hal_mod, "tcp_preflight", fake_preflight)

        svc = _run_init_with_fake_driver(
            monkeypatch, category_key="channelEmulator", model_name="FAKE-1"
        )

        subnets = {s.cidr: s for s in svc.last_readiness_report.subnets}
        assert "192.168.9.0/24" in subnets
        bad = subnets["192.168.9.0/24"]
        assert bad.reachable is False
        assert bad.hint is not None
        assert "方案 A" in bad.hint

    @classmethod
    def teardown_class(cls):
        # Reset the class-level flag so cross-test ordering is clean.
        _FakeRealDriver.connect_result = True
