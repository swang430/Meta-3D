"""PROPSIM F64 calibration-tone driver tests.

Pin the 5 methods that bridge the path-loss / QZ / pattern services to real
PROPSIM hardware:
  - get_calibration_tone_capabilities()      — license-aware declaration
  - set_calibration_tone(freq, power, port)  — D path (Internal Interference Gen)
  - stop_calibration_tone()
  - set_passthrough_mode()                   — B path (calibration bypass)
  - clear_passthrough_mode()

We mock the PyVISA resource so the tests run hardware-free; the assertions
target the exact SCPI strings the driver sends, which is the contract real
PROPSIM hardware will execute.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.channel_emulator import CalibrationToneCapability
from app.hal.propsim_f64 import F64BypassMode, RealPropsimF64Driver


_SENTINEL = object()


def _make_driver(*, has_interference_generator=_SENTINEL):
    """Build a driver with a mocked VISA resource so SCPI writes / queries
    are captured but never go on the wire.

    We also patch the driver's _write/_query template methods directly so the
    base-class transport wrapper (which does asyncio.to_thread on the visa
    resource) doesn't try to coroutine-wrap our MagicMock. The visa_mock
    itself stays as the spy: every _write delegates to visa.write, every
    _query delegates to visa.query, so test assertions still work.

    has_interference_generator semantics:
      - omitted (sentinel) → no config key → driver state is None (probe path).
                              In tests for tone behavior we then set it via
                              `drv.has_interference_generator = True` to bypass
                              probing (no real connect happens).
      - True/False         → explicit config override (skips probe).
    """
    cfg: dict = {}
    if has_interference_generator is not _SENTINEL:
        cfg["has_interference_generator"] = has_interference_generator
    drv = RealPropsimF64Driver("propsim-test", cfg)

    visa_mock = MagicMock()
    visa_mock.query.return_value = '0,"No error"'
    visa_mock.write.return_value = None
    drv._visa_resource = visa_mock

    # Bypass base-class transport wrapper — call the visa mock directly,
    # async-wrap with a trivial coroutine. Driver code only awaits, doesn't
    # care about the underlying transport mechanics in tests.
    async def _async_write(cmd, timeout=None):
        visa_mock.write(cmd)

    async def _async_query(cmd, timeout=None):
        return visa_mock.query(cmd)

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    return drv, visa_mock


def _writes(visa_mock):
    """Return the list of SCPI strings the driver wrote, in order."""
    return [call.args[0] for call in visa_mock.write.call_args_list]


# ============================================================================
# Capability declaration (license-aware)
# ============================================================================

class TestGetCalibrationToneCapabilities:

    def test_with_interference_license_declares_both_paths(self):
        drv, _ = _make_driver(has_interference_generator=True)
        caps = drv.get_calibration_tone_capabilities()
        assert CalibrationToneCapability.INTERNAL_CW_GENERATOR in caps
        assert CalibrationToneCapability.PASSTHROUGH_ONLY in caps
        # D first → service prefers it
        assert caps[0] == CalibrationToneCapability.INTERNAL_CW_GENERATOR

    def test_without_interference_license_only_passthrough(self):
        drv, _ = _make_driver(has_interference_generator=False)
        caps = drv.get_calibration_tone_capabilities()
        assert caps == [CalibrationToneCapability.PASSTHROUGH_ONLY]

    def test_default_config_no_license(self):
        """Conservative default: chambers without explicit config get B path
        only (always supported via calibration bypass)."""
        drv = RealPropsimF64Driver("propsim-test", {})
        drv._visa_resource = MagicMock()
        caps = drv.get_calibration_tone_capabilities()
        assert caps == [CalibrationToneCapability.PASSTHROUGH_ONLY]


# ============================================================================
# D path — set_calibration_tone / stop_calibration_tone
# ============================================================================

class TestSetCalibrationTone:

    @pytest.mark.asyncio
    async def test_sends_full_interference_scpi_sequence(self):
        drv, visa = _make_driver(has_interference_generator=True)
        ok = await drv.set_calibration_tone(
            frequency_hz=3500e6, power_dbm=-20.0, ce_port="B1.1",
        )
        assert ok is True
        sent = _writes(visa)
        # 5-step SCPI sequence per §20.4.9
        # 0. (idempotent) try REMove first — may succeed on retry, fine here
        # 1. ADD with type=2 (CW) on output 1 (parsed from "B1.1")
        assert any("OUTPut:INTERFerence:ADD 1,ce_sa_cal_tone,2" in s for s in sent), sent
        # 2. Constant-power strategy (1)
        assert any("OUTPut:INTERFerence:STRATegy:SET ce_sa_cal_tone,1" in s for s in sent)
        # 3. Frequency in MHz (3500.0)
        assert any("OUTPut:INTERFerence:FREQuency:SET ce_sa_cal_tone,3500" in s for s in sent)
        # 4. Power in dBm (-20.0)
        assert any("OUTPut:INTERFerence:POWer:SET ce_sa_cal_tone,-20" in s for s in sent)
        # 5. Enable
        assert any("OUTPut:INTERFerence:STatus ce_sa_cal_tone,1" in s for s in sent)

        assert drv._cal_tone_active is True

    @pytest.mark.asyncio
    async def test_ce_port_pure_int_passed_through(self):
        drv, visa = _make_driver(has_interference_generator=True)
        await drv.set_calibration_tone(3500e6, -20.0, ce_port="7")
        sent = _writes(visa)
        assert any("OUTPut:INTERFerence:ADD 7," in s for s in sent)

    @pytest.mark.asyncio
    async def test_ce_port_none_defaults_to_output_1(self):
        drv, visa = _make_driver(has_interference_generator=True)
        await drv.set_calibration_tone(3500e6, -20.0, ce_port=None)
        sent = _writes(visa)
        assert any("OUTPut:INTERFerence:ADD 1," in s for s in sent)

    @pytest.mark.asyncio
    async def test_ce_port_dotted_notation_parsed(self):
        """ETSL convention: B1.3 → output 3."""
        drv, visa = _make_driver(has_interference_generator=True)
        await drv.set_calibration_tone(3500e6, -20.0, ce_port="A2.5")
        sent = _writes(visa)
        assert any("OUTPut:INTERFerence:ADD 5," in s for s in sent)

    @pytest.mark.asyncio
    async def test_no_license_returns_false_without_scpi(self):
        """has_interference_generator=False → reject early, don't touch SCPI."""
        drv, visa = _make_driver(has_interference_generator=False)
        ok = await drv.set_calibration_tone(3500e6, -20.0, ce_port="B1.1")
        assert ok is False
        # No INTERFerence SCPI written
        sent = _writes(visa)
        assert not any("INTERFerence" in s for s in sent)

    @pytest.mark.asyncio
    async def test_no_visa_resource_returns_false(self):
        drv = RealPropsimF64Driver("propsim-test", {"has_interference_generator": True})
        # _visa_resource is None
        ok = await drv.set_calibration_tone(3500e6, -20.0, ce_port="B1.1")
        assert ok is False

    @pytest.mark.asyncio
    async def test_idempotent_retry_removes_stale_id_first(self):
        """Calling set_calibration_tone twice should not fail on second call
        even though id is in use — driver REMoves first, then re-ADDs."""
        drv, visa = _make_driver(has_interference_generator=True)
        await drv.set_calibration_tone(3500e6, -20.0, ce_port="1")
        await drv.set_calibration_tone(3700e6, -15.0, ce_port="1")
        sent = _writes(visa)
        # At least 2 REMove + 2 ADD
        assert sum(1 for s in sent if "INTERFerence:REMove" in s) >= 2
        assert sum(1 for s in sent if "INTERFerence:ADD 1," in s) >= 2

    @pytest.mark.asyncio
    async def test_failure_mid_sequence_clears_state(self):
        """SCPI write fails mid-sequence → driver should attempt cleanup
        (REMove the partially-added id) so next call starts clean."""
        drv, visa = _make_driver(has_interference_generator=True)
        # Fail on FREQuency:SET (mid-sequence)
        call_count = {"i": 0}
        def _write_with_failure(cmd):
            call_count["i"] += 1
            if "FREQuency:SET" in cmd:
                raise RuntimeError("simulated SCPI timeout")
            return None
        visa.write.side_effect = _write_with_failure

        ok = await drv.set_calibration_tone(3500e6, -20.0, ce_port="1")
        assert ok is False
        assert drv._cal_tone_active is False


class TestStopCalibrationTone:

    @pytest.mark.asyncio
    async def test_disable_then_remove(self):
        drv, visa = _make_driver(has_interference_generator=True)
        # Pretend a tone is active first
        await drv.set_calibration_tone(3500e6, -20.0, ce_port="1")
        visa.write.reset_mock()

        ok = await drv.stop_calibration_tone()
        assert ok is True
        sent = _writes(visa)
        # Disable then remove
        assert any("OUTPut:INTERFerence:STatus ce_sa_cal_tone,0" in s for s in sent)
        assert any("OUTPut:INTERFerence:REMove ce_sa_cal_tone" in s for s in sent)
        assert drv._cal_tone_active is False

    @pytest.mark.asyncio
    async def test_safe_when_no_tone_was_active(self):
        """Calling stop without a prior set should not blow up — REMove of
        non-existent id raises -200, we ignore and continue."""
        drv, visa = _make_driver(has_interference_generator=True)
        ok = await drv.stop_calibration_tone()
        assert ok is True


class TestCalibrationToneFailLoud:
    """Codex #202 R10 P2: SCPI 拒绝只进错误队列不抛异常, 原 _check_errors
    只 log → set/stop 恒 True 假成功 (set 假成功 = SA 读噪声本底路损全错;
    stop 假成功 = 残留 tone 且证书 warnings 干净)。改 _first_error 门。"""

    def _err_queue_after_drain(self, visa, errors):
        """drain 先吃 stale 至 clean, 之后写序列产生 errors 队列。

        实现: SYST:ERR? 应答序列 = [clean(drain 停止)] + errors + clean...
        """
        q = ['0,"No error"'] + list(errors)

        def _q(cmd):
            if cmd == "SYST:ERR?":
                return q.pop(0) if q else '0,"No error"'
            return '0,"No error"'

        visa.query.side_effect = _q

    @pytest.mark.asyncio
    async def test_set_rejected_returns_false_and_cleans_up(self):
        """写序列被拒 (-113 进队列) → False + REMove 清理 + active=False。"""
        drv, visa = _make_driver(has_interference_generator=True)
        self._err_queue_after_drain(visa, ['-113,"Undefined header"'])
        ok = await drv.set_calibration_tone(3500e6, -20.0, ce_port="1")
        assert ok is False
        assert drv._cal_tone_active is False
        assert "-113" in (drv._last_error or "")
        # 失败清理: 门后又发了一次 REMove (开头幂等 REMove + 失败 REMove = 2)
        removes = [s for s in _writes(visa) if "REMove" in s]
        assert len(removes) == 2, _writes(visa)

    @pytest.mark.asyncio
    async def test_stop_rejected_while_active_returns_false_keeps_flag(self):
        """tone 真活跃时停止被拒 → False 且 active 保持 (R8 被拒状态不动同族,
        标'可能仍在发')。"""
        drv, visa = _make_driver(has_interference_generator=True)
        await drv.set_calibration_tone(3500e6, -20.0, ce_port="1")
        assert drv._cal_tone_active is True
        self._err_queue_after_drain(visa, ['-200,"Execution error"'])
        ok = await drv.stop_calibration_tone()
        assert ok is False
        assert drv._cal_tone_active is True  # 未清 — F64 可能仍在发
        assert "-200" in (drv._last_error or "")

    @pytest.mark.asyncio
    async def test_stop_inactive_with_expected_200_still_true(self):
        """防御性清理 (从未启动) 场景 REMove 报 -200 是预期 — 不假警。"""
        drv, visa = _make_driver(has_interference_generator=True)
        assert drv._cal_tone_active is False
        self._err_queue_after_drain(visa, ['-200,"Execution error;REMove no such id"'])
        ok = await drv.stop_calibration_tone()
        assert ok is True

    @pytest.mark.asyncio
    async def test_stop_write_exception_returns_false_keeps_flag(self):
        """写异常 (仪器失联) → False 且 active 保持 (tone 状态未知)。"""
        drv, visa = _make_driver(has_interference_generator=True)
        await drv.set_calibration_tone(3500e6, -20.0, ce_port="1")
        visa.write.side_effect = RuntimeError("VISA session dropped")
        ok = await drv.stop_calibration_tone()
        assert ok is False
        assert drv._cal_tone_active is True
        assert "write failed" in (drv._last_error or "")


# ============================================================================
# B path — passthrough via calibration bypass
# ============================================================================

class TestPassthroughMode:

    @pytest.mark.asyncio
    async def test_set_passthrough_drives_calibration_bypass(self):
        """B path = DIAG:SIMU:MODEL:STATIC 3 (calibration bypass: equal gain,
        equal delay, zero phase across all channels)."""
        drv, visa = _make_driver(has_interference_generator=False)  # B path doesn't need license
        ok = await drv.set_passthrough_mode(ce_port="B1.1", ce_input_port="A1")
        assert ok is True
        sent = _writes(visa)
        assert "DIAG:SIMU:MODEL:STATIC 3" in sent
        assert drv._passthrough_active is True
        assert drv._bypass_mode == F64BypassMode.CALIBRATION

    @pytest.mark.asyncio
    async def test_clear_passthrough_disables_bypass(self):
        drv, visa = _make_driver(has_interference_generator=False)
        await drv.set_passthrough_mode()
        visa.write.reset_mock()

        ok = await drv.clear_passthrough_mode()
        assert ok is True
        sent = _writes(visa)
        assert "DIAG:SIMU:MODEL:STATIC 0" in sent
        assert drv._passthrough_active is False
        assert drv._bypass_mode == F64BypassMode.DISABLED

    @pytest.mark.asyncio
    async def test_passthrough_works_without_license(self):
        """B path is the fallback for chambers without Internal Interference
        Generator option — must always be available."""
        drv, _ = _make_driver(has_interference_generator=False)
        caps = drv.get_calibration_tone_capabilities()
        assert CalibrationToneCapability.PASSTHROUGH_ONLY in caps
        ok = await drv.set_passthrough_mode()
        assert ok is True


# ============================================================================
# Startup *OPT? probe — license discovery instead of config declaration
# ============================================================================

class TestOptionsProbe:
    """connect() 启动时推 has_interference_generator (license discovery).

    CAICT 2026-05-13 confirmed F64's ATE Server doesn't implement
    ``*OPT?`` — returns -100 (memory ``project_f64_ate_server_capabilities``).
    F64 now overrides ``_probe_installed_options`` with a feature-probe
    strategy (SYST:INFO? keyword scan + soft per-feature probes).

    Token-shape pinning for the old ``*OPT?`` CSV path moved to
    ``tests/test_f64_license_probe.py`` against the new probe surface.
    The remaining cases here pin the **outcome contract** that must
    survive any future probe replacement: explicit config overrides
    discovery, probe failure doesn't break connect, empty discovery
    means "no license".
    """

    @pytest.mark.asyncio
    async def test_probe_token_match_is_case_insensitive(self):
        drv, visa = _make_driver()
        visa.query.return_value = "k01,foo"  # lower-case

        opts = await drv._probe_installed_options()
        await drv._apply_discovered_capabilities(opts)

        assert drv.has_interference_generator is True

    @pytest.mark.asyncio
    async def test_explicit_config_true_skips_probe_application(self):
        """config explicitly says True → probe still runs (logging) but does
        not override the explicit value, even if discovery returns nothing."""
        drv, visa = _make_driver(has_interference_generator=True)
        assert drv.has_interference_generator is True
        visa.query.return_value = ""  # empty options

        opts = await drv._probe_installed_options()
        await drv._apply_discovered_capabilities(opts)

        # Explicit config wins; probe doesn't downgrade to False
        assert drv.has_interference_generator is True

    @pytest.mark.asyncio
    async def test_explicit_config_false_skips_probe_application(self):
        drv, visa = _make_driver(has_interference_generator=False)
        visa.query.return_value = "K01"  # license actually present

        opts = await drv._probe_installed_options()
        await drv._apply_discovered_capabilities(opts)

        # Explicit False overrides discovered True (mock/CI scenario)
        assert drv.has_interference_generator is False

    @pytest.mark.asyncio
    async def test_probe_failure_is_tolerated(self):
        """Instrument that doesn't implement the probe SCPIs must not
        break connect."""
        drv, visa = _make_driver()

        async def _query_raises(cmd, timeout=None):
            raise RuntimeError("simulated NAK")

        drv._query = _query_raises  # type: ignore[assignment]

        opts = await drv._probe_installed_options()
        await drv._apply_discovered_capabilities(opts)

        assert opts == []
        # Probe failed → no token matched → capability stays False (the
        # "not licensed" outcome). Conservative: better deny than assume.
        assert drv.has_interference_generator is False


class TestParseOptionsResponse:
    """Base helper coverage — parse_options_response on edge cases."""

    def test_parses_simple_csv(self):
        from app.hal.base import InstrumentDriver
        assert InstrumentDriver._parse_options_response("K01,K02") == ["K01", "K02"]

    def test_strips_quotes_and_whitespace(self):
        from app.hal.base import InstrumentDriver
        assert InstrumentDriver._parse_options_response(
            '  "K01" , "K02"  ,"INT-GEN"'
        ) == ["K01", "K02", "INT-GEN"]

    def test_drops_empty_tokens(self):
        from app.hal.base import InstrumentDriver
        assert InstrumentDriver._parse_options_response("K01,,K02,") == ["K01", "K02"]

    def test_empty_response_returns_empty_list(self):
        from app.hal.base import InstrumentDriver
        assert InstrumentDriver._parse_options_response("") == []
        assert InstrumentDriver._parse_options_response("   ") == []
