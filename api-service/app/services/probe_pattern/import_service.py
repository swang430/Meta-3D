"""ProbePattern import orchestration: file → parser → DB row.

调用方提供文件原始内容 + 业务元数据 (probe_id, polarization, frequency_mhz,
vendor/model/serial); 本服务负责:
  1. 选 parser (按 file_format 或 filename 自动探测)
  2. 解析为 ParsedPattern
  3. 验证 + 计算 hpbw/front-to-back ratio (parser 没给的话)
  4. 写一行 ProbePattern, source="vendor_datasheet"

幂等: 同一 (probe_id, polarization, frequency_mhz, source, probe_serial) 已存在
有效记录时, 默认 invalidate 旧记录, 写新记录(可通过 replace_existing=False 关闭)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePattern,
)
from app.services.probe_pattern.parsers import (
    ParsedPattern,
    detect_format_from_filename,
    get_parser,
)

logger = logging.getLogger("app.calibration.probe_pattern_import")

# Phase 2a-import: vendor datasheet 默认有效期 (12 个月; 厂家 typical re-cal cycle)
VENDOR_PATTERN_VALIDITY_DAYS = 365


@dataclass
class ImportResult:
    success: bool
    pattern_id: Optional[str] = None
    invalidated_id: Optional[str] = None
    peak_gain_dbi: Optional[float] = None
    peak_azimuth_deg: Optional[float] = None
    peak_elevation_deg: Optional[float] = None
    hpbw_azimuth_deg: Optional[float] = None
    hpbw_elevation_deg: Optional[float] = None
    front_to_back_ratio_db: Optional[float] = None
    num_az_points: int = 0
    num_el_points: int = 0
    warnings: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def import_probe_pattern(
    db: Session,
    *,
    chamber_id: UUID,
    file_content: bytes | str,
    filename: str,
    probe_id: int,
    polarization: str,
    frequency_mhz: float,
    file_format: Optional[str] = None,
    probe_model: Optional[str] = None,
    probe_vendor: Optional[str] = None,
    probe_serial: Optional[str] = None,
    measured_by: str = "vendor_datasheet_import",
    raw_data_file_path: Optional[str] = None,
    replace_existing: bool = True,
) -> ImportResult:
    """Parse an uploaded pattern file and persist as a ProbePattern row.

    Args:
        file_content: raw file bytes or string
        filename: original filename (used for format auto-detect if file_format is None)
        probe_id / polarization / frequency_mhz: identifies which physical probe
            this pattern characterizes
        file_format: 'ticra_cut' | 'csv' | 'json' | None for auto-detect
        probe_model / probe_vendor / probe_serial: vendor metadata for traceability
        measured_by: written into ProbePattern.measured_by (operator name typical)
        raw_data_file_path: optional pointer to where the raw file is archived
            (e.g., on a shared file server); not strictly required
        replace_existing: True → mark prior valid pattern for same key as INVALIDATED
            and create new row; False → keep old, append new (rarely useful)

    Returns:
        ImportResult with pattern_id and key derived stats on success.
    """
    # 1. Resolve format
    fmt = file_format or detect_format_from_filename(filename)
    if fmt is None:
        return ImportResult(
            success=False,
            error=(
                f"Cannot determine format for '{filename}'; pass file_format explicitly "
                f"(supported: ticra_cut / csv / json)"
            ),
        )

    # 2. Parse
    try:
        parser = get_parser(fmt)
        parsed: ParsedPattern = parser.parse(file_content)
    except (ValueError, KeyError) as e:
        logger.error("Pattern parse failed: %s", e)
        return ImportResult(success=False, error=f"Parse error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected parser failure")
        return ImportResult(success=False, error=f"Unexpected parser error: {e}")

    # 3. Derive HPBW / front-to-back if parser didn't provide
    if parsed.hpbw_azimuth_deg is None:
        parsed.hpbw_azimuth_deg = _estimate_hpbw_azimuth(parsed)
    if parsed.hpbw_elevation_deg is None:
        parsed.hpbw_elevation_deg = _estimate_hpbw_elevation(parsed)
    if parsed.front_to_back_ratio_db is None:
        parsed.front_to_back_ratio_db = _estimate_front_to_back(parsed)

    # 4. Invalidate prior matching pattern if replace_existing
    invalidated_id = None
    if replace_existing:
        prior = (
            db.query(ProbePattern)
            .filter(
                ProbePattern.probe_id == probe_id,
                ProbePattern.chamber_id == chamber_id,
                ProbePattern.polarization == polarization,
                ProbePattern.frequency_mhz == frequency_mhz,
                ProbePattern.status == CalibrationStatus.VALID.value,
            )
            .first()
        )
        if prior is not None:
            prior.status = CalibrationStatus.INVALIDATED.value
            invalidated_id = str(prior.id)
            logger.info(
                "Invalidating prior ProbePattern %s for probe=%d pol=%s freq=%.0f MHz",
                prior.id, probe_id, polarization, frequency_mhz,
            )

    # 5. Persist
    now = datetime.utcnow()
    pattern = ProbePattern(
        chamber_id=chamber_id,
        use_mock=False,
        probe_id=probe_id,
        polarization=polarization,
        frequency_mhz=frequency_mhz,
        azimuth_deg=parsed.azimuth_deg,
        elevation_deg=parsed.elevation_deg,
        gain_pattern_dbi=parsed.gain_pattern_dbi,
        peak_gain_dbi=parsed.peak_gain_dbi,
        peak_azimuth_deg=parsed.peak_azimuth_deg,
        peak_elevation_deg=parsed.peak_elevation_deg,
        hpbw_azimuth_deg=parsed.hpbw_azimuth_deg,
        hpbw_elevation_deg=parsed.hpbw_elevation_deg,
        front_to_back_ratio_db=parsed.front_to_back_ratio_db,
        reference_antenna=None,  # vendor datasheet path doesn't have this
        turntable=None,
        measurement_distance_m=None,
        measured_at=now,
        measured_by=measured_by,
        valid_until=now + timedelta(days=VENDOR_PATTERN_VALIDITY_DAYS),
        status=CalibrationStatus.VALID.value,
        raw_data_file_path=raw_data_file_path,
        # Phase 2a-import provenance fields
        source="vendor_datasheet",
        probe_model=probe_model,
        probe_vendor=probe_vendor,
        probe_serial=probe_serial,
        imported_file_format=fmt,
        coordinate_system=parsed.source_coordinate_system,
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    logger.info(
        "Imported ProbePattern %s: probe=%d pol=%s freq=%.0f MHz "
        "vendor=%s model=%s peak=%.1f dBi",
        pattern.id, probe_id, polarization, frequency_mhz,
        probe_vendor, probe_model, parsed.peak_gain_dbi or 0.0,
    )

    return ImportResult(
        success=True,
        pattern_id=str(pattern.id),
        invalidated_id=invalidated_id,
        peak_gain_dbi=parsed.peak_gain_dbi,
        peak_azimuth_deg=parsed.peak_azimuth_deg,
        peak_elevation_deg=parsed.peak_elevation_deg,
        hpbw_azimuth_deg=parsed.hpbw_azimuth_deg,
        hpbw_elevation_deg=parsed.hpbw_elevation_deg,
        front_to_back_ratio_db=parsed.front_to_back_ratio_db,
        num_az_points=len(parsed.azimuth_deg),
        num_el_points=len(parsed.elevation_deg),
        warnings=parsed.warnings,
    )


# ============================================================
# Derived stats (cheap heuristics for fields parser doesn't provide)
# ============================================================


def _estimate_hpbw_azimuth(p: ParsedPattern) -> Optional[float]:
    """Estimate -3 dB azimuth beamwidth at the elevation slice with peak gain."""
    if p.peak_gain_dbi is None or p.peak_elevation_deg is None or not p.azimuth_deg:
        return None
    n_az = len(p.azimuth_deg)
    try:
        el_idx = p.elevation_deg.index(p.peak_elevation_deg)
    except ValueError:
        return None
    slice_gains = p.gain_pattern_dbi[el_idx * n_az:(el_idx + 1) * n_az]
    return _hpbw_from_slice(p.azimuth_deg, slice_gains, p.peak_gain_dbi)


def _estimate_hpbw_elevation(p: ParsedPattern) -> Optional[float]:
    """Estimate -3 dB elevation beamwidth at the azimuth slice with peak gain."""
    if p.peak_gain_dbi is None or p.peak_azimuth_deg is None or not p.elevation_deg:
        return None
    n_az = len(p.azimuth_deg)
    try:
        az_idx = p.azimuth_deg.index(p.peak_azimuth_deg)
    except ValueError:
        return None
    slice_gains = [p.gain_pattern_dbi[el_idx * n_az + az_idx] for el_idx in range(len(p.elevation_deg))]
    return _hpbw_from_slice(p.elevation_deg, slice_gains, p.peak_gain_dbi)


def _hpbw_from_slice(angles: List[float], gains: List[float], peak: float) -> Optional[float]:
    """Find first-crossing -3 dB points either side of the peak; return their distance."""
    threshold = peak - 3.0
    peak_idx = max(range(len(gains)), key=lambda i: gains[i])

    left_idx = peak_idx
    while left_idx > 0 and gains[left_idx] > threshold:
        left_idx -= 1
    right_idx = peak_idx
    while right_idx < len(gains) - 1 and gains[right_idx] > threshold:
        right_idx += 1

    if left_idx == right_idx:
        return None
    return abs(angles[right_idx] - angles[left_idx])


def _estimate_front_to_back(p: ParsedPattern) -> Optional[float]:
    """Front-to-back ratio: peak gain - gain at (peak_az + 180°, peak_el)."""
    if p.peak_gain_dbi is None or p.peak_azimuth_deg is None or p.peak_elevation_deg is None:
        return None
    back_az = (p.peak_azimuth_deg + 180.0) % 360.0
    n_az = len(p.azimuth_deg)
    if n_az == 0:
        return None
    # Find closest azimuth index
    az_idx = min(range(n_az), key=lambda i: abs(p.azimuth_deg[i] - back_az))
    try:
        el_idx = p.elevation_deg.index(p.peak_elevation_deg)
    except ValueError:
        return None
    back_gain = p.gain_pattern_dbi[el_idx * n_az + az_idx]
    if back_gain == float("-inf"):
        return None
    return float(p.peak_gain_dbi - back_gain)
