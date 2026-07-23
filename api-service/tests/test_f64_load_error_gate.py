"""F64 set_channel_model 加载后 fail-loud gate 测试 (P0-8 Step 3).

背景: F64 即便 .smu 缺失/损坏 (或早期错端口 5025) 也会对 *OPC? 答 "1", 唯一可靠的
失败信号是 SYST:ERR? (-200 "No simulation opened" / -300)。旧 set_channel_model
加载后只在最后 _check_errors (log-only), 方法仍返回 True —— 2026-05-27 早上把
"文件没加载"误诊成"通道数不匹配"就源于此 (加载失败后继续设频 → 错误叠加)。

本 gate 在加载 *OPC? 后立刻查 SYST:ERR?, 有真错误就 fail-loud (return False) 且不设频。

**Codex (PR #93) follow-up**: SYST:ERR? 是 FIFO。前序命令遗留的 stale 错误会被 gate
误判成本次加载失败。修复 = 加载前先 _drain_errors() 清队列, 确保 gate 只评估本次
CALC:FILT:FILE 产生的错误。本测试用"队列式 SYST:ERR? mock"分别覆盖:
  · stale 错误被 drain 清掉、干净加载仍成功 (回归核心)
  · drain 不会掩盖本次加载真错误

验证方式: revert _first_error gate → 失败/-200 类用例失败; revert _drain_errors →
stale 用例失败 (干净加载被 stale 误判成 False)。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.hal.propsim_f64 import RealPropsimF64Driver


def _make_driver(syst_err_responses):
    """造 mock 驱动: SYST:ERR? 按 syst_err_responses 顺序返回, 耗尽后返回 '0,"No error"'。

    这样可分别模拟"加载前队列里的遗留错误 (被 drain 清掉)"与"加载本身产生的错误":
    drain 会一直 pop 到遇到一个 no-error 为止, 之后 gate 的 _first_error 再 pop 一次。
    """
    drv = RealPropsimF64Driver("propsim-test", {})
    drv._channel_count = 2  # 收敛设频循环, 保持测试精简
    visa = MagicMock()
    queue = list(syst_err_responses)

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return queue.pop(0) if queue else '0,"No error"'
        # P0-3 缩范围: 加载走 _load_smu_with_preflight — STATE? 判态 + CLOSE 后
        # 复查 ==CLOSED 才继续; CENT:CH? 回读真频。均不查 MODEL:INFO? (拓扑回读留
        # F64R-2), 也**不碰** SYST:ERR? 队列, 故 stale-drain / fail-loud gate 语义不变。
        if cmd == "DIAG:SIMU:STATE?":
            return "CLOSED"
        if cmd.startswith("CALC:FILT:CENT:CH?"):
            return ""  # 回读真频不可用 → 非致命, 加载仍成功
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


def _cent_issued(visa):
    return any(w.startswith("CALC:FILT:CENT:CH") for w in _writes(visa))


class TestLoadErrorGate:
    async def test_clean_load_proceeds_and_returns_true(self):
        # 队列干净: drain 立刻终止, gate 看到 no-error → 继续设频
        drv, visa = _make_driver(['0,"No error"'])
        ok = await drv.set_channel_model(
            "CDL-C", "UMa",
            {"emulation_file": "D:\\ok\\model.smu", "center_frequency_mhz": 3600},
        )
        assert ok is True
        assert _cent_issued(visa)
        assert drv._loaded_emulation_file == "D:\\ok\\model.smu"

    async def test_plus_zero_no_error_is_clean(self):
        # "+0,..." 形式的 no-error 不应被误判为失败
        drv, visa = _make_driver(['+0,"No error"'])
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\ok\\model.smu"}
        )
        assert ok is True

    async def test_failed_load_returns_false_and_skips_freq(self):
        # 队列加载前干净, 加载后报 -200 → fail-loud, 不进设频
        drv, visa = _make_driver(['0,"No error"', '-200,"No simulation opened"'])
        ok = await drv.set_channel_model(
            "CDL-C", "UMa",
            {"emulation_file": "D:\\bad\\missing.smu", "center_frequency_mhz": 3600},
        )
        assert ok is False
        assert drv._last_error and "No simulation opened" in drv._last_error
        assert not _cent_issued(visa)
        assert drv._loaded_emulation_file != "D:\\bad\\missing.smu"

    async def test_minus_300_also_gated(self):
        drv, visa = _make_driver(['0,"No error"', '-300,"Device-specific error"'])
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\bad\\corrupt.smu"}
        )
        assert ok is False
        assert not _cent_issued(visa)

    # ---- Codex (PR #93) regression: stale FIFO 错误不能误判本次加载 ----

    async def test_stale_error_drained_does_not_fail_clean_load(self):
        # 加载前队列里有前序命令遗留的 stale 错误 (-221), 但本次加载是干净的。
        # drain 应清掉 stale, gate 只看本次加载 → 必须成功 (而非被 stale 误判成 False)。
        drv, visa = _make_driver([
            '-221,"Settings conflict (stale from prior cmd)"',
            '0,"No error"',   # drain 终止
            '0,"No error"',   # gate: 本次加载干净
        ])
        ok = await drv.set_channel_model(
            "CDL-C", "UMa",
            {"emulation_file": "D:\\ok\\model.smu", "center_frequency_mhz": 3600},
        )
        assert ok is True, "stale FIFO 错误被误判成本次加载失败 (drain 未生效)"
        assert _cent_issued(visa)
        # stale 错误不应污染 _last_error
        assert not (drv._last_error and "Settings conflict" in drv._last_error)

    async def test_stale_drained_then_real_load_error_still_caught(self):
        # drain 清掉 stale 后, 本次加载又真失败 (-200) → gate 仍要拦住 (drain 不掩盖真错误)
        drv, visa = _make_driver([
            '-221,"Settings conflict (stale)"',
            '0,"No error"',   # drain 终止
            '-200,"No simulation opened"',  # gate: 本次加载真失败
        ])
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\bad\\missing.smu"}
        )
        assert ok is False
        assert drv._last_error and "No simulation opened" in drv._last_error
        assert not _cent_issued(visa)
