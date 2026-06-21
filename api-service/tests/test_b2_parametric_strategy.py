"""F6/PR-5 单测 — B-2 参数化 TDL 路由 + 能力门 + CE 聚类接线 (P2-14)。"""
import asyncio
from unittest.mock import MagicMock, AsyncMock

from app.hal.channel_emulator import ChannelLoadMode
from app.services.channel_generation.base_generator import EngineMode
from app.services.channel_generation.b2_parametric_strategy import B2ParametricTdlStrategy
from app.services.channel_engine_client import B2ClusterResult

_RAYS = [{"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30.0, "aod_deg": 10.0}]


def _strategy(supports=True, ce_result=None):
    emu = MagicMock()
    emu.get_supported_load_modes.return_value = (
        [ChannelLoadMode.PARAMETRIC_TDL] if supports else [ChannelLoadMode.EXTERNAL_WAVEFORM])
    ce_client = MagicMock()
    ce_client.cluster_b2_native = AsyncMock(
        return_value=ce_result if ce_result is not None else B2ClusterResult(
            success=True, target_path="B2_parametric", clustering_algo="geometric_native_fit",
            tap_params=[{"tap_index": 0}], note="待现场 Channel Studio"))
    return B2ParametricTdlStrategy(emu, ce_client, chamber_config=None, calibration_entries=[])


# ───────────── 枚举 (F6) ─────────────

def test_engine_mode_b2_exists():
    assert EngineMode.B2_PARAMETRIC_TDL.value == "b2_parametric_tdl"
    assert EngineMode("b2_parametric_tdl") is EngineMode.B2_PARAMETRIC_TDL


def test_channel_load_mode_parametric_tdl_exists():
    assert ChannelLoadMode.PARAMETRIC_TDL.value == "parametric_tdl"


# ───────────── 能力门 (F6) ─────────────

def test_capability_gate_rejects_unsupported_emulator():
    """仪器不支持 PARAMETRIC_TDL → 能力门 fail-loud, 不调 CE。"""
    strat = _strategy(supports=False)
    assert strat.supports_parametric_tdl() is False
    assert asyncio.run(strat.generate_and_load({}, {"rt_rays": _RAYS})) is False
    strat.ce_client.cluster_b2_native.assert_not_called()


# ───────────── RT 射线接线 (PR-5) ─────────────

def test_no_rt_rays_fails_loud_without_calling_ce():
    """无 rt_rays (真实 RT 需 RT-Release/现场) → fail-loud, 不调 CE、不臆造假子径。"""
    strat = _strategy()
    assert asyncio.run(strat.generate_and_load({}, {"model_name": "UMa CDL-C"})) is False
    strat.ce_client.cluster_b2_native.assert_not_called()


def test_rt_rays_calls_ce_returns_false_pending_onsite():
    """有 rt_rays → 调 CE cluster_b2_native (透传 rt_rays/freq/test_class); 参数表就绪但
    .tap 字节 + F64 加载现场 → generate_and_load 仍 False。"""
    strat = _strategy()
    ok = asyncio.run(strat.generate_and_load(
        {"frequency_hz": 3.5e9, "ue_velocity_mps": (10.0, 0.0, 0.0)},
        {"rt_rays": _RAYS, "test_class": "throughput_psd"}))
    strat.ce_client.cluster_b2_native.assert_called_once()
    call = strat.ce_client.cluster_b2_native.call_args.kwargs
    assert call["rt_rays"] == _RAYS
    assert call["center_frequency_hz"] == 3.5e9
    assert call["test_class"] == "throughput_psd"
    assert ok is False           # .tap 字节 + F64 加载现场


def test_ce_failure_fails():
    """CE 聚类/判决失败 (如 ESCALATE) → generate_and_load False。"""
    strat = _strategy(ce_result=B2ClusterResult(success=False, message="ESCALATE 需现场升级"))
    ok = asyncio.run(strat.generate_and_load(
        {"frequency_hz": 3.5e9}, {"rt_rays": _RAYS, "test_class": "beam_tracking"}))
    assert ok is False


# ───────────── caller 契约: measure 透传 (Codex P1 #169) ─────────────

def test_measure_forwards_b2_inputs_from_config_extra():
    """measure caller 必须把 TestCase config 的 rt_rays/test_class/f64_profile/velocity
    透传进 cdl_model_data, 否则 strategy 永远拿不到 rt_rays → fail-loud, B-2 路死
    (Codex P1 #169; feedback_helper_test_misses_caller_contract)。"""
    from app.services.mimo_ota.executors.measure import _extract_b2_cluster_inputs
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    cfg = MIMOOTAConfiguration.model_validate({
        "engine_mode": "b2_parametric_tdl",
        "rt_rays": _RAYS,
        "test_class": "beam_tracking",
        "f64_profile": {"has_gcm": True},
        "ue_velocity_mps": [12.0, 0.0, 0.0],
    })
    out = _extract_b2_cluster_inputs(cfg)
    assert out["rt_rays"] == _RAYS
    assert out["test_class"] == "beam_tracking"
    assert out["f64_profile"] == {"has_gcm": True}
    assert out["ue_velocity_mps"] == [12.0, 0.0, 0.0]


def test_measure_b2_inputs_default_when_absent():
    """config 无 B-2 extra (standard CDL 路) → rt_rays None (strategy fail-loud),
    test_class 缺省 throughput_psd = 设计预期 (V1.0 §3.3 (5)(6))。"""
    from app.services.mimo_ota.executors.measure import _extract_b2_cluster_inputs
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    cfg = MIMOOTAConfiguration.model_validate({"engine_mode": "b2_parametric_tdl"})
    out = _extract_b2_cluster_inputs(cfg)
    assert out["rt_rays"] is None          # → strategy fail-loud (设计预期)
    assert out["test_class"] == "throughput_psd"
    assert out["f64_profile"] is None
    assert out["ue_velocity_mps"] is None
