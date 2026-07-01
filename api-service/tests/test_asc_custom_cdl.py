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


def _channel_asset():
    a = MagicMock()
    a.name = "CA-custom"
    a.center_frequency_hz = 3.5e9
    a.is_los = False
    a.k_factor_db = None
    a.ue_velocity_mps = [5.0, 0.0, 0.0]
    a.payload = {"pathloss_db": 88.0}  # ChannelAsset 顶层无 pathloss_db, 在 payload
    return a


def test_channel_asset_clusters_branch():
    """P2-16 S2: cdl_model_data['clusters'] → _synthesize_from_clusters (不查 CustomCDLProfile 表)。"""
    strat = _strategy()
    clusters = [{"delay_s": 0.0, "power_linear": 0.7, "aoa_deg": 45, "aod_deg": 12, "num_rays": 16}]
    with patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"clusters": clusters, "channel_asset": _channel_asset()}))
    assert ok is True
    call = strat.ce_client.synthesize_hardware_pipeline.call_args.kwargs
    assert call["input_mode"] == "custom"
    # P2-16 S3-3: ChannelAsset custom_static 升路由到标注式 B-1 烘焙脊 (S3-1, #176 golden
    # 证与 legacy 逐位等价)。legacy cdl_profile_id 路保持 legacy (见下个测试)。
    assert call["routing_mode"] == "annotated_b1"
    assert call["cdl_model_name"] == "CA-custom"
    assert len(call["clusters"]) == 1
    assert call["clusters"][0].power_relative_linear == 0.7  # power_linear → power_relative_linear
    assert call["clusters"][0].num_rays == 16
    assert call["pathloss_db"] == 88.0          # 从 payload (ChannelAsset 顶层无此字段)
    assert call["ue_velocity_mps"] == [5.0, 0.0, 0.0]
    assert call["frequency_hz"] == 3.5e9        # 频率门: asset==TestCase, 一致


def test_channel_asset_clusters_frequency_mismatch_fails():
    """clusters 路也走共用频率门 (_check_custom_physical_gates): asset center_frequency ≠
    TestCase → fail-loud。直接调 _synthesize_from_clusters (generate_and_load 的 try/except
    会把 ValueError catch 成 return False, 测门本身须绕过)。"""
    import pytest
    strat = _strategy()
    ca = _channel_asset()
    ca.center_frequency_hz = 2.6e9  # ≠ TestCase 3.5e9
    with pytest.raises(ValueError, match="测量污染"):
        asyncio.run(strat._synthesize_from_clusters(
            [{"delay_s": 0, "power_linear": 1, "aoa_deg": 1, "aod_deg": 1}],
            ca, {"frequency_hz": 3.5e9}, "sess"))


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
    # P2-16 S3-3: legacy cdl_profile_id 路保持 legacy 路由 (不升 annotated_b1), 待 S4
    # deprecate; 仅 ChannelAsset custom_static 路升脊。
    assert call.get("routing_mode", "legacy") != "annotated_b1"
    assert call["frequency_hz"] == 3.5e9       # 频率用 TestCase (profile==TestCase, 一致)
    assert call["cdl_model_name"] == "UMa-改"
    assert len(call["clusters"]) == 1
    assert call["clusters"][0].power_relative_linear == 0.5   # power_linear → power_relative_linear
    assert call["clusters"][0].num_rays == 12
    assert call["pathloss_db"] == 90.0
    assert call["ue_velocity_mps"] == [10.0, 0.0, 0.0]


def test_cdl_profile_id_redirects_to_channel_asset():
    """P2-16 deprecate-legacy (消费收敛): cdl_profile_id 命中同 id custom_static ChannelAsset →
    走 ChannelAsset payload (annotated_b1 脊 + ChannelAsset 簇/name/pathloss), **不读** legacy
    custom_cdl_profiles。证 ChannelAsset 是收敛后单一真值源 (工作台编辑落这里, 消除双副本 stale)。"""
    strat = _strategy()
    ca = _channel_asset()
    ca.source_type = "custom_static"
    ca.payload = {"snapshots": [{"clusters": [
        {"delay_s": 0.0, "power_linear": 0.9, "aoa_deg": 77, "aod_deg": 5, "num_rays": 20},
    ]}], "pathloss_db": 85.0}
    legacy = _profile()          # 故意不同 (name/簇/pathloss) — 若误读 legacy 断言会失败
    legacy.pathloss_db = 999.0
    with patch("app.services.channel_asset_service.find_custom_static_asset", return_value=ca), \
         patch("app.services.custom_cdl_profile_service.get_custom_cdl_profile", return_value=legacy), \
         patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"cdl_profile_id": "11111111-1111-1111-1111-111111111111"}))
    assert ok is True
    call = strat.ce_client.synthesize_hardware_pipeline.call_args.kwargs
    assert call["routing_mode"] == "annotated_b1"           # ChannelAsset 路 (非 legacy)
    assert call["cdl_model_name"] == "CA-custom"            # ChannelAsset name (非 legacy "UMa-改")
    assert len(call["clusters"]) == 1
    assert call["clusters"][0].power_relative_linear == 0.9  # ChannelAsset 簇 (非 legacy 0.5)
    assert call["pathloss_db"] == 85.0                      # ChannelAsset payload (非 legacy 999)


def test_cdl_profile_id_no_channel_asset_falls_back_to_legacy():
    """未迁移的 legacy-only profile (find_custom_static_asset→None) → 仍读旧表 custom_cdl_profiles
    (向后兼容, legacy 路由不升 annotated_b1)。"""
    strat = _strategy()
    with patch("app.services.channel_asset_service.find_custom_static_asset", return_value=None), \
         patch("app.services.custom_cdl_profile_service.get_custom_cdl_profile",
               return_value=_profile()), patch("os.path.exists", return_value=True):
        ok = asyncio.run(strat.generate_and_load(
            {"frequency_hz": 3.5e9},
            {"cdl_profile_id": "11111111-1111-1111-1111-111111111111"}))
    assert ok is True
    call = strat.ce_client.synthesize_hardware_pipeline.call_args.kwargs
    assert call.get("routing_mode", "legacy") != "annotated_b1"   # legacy 路
    assert call["cdl_model_name"] == "UMa-改"                     # legacy profile name
    assert call["pathloss_db"] == 90.0                           # legacy profile pathloss


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
