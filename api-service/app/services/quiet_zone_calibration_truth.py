"""Read-time truth projection for legacy quiet-zone calibration rows.

历史行（本层立层时的全部行）出自 mock/random 写方、先于显式 real provenance
契约，所以按 UNKNOWN/N/A 投影：保留配置/审计身份，不把网格样本、工程值、
有效期、判决当正式证据放出。

⚠ P1-71 起该前提**不再对未来行成立**：QZ 并轨后
`quiet_zone_validation_service` 的 real 路径（今天在网格取数前 fail-closed，
等 XY 场扫描平台）会向 ChannelQuietZoneCalibration 写入带
`measurement_grid.provenance.measurement_method == "ce_sa"` 的真实行。
**激活批的硬前置**：先教会本层按行内 provenance 分流（真行放行、legacy 行
维持 UNKNOWN），否则真实证据会被这里无条件吞掉 —— 三个 sanitizer 都要改，
calibration_orchestrator 的 QUIET_ZONE_UNIFORMITY 状态分支同步。
"""

from typing import Any, Dict


def sanitize_channel_qz_detail(calibration: Any) -> Dict[str, Any]:
    """Project a legacy ChannelQuietZoneCalibration as UNKNOWN/N/A."""
    return {
        "id": calibration.id,
        "session_id": calibration.session_id,
        "quiet_zone_shape": calibration.quiet_zone_shape,
        "quiet_zone_diameter_m": calibration.quiet_zone_diameter_m,
        "quiet_zone_height_m": calibration.quiet_zone_height_m,
        "field_probe_type": calibration.field_probe_type,
        "field_probe_size_mm": calibration.field_probe_size_mm,
        "measurement_grid": {},
        "num_points": 0,
        "amplitude_mean_db": None,
        "amplitude_std_db": None,
        "amplitude_range_db": None,
        "phase_mean_deg": None,
        "phase_std_deg": None,
        "phase_range_deg": None,
        "amplitude_uniformity_pass": None,
        "phase_uniformity_pass": None,
        "validation_pass": None,
        "amplitude_threshold_db": calibration.amplitude_threshold_db,
        "phase_threshold_deg": calibration.phase_threshold_deg,
        "fc_ghz": calibration.fc_ghz,
        "calibrated_at": calibration.calibrated_at,
        "calibrated_by": calibration.calibrated_by,
        "valid_until": None,
        "status": "unknown",
    }


def sanitize_channel_qz_history(calibration: Any) -> Dict[str, Any]:
    """Project a legacy QZ row for history/status consumers."""
    return {
        "calibration_id": calibration.id,
        "calibration_type": "quiet_zone",
        "calibrated_at": calibration.calibrated_at,
        "calibrated_by": calibration.calibrated_by,
        "status": "unknown",
        "validation_pass": None,
        "summary": {
            "shape": calibration.quiet_zone_shape,
            "diameter_m": calibration.quiet_zone_diameter_m,
            "formal_status": "UNKNOWN",
            "amplitude_std_db": None,
        },
    }


def sanitize_channel_qz_report(calibration: Any) -> Dict[str, Any]:
    """Retain row identity in reports while excluding all untrusted values."""
    return {
        "id": str(calibration.id),
        "quiet_zone_shape": calibration.quiet_zone_shape,
        "quiet_zone_diameter_m": calibration.quiet_zone_diameter_m,
        "fc_ghz": calibration.fc_ghz,
        "validation_pass": None,
        "formal_status": "UNKNOWN",
        "calibrated_at": (
            str(calibration.calibrated_at) if calibration.calibrated_at else None
        ),
        "amplitude_uniformity_db": None,
        "phase_uniformity_deg": None,
    }
