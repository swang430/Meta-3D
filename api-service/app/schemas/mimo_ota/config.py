"""MIMO_OTA TestCase configuration schema.

Mirrors what the legacy `commissioning_config.StaticMIMOConfig` dataclass
held, but lives inside `TestCase.configuration` (JSON) so it travels with the
TestCase row instead of being a process-memory thing. Also defines the canonical
step-type strings used by the ExecutorRegistry.

═══════════════════════════════════════════════════════════════════════════
RECONCILIATION NOTE — read before adding a 2nd test_type schema (TRP/TIS/...)
═══════════════════════════════════════════════════════════════════════════

We deliberately did NOT factor out a shared `BaseRFTestConfig` parent class
when this schema was written, because at the time MIMO_OTA was the only
test_type using the new TestCase.configuration JSON shape. Rule-of-three
applies: refactor when the third user shows up.

When you build the next test_type schema (TRP / TIS / Throughput / ...), use
the names + units below as canonical. Discrepancies surface as "this should
have been `frequency_hz` not `freq_ghz`" — fix them at write time, do NOT
add another column with a different unit.

Canonical RF parameters (all test_types):
- frequency_hz: float        # always Hz, never MHz/GHz inside configuration
                             # (TestCase.frequency_mhz column stays as it is
                             # for filterability — it's a derived view)
- bandwidth_mhz: float       # always MHz here (legacy column matches)
- tx_power_dbm: float        # downlink BS transmit power; NOT DUT power
- target_rsrp_dbm: float     # absolute, signed (e.g. -85.0)
- target_snr_db: float       # SNR target at DUT input

Spatial sweep (TRP / TIS / MIMO_OTA when sampling specific positions):
- azimuths_deg: List[float]                  # MIMO_OTA-style: 4 discrete points
  OR
- spatial_grid: {theta_step_deg, phi_step_deg, theta_range, phi_range}
                                             # TRP/TIS-style: full sphere grid
  Use one OR the other, not both. Pick based on whether the test walks discrete
  azimuths (MIMO_OTA) or sweeps a sphere (TRP/TIS).

- settling_time_s: float
- num_samples_per_position: int              # rename `num_samples_per_azimuth`
                                             # to this when going generic

Channel model (MIMO_OTA / Throughput / VRT):
- cdl_model_name: str                        # 3GPP CDL profile, e.g. "CDL-A"
                                             # The TestCase.channel_model
                                             # column is a higher-level label
                                             # ("UMi-LOS"); both can coexist.

MIMO-specific (MIMO_OTA / Throughput / VRT-conducted):
- mimo_layers: int           # number of layers, NOT antennas
- modulation: str            # "256QAM" / "1024QAM"
- mcs: int                   # 3GPP MCS index
- tdd_pattern, tdd_period: str
- harq_max_trans, harq_processes: int

Pass criteria (every test_type):
- prefix with min_ / max_, suffix with the unit (e.g. min_throughput_mbps,
  max_rsrp_variance_db). Avoid bare names like `throughput` or `bler`.

If any of the above genuinely doesn't fit a new test_type's needs, document
the deviation here AND open a refactor ticket — do not silently diverge.
═══════════════════════════════════════════════════════════════════════════
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# Canonical TestCase.test_type value
MIMO_OTA_TEST_TYPE = "MIMO_OTA"


class MIMOOTAStepType(str, Enum):
    """Step types registered by mimo_ota executors. Used as step.type strings."""

    PRECHECK = "MIMO_OTA_PRECHECK"
    REFERENCE = "MIMO_OTA_REFERENCE"
    MEASURE = "MIMO_OTA_MEASURE"
    ANALYSIS = "MIMO_OTA_ANALYSIS"
    REPORT = "MIMO_OTA_REPORT"


# 5-phase canonical sequence — order matters
MIMO_OTA_DEFAULT_STEPS: List[MIMOOTAStepType] = [
    MIMOOTAStepType.PRECHECK,
    MIMOOTAStepType.REFERENCE,
    MIMOOTAStepType.MEASURE,
    MIMOOTAStepType.ANALYSIS,
    MIMOOTAStepType.REPORT,
]


class MIMOOTAPassCriteria(BaseModel):
    """CTIA OTA pass/fail thresholds. Defaults are the historical Commissioning
    values; can be tightened via TestCase.pass_criteria override.
    """

    min_throughput_ratio: float = 0.70
    min_throughput_mbps: float = 300.0
    max_rsrp_variance_db: float = 3.0
    rsrp_range_dbm: tuple = (-95.0, -75.0)
    min_sinr_db: float = 10.0
    min_avg_rank_indicator: float = 1.8
    max_quiet_zone_ripple_db: float = 1.0


class MIMOOTAConfiguration(BaseModel):
    """Pydantic shape that lives inside TestCase.configuration for MIMO_OTA tests.

    All fields have CAICT-Lab-1-friendly defaults so omitting overrides on
    create is allowed; LabProfile-derived parameters can be merged in by the
    factory at TestCase build time.
    """

    model_config = ConfigDict(extra="allow")  # tolerate forward-compat extras

    # === 3GPP TR 38.901 channel ===
    cdl_model_name: str = "UMa CDL-C NLOS"
    frequency_hz: float = 3.5e9
    bandwidth_mhz: float = 100.0

    # === MIMO ===
    mimo_layers: int = 2
    modulation: str = "256QAM"
    subcarrier_spacing_khz: int = 30

    # === Turntable ===
    azimuths_deg: List[float] = Field(default_factory=lambda: [0.0, 90.0, 180.0, 270.0])
    measurement_duration_s: float = 10.0
    settling_time_s: float = 2.0

    # === Sampling ===
    num_samples_per_azimuth: int = 100
    sample_interval_ms: float = 100.0

    # === Power ===
    target_tx_power_dbm: float = 0.0
    target_rsrp_dbm: float = -85.0
    target_snr_db: float = 20.0

    # === Reference antenna (for Phase 2) ===
    reference_antenna_model: str = "SGA-3500"
    reference_antenna_gain_dbi: float = 6.1

    # === Base station MAC throughput parameters (for Phase 3) ===
    mcs: int = 28
    enable_amc: bool = False
    tdd_pattern: str = "DDDSU"
    tdd_period: str = "5MS"
    harq_max_trans: int = 4
    harq_processes: int = 16
    stat_count: int = 5000

    # === Channel generation engine ===
    engine_mode: str = "mimo_first_asc"  # "mimo_first_asc" | "keysight_gcm"

    # === Theoretical reference for ratio calculations (3GPP 2x2 256QAM 100MHz ≈ 450 Mbps) ===
    theoretical_peak_throughput_mbps: float = 450.0

    # === Pass/fail thresholds ===
    pass_criteria: MIMOOTAPassCriteria = Field(default_factory=MIMOOTAPassCriteria)

    # === Optional explicit per-step parameter overrides ===
    # Keyed by MIMOOTAStepType.value; merged into step.parameters by the factory.
    # Lets tests pin one phase without rewriting the whole config.
    step_overrides: Optional[dict] = None
