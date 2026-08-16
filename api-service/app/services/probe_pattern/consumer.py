"""ProbePattern data consumer (Phase 2f).

Bridges between imported / measured ProbePattern rows and the MIMO_OTA
executors that need them:
  - measure: get_probe_gain_at_azimuth() → realistic per-probe gain
    instead of random.gauss synthesis
  - precheck: estimate_quiet_zone_ripple_db() → proxy for QZ ripple
    using cross-probe peak-gain variation, replaces hardcoded 0.7

Both functions degrade gracefully (return None) if no valid pattern data
exists, so labs that haven't seeded any pattern (Path A or B) still get
the legacy synthesis path.

Design intent: this is the *cheap* consumer. A future Phase 2f-extended
could pull the full gain_pattern_dbi tensor and do bilinear interpolation
to (az_offset, el=90°) — for 4-azimuth canonical tests the cheap version
is good enough.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.probe_calibration import CalibrationStatus, ProbePattern

logger = logging.getLogger(__name__)


def _query_valid_pattern(
    db: Session,
    probe_id: int,
    polarization: str,
    frequency_mhz: float,
    freq_tolerance_pct: float = 5.0,
    chamber_id: Optional[UUID] = None,
) -> Optional[ProbePattern]:
    """Most-recent VALID ProbePattern matching probe_id+pol within ±5% freq.

    probe_id 在多暗室下不再全局唯一。给定 chamber_id 时只返回显式属于该暗室的
    方向图；legacy NULL 与其它暗室记录都不能进入正式测量。
    chamber_id 为 None 时维持历史行为 (仅按 probe_id+pol+freq 取最新)。
    """
    f_min = frequency_mhz * (1.0 - freq_tolerance_pct / 100.0)
    f_max = frequency_mhz * (1.0 + freq_tolerance_pct / 100.0)

    def _base():
        return db.query(ProbePattern).filter(
            ProbePattern.probe_id == probe_id,
            ProbePattern.polarization == polarization,
            ProbePattern.frequency_mhz >= f_min,
            ProbePattern.frequency_mhz <= f_max,
            ProbePattern.status == CalibrationStatus.VALID.value,
        )

    if chamber_id is None:
        return _base().order_by(desc(ProbePattern.measured_at)).first()

    exact = (
        _base()
        .filter(ProbePattern.chamber_id == chamber_id)
        .order_by(desc(ProbePattern.measured_at))
        .first()
    )
    return exact


def select_active_probe_id(num_probes: int, azimuth_deg: float) -> Optional[int]:
    """Map azimuth → closest probe_id assuming uniform angular distribution.

    Real chambers with non-uniform probe placement need a probe_locations
    table (Phase 2i / 2b in the roadmap). Until then, uniform assumption
    matches CAICT-Lab-1's actual layout (32 probes equally spaced).
    """
    if num_probes <= 0:
        return None
    az_per_probe = 360.0 / num_probes
    return int(round(azimuth_deg / az_per_probe)) % num_probes


def get_probe_gain_at_azimuth(
    db: Session,
    num_probes: int,
    azimuth_deg: float,
    frequency_mhz: float,
    polarization: str = "V",
    chamber_id: Optional[UUID] = None,
) -> Optional[float]:
    """Return peak gain (dBi) of the probe closest to `azimuth_deg`.

    Currently uses peak_gain_dbi (boresight); a future extension can sample
    gain_pattern_dbi at the actual angle offset, but for canonical 4-azimuth
    tests where each azimuth aligns with a probe, peak gain is appropriate.

    chamber_id: 见 _query_valid_pattern — 限定取该暗室 (或 legacy) 的方向图。

    Returns None if no valid pattern exists for the resolved probe — caller
    should fall back to nominal gain or synthesize.
    """
    probe_id = select_active_probe_id(num_probes, azimuth_deg)
    if probe_id is None:
        return None
    pattern = _query_valid_pattern(
        db, probe_id, polarization, frequency_mhz, chamber_id=chamber_id
    )
    if pattern is None or pattern.peak_gain_dbi is None:
        return None
    return float(pattern.peak_gain_dbi)


def estimate_quiet_zone_ripple_db(
    db: Session,
    num_probes: int,
    frequency_mhz: float,
    polarization: str = "V",
    chamber_id: Optional[UUID] = None,
) -> Optional[float]:
    """Estimate QZ ripple from cross-probe peak-gain spread.

    Approach: collect peak_gain_dbi for every probe at this frequency / pol
    that has a VALID ProbePattern, then return max-min as ripple proxy.

    Why this works as a proxy: a balanced probe array has all probes
    contributing similar gain to the quiet zone center; if probe gains span
    a wide range, the synthesized field at the QZ center will be more
    uneven (each azimuth's "main probe" delivers a different power level).
    Real ripple measurement needs spherical integration over the QZ volume
    — that's a Phase 2f-extended item.

    Returns None if fewer than 2 probes have data (insufficient sample).
    """
    patterns: List[ProbePattern] = []
    for probe_id in range(num_probes):
        p = _query_valid_pattern(
            db, probe_id, polarization, frequency_mhz, chamber_id=chamber_id
        )
        if p is not None and p.peak_gain_dbi is not None:
            patterns.append(p)

    if len(patterns) < 2:
        logger.info(
            "[QZ] insufficient ProbePattern data (%d probes have valid data, need ≥2) "
            "@ %.0f MHz pol=%s; ripple estimate unavailable",
            len(patterns), frequency_mhz, polarization,
        )
        return None

    peaks = [float(p.peak_gain_dbi) for p in patterns]
    ripple = max(peaks) - min(peaks)
    logger.info(
        "[QZ] %d/%d probes with pattern data, peak-to-peak ripple = %.2f dB "
        "(min %.2f, max %.2f) @ %.0f MHz pol=%s",
        len(patterns), num_probes, ripple, min(peaks), max(peaks),
        frequency_mhz, polarization,
    )
    return float(ripple)
