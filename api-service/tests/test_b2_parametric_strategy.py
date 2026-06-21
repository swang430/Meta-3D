"""F6 单测 — B-2 参数化 TDL 路由 + 能力门 (P2-14)。"""
import asyncio

from app.hal.channel_emulator import ChannelLoadMode
from app.services.channel_generation.base_generator import EngineMode
from app.services.channel_generation.b2_parametric_strategy import B2ParametricTdlStrategy


class _MockEmu:
    """最小 mock: 只暴露 get_supported_load_modes。"""

    def __init__(self, modes):
        self._modes = modes

    def get_supported_load_modes(self):
        return self._modes


def test_engine_mode_b2_exists():
    assert EngineMode.B2_PARAMETRIC_TDL.value == "b2_parametric_tdl"
    # 字符串构造 (config.engine_mode 是字符串) 能解析
    assert EngineMode("b2_parametric_tdl") is EngineMode.B2_PARAMETRIC_TDL


def test_channel_load_mode_parametric_tdl_exists():
    assert ChannelLoadMode.PARAMETRIC_TDL.value == "parametric_tdl"


def test_capability_gate_rejects_unsupported_emulator():
    """仪器不支持 PARAMETRIC_TDL → 能力门 fail-loud (返回 False)。"""
    emu = _MockEmu([ChannelLoadMode.EXTERNAL_WAVEFORM])
    strat = B2ParametricTdlStrategy(emu, chamber_config=None, calibration_entries=[])
    assert strat.supports_parametric_tdl() is False
    ok = asyncio.run(strat.generate_and_load({}, {"session_id": "s", "model_name": "m"}))
    assert ok is False


def test_supported_emulator_routes_but_generation_pending_f7():
    """仪器支持 PARAMETRIC_TDL → 过能力门, 但生成/加载 F7+现场 pending → 当前 False。"""
    emu = _MockEmu([ChannelLoadMode.EXTERNAL_WAVEFORM, ChannelLoadMode.PARAMETRIC_TDL])
    strat = B2ParametricTdlStrategy(emu, chamber_config=None, calibration_entries=[])
    assert strat.supports_parametric_tdl() is True
    ok = asyncio.run(strat.generate_and_load({}, {"session_id": "s", "model_name": "m"}))
    assert ok is False
