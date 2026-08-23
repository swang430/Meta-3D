"""Read-time truth projection for legacy quiet-zone calibration rows.

Both existing QZ tables predate an explicit-real provenance contract and were
populated by mock/random writers.  Preserve their configuration/audit identity,
but never disclose their grid samples, engineering values, validity, or verdict
as formal evidence.
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
