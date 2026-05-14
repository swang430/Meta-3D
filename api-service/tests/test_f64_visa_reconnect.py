"""RealPropsimF64Driver — transparent VISA reconnect on conn-lost shapes.

Mirrors the Aerotech idle-close reconnect (PR #14) but for PyVISA
transport. F64 is the first PyVISA-backed driver to get the pattern
because calibration loops leave the resource idle for minutes between
commands, which is exactly when network NAT / instrument-side idle
timeouts surface.

Contract pinned by these tests:
  1. ``VI_ERROR_CONN_LOST`` (0xBFFF00B5) triggers ONE reconnect + retry.
  2. ``VI_ERROR_INV_OBJECT`` (0xBFFF000E) triggers ONE reconnect + retry.
  3. ``VI_ERROR_TMO`` (0xBFFF0015) does NOT trigger reconnect — let
     timeouts propagate so callers can decide (same Codex-#14 lesson).
  4. Non-VISA exceptions don't trigger reconnect.
  5. Bounded — second consecutive conn-lost still raises (no infinite loop).
  6. Both ``_do_write`` and ``_do_query`` honour the contract.

We don't talk to a real F64; PyVISA is monkey-patched at the
``ResourceManager.open_resource`` boundary with a fake resource whose
``write`` / ``query`` can be programmed to fail-then-succeed.
"""
from __future__ import annotations

from typing import Any, List

import pytest

# pyvisa must be importable — F64 driver imports it lazily inside
# methods, the test imports it eagerly so VisaIOError is available to
# the test.
pyvisa = pytest.importorskip("pyvisa")

from app.hal.propsim_f64 import RealPropsimF64Driver


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeVisaResource:
    """Records every write/query, can be programmed to raise specific
    VisaIOErrors on the first N calls then succeed."""

    def __init__(self, name: str = "primary") -> None:
        self.name = name
        self.writes: List[str] = []
        self.queries: List[str] = []
        self.write_fail_with: List[BaseException] = []
        self.query_fail_with: List[BaseException] = []
        self.query_response: str = "OK\n"
        self.timeout: int = 5000
        self.closed = False

    def write(self, cmd: str) -> None:
        if self.write_fail_with:
            exc = self.write_fail_with.pop(0)
            if exc is not None:
                raise exc
        self.writes.append(cmd)

    def query(self, cmd: str) -> str:
        if self.query_fail_with:
            exc = self.query_fail_with.pop(0)
            if exc is not None:
                raise exc
        self.queries.append(cmd)
        return self.query_response

    def close(self) -> None:
        self.closed = True


class _FakeResourceManager:
    """Hands out fake resources from a pre-built list — first call gets
    the first resource, the silent-reconnect call gets the next one.
    Test asserts which resource each command landed on."""

    def __init__(self, resources: List[_FakeVisaResource]) -> None:
        self._resources = resources
        self.open_calls: int = 0

    def open_resource(self, *_args, **_kwargs) -> _FakeVisaResource:
        self.open_calls += 1
        if not self._resources:
            raise OSError("test bug: open_resource called more times than fakes provided")
        return self._resources.pop(0)


def _mk_visa_error(code_unsigned: int) -> pyvisa.errors.VisaIOError:
    """Build a VisaIOError with the requested error_code so the driver's
    ``_is_visa_conn_lost`` sees what it expects.

    PyVISA's constructor signature varies a tiny bit by version; the
    safe path is to instantiate then poke error_code."""
    err = pyvisa.errors.VisaIOError(code_unsigned)
    return err


def _build_driver_with_fake_session(primary: _FakeVisaResource, *, post_reconnect: List[_FakeVisaResource] = None):
    """Construct a F64 driver wired to ``primary`` as its live resource
    and a fake RM that hands out ``post_reconnect`` when silent reconnect
    fires."""
    d = RealPropsimF64Driver(
        instrument_id="f64-test",
        config={"ip": "192.168.0.100", "port": 5025},
    )
    d._visa_resource = primary
    d._rm = _FakeResourceManager(list(post_reconnect or []))
    return d


# ---------------------------------------------------------------------------
# 1. Conn-lost shapes trigger reconnect
# ---------------------------------------------------------------------------

class TestConnLostTriggersReconnect:
    @pytest.mark.asyncio
    async def test_conn_lost_on_query_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]  # VI_ERROR_CONN_LOST
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_response = "READY\n"

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        result = await d._do_query("*IDN?")
        assert result == "READY\n"
        # Old resource closed, new one used for the retry.
        assert primary.closed is True
        assert replacement.queries == ["*IDN?"]
        # Exactly one open_resource call (the silent reconnect).
        assert d._rm.open_calls == 1

    @pytest.mark.asyncio
    async def test_inv_object_on_write_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(0xBFFF000E)]  # VI_ERROR_INV_OBJECT
        replacement = _FakeVisaResource("post-reconnect")

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        await d._do_write("INIT")
        assert replacement.writes == ["INIT"]
        assert primary.closed is True


# ---------------------------------------------------------------------------
# 2. Timeout MUST NOT trigger reconnect — Codex P2 lesson
# ---------------------------------------------------------------------------

class TestTimeoutDoesNotReconnect:
    @pytest.mark.asyncio
    async def test_vi_error_tmo_on_query_propagates(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)]  # VI_ERROR_TMO

        d = _build_driver_with_fake_session(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            await d._do_query("SYST:ERR?")
        # The exact error_code survived — caller can switch on it.
        assert (exc_info.value.error_code & 0xFFFFFFFF) == 0xBFFF0015
        # No reconnect attempted (we provided no post-reconnect resource;
        # if the driver tried, open_resource would raise OSError).
        assert d._rm.open_calls == 0
        assert primary.closed is False

    @pytest.mark.asyncio
    async def test_vi_error_tmo_on_write_propagates(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(0xBFFF0015)]

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_write("CALC:STAT ON")
        assert d._rm.open_calls == 0


# ---------------------------------------------------------------------------
# 3. Non-VISA errors don't trigger reconnect
# ---------------------------------------------------------------------------

class TestNonVisaErrorsPropagate:
    @pytest.mark.asyncio
    async def test_plain_runtime_error_does_not_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [RuntimeError("test: not a VISA error")]

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        with pytest.raises(RuntimeError):
            await d._do_query("*IDN?")
        assert d._rm.open_calls == 0


# ---------------------------------------------------------------------------
# 4. Bounded retry — second conn-lost still raises (no infinite loop)
# ---------------------------------------------------------------------------

class TestRetryIsBounded:
    @pytest.mark.asyncio
    async def test_second_consecutive_conn_lost_raises(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]
        # Post-reconnect resource ALSO conn-losts on the retry.
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_fail_with = [_mk_visa_error(0xBFFF00B5)]

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("*IDN?")
        # Reconnect happened exactly once — no third attempt.
        assert d._rm.open_calls == 1

    @pytest.mark.asyncio
    async def test_silent_reconnect_failure_surfaces_original(self):
        """When ``_silent_reconnect_visa`` itself can't reopen
        (e.g. rm.open_resource raises), the original conn-lost VISA
        error propagates — caller sees a meaningful exception, not a
        masked one."""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        # Empty post_reconnect list — RM.open_resource will raise OSError,
        # _silent_reconnect_visa returns False, original VisaIOError propagates.
        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            await d._do_query("*IDN?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == 0xBFFF00B5


# ---------------------------------------------------------------------------
# 5. Healthy path: no reconnect happens when nothing fails
# ---------------------------------------------------------------------------

class TestHealthyPathNoReconnect:
    @pytest.mark.asyncio
    async def test_successful_query_uses_same_session(self):
        primary = _FakeVisaResource("primary")
        primary.query_response = "PROPSIM,F64,SN12345\n"

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        result = await d._do_query("*IDN?")
        assert result == "PROPSIM,F64,SN12345\n"
        assert d._rm.open_calls == 0  # never reconnected
        assert primary.closed is False
        assert primary.queries == ["*IDN?"]


# ---------------------------------------------------------------------------
# 6. _is_visa_conn_lost classifier unit tests
# ---------------------------------------------------------------------------

class TestIsVisaConnLostClassifier:
    def test_conn_lost_code_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(_mk_visa_error(0xBFFF00B5)) is True

    def test_inv_object_code_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(_mk_visa_error(0xBFFF000E)) is True

    def test_timeout_not_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(_mk_visa_error(0xBFFF0015)) is False

    def test_non_visa_error_not_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(RuntimeError("not visa")) is False
        assert d._is_visa_conn_lost(ConnectionResetError("plain")) is False
