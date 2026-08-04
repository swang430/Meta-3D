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
        captured without going over the network.

        P1-19 后 query 必须回显式: IRAT profile 默认开写后回读对账, 恒返
        "0" 会被判 "下发≠生效" fail-loud (这正是对账的职责); 回显最近一次
        对应写入让 "配置已生效" 的 fake 语义成立。"""
        sess = MagicMock()
        written: list[str] = []
        sess.write = MagicMock(side_effect=lambda c: written.append(c.strip()))

        def _echo_query(cmd):
            c = cmd.strip()
            if c == "*OPC?":
                return "1"
            if c.endswith("ACTive:STATe?"):
                return "0"
            base = c.rstrip("?")
            for w in reversed(written):
                if w.startswith(base + " "):
                    return w[len(base) + 1:]
            return "0"

        sess.query = MagicMock(side_effect=_echo_query)
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
        # P1-19: IRAT 带宽值令牌形式 (2026-07-03 实证: 裸 "100" 被拒)
        assert any("BSE:CONFig:NR5G:CELL1:DL:BW BW100" in w for w in written), written
        # ARFCN auto-fill: agent R6 F3 起 N78 fallback = EMQuest 基线 636666。
        assert any("BSE:CONFig:NR5G:CELL1:DL:ARFCN 636666" in w for w in written), written

        # ⚠ P1-33（2026-08-04）：`HARQ:` 与 `CSIRS:PORTs` **已按手册补进 IRAT**，
        #   不再属于"本方言没有"那一档 —— 从禁发清单里移出。
        #   移出后它们该照发，且值形态是手册要的**枚举 token**（下面单独断言）。
        for forbidden in ("DUPLex", "SCS", "MIMO:LAYers", "TDD:PATTern",
                          "RFSettings:DL:PORT",
                          "BTHRoughput:DL:TSTatistics:COUNt"):
            offending = [w for w in written if forbidden in w]
            assert offending == [], f"IRAT skipped command leaked: {offending}"

        # ⭐ 生效端：HARQ 现在会发，且必须发**枚举 token** 不是裸整数
        #   （手册 Range: N1|N2|...；裸 `4` 是旧的无前缀写法留下的错值形态）。
        harq = [w for w in written if "HARQ:" in w]
        assert harq, "HARQ 已补进 IRAT，该发却没发"
        for w in harq:
            tail = w.rsplit(" ", 1)[-1]
            assert tail.startswith("N"), (
                f"HARQ 发的是裸值不是手册枚举 token: {w!r}")

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
        # ⚠ P1-33（2026-08-04）：`TDD:PATTern` / `HARQ:MaxTrans` 这两条
        #   **本来就是编出来的** —— 逐条 grep 厂商手册原件，**0 命中**
        #   （连 `SchedAlgoritm` 的拼写都是错的）。它们从没在真机上工作过：
        #   IRAT 上是 `None`，这里则是发出去等 -113。
        #   按「禁盲试」已置 `None`，所以本门不再断言它们被发出 ——
        #   **断言反过来：编出来的命令一条都不许再发**。
        for fabricated in ("TDD:PATTern", "HARQ:MaxTrans", "PDSCH:SchedAlgoritm",
                           "PDSCH:AMC:ENABle", "CSIRS:PORTs",
                           "BTHRoughput:DL:TSTatistics:COUNt"):
            assert not any(fabricated in w for w in written), (
                f"仍在发手册里不存在的编造命令: {fabricated}")


class TestProfileSelectedByConfigHint:
    """Sanity: ``config["uxm_profile"]="irat"`` picks IRAT in __init__
    so PRIMARY_CELL etc. take effect before connect()."""

    def test_default_profile_is_5g(self, driver_5g):
        # ``isinstance`` not ``is`` — ``_cmds`` is an instance of the
        # profile class (per-driver state), not the class itself.
        assert isinstance(driver_5g._cmds, Uxm5GNRTestAppProfile)
        assert driver_5g._cell_id == "CELL0"

    def test_irat_hint_picks_irat(self, driver_irat):
        assert isinstance(driver_irat._cmds, UxmLteNrIratProfile)
        assert driver_irat._cell_id == "CELL1"
        assert driver_irat._cmds.HISLIP_INDEX == 2
