"""F64 set_channel_model 加载后 fail-loud gate 测试 (P0-8 Step 3).

背景: F64 即便 .smu 文件缺失/损坏 (或早期错端口 5025) 也会对 *OPC? 答 "1",
唯一可靠的失败信号是 SYST:ERR? (-200 "No simulation opened" / -300)。旧
set_channel_model 加载后只在最后 _check_errors (log-only), 方法仍返回 True ——
2026-05-27 早上的 -200 误诊 (以为是通道数不匹配) 就源于此: 加载失败后继续
设频 → 错误叠加。

本 gate 在加载 *OPC? 后立刻查 SYST:ERR?, 有真错误就 fail-loud (return False)
且不继续设频。

验证方式: revert _first_error gate 后 test_failed_load_* 应失败 (方法会返回 True
并继续下发 CALC:FILT:CENT:CH)。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.hal.propsim_f64 import RealPropsimF64Driver


def _make_driver(syst_err_after_load: str):
    """造一个 mock 驱动: SYST:ERR? 返回指定值, 其余查询返回安全默认。"""
    drv = RealPropsimF64Driver("propsim-test", {})
    drv._channel_count = 2  # 收敛设频循环, 保持测试精简
    visa = MagicMock()

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return syst_err_after_load
        if cmd.startswith("ROUT:PATH:CONN?"):
            return "B1.1"
        return '0,"No error"'

    visa.query.side_effect = _router
    visa.write.return_value = None
    drv._visa_resource = visa

    async def _async_write(cmd, timeout=None):
        visa.write(cmd)

    async def _async_query(cmd, timeout=None):
        return visa.query(cmd)

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


class TestLoadErrorGate:
    async def test_failed_load_returns_false_and_skips_freq(self):
        # 加载后 SYST:ERR? 报 -200 → fail-loud, 不进设频步骤
        drv, visa = _make_driver('-200,"No simulation opened"')
        ok = await drv.set_channel_model(
            "CDL-C",
            "UMa",
            {"emulation_file": "D:\\bad\\missing.smu", "center_frequency_mhz": 3600},
        )
        assert ok is False
        assert drv._last_error and "No simulation opened" in drv._last_error
        # 关键: 加载失败后不应继续下发 CALC:FILT:CENT:CH (早上的错误叠加根因)
        assert not any(w.startswith("CALC:FILT:CENT:CH") for w in _writes(visa))
        # 失败文件不应被记成已加载
        assert drv._loaded_emulation_file != "D:\\bad\\missing.smu"

    async def test_minus_300_also_gated(self):
        drv, visa = _make_driver('-300,"Device-specific error"')
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\bad\\corrupt.smu"}
        )
        assert ok is False
        assert not any(w.startswith("CALC:FILT:CENT:CH") for w in _writes(visa))

    async def test_clean_load_proceeds_and_returns_true(self):
        drv, visa = _make_driver('0,"No error"')
        ok = await drv.set_channel_model(
            "CDL-C",
            "UMa",
            {"emulation_file": "D:\\ok\\model.smu", "center_frequency_mhz": 3600},
        )
        assert ok is True
        # 加载干净 → 继续设频
        assert any(w.startswith("CALC:FILT:CENT:CH") for w in _writes(visa))
        assert drv._loaded_emulation_file == "D:\\ok\\model.smu"

    async def test_plus_zero_no_error_is_clean(self):
        # 有些固件返回 "+0,..." 形式的 no-error, gate 不应误判为失败
        drv, visa = _make_driver('+0,"No error"')
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\ok\\model.smu"}
        )
        assert ok is True
