"""P2-15 S2: CustomCDLProfile 簇 → CDLCluster 装配 + input_mode=custom payload 透传。

装配 cdl_clusters_from_profile_dicts 把 profile 的 JSONB 簇 (power_linear 命名 + num_rays)
映射成 client CDLCluster (power_relative_linear), 经 _build_payload(input_mode=custom) 透传。
"""
import uuid

from app.models.chamber import ChamberConfiguration
from app.services.channel_engine_client import (
    AntennaConfig,
    ChannelEngineClient,
    cdl_clusters_from_profile_dicts,
)


def test_field_mapping_power_and_num_rays():
    cs = cdl_clusters_from_profile_dicts([{
        "delay_s": 1e-7, "power_linear": 0.5, "aoa_deg": 30.0, "aod_deg": 10.0,
        "zoa_deg": 85.0, "zod_deg": 88.0, "as_aoa_deg": 1.0, "as_zoa_deg": 3.0,
        "xpr_db": 9.0, "initial_phases_rad": [0.1, 0.2, 0.3, 0.4], "num_rays": 10,
    }])
    assert len(cs) == 1
    c = cs[0]
    assert c.power_relative_linear == 0.5        # power_linear → power_relative_linear
    assert c.delay_s == 1e-7 and c.aoa_deg == 30.0 and c.zoa_deg == 85.0
    assert c.as_zoa_deg == 3.0 and c.xpr_db == 9.0
    assert c.initial_phases_rad == [0.1, 0.2, 0.3, 0.4]
    assert c.num_rays == 10


def test_defaults_xpr_num_rays_zenith():
    cs = cdl_clusters_from_profile_dicts([
        {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 0.0, "aod_deg": 0.0}])
    assert cs[0].xpr_db == 7.0        # None → 38.901 默认
    assert cs[0].num_rays == 20       # 默认
    assert cs[0].zoa_deg == 90.0      # 默认水平面


def _payload_with_clusters(clusters):
    client = ChannelEngineClient(db=None)
    chamber = ChamberConfiguration(
        id=uuid.uuid4(), name="s2-test", chamber_type="type_a",
        chamber_radius_m=1.5, quiet_zone_diameter_m=0.6, num_probes=16,
        num_polarizations=2, num_rings=4, is_system_preset=False, is_active=True,
    )
    return client._build_payload(
        chamber=chamber, calibration_entries=[], frequency_hz=3.5e9,
        clusters=clusters, cdl_model_name="custom", pathloss_db=90.0, is_los=False,
        tx_antenna=AntennaConfig(polarization="V"),
        rx_antenna=AntennaConfig(polarization="H"),
        target_tx_power_dbm=0.0, target_rsrp_dbm=-85.0, target_snr_db=20.0,
        ue_velocity_kph=15.0, ue_velocity_mps=[4.17, 0.0, 0.0], k_factor_db=None,
        synthesis_method="strict_pfs", input_mode="custom",
    )


def test_payload_custom_carries_num_rays_and_power():
    """装配的 custom 簇 → _build_payload(input_mode=custom) → clusters 透传
    num_rays (P2-15 新加, 不再丢) + power_relative_linear。"""
    cs = cdl_clusters_from_profile_dicts([{
        "delay_s": 0.0, "power_linear": 0.7, "aoa_deg": 5.0, "aod_deg": 2.0, "num_rays": 12,
    }])
    p = _payload_with_clusters(cs)
    assert p["input_mode"] == "custom"
    c0 = p["cdl_model_data"]["clusters"][0]
    assert c0["num_rays"] == 12                   # P2-15: num_rays 透传
    assert c0["power_relative_linear"] == 0.7
