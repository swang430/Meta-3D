"""Pin `DriverMode.MOCK_FORCE` semantics — Codex P1 fix on PR #30.

The bug: ``scripts/driver_selftest --mode mock`` (defaulting to
``DriverMode.MOCK``) was opening real TCP/VISA connections to
configured hardware whenever any ``InstrumentCategory`` had
``driver_mode='real'`` set per-instrument. Operator running the
no-arg self-test could accidentally poke equipment.

The fix introduces a third mode, ``DriverMode.MOCK_FORCE``, that
overrides per-instrument ``'real'`` too. Existing ``MOCK`` /
``REAL`` semantics are preserved (per-instrument override still
honoured) so the GUI's HAL mode switch isn't affected.

Tests here pin both:
- the ``_decide_use_real`` decision table directly (pure function,
  no DB), so a future refactor of the per-instrument decision
  logic can't silently bring back the bug
- that ``MOCK`` (legacy) still honours per-instrument ``'real'`` —
  the regression boundary for the GUI flow
"""
from __future__ import annotations

import pytest

from app.services.instrument_hal_service import DriverMode, InstrumentHALService


class TestDecideUseRealMockForce:
    """MOCK_FORCE — hard mock, ignores per-instrument 'real'."""

    @pytest.fixture
    def svc(self):
        return InstrumentHALService(mode=DriverMode.MOCK_FORCE)

    def test_per_instrument_real_overridden(self, svc):
        # The exact bug Codex caught: in MOCK_FORCE, even an explicit
        # per-instrument 'real' must NOT load a real driver.
        assert svc._decide_use_real("real") is False

    def test_per_instrument_mock_stays_mock(self, svc):
        assert svc._decide_use_real("mock") is False

    def test_per_instrument_auto_stays_mock(self, svc):
        assert svc._decide_use_real("auto") is False

    def test_per_instrument_unset_stays_mock(self, svc):
        # Practical: a category row with no driver_mode column value
        # gets normalized to 'auto' upstream; pinning here so a future
        # refactor that drops the normalisation still produces mock.
        assert svc._decide_use_real("") is False


class TestDecideUseRealMockSoft:
    """MOCK (legacy) — soft mock, per-instrument 'real' still
    connects to hardware. Pinning the regression boundary so the
    GUI's existing HAL mode switch behavior doesn't drift."""

    @pytest.fixture
    def svc(self):
        return InstrumentHALService(mode=DriverMode.MOCK)

    def test_per_instrument_real_still_loads_real(self, svc):
        # This is the EXPECTED behavior for MOCK (in contrast to
        # MOCK_FORCE). An operator who deliberately set one
        # instrument to 'real' wants it real even when global is mock.
        assert svc._decide_use_real("real") is True

    def test_per_instrument_mock_stays_mock(self, svc):
        assert svc._decide_use_real("mock") is False

    def test_per_instrument_auto_follows_global(self, svc):
        # auto + global MOCK → mock
        assert svc._decide_use_real("auto") is False


class TestDecideUseRealRealMode:
    """REAL — real by default, per-instrument 'mock' still goes mock."""

    @pytest.fixture
    def svc(self):
        return InstrumentHALService(mode=DriverMode.REAL)

    def test_per_instrument_mock_stays_mock(self, svc):
        assert svc._decide_use_real("mock") is False

    def test_per_instrument_real_loads_real(self, svc):
        assert svc._decide_use_real("real") is True

    def test_per_instrument_auto_follows_global(self, svc):
        # auto + global REAL → real
        assert svc._decide_use_real("auto") is True


class TestEnumMembership:
    """Pin that all three modes exist by name + value so the CLI's
    string mapping (``"mock_force"`` <-> ``DriverMode.MOCK_FORCE``)
    can't silently drift."""

    def test_three_modes_present(self):
        assert {m.value for m in DriverMode} == {"mock", "real", "mock_force"}

    def test_mock_force_value_is_stable(self):
        # Spelled in scripts/driver_selftest.py + GUI HAL switch
        # endpoint; renaming would break wire-compat for any caller
        # passing the string form.
        assert DriverMode.MOCK_FORCE.value == "mock_force"
