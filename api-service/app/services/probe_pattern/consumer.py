"""ProbePattern data consumer (Phase 2f).

Bridges between imported / measured ProbePattern rows and the MIMO_OTA
executors that need them:
  - measure: get_probe_gain_at_azimuth() → realistic per-probe gain
    instead of random.gauss synthesis
  - precheck: estimate_quiet_zone_ripple_db() → proxy for QZ ripple
    using cross-probe peak-gain variation, replaces hardcoded 0.7

Both functions return None if no formally eligible pattern data exists.
Callers preserve missing calibration instead of inventing gain or a verdict.

Design intent: this is the *cheap* consumer. A future Phase 2f-extended
could pull the full gain_pattern_dbi tensor and do bilinear interpolation
to (az_offset, el=90°) — for 4-azimuth canonical tests the cheap version
is good enough.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.probe_calibration import CalibrationStatus, ProbePattern
from app.services.calibration.rf_chain_resolver import (
    normalize_rf_chain_identity,
    rf_chain_identity_is_complete,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbePatternFormalEligibility:
    """One shared verdict for every formal ProbePattern consumer."""

    formal_eligible: bool
    reasons: Tuple[str, ...]


def infer_rf_chain_probe_id_base(
    num_probes: int,
    probe_ids: List[int],
) -> Optional[int]:
    """Infer a zero/one-based RF-chain namespace only from a proven edge."""
    ids = set(probe_ids)
    zero_based = set(range(num_probes))
    one_based = set(range(1, num_probes + 1))
    if ids == zero_based or (ids and ids <= zero_based and 0 in ids):
        return 0
    if ids == one_based or (ids and ids <= one_based and num_probes in ids):
        return 1
    return None


def evaluate_probe_pattern_formal_eligibility(
    db: Session,
    pattern: ProbePattern,
    *,
    num_probes: int,
    expected_lab_profile_id: Optional[UUID] = None,
    expected_operating_mode: Optional[str] = None,
    route_cache: Optional[Dict[Any, Any]] = None,
    now: Optional[datetime] = None,
) -> ProbePatternFormalEligibility:
    """Evaluate the single formal boundary for a stored probe pattern.

    Vendor patterns are route-independent.  In-chamber measurements require
    both an exact current route and an authoritative antenna aperture frozen
    with the row.  ProbePattern has no aperture field today, so measured rows
    remain auditable but cannot prove far-field gain or enter formal consumers.
    """
    reasons: List[str] = []
    current_time = now or datetime.utcnow()
    if pattern.use_mock is not False:
        reasons.append("provenance_not_explicit_real")
    if pattern.status != CalibrationStatus.VALID.value:
        reasons.append("status_not_valid")
    if pattern.valid_until is None or pattern.valid_until <= current_time:
        reasons.append("expired_or_missing_validity")

    if pattern.source == "vendor_datasheet":
        return ProbePatternFormalEligibility(not reasons, tuple(reasons))
    if pattern.source != "in_chamber_measured":
        reasons.append("unsupported_pattern_source")
        return ProbePatternFormalEligibility(False, tuple(dict.fromkeys(reasons)))

    # Until the authoritative probe/reference-antenna aperture is modeled and
    # frozen, no Fraunhofer decision can be audited.  Distance alone is not
    # enough, and a guessed diameter would turn near-field data into fake gain.
    reasons.append("authoritative_antenna_aperture_missing")
    if (
        pattern.chain_correction_db is None
        or not math.isfinite(float(pattern.chain_correction_db))
    ):
        reasons.append("chain_correction_missing_or_invalid")
    if pattern.lab_profile_id is None or not pattern.operating_mode:
        reasons.append("frozen_route_context_missing")
        return ProbePatternFormalEligibility(False, tuple(dict.fromkeys(reasons)))
    if (
        expected_lab_profile_id is not None
        and pattern.lab_profile_id != expected_lab_profile_id
    ):
        reasons.append("lab_profile_mismatch")
    if (
        expected_operating_mode is not None
        and pattern.operating_mode != expected_operating_mode
    ):
        reasons.append("operating_mode_mismatch")

    if route_cache is None:
        route_cache = {}
    cache_key = (pattern.lab_profile_id, pattern.operating_mode)
    if cache_key not in route_cache:
        try:
            from app.services.calibration.rf_chain_resolver import resolve_rf_chains

            route_cache[cache_key] = resolve_rf_chains(
                db, pattern.lab_profile_id, pattern.operating_mode
            )
        except ValueError as exc:
            logger.warning(
                "[ProbePattern] current route resolution failed for lab=%s "
                "mode=%s: %s",
                pattern.lab_profile_id,
                pattern.operating_mode,
                exc,
            )
            route_cache[cache_key] = None
    resolution = route_cache[cache_key]
    if (
        resolution is None
        or resolution.chamber_id != pattern.chamber_id
        or not resolution.topology_id
        or pattern.topology_id != str(resolution.topology_id)
    ):
        reasons.append("current_topology_mismatch_or_unresolved")
        return ProbePatternFormalEligibility(False, tuple(dict.fromkeys(reasons)))

    probe_id_base = infer_rf_chain_probe_id_base(
        num_probes,
        [candidate.probe_id for candidate in resolution.chains],
    )
    if probe_id_base is None:
        reasons.append("probe_id_namespace_ambiguous")
        return ProbePatternFormalEligibility(False, tuple(dict.fromkeys(reasons)))
    matching = [
        chain
        for chain in resolution.chains
        if chain.probe_id == pattern.probe_id + probe_id_base
        and chain.polarization.upper() == pattern.polarization.upper()
    ]
    if len(matching) != 1 or not rf_chain_identity_is_complete(matching[0]):
        reasons.append("current_chain_missing_or_ambiguous")
        return ProbePatternFormalEligibility(False, tuple(dict.fromkeys(reasons)))
    chain = matching[0]
    if (
        normalize_rf_chain_identity(pattern.chain_id)
        != normalize_rf_chain_identity(chain.chain_id)
        or normalize_rf_chain_identity(pattern.ce_port)
        != normalize_rf_chain_identity(chain.ce_port)
    ):
        reasons.append("current_chain_identity_mismatch")

    return ProbePatternFormalEligibility(False, tuple(dict.fromkeys(reasons)))


def _query_valid_pattern(
    db: Session,
    probe_id: int,
    polarization: str,
    frequency_mhz: float,
    freq_tolerance_pct: float = 5.0,
    *,
    chamber_id: UUID,
    num_probes: int,
    lab_profile_id: Optional[UUID] = None,
    operating_mode: str = "mimo_ota",
    route_cache: Optional[Dict[str, Any]] = None,
) -> Optional[ProbePattern]:
    """Most-recent VALID ProbePattern matching probe_id+pol within ±5% freq.

    probe_id 在多暗室下不再全局唯一。只返回显式属于 chamber_id 的方向图；
    legacy NULL 与其它暗室记录都不能进入正式测量。
    """
    if chamber_id is None:
        raise ValueError("chamber_id is required for formal ProbePattern consumption")
    f_min = frequency_mhz * (1.0 - freq_tolerance_pct / 100.0)
    f_max = frequency_mhz * (1.0 + freq_tolerance_pct / 100.0)
    if route_cache is None:
        route_cache = {}

    def _base():
        return db.query(ProbePattern).filter(
            ProbePattern.probe_id == probe_id,
            ProbePattern.polarization == polarization,
            ProbePattern.frequency_mhz >= f_min,
            ProbePattern.frequency_mhz <= f_max,
            ProbePattern.status == CalibrationStatus.VALID.value,
            ProbePattern.use_mock.is_(False),
            ProbePattern.valid_until > datetime.utcnow(),
        )

    candidates = (
        _base()
        .filter(ProbePattern.chamber_id == chamber_id)
        .order_by(desc(ProbePattern.measured_at))
        .all()
    )
    for pattern in candidates:
        eligibility = evaluate_probe_pattern_formal_eligibility(
            db,
            pattern,
            num_probes=num_probes,
            expected_lab_profile_id=lab_profile_id,
            expected_operating_mode=operating_mode,
            route_cache=route_cache,
        )
        if eligibility.formal_eligible:
            return pattern
    return None


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


def select_active_rf_chain_probe_id(
    num_probes: int,
    azimuth_deg: float,
    *,
    probe_id_base: int = 1,
) -> Optional[int]:
    """Map azimuth to an explicitly based topology/certificate probe ID.

    ``select_active_probe_id`` is the historical ProbePattern index contract and
    remains zero-based.  Current physical topology uses one-based IDs, while
    historical RF-chain certificates may be zero-based.  Callers that consume
    a certificate must derive the base from its complete ID set, never guess.
    """
    if probe_id_base not in (0, 1):
        raise ValueError("probe_id_base must be 0 or 1")
    pattern_index = select_active_probe_id(num_probes, azimuth_deg)
    return None if pattern_index is None else pattern_index + probe_id_base


def get_probe_gain_at_azimuth(
    db: Session,
    num_probes: int,
    azimuth_deg: float,
    frequency_mhz: float,
    polarization: str = "V",
    *,
    chamber_id: UUID,
    lab_profile_id: UUID,
    operating_mode: str,
) -> Optional[float]:
    """Return peak gain (dBi) of the probe closest to `azimuth_deg`.

    Currently uses peak_gain_dbi (boresight); a future extension can sample
    gain_pattern_dbi at the actual angle offset, but for canonical 4-azimuth
    tests where each azimuth aligns with a probe, peak gain is appropriate.

    chamber_id: 见 _query_valid_pattern — 只取该暗室的显式可信方向图。

    Returns None if no valid pattern exists for the resolved probe — caller
    should fall back to nominal gain or synthesize.
    """
    probe_id = select_active_probe_id(num_probes, azimuth_deg)
    if probe_id is None:
        return None
    pattern = _query_valid_pattern(
        db,
        probe_id,
        polarization,
        frequency_mhz,
        chamber_id=chamber_id,
        num_probes=num_probes,
        lab_profile_id=lab_profile_id,
        operating_mode=operating_mode,
        route_cache={},
    )
    if pattern is None or pattern.peak_gain_dbi is None:
        return None
    return float(pattern.peak_gain_dbi)


def estimate_quiet_zone_ripple_db(
    db: Session,
    num_probes: int,
    frequency_mhz: float,
    polarization: str = "V",
    *,
    chamber_id: UUID,
    lab_profile_id: UUID,
    operating_mode: str,
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
    route_cache: Dict[str, Any] = {}
    for probe_id in range(num_probes):
        p = _query_valid_pattern(
            db,
            probe_id,
            polarization,
            frequency_mhz,
            chamber_id=chamber_id,
            num_probes=num_probes,
            lab_profile_id=lab_profile_id,
            operating_mode=operating_mode,
            route_cache=route_cache,
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
