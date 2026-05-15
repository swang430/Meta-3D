"""P2-2 — canonical ``driver.capabilities: Set[str]`` contract.

The legacy ``has_interference_generator`` (F64) and ``is_single_axis``
(Aerotech) boolean attributes stay alive as backwards-compat aliases —
those tests live in ``test_propsim_calibration_tone.py`` /
``test_aerotech_driver_single_axis.py``. This file pins the **new**
contract that P1-1 will consume:

  - Every driver exposes ``self.capabilities: Set[str]`` (single source
    of truth for "what does this driver expose right now").
  - Token vocabulary lives in ``app/hal/capabilities.py``; values
    outside ``KNOWN_CAPABILITIES`` are still accepted but log a warning.
  - F64 / Aerotech populate canonical tokens in lock-step with their
    legacy boolean attributes — they cannot drift.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.hal.capabilities import (
    CE_INTERFERENCE_GENERATOR,
    CE_USER_ALIGNMENT,
    KNOWN_CAPABILITIES,
    POS_DUAL_AXIS_AZEL,
    POS_SINGLE_AXIS_AZ,
)
from app.hal.propsim_f64 import RealPropsimF64Driver


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

class TestKnownCapabilities:
    """The canonical token set is the spec; drift is the bug. Pin both
    membership and naming convention so a future PR that adds a token
    without registering it here fails this test."""

    def test_vocabulary_is_namespaced(self):
        """Every token must be ``<prefix>.<name>`` — no nested dots,
        no missing prefix."""
        for tok in KNOWN_CAPABILITIES:
            assert "." in tok, tok
            assert tok.count(".") == 1, tok
            prefix, name = tok.split(".")
            assert prefix and name, tok

    def test_currently_registered_tokens(self):
        """Snapshot of the vocabulary at P2-2 landing time. Update this
        list when adding a new token AND when promoting an unused one
        out of the vocabulary — keeps the registry honest."""
        assert KNOWN_CAPABILITIES == {
            CE_INTERFERENCE_GENERATOR,
            CE_USER_ALIGNMENT,
            POS_SINGLE_AXIS_AZ,
            POS_DUAL_AXIS_AZEL,
        }


# ---------------------------------------------------------------------------
# DriverBase: capabilities set + add/remove helpers
# ---------------------------------------------------------------------------

class TestDriverBaseCapabilitySet:
    def _drv(self):
        # Use F64 as the concrete driver — base is abstract. The set
        # behavior under test is inherited unchanged.
        return RealPropsimF64Driver("base-test", {})

    def test_empty_by_default(self):
        assert self._drv().capabilities == set()

    def test_add_canonical_token_adds(self):
        drv = self._drv()
        drv._add_capability(CE_USER_ALIGNMENT)
        assert CE_USER_ALIGNMENT in drv.capabilities

    def test_add_is_idempotent(self):
        drv = self._drv()
        drv._add_capability(CE_USER_ALIGNMENT)
        drv._add_capability(CE_USER_ALIGNMENT)
        # Set semantics — exactly one entry, no duplicate-add side effect.
        assert drv.capabilities == {CE_USER_ALIGNMENT}

    def test_remove_clears(self):
        drv = self._drv()
        drv._add_capability(CE_USER_ALIGNMENT)
        drv._remove_capability(CE_USER_ALIGNMENT)
        assert CE_USER_ALIGNMENT not in drv.capabilities

    def test_remove_missing_token_is_noop(self):
        drv = self._drv()
        # discard()-backed: removing what's not there must not raise.
        drv._remove_capability(CE_USER_ALIGNMENT)
        assert drv.capabilities == set()

    def test_non_canonical_token_warns_but_adds(self, caplog):
        """A typo or forgotten registration must surface in logs (so
        the drift is visible during first-call debugging), but the add
        must still succeed — we don't want a typo to silently disable
        a capability the driver actually probed positive on."""
        drv = self._drv()
        with caplog.at_level("WARNING"):
            drv._add_capability("ce.not_a_real_token")
        assert "ce.not_a_real_token" in drv.capabilities
        # Warning text must name the bad token so it's grep-able.
        assert any(
            "non-canonical" in r.message and "ce.not_a_real_token" in r.message
            for r in caplog.records
        ), [r.message for r in caplog.records]


# ---------------------------------------------------------------------------
# F64 — capability mirroring of has_interference_generator
# ---------------------------------------------------------------------------

class TestF64CapabilityMirroring:
    """The legacy ``has_interference_generator`` flag and the canonical
    ``ce.interference_generator`` token must agree at all times — drift
    would mean two sources of truth and break P1-1 pre-flight."""

    def test_explicit_true_populates_token(self):
        drv = RealPropsimF64Driver("f64-test", {"has_interference_generator": True})
        assert drv.has_interference_generator is True
        assert CE_INTERFERENCE_GENERATOR in drv.capabilities

    def test_explicit_false_does_not_populate_token(self):
        drv = RealPropsimF64Driver("f64-test", {"has_interference_generator": False})
        assert drv.has_interference_generator is False
        assert CE_INTERFERENCE_GENERATOR not in drv.capabilities

    def test_unprobed_default_does_not_populate_token(self):
        """No config + no connect → unprobed (None). Capability set is
        empty until probe lands."""
        drv = RealPropsimF64Driver("f64-test", {})
        assert drv.has_interference_generator is None
        assert CE_INTERFERENCE_GENERATOR not in drv.capabilities

    @pytest.mark.asyncio
    async def test_probe_finds_K01_populates_token(self):
        drv = RealPropsimF64Driver("f64-test", {})
        await drv._apply_discovered_capabilities(["K01", "K02"])
        assert drv.has_interference_generator is True
        assert CE_INTERFERENCE_GENERATOR in drv.capabilities

    @pytest.mark.asyncio
    async def test_probe_misses_K01_removes_token(self):
        """Re-probe that comes back negative must clear the token —
        otherwise a unit that lost its license between probes (e.g. F64
        with the dongle removed) would still appear capable."""
        drv = RealPropsimF64Driver("f64-test", {})
        # Pre-seed as if a previous probe had flipped it on.
        drv._add_capability(CE_INTERFERENCE_GENERATOR)
        await drv._apply_discovered_capabilities([])  # empty *OPT?
        assert drv.has_interference_generator is False
        assert CE_INTERFERENCE_GENERATOR not in drv.capabilities

    @pytest.mark.asyncio
    async def test_explicit_override_skips_probe_path(self):
        """Construction-time explicit value short-circuits the probe;
        capability set should still reflect the explicit declaration
        (seeded in __init__), not get cleared by an empty probe."""
        drv = RealPropsimF64Driver(
            "f64-test", {"has_interference_generator": True},
        )
        assert CE_INTERFERENCE_GENERATOR in drv.capabilities
        await drv._apply_discovered_capabilities([])
        # Explicit override path returns early; token must persist.
        assert CE_INTERFERENCE_GENERATOR in drv.capabilities


# ---------------------------------------------------------------------------
# Aerotech — single/dual axis capability mirroring
# ---------------------------------------------------------------------------

class TestF64UserAlignmentCapability:
    """``ce.user_alignment`` is set IFF the F64 has an active user
    alignment loaded — runtime state, not vocabulary placeholder.
    These tests cover the helper directly so they don't have to
    simulate the full connect() handshake; the connect path itself
    is already covered by the F64 connection tests.

    Pre-fix, the token sat in KNOWN_CAPABILITIES but no driver path
    ever wrote it — P1-1 pre-flight would reject every step needing
    user alignment, even on an active F64 (Codex P2 on PR #21).
    """

    def _drv(self):
        return RealPropsimF64Driver("f64-align", {})

    def test_no_active_alignment_does_not_set_token(self):
        drv = self._drv()
        drv._active_alignment = None
        drv._update_user_alignment_capability()
        assert CE_USER_ALIGNMENT not in drv.capabilities

    def test_active_alignment_with_name_sets_token(self):
        drv = self._drv()
        drv._active_alignment = {
            "alignment_name": "caict-bench-2026",
            "loaded_at": "2026-05-15T10:00:00Z",
        }
        drv._update_user_alignment_capability()
        assert CE_USER_ALIGNMENT in drv.capabilities

    def test_active_alignment_missing_name_does_not_set_token(self):
        """A status row with no alignment_name (F64 returns an empty
        struct in some edge states) should not falsely register the
        token — the populate helper guards on the name being truthy."""
        drv = self._drv()
        drv._active_alignment = {"loaded_at": "2026-05-15T10:00:00Z"}
        drv._update_user_alignment_capability()
        assert CE_USER_ALIGNMENT not in drv.capabilities

    def test_helper_is_idempotent(self):
        drv = self._drv()
        drv._active_alignment = {"alignment_name": "x"}
        drv._update_user_alignment_capability()
        drv._update_user_alignment_capability()
        assert drv.capabilities == {CE_USER_ALIGNMENT}

    def test_token_cleared_when_alignment_drops(self):
        """A re-probe after an alignment was unloaded should clear
        the token — otherwise the GUI / P1-1 pre-flight would still
        green-light a step that needs alignment after operator
        explicitly cleared it."""
        drv = self._drv()
        drv._active_alignment = {"alignment_name": "x"}
        drv._update_user_alignment_capability()
        assert CE_USER_ALIGNMENT in drv.capabilities

        drv._active_alignment = None
        drv._update_user_alignment_capability()
        assert CE_USER_ALIGNMENT not in drv.capabilities


class TestAerotechCapabilityMirroring:
    """Drive Aerotech's axis-discovery path via mocked probe results and
    verify the canonical pos.* tokens land in the capability set."""

    @pytest.fixture
    def driver(self):
        from app.hal.aerotech_positioner import RealAerotechDriver
        return RealAerotechDriver(
            "aero-test",
            {"ip_address": "127.0.0.1", "port": 8000,
             "azimuth_axis": "X", "elevation_axis": "Y"},
        )

    @pytest.mark.asyncio
    async def test_dual_axis_populates_dual_token(self, driver):
        # Mock the probe to find both axes; bypass the actual TCP
        # connect by patching the low-level helpers.
        from app.hal.base import InstrumentStatus
        driver._set_status = MagicMock()
        driver._clear_error = MagicMock()
        driver._enable_tcp_keepalive = MagicMock()

        async def fake_probe(axis):
            return axis in {"X", "Y"}

        async def fake_send(cmd, **kw):
            return None

        async def fake_query_value(cmd):
            return 0.0

        async def fake_open(host, port):
            return MagicMock(), MagicMock()

        with patch("asyncio.open_connection", side_effect=fake_open), \
             patch.object(driver, "_probe_axis", side_effect=fake_probe), \
             patch.object(driver, "_send", side_effect=fake_send), \
             patch.object(driver, "_query_value", side_effect=fake_query_value):
            await driver.connect()

        assert driver.is_single_axis is False
        assert POS_DUAL_AXIS_AZEL in driver.capabilities
        assert POS_SINGLE_AXIS_AZ not in driver.capabilities

    @pytest.mark.asyncio
    async def test_single_axis_populates_single_token(self, driver):
        driver._set_status = MagicMock()
        driver._clear_error = MagicMock()
        driver._enable_tcp_keepalive = MagicMock()

        async def fake_probe(axis):
            return axis == "X"  # Y missing → single-axis controller

        async def fake_send(cmd, **kw):
            return None

        async def fake_query_value(cmd):
            return 0.0

        async def fake_open(host, port):
            return MagicMock(), MagicMock()

        with patch("asyncio.open_connection", side_effect=fake_open), \
             patch.object(driver, "_probe_axis", side_effect=fake_probe), \
             patch.object(driver, "_send", side_effect=fake_send), \
             patch.object(driver, "_query_value", side_effect=fake_query_value):
            await driver.connect()

        assert driver.is_single_axis is True
        assert POS_SINGLE_AXIS_AZ in driver.capabilities
        assert POS_DUAL_AXIS_AZEL not in driver.capabilities
