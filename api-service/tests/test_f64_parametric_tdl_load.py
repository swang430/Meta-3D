"""F7 单测 — F64 PARAMETRIC_TDL (.tap/.rtc) B-2 加载原语 (P2-14)。

mock 掉 FTP/SCPI (monkeypatch upload_asc_files), 只验路由 + pipeline 标记 + fail-loud。
真机 .tap schema / gaussian 谱 / 运行时切换为现场验证 (V1.0 §9)。
"""
import asyncio

import pytest

from app.hal.channel_emulator import ChannelLoadMode
from app.hal.propsim_f64 import F64Pipeline, RealPropsimF64Driver


def _drv():
    return RealPropsimF64Driver("propsim-test", {})


def test_parametric_tdl_in_supported_modes():
    assert ChannelLoadMode.PARAMETRIC_TDL in _drv().get_supported_load_modes()


def test_f64_pipeline_b2_exists():
    assert F64Pipeline.B2_PARAMETRIC_TDL.value == "b2_parametric_tdl"


def test_load_channel_routes_parametric_tdl_and_sets_pipeline():
    drv = _drv()
    called = {}

    async def _fake_upload(waveform_dir, model_name):
        called["args"] = (waveform_dir, model_name)
        return True

    drv.upload_asc_files = _fake_upload
    ok = asyncio.run(drv.load_channel(
        ChannelLoadMode.PARAMETRIC_TDL, "UMa-CDL-C", "scenario", {},
        waveform_dir="/tmp/b2_tdl"))
    assert ok is True
    assert called["args"] == ("/tmp/b2_tdl", "UMa-CDL-C")
    assert drv._active_pipeline == F64Pipeline.B2_PARAMETRIC_TDL   # 覆盖 ASC_RUNTIME 标记


def test_load_channel_parametric_tdl_requires_waveform_dir():
    drv = _drv()
    with pytest.raises(ValueError, match="waveform_dir"):
        asyncio.run(drv.load_channel(
            ChannelLoadMode.PARAMETRIC_TDL, "m", "s", {}, waveform_dir=None))


def test_load_parametric_tdl_propagates_upload_failure():
    """upload 失败 → 返回 False 且不设 B-2 pipeline 标记 (fail-loud)。"""
    drv = _drv()

    async def _fail_upload(waveform_dir, model_name):
        return False

    drv.upload_asc_files = _fail_upload
    ok = asyncio.run(drv.load_parametric_tdl("/tmp/x", "m"))
    assert ok is False
    assert drv._active_pipeline != F64Pipeline.B2_PARAMETRIC_TDL
