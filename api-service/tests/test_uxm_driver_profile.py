"""RealUxmDriver — command-profile graceful-skip tests.

Addresses codex P1 on PR #10 (f99c9d9): when ``self._cmds`` is the
``UxmLteNrIratProfile``, several command templates are deliberately
``None`` (the IRAT app on E7515B doesn't surface those mnemonics).
Driver methods that used to call ``self._cmds.X.format(...)`` directly
crashed with ``AttributeError: 'NoneType' object has no attribute
'format'``. ``RealUxmDriver._cmd()`` centralises the skip-or-format
decision; callers that opt in to graceful skip get ``None`` when the
profile doesn't expose the command.

These tests exercise the helper in isolation + verify ``set_cell_config``
no longer crashes on an IRAT profile with optional fields. We don't
need a live UXM session — the helper is pure-Python and the config
path's SCPI sends are intercepted via a fake ``_visa_session``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)


@pytest.fixture
def driver_5g():
    """Driver pre-configured with the 5G_NR_Test profile (legacy default)."""
    return RealUxmDriver("uxm-5g", {"ip": "10.0.0.1"})


@pytest.fixture
def driver_irat():
    """Driver pre-configured with the LTE_NR_IRAT profile via config hint
    (skips the connect-time auto-detect)."""
    return RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})


class TestCmdHelper:
    """``RealUxmDriver._cmd(name, **fmt)``."""

    def test_returns_formatted_when_supported(self, driver_irat):
        # IRAT profile defines CELL_BAND as 'BSE:CONFig:NR5G:{cell}:BAND'.
        result = driver_irat._cmd("CELL_BAND", cell="CELL1")
        assert result == "BSE:CONFig:NR5G:CELL1:BAND"

    def test_returns_none_when_unsupported_in_profile(self, driver_irat):
        # IRAT profile sets CELL_SCS = None (no equivalent in this Test App).
        assert driver_irat._cmd("CELL_SCS", cell="CELL1") is None

    def test_returns_none_when_attribute_missing(self, driver_irat):
        # Attribute doesn't exist on the profile at all.
        assert driver_irat._cmd("DOES_NOT_EXIST", cell="CELL1") is None

    def test_returns_template_unchanged_when_no_kwargs(self, driver_5g):
        # No placeholders to substitute — return template verbatim.
        result = driver_5g._cmd("IDN")
        assert result == "*IDN?"

    def test_5g_profile_resolves_known_commands(self, driver_5g):
        # CELL_DUPLEX exists in 5G_NR_Test profile.
        result = driver_5g._cmd("CELL_DUPLEX", cell="CELL0")
        assert result == "CONFig:NR5G:CELL0:DUPLex"


class TestSetCellConfigGracefulSkip:
    """``set_cell_config`` no longer crashes when running against the
    IRAT profile with config keys the profile doesn't expose. Each
    optional-feature branch should silently skip (logging the reason)
    instead of raising AttributeError."""

    def _wire_fake_visa(self, driver):
        """Replace pyvisa session with a recording mock so SCPI writes are
        captured without going over the network."""
        sess = MagicMock()
        sess.write = MagicMock()
        sess.query = MagicMock(return_value="0")
        sess.timeout = 5000
        driver._visa_session = sess
        return sess

    @pytest.mark.asyncio
    async def test_irat_skips_unsupported_optional_fields(self, driver_irat):
        sess = self._wire_fake_visa(driver_irat)
        # All these are None in UxmLteNrIratProfile — driver must skip
        # each, NOT crash. Mandatory fields (band, bandwidth_mhz, ARFCN)
        # ARE supported and should still be sent.
        ok = await driver_irat.set_cell_config({
            "band": "N78",
            "bandwidth_mhz": 100,
            "duplex": "TDD",          # CELL_DUPLEX = None in IRAT
            "scs_khz": 30,            # CELL_SCS = None in IRAT
            "mimo_layers": 4,         # MIMO_DL_LAYERS = None in IRAT
            "rf_port_dl": "RF1OUT",   # RF_PORT_DL = None in IRAT
            "tdd_pattern": "DDDSU",   # TDD_PATTERN = None in IRAT
            "tdd_period": 5,          # TDD_PERIOD = None in IRAT
            "harq_max_trans": 4,      # HARQ_MAX_TRANS = None in IRAT
            "harq_processes": 16,     # HARQ_PROCESSES = None in IRAT
            "csi_rs_ports": 4,        # CSIRS_PORTS = None in IRAT
            "stat_count": 5000,       # MEAS_TPUT_STAT_COUNT = None in IRAT
        })
        assert ok is True

        # Mandatory commands DID go out (with BSE: prefix, CELL1 default).
        written = [call.args[0] for call in sess.write.call_args_list]
        assert any("BSE:CONFig:NR5G:CELL1:BAND N78" in w for w in written), written
        assert any("BSE:CONFig:NR5G:CELL1:DL:BW 100" in w for w in written), written
        # ARFCN is the auto-filled value for N78 (632628).
        assert any("BSE:CONFig:NR5G:CELL1:DL:ARFCN 632628" in w for w in written), written

        # None of the unsupported-in-IRAT fields produced a write.
        for forbidden in ("DUPLex", "SCS", "MIMO:LAYers", "TDD:PATTern",
                          "HARQ:", "CSIRS:PORTs", "RFSettings:DL:PORT",
                          "BTHRoughput:DL:TSTatistics:COUNt"):
            offending = [w for w in written if forbidden in w]
            assert offending == [], f"IRAT skipped command leaked: {offending}"

    @pytest.mark.asyncio
    async def test_5g_profile_sends_all_optional_fields(self, driver_5g):
        sess = self._wire_fake_visa(driver_5g)
        # Same config — but the 5G_NR_Test profile defines every command,
        # so all writes should fire.
        ok = await driver_5g.set_cell_config({
            "band": "N78",
            "bandwidth_mhz": 100,
            "duplex": "TDD",
            "scs_khz": 30,
            "mimo_layers": 4,
            "tdd_pattern": "DDDSU",
            "harq_max_trans": 4,
        })
        assert ok is True

        written = [call.args[0] for call in sess.write.call_args_list]
        # No BSE: prefix on 5G_NR_Test profile; CELL0 is the default.
        assert any("CONFig:NR5G:CELL0:DUPLex TDD" in w for w in written), written
        assert any("CONFig:NR5G:CELL0:SCS 30" in w for w in written), written
        assert any("CONFig:NR5G:CELL0:PHY:DL:MIMO:LAYers 4" in w for w in written), written
        assert any("CONFig:NR5G:CELL0:TDD:PATTern DDDSU" in w for w in written), written
        assert any("CONFig:NR5G:CELL0:HARQ:MaxTrans 4" in w for w in written), written


class TestProfileSelectedByConfigHint:
    """Sanity: ``config["uxm_profile"]="irat"`` picks IRAT in __init__
    so PRIMARY_CELL etc. take effect before connect()."""

    def test_default_profile_is_5g(self, driver_5g):
        assert driver_5g._cmds is Uxm5GNRTestAppProfile
        assert driver_5g._cell_id == "CELL0"

    def test_irat_hint_picks_irat(self, driver_irat):
        assert driver_irat._cmds is UxmLteNrIratProfile
        assert driver_irat._cell_id == "CELL1"
        assert driver_irat._cmds.HISLIP_INDEX == 2
