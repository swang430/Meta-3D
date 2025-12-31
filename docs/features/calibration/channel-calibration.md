# Channel Calibration Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Calibration Subsystem (校准子系统)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

信道校准（Channel Calibration）确保MPAC系统能够准确重现3GPP定义的空间信道模型。与探头校准（物理层面）不同，信道校准关注的是整个系统作为一个整体能否正确仿真无线信道的**统计特性**和**空间特性**。

### 1.2 核心校准目标

| 校准项 | 目标参数 | 验证方法 | 合格标准 |
|-------|---------|---------|---------|
| **多径衰落准确性** | 时延扩展、功率时延谱 | 与3GPP模型对比 | RMSE < 10% |
| **空间相关性** | 天线间相关系数 | 测量vs.理论 | \|Δρ\| < 0.1 |
| **角度扩展** | AoA/AoD扩展 | 角度功率谱 | RMS差异 < 5° |
| **多普勒谱** | 多普勒扩展、谱形状 | 频域分析 | 形状相似度 > 90% |
| **静区均匀性** | 场幅度/相位均匀性 | 静区内扫描 | 标准差 < 1 dB |
| **信道互易性** | UL vs. DL信道对称性 | 双向测量 | 相关性 > 0.95 |

### 1.3 标准依据

- **3GPP TR 38.901**: Study on channel model for frequencies from 0.5 to 100 GHz
- **3GPP TS 34.114**: 5G NR UE/BS OTA performance requirements
- **COST 2100**: Channel model for MIMO OTA testing
- **IEEE 1720**: Recommended Practice for Near-Field Antenna Measurements

## 2. 系统架构

### 2.1 信道校准层次

```
┌─────────────────────────────────────────────────────────────────┐
│                  Level 3: End-to-End Validation                  │
│  - 完整3GPP场景验证（UMa/UMi/InH）                                 │
│  - DUT性能指标验证（吞吐量、SINR）                                  │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│              Level 2: Spatial Channel Calibration                │
│  - 空间相关性校准                                                 │
│  - 角度扩展校准                                                   │
│  - 静区场均匀性校准                                                │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│              Level 1: Temporal Channel Calibration               │
│  - 多径时延扩展校准                                                │
│  - 多普勒频谱校准                                                  │
│  - 信道仿真器精度验证                                              │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│                   Level 0: Probe Calibration                     │
│  (见 Probe-Calibration-Design.md)                                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 校准系统组件

```
┌─────────────────────────────────────────────────────────────────┐
│                  Channel Calibration Orchestrator                │
│  - 校准流程编排                                                   │
│  - 参数配置管理                                                   │
│  - 结果验证和报告                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌──────────────────────┬──────────────────────┬──────────────────┐
│   Temporal Channel   │  Spatial Channel    │  EIS Validation  │
│   Calibration        │  Calibration        │  (End-to-End)    │
└──────────────────────┴──────────────────────┴──────────────────┘
          ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Measurement Instruments                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Channel      │  │ Base Station │  │ Signal       │           │
│  │ Emulator     │  │ Emulator     │  │ Analyzer     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Test DUT     │  │ Positioner   │  │ Power Meter  │           │
│  │ (Reference)  │  │              │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Calibration Data Management                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database                         │   │
│  │  - temporal_channel_calibrations                         │   │
│  │  - spatial_channel_calibrations                          │   │
│  │  - eis_validation_results                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Analysis & Reporting                        │   │
│  │  - 3GPP参数提取                                           │   │
│  │  - 统计分析                                               │   │
│  │  - 对比报告生成                                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 时域信道校准 (Temporal Channel Calibration)

### 3.1 多径时延扩展校准

#### 3.1.1 校准原理

**目标**: 验证信道仿真器能够正确生成3GPP定义的功率时延谱（Power Delay Profile, PDP）。

**3GPP模型**: TR 38.901定义的PDP为簇状模型（Cluster-based Model）
```
PDP(τ) = Σ P_n · δ(τ - τ_n)
```
- P_n: 第n个簇的功率
- τ_n: 第n个簇的时延

**验证方法**:
1. 配置信道仿真器生成特定3GPP场景（如UMa LOS）
2. 使用宽带信号（如OFDM）测量信道冲激响应
3. 提取PDP参数（RMS时延扩展、最大多径时延）
4. 与3GPP理论值对比

#### 3.1.2 测量配置

**信号**: OFDM Symbol
- 带宽: 100 MHz (覆盖时延分辨率 ~10 ns)
- 子载波间隔: 30 kHz
- FFT size: 4096

**测量链路**:
```
BS Emulator → Channel Emulator → Probe Array → Test DUT → Signal Analyzer
```

**测量参数**:
- 冲激响应长度: 10 μs (覆盖最大多径时延)
- 平均次数: 100 (降低噪声)
- 采样率: 200 MHz

#### 3.1.3 参数提取

**RMS时延扩展**:
```
τ_rms = sqrt(E[τ²] - E[τ]²)

其中:
E[τ] = Σ P_n · τ_n / Σ P_n
E[τ²] = Σ P_n · τ_n² / Σ P_n
```

**最大多径时延**:
```
τ_max = max{τ_n | P_n > threshold}
threshold通常设为最大功率的 -25 dB
```

#### 3.1.4 数据模型

```typescript
interface TemporalChannelCalibration {
  id: string
  scenario: {
    type: 'UMa' | 'UMi' | 'RMa' | 'InH'
    condition: 'LOS' | 'NLOS' | 'O2I'
    fc_ghz: number
    distance_2d_m: number
  }

  // 测量PDP
  measured_pdp: {
    delay_bins_ns: number[]  // [0, 10, 20, ..., 10000]
    power_db: number[]  // 相对功率（dB）
  }

  // 提取参数
  measured_params: {
    rms_delay_spread_ns: number
    max_delay_ns: number
    num_clusters: number
    cluster_delays_ns: number[]
    cluster_powers_db: number[]
  }

  // 3GPP理论参考
  reference_params: {
    rms_delay_spread_ns: number
    rms_delay_spread_range_ns: [number, number]  // 统计范围
    num_clusters: number
  }

  // 验证结果
  validation: {
    rms_error_percent: number
    cluster_count_match: boolean
    pass: boolean
    threshold_percent: number  // 通常 10%
  }

  // 元数据
  calibrated_at: Date
  calibrated_by: string
  channel_emulator: string
}
```

### 3.2 多普勒频谱校准

#### 3.2.1 校准原理

**目标**: 验证信道仿真器能够正确生成多普勒频谱。

**3GPP模型**: 经典多普勒谱（Classical Doppler Spectrum）
```
S(f) = 1 / (π·f_d·sqrt(1 - (f/f_d)²))   for |f| < f_d

其中:
f_d = v·fc/c  (最大多普勒频移)
v: 移动速度
fc: 载波频率
c: 光速
```

**验证方法**:
1. 配置信道仿真器生成指定速度（如120 km/h）的多普勒
2. 发射CW信号（连续波），测量接收信号
3. FFT分析，提取多普勒频谱
4. 与理论谱对比

#### 3.2.2 数据模型

```typescript
interface DopplerCalibration {
  id: string

  // 配置
  config: {
    velocity_kmh: number
    fc_ghz: number
    expected_doppler_hz: number  // v·fc/c
  }

  // 测量谱
  measured_spectrum: {
    frequency_bins_hz: number[]  // [-fd, ..., 0, ..., +fd]
    power_density_db: number[]
  }

  // 理论谱
  reference_spectrum: {
    frequency_bins_hz: number[]
    power_density_db: number[]  // Classical Doppler形状
  }

  // 验证
  validation: {
    spectral_correlation: number  // 0-1, 谱形状相似度
    doppler_spread_error_percent: number
    pass: boolean
    threshold_correlation: number  // 通常 0.9
  }

  calibrated_at: Date
}
```

### 3.3 数据库模式

```sql
CREATE TABLE temporal_channel_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 场景
  scenario_type VARCHAR(50) NOT NULL,
  scenario_condition VARCHAR(50) NOT NULL,
  fc_ghz FLOAT NOT NULL,
  distance_2d_m FLOAT,

  -- 测量PDP
  measured_pdp JSONB NOT NULL,  -- {delay_bins_ns, power_db}

  -- 提取参数
  measured_rms_delay_spread_ns FLOAT,
  measured_max_delay_ns FLOAT,
  measured_num_clusters INTEGER,
  measured_cluster_delays_ns JSONB,
  measured_cluster_powers_db JSONB,

  -- 参考参数
  reference_rms_delay_spread_ns FLOAT,
  reference_rms_delay_spread_range_ns JSONB,  -- [min, max]
  reference_num_clusters INTEGER,

  -- 验证
  rms_error_percent FLOAT,
  cluster_count_match BOOLEAN,
  validation_pass BOOLEAN,
  threshold_percent FLOAT DEFAULT 10.0,

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),
  channel_emulator VARCHAR(255),

  -- 原始数据
  raw_data_file_path TEXT,

  INDEX idx_scenario (scenario_type, scenario_condition),
  INDEX idx_validation_pass (validation_pass)
);

CREATE TABLE doppler_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 配置
  velocity_kmh FLOAT NOT NULL,
  fc_ghz FLOAT NOT NULL,
  expected_doppler_hz FLOAT NOT NULL,

  -- 测量谱
  measured_spectrum JSONB NOT NULL,

  -- 参考谱
  reference_spectrum JSONB NOT NULL,

  -- 验证
  spectral_correlation FLOAT,
  doppler_spread_error_percent FLOAT,
  validation_pass BOOLEAN,
  threshold_correlation FLOAT DEFAULT 0.9,

  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  INDEX idx_validation_pass (validation_pass)
);
```

## 4. 空间信道校准 (Spatial Channel Calibration)

### 4.1 空间相关性校准

#### 4.1.1 校准原理

**目标**: 验证MPAC系统能否正确重现MIMO天线间的空间相关性。

**理论基础**: 空间相关性由角度功率谱（Angular Power Spectrum, APS）决定

对于间距为 d 的两天线，相关系数：
```
ρ = ∫ P(θ) · e^(j·k·d·sinθ) dθ

其中:
P(θ): 角度功率谱
k = 2π/λ: 波数
d: 天线间距
```

**3GPP模型**: Laplacian角度分布
```
P(θ) = exp(-√2·|θ - θ_mean|/σ_θ) / (√2·σ_θ)

σ_θ: RMS角度扩展
```

#### 4.1.2 测量配置

**测试DUT**: 双天线接收机（已知天线间距）
- 天线类型: 偶极子
- 间距: 0.5λ, 1λ, 2λ (多个配置)
- 极化: 同极化

**测量流程**:
1. 配置信道仿真器生成UMa NLOS场景（角度扩展 ~15°）
2. 测试DUT接收信号
3. 同时记录两天线的复数信道系数 h1(t), h2(t)
4. 计算相关系数:
   ```
   ρ_measured = E[h1 · h2*] / sqrt(E[|h1|²] · E[|h2|²])
   ```
5. 与理论值对比

#### 4.1.3 数据模型

```typescript
interface SpatialCorrelationCalibration {
  id: string

  // 场景配置
  scenario: {
    type: 'UMa' | 'UMi' | 'RMa' | 'InH'
    condition: 'LOS' | 'NLOS'
    fc_ghz: number
    angular_spread_deg: number  // RMS角度扩展
  }

  // 测试DUT配置
  test_dut: {
    antenna_spacing_wavelengths: number
    antenna_spacing_m: number
    antenna_type: string
  }

  // 测量结果
  measured_correlation: {
    magnitude: number  // 0-1
    phase_deg: number
    samples: number  // 统计样本数
    confidence_interval: [number, number]
  }

  // 理论参考
  reference_correlation: {
    magnitude: number
    phase_deg: number
    calculation_method: '3GPP_TR_38_901_Laplacian'
  }

  // 验证
  validation: {
    magnitude_error: number
    phase_error_deg: number
    pass: boolean
    threshold_magnitude: number  // 通常 0.1
    threshold_phase_deg: number  // 通常 10°
  }

  calibrated_at: Date
  calibrated_by: string
}
```

### 4.2 角度扩展校准

#### 4.2.1 校准原理

**目标**: 验证MPAC系统的角度功率谱（APS）与3GPP模型一致。

**测量方法**: 旋转测试DUT，测量不同角度的接收功率。

**流程**:
1. 测试DUT固定在转台上
2. 配置信道仿真器生成UMa场景
3. 旋转DUT，扫描方位角 0°-360°，步长 5°
4. 记录每个角度的平均接收功率
5. 归一化，得到角度功率谱 P(θ)
6. 拟合Laplacian分布，提取角度扩展参数

#### 4.2.2 数据模型

```typescript
interface AngularSpreadCalibration {
  id: string

  scenario: {
    type: string
    condition: string
    fc_ghz: number
  }

  // 测量角度功率谱
  measured_aps: {
    azimuth_deg: number[]  // [0, 5, 10, ..., 355]
    power_db: number[]  // 归一化功率（dB）
  }

  // 拟合参数
  fitted_params: {
    mean_azimuth_deg: number
    rms_angular_spread_deg: number
    distribution_type: 'Laplacian' | 'Gaussian'
    r_squared: number  // 拟合优度
  }

  // 参考参数
  reference_params: {
    rms_angular_spread_deg: number
    rms_angular_spread_range_deg: [number, number]
  }

  // 验证
  validation: {
    rms_error_deg: number
    pass: boolean
    threshold_deg: number  // 通常 5°
  }

  calibrated_at: Date
}
```

### 4.3 静区场均匀性校准

#### 4.3.1 校准原理

**目标**: 验证静区（Quiet Zone）内的电磁场幅度和相位均匀性。

**定义**: 静区是DUT放置区域，通常为球形或圆柱形区域。

**要求** (CTIA):
- 幅度均匀性: ±1 dB
- 相位均匀性: ±30° (mmWave可放宽至 ±45°)

**测量方法**: 场探头扫描法

**流程**:
1. 使用小型场探头（如微型偶极子）
2. 配置MPAC生成平面波
3. 扫描静区内多个点（球形网格）
4. 记录每个点的场幅度和相位
5. 计算标准差

#### 4.3.2 数据模型

```typescript
interface QuietZoneCalibration {
  id: string

  // 静区定义
  quiet_zone: {
    shape: 'sphere' | 'cylinder'
    diameter_m: number
    height_m?: number  // 仅圆柱形
  }

  // 探针配置
  field_probe: {
    type: 'dipole' | 'loop'
    size_mm: number
  }

  // 测量网格
  measurement_grid: {
    points: Array<{
      x_m: number
      y_m: number
      z_m: number
      amplitude_v_per_m: number
      phase_deg: number
    }>
    num_points: number
  }

  // 统计分析
  uniformity: {
    amplitude_mean_db: number
    amplitude_std_db: number
    amplitude_range_db: [number, number]

    phase_mean_deg: number
    phase_std_deg: number
    phase_range_deg: [number, number]
  }

  // 验证
  validation: {
    amplitude_uniformity_pass: boolean
    phase_uniformity_pass: boolean
    amplitude_threshold_db: number  // 1 dB
    phase_threshold_deg: number  // 30°
  }

  calibrated_at: Date
}
```

### 4.4 数据库模式

```sql
CREATE TABLE spatial_correlation_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 场景
  scenario_type VARCHAR(50),
  scenario_condition VARCHAR(50),
  fc_ghz FLOAT,
  angular_spread_deg FLOAT,

  -- 测试DUT
  antenna_spacing_wavelengths FLOAT,
  antenna_spacing_m FLOAT,
  antenna_type VARCHAR(100),

  -- 测量结果
  measured_correlation_magnitude FLOAT,
  measured_correlation_phase_deg FLOAT,
  samples INTEGER,
  confidence_interval JSONB,

  -- 参考
  reference_correlation_magnitude FLOAT,
  reference_correlation_phase_deg FLOAT,

  -- 验证
  magnitude_error FLOAT,
  phase_error_deg FLOAT,
  validation_pass BOOLEAN,

  calibrated_at TIMESTAMP DEFAULT NOW(),

  INDEX idx_scenario (scenario_type),
  INDEX idx_validation_pass (validation_pass)
);

CREATE TABLE angular_spread_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  scenario_type VARCHAR(50),
  scenario_condition VARCHAR(50),
  fc_ghz FLOAT,

  -- 测量APS
  measured_aps JSONB,  -- {azimuth_deg, power_db}

  -- 拟合参数
  fitted_mean_azimuth_deg FLOAT,
  fitted_rms_angular_spread_deg FLOAT,
  fitted_distribution_type VARCHAR(50),
  fitted_r_squared FLOAT,

  -- 参考
  reference_rms_angular_spread_deg FLOAT,
  reference_rms_angular_spread_range_deg JSONB,

  -- 验证
  rms_error_deg FLOAT,
  validation_pass BOOLEAN,

  calibrated_at TIMESTAMP DEFAULT NOW(),

  INDEX idx_validation_pass (validation_pass)
);

CREATE TABLE quiet_zone_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 静区配置
  quiet_zone_shape VARCHAR(50),
  quiet_zone_diameter_m FLOAT,
  quiet_zone_height_m FLOAT,

  -- 探针
  field_probe_type VARCHAR(50),
  field_probe_size_mm FLOAT,

  -- 测量网格
  measurement_grid JSONB,  -- {points: [...]}
  num_points INTEGER,

  -- 统计
  amplitude_mean_db FLOAT,
  amplitude_std_db FLOAT,
  amplitude_range_db JSONB,

  phase_mean_deg FLOAT,
  phase_std_deg FLOAT,
  phase_range_deg JSONB,

  -- 验证
  amplitude_uniformity_pass BOOLEAN,
  phase_uniformity_pass BOOLEAN,

  calibrated_at TIMESTAMP DEFAULT NOW(),

  INDEX idx_validation_pass (amplitude_uniformity_pass, phase_uniformity_pass)
);
```

## 5. EIS验证 (Equivalent Isotropic Sensitivity)

### 5.1 EIS原理

**EIS定义**: 等效全向灵敏度，是OTA测试中最重要的性能指标，定义为：

```
EIS = REFSENS + Probe_Gain + Path_Loss - TRP_DUT
```

**物理意义**: DUT在理想全向辐射模式下达到参考灵敏度所需的输入功率。

### 5.2 EIS测量流程

**步骤**:
1. 配置信道仿真器生成3GPP场景（如UMa NLOS）
2. DUT固定在转台上
3. 旋转DUT，扫描3D空间（θ, φ）
4. 对每个角度：
   - 调整输入功率，找到DUT的灵敏度点（如吞吐量 = 95% max）
   - 记录所需功率 P_in(θ, φ)
5. 计算 EIS = -min{P_in(θ, φ)} (最佳方向)

### 5.3 数据模型

```typescript
interface EISValidation {
  id: string

  // 测试配置
  test_config: {
    scenario: string
    fc_ghz: number
    bandwidth_mhz: number
    modulation: string  // e.g., '64QAM'
    target_throughput_percent: number  // 95%
  }

  // DUT信息
  dut: {
    type: 'smartphone' | 'vehicle' | 'module'
    model: string
    num_rx_antennas: number
  }

  // 测量数据
  eis_map: {
    azimuth_deg: number[]
    elevation_deg: number[]
    eis_dbm: number[][]  // 2D map
  }

  // 结果
  results: {
    peak_eis_dbm: number
    peak_direction: { azimuth_deg: number; elevation_deg: number }
    median_eis_dbm: number
    eis_spread_db: number  // Peak - 5th percentile
  }

  // 3GPP要求（参考）
  requirements: {
    min_eis_dbm: number  // e.g., -96 dBm for FR1
    pass: boolean
  }

  measured_at: Date
  measured_by: string
}
```

### 5.4 数据库模式

```sql
CREATE TABLE eis_validations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 测试配置
  scenario VARCHAR(100),
  fc_ghz FLOAT,
  bandwidth_mhz FLOAT,
  modulation VARCHAR(50),
  target_throughput_percent FLOAT,

  -- DUT
  dut_type VARCHAR(50),
  dut_model VARCHAR(255),
  num_rx_antennas INTEGER,

  -- 测量数据
  eis_map JSONB,  -- {azimuth_deg, elevation_deg, eis_dbm}

  -- 结果
  peak_eis_dbm FLOAT,
  peak_azimuth_deg FLOAT,
  peak_elevation_deg FLOAT,
  median_eis_dbm FLOAT,
  eis_spread_db FLOAT,

  -- 要求
  min_eis_dbm FLOAT,
  validation_pass BOOLEAN,

  measured_at TIMESTAMP DEFAULT NOW(),
  measured_by VARCHAR(100),

  INDEX idx_validation_pass (validation_pass),
  INDEX idx_dut_model (dut_model)
);
```

## 6. 校准调度和自动化

### 6.1 校准调度策略

| 校准类型 | 频率 | 触发条件 | 优先级 |
|---------|------|---------|--------|
| 时域信道校准 | 每月 | 信道仿真器更新/维护后 | P0 |
| 空间相关性校准 | 每季度 | 探头阵列配置变更后 | P0 |
| 角度扩展校准 | 每季度 | 同上 | P1 |
| 静区均匀性校准 | 每半年 | 暗室改造后 | P0 |
| EIS验证 | 每次重大系统变更后 | - | P0 |

### 6.2 自动化工作流

```yaml
# channel_calibration_workflow.yaml

name: "Complete Channel Calibration"
version: "1.0"

stages:
  - stage: "pre_check"
    actions:
      - name: "Verify probe calibration validity"
        api: "/api/v1/calibration/validity/check"
        fail_if: "any_probe_expired"

      - name: "Preheat instruments"
        duration_minutes: 30
        instruments: ["channel_emulator", "base_station", "signal_analyzer"]

  - stage: "temporal_calibration"
    parallel: false
    tests:
      - name: "Delay Spread - UMa LOS"
        type: "temporal"
        scenario: { type: "UMa", condition: "LOS", fc_ghz: 3.5 }

      - name: "Delay Spread - UMa NLOS"
        type: "temporal"
        scenario: { type: "UMa", condition: "NLOS", fc_ghz: 3.5 }

      - name: "Doppler Spectrum - 120 km/h"
        type: "doppler"
        config: { velocity_kmh: 120, fc_ghz: 3.5 }

  - stage: "spatial_calibration"
    parallel: true
    tests:
      - name: "Spatial Correlation - 0.5λ"
        type: "spatial_correlation"
        dut: { antenna_spacing_wavelengths: 0.5 }

      - name: "Spatial Correlation - 1λ"
        type: "spatial_correlation"
        dut: { antenna_spacing_wavelengths: 1.0 }

      - name: "Angular Spread - UMa"
        type: "angular_spread"
        scenario: { type: "UMa", condition: "NLOS" }

  - stage: "quiet_zone_calibration"
    tests:
      - name: "QZ Uniformity - 0.5m sphere"
        type: "quiet_zone"
        quiet_zone: { shape: "sphere", diameter_m: 0.5 }

  - stage: "eis_validation"
    tests:
      - name: "EIS - Reference DUT"
        type: "eis"
        dut: { model: "Standard_Dipole_Array" }
        scenario: { type: "UMa", condition: "NLOS" }

  - stage: "report_generation"
    actions:
      - name: "Generate calibration report"
        format: "PDF"
        include: ["summary", "all_results", "pass_fail_status"]

      - name: "Update calibration validity"
        api: "/api/v1/calibration/validity/update"

      - name: "Notify stakeholders"
        method: "email"
        recipients: ["calibration_team@example.com"]
```

### 6.3 工作流执行API

```typescript
// POST /api/v1/channel-calibration/workflows/execute
interface ExecuteWorkflowRequest {
  workflow_id: string  // e.g., "complete_channel_calibration"
  configuration?: {
    skip_stages?: string[]
    override_params?: Record<string, any>
  }
}

interface ExecuteWorkflowResponse {
  execution_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  estimated_duration_hours: number
  current_stage?: string
  progress_percent?: number
}

// GET /api/v1/channel-calibration/workflows/{execution_id}/status
interface WorkflowStatusResponse {
  execution_id: string
  status: string
  stages: Array<{
    name: string
    status: 'pending' | 'running' | 'completed' | 'failed'
    tests: Array<{
      name: string
      status: string
      pass?: boolean
      result_id?: string
    }>
  }>
}
```

## 7. UI设计

### 7.1 信道校准仪表盘

```typescript
// ChannelCalibrationDashboard.tsx

export function ChannelCalibrationDashboard() {
  const { data: status } = useQuery('channel-calibration-status',
    () => api.getChannelCalibrationStatus()
  )

  return (
    <Stack gap="lg">
      <Title order={2}>信道校准管理</Title>

      {/* 总体状态 */}
      <Grid>
        <Grid.Col span={3}>
          <StatCard
            title="时域校准"
            status={status.temporal_status}
            lastCalibrated={status.temporal_last_calibrated}
            nextDue={status.temporal_next_due}
          />
        </Grid.Col>
        <Grid.Col span={3}>
          <StatCard
            title="空间相关性"
            status={status.spatial_correlation_status}
            lastCalibrated={status.spatial_last_calibrated}
            nextDue={status.spatial_next_due}
          />
        </Grid.Col>
        <Grid.Col span={3}>
          <StatCard
            title="静区均匀性"
            status={status.quiet_zone_status}
            lastCalibrated={status.quiet_zone_last_calibrated}
            nextDue={status.quiet_zone_next_due}
          />
        </Grid.Col>
        <Grid.Col span={3}>
          <StatCard
            title="EIS验证"
            status={status.eis_status}
            lastCalibrated={status.eis_last_calibrated}
            nextDue={status.eis_next_due}
          />
        </Grid.Col>
      </Grid>

      {/* 最近校准结果 */}
      <Card withBorder>
        <Title order={4} mb="md">最近校准结果</Title>
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>校准类型</Table.Th>
              <Table.Th>场景</Table.Th>
              <Table.Th>日期</Table.Th>
              <Table.Th>关键指标</Table.Th>
              <Table.Th>结果</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {status.recent_calibrations.map(cal => (
              <Table.Tr key={cal.id}>
                <Table.Td>{cal.type}</Table.Td>
                <Table.Td>{cal.scenario}</Table.Td>
                <Table.Td>{formatDate(cal.calibrated_at)}</Table.Td>
                <Table.Td>
                  {cal.type === 'temporal' && (
                    <Text size="sm">
                      RMS误差: {cal.rms_error_percent.toFixed(1)}%
                    </Text>
                  )}
                  {cal.type === 'spatial_correlation' && (
                    <Text size="sm">
                      相关误差: {cal.magnitude_error.toFixed(3)}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge color={cal.pass ? 'green' : 'red'}>
                    {cal.pass ? 'PASS' : 'FAIL'}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Button
                    size="xs"
                    variant="light"
                    onClick={() => handleViewDetail(cal.id)}
                  >
                    详情
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      {/* 快速操作 */}
      <Group>
        <Button
          leftSection={<IconRefresh />}
          onClick={() => handleStartWorkflow('complete_channel_calibration')}
        >
          完整校准流程
        </Button>
        <Button
          leftSection={<IconFileReport />}
          variant="light"
          onClick={() => handleGenerateReport()}
        >
          生成校准报告
        </Button>
      </Group>
    </Stack>
  )
}
```

### 7.2 校准结果详情视图

```typescript
// TemporalCalibrationDetail.tsx

export function TemporalCalibrationDetail({ calibrationId }: { calibrationId: string }) {
  const { data } = useQuery(['temporal-calibration', calibrationId],
    () => api.getTemporalCalibration(calibrationId)
  )

  return (
    <Stack gap="md">
      <Title order={3}>时域信道校准详情</Title>

      {/* 场景信息 */}
      <Card withBorder>
        <Title order={5} mb="sm">场景配置</Title>
        <Group>
          <Text><strong>类型:</strong> {data.scenario.type}</Text>
          <Text><strong>条件:</strong> {data.scenario.condition}</Text>
          <Text><strong>频率:</strong> {data.scenario.fc_ghz} GHz</Text>
          <Text><strong>距离:</strong> {data.scenario.distance_2d_m} m</Text>
        </Group>
      </Card>

      {/* PDP对比图 */}
      <Card withBorder>
        <Title order={5} mb="sm">功率时延谱对比</Title>
        <LineChart
          data={[
            {
              name: '测量PDP',
              data: data.measured_pdp.delay_bins_ns.map((delay, i) => ({
                x: delay,
                y: data.measured_pdp.power_db[i]
              })),
              color: 'blue'
            },
            {
              name: '3GPP参考簇',
              data: data.measured_params.cluster_delays_ns.map((delay, i) => ({
                x: delay,
                y: data.measured_params.cluster_powers_db[i]
              })),
              type: 'scatter',
              color: 'red'
            }
          ]}
          xLabel="时延 (ns)"
          yLabel="功率 (dB)"
          xScale="linear"
          yScale="linear"
        />
      </Card>

      {/* 参数对比 */}
      <Card withBorder>
        <Title order={5} mb="sm">参数对比</Title>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>参数</Table.Th>
              <Table.Th>测量值</Table.Th>
              <Table.Th>3GPP参考</Table.Th>
              <Table.Th>误差</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            <Table.Tr>
              <Table.Td>RMS时延扩展</Table.Td>
              <Table.Td>{data.measured_params.rms_delay_spread_ns.toFixed(1)} ns</Table.Td>
              <Table.Td>
                {data.reference_params.rms_delay_spread_ns.toFixed(1)} ns
                <br />
                <Text size="xs" c="dimmed">
                  (范围: {data.reference_params.rms_delay_spread_range_ns[0]}-
                  {data.reference_params.rms_delay_spread_range_ns[1]} ns)
                </Text>
              </Table.Td>
              <Table.Td>
                <Badge color={data.validation.rms_error_percent < 10 ? 'green' : 'red'}>
                  {data.validation.rms_error_percent.toFixed(1)}%
                </Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>簇数量</Table.Td>
              <Table.Td>{data.measured_params.num_clusters}</Table.Td>
              <Table.Td>{data.reference_params.num_clusters}</Table.Td>
              <Table.Td>
                <Badge color={data.validation.cluster_count_match ? 'green' : 'yellow'}>
                  {data.validation.cluster_count_match ? '匹配' : '不匹配'}
                </Badge>
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      </Card>

      {/* 验证结果 */}
      <Alert
        icon={data.validation.pass ? <IconCheck /> : <IconX />}
        title={data.validation.pass ? '校准通过' : '校准失败'}
        color={data.validation.pass ? 'green' : 'red'}
      >
        <Text size="sm">
          {data.validation.pass
            ? `RMS时延扩展误差 ${data.validation.rms_error_percent.toFixed(1)}% < ${data.validation.threshold_percent}% (阈值)`
            : `RMS时延扩展误差 ${data.validation.rms_error_percent.toFixed(1)}% > ${data.validation.threshold_percent}% (阈值)，需要重新校准或检查系统配置`
          }
        </Text>
      </Alert>
    </Stack>
  )
}
```

## 8. 实现计划

### Phase 1: 时域校准 (2周)

**Week 1: 后端实现**
- [ ] 时域校准数据模型和数据库
- [ ] PDP测量自动化
- [ ] 3GPP参数提取算法
- [ ] 多普勒谱分析

**Week 2: 验证和API**
- [ ] 验证算法实现
- [ ] REST API设计和实现
- [ ] 单元测试

### Phase 2: 空间校准 (2周)

**Week 3: 空间相关性和角度扩展**
- [ ] 数据模型和数据库
- [ ] 相关性测量自动化
- [ ] 角度扫描控制（转台集成）
- [ ] APS拟合算法

**Week 4: 静区均匀性和EIS**
- [ ] 静区扫描自动化（3D网格）
- [ ] EIS测量流程
- [ ] 数据分析和可视化

### Phase 3: 工作流和UI (1周)

**Week 5: 自动化和UI**
- [ ] 校准工作流引擎
- [ ] ChannelCalibrationDashboard
- [ ] 详情视图组件
- [ ] 报告生成

### Phase 4: 集成和测试 (1周)

**Week 6: 生产就绪**
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档和SOP
- [ ] 用户培训

## 9. 总结

信道校准是MPAC系统准确性的核心保证，本设计实现：

- **3层校准架构**: 时域 → 空间 → 端到端
- **全面覆盖**: 多径、多普勒、相关性、角度扩展、静区均匀性、EIS
- **自动化流程**: 从测量到验证全自动，减少人工干预
- **3GPP对齐**: 所有验证基于3GPP TR 38.901标准
- **可追溯性**: 完整的校准历史和报告

实现后，系统将确保:
- 时延扩展误差 < 10%
- 空间相关误差 < 0.1
- 角度扩展误差 < 5°
- 静区幅度均匀性 < ±1 dB
- EIS测量准确性符合3GPP要求
