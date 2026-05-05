"""TRP TestCase configuration schema.

整机辐射功率(Total Radiated Power)是 3GPP TS 38.521-2 / CTIA OTA Test
Plan §A.6 定义的测试: DUT 在转台上以 UL grant 向 BS 发射, 信号分析仪
在球面网格上扫描接收功率, 积分得到 TRP 数值(单位 dBm)。

═══════════════════════════════════════════════════════════════════════════
RECONCILIATION 遵守清单 (按 mimo_ota/config.py 顶部 NOTE 校核)
═══════════════════════════════════════════════════════════════════════════

Canonical (按规约采用):
  ✓ frequency_hz: 用 Hz 不用 MHz/GHz
  ✓ bandwidth_mhz: 用 MHz
  ✓ spatial_grid: TRP 是球面扫描, 用 spatial_grid (theta/phi step + range)
                   而非 azimuths_deg (后者是 MIMO_OTA 走离散 4 点)
  ✓ settling_time_s
  ✓ num_samples_per_position (取代旧名 num_samples_per_azimuth)

REGISTERED DEVIATIONS (在 mimo_ota/config.py NOTE 里有登记):
  ✗ tx_power_dbm: canonical 含义是 BS 下行功率, 不适用 TRP。
    TRP 用 dut_tx_power_target_dbm 表示"命令 DUT 上行的功率目标"。
    见 mimo_ota/config.py 顶部 [2026-05-05] 登记。

不需要的 canonical 字段(TRP 不消费):
  - cdl_model_name (TRP 不走信道模型, BS 透传)
  - target_rsrp_dbm / target_snr_db (TRP 不关心 DL KPIs)
  - mimo_layers (TRP 默认单层, 多层 TRP 是另一个测试类)
  - mcs / tdd_pattern / harq_* (TRP 不测吞吐量)

Pass criteria 命名 (规约 prefix min_/max_ + suffix unit):
  ✓ min_trp_dbm
  ✓ max_psd_variance_db
  ✓ min_efficiency_pct
═══════════════════════════════════════════════════════════════════════════
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Canonical TestCase.test_type value (matches TestCaseType.TRP in models)
TRP_TEST_TYPE = "TRP"


class TRPStepType(str, Enum):
    """TRP 5 步流程, 与 MIMO_OTA 对齐 (precheck/configure/measure/analysis/report)
    便于 ExecutorRegistry 复用约定。"""

    PRECHECK = "TRP_PRECHECK"
    CONFIGURE_DUT = "TRP_CONFIGURE_DUT"
    MEASURE = "TRP_MEASURE"
    ANALYSIS = "TRP_ANALYSIS"
    REPORT = "TRP_REPORT"


TRP_DEFAULT_STEPS: List[TRPStepType] = [
    TRPStepType.PRECHECK,
    TRPStepType.CONFIGURE_DUT,
    TRPStepType.MEASURE,
    TRPStepType.ANALYSIS,
    TRPStepType.REPORT,
]


class SpatialGrid(BaseModel):
    """球面扫描网格(canonical TRP/TIS 形式)。

    DUT 在 (theta, phi) 球面位置矩阵上停留采样。theta 是俯仰角(0=top
    pole, 180=bottom pole), phi 是方位角(0..360)。CTIA 规定的 fine
    grid 是 15° step → 12 × 24 = 288 点。
    """

    theta_step_deg: float = Field(default=15.0, gt=0, le=90)
    phi_step_deg: float = Field(default=15.0, gt=0, le=180)
    theta_range_deg: tuple = Field(default=(0.0, 180.0))
    phi_range_deg: tuple = Field(default=(0.0, 360.0))

    def total_points(self) -> int:
        n_theta = int((self.theta_range_deg[1] - self.theta_range_deg[0]) / self.theta_step_deg) + 1
        n_phi = int((self.phi_range_deg[1] - self.phi_range_deg[0]) / self.phi_step_deg)
        return n_theta * n_phi


class TRPPassCriteria(BaseModel):
    """TRP pass/fail 阈值 (CTIA OTA Test Plan §A.6 默认值)。"""

    min_trp_dbm: float = Field(
        default=23.0,
        description="TRP 最低值 (dBm); CTIA 高功率终端 ≥ 23, 低功率 ≥ 17",
    )
    max_psd_variance_db: float = Field(
        default=6.0,
        description="球面 PSD 极差 (max - min, dB); 衡量发射方向性, 太高说明 DUT 朝向偏置",
    )
    min_efficiency_pct: float = Field(
        default=40.0,
        ge=0,
        le=100,
        description="天线效率 = TRP / 标定输入功率 × 100%",
    )


class TRPConfiguration(BaseModel):
    """TRP TestCase.configuration JSON 形状。

    与 MIMOOTAConfiguration 共享几个 canonical 字段名(frequency_hz,
    bandwidth_mhz, spatial_grid, settling_time_s, num_samples_per_position),
    但**不共享父类** — rule of three 还差一步, 等 TIS/Throughput 真出现
    再抽 BaseRFTestConfig。
    """

    model_config = ConfigDict(extra="allow")

    # === Canonical RF (与 MIMO_OTA 对齐) ===
    frequency_hz: float = Field(default=3.5e9, gt=0)
    bandwidth_mhz: float = Field(default=20.0, gt=0)
    subcarrier_spacing_khz: int = 30

    # === Canonical spatial sweep (球面扫描, 选 spatial_grid 不选 azimuths_deg) ===
    spatial_grid: SpatialGrid = Field(default_factory=SpatialGrid)
    settling_time_s: float = Field(default=2.0, ge=0)
    num_samples_per_position: int = Field(default=10, ge=1)

    # === REGISTERED DEVIATION: DUT-side transmit power target ===
    # 与 mimo_ota.target_tx_power_dbm (BS-side) 命名分开, 防止 silent 复用。
    # 见 schemas/mimo_ota/config.py 顶部 NOTE 中 [2026-05-05] 登记。
    dut_tx_power_target_dbm: float = Field(
        default=23.0,
        description="UL grant 命令 DUT 发射的功率 (dBm); CTIA 测试通常 23 dBm 或 26 dBm",
    )

    # === Reference antenna for absolute calibration (与 MIMO_OTA Phase 2 复用) ===
    reference_antenna_model: str = "SGA-3500"
    reference_antenna_gain_dbi: float = 6.1

    # === 信号分析仪测量参数 ===
    sa_rbw_hz: float = Field(default=1e5, description="分析仪 RBW (Hz)")
    sa_vbw_hz: float = Field(default=1e5, description="分析仪 VBW (Hz)")
    sa_span_hz: float = Field(default=2e8, description="分析仪扫描带宽 (Hz)")

    # === Pass criteria ===
    pass_criteria: TRPPassCriteria = Field(default_factory=TRPPassCriteria)

    # === Optional per-step overrides (与 MIMO_OTA 同模式) ===
    step_overrides: Optional[dict] = None

    @model_validator(mode="after")
    def _validate_consistency(self) -> "TRPConfiguration":
        # 防止 spatial_grid 退化为 0 点
        if self.spatial_grid.total_points() < 4:
            raise ValueError(
                f"spatial_grid is too coarse ({self.spatial_grid.total_points()} points); "
                "TRP needs ≥ 4 points for sphere integration to be meaningful"
            )
        return self
