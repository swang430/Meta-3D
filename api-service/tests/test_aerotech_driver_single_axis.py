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

import asyncio
from typing import Any, Dict, List, Set

import pytest

from app.hal.aerotech_positioner import (
    AerotechCommandRejected,
    AerotechError,
    RealAerotechDriver,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

class FakeController:
    """Records every AeroBasic command + emits canned responses.

    The axis universe (``known_axes``) is the single source of truth for
    what NAKs and what ACKs. Commands that name an unknown axis raise
    ``AerotechCommandRejected`` — same shape as the real driver's NAK path.

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
                    raise AerotechCommandRejected(
                        f"AeroBasic error for '{cmd}': !"
                    )
                if prefix == "PFBK":
                    return f"{self._positions[axis]:.4f}"
                if prefix == "VFBK":
                    return "0.0000"
                if prefix == "AXISSTATUS":
                    return str(self.axis_status)
                # AXISFAULT
                return str(self.fault)
        if cmd.startswith("WAIT INPOS "):
            axis = cmd.removeprefix("WAIT INPOS ")
            if axis not in self.known_axes:
                raise AerotechCommandRejected(
                    f"AeroBasic error for '{cmd}': !"
                )
            return ""
        # ENABLE / DISABLE / HOME / ABORT / MOVEABS — accept any axis list
        # that consists only of known axes; NAK if any axis is unknown.
        for prefix in ("ENABLE", "DISABLE", "HOME", "ABORT", "MOVEABS"):
            if cmd.startswith(prefix + " "):
                rest = cmd[len(prefix) + 1:]
                # The checked-in integration guide and the CAICT controller
                # use ``MOVEABS X <target> XF<feed>``.
                tokens = rest.split()
                axes_named = (
                    [tokens[0]] if prefix == "MOVEABS" else tokens
                )
                for a in axes_named:
                    if a not in self.known_axes:
                        raise AerotechError(f"AeroBasic error for '{cmd}': !")
                # Happy-path controller: accepted motion updates encoder
                # feedback. P1-56 stuck-encoder cases use their own scripted
                # controller so the legacy single/dual-axis tests keep
                # describing a normally moving device.
                if prefix == "HOME":
                    for axis in axes_named:
                        self._positions[axis] = 0.0
                elif prefix == "MOVEABS":
                    self._positions[tokens[0]] = float(tokens[1])
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

    async def _send(
        self,
        cmd: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        if (
            expected_operator_stop_generation is not None
            and self.operator_stop_generation()
            != expected_operator_stop_generation
        ):
            raise AerotechError("operator stop requested")
        return await self._fake.respond(cmd)


def _make_driver(known_axes=("X", "Y"), config=None) -> "tuple[StubbedDriver, FakeController]":
    cfg = {
        "motion_truth_units_verified": True,
        "motion_truth_user_units": "degree",
        "motion_truth_min_deg": 0.0,
        "motion_truth_max_deg": 360.0,
        "motion_truth_xf_speed": 5.0,
        "motion_truth_coordinate_offset_verified": True,
        "motion_truth_coordinate_offset_deg": 0.0,
        **(config or {}),
    }
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
        d.poll_interval_s = 0.001
        assert await d.move_to(180.0, 0.0) is True

        moveabs = [c for c in fake.sent if c.startswith("MOVEABS")]
        assert len(moveabs) == 1
        # Single-axis: explicit, site-attested feed (no Y).
        assert moveabs[0] == "MOVEABS X 180.0000 XF5.0000"
        # And no Y-axis PFBK after the move either.
        assert "PFBK(Y)" not in fake.sent

    @pytest.mark.asyncio
    async def test_nonzero_elevation_is_rejected_before_io(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        assert await d.move_to(45.0, 30.0) is False
        assert not any(c.startswith("MOVEABS") for c in fake.sent)

    @pytest.mark.asyncio
    async def test_dual_axis_motion_is_fail_closed_without_vendor_command_evidence(self):
        d, fake = _make_driver(known_axes=("X", "Y"))
        d._axes_present = ["X", "Y"]
        assert await d.move_to(180.0, 45.0) is False
        moveabs = [c for c in fake.sent if c.startswith("MOVEABS")]
        assert moveabs == []


class TestSocket2ResponseFraming:
    class _Writer:
        def __init__(self) -> None:
            self.sent: list[bytes] = []

        def write(self, payload: bytes) -> None:
            self.sent.append(payload)

        async def drain(self) -> None:
            return None

    @pytest.mark.asyncio
    async def test_command_ack_without_line_terminator_returns_immediately(self):
        driver = RealAerotechDriver(
            "aerotech-test",
            {"ip": "192.0.2.10", "timeout_s": 0.01},
        )
        reader = asyncio.StreamReader()
        reader.feed_data(b"%")
        writer = self._Writer()
        driver._reader = reader
        driver._writer = writer  # type: ignore[assignment]

        assert await driver._tx_rx("ABORT X") == ""
        assert writer.sent == [b"ABORT X\n"]

    @pytest.mark.asyncio
    async def test_command_terminator_cannot_be_reused_as_next_query_response(self):
        driver = RealAerotechDriver(
            "aerotech-test",
            {"ip": "192.0.2.10", "timeout_s": 0.05},
        )
        reader = asyncio.StreamReader()
        # CAICT 2026-08-27 trace: a command response can leave LF after the
        # one-byte ACK.  The following query must skip that framing byte and
        # consume only its own marker + data.
        reader.feed_data(b"%\n%12.5\n")
        writer = self._Writer()
        driver._reader = reader
        driver._writer = writer  # type: ignore[assignment]

        assert await driver._tx_rx("ENABLE X") == ""
        assert await driver._tx_rx("PFBK(X)") == "12.5"
        assert writer.sent == [b"ENABLE X\n", b"PFBK(X)\n"]

    def test_motion_commands_use_the_settle_timeout_budget(self):
        driver = RealAerotechDriver(
            "aerotech-test",
            {"ip": "192.0.2.10", "timeout_s": 0.01, "settle_timeout_s": 60},
        )

        assert driver._response_timeout_s("ENABLE X") == pytest.approx(0.01)
        assert driver._response_timeout_s("MOVEABS X 20 XF5") == pytest.approx(60)
        assert driver._response_timeout_s("HOME X") == pytest.approx(60)
        assert driver._response_timeout_s("WAIT INPOS X") == pytest.approx(60)

    def test_space_form_getparm_is_classified_as_query(self):
        assert (
            RealAerotechDriver._aerobasic_operation("GETPARM X, 129")
            == "query"
        )


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
    async def test_disconnect_is_transport_only_without_unsourced_disable(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        await d.disconnect()
        disables = [c for c in fake.sent if c.startswith("DISABLE")]
        assert disables == []

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
        d.poll_interval_s = 0.001
        await d.reset()
        homes = [c for c in fake.sent if c.startswith("HOME")]
        assert homes == ["HOME X"]

    @pytest.mark.asyncio
    async def test_wait_for_settle_uses_sourced_wait_inpos_only_for_x(self):
        d, fake = _make_driver(known_axes=("X",))
        d._axes_present = ["X"]
        d.poll_interval_s = 0.001
        await d._wait_for_settle()
        assert "WAIT INPOS X" in fake.sent
        assert not any(c.startswith("AXISSTATUS(") for c in fake.sent)


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
        assert cap.parameters["position_unit"] == "degree"
        assert cap.supported is True
        assert cap.parameters["axes_present"] == ["X"]

    @pytest.mark.asyncio
    async def test_dual_axis_is_read_only_without_sourced_motion_contract(self):
        d, _ = _make_driver(known_axes=("X", "Y"))
        d._axes_present = ["X", "Y"]
        caps = await d.get_capabilities()
        assert caps[0].name == "3d_positioning"
        assert caps[0].supported is False
        assert caps[0].parameters["position_unit"] == "unknown"
        assert "elevation_range" not in caps[0].parameters
        assert caps[0].parameters["axes_present"] == ["X", "Y"]
