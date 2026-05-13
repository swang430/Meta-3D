"""RealAerotechDriver — transparent reconnect after idle close.

CAICT 2026-05-13 site reality: the Ensemble Socket2 silently closes idle
TCP connections after ~30 s of inactivity. The first command after the
close used to surface as ``BrokenPipeError`` / empty-readline EOF and
broke every probe / poll that wasn't sending back-to-back.

These tests pin the recovery contract:

  1. One transparent reconnect on connection error (write OR read side).
  2. After reconnect, ACKNOWLEDGE_ALL + ENABLE of the cached
     ``_axes_present`` is re-sent BEFORE the user's command is retried.
  3. Only one retry — if reconnect fails, the original error surfaces
     as ``AerotechError`` (we don't hammer a dead controller).
  4. Caller gets the second response transparently — no exception leaks
     for the happy-path "socket recycled cleanly" case.

No real network: we replace the ``asyncio.StreamReader`` /
``StreamWriter`` pair with deterministic fakes and monkey-patch
``asyncio.open_connection`` so the reconnect path produces a fresh pair.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

import pytest

from app.hal import aerotech_positioner as aero_mod
from app.hal.aerotech_positioner import AerotechError, RealAerotechDriver


# ---------------------------------------------------------------------------
# Fake asyncio stream pair
# ---------------------------------------------------------------------------

class _FakeWriter:
    """Stub for ``asyncio.StreamWriter``. Records writes, can fail on
    ``drain()`` to simulate the Aerotech idle-close scenario where the
    OS-side socket buffer accepts the write but the remote has gone away.
    """

    def __init__(self, server: "_FakeServer"):
        self._server = server
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            raise BrokenPipeError("writer is closed")
        # Hand the bytes to the server so the matching reader can replay
        # them when ``readline()`` is awaited.
        self._server.feed_command(data)

    async def drain(self) -> None:
        # The server decides whether this drain succeeds (simulating the
        # case where the remote half-closed between writes).
        if self._server.drain_should_fail():
            raise ConnectionResetError("simulated broken pipe on drain")

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self._closed


class _FakeReader:
    """Stub for ``asyncio.StreamReader``. ``readline()`` returns canned
    responses queued by the server in order; an empty bytes return simulates
    a clean EOF half-close from the controller.
    """

    def __init__(self, server: "_FakeServer"):
        self._server = server

    async def readline(self) -> bytes:
        return await self._server.next_response()


class _FakeServer:
    """Pairs a fake reader+writer with controllable behaviour.

    The test sets up a queue of canned responses keyed off the next-command
    counter. ``drain_should_fail()`` lets us force a write-side failure
    on a specific command index. ``read_eof_on_command`` lets us return
    b'' from readline for a specific command index.

    Each ``open_connection()`` call in the driver gets a NEW server via the
    factory ``new_server()`` so the test can track "old server" vs
    "post-reconnect server" separately.
    """

    def __init__(self, name: str):
        self.name = name
        self.sent: List[str] = []
        self._responses: List[bytes] = []
        self._cmd_count = 0
        self._drain_fail_on: Optional[int] = None  # 0-indexed cmd number
        self._read_eof_on: Optional[int] = None

    # ---- test setup hooks ----
    def queue_response(self, line: str) -> None:
        """Queue a response (will receive the trailing \\n automatically)."""
        self._responses.append((line + "\n").encode("ascii"))

    def fail_drain_on(self, cmd_index: int) -> None:
        self._drain_fail_on = cmd_index

    def eof_read_on(self, cmd_index: int) -> None:
        self._read_eof_on = cmd_index

    # ---- driver-facing hooks ----
    def feed_command(self, data: bytes) -> None:
        self.sent.append(data.decode("ascii").rstrip("\n"))

    def drain_should_fail(self) -> bool:
        if self._drain_fail_on is not None and self._cmd_count == self._drain_fail_on:
            return True
        return False

    async def next_response(self) -> bytes:
        # If this command index is configured for EOF, return empty bytes
        # to simulate the remote closing the connection cleanly.
        if self._read_eof_on is not None and self._cmd_count == self._read_eof_on:
            self._cmd_count += 1
            return b""
        idx = self._cmd_count
        self._cmd_count += 1
        if idx >= len(self._responses):
            # Default ACK if test didn't queue anything specific.
            return b"%\n"
        return self._responses[idx]

    def make_streams(self) -> tuple[_FakeReader, _FakeWriter]:
        return _FakeReader(self), _FakeWriter(self)


def _install_open_connection(monkeypatch, servers: List[_FakeServer]) -> List[_FakeServer]:
    """Pre-build a list of servers; each ``open_connection`` call pops one.

    Returns the same list so tests can assert call counts / which server
    saw which command.
    """
    iterator = iter(servers)

    async def fake_open_connection(host, port, *args, **kwargs):
        try:
            srv = next(iterator)
        except StopIteration:
            raise OSError(
                f"test bug: open_connection called more times than fakes provided "
                f"(host={host}, port={port})"
            )
        return srv.make_streams()

    monkeypatch.setattr(aero_mod.asyncio, "open_connection", fake_open_connection)
    return servers


def _make_driver_with_streams(server: _FakeServer) -> RealAerotechDriver:
    """Build a driver in post-connect state, wired to ``server``."""
    d = RealAerotechDriver(
        instrument_id="aerotech-test",
        config={"ip": "192.168.0.16", "port": 8000, "elevation_axis": ""},
    )
    d._reader, d._writer = server.make_streams()
    # Pretend connect() already ran and discovered a single-axis turntable.
    d._axes_present = ["X"]
    return d


# ---------------------------------------------------------------------------
# Happy path — no idle close, no reconnect
# ---------------------------------------------------------------------------

class TestNoReconnectOnHealthyPath:
    @pytest.mark.asyncio
    async def test_send_uses_existing_socket_when_drain_and_read_ok(self, monkeypatch):
        srv = _FakeServer("primary")
        srv.queue_response("%12.34")
        d = _make_driver_with_streams(srv)
        # No new servers provisioned — if reconnect happens, the test fails
        # loudly because open_connection has nothing to return.
        _install_open_connection(monkeypatch, [])

        result = await d._send("PFBK(X)")

        assert result == "12.34"
        assert srv.sent == ["PFBK(X)"]


# ---------------------------------------------------------------------------
# Reconnect on EOF readline (the common Ensemble idle-close shape)
# ---------------------------------------------------------------------------

class TestReconnectOnEofRead:
    @pytest.mark.asyncio
    async def test_eof_triggers_reconnect_and_retries(self, monkeypatch):
        old = _FakeServer("old")
        old.eof_read_on(0)  # first command returns EOF on read
        new = _FakeServer("new")
        # Post-reconnect: ACK%, ENABLE%, then the retried PFBK gets "%12.34"
        new.queue_response("%")           # ACKNOWLEDGE_ALL
        new.queue_response("%")           # ENABLE X
        new.queue_response("%12.34")     # retried PFBK(X)

        d = _make_driver_with_streams(old)
        _install_open_connection(monkeypatch, [new])

        result = await d._send("PFBK(X)")

        # Caller sees the post-reconnect response, not the EOF.
        assert result == "12.34"
        # Old server saw exactly the original command before close.
        assert old.sent == ["PFBK(X)"]
        # New server saw the handshake then the retried command, in order.
        assert new.sent == ["ACKNOWLEDGEALL", "ENABLE X", "PFBK(X)"]
        # Driver now holds the *new* reader/writer pair.
        assert isinstance(d._writer, _FakeWriter)
        assert d._writer is not None and not d._writer.is_closing()

    @pytest.mark.asyncio
    async def test_dual_axis_reconnect_re_enables_both(self, monkeypatch):
        old = _FakeServer("old")
        old.eof_read_on(0)
        new = _FakeServer("new")
        new.queue_response("%")
        new.queue_response("%")
        new.queue_response("%5.0")

        d = _make_driver_with_streams(old)
        d._axes_present = ["X", "Y"]  # dual-axis post-connect state
        _install_open_connection(monkeypatch, [new])

        await d._send("PFBK(X)")
        # ENABLE must list both axes, in the cached order.
        assert new.sent[1] == "ENABLE X Y"


# ---------------------------------------------------------------------------
# Reconnect on write-side broken pipe (drain() raise)
# ---------------------------------------------------------------------------

class TestReconnectOnBrokenPipe:
    @pytest.mark.asyncio
    async def test_drain_failure_triggers_reconnect_and_retries(self, monkeypatch):
        old = _FakeServer("old")
        old.fail_drain_on(0)  # first command's drain() raises ConnectionReset
        new = _FakeServer("new")
        new.queue_response("%")
        new.queue_response("%")
        new.queue_response("%180.0")

        d = _make_driver_with_streams(old)
        _install_open_connection(monkeypatch, [new])

        result = await d._send("PFBK(X)")

        assert result == "180.0"
        # The handshake + retry hit the new server, in order.
        assert new.sent == ["ACKNOWLEDGEALL", "ENABLE X", "PFBK(X)"]


# ---------------------------------------------------------------------------
# Failure modes — bounded retry, no infinite loop
# ---------------------------------------------------------------------------

class TestReconnectBounded:
    @pytest.mark.asyncio
    async def test_reconnect_failure_surfaces_aerotech_error(self, monkeypatch):
        old = _FakeServer("old")
        old.eof_read_on(0)
        d = _make_driver_with_streams(old)

        # open_connection itself raises — silent reconnect can't recover.
        async def boom(*a, **k):
            raise OSError("test: controller unreachable")

        monkeypatch.setattr(aero_mod.asyncio, "open_connection", boom)

        with pytest.raises(AerotechError) as exc_info:
            await d._send("PFBK(X)")

        # The thrown error names the original command + makes clear that
        # reconnect was attempted (cause chain preserved).
        assert "PFBK(X)" in str(exc_info.value)
        assert "reconnect failed" in str(exc_info.value).lower()
        # Driver streams torn down — next caller hits the "Not connected"
        # path instead of trying to write on a dead socket.
        assert d._reader is None
        assert d._writer is None

    @pytest.mark.asyncio
    async def test_only_one_retry_attempt(self, monkeypatch):
        """If the freshly-reconnected socket ALSO returns EOF on the
        retried command, we surface the error — we do NOT retry twice."""
        old = _FakeServer("old")
        old.eof_read_on(0)
        new = _FakeServer("new")
        # ACK + ENABLE succeed, but the retried PFBK gets EOF too.
        new.queue_response("%")
        new.queue_response("%")
        new.eof_read_on(2)  # 0=ACK, 1=ENABLE, 2=retried PFBK → EOF

        d = _make_driver_with_streams(old)
        # Only one fake post-reconnect — if the driver tried to reconnect
        # again, open_connection would raise StopIteration → OSError.
        _install_open_connection(monkeypatch, [new])

        with pytest.raises((ConnectionResetError, AerotechError)):
            await d._send("PFBK(X)")
        # ACK + ENABLE + PFBK retry — 3 commands sent to the new socket,
        # no fourth-command attempt against any later server.
        assert new.sent == ["ACKNOWLEDGEALL", "ENABLE X", "PFBK(X)"]

    @pytest.mark.asyncio
    async def test_reconnect_refused_when_axes_present_empty(self, monkeypatch):
        """Pre-connect EOF: ``_silent_reconnect`` returns False because
        there's no cached ENABLE state to restore. We don't half-init
        the controller."""
        old = _FakeServer("old")
        old.eof_read_on(0)
        d = _make_driver_with_streams(old)
        d._axes_present = []  # never finished a real connect
        # Provision a fake just in case — the test asserts it's never used.
        spare = _FakeServer("spare")
        _install_open_connection(monkeypatch, [spare])

        with pytest.raises(AerotechError):
            await d._send("PFBK(X)")
        assert spare.sent == []  # reconnect path never even opened a socket
