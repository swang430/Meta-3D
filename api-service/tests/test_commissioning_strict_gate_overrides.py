"""Regression: commissioning CreateSessionRequest → config override mapping for
the strict precheck gates (P1-8 cal / P1-9 DUT).

The Lab-smoke fix added optional `precheck_strict_dut` / `precheck_strict_cal`
fields to CreateSessionRequest. The correctness hazard is the explicit-null vs
omitted vs value cartesian (cf. feedback_endpoint_null_field_cartesian):

  - omitted (None)  → MUST NOT appear in the override dict, so the config schema
                      default (True / strict) is preserved. Leaking None into the
                      config would falsy-bypass `if config.precheck_strict_dut:`
                      for EVERY session — silently disabling the on-site gate.
  - explicit False  → appears as False (Lab-smoke opt-out).
  - explicit True   → appears as True.
"""
from app.api.commissioning import (
    CreateSessionRequest,
    _request_overrides,
    _apply_strict_gate_defaults,
)
from app.hal.base_station import MockBaseStation
from app.hal.channel_emulator import MockChannelEmulator


class _FakeHal:
    """Minimal HAL stand-in exposing only the `.drivers` dict the auto-default
    helper reads."""

    def __init__(self, drivers):
        self.drivers = drivers


class _RealishBaseStation:
    """A non-mock driver instance — is_mock_driver() returns False for it, so
    the gate treats it as real hardware. (We don't need a full real driver;
    only its type matters for the isinstance check.)"""


def test_strict_flags_omitted_are_absent_from_overrides():
    """Default request → flags not in overrides → config keeps strict default."""
    overrides = _request_overrides(CreateSessionRequest())
    assert "precheck_strict_dut" not in overrides
    assert "precheck_strict_cal" not in overrides


def test_strict_flags_false_pass_through():
    """Lab-smoke toggle → explicit False is carried into overrides."""
    overrides = _request_overrides(
        CreateSessionRequest(precheck_strict_dut=False, precheck_strict_cal=False)
    )
    assert overrides["precheck_strict_dut"] is False
    assert overrides["precheck_strict_cal"] is False


def test_strict_flags_true_pass_through():
    """Explicit True is carried (distinct from omitted, though same effect)."""
    overrides = _request_overrides(
        CreateSessionRequest(precheck_strict_dut=True, precheck_strict_cal=True)
    )
    assert overrides["precheck_strict_dut"] is True
    assert overrides["precheck_strict_cal"] is True


def test_one_flag_set_other_omitted():
    """Setting only one flag must not drag the other in as None."""
    overrides = _request_overrides(CreateSessionRequest(precheck_strict_dut=False))
    assert overrides["precheck_strict_dut"] is False
    assert "precheck_strict_cal" not in overrides


# --- _apply_strict_gate_defaults: auto-default by HAL mock/real mode ---------
# A real DUT can only attach to a real baseStation; mock/absent BS → no real
# DUT possible → strict DUT gate is moot. Same for cal keyed on channelEmulator.


def test_auto_default_mock_drivers_relax_gates():
    """Mock BS + mock CE → both strict gates default OFF (local rehearsal works
    without hunting for a toggle)."""
    hal = _FakeHal({
        "baseStation": MockBaseStation("mock-bs", {"model": "Mock"}),
        "channelEmulator": MockChannelEmulator("mock-ce", {"model": "Mock"}),
    })
    overrides: dict = {}
    _apply_strict_gate_defaults(overrides, hal)
    assert overrides["precheck_strict_dut"] is False
    assert overrides["precheck_strict_cal"] is False


def test_auto_default_real_drivers_keep_gates_strict():
    """Real (non-mock) BS + CE → strict gates default ON (P1-8/P1-9 preserved)."""
    hal = _FakeHal({
        "baseStation": _RealishBaseStation(),
        "channelEmulator": _RealishBaseStation(),  # any non-mock instance
    })
    overrides: dict = {}
    _apply_strict_gate_defaults(overrides, hal)
    assert overrides["precheck_strict_dut"] is True
    assert overrides["precheck_strict_cal"] is True


def test_auto_default_absent_drivers_relax_gates():
    """No BS / CE loaded → no real DUT possible → gates default OFF."""
    hal = _FakeHal({})
    overrides: dict = {}
    _apply_strict_gate_defaults(overrides, hal)
    assert overrides["precheck_strict_dut"] is False
    assert overrides["precheck_strict_cal"] is False


def test_auto_default_does_not_override_explicit_flag():
    """An explicit request flag wins even against the HAL-mode default —
    operator's Lab-smoke override / a test's explicit config is honoured."""
    hal = _FakeHal({"baseStation": _RealishBaseStation()})  # real → would default True
    overrides = {"precheck_strict_dut": False}  # explicit opt-out already present
    _apply_strict_gate_defaults(overrides, hal)
    assert overrides["precheck_strict_dut"] is False  # not clobbered to True
    # cal flag was unset + CE absent → defaults False
    assert overrides["precheck_strict_cal"] is False
