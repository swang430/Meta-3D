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


@pytest.mark.parametrize(
    ("global_mode", "instrument_mode", "expected"),
    [
        pytest.param(
            DriverMode.MOCK_FORCE, "real", False, id="mock-force-overrides-instrument-real"
        ),
        pytest.param(DriverMode.MOCK_FORCE, "mock", False, id="mock-force-keeps-instrument-mock"),
        pytest.param(
            DriverMode.MOCK_FORCE, "auto", False, id="mock-force-keeps-instrument-auto-mock"
        ),
        pytest.param(DriverMode.MOCK_FORCE, "", False, id="mock-force-keeps-unset-instrument-mock"),
        pytest.param(DriverMode.MOCK, "real", True, id="legacy-mock-honors-instrument-real"),
        pytest.param(DriverMode.MOCK, "mock", False, id="legacy-mock-keeps-instrument-mock"),
        pytest.param(DriverMode.MOCK, "auto", False, id="legacy-mock-auto-follows-global"),
        pytest.param(DriverMode.REAL, "mock", False, id="real-mode-honors-instrument-mock"),
        pytest.param(DriverMode.REAL, "real", True, id="real-mode-keeps-instrument-real"),
        pytest.param(DriverMode.REAL, "auto", True, id="real-mode-auto-follows-global"),
    ],
)
def test_decide_use_real_contract_matrix(global_mode, instrument_mode, expected):
    """Pin every cell of the global/per-instrument hardware safety matrix."""
    svc = InstrumentHALService(mode=global_mode)

    assert svc._decide_use_real(instrument_mode) is expected


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
