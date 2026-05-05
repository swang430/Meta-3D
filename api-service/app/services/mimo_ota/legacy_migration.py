"""Legacy → MIMO_OTA TestCase migration helpers.

Used by both `scripts/seed_test_cases.py` (build-time) and
`scripts/migrate_seed_mimo_ota.py` (one-shot upgrade of DB rows that were
seeded before the MIMO_OTA test_type existed).

Transforms a legacy MIMO TestCase dict (sparse 4-field configuration,
test_type='MIMO', UMi-LOS-style channel_model) into a fully-populated
MIMOOTAConfiguration JSON ready to drop into TestCase.configuration.
"""
from __future__ import annotations

from typing import Any, Dict

from app.schemas.mimo_ota.config import MIMOOTAConfiguration


# High-level channel labels → 3GPP CDL standard model names. Chosen so the
# 5 CDL profiles (A-E) cover the typical UMi/UMa/InH cases used in seeds.
# CDL-A/B = NLOS, CDL-D/E = LOS, CDL-C = mixed mid-correlation. Mapping is
# best-effort; users can override with config_overrides at TestCase creation.
_CHANNEL_MODEL_TO_CDL: Dict[str, str] = {
    "UMi-LOS": "UMi LOS CDL-D",
    "UMi LOS": "UMi LOS CDL-D",
    "UMi-NLOS": "UMi NLOS CDL-A",
    "UMi NLOS": "UMi NLOS CDL-A",
    "UMa-LOS": "UMa LOS CDL-D",
    "UMa LOS": "UMa LOS CDL-D",
    "UMa-NLOS": "UMa NLOS CDL-C",
    "UMa NLOS": "UMa NLOS CDL-C",
    "UMa": "UMa NLOS CDL-C",
    "InH": "InH CDL-B",
    "CDL-A": "CDL-A",
    "CDL-B": "CDL-B",
    "CDL-C": "CDL-C",
    "CDL-D": "CDL-D",
    "CDL-E": "CDL-E",
}


def _resolve_cdl_name(legacy_channel_model: str | None) -> str:
    """Map legacy channel_model string to a 3GPP CDL profile name.

    Falls back to "UMa NLOS CDL-C" (the de-facto default for MIMO OTA testing
    of vehicular DUTs in 3GPP TR 37.977).
    """
    if not legacy_channel_model:
        return "UMa NLOS CDL-C"
    return _CHANNEL_MODEL_TO_CDL.get(legacy_channel_model, "UMa NLOS CDL-C")


def _extract_mimo_layers(channel_params: Dict[str, Any] | None) -> int:
    """Parse '2T4R' / '4T8R' style strings; default to 2 if absent or unparseable."""
    if not channel_params:
        return 2
    mimo_str = channel_params.get("mimo_config") or ""
    if "T" in mimo_str:
        try:
            return int(mimo_str.split("T", 1)[0])
        except (ValueError, IndexError):
            pass
    return 2


def _build_step_overrides(legacy_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve any sweep_type / sweep ranges from legacy configuration.

    Doppler / power sweep cases stash their sweep parameters under the MEASURE
    step's overrides so a future enhanced executor can act on them.
    Returns empty dict if there's nothing to carry forward.
    """
    sweep_type = legacy_cfg.get("sweep_type")
    if not sweep_type:
        return {}

    measure_overrides: Dict[str, Any] = {"sweep_type": sweep_type}
    # Carry through any *_range / *_sweep keys verbatim
    for key, value in legacy_cfg.items():
        if key in ("mimo_config", "target_throughput_mbps", "num_base_stations", "sweep_type"):
            continue
        measure_overrides[key] = value

    return {"MIMO_OTA_MEASURE": measure_overrides}


def legacy_to_mimo_ota_config(legacy_case: Dict[str, Any]) -> Dict[str, Any]:
    """Build a complete MIMOOTAConfiguration JSON from a legacy MIMO case dict.

    Input keys read (all optional, sensible defaults applied):
    - channel_model           e.g. "UMi-LOS", "CDL-A"
    - channel_parameters      {mimo_config, speed_kmh, ...}
    - configuration           {mimo_config, target_throughput_mbps, sweep_type, ...}
    - pass_criteria           {min_throughput_mbps, max_bler, ...}
    - frequency_mhz, bandwidth_mhz

    Output: a dict that round-trips through MIMOOTAConfiguration.model_validate.
    """
    chan_params: Dict[str, Any] = legacy_case.get("channel_parameters") or {}
    legacy_cfg: Dict[str, Any] = legacy_case.get("configuration") or {}
    legacy_pass: Dict[str, Any] = legacy_case.get("pass_criteria") or {}

    freq_hz = float(legacy_case.get("frequency_mhz", 3500)) * 1e6
    layers = _extract_mimo_layers(chan_params)
    target = float(
        legacy_cfg.get("target_throughput_mbps")
        or legacy_pass.get("min_throughput_mbps", 0) * 2  # if no target, infer from min*2
        or 450.0
    )
    cdl_name = _resolve_cdl_name(legacy_case.get("channel_model"))

    # Build pass_criteria respecting legacy values where present
    min_tput = float(legacy_pass.get("min_throughput_mbps", target * 0.5))
    pass_criteria: Dict[str, Any] = {
        "min_throughput_ratio": (min_tput / target) if target > 0 else 0.50,
        "min_throughput_mbps": min_tput,
        "max_rsrp_variance_db": 3.0,
        "rsrp_range_dbm": [-95.0, -75.0],
        "min_sinr_db": 10.0,
        "min_avg_rank_indicator": 1.8 if layers >= 2 else 1.0,
        "max_quiet_zone_ripple_db": 1.0,
    }

    cfg = MIMOOTAConfiguration(
        cdl_model_name=cdl_name,
        frequency_hz=freq_hz,
        bandwidth_mhz=float(legacy_case.get("bandwidth_mhz", 100.0)),
        mimo_layers=layers,
        # Defaults already correct for: modulation, subcarrier_spacing_khz,
        # azimuths_deg, measurement_duration_s, settling_time_s,
        # num_samples_per_azimuth, sample_interval_ms, target_tx_power_dbm,
        # target_rsrp_dbm, target_snr_db, reference_antenna_*, mcs, enable_amc,
        # tdd_pattern, tdd_period, harq_*, stat_count, engine_mode
        theoretical_peak_throughput_mbps=target,
        pass_criteria=pass_criteria,
        step_overrides=_build_step_overrides(legacy_cfg) or None,
    )
    return cfg.model_dump(mode="json")
