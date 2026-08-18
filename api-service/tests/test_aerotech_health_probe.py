"""aerotech_positioner_health diagnostic sequence — coverage tests.

Sibling of test_diagnostic_sequences.py:TestPropsimF64HealthSequence —
the F64 probe has its own test class because its scenarios are different
enough that pin-by-pin assertions don't generalise to a single helper.
Same here for Aerotech: AeroBasic three-state classification
(% / ! / #) differs from SCPI SYST:ERR? buckets, single-axis turntables
need their own assertions, and AXISFAULT-non-zero-but-comms-OK is a
chamber-specific blocker the F64 probe doesn't model.

What's covered
--------------
1. Loader registration + metadata shape (required_categories,
   safe_during_test, params_schema names).
2. Driver gating — refuses to run without a bound positioner driver,
   refuses on MockPositioner (mirrors P2 SCPI Console mock-gate),
   refuses when the driver lacks ``_send``, refuses when the driver
   exists but its TCP transport is not connected (``_writer=None``).
3. Single-axis happy path — Y commands skipped, summary mentions
   "single-axis turntable", 4 SUPPORTED reported.
4. Dual-axis happy path — all 8 commands SUPPORTED, summary mentions
   both axes' positions.
5. AeroBasic three-state classification:
   * NAK ``!`` (AerotechError) → UNSUPPORTED bucket
   * FAULT ``#`` prefix in returned data → SUPPORTED_BUT_FAULT bucket
   * timeout → UNKNOWN bucket
6. Phase-A fail-fast — 3 consecutive UNKNOWN responses abort the rest
   of Phase A and skip Phase B, with an actionable summary.
7. AXISFAULT non-zero → BLOCKER even when AeroBasic comms succeed.
8. AXISSTATUS hex decoding — operator sees
   ``0x90480005 (Enabled, InPosition)`` not raw signed int.
9. params_schema flags — ``functional_checks=False`` skips Phase B;
   ``include_supported=True`` emits SUPPORTED rows even for non-critical
   commands.

Fake driver factory
-------------------
We build a plain-Python instance with a dynamic class name (so probe's
``type(pos).__name__.startswith("Mock")`` check sees what we want)
plus the attributes ``RealAerotechDriver`` exposes (``az_axis``,
``el_axis``, ``ip_address``, ``port``, ``_axes_present``, ``_writer``,
``is_single_axis``) and an async ``_send`` that returns canned
responses for ``PFBK / VFBK / AXISSTATUS / AXISFAULT`` per axis.

We do NOT mock ``RealAerotechDriver`` itself — that would couple the
test to driver internals. The probe only reads via ``_send`` and a
small set of attributes, so a duck-typed instance suffices.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.diagnostics import loader
from app.hal.aerotech_positioner import AerotechCommandRejected, AerotechError
from app.main import app
from app.models.chamber import ChamberType, create_chamber_from_preset
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Aerotech Test Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab_with_positioner(db, chamber):
    """Lab profile bound to a positioner category so the Aerotech probe
    can resolve its required_categories=['positioner'] gate."""
    from app.models.instrument import InstrumentCategory

    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="positioner",
        category_name="DUT Turntable",
        is_active=True,
    )
    db.add(cat)
    db.commit()
    lp = LabProfile(
        name="Aerotech-Probe-Test-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(cat.id),
                "connection_endpoint": "192.168.0.16:8000",
                "driver_mode": "real",
                "role": "primary_positioner",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _patched_hal(monkeypatch, drivers: dict):
    """Replace get_hal_service() with a stub returning the given drivers dict.
    Mirrors test_diagnostic_sequences.py:_patched_hal."""
    fake_hal = MagicMock()
    fake_hal.drivers = drivers
    monkeypatch.setattr(
        "app.api.diagnostic_sequence.get_hal_service", lambda: fake_hal
    )
    return fake_hal


# ---------------------------------------------------------------------------
# Fake driver factory
# ---------------------------------------------------------------------------

# Healthy single-axis controller bitmask: Enabled + InPosition.
# Picked from real CAICT 2026-05-13 readout post-connect.
HEALTHY_AXISSTATUS = 0x90480005


def _build_pos(
    *,
    class_name: str = "RealAerotechDriver",
    connected: bool = True,
    has_send: bool = True,
    axes_present=("X",),
    pfbk=None,         # {axis: float}
    axisstatus=None,   # {axis: int}
    axisfault=None,    # {axis: int}
    vfbk=None,         # {axis: float}
    response_override=None,  # cmd -> exception | str | callable(cmd) -> str
):
    """Build a duck-typed positioner driver instance.

    ``class_name`` controls ``type(pos).__name__`` so the probe's
    Mock-driver gate can be tested by passing class_name='MockPositioner'.
    """
    pos_cls = type(class_name, (object,), {})
    pos = pos_cls()
    pos.az_axis = "X"
    pos.el_axis = "Y"
    pos.ip_address = "192.168.0.16"
    pos.port = 8000
    pos._axes_present = list(axes_present)
    pos._writer = object() if connected else None  # truthy sentinel
    pos.is_single_axis = ("X" in axes_present and "Y" not in axes_present)

    pfbk = pfbk if pfbk is not None else {"X": 0.0, "Y": 0.0}
    axisstatus = axisstatus if axisstatus is not None else {
        "X": HEALTHY_AXISSTATUS, "Y": HEALTHY_AXISSTATUS,
    }
    axisfault = axisfault if axisfault is not None else {"X": 0, "Y": 0}
    vfbk = vfbk if vfbk is not None else {"X": 0.0, "Y": 0.0}

    if has_send:
        async def fake_send(cmd):
            # Per-command override (raise / return arbitrary string / call lambda)
            if response_override and cmd in response_override:
                spec = response_override[cmd]
                if isinstance(spec, BaseException):
                    raise spec
                if callable(spec):
                    return spec(cmd)
                return spec
            # NAME(axis) shape parsing
            for prefix, mapping in (
                ("PFBK", pfbk),
                ("AXISSTATUS", axisstatus),
                ("AXISFAULT", axisfault),
                ("VFBK", vfbk),
            ):
                if cmd.startswith(f"{prefix}(") and cmd.endswith(")"):
                    axis = cmd[len(prefix) + 1:-1]
                    # Probe shouldn't ask about unconfigured axes when
                    # the driver advertises ``is_single_axis``, but if
                    # it did, the controller would NAK — simulate that.
                    if axis not in mapping:
                        raise AerotechError(f"AeroBasic error for '{cmd}': !")
                    return str(mapping[axis])
            return ""
        pos._send = fake_send

    pos.get_position = AsyncMock(return_value=(
        pfbk.get("X", 0.0),
        0.0 if pos.is_single_axis else pfbk.get("Y", 0.0),
    ))
    pos.get_metrics = AsyncMock(return_value=MagicMock(
        spec=["timestamp", "metrics"],
        metrics={"azimuth": pfbk.get("X", 0.0), "elevation": 0.0},
    ))
    pos.get_capabilities = AsyncMock(return_value=[
        MagicMock(name="2d_positioning" if pos.is_single_axis else "3d_positioning"),
    ])
    return pos


# ---------------------------------------------------------------------------
# Registration + metadata
# ---------------------------------------------------------------------------

class TestSequenceRegistration:
    def test_registered_in_loader(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "aerotech_positioner_health" in keys

    def test_metadata_requires_positioner(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        entry = next(
            s for s in resp.json() if s["key"] == "aerotech_positioner_health"
        )
        assert entry["required_categories"] == ["positioner"]
        assert entry["safe_during_test"] is False, (
            "Probe drains AXISSTATUS while a real test is moving the axis — "
            "must not be flagged safe_during_test"
        )
        param_names = {p["name"] for p in entry["params_schema"]}
        assert {"include_supported", "functional_checks"}.issubset(param_names)


# ---------------------------------------------------------------------------
# Driver gating
# ---------------------------------------------------------------------------

class TestDriverGating:
    def test_no_driver_loaded_summary_is_actionable(self, lab_with_positioner, monkeypatch):
        """HAL has no driver loaded for 'positioner' — probe reports an
        actionable summary (shared `driver_not_loaded_summary`), not a crash.
        Post-PR #85 the summary is the unified actionable text: names the
        category, points at the SCPI/connectivity probes, and tells the
        operator to reload HAL after connecting."""
        _patched_hal(monkeypatch, drivers={})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        summary = body["summary"]
        assert "positioner" in summary            # names the category
        assert "scpi-probe" in summary            # points at connectivity probe
        assert "hal/reload" in summary.lower()    # tells operator to reload HAL

    def test_mock_driver_refused(self, lab_with_positioner, monkeypatch):
        """MockPositioner would silently 'succeed' on every probe — probe
        must refuse it, telling operator to set a real driver."""
        mock_pos = _build_pos(class_name="MockPositioner")
        monkeypatch.setattr(
            "app.diagnostics.sequences.aerotech_positioner_health.is_mock_driver",
            lambda driver: driver is mock_pos,
        )
        _patched_hal(monkeypatch, drivers={"positioner": mock_pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "MockPositioner" in body["summary"]
        # Should mention how to fix it
        assert "real" in body["summary"].lower() or "RealAerotechDriver" in body["summary"]

    def test_driver_without_send_refused(self, lab_with_positioner, monkeypatch):
        pos = _build_pos(has_send=False)
        # Strip the _send attribute that fake factory set up
        if hasattr(pos, "_send"):
            del pos._send
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "_send" in body["summary"]

    def test_driver_not_connected_refused(self, lab_with_positioner, monkeypatch):
        """_writer=None means the TCP transport isn't up — probe should
        bail with an actionable message about Socket2 + firewall, not
        try to call _send (which would crash inside the real driver)."""
        pos = _build_pos(connected=False)
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "not connected" in body["summary"].lower()
        # Actionable next-step hints
        summary_lower = body["summary"].lower()
        assert "socket2" in summary_lower or "firewall" in summary_lower


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_single_axis_skips_y_4_supported(self, lab_with_positioner, monkeypatch):
        # Single-axis: only X registered; PFBK(Y) would NAK if asked but
        # probe shouldn't ask. We verify both: 4 SUPPORTED + summary
        # mentions "single-axis turntable".
        pos = _build_pos(axes_present=("X",))
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is True, body["summary"]
        assert "Aerotech health OK" in body["summary"]
        assert "single-axis turntable" in body["summary"]
        # 4 read-only commands × 1 axis = 4 probes (no UNSUPPORTED).
        counts = body["extra"]["counts"]
        assert counts["SUPPORTED"] == 4
        assert counts["UNSUPPORTED"] == 0
        assert counts["SUPPORTED_BUT_FAULT"] == 0
        assert counts["UNKNOWN"] == 0
        assert body["extra"]["single_axis"] is True
        assert body["extra"]["axes_present"] == ["X"]

    def test_dual_axis_8_supported(self, lab_with_positioner, monkeypatch):
        pos = _build_pos(axes_present=("X", "Y"))
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert "single-axis" not in body["summary"]
        counts = body["extra"]["counts"]
        assert counts["SUPPORTED"] == 8
        assert counts["UNSUPPORTED"] == 0
        assert body["extra"]["single_axis"] is False

    def test_discovered_dual_axis_requires_elevation_feedback(
        self, lab_with_positioner, monkeypatch,
    ):
        pos = _build_pos(
            axes_present=("X", "Y"),
            response_override={"PFBK(Y)": asyncio.TimeoutError()},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()

        assert body["success"] is False
        assert "PFBK_EL" in body["extra"]["critical_failures"]


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

class TestStatusClassification:
    def test_axisstatus_is_presented_only_as_raw_bitmask_without_guessed_labels(
        self, lab_with_positioner, monkeypatch
    ):
        pos = _build_pos(axes_present=("X",))
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={
                "lab_profile_id": str(lab_with_positioner.id),
                "params": {"include_supported": True},
            },
        )
        body = resp.json()
        axisstatus_step = next(
            step for step in body["steps"] if "AXISSTATUS" in step["label"]
        )
        assert "0x" in axisstatus_step["detail"]
        assert "Enabled" not in axisstatus_step["detail"]
        assert "InPosition" not in axisstatus_step["detail"]
        assert "MoveActive" not in axisstatus_step["detail"]

    def test_nak_categorized_as_unsupported(self, lab_with_positioner, monkeypatch):
        """A real Aerotech NAK comes back as AerotechError from _send.
        Probe should bucket as UNSUPPORTED, not crash."""
        pos = _build_pos(
            axes_present=("X",),
            # PFBK(X) NAKs; everything else fine
            response_override={
                "PFBK(X)": AerotechCommandRejected(
                    "AeroBasic error for 'PFBK(X)': !"
                ),
            },
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        counts = body["extra"]["counts"]
        # PFBK_AZ is critical, so this will mark probe as failed.
        assert body["success"] is False
        assert counts["UNSUPPORTED"] >= 1
        assert "PFBK_AZ" in body["extra"]["critical_failures"]

    def test_fault_prefix_categorized_as_supported_but_fault(self, lab_with_positioner, monkeypatch):
        """Driver's _send doesn't translate '#' prefix (only '!' raises),
        so probe receives the raw '#...' string and classifies it as
        SUPPORTED_BUT_FAULT (header recognised, controller in fault state)."""
        pos = _build_pos(
            axes_present=("X",),
            response_override={"PFBK(X)": "#fault-condition-1"},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        counts = body["extra"]["counts"]
        assert counts["SUPPORTED_BUT_FAULT"] >= 1

    @pytest.mark.parametrize("bad_value", ["", "NaN", "inf", "12 counts"])
    def test_feedback_requires_a_complete_finite_number(
        self, lab_with_positioner, monkeypatch, bad_value,
    ):
        pos = _build_pos(
            axes_present=("X",),
            response_override={"PFBK(X)": bad_value},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()

        assert body["success"] is False
        pfbk = next(step for step in body["steps"] if "PFBK(X)" in step["label"])
        assert "UNKNOWN" in pfbk["detail"]

    def test_any_controller_task_fault_blocks_overall_health(
        self, lab_with_positioner, monkeypatch,
    ):
        pos = _build_pos(
            axes_present=("X",),
            response_override={"AXISSTATUS(X)": "#task-fault"},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()

        assert body["extra"]["counts"]["SUPPORTED_BUT_FAULT"] == 1
        assert body["success"] is False

    def test_timeout_categorized_as_unknown(self, lab_with_positioner, monkeypatch):
        """asyncio.TimeoutError from _send → UNKNOWN bucket."""
        pos = _build_pos(
            axes_present=("X",),
            response_override={"PFBK(X)": asyncio.TimeoutError()},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        counts = body["extra"]["counts"]
        assert counts["UNKNOWN"] >= 1


# ---------------------------------------------------------------------------
# Fail-fast on stuck channel
# ---------------------------------------------------------------------------

class TestFailFastOnStuckChannel:
    def test_three_consecutive_unknown_aborts_phase_a(self, lab_with_positioner, monkeypatch):
        """If the TCP session is dead, every probe will time out. After 3
        consecutive UNKNOWN, abort to save the operator from waiting
        ~10s per remaining probe."""
        # All 4 single-axis commands time out → first 3 trigger abort.
        pos = _build_pos(
            axes_present=("X",),
            response_override={
                "PFBK(X)":       asyncio.TimeoutError(),
                "AXISSTATUS(X)": asyncio.TimeoutError(),
                "AXISFAULT(X)":  asyncio.TimeoutError(),
                "VFBK(X)":       asyncio.TimeoutError(),
            },
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["extra"]["phase_a_aborted"] is True
        # Summary tells operator next step
        assert "ABORTED" in body["summary"]
        assert "reload hal" in body["summary"].lower()


# ---------------------------------------------------------------------------
# Axis fault is a blocker even when comms work
# ---------------------------------------------------------------------------

class TestAxisFaultBlocker:
    def test_axis_fault_nonzero_makes_probe_fail(self, lab_with_positioner, monkeypatch):
        """AXISFAULT returns non-zero but all comms succeed — probe should
        still fail (so the operator doesn't green-flag a faulted axis
        and command MOVEABS)."""
        pos = _build_pos(
            axes_present=("X",),
            axisfault={"X": 0x0040},  # arbitrary non-zero fault
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "axis fault active" in body["summary"]
        assert body["extra"]["axis_in_fault"] is True
        assert body["extra"]["axis_fault_az"] == 0x0040

    def test_fractional_axis_fault_is_unknown_not_truncated_to_healthy(
        self, lab_with_positioner, monkeypatch,
    ):
        pos = _build_pos(
            axes_present=("X",),
            axisfault={"X": 0.5},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={"lab_profile_id": str(lab_with_positioner.id)},
        )
        body = resp.json()
        fault_step = next(
            step for step in body["steps"] if "AXISFAULT(X)" in step["label"]
        )
        assert body["success"] is False
        assert "UNKNOWN" in fault_step["detail"]
        assert body["extra"].get("axis_fault_az") is None


# ---------------------------------------------------------------------------
# AXISSTATUS hex decoding
# ---------------------------------------------------------------------------

class TestAxisStatusBitmaskDecode:
    def test_high_bit_status_renders_unsigned_without_unverified_flag_names(
        self, lab_with_positioner, monkeypatch,
    ):
        """0x90480005 has the sign bit set — Python int(float(x)) carries
        the sign, but probe must mask to 32-bit unsigned before hex
        formatting, but must not invent flag meanings absent from the
        checked-in vendor guide."""
        pos = _build_pos(
            axes_present=("X",),
            axisstatus={"X": 0x90480005},
        )
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={
                "lab_profile_id": str(lab_with_positioner.id),
                "params": {"include_supported": True},
            },
        )
        body = resp.json()
        axisstatus_step = next(
            s for s in body["steps"] if "AXISSTATUS" in s["label"]
        )
        # Bug guard: ``0x-6FB7FFFB`` was the pre-fix render — must NOT appear.
        assert "0x-" not in axisstatus_step["detail"]
        # Correct unsigned 32-bit form.
        assert "0x90480005" in axisstatus_step["detail"]
        assert "raw" in axisstatus_step["detail"]
        assert "Enabled" not in axisstatus_step["detail"]
        assert "InPosition" not in axisstatus_step["detail"]


# ---------------------------------------------------------------------------
# Params schema flags
# ---------------------------------------------------------------------------

class TestParamsSchemaFlags:
    def test_functional_checks_false_skips_phase_b(self, lab_with_positioner, monkeypatch):
        pos = _build_pos(axes_present=("X",))
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={
                "lab_profile_id": str(lab_with_positioner.id),
                "params": {"functional_checks": False},
            },
        )
        body = resp.json()
        labels = [s["label"] for s in body["steps"]]
        assert not any("get_position()" in lb for lb in labels)
        assert not any("get_metrics()" in lb for lb in labels)
        # Phase A still ran.
        assert any("PFBK_AZ" in lb for lb in labels)
        pos.get_position.assert_not_called()
        pos.get_metrics.assert_not_called()

    def test_include_supported_true_emits_all_supported_rows(
        self, lab_with_positioner, monkeypatch,
    ):
        """Default suppresses non-critical SUPPORTED rows; with the flag
        on, every probed command emits a step so the operator can see
        per-axis VFBK / etc passed too."""
        pos = _build_pos(axes_present=("X",))
        _patched_hal(monkeypatch, drivers={"positioner": pos})

        resp_default = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={
                "lab_profile_id": str(lab_with_positioner.id),
                "params": {"include_supported": False, "functional_checks": False},
            },
        )
        resp_all = client.post(
            "/api/v1/diagnostic-sequences/aerotech_positioner_health/run",
            json={
                "lab_profile_id": str(lab_with_positioner.id),
                "params": {"include_supported": True, "functional_checks": False},
            },
        )
        default_count = len(resp_default.json()["steps"])
        full_count = len(resp_all.json()["steps"])
        # VFBK_AZ is non-critical; default mode suppresses it, full mode emits.
        # Default emits only the 3 critical X rows (PFBK_AZ, AXISSTAT_AZ, AXISFAULT_AZ).
        assert default_count == 3
        assert full_count == 4  # adds VFBK_AZ
