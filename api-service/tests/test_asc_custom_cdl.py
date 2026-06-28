"""P2-15 S4: ASC strategy custom CDL 分支 — cdl_profile_id → 查 profile → input_mode=custom。

cdl_model_data 带 cdl_profile_id → _synthesize_custom_cdl 查 CustomCDLProfile + 装配簇 →
synthesize(input_mode=custom); 无 cdl_profile_id → standard 38.901 路 (不变)。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.channel_generation.asc_strategy import ExternalWaveformStrategy


def _strategy():
    emu = MagicMock()
    emu.load_channel = AsyncMock(return_value=True)
    ce_client = MagicMock()
    ce_client.db = MagicMock()
    result = MagicMock()
    result.success = True
    result.asc_files_path = "/tmp/custom_cdl.zip"
    ce_client.synthesize_hardware_pipeline = AsyncMock(return_value=result)
    chamber = MagicMock()
    chamber.id = "chamber-1"
    return ExternalWaveformStrategy(emu, ce_client, chamber_config=chamber, calibration_entries=[])


def _profile():
    p = MagicMock()
    p.name = "UMa-改"
    p.clusters = [
        {"delay_s": 0.0, "power_linear": 0.5, "aoa_deg": 30, "aod_deg": 10, "num_rays": 12},
    ]
    p.center_frequency_hz = 3.5e9
    p.pathloss_db = 90.0
    p.is_los = False
    p.k_factor_db = None
    p.ue_velocity_mps = [10.0, 0.0, 0.0]
    return p


def test_custom_cdl_branch_input_mode_custom():
    """cdl_profile_id → 查 profile + 装配簇 → input_mode=custom + 簇映射透传。"""
    strat = _strategy()
    with patch("app.services.custom_cdl_profile_service.get_custom_cdl_profile",
               return_value=_profile()), patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"cdl_profile_id": "11111111-1111-1111-1111-111111111111"}))
    assert ok is True
    call = strat.ce_client.synthesize_hardware_pipeline.call_args.kwargs
    assert call["input_mode"] == "custom"
    assert call["frequency_hz"] == 3.5e9       # 频率用 TestCase (profile==TestCase, 一致)
    assert call["cdl_model_name"] == "UMa-改"
    assert len(call["clusters"]) == 1
    assert call["clusters"][0].power_relative_linear == 0.5   # power_linear → power_relative_linear
    assert call["clusters"][0].num_rays == 12
    assert call["pathloss_db"] == 90.0
    assert call["ue_velocity_mps"] == [10.0, 0.0, 0.0]


def test_standard_branch_when_no_profile_id():
    """无 cdl_profile_id → standard 38.901 路 (input_mode=standard)。"""
    strat = _strategy()
    with patch("os.path.exists", return_value=True):
        asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9}, {"model_name": "UMa NLOS CDL-C"}))
    call = strat.ce_client.synthesize_hardware_pipeline.call_args.kwargs
    assert call["input_mode"] == "standard"
    assert call.get("clusters") is None


def test_custom_cdl_frequency_mismatch_fails_loud():
    """profile.center_frequency_hz ≠ TestCase frequency_hz → fail-loud, 不合成 (Codex P1 #171:
    防波形在 profile 频率合成+校准、系统按 TestCase 频率跑 → 测量污染)。"""
    strat = _strategy()
    p = _profile()
    p.center_frequency_hz = 2.6e9          # ≠ TestCase 3.5e9
    with patch("app.services.custom_cdl_profile_service.get_custom_cdl_profile",
               return_value=p), patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"cdl_profile_id": "11111111-1111-1111-1111-111111111111"}))
    assert ok is False
    strat.ce_client.synthesize_hardware_pipeline.assert_not_called()  # raise 在 synthesize 前


def test_is_los_null_with_kfactor_fails_loud():
    """is_los 未声明 (null) + k_factor 设了 → 矛盾 fail-loud (Codex P2 #171: K-factor 仅 LOS 有意义)。"""
    strat = _strategy()
    p = _profile()
    p.is_los = None
    p.k_factor_db = 10.0
    with patch("app.services.custom_cdl_profile_service.get_custom_cdl_profile",
               return_value=p), patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"cdl_profile_id": "11111111-1111-1111-1111-111111111111"}))
    assert ok is False
    strat.ce_client.synthesize_hardware_pipeline.assert_not_called()


def test_is_los_null_no_kfactor_defaults_nlos():
    """is_los null + 无 k_factor → 默认 NLOS (is_los=False), 合成正常 (Codex P2 #171)。"""
    strat = _strategy()
    p = _profile()
    p.is_los = None
    p.k_factor_db = None
    with patch("app.services.custom_cdl_profile_service.get_custom_cdl_profile",
               return_value=p), patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"cdl_profile_id": "11111111-1111-1111-1111-111111111111"}))
    assert ok is True
    assert strat.ce_client.synthesize_hardware_pipeline.call_args.kwargs["is_los"] is False
