"""
Seed standard test case templates for MIMO OTA testing.

Based on 3GPP TR 37.977, CTIA OTA Test Plan, and internal VRT requirements.

Usage:
    cd api-service
    .venv/bin/python scripts/seed_test_cases.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase
from app.schemas.mimo_ota.config import MIMO_OTA_TEST_TYPE
from app.services.mimo_ota.legacy_migration import legacy_to_mimo_ota_config

MIMO_OTA_CATEGORY = "MIMO OTA 吞吐量"


def _resolve_default_lab_profile_id(db: Session):
    """Find the unique active LabProfile to attach to MIMO_OTA seed cases.

    Returns None if no active profile exists yet (the seed will still run,
    rows will get lab_profile_id=NULL and can be backfilled later).
    """
    profile = db.query(LabProfile).filter(LabProfile.is_active.is_(True)).first()
    return profile.id if profile else None


def _upgrade_to_mimo_ota(case_data: dict, lab_profile_id) -> dict:
    """Transform a legacy MIMO seed dict into a MIMO_OTA TestCase row spec."""
    upgraded = dict(case_data)
    upgraded["test_type"] = MIMO_OTA_TEST_TYPE
    upgraded["configuration"] = legacy_to_mimo_ota_config(case_data)
    if lab_profile_id is not None:
        upgraded["lab_profile_id"] = lab_profile_id
    # pass_criteria moves into configuration.pass_criteria; keep the column
    # mirror for backward-compat (e.g. TestCaseSummary.pass_criteria readers)
    upgraded["pass_criteria"] = upgraded["configuration"]["pass_criteria"]
    return upgraded


def get_test_cases():
    """Define all standard test case templates."""
    return [
        # ==================== Suite 1: TRP ====================
        {
            "name": "TRP 全球扫描 (Sub-6 GHz)",
            "description": "3GPP 标准全球面 TRP 测量，Sub-6 频段。θ=15°/φ=30° 步进，覆盖完整球面辐射方向图。",
            "test_type": "TRP",
            "is_template": True,
            "template_category": "TRP 全向辐射功率",
            "configuration": {
                "measurement_type": "TRP",
                "scan_type": "full_sphere",
                "theta_step_deg": 15,
                "phi_step_deg": 30,
                "polarization": "dual",
            },
            "pass_criteria": {"min_trp_dbm": 20.0, "max_trp_variation_db": 3.0},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 2700,
            "tags": ["TRP", "Sub-6", "3GPP"],
            "created_by": "system",
        },
        {
            "name": "TRP 全球扫描 (mmWave FR2)",
            "description": "毫米波频段 TRP 测量，高角度分辨率 θ=5°/φ=10°。",
            "test_type": "TRP",
            "is_template": True,
            "template_category": "TRP 全向辐射功率",
            "configuration": {
                "measurement_type": "TRP",
                "scan_type": "full_sphere",
                "theta_step_deg": 5,
                "phi_step_deg": 10,
                "polarization": "dual",
            },
            "pass_criteria": {"min_eirp_dbm": 22.4},
            "frequency_mhz": 26500,
            "bandwidth_mhz": 400,
            "test_duration_sec": 7200,
            "tags": ["TRP", "FR2", "mmWave"],
            "created_by": "system",
        },
        {
            "name": "TRP 上半球扫描",
            "description": "仅扫描上半球（θ=0~90°），用于车载天线快速评估。",
            "test_type": "TRP",
            "is_template": True,
            "template_category": "TRP 全向辐射功率",
            "configuration": {
                "measurement_type": "TRP",
                "scan_type": "upper_hemisphere",
                "theta_step_deg": 15,
                "phi_step_deg": 30,
            },
            "pass_criteria": {"min_trp_dbm": 18.0},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1200,
            "tags": ["TRP", "快速", "车载"],
            "created_by": "system",
        },
        # ==================== Suite 2: TIS ====================
        {
            "name": "TIS 全球扫描 (Sub-6 GHz)",
            "description": "3GPP 标准全球面 TIS 测量。目标吞吐量为峰值的 70%。",
            "test_type": "TIS",
            "is_template": True,
            "template_category": "TIS 全向灵敏度",
            "configuration": {
                "measurement_type": "TIS",
                "scan_type": "full_sphere",
                "target_throughput_pct": 70,
                "theta_step_deg": 15,
                "phi_step_deg": 30,
            },
            "pass_criteria": {"max_tis_dbm": -95.0},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 3600,
            "tags": ["TIS", "Sub-6", "3GPP"],
            "created_by": "system",
        },
        {
            "name": "TIS 部分球面 (N41)",
            "description": "N41 频段部分球面 TIS 测量，快速灵敏度评估。",
            "test_type": "TIS",
            "is_template": True,
            "template_category": "TIS 全向灵敏度",
            "configuration": {
                "measurement_type": "TIS",
                "scan_type": "partial_sphere",
                "target_throughput_pct": 70,
            },
            "pass_criteria": {"max_tis_dbm": -93.0},
            "frequency_mhz": 2600,
            "bandwidth_mhz": 60,
            "test_duration_sec": 1800,
            "tags": ["TIS", "N41"],
            "created_by": "system",
        },
        # ==================== Suite 3: MIMO OTA Throughput ====================
        {
            "name": "2x2 MIMO 吞吐量 - UMi LOS",
            "description": "3GPP TR 37.977 标准 MIMO OTA 吞吐量测试。UMi 视距信道，2T4R 配置。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "MIMO OTA 吞吐量",
            "channel_model": "UMi-LOS",
            "channel_parameters": {"mimo_config": "2T4R", "speed_kmh": 3, "correlation": "low"},
            "configuration": {
                "mimo_config": "2T4R",
                "target_throughput_mbps": 200,
                "num_base_stations": 1,
                "power_sweep": False,
            },
            "pass_criteria": {"min_throughput_mbps": 100, "max_bler": 0.1, "min_rsrp_dbm": -100},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1800,
            "tags": ["MIMO", "5G NR", "3GPP 37.977", "UMi"],
            "created_by": "system",
        },
        {
            "name": "2x2 MIMO 吞吐量 - UMa NLOS",
            "description": "UMa 非视距信道下的 MIMO 吞吐量测试，评估多径环境性能。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "MIMO OTA 吞吐量",
            "channel_model": "UMa-NLOS",
            "channel_parameters": {"mimo_config": "2T4R", "speed_kmh": 30, "correlation": "medium"},
            "configuration": {
                "mimo_config": "2T4R",
                "target_throughput_mbps": 150,
                "num_base_stations": 1,
            },
            "pass_criteria": {"min_throughput_mbps": 70, "max_bler": 0.1},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1800,
            "tags": ["MIMO", "5G NR", "UMa", "NLOS"],
            "created_by": "system",
        },
        {
            "name": "4x4 MIMO 吞吐量 - CDL-A",
            "description": "CDL-A 信道模型下的 4x4 MIMO 高阶空间复用测试。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "MIMO OTA 吞吐量",
            "channel_model": "CDL-A",
            "channel_parameters": {"mimo_config": "4T8R", "delay_spread_ns": 300},
            "configuration": {"mimo_config": "4T8R", "target_throughput_mbps": 400},
            "pass_criteria": {"min_throughput_mbps": 200, "max_bler": 0.1},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 2700,
            "tags": ["MIMO", "4x4", "CDL-A"],
            "created_by": "system",
        },
        {
            "name": "4x4 MIMO 吞吐量 - CDL-C",
            "description": "CDL-C 信道模型（室内热点场景）下的 4x4 MIMO 测试。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "MIMO OTA 吞吐量",
            "channel_model": "CDL-C",
            "channel_parameters": {"mimo_config": "4T8R", "delay_spread_ns": 100},
            "configuration": {"mimo_config": "4T8R", "target_throughput_mbps": 500},
            "pass_criteria": {"min_throughput_mbps": 250},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 2700,
            "tags": ["MIMO", "4x4", "CDL-C", "InH"],
            "created_by": "system",
        },
        {
            "name": "MIMO 多普勒扫描",
            "description": "在 3/30/120 km/h 三个速度点测量 MIMO 吞吐量，评估多普勒影响。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "MIMO OTA 吞吐量",
            "channel_model": "UMa",
            "channel_parameters": {"mimo_config": "2T4R", "speed_sweep_kmh": [3, 30, 120]},
            "configuration": {"mimo_config": "2T4R", "sweep_type": "doppler"},
            "pass_criteria": {"min_throughput_mbps": 50},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 5400,
            "tags": ["MIMO", "多普勒", "速度扫描"],
            "created_by": "system",
        },
        {
            "name": "MIMO 功率扫描",
            "description": "在 -70 ~ -100 dBm 范围内扫描下行功率，绘制吞吐量-SNR 曲线。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "MIMO OTA 吞吐量",
            "channel_model": "CDL-A",
            "channel_parameters": {"mimo_config": "2T4R"},
            "configuration": {
                "mimo_config": "2T4R",
                "sweep_type": "power",
                "power_range_dbm": [-70, -75, -80, -85, -90, -95, -100],
            },
            "pass_criteria": {"min_throughput_at_minus90": 30},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 3600,
            "tags": ["MIMO", "功率扫描", "SNR曲线"],
            "created_by": "system",
        },
        # ==================== Suite 4: Channel Validation ====================
        {
            "name": "静区纹波验证",
            "description": "验证静区内幅度纹波是否满足 ±1 dB 指标，确保测试区域场均匀性。",
            "test_type": "ChannelModel",
            "is_template": True,
            "template_category": "信道模型验证",
            "configuration": {
                "validation_type": "quiet_zone_ripple",
                "target_ripple_db": 1.0,
                "scan_points": 9,
            },
            "pass_criteria": {"max_ripple_db": 1.0},
            "frequency_mhz": 3500,
            "test_duration_sec": 1200,
            "tags": ["校验", "静区", "QZ"],
            "created_by": "system",
        },
        {
            "name": "空间相关性验证",
            "description": "验证合成信道的空间相关矩阵与目标模型的偏差。",
            "test_type": "ChannelModel",
            "is_template": True,
            "template_category": "信道模型验证",
            "configuration": {
                "validation_type": "spatial_correlation",
                "reference_model": "UMa-NLOS",
            },
            "pass_criteria": {"max_correlation_error": 0.15},
            "frequency_mhz": 3500,
            "test_duration_sec": 1800,
            "tags": ["校验", "相关性"],
            "created_by": "system",
        },
        {
            "name": "多普勒谱验证",
            "description": "验证合成信道的多普勒功率谱密度与理论 Jakes 谱的匹配度。",
            "test_type": "ChannelModel",
            "is_template": True,
            "template_category": "信道模型验证",
            "configuration": {"validation_type": "doppler_psd", "target_speed_kmh": 30},
            "pass_criteria": {"max_psd_error_db": 2.0},
            "frequency_mhz": 3500,
            "test_duration_sec": 900,
            "tags": ["校验", "多普勒"],
            "created_by": "system",
        },
        {
            "name": "功率时延谱验证",
            "description": "验证合成信道的 PDP 与目标信道模型的时延扩展匹配。",
            "test_type": "ChannelModel",
            "is_template": True,
            "template_category": "信道模型验证",
            "configuration": {"validation_type": "power_delay_profile"},
            "pass_criteria": {"max_pdp_error_db": 3.0},
            "frequency_mhz": 3500,
            "test_duration_sec": 900,
            "tags": ["校验", "PDP"],
            "created_by": "system",
        },
        # ==================== Suite 5: Beam Management ====================
        {
            "name": "SSB 波束扫描",
            "description": "5G NR SSB 初始接入波束扫描，验证最优波束选择正确性。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "波束管理",
            "configuration": {
                "test_subtype": "beam_management",
                "beam_procedure": "ssb_sweep",
                "num_ssb_beams": 8,
            },
            "pass_criteria": {"min_beam_detection_rate": 0.95},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1200,
            "tags": ["波束", "SSB", "5G NR"],
            "created_by": "system",
        },
        {
            "name": "CSI-RS 波束精细化",
            "description": "基于 CSI-RS 的波束精细化测试，验证 CSI 反馈精度。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "波束管理",
            "configuration": {
                "test_subtype": "beam_management",
                "beam_procedure": "csi_rs_refinement",
            },
            "pass_criteria": {"min_cqi_accuracy": 0.9},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1500,
            "tags": ["波束", "CSI-RS"],
            "created_by": "system",
        },
        {
            "name": "波束恢复 (BFR)",
            "description": "波束失败检测与恢复测试，验证 BFR 触发时延和成功率。",
            "test_type": "MIMO",
            "is_template": True,
            "template_category": "波束管理",
            "configuration": {
                "test_subtype": "beam_management",
                "beam_procedure": "beam_failure_recovery",
            },
            "pass_criteria": {"min_bfr_success_rate": 0.95, "max_bfr_latency_ms": 50},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 900,
            "tags": ["波束", "BFR"],
            "created_by": "system",
        },
        # ==================== Suite 6: VRT ====================
        {
            "name": "VRT 城市道路驾驶",
            "description": "虚拟路测 - 城市宏蜂窝场景，3 基站覆盖，30 km/h 行驶。",
            "test_type": "Throughput",
            "is_template": True,
            "template_category": "虚拟路测",
            "channel_model": "UMa",
            "configuration": {
                "scenario_type": "urban",
                "num_base_stations": 3,
                "speed_kmh": 30,
                "route_distance_m": 5000,
                "enable_handover": True,
            },
            "pass_criteria": {"min_throughput_mbps": 50, "max_latency_ms": 50, "min_rsrp_dbm": -110},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1800,
            "tags": ["VRT", "城市", "切换"],
            "created_by": "system",
        },
        {
            "name": "VRT 高速公路驾驶",
            "description": "虚拟路测 - 农村宏蜂窝场景，2 基站，120 km/h 高速行驶。",
            "test_type": "Throughput",
            "is_template": True,
            "template_category": "虚拟路测",
            "channel_model": "RMa",
            "configuration": {
                "scenario_type": "highway",
                "num_base_stations": 2,
                "speed_kmh": 120,
                "route_distance_m": 10000,
                "enable_handover": True,
            },
            "pass_criteria": {"min_throughput_mbps": 30, "min_rsrp_dbm": -115},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1200,
            "tags": ["VRT", "高速", "高多普勒"],
            "created_by": "system",
        },
        {
            "name": "VRT 城市密集区",
            "description": "虚拟路测 - 城市微蜂窝密集部署，5 基站，低速行驶。",
            "test_type": "Throughput",
            "is_template": True,
            "template_category": "虚拟路测",
            "channel_model": "UMi",
            "configuration": {
                "scenario_type": "dense_urban",
                "num_base_stations": 5,
                "speed_kmh": 15,
                "route_distance_m": 3000,
                "enable_handover": True,
            },
            "pass_criteria": {"min_throughput_mbps": 100, "max_latency_ms": 20},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 2700,
            "tags": ["VRT", "密集", "UMi"],
            "created_by": "system",
        },
        {
            "name": "VRT 混合环境",
            "description": "虚拟路测 - UMa+UMi 混合环境，4 基站，多场景切换。",
            "test_type": "Throughput",
            "is_template": True,
            "template_category": "虚拟路测",
            "channel_model": "UMa+UMi",
            "configuration": {
                "scenario_type": "mixed",
                "num_base_stations": 4,
                "speed_kmh": 40,
                "route_distance_m": 8000,
            },
            "pass_criteria": {"min_throughput_mbps": 40},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 2400,
            "tags": ["VRT", "混合"],
            "created_by": "system",
        },
        {
            "name": "VRT 隧道进出",
            "description": "虚拟路测 - 模拟隧道进出场景，InH→UMa 信道切换。",
            "test_type": "Throughput",
            "is_template": True,
            "template_category": "虚拟路测",
            "channel_model": "InH→UMa",
            "configuration": {
                "scenario_type": "tunnel",
                "num_base_stations": 2,
                "speed_kmh": 60,
                "route_distance_m": 2000,
            },
            "pass_criteria": {"max_interruption_ms": 200},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 900,
            "tags": ["VRT", "隧道", "中断恢复"],
            "created_by": "system",
        },
        # ==================== Suite 7: Handover ====================
        {
            "name": "同频切换测试",
            "description": "同频小区间切换成功率和中断时间测量。",
            "test_type": "Handover",
            "is_template": True,
            "template_category": "切换测试",
            "configuration": {
                "handover_type": "intra_frequency",
                "num_handovers": 20,
                "speed_kmh": 30,
            },
            "pass_criteria": {"min_success_rate": 0.98, "max_interruption_ms": 50},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1800,
            "tags": ["切换", "同频"],
            "created_by": "system",
        },
        {
            "name": "异频切换测试",
            "description": "异频小区间切换（N78→N41），评估频段间切换性能。",
            "test_type": "Handover",
            "is_template": True,
            "template_category": "切换测试",
            "configuration": {
                "handover_type": "inter_frequency",
                "source_freq_mhz": 3500,
                "target_freq_mhz": 2600,
                "num_handovers": 10,
            },
            "pass_criteria": {"min_success_rate": 0.95, "max_interruption_ms": 100},
            "frequency_mhz": 3500,
            "bandwidth_mhz": 100,
            "test_duration_sec": 1200,
            "tags": ["切换", "异频", "N78→N41"],
            "created_by": "system",
        },
    ]


def seed_test_cases():
    """Seed test case templates into database."""
    db: Session = SessionLocal()
    try:
        existing = db.query(TestCase).filter(TestCase.is_template == True).count()
        if existing > 0:
            print(f"⚠️  已有 {existing} 个模板测试用例，跳过初始化。")
            print("   如需重新初始化，请先清空 test_cases 表中 is_template=True 的记录。")
            return

        cases = get_test_cases()
        lab_profile_id = _resolve_default_lab_profile_id(db)
        if lab_profile_id is None:
            print("⚠️  无活跃 LabProfile,MIMO_OTA 用例的 lab_profile_id 将为 NULL")
            print("   建议先跑 scripts/seed_caict_lab_profile.py 再回头跑此脚本")

        upgraded_count = 0
        for case_data in cases:
            if case_data.get("template_category") == MIMO_OTA_CATEGORY:
                case_data = _upgrade_to_mimo_ota(case_data, lab_profile_id)
                upgraded_count += 1
            tc = TestCase(**case_data)
            db.add(tc)

        db.commit()
        print(f"✅ 成功创建 {len(cases)} 个标准测试用例模板 (其中 {upgraded_count} 个升级到 MIMO_OTA schema)\n")

        # Print summary by category
        from collections import Counter
        categories = Counter(c["template_category"] for c in cases)
        for cat, count in categories.items():
            print(f"   📁 {cat}: {count} 个用例")

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_test_cases()
