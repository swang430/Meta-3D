"""RealAerotechDriver — TCP keepalive on the underlying socket.

The silent-reconnect path (PR #14) catches idle-close at the *next* I/O.
For polling code that hits the wire every few seconds that's fine, but
calibration loops idle for minutes between motion commands — without OS-
level keepalive, the half-close is only discovered when the operator's
next ``MOVEABS`` times out.

These tests verify the driver asks the OS for keepalive on connect() and
on silent_reconnect(). They don't simulate a NAT timeout (that needs a
real network); they pin the ``setsockopt`` contract so a future refactor
that strips this hardening fails loudly.

Single source of truth for the keepalive values is
``_enable_tcp_keepalive`` in ``aerotech_positioner.py``.
"""
from __future__ import annotations

import asyncio
import socket as _socket
from typing import Any, List, Tuple

import pytest

from app.hal import aerotech_positioner as aero_mod
from app.hal.aerotech_positioner import RealAerotechDriver


class _RecordingSocket:
    """Captures every ``setsockopt`` call so the test can assert on them.

    Behaves like a real socket only insofar as the keepalive helper
    needs — accepts setsockopt, errors are surfaced as the helper
    expects (returns rather than raising for non-fatal misses)."""

    def __init__(self) -> None:
        self.calls: List[Tuple[int, int, int]] = []
        self.refuse: set[Tuple[int, int]] = set()

    def setsockopt(self, level: int, optname: int, value: int) -> None:
        if (level, optname) in self.refuse:
            raise OSError("simulated: kernel rejects this option")
        self.calls.append((level, optname, value))


class _RecordingWriter:
    """asyncio.StreamWriter stub exposing the recording socket via
    ``get_extra_info("socket")`` — same surface the helper uses."""

    def __init__(self, sock: _RecordingSocket) -> None:
        self._sock = sock

    def get_extra_info(self, name: str) -> Any:
        return self._sock if name == "socket" else None


class TestEnableTcpKeepaliveSetsSoKeepalive:
    def test_so_keepalive_set_on_success(self):
        sock = _RecordingSocket()
        writer = _RecordingWriter(sock)
        RealAerotechDriver._enable_tcp_keepalive(writer)  # type: ignore[arg-type]
        # SO_KEEPALIVE at SOL_SOCKET must always be turned on.
        assert (_socket.SOL_SOCKET, _socket.SO_KEEPALIVE, 1) in sock.calls

    def test_so_keepalive_failure_is_non_fatal(self):
        """If the OS refuses SO_KEEPALIVE, the helper bails without
        raising — the socket still works at OS defaults."""
        sock = _RecordingSocket()
        sock.refuse.add((_socket.SOL_SOCKET, _socket.SO_KEEPALIVE))
        writer = _RecordingWriter(sock)
        # Must not raise.
        RealAerotechDriver._enable_tcp_keepalive(writer)  # type: ignore[arg-type]
        # And it shouldn't have tried later opts after the initial refusal.
        assert all(c[1] != _socket.SO_KEEPALIVE for c in sock.calls)


class TestKeepaliveTuningApplied:
    def test_tcp_keepidle_or_keepalive_attempted(self):
        """Platform-specific idle-time option must be attempted.

        Linux exposes the idle time as ``TCP_KEEPIDLE``, macOS as
        ``TCP_KEEPALIVE`` (different from ``SO_KEEPALIVE``, same purpose
        as Linux's IDLE). At least one of the two must end up in the
        recorded setsockopt calls — depending on which constants exist
        in the running platform's ``socket`` module."""
        sock = _RecordingSocket()
        RealAerotechDriver._enable_tcp_keepalive(_RecordingWriter(sock))  # type: ignore[arg-type]
        applicable = []
        for name in ("TCP_KEEPIDLE", "TCP_KEEPALIVE"):
            opt = getattr(_socket, name, None)
            if opt is not None:
                applicable.append((opt, name))
        if not applicable:
            pytest.skip("running platform exposes neither TCP_KEEPIDLE nor TCP_KEEPALIVE")
        opt_codes_seen = {c[1] for c in sock.calls if c[0] == _socket.IPPROTO_TCP}
        # At least one of the platform-available idle-time options was attempted.
        assert any(opt in opt_codes_seen for opt, _name in applicable)

    def test_keepintvl_and_keepcnt_attempted_when_available(self):
        sock = _RecordingSocket()
        RealAerotechDriver._enable_tcp_keepalive(_RecordingWriter(sock))  # type: ignore[arg-type]
        opt_codes_seen = {c[1] for c in sock.calls if c[0] == _socket.IPPROTO_TCP}
        for name in ("TCP_KEEPINTVL", "TCP_KEEPCNT"):
            opt = getattr(_socket, name, None)
            if opt is None:
                continue
            assert opt in opt_codes_seen, (
                f"{name} is available on this platform but the helper "
                f"never called setsockopt with it"
            )


class TestNoSocketAvailableIsNoOp:
    def test_writer_with_no_extra_info_socket_does_not_raise(self):
        """Some asyncio transports don't expose a raw socket (testing
        stubs, custom transports). The helper must gracefully no-op
        rather than crashing connect()."""

        class _NoSockWriter:
            def get_extra_info(self, _name: str) -> Any:
                return None

        # Must not raise.
        RealAerotechDriver._enable_tcp_keepalive(_NoSockWriter())  # type: ignore[arg-type]


class TestKeepaliveCalledOnConnectAndReconnect:
    """End-to-end check: keepalive helper is invoked during both
    ``connect()`` (initial open) and ``_silent_reconnect()`` (post idle-
    close re-open). Easy to silently regress in a refactor — pin it."""

    def _build_driver(self) -> RealAerotechDriver:
        return RealAerotechDriver(
            instrument_id="aero-keepalive-test",
            config={"ip": "192.168.0.16", "port": 8000, "elevation_axis": ""},
        )

    @pytest.mark.asyncio
    async def test_connect_invokes_keepalive(self, monkeypatch):
        d = self._build_driver()
        calls: List[str] = []

        class _StubReader:
            def __init__(self) -> None:
                self._responses = [
                    b"%\n",          # ACKNOWLEDGE_ALL
                    b"%0.0\n",       # PFBK(X) probe
                    b"%\n",          # ENABLE X
                    b"%0.0\n",       # PFBK(X) initial position read
                ]
            async def readline(self) -> bytes:
                return self._responses.pop(0) if self._responses else b"%\n"

        class _StubWriter:
            def __init__(self, name: str) -> None:
                self._name = name
            def write(self, data: bytes) -> None:
                pass
            async def drain(self) -> None:
                pass
            def close(self) -> None:
                pass
            async def wait_closed(self) -> None:
                pass
            def is_closing(self) -> bool:
                return False
            def get_extra_info(self, _name: str) -> Any:
                return _RecordingSocket()

        async def fake_open(host, port):
            return _StubReader(), _StubWriter("primary")

        monkeypatch.setattr(aero_mod.asyncio, "open_connection", fake_open)
        monkeypatch.setattr(
            RealAerotechDriver,
            "_enable_tcp_keepalive",
            staticmethod(lambda writer: calls.append("connect")),
        )

        assert await d.connect() is True
        assert "connect" in calls

    @pytest.mark.asyncio
    async def test_silent_reconnect_invokes_keepalive(self, monkeypatch):
        d = self._build_driver()
        d._axes_present = ["X"]

        class _AlwaysOkReader:
            async def readline(self) -> bytes:
                return b"%\n"

        class _StubWriter:
            def write(self, _data: bytes) -> None:
                pass
            async def drain(self) -> None:
                pass
            def close(self) -> None:
                pass
            async def wait_closed(self) -> None:
                pass
            def is_closing(self) -> bool:
                return False
            def get_extra_info(self, _name: str) -> Any:
                return _RecordingSocket()

        async def fake_open(host, port):
            return _AlwaysOkReader(), _StubWriter()

        monkeypatch.setattr(aero_mod.asyncio, "open_connection", fake_open)
        calls: List[str] = []
        monkeypatch.setattr(
            RealAerotechDriver,
            "_enable_tcp_keepalive",
            staticmethod(lambda writer: calls.append("reconnect")),
        )

        # Pretend the old streams are dead — call _silent_reconnect directly.
        d._reader = None
        d._writer = None
        assert await d._silent_reconnect() is True
        assert "reconnect" in calls
