"""P1-16: scpi-command 端点 timeout 透传 + _driver_supports_timeout_kwarg 单测。

背景: 2026-05-27 CAICT 现场, 经后端发 F64 慢操作 (加载后 *OPC?、INP:LEV:MEAS?、
INP:LEV:AUTOSET) 用 `_run_command_via_hal` 不透传 `timeout_ms` → 默认短超时让真
响应迟到串到下一次读 (desync 级联), 必须直连 `/tmp/f64ctl.py` workaround → P0-8
input level 经后端 closed loop 没闭环的直接原因之一。

本文件钉死:
1. **`_driver_supports_timeout_kwarg` introspection 正确性** (F64-like ✓ /
   pyvisa-like ✗ / 没 `_do_query` ✗) — 不能误判, 否则 pyvisa driver 会 TypeError。
2. **`_run_command_via_hal` timeout 透传 cartesian**:
   (driver 支持 vs 不支持) × (timeout_ms 给了 vs None) × (query vs write)
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import logging

import pytest

from app.api.instrument import (
    _driver_supports_timeout_kwarg,
    _looks_like_scpi_query,
    _run_command_via_hal,
)


# ---------------------------------------------------------------------------
# Fake drivers — match the real shape so introspection sees the right thing
# ---------------------------------------------------------------------------


class _FakeF64LikeDriver:
    """模拟 PROPSIM F64 / FS16: socket-based, `_do_query` 显式签名带 timeout。

    `_query` / `_write` 是 template method 一律 **kwargs (跟 base.py 一致), 真正
    的 signature constraint 在 `_do_query` / `_do_write` 上。
    """

    def __init__(self):
        self.query_calls: list[Dict[str, Any]] = []
        self.write_calls: list[Dict[str, Any]] = []

    async def _do_query(self, cmd: str, timeout=None) -> str:
        return "ok"

    async def _do_write(self, cmd: str, timeout=None) -> None:
        return None

    async def _query(self, cmd: str, **kwargs) -> str:
        self.query_calls.append({"cmd": cmd, **kwargs})
        return await self._do_query(cmd, **kwargs)

    async def _write(self, cmd: str, **kwargs) -> None:
        self.write_calls.append({"cmd": cmd, **kwargs})
        await self._do_write(cmd, **kwargs)


class _FakePyVisaDriver:
    """模拟 UXM/ENA/FSVA/CMW500: pyvisa-based, `_do_query` 签名 (cmd) 不带 timeout。

    透传 timeout=X 会 TypeError, 必须不透传。"""

    def __init__(self):
        self.query_calls: list[Dict[str, Any]] = []
        self.write_calls: list[Dict[str, Any]] = []

    def _do_query(self, cmd: str) -> str:
        return "ok"

    def _do_write(self, cmd: str) -> None:
        return None

    def _query(self, cmd: str, **kwargs) -> str:
        if kwargs:
            # 模拟 base.py 模板方法把 kwargs 透传给 _do_query 时若 sub class 不
            # 接受会 TypeError。在测试里直接 raise 让回归 fail-loud。
            raise TypeError(
                f"_do_query() got an unexpected keyword argument: {list(kwargs)!r}"
            )
        self.query_calls.append({"cmd": cmd})
        return self._do_query(cmd)

    def _write(self, cmd: str, **kwargs) -> None:
        if kwargs:
            raise TypeError(
                f"_do_write() got an unexpected keyword argument: {list(kwargs)!r}"
            )
        self.write_calls.append({"cmd": cmd})
        self._do_write(cmd)


class _FakeDriverWithoutDoQuery:
    """退化情形: driver 没 `_do_query` (e.g. 未来未实现 driver)。
    introspection 应返回 False 避免崩。"""
    pass


# ---------------------------------------------------------------------------
# helper introspection
# ---------------------------------------------------------------------------


class TestDriverSupportsTimeoutKwarg:
    def test_f64_like_driver_supports_timeout(self):
        assert _driver_supports_timeout_kwarg(_FakeF64LikeDriver()) is True

    def test_pyvisa_like_driver_does_not_support_timeout(self):
        # pyvisa driver `_do_query(cmd)` 显式不带 timeout → 不能透传
        assert _driver_supports_timeout_kwarg(_FakePyVisaDriver()) is False

    def test_driver_without_do_query_returns_false(self):
        # 防御: introspection 不能崩, 应返回 False
        assert _driver_supports_timeout_kwarg(_FakeDriverWithoutDoQuery()) is False

    def test_kwargs_only_signature_supports_timeout(self):
        """边界: _do_query(cmd, **kwargs) 也应认为支持 timeout (kwargs sink)。"""

        class _KwargsOnly:
            def _do_query(self, cmd, **kwargs):
                return "ok"

        assert _driver_supports_timeout_kwarg(_KwargsOnly()) is True


# ---------------------------------------------------------------------------
# _run_command_via_hal 透传 cartesian
# ---------------------------------------------------------------------------


class TestRunCommandViaHalTimeoutPassthrough:
    """timeout_ms × driver 支持性 × query|write 矩阵。"""

    @pytest.fixture
    def scpi_logger(self):
        return logging.getLogger("test.scpi")

    # ---- F64-like + timeout 给了 ----
    async def test_f64_query_receives_timeout(self, scpi_logger):
        drv = _FakeF64LikeDriver()
        result = await _run_command_via_hal(
            drv, "*OPC?", scpi_logger, "channelEmulator", timeout_ms=60000,
        )
        assert result.success is True
        assert len(drv.query_calls) == 1
        assert drv.query_calls[0]["timeout"] == 60000

    async def test_f64_write_receives_timeout(self, scpi_logger):
        drv = _FakeF64LikeDriver()
        result = await _run_command_via_hal(
            drv, "INP:LEV:AUTOSET 0,3", scpi_logger, "channelEmulator", timeout_ms=10000,
        )
        assert result.success is True
        assert len(drv.write_calls) == 1
        assert drv.write_calls[0]["timeout"] == 10000

    # ---- pyvisa-like + timeout 给了 → 不能透传 ----
    async def test_pyvisa_query_does_not_receive_timeout(self, scpi_logger):
        """pyvisa driver 不接受 timeout kwarg, 透传会 TypeError → 不能传。

        当前实现根据 _driver_supports_timeout_kwarg 自动跳过透传, 这里钉死回归:
        即使 caller 给了 timeout_ms, pyvisa driver 调用栈里也不能出现 timeout kwarg。
        """
        drv = _FakePyVisaDriver()
        result = await _run_command_via_hal(
            drv, "*IDN?", scpi_logger, "baseStation", timeout_ms=60000,
        )
        # 没崩 + 成功
        assert result.success is True
        # query 调用栈里没 timeout (而非 timeout=None 也存进 kwargs)
        assert len(drv.query_calls) == 1
        assert "timeout" not in drv.query_calls[0]

    async def test_pyvisa_write_does_not_receive_timeout(self, scpi_logger):
        drv = _FakePyVisaDriver()
        result = await _run_command_via_hal(
            drv, "INIT:IMM", scpi_logger, "baseStation", timeout_ms=10000,
        )
        assert result.success is True
        assert len(drv.write_calls) == 1
        assert "timeout" not in drv.write_calls[0]

    # ---- timeout_ms=None (兼容性) ----
    async def test_timeout_none_skips_pass_for_f64(self, scpi_logger):
        """timeout_ms=None → 即使 driver 支持也不应透传 (兼容老调用)。"""
        drv = _FakeF64LikeDriver()
        result = await _run_command_via_hal(
            drv, "*IDN?", scpi_logger, "channelEmulator", timeout_ms=None,
        )
        assert result.success is True
        assert len(drv.query_calls) == 1
        assert "timeout" not in drv.query_calls[0]

    async def test_timeout_none_skips_pass_for_pyvisa(self, scpi_logger):
        drv = _FakePyVisaDriver()
        result = await _run_command_via_hal(
            drv, "*IDN?", scpi_logger, "baseStation", timeout_ms=None,
        )
        assert result.success is True

    # ---- default 参数 (调用栈没传 timeout_ms) ----
    async def test_default_call_no_timeout_kwarg(self, scpi_logger):
        """没传 timeout_ms 应该等价 None (老 caller 不传, 行为不变)。"""
        drv = _FakeF64LikeDriver()
        result = await _run_command_via_hal(drv, "*IDN?", scpi_logger, "channelEmulator")
        assert result.success is True
        assert "timeout" not in drv.query_calls[0]

    async def test_query_with_path_argument_reads_response(self, scpi_logger):
        drv = _FakeF64LikeDriver()
        result = await _run_command_via_hal(
            drv,
            'MMEM:CAT? "D:\\User Playbacks"',
            scpi_logger,
            "channelEmulator",
        )
        assert result.success is True
        assert len(drv.query_calls) == 1
        assert drv.query_calls[0]["cmd"] == 'MMEM:CAT? "D:\\User Playbacks"'
        assert drv.write_calls == []


class TestLooksLikeScpiQuery:
    def test_plain_query(self):
        assert _looks_like_scpi_query("*IDN?") is True

    def test_query_with_argument_after_question_mark(self):
        assert _looks_like_scpi_query('MMEM:CAT? "D:\\User Playbacks"') is True

    def test_write_command(self):
        assert _looks_like_scpi_query('MMEM:CDIR "D:\\User Playbacks"') is False
