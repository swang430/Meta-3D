"""HAL init — pre-flight TCP reachability probe.

The pre-#15 problem: when a configured instrument was unreachable
(wrong subnet, instrument off, firewall blocking), HAL init blocked
~10 s per instrument waiting for the underlying VISA/socket open to
time out. With 5 categories that's a 60-second cold start, and the
operator can't tell what's wrong until the readiness report finally
prints.

The fix: ``tcp_preflight()`` probes the configured ``(ip, port)`` with
a 1-second timeout before instantiating each real driver. If the host
isn't reachable, we skip ``driver.connect()`` entirely and write a
``preflight: ...`` row in the readiness report — operator sees the
problem in seconds, with the specific failure reason (SYN timeout vs
DNS fail vs no route).

These tests pin three contracts:
  1. Successful TCP connect → preflight returns (True, None).
  2. ConnectionRefused → (True, None) — host is alive, port is closed
     (VISA may still connect on a different port via HiSLIP/VXI-11).
  3. Timeout / OSError → (False, reason) — host is not reachable.
"""
from __future__ import annotations

import asyncio
import pytest

from app.services import instrument_hal_service as hal_mod
from app.services.instrument_hal_service import (
    detect_preflight_trustworthy,
    tcp_preflight,
)


class _StubWriter:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class TestPreflightSuccess:
    @pytest.mark.asyncio
    async def test_successful_open_returns_alive(self, monkeypatch):
        called: dict[str, object] = {}

        async def fake_open(host, port):
            called["host"] = host
            called["port"] = port
            return object(), _StubWriter()

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        alive, reason = await tcp_preflight("192.168.0.100", 5025, timeout_s=1.0)
        assert alive is True
        assert reason is None
        assert called == {"host": "192.168.0.100", "port": 5025}

    @pytest.mark.asyncio
    async def test_writer_is_closed_after_probe(self, monkeypatch):
        """Preflight must not leak file descriptors — close the writer
        after the SYN succeeds, otherwise we'd hold a TCP session open
        on every probed instrument every startup."""
        writer = _StubWriter()

        async def fake_open(host, port):
            return object(), writer

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        await tcp_preflight("192.168.0.100", 5025)
        assert writer.closed is True


class TestPreflightConnectionRefused:
    @pytest.mark.asyncio
    async def test_connection_refused_is_treated_as_alive(self, monkeypatch):
        """RST means the host is up, just not listening on that port.
        Driver may legitimately connect on a different port (VISA
        HiSLIP at 4880 when we preflighted 5025). Pre-flight must NOT
        block this case — otherwise we lose every HiSLIP instrument."""
        async def fake_open(host, port):
            raise ConnectionRefusedError("test: RST from peer")

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        alive, reason = await tcp_preflight("192.168.0.100", 5025)
        assert alive is True
        assert reason is None


class TestPreflightDead:
    @pytest.mark.asyncio
    async def test_syn_timeout_returns_dead_with_specific_reason(self, monkeypatch):
        async def fake_open(host, port):
            await asyncio.sleep(10)  # past the 0.05s timeout below
            return object(), _StubWriter()

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        alive, reason = await tcp_preflight("10.255.255.1", 5025, timeout_s=0.05)
        assert alive is False
        assert reason is not None
        assert "SYN timeout" in reason
        # The reason includes the host so the readiness report can
        # explain WHICH instrument failed without the operator
        # cross-referencing the log lines.
        assert "10.255.255.1" in reason

    @pytest.mark.asyncio
    async def test_oserror_returns_dead_with_specific_reason(self, monkeypatch):
        async def fake_open(host, port):
            # ENETUNREACH-like error — host is on a network we can't route to.
            raise OSError("Network is unreachable")

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        alive, reason = await tcp_preflight("10.255.255.1", 5025)
        assert alive is False
        assert "OSError" in (reason or "")
        assert "Network is unreachable" in (reason or "")


class TestPreflightCanary:
    """P1-15: ``detect_preflight_trustworthy`` is the negative control that
    keeps tcp_preflight honest. It probes RFC 5737 TEST-NET canaries, which can
    only be dead on a correct network. If a canary is alive, a transparent
    proxy / VPN / blackhole gateway is answering for unroutable addresses, so
    every preflight "alive" is meaningless → the verdict must be 'untrustworthy'.
    """

    @pytest.mark.asyncio
    async def test_all_canaries_dead_is_trustworthy(self, monkeypatch):
        """Honest LAN: every canary times out / no-route → trustworthy=True."""
        async def fake_open(host, port):
            raise OSError("Network is unreachable")

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        assert await detect_preflight_trustworthy(timeout_s=0.05) is True

    @pytest.mark.asyncio
    async def test_any_canary_alive_is_untrustworthy(self, monkeypatch):
        """Lying network (proxy/VPN/captive): a canary to an unroutable
        TEST-NET address 'connects' → trustworthy=False. This is the exact
        field symptom — a VPN accepted connects to every IP, so all subnets
        showed 可达 with no instruments present."""
        async def fake_open(host, port):
            return object(), _StubWriter()

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        assert await detect_preflight_trustworthy(timeout_s=0.05) is False

    @pytest.mark.asyncio
    async def test_connection_refused_canary_is_also_untrustworthy(self, monkeypatch):
        """RST from a TEST-NET canary still means *something* answered for an
        address that can't exist (tcp_preflight treats refused as alive), so the
        network is lying just the same → untrustworthy."""
        async def fake_open(host, port):
            raise ConnectionRefusedError("RST")

        monkeypatch.setattr(hal_mod.asyncio, "open_connection", fake_open)
        assert await detect_preflight_trustworthy(timeout_s=0.05) is False
