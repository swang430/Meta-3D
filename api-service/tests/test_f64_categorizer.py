"""F64 health probe — SCPI error-code categoriser regression.

CAICT 2026-05-13: F64's ATE Server uses ``-100,"ATE command not
supported"`` for "command not in firmware", deviating from IEEE 488.2
default semantics where ``-100..-109`` is "command syntax error" (header
parses, payload is off). Pre-fix, the probe miscategorised the range as
SUPPORTED — 8 commands were silently reported green on an F64 that
didn't implement them.

These tests pin the bucket boundaries so a future refactor that "tidies
up" the categoriser can't silently re-introduce the bug.

Reference: ``propsim_f64_health.py:_categorize_status`` docstring + the
F64 ATE Server SCPI guide §3.2 (`-100` is overloaded).
"""
from __future__ import annotations

import pytest

from app.diagnostics.sequences.propsim_f64_health import _categorize_status


class TestZeroIsSupported:
    def test_zero_is_supported(self):
        assert _categorize_status(0) == "SUPPORTED"


class TestNoneIsUnknown:
    def test_none_is_unknown(self):
        """No error code captured at all (e.g. transport-level failure
        before SYST:ERR? could be queried) — UNKNOWN, not SUPPORTED."""
        assert _categorize_status(None) == "UNKNOWN"


class TestF64UnsupportedRange:
    """The core regression fix: -109..-100 must bucket as UNSUPPORTED,
    not SUPPORTED. F64 ATE Server overloads this range."""

    @pytest.mark.parametrize("code", [-100, -101, -102, -103, -104, -105, -106, -107, -108, -109])
    def test_each_code_in_minus_100_to_minus_109_is_unsupported(self, code: int):
        assert _categorize_status(code) == "UNSUPPORTED", (
            f"err_code={code} must be UNSUPPORTED — F64 ATE Server uses this "
            f"range for 'command not in firmware', not for IEEE 488.2 "
            f"command-syntax-error semantics"
        )

    def test_minus_100_specifically_is_unsupported(self):
        """The exact code F64 returns for unknown commands. Pinning
        explicitly so a partial-range refactor (e.g. -109 < code, off-by-
        one) gets caught immediately."""
        assert _categorize_status(-100) == "UNSUPPORTED"


class TestUndefinedHeaderRangeUnsupported:
    """IEEE 488.2 ``-113`` ('undefined header') and ``-114`` ('header
    suffix out of range') — both mean "controller doesn't know this
    command". Same bucket as F64's -100 overload."""

    @pytest.mark.parametrize("code", [-113, -114])
    def test_undefined_header_codes_are_unsupported(self, code: int):
        assert _categorize_status(code) == "UNSUPPORTED"


class TestStateRejectedRangeSupported:
    """``-200..-299`` ('execution error') means the header WAS
    recognised — F64 knows the command, just refused this particular
    parameter / current state. From a probe POV that's success: the
    capability IS there, the test just chose the wrong arguments."""

    @pytest.mark.parametrize("code", [-200, -222, -250, -270, -299])
    def test_each_code_in_minus_200_to_minus_299_is_supported_but_state(self, code: int):
        assert _categorize_status(code) == "SUPPORTED_BUT_STATE"


class TestBucketBoundaries:
    """Off-by-one guards — the most likely shape of a regression is a
    boundary slip in ``<=``/`<`."""

    def test_minus_99_not_in_unsupported_range(self):
        """-99 is above the unsupported-range upper bound."""
        assert _categorize_status(-99) != "UNSUPPORTED"

    def test_minus_110_not_in_unsupported_range(self):
        """-110/-111/-112 fall between the two unsupported groups —
        they bucket as UNKNOWN under the current rules. Pinning so a
        future widening or narrowing has to update this test
        deliberately."""
        for code in (-110, -111, -112):
            assert _categorize_status(code) == "UNKNOWN", (
                f"err_code={code} sits in a SCPI-defined region that "
                f"the F64 probe rules don't currently cover; bucket "
                f"is intentionally UNKNOWN. Change the rule deliberately "
                f"if you mean to."
            )

    def test_minus_115_is_unknown(self):
        """-115..-199 isn't in any explicit bucket — UNKNOWN by default."""
        assert _categorize_status(-115) == "UNKNOWN"

    def test_minus_199_not_in_state_range(self):
        """-199 is just above the state-rejected range — UNKNOWN."""
        assert _categorize_status(-199) == "UNKNOWN"

    def test_minus_300_not_in_state_range(self):
        """-300 is just below the state-rejected range — UNKNOWN."""
        assert _categorize_status(-300) == "UNKNOWN"


class TestPositiveCodesAreUnknown:
    """Positive error codes are device-specific in IEEE 488.2 — the F64
    probe doesn't claim to interpret them, so they bucket as UNKNOWN."""

    @pytest.mark.parametrize("code", [1, 100, 999])
    def test_positive_codes_are_unknown(self, code: int):
        assert _categorize_status(code) == "UNKNOWN"
