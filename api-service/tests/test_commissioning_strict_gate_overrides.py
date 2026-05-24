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
from app.api.commissioning import CreateSessionRequest, _request_overrides


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
