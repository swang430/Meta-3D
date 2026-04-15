"""
3GPP Static MIMO OTA Commissioning Configuration

定义首次暗室验证的标准测试参数，遵循：
- 3GPP TR 37.977: MIMO OTA 测试方法论
- 3GPP TR 38.901: 信道模型 (CDL-C)
- CTIA OTA Test Plan: Pass/Fail 门限

默认配置为最小可行的首测方案 (2x2 MIMO, 4方位)。
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class CommissioningPhase(str, Enum):
    """首测阶段"""
    PRECHECK = "precheck"
    REFERENCE = "reference"
    MIMO_TEST = "mimo_test"
    ANALYSIS = "analysis"
    REPORT = "report"


class PhaseStatus(str, Enum):
    """阶段状态"""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"       # 等待人工确认 (如更换天线)
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Verdict(str, Enum):
    """判定结果"""
    PASS = "PASS"
    FAIL = "FAIL"
    MARGINAL = "MARGINAL"     # 通过但裕量不足
    NOT_TESTED = "NOT_TESTED"


# ==================== 测试配置 ====================

@dataclass
class StaticMIMOConfig:
    """
    3GPP 静态 MIMO OTA 测试配置

    所有参数均可在前端 UI 中调整，此处为推荐默认值。
    """

    # --- 3GPP TR 38.901 信道模型 ---
    cdl_model_name: str = "UMa CDL-C NLOS"
    frequency_hz: float = 3.5e9          # n78 频段, 3GPP Band
    bandwidth_mhz: float = 100           # 100 MHz (NR 典型)

    # --- MIMO 配置 ---
    mimo_layers: int = 2                 # 2x2 (首测简化)
    modulation: str = "256QAM"           # 最高调制阶
    subcarrier_spacing_khz: int = 30     # NR SCS

    # --- 转台配置 ---
    azimuths_deg: List[float] = field(
        default_factory=lambda: [0.0, 90.0, 180.0, 270.0]
    )
    measurement_duration_s: float = 10.0  # 每方位稳态测量时长
    settling_time_s: float = 2.0          # 转台稳定等待时间

    # --- 采样配置 ---
    num_samples_per_azimuth: int = 100    # KPI 采样点数
    sample_interval_ms: float = 100.0     # 采样间隔 (100ms)

    # --- 功率配置 ---
    target_tx_power_dbm: float = 0.0     # 基站仿真器发射功率
    target_rsrp_dbm: float = -85.0       # 目标 RSRP
    target_snr_db: float = 20.0          # 目标 SNR

    # --- 参考天线 ---
    reference_antenna_gain_dbi: float = 6.1   # 标准增益喇叭 (typical)
    reference_antenna_model: str = "SGA-3500"  # 型号标识

    # --- 并行控制机制 ---
    engine_mode: str = "mimo_first_asc"      # 默认走本系统自研引擎，可选 "keysight_gcm"

    @property
    def total_measurement_time_s(self) -> float:
        """预估总测量时间 (秒)"""
        per_az = self.measurement_duration_s + self.settling_time_s
        return per_az * len(self.azimuths_deg)

    @property
    def theoretical_peak_throughput_mbps(self) -> float:
        """2x2 MIMO 256QAM 30kHz SCS 100MHz 理论峰值"""
        # 简化计算: ~450 Mbps for 2x2, 256QAM, 100MHz
        return 450.0


# ==================== CTIA Pass/Fail 门限 ====================

@dataclass
class CTIACriteria:
    """
    CTIA OTA Test Plan Pass/Fail 门限

    基于 CTIA Certification Test Plan for MIMO OTA Performance。
    首测阶段使用略宽松的门限，可在 UI 中调整。
    """

    # 吞吐量门限
    min_throughput_ratio: float = 0.70    # 实测/理论峰值 >= 70%
    min_throughput_mbps: float = 300.0    # 绝对最低吞吐量

    # RSRP 一致性
    max_rsrp_variance_db: float = 3.0    # 方位间 RSRP 最大偏差
    rsrp_range_dbm: tuple = (-75.0, -95.0)  # 可接受的 RSRP 范围

    # SINR 门限
    min_sinr_db: float = 10.0            # 最低 SINR

    # Rank Indicator
    min_avg_rank_indicator: float = 1.8  # 平均 RI >= 1.8 (近满秩)

    # 静区质量 (从校准继承)
    max_quiet_zone_ripple_db: float = 1.0  # QZ ripple <= +/-1 dB


# ==================== 阶段结果数据类 ====================

@dataclass
class PrecheckResult:
    """阶段1: 系统预检结果"""
    instruments_online: dict = field(default_factory=dict)
    # e.g. {"base_station": True, "channel_emulator": True, "signal_analyzer": True}
    calibration_valid: bool = False
    calibration_age_hours: float = 0.0
    quiet_zone_ripple_db: float = 0.0
    quiet_zone_pass: bool = False
    chamber_id: str = ""
    overall_pass: bool = False
    messages: List[str] = field(default_factory=list)


@dataclass
class AzimuthMeasurement:
    """单方位测量数据"""
    azimuth_deg: float = 0.0
    rsrp_dbm: float = -85.0
    sinr_db: float = 20.0
    throughput_mbps: float = 0.0
    rank_indicator: float = 2.0
    num_samples: int = 0
    # 统计
    rsrp_std_db: float = 0.0
    sinr_std_db: float = 0.0
    throughput_std_mbps: float = 0.0


@dataclass
class ReferenceMeasurement:
    """阶段2: 参考天线测量结果"""
    antenna_model: str = ""
    antenna_gain_dbi: float = 0.0
    measured_trp_dbm: float = 0.0
    compensation_factor_db: float = 0.0
    confirmed: bool = False   # 工程师确认


@dataclass
class MIMOTestResult:
    """阶段3: MIMO 测试结果"""
    cdl_model_name: str = ""
    frequency_ghz: float = 3.5
    mimo_config: str = "2x2"
    asc_files_loaded: bool = False
    azimuth_results: List[AzimuthMeasurement] = field(default_factory=list)
    total_duration_s: float = 0.0


@dataclass
class AnalysisResult:
    """阶段4: 分析判定结果"""
    verdict: Verdict = Verdict.NOT_TESTED
    # 吞吐量
    avg_throughput_mbps: float = 0.0
    throughput_ratio: float = 0.0
    throughput_pass: bool = False
    # RSRP
    rsrp_variance_db: float = 0.0
    rsrp_pass: bool = False
    # SINR
    avg_sinr_db: float = 0.0
    sinr_pass: bool = False
    # Rank
    avg_rank_indicator: float = 0.0
    rank_pass: bool = False
    # QZ
    qz_pass: bool = False
    # 裕量
    margin_db: float = 0.0
    details: List[str] = field(default_factory=list)


@dataclass
class CommissioningState:
    """完整的首测状态"""
    session_id: str = ""
    phase: CommissioningPhase = CommissioningPhase.PRECHECK
    phase_statuses: dict = field(default_factory=lambda: {
        CommissioningPhase.PRECHECK: PhaseStatus.PENDING,
        CommissioningPhase.REFERENCE: PhaseStatus.PENDING,
        CommissioningPhase.MIMO_TEST: PhaseStatus.PENDING,
        CommissioningPhase.ANALYSIS: PhaseStatus.PENDING,
        CommissioningPhase.REPORT: PhaseStatus.PENDING,
    })
    config: StaticMIMOConfig = field(default_factory=StaticMIMOConfig)
    criteria: CTIACriteria = field(default_factory=CTIACriteria)
    # 各阶段结果
    precheck: Optional[PrecheckResult] = None
    reference: Optional[ReferenceMeasurement] = None
    mimo_test: Optional[MIMOTestResult] = None
    analysis: Optional[AnalysisResult] = None
    report_id: Optional[str] = None
    # 时间
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    @property
    def overall_progress(self) -> float:
        """总体进度百分比"""
        completed = sum(
            1 for s in self.phase_statuses.values()
            if s in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED)
        )
        return completed / len(self.phase_statuses) * 100
