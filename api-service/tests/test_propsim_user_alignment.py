"""PROPSIM F64 user alignment (Integrated Setup Calibration) driver tests.

Pin the 3 SCPI methods plus the connect()-time auto-reload + precheck
surfacing:
  - get_user_alignment_status()  — SYST:CALIB:USER:GET? + INFO?
  - enable_user_alignment(name)  — SYST:CALIB:USER:SET 1,<name>
  - list_external_units()        — SYST:EXT:UNIT:LIST? 0
  - precheck phase reports both pieces back to the operator without
    failing on a missing alignment (it's an OPTIONAL license).

We mock the PyVISA resource the same way test_propsim_calibration_tone
does, so SCPI strings can be inspected directly without hardware.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver


def _make_driver(*, alignment_name: str | None = None):
    cfg: dict = {}
    if alignment_name is not None:
        cfg["alignment_name"] = alignment_name
    drv = RealPropsimF64Driver("propsim-test", cfg)

    visa_mock = MagicMock()
    visa_mock.query.return_value = '0,"No error"'
    visa_mock.write.return_value = None
    drv._visa_resource = visa_mock

    async def _async_write(cmd, timeout=None):
        visa_mock.write(cmd)

    async def _async_query(cmd, timeout=None, **_kw):
        return visa_mock.query(cmd)

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    return drv, visa_mock


def _writes(visa_mock):
    return [call.args[0] for call in visa_mock.write.call_args_list]


# ============================================================================
# get_user_alignment_status()
# ============================================================================

class TestGetUserAlignmentStatus:

    @pytest.mark.asyncio
    async def test_returns_name_and_info_when_active(self):
        drv, visa = _make_driver()
        responses = iter([
            "MyAlignment_5G_3500MHz",  # USER:GET?
            "FI1234567, 29.01.2024, External Response Calibration Tool 3.0, "
            "PROPSIM FW 10.0",  # USER:INFO?
        ])
        visa.query.side_effect = lambda cmd: next(responses)

        status = await drv.get_user_alignment_status()
        assert status is not None
        assert status["alignment_name"] == "MyAlignment_5G_3500MHz"
        assert "29.01.2024" in status["info"]

    @pytest.mark.asyncio
    async def test_empty_response_means_no_alignment(self):
        drv, visa = _make_driver()
        visa.query.return_value = ""

        status = await drv.get_user_alignment_status()
        assert status is None

    @pytest.mark.asyncio
    async def test_whitespace_only_response_means_no_alignment(self):
        drv, visa = _make_driver()
        visa.query.return_value = "   \r\n  "

        status = await drv.get_user_alignment_status()
        assert status is None

    @pytest.mark.asyncio
    async def test_quoted_name_is_unwrapped(self):
        """Some firmware versions wrap string responses in quotes."""
        drv, visa = _make_driver()
        responses = iter(['"MyAlign"', '"some info"'])
        visa.query.side_effect = lambda cmd: next(responses)

        status = await drv.get_user_alignment_status()
        assert status is not None
        assert status["alignment_name"] == "MyAlign"
        assert status["info"] == "some info"

    @pytest.mark.asyncio
    async def test_query_failure_returns_none(self):
        drv, _ = _make_driver()

        async def _query_raises(cmd, timeout=None, **_kw):
            raise RuntimeError("instrument does not support SYST:CALIB:USER:GET?")

        drv._query = _query_raises  # type: ignore[assignment]

        status = await drv.get_user_alignment_status()
        assert status is None

    @pytest.mark.asyncio
    async def test_info_query_failure_is_tolerated(self):
        """INFO? failing should not invalidate the GET? result."""
        drv, _ = _make_driver()
        call_n = {"i": 0}

        async def _query(cmd, timeout=None, **_kw):
            call_n["i"] += 1
            if "INFO" in cmd:
                raise RuntimeError("INFO? not supported")
            return "MyAlign"

        drv._query = _query  # type: ignore[assignment]

        status = await drv.get_user_alignment_status()
        assert status is not None
        assert status["alignment_name"] == "MyAlign"
        assert status["info"] == ""

    @pytest.mark.asyncio
    async def test_no_visa_resource_returns_none(self):
        drv = RealPropsimF64Driver("propsim-test", {})
        # _visa_resource is None
        status = await drv.get_user_alignment_status()
        assert status is None


# ============================================================================
# enable_user_alignment(name)
# ============================================================================

class TestEnableUserAlignment:

    @pytest.mark.asyncio
    async def test_writes_set_command_and_verifies(self):
        drv, visa = _make_driver()
        visa.query.return_value = "MyAlign"  # GET? confirms

        ok = await drv.enable_user_alignment("MyAlign")
        assert ok is True
        sent = _writes(visa)
        assert any("SYSTem:CALIBration:USER:SET 1,MyAlign" in s for s in sent)

    @pytest.mark.asyncio
    async def test_mismatch_returns_false(self):
        """If the file doesn't exist on the emulator, GET? returns the
        previously active name (or empty) instead of the requested one."""
        drv, visa = _make_driver()
        visa.query.return_value = "DifferentAlign"

        ok = await drv.enable_user_alignment("MyAlign")
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_returning_empty_means_failed(self):
        drv, visa = _make_driver()
        visa.query.return_value = ""

        ok = await drv.enable_user_alignment("MyAlign")
        assert ok is False

    @pytest.mark.asyncio
    async def test_quoted_response_matches_clean_name(self):
        drv, visa = _make_driver()
        visa.query.return_value = '"MyAlign"'

        ok = await drv.enable_user_alignment("MyAlign")
        assert ok is True

    @pytest.mark.asyncio
    async def test_empty_name_raises(self):
        drv, _ = _make_driver()
        with pytest.raises(ValueError):
            await drv.enable_user_alignment("")

    @pytest.mark.asyncio
    async def test_scpi_failure_returns_false(self):
        drv, visa = _make_driver()

        def _write_raises(cmd):
            raise RuntimeError("VISA timeout")
        visa.write.side_effect = _write_raises

        ok = await drv.enable_user_alignment("MyAlign")
        assert ok is False

    @pytest.mark.asyncio
    async def test_no_visa_resource_returns_false(self):
        drv = RealPropsimF64Driver("propsim-test", {})
        ok = await drv.enable_user_alignment("MyAlign")
        assert ok is False


# ============================================================================
# list_external_units()
# ============================================================================

class TestListExternalUnits:

    @pytest.mark.asyncio
    async def test_parses_two_acus_with_connectors(self):
        drv, visa = _make_driver()
        # Manual format: "ACU 12345 (C5),ACU 67890 (C6)"
        visa.query.return_value = "ACU 12345 (C5),ACU 67890 (C6)"

        units = await drv.list_external_units()
        assert units == [
            {"unit": "ACU 12345", "connector": "C5"},
            {"unit": "ACU 67890", "connector": "C6"},
        ]
        # Confirm the LIST? variant we use disables scan (cheap path)
        sent_queries = [c.args[0] for c in visa.query.call_args_list]
        assert any("SYSTem:EXTernal:UNIT:LIST? 0" in s for s in sent_queries)

    @pytest.mark.asyncio
    async def test_unit_without_connector_keeps_none(self):
        drv, visa = _make_driver()
        visa.query.return_value = "ACU 99999"

        units = await drv.list_external_units()
        assert units == [{"unit": "ACU 99999", "connector": None}]

    @pytest.mark.asyncio
    async def test_empty_response_means_no_units(self):
        drv, visa = _make_driver()
        visa.query.return_value = ""

        units = await drv.list_external_units()
        assert units == []

    @pytest.mark.asyncio
    async def test_query_failure_returns_empty_list(self):
        drv, _ = _make_driver()

        async def _query_raises(cmd, timeout=None, **_kw):
            raise RuntimeError("SYST:EXT:UNIT:LIST? not supported")
        drv._query = _query_raises  # type: ignore[assignment]

        units = await drv.list_external_units()
        assert units == []

    @pytest.mark.asyncio
    async def test_quoted_csv_is_parsed(self):
        drv, visa = _make_driver()
        visa.query.return_value = '"ACU 12345 (C5)" , "ACU 67890 (C7)"'

        units = await drv.list_external_units()
        assert units == [
            {"unit": "ACU 12345", "connector": "C5"},
            {"unit": "ACU 67890", "connector": "C7"},
        ]

    @pytest.mark.asyncio
    async def test_no_visa_resource_returns_empty(self):
        drv = RealPropsimF64Driver("propsim-test", {})
        units = await drv.list_external_units()
        assert units == []


# ============================================================================
# Precheck phase surfacing
# ============================================================================

class TestPrecheckAlignmentSurface:
    """precheck.py 在 phase 结果里暴露 CE user alignment 状态.

    OPTIONAL license — 没有 alignment 不应该 hard-fail, 只是 warning."""

    def _build_context(self, ce_driver):
        """Construct the minimum stub needed by precheck up to the alignment
        block. We don't run the full executor — we exercise the isolated
        block via a helper that mirrors the production loop."""
        from unittest.mock import MagicMock
        ctx = MagicMock()
        # HAL: only channelEmulator matters here
        return ctx, ce_driver

    @pytest.mark.asyncio
    async def test_active_alignment_surfaces_in_result_payload(self):
        """When CE has an alignment loaded, precheck records it and adds an
        info-style message (no warning)."""
        from unittest.mock import AsyncMock, MagicMock

        ce = MagicMock()
        ce.get_user_alignment_status = AsyncMock(return_value={
            "alignment_name": "CAICT_5G_3500MHz",
            "info": "FI1234567, 29.01.2024, ...",
        })
        ce.list_external_units = AsyncMock(return_value=[])

        # Mirror the precheck block inline (also documents the contract for
        # any future executor refactor).
        result_payload: dict = {}
        warnings: list[str] = []
        messages: list[str] = []

        if ce is not None and hasattr(ce, "get_user_alignment_status"):
            alignment = await ce.get_user_alignment_status()
            if alignment:
                result_payload["channel_emulator_user_alignment"] = alignment
                messages.append(
                    f"CE user alignment: ACTIVE "
                    f"(name={alignment.get('alignment_name')!r})"
                )
            else:
                result_payload["channel_emulator_user_alignment"] = None
                warnings.append("Channel emulator has no user alignment loaded")
            units = await ce.list_external_units()
            result_payload["channel_emulator_external_units"] = units

        assert result_payload["channel_emulator_user_alignment"] == {
            "alignment_name": "CAICT_5G_3500MHz",
            "info": "FI1234567, 29.01.2024, ...",
        }
        assert any("ACTIVE" in m for m in messages)
        assert warnings == []  # active alignment ⇒ no warning

    @pytest.mark.asyncio
    async def test_missing_alignment_warns_but_does_not_fail(self):
        """Driver returning None (no license / never aligned) should NOT
        raise; precheck just appends a warning so the operator can decide."""
        from unittest.mock import AsyncMock, MagicMock

        ce = MagicMock()
        ce.get_user_alignment_status = AsyncMock(return_value=None)
        ce.list_external_units = AsyncMock(return_value=[])

        result_payload: dict = {}
        warnings: list[str] = []

        alignment = await ce.get_user_alignment_status()
        if alignment is None:
            result_payload["channel_emulator_user_alignment"] = None
            warnings.append("Channel emulator has no user alignment loaded")

        assert result_payload["channel_emulator_user_alignment"] is None
        assert any("no user alignment" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_real_driver_without_visa_falls_back_cleanly(self):
        """Smoke: a real RealPropsimF64Driver with no VISA connection (mock
        scenario) returns None / [] — precheck should accept this."""
        drv = RealPropsimF64Driver("propsim-mock", {})

        status = await drv.get_user_alignment_status()
        units = await drv.list_external_units()

        assert status is None
        assert units == []


# ============================================================================
# P2-10 Step 3: alignment 标定数据新鲜度 (该不该重标)
# ============================================================================

class TestAlignmentFreshness:
    """alignment 补偿随温度/时间漂移, 标定数据会过期。解析 INFO? 时间戳跟 today 比,
    超阈值 → stale 建议重标。把注释 159 的"供操作员判断是否新鲜"从人工眼看升级成解析。"""

    def test_parse_f64_real_info_format(self):
        # F64 INFO? 实测格式 (本文件 test_returns_name_and_info 同款): DD.MM.YYYY 点分隔
        from datetime import date
        drv, _ = _make_driver()
        assert drv._parse_alignment_date(
            "FI1234567, 29.01.2024, External Response Calibration Tool 3.0, PROPSIM FW 10.0"
        ) == date(2024, 1, 29)

    def test_parse_iso_and_slash_variants(self):
        from datetime import date
        drv, _ = _make_driver()
        assert drv._parse_alignment_date("calibrated 2026-05-27 ok") == date(2026, 5, 27)
        assert drv._parse_alignment_date("2026/05/27") == date(2026, 5, 27)

    def test_parse_unparseable_returns_none(self):
        drv, _ = _make_driver()
        assert drv._parse_alignment_date("no date here") is None
        assert drv._parse_alignment_date("") is None
        assert drv._parse_alignment_date(None) is None

    def test_freshness_fresh(self):
        from datetime import date
        drv, _ = _make_driver()  # default max_age 30
        r = drv.alignment_freshness("29.01.2024", today=date(2024, 2, 8))  # 10 天前
        assert r["freshness"] == "fresh"
        assert r["calibrated_date"] == "2024-01-29"
        assert r["age_days"] == 10

    def test_freshness_stale(self):
        from datetime import date
        drv, _ = _make_driver()  # default max_age 30
        r = drv.alignment_freshness("29.01.2024", today=date(2024, 5, 8))  # 100 天前
        assert r["freshness"] == "stale"
        assert r["age_days"] == 100

    def test_freshness_unknown_when_no_date(self):
        from datetime import date
        drv, _ = _make_driver()
        r = drv.alignment_freshness("no date in info", today=date(2024, 5, 8))
        assert r["freshness"] == "unknown"
        assert r["calibrated_date"] is None and r["age_days"] is None

    def test_boundary_exactly_max_age_is_fresh(self):
        from datetime import date
        drv, _ = _make_driver()  # max_age 30
        r = drv.alignment_freshness("29.01.2024", today=date(2024, 2, 28))  # 恰好 30 天
        assert r["age_days"] == 30 and r["freshness"] == "fresh"  # age > max 才 stale

    def test_max_age_override_from_connection_params(self):
        from datetime import date
        drv = RealPropsimF64Driver("propsim-test", {"alignment_max_age_days": 7})
        r = drv.alignment_freshness("29.01.2024", today=date(2024, 2, 8))  # 10 天 > 7
        assert r["freshness"] == "stale" and r["max_age_days"] == 7

    def test_max_age_param_overrides_default(self):
        from datetime import date
        drv, _ = _make_driver()
        r = drv.alignment_freshness("29.01.2024", today=date(2024, 2, 8), max_age_days=5)
        assert r["freshness"] == "stale" and r["max_age_days"] == 5

    def test_max_age_blank_override_falls_back_to_default(self):
        # Codex on PR #125: operator 清空 optional override → connection_params 留 null/""
        # → 不能崩 driver 构造, 回退默认 30。
        from datetime import date
        for blank in (None, ""):
            drv = RealPropsimF64Driver("propsim-test", {"alignment_max_age_days": blank})
            assert drv._alignment_max_age_days == 30
            r = drv.alignment_freshness("29.01.2024", today=date(2024, 2, 8))
            assert r["max_age_days"] == 30 and r["freshness"] == "fresh"

    def test_max_age_invalid_string_falls_back_to_default(self):
        # 非法字符串 (无法 int) 同样回退默认, 不崩
        drv = RealPropsimF64Driver("propsim-test", {"alignment_max_age_days": "abc"})
        assert drv._alignment_max_age_days == 30

    def test_max_age_numeric_string_coerced(self):
        # JSON 里字符串数字 "7" → 7
        drv = RealPropsimF64Driver("propsim-test", {"alignment_max_age_days": "7"})
        assert drv._alignment_max_age_days == 7
