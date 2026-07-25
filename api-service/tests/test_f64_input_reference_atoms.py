"""F64 输入信号参考原子能力测试 (P0-8 Step 2 Phase 1).

覆盖 driver 层薄封装: measure_input / autoset_all_inputs / level·crest limits /
crest get·set / 测量模式 (burst) / burst 触发 / 系统状态 / clipping per-mille。
全部基于 User Reference §20.4.4 / §20.4.2.5 / §20.4.7.6, mock SCPI, 不需硬件。
设计见 docs/architecture/f64-input-level-and-dynamic-range.md。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.hal.propsim_f64 import F64InputMeasMode, RealPropsimF64Driver


def _make_driver(query_map=None, syst_err_responses=None):
    """mock 驱动: query_map 映射查询→响应; syst_err_responses 给 SYST:ERR? 一个序列
    (耗尽后默认 no-error), 用于测 autoset 的 drain + fail-loud; 其余默认安全值。"""
    drv = RealPropsimF64Driver("propsim-test", {})
    visa = MagicMock()
    err_q = list(syst_err_responses) if syst_err_responses is not None else None

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            if err_q is not None:
                return err_q.pop(0) if err_q else '0,"No error"'
            return '0,"No error"'
        if query_map and cmd in query_map:
            return query_map[cmd]
        return '0,"No error"'

    visa.query.side_effect = _router
    visa.write.return_value = None
    drv._visa_resource = visa

    async def _async_write(cmd, timeout=None):
        visa.write(cmd)

    async def _async_query(cmd, timeout=None, **_kw):
        return visa.query(cmd)

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


def _queries(visa):
    return [c.args[0] for c in visa.query.call_args_list]


class TestMeasureInput:
    async def test_parses_avg_and_crest(self):
        drv, visa = _make_driver({"INP:LEV:MEAS? 1,1.0": "-21.4,4"})
        assert await drv.measure_input(1, 1.0) == (-21.4, 4.0)
        assert "INP:LEV:MEAS? 1,1.0" in _queries(visa)

    async def test_no_signal_device_error_returns_none(self):
        # 无信号 / 输出过强 → F64 device error (非数字串) → None
        drv, _ = _make_driver({"INP:LEV:MEAS? 1,3.0": '-300,"No input signal"'})
        assert await drv.measure_input(1, 3.0) is None

    async def test_avg_only_defaults_crest_zero(self):
        drv, _ = _make_driver({"INP:LEV:MEAS? 1,1.0": "-15.0"})
        assert await drv.measure_input(1, 1.0) == (-15.0, 0.0)


class TestAutosetAllInputs:
    async def test_issues_autoset_zero_and_succeeds_clean(self):
        drv, visa = _make_driver()  # SYST:ERR? 恒 no-error
        assert await drv.autoset_all_inputs(3.0) is True
        assert "INP:LEV:AUTOSET 0,3.0" in _writes(visa)  # in=0 = 全部输入同测

    async def test_fails_loud_on_device_error(self):
        # AUTOSET 失败 (无信号/过强) → SYST:ERR? 报 device error → return False
        # (而非像 _check_errors 只 log 后仍 return True; Codex on PR #95)
        drv, visa = _make_driver(syst_err_responses=[
            '0,"No error"',                 # ① drain: 队列已空
            '-300,"No input signal"',       # ③ check: 本次 AUTOSET 失败
        ])
        ok = await drv.autoset_all_inputs(3.0)
        assert ok is False
        assert drv._last_error and "No input signal" in drv._last_error
        assert "INP:LEV:AUTOSET 0,3.0" in _writes(visa)

    async def test_drains_stale_then_succeeds(self):
        # 前序命令遗留的 stale 错误 → drain 清掉 → 本次 AUTOSET 干净 → True
        # (stale 不能被误判成 AUTOSET 失败 —— 同 PR #93 stale-FIFO 教训)
        drv, _ = _make_driver(syst_err_responses=[
            '-221,"Settings conflict (stale)"',  # ① drain: stale
            '0,"No error"',                       # ① drain 终止
            '0,"No error"',                       # ③ check: 本次 AUTOSET 干净
        ])
        assert await drv.autoset_all_inputs(3.0) is True


class TestAutosetInputsSubset:
    """子集 autoset (Codex on PR #96: 避免对未连接输入触发 no-signal 错误)。"""

    async def test_subset_succeeds_per_input(self):
        drv, visa = _make_driver()
        assert await drv.autoset_inputs([1, 3], 1.0) is True
        autosets = [w for w in _writes(visa) if w.startswith("INP:LEV:AUTOSET")]
        # 按顺序对 1 和 3 各发一次 (in!=0, 不是 AUTOSET 0)
        assert autosets == ["INP:LEV:AUTOSET 1,1.0", "INP:LEV:AUTOSET 3,1.0"]

    async def test_empty_list_is_noop(self):
        drv, visa = _make_driver()
        assert await drv.autoset_inputs([], 1.0) is True
        assert not any(w.startswith("INP:LEV:AUTOSET") for w in _writes(visa))

    async def test_per_input_fail_loud(self):
        # input 3 autoset 失败 → return False; _last_error 标该输入
        # (Codex #203 R3 后每 input 是独立事务: drain → AUTOSET → OPC → check)
        drv, visa = _make_driver(syst_err_responses=[
            '0,"No error"',                  # input 1 事务 drain 终止 (无 stale)
            '0,"No error"',                  # input 1 check ok
            '0,"No error"',                  # input 3 事务 drain 终止
            '-300,"No input signal"',        # input 3 check fail
        ])
        ok = await drv.autoset_inputs([1, 3], 1.0)
        assert ok is False
        assert drv._last_error and "input 3" in drv._last_error
        assert "No input signal" in drv._last_error

    async def test_drains_stale_before_loop(self):
        # 前序 stale 错误 → drain 清掉 → 后续 per-input 干净 → True
        drv, _ = _make_driver(syst_err_responses=[
            '-221,"stale"',                  # drain: stale
            '0,"No error"',                  # drain 终止
            '0,"No error"',                  # input 1 check ok
            '0,"No error"',                  # input 2 check ok
        ])
        assert await drv.autoset_inputs([1, 2], 1.0) is True


class TestLimits:
    async def test_level_limits(self):
        drv, _ = _make_driver({"INP:LEV:AMP:LIM? 1": "-23,0"})
        assert await drv.get_input_level_limits(1) == (-23.0, 0.0)

    async def test_crest_limits(self):
        drv, _ = _make_driver({"INP:CRE:LIM? 6": "0,23"})
        assert await drv.get_crest_limits(6) == (0.0, 23.0)

    async def test_limits_garbage_returns_none(self):
        drv, _ = _make_driver({"INP:LEV:AMP:LIM? 1": "garbage"})
        assert await drv.get_input_level_limits(1) is None


class TestCrest:
    async def test_get_crest(self):
        drv, _ = _make_driver({"INP:CRE:GET? 1": "4"})
        assert await drv.get_crest_factor(1) == 4.0

    async def test_set_crest_issues_command(self):
        drv, visa = _make_driver()
        assert await drv.set_crest_factor(1, 12.0) is True
        assert "INP:CRE:SET 1,12.00" in _writes(visa)


class TestMeasurementMode:
    async def test_set_burst_mode_issues_int(self):
        drv, visa = _make_driver()
        assert await drv.set_input_measurement_mode(1, F64InputMeasMode.BURST) is True
        assert "INP:MEAS:MODE:SET 1,3" in _writes(visa)

    async def test_get_mode_parses_enum(self):
        drv, _ = _make_driver({"INP:MEAS:MODE:GET? 1": "3"})
        assert await drv.get_input_measurement_mode(1) is F64InputMeasMode.BURST

    async def test_set_burst_trigger_level(self):
        drv, visa = _make_driver()
        assert await drv.set_burst_trigger_level(1, -10.1) is True
        assert "INP:MEAS:BURST:TRIG:SET 1,-10.10" in _writes(visa)


class TestSystemStatus:
    async def test_ok(self):
        drv, _ = _make_driver({"SYST:STAT?": "1"})
        assert await drv.get_system_status() == (True, [])

    async def test_warnings_parsed(self):
        drv, _ = _make_driver(
            {"SYST:STAT?": "0,Warning: External Reference missing,Input cut-off"}
        )
        ok, warnings = await drv.get_system_status()
        assert ok is False
        assert "Warning: External Reference missing" in warnings
        assert "Input cut-off" in warnings


class TestGroupClipping:
    async def test_per_mille_no_reset(self):
        drv, visa = _make_driver({"GROup:CLIpping:GET? 1,0": "28.75"})
        assert await drv.get_group_clipping(1) == 28.75
        assert "GROup:CLIpping:GET? 1,0" in _queries(visa)

    async def test_reset_flag(self):
        drv, visa = _make_driver({"GROup:CLIpping:GET? 1,1": "0"})
        assert await drv.get_group_clipping(1, reset=True) == 0.0
        assert "GROup:CLIpping:GET? 1,1" in _queries(visa)


class TestNoVisaResourceSafe:
    async def test_methods_return_safe_when_disconnected(self):
        drv = RealPropsimF64Driver("propsim-test", {})
        drv._visa_resource = None
        assert await drv.measure_input(1) is None
        assert await drv.get_input_level_limits(1) is None
        assert await drv.get_group_clipping(1) is None
        assert await drv.autoset_all_inputs() is False
        assert await drv.set_crest_factor(1, 10) is False
        assert await drv.set_input_measurement_mode(1, F64InputMeasMode.BURST) is False
