"""P2-10 Step 2: F64 per-output 精细输出端配置 driver 测试.

set_output_path_loss / set_output_gain —— per-output 单通道精细控制, 区别于:
  - set_path_loss: batch 全输出统一 loss
  - set_external_attenuators: per-output map 但强制负增益 (只衰减)

mock VISA (同 test_propsim_user_alignment), 验 SCPI 字符串; mock _check_errors no-op
(聚焦 SCPI 写入验证, 错误检查副路径不干扰)。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver


def _make_driver():
    drv = RealPropsimF64Driver("propsim-test", {})
    visa_mock = MagicMock()
    visa_mock.query.return_value = '0,"No error"'
    visa_mock.write.return_value = None
    drv._visa_resource = visa_mock

    async def _async_write(cmd, timeout=None):
        visa_mock.write(cmd)

    async def _async_query(cmd, timeout=None):
        return visa_mock.query(cmd)

    async def _async_check_errors():
        return None

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    drv._check_errors = _async_check_errors  # type: ignore[assignment]
    return drv, visa_mock


def _writes(visa_mock):
    return [call.args[0] for call in visa_mock.write.call_args_list]


class TestSetOutputPathLoss:
    @pytest.mark.asyncio
    async def test_writes_per_output_loss_scpi(self):
        drv, visa = _make_driver()
        ok = await drv.set_output_path_loss(3, 12.5)
        assert ok is True
        assert any("OUTP:LOSS:SET 3,12.5" in s for s in _writes(visa))

    @pytest.mark.asyncio
    async def test_only_targets_given_output(self):
        # per-output: 只设指定通道, 不像 set_path_loss batch 全部输出
        drv, visa = _make_driver()
        await drv.set_output_path_loss(5, 8.0)
        loss_writes = [s for s in _writes(visa) if "OUTP:LOSS:SET" in s]
        assert loss_writes == ["OUTP:LOSS:SET 5,8.0"]

    @pytest.mark.asyncio
    async def test_no_visa_returns_false(self):
        drv = RealPropsimF64Driver("propsim-test", {})  # _visa_resource None
        assert await drv.set_output_path_loss(1, 10.0) is False

    @pytest.mark.asyncio
    async def test_scpi_failure_returns_false(self):
        drv, visa = _make_driver()

        def _boom(cmd):
            raise RuntimeError("VISA timeout")

        visa.write.side_effect = _boom
        assert await drv.set_output_path_loss(1, 10.0) is False


class TestSetOutputGain:
    @pytest.mark.asyncio
    async def test_positive_gain(self):
        # 正增益 (放大) —— set_external_attenuators 做不到 (强制 -abs 只衰减)
        drv, visa = _make_driver()
        ok = await drv.set_output_gain(2, 5.25)
        assert ok is True
        assert any("OUTP:GAIN:CH 2,5.25" in s for s in _writes(visa))

    @pytest.mark.asyncio
    async def test_negative_gain_attenuation(self):
        drv, visa = _make_driver()
        await drv.set_output_gain(4, -10.0)
        assert any("OUTP:GAIN:CH 4,-10.00" in s for s in _writes(visa))

    @pytest.mark.asyncio
    async def test_only_targets_given_output(self):
        drv, visa = _make_driver()
        await drv.set_output_gain(7, 1.5)
        gain_writes = [s for s in _writes(visa) if "OUTP:GAIN:CH" in s]
        assert gain_writes == ["OUTP:GAIN:CH 7,1.50"]

    @pytest.mark.asyncio
    async def test_no_visa_returns_false(self):
        drv = RealPropsimF64Driver("propsim-test", {})
        assert await drv.set_output_gain(1, 3.0) is False

    @pytest.mark.asyncio
    async def test_scpi_failure_returns_false(self):
        drv, visa = _make_driver()

        def _boom(cmd):
            raise RuntimeError("VISA timeout")

        visa.write.side_effect = _boom
        assert await drv.set_output_gain(1, 3.0) is False
