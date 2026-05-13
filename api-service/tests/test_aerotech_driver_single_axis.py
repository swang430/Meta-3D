"""RealAerotechDriver — single-axis turntable support.

CAICT 2026-05-13 site reality: the chamber DUT positioner is a single-axis
Ensemble (azimuth-only) because chamber elevation comes from the probe array,
not the positioner. Driver was previously hard-coded to ENABLE both X and Y
in ``connect()`` — Y NAK on a single-axis box failed the entire connect.

These tests pin the read-only ``PFBK`` probe behaviour in ``connect()`` that
discovers which configured axes the controller actually has, and verify that
every per-axis method (move_to, get_position, _wait_for_settle, disconnect,
stop, reset) honours ``_axes_present`` instead of blindly addressing X + Y.

No real TCP — we hijack ``_send`` with a FakeController that records every
command and returns ACK / NAK based on a configurable axis set.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

import pytest

from app.hal.aerotech_positioner import (
    AerotechError,
    AxisStatusBit,
    RealAerotechDriver,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

class FakeController:
    """Records every AeroBasic command + emits canned responses.

    The axis universe (``known_axes``) is the single source of truth for
    what NAKs and what ACKs. Commands that name an unknown axis raise
    ``AerotechError`` — same shape as the real driver's ``_send`` on a NAK.

    AXISSTATUS responds with a configurable ``axis_status`` int so tests
    can fake "still moving" vs "settled" without poking the driver.
    """

    def __init__(self, known_axes=("X", "Y"), axis_status: int = 0, fault: int = 0):
        self.known_axes: Set[str] = set(known_axes)
        self.sent: List[str] = []
        self.axis_status = axis_status
        self.fault = fault
        self._positions: Dict[str, float] = {a: 0.0 for a in known_axes}

    def set_position(self, axis: str, value: float) -> None:
        self._positions[axis] = value

    async def respond(self, cmd: str) -> str:
        self.sent.append(cmd)
        # AXISSTATUS / AXISFAULT / PFBK / VFBK are 'NAME(axis)' shape
        for prefix in ("PFBK", "VFBK", "AXISSTATUS", "AXISFAULT"):
            if cmd.startswith(f"{prefix}(") and cmd.endswith(")"):
                axis = cmd[len(prefix) + 1:-1]
                if axis not in self.known_axes:
                    raise AerotechError(f"AeroBasic error for '{cmd}': !")
                if prefix in ("PFBK", "VFBK"):
                    return f"{self._positions[axis]:.4f}"
                if prefix == "AXISSTATUS":
                    return str(self.axis_status)
                # AXISFAULT
                return str(self.fault)
        # ENABLE / DISABLE / HOME / ABORT / MOVEABS — accept any axis list
        # that consists only of known axes; NAK if any axis is unknown.
        for prefix in ("ENABLE", "DISABLE", "HOME", "ABORT", "MOVEABS"):
            if cmd.startswith(prefix + " "):
                rest = cmd[len(prefix) + 1:]
                # MOVEABS is "MOVEABS X 0.0000 Y 1.0000" — pick axis names
                # by position 0/2/... (every other token).
                tokens = rest.split()
                axes_named = tokens[0::2] if prefix == "MOVEABS" else tokens
                for a in axes_named:
                    if a not in self.known_axes:
                        raise AerotechError(f"AeroBasic error for '{cmd}': !")
                return ""
        if cmd == "ACKNOWLEDGEALL":
            return ""
        return ""


class StubbedDriver(RealAerotechDriver):
    """RealAerotechDriver with ``_send`` hijacked + TCP layer faked.

    Bypasses real ``asyncio.open_connection`` so tests don't need a network.
    The ``_reader`` / ``_writer`` are set to truthy sentinels so the
    ``not self._writer`` guard in the real ``_send`` (which we override
    here anyway) wouldn't trip if subclasses call super.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any], fake: FakeController):
        super().__init__(instrument_id, config)
        self._fake = fake
        self._reader = object()  # type: ignore[assignment]
        self._writer = object()  # type: ignore[assignment]

    async def _send(self, cmd: str) -> str:
        return await self._fake.respond(cmd)


def _make_driver(known_axes=("X", "Y"), config=None) -> "tuple[StubbedDriver, FakeController]":
    cfg = config or {}
    fake = FakeController(known_axes=known_axes)
    return StubbedDriver("aerotech-test", cfg, fake), fake


# ---------------------------------------------------------------------------
# _probe_axis + is_single_axis
# ---------------------------------------------------------------------------

class TestProbeAxis:
    @pytest.mark.asyncio
    async def test_probe_known_axis_returns_true(self):
        d, _ = _make_driver(known_axes=("X", "Y"))
        assert await d._probe_axis("X") is True

    @pytest.mark.asyncio
    async def test_probe_unknown_axis_returns_false_no_raise(self):
        d, _ = _make_driver(known_axes=("X",))
        # PFBK(Y) NAK on a single-axis controller — must NOT raise.
        assert await d._probe_axis("Y") is False

    @pytest.mark.asyncio
    async def test_probe_sends_pfbk_only(self):
        d, fake = _make_driver(known_axes=("X",))
        await d._probe_axis("X")
        # Read-only contract: only PFBK was sent, never ENABLE / HOME / etc.
        assert fake.sent == ["PFBK(X)"]


class TestIsSingleAxisProperty:
    def test_before_connect_returns_false(self):
        d, _ = _make_driver()
        # _axes_present is empty before connect → property is meaningless
        # but must not raise.
        assert d.is_single_axis is False

    def test_with_az_only_present_returns_true(self):
        d, _ = _make_driver()
        d._axes_present = ["X"]
        assert d.is_single_axis is True

    def test_with_both_axes_present_returns_false(self):
        d, _ = _make_driver()
        d._axes_present = ["X", "Y"]
        assert d.is_single_axis is False


# ---------------------------------------------------------------------------
# move_to in single-axis mode
# ---------------------------------------------------------------------------

class TestMoveToSingleAxis:
    @pytest.mark.asyncio
    async def test_send_moveabs_only_for_x(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]  # simulate post-connect state
        # _wait_for_settle polls AXISSTATUS — make it settled immediately
        # so move_to returns instead of hitting the 60s settle timeout.
        fake.axis_status = 1 << AxisStatusBit.IN_POSITION
        d.poll_interval_s = 0.001
        assert await d.move_to(180.0, 30.0) is True

        moveabs = [c for c in fake.sent if c.startswith("MOVEABS")]
        assert len(moveabs) == 1
        # Single-axis: MOVEABS X 180.0000  (no Y)
        assert moveabs[0] == "MOVEABS X 180.0000"
        # And no Y-axis PFBK after the move either.
        assert "PFBK(Y)" not in fake.sent

    @pytest.mark.asyncio
    async def test_elevation_ignored_with_warning(self, caplog):
        import logging
        caplog.set_level(logging.WARNING, logger="app.hal.aerotech_positioner")
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        fake.axis_status = 1 << AxisStatusBit.IN_POSITION
        d.poll_interval_s = 0.001
        await d.move_to(45.0, 30.0)  # non-zero el on single-axis box
        # Operator should see something in the log so they don't think
        # they commanded 3D motion.
        assert any(
            "elevation=30.00" in rec.getMessage() and "ignored" in rec.getMessage()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_dual_axis_still_sends_both(self):
        d, fake = _make_driver(known_axes=("X", "Y"))
        d._axes_present = ["X", "Y"]
        fake.axis_status = 1 << AxisStatusBit.IN_POSITION
        d.poll_interval_s = 0.001
        assert await d.move_to(180.0, 45.0) is True
        moveabs = [c for c in fake.sent if c.startswith("MOVEABS")]
        # AeroBasic MOVEABS is axis-position interleaved, NOT axes-then-positions.
        assert moveabs == ["MOVEABS X 180.0000 Y 45.0000"]


# ---------------------------------------------------------------------------
# get_position / disconnect / stop / _wait_for_settle in single-axis mode
# ---------------------------------------------------------------------------

class TestPerAxisMethodsRespectAxesPresent:
    @pytest.mark.asyncio
    async def test_get_position_single_axis_skips_y(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        fake.set_position("X", 95.5)
        az, el = await d.get_position()
        assert az == pytest.approx(95.5)
        # Single-axis contract: elevation always 0.0 (PositionerDriver
        # returns a 2-tuple; we don't break the contract, we degrade it).
        assert el == 0.0
        assert "PFBK(Y)" not in fake.sent

    @pytest.mark.asyncio
    async def test_disconnect_single_axis_disables_only_x(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        await d.disconnect()
        disables = [c for c in fake.sent if c.startswith("DISABLE")]
        assert disables == ["DISABLE X"]

    @pytest.mark.asyncio
    async def test_stop_single_axis_aborts_only_x(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        await d.stop()
        aborts = [c for c in fake.sent if c.startswith("ABORT")]
        assert aborts == ["ABORT X"]

    @pytest.mark.asyncio
    async def test_reset_single_axis_homes_only_x(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        # Set status to "settled" so _wait_for_settle returns immediately
        fake.axis_status = (
            (1 << AxisStatusBit.IN_POSITION)
        )
        d.poll_interval_s = 0.001
        await d.reset()
        homes = [c for c in fake.sent if c.startswith("HOME")]
        assert homes == ["HOME X"]

    @pytest.mark.asyncio
    async def test_wait_for_settle_single_axis_queries_only_x(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        fake.axis_status = (1 << AxisStatusBit.IN_POSITION)  # settled
        d.poll_interval_s = 0.001
        await d._wait_for_settle()
        # Only X status was polled — never Y.
        status_queries = [c for c in fake.sent if c.startswith("AXISSTATUS(")]
        assert all("X" in q for q in status_queries)
        assert not any("AXISSTATUS(Y)" in q for q in status_queries)


# ---------------------------------------------------------------------------
# get_capabilities reports the right shape
# ---------------------------------------------------------------------------

class TestCapabilitiesReflectActualAxes:
    @pytest.mark.asyncio
    async def test_single_axis_reports_2d_positioning_no_elevation(self):
        d, _ = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        caps = await d.get_capabilities()
        assert len(caps) == 1
        cap = caps[0]
        assert cap.name == "2d_positioning"
        assert "single-axis" in cap.description
        assert "elevation_range" not in cap.parameters
        assert cap.parameters["azimuth_range"] == [0, 360]
        assert cap.parameters["axes_present"] == ["X"]

    @pytest.mark.asyncio
    async def test_dual_axis_keeps_3d_positioning(self):
        d, _ = _make_driver(known_axes=("X", "Y"))
        d._axes_present = ["X", "Y"]
        caps = await d.get_capabilities()
        assert caps[0].name == "3d_positioning"
        assert caps[0].parameters["elevation_range"] == [-90, 90]
        assert caps[0].parameters["axes_present"] == ["X", "Y"]
