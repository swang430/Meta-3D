# Probe Calibration Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Calibration Subsystem (校准子系统)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

探头校准（Probe Calibration）是MIMO OTA测试系统测量准确性的基础。探头校准确保：

1. **幅度一致性**: 所有探头的发射/接收增益已知且可溯源
2. **相位参考**: 所有探头相位相对于参考探头的相位偏差已知
3. **极化纯度**: 双极化探头的V/H极化隔离度满足要求
4. **方向图准确性**: 探头辐射方向图已测量，用于场重构算法
5. **可追溯性**: 校准数据可追溯到国家/国际标准（如NIST）

### 1.2 校准类型

| 校准类型 | 目标参数 | 频率 | 优先级 |
|---------|---------|------|--------|
| **幅度校准** | 增益、功率、插损 | 每月/每季度 | P0 |
| **相位校准** | 相位偏差、群时延 | 每月/每季度 | P0 |
| **极化校准** | 极化隔离度、轴比 | 每季度 | P0 |
| **方向图校准** | 3D辐射方向图 | 每年/更换探头后 | P1 |
| **温度补偿** | 温度系数 | 每年 | P1 |
| **链路校准** | RF链路端到端校准 | 每周 | P0 |

### 1.3 标准依据

- **3GPP TS 34.114**: 5G NR User Equipment (UE) / Base Station (BS) Over-the-Air (OTA) performance requirements
- **CTIA Ver. 4.0**: Test Plan for 2x2 Downlink MIMO and Transmit Diversity Over-the-Air Performance
- **IEC 61094**: Measurement microphones - 校准方法参考
- **ISO/IEC 17025**: Testing and Calibration Laboratories - 质量管理要求

## 2. 系统架构

### 2.1 校准系统组成

```
┌─────────────────────────────────────────────────────────────────┐
│                    Calibration Orchestrator                      │
│  - 校准流程编排                                                   │
│  - 校准数据管理                                                   │
│  - 有效性跟踪                                                     │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Calibration Procedures                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Amplitude  │  │    Phase     │  │ Polarization │           │
│  │  Calibration │  │ Calibration  │  │ Calibration  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Pattern    │  │ Temperature  │  │     Link     │           │
│  │  Calibration │  │ Compensation │  │ Calibration  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Calibration Instruments                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Vector Network│ │ Power Meter  │  │ Signal Gen.  │           │
│  │  Analyzer    │  │ (Calibrated) │  │ (Calibrated) │           │
│  │  (VNA)       │  │              │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Spectrum     │  │ Reference    │  │ Temperature  │           │
│  │ Analyzer     │  │ Antenna      │  │ Chamber      │           │
│  │              │  │ (Traceable)  │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Calibration Data Storage                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database                         │   │
│  │  - 校准系数表 (calibration_coefficients)                  │   │
│  │  - 校准历史表 (calibration_history)                       │   │
│  │  - 有效性跟踪表 (calibration_validity)                    │   │
│  │  - 方向图数据表 (probe_patterns)                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              File Storage (S3/MinIO)                     │   │
│  │  - 原始测量数据 (CSV, Touchstone files)                   │   │
│  │  - 校准报告 (PDF)                                         │   │
│  │  - 校准证书 (PDF with digital signature)                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 校准流程状态机

```
┌─────────────┐
│   Scheduled │  (定期触发或手动触发)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Preparing  │  (预热仪器、检查设备状态)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Measuring  │  (执行校准测量)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Processing  │  (计算校准系数、验证数据质量)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Validating │  (与历史数据对比、异常检测)
└──────┬──────┘
       │
       ├───────────┐
       ▼           ▼
┌─────────────┐ ┌─────────────┐
│  Completed  │ │   Failed    │
└─────────────┘ └─────────────┘
       │
       ▼
┌─────────────┐
│   Applied   │  (校准系数应用到系统)
└─────────────┘
```

## 3. 幅度校准

### 3.1 校准原理

**目标**: 测量每个探头的绝对增益和相对增益一致性。

**方法**: 使用已校准的功率计和信号源，测量每个探头的发射/接收增益。

**链路模型**:
```
TX: Signal Generator → RF Switch Matrix → Probe → Free Space → Reference Antenna → Power Meter

RX: Signal Generator → Reference Antenna → Free Space → Probe → RF Switch Matrix → Spectrum Analyzer
```

### 3.2 校准流程

#### 3.2.1 TX增益校准

**步骤**:
1. 连接参考天线（已校准，增益已知）到功率计
2. 对每个探头 i = 1...N:
   - 设置信号源输出功率 P_in (dBm)
   - 通过RF矩阵路由到探头 i
   - 参考天线接收，功率计测量 P_out (dBm)
   - 计算链路增益: G_link = P_out - P_in
3. 计算探头增益: G_probe_i = G_link - G_ref_antenna - L_free_space + L_switch_matrix

**频率点**: 每个测试频段扫描 (e.g., 3.3-3.8 GHz, 26-30 GHz)

#### 3.2.2 RX增益校准

**步骤**:
1. 连接参考天线到信号源
2. 对每个探头 i = 1...N:
   - 信号源通过参考天线发射已知功率 P_tx
   - 探头 i 接收，通过RF矩阵到频谱分析仪
   - 频谱分析仪测量接收功率 P_rx
   - 计算探头RX增益

**互易性校准**: 在天线互易条件下，TX增益 ≈ RX增益，可用于交叉验证。

### 3.3 校准数据模型

```typescript
interface AmplitudeCalibration {
  probe_id: number
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP'

  // 频率-增益曲线 (单位: dBi)
  frequency_points_mhz: number[]
  tx_gain_dbi: number[]
  rx_gain_dbi: number[]

  // 不确定度 (单位: dB)
  tx_gain_uncertainty_db: number[]
  rx_gain_uncertainty_db: number[]

  // 参考
  reference_antenna: string  // e.g., "Schwarzbeck BBHA 9120 D SN:12345"
  reference_power_meter: string  // e.g., "Keysight N1913A SN:67890"

  // 元数据
  calibrated_at: Date
  calibrated_by: string
  temperature_celsius: number
  humidity_percent: number

  // 有效性
  valid_until: Date
  status: 'valid' | 'expired' | 'invalidated'
}
```

### 3.4 数据库模式

```sql
CREATE TABLE probe_amplitude_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  probe_id INTEGER NOT NULL,
  polarization VARCHAR(10) NOT NULL,

  -- 频率-增益数据 (JSONB数组)
  frequency_points_mhz JSONB NOT NULL,  -- [3300, 3400, ..., 3800]
  tx_gain_dbi JSONB NOT NULL,
  rx_gain_dbi JSONB NOT NULL,
  tx_gain_uncertainty_db JSONB NOT NULL,
  rx_gain_uncertainty_db JSONB NOT NULL,

  -- 参考仪器
  reference_antenna VARCHAR(255),
  reference_power_meter VARCHAR(255),

  -- 环境条件
  temperature_celsius FLOAT,
  humidity_percent FLOAT,

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  -- 有效性
  valid_until TIMESTAMP,
  status VARCHAR(50) DEFAULT 'valid',

  -- 原始数据文件
  raw_data_file_path TEXT,

  -- 索引
  INDEX idx_probe_id (probe_id),
  INDEX idx_valid_until (valid_until),
  INDEX idx_status (status)
);
```

### 3.5 API设计

```typescript
// POST /api/v1/calibration/amplitude/start
interface StartAmplitudeCalibrationRequest {
  probe_ids: number[]  // 要校准的探头ID列表
  polarizations: ('V' | 'H' | 'LHCP' | 'RHCP')[]
  frequency_range_mhz: {
    start: number
    stop: number
    step: number
  }
  reference_antenna_id: string
  power_meter_id: string
}

// GET /api/v1/calibration/amplitude/{probe_id}
interface AmplitudeCalibrationResponse {
  probe_id: number
  calibrations: AmplitudeCalibration[]
  current_valid: AmplitudeCalibration  // 当前有效的校准
}
```

## 4. 相位校准

### 4.1 校准原理

**目标**: 测量每个探头相对于参考探头（通常是Probe 0）的相位偏差。

**挑战**:
- 相位受RF链路长度影响（电缆长度、RF矩阵路径）
- 相位随频率快速变化
- 需要高精度相位测量（±1°或更好）

**方法**: 使用矢量网络分析仪（VNA）测量S参数，提取相位信息。

### 4.2 校准流程

#### 4.2.1 端口延迟校准

**步骤**:
1. 连接VNA到RF矩阵输入端
2. 对每个RF路径，测量S21相位
3. 计算每个路径的电长度（时延）
4. 存储为相位校准的一部分

#### 4.2.2 探头间相位校准

**方法A: 共同参考法**

```
┌──────────────────────────────────────────────┐
│                                              │
│    VNA Port 1 → RF Matrix → Probe i         │
│                                   ↓          │
│                              Reference       │
│                              Antenna (RX)    │
│                                   ↓          │
│    VNA Port 2 ← RF Matrix ← Spectrum Analyzer│
│                                              │
└──────────────────────────────────────────────┘

测量所有探头到参考天线的相位，相对相位 = φ_i - φ_ref (Probe 0)
```

**方法B: 环回法**

如果探头支持TX/RX切换，可使用环回测量：
```
VNA Port 1 → Probe i (TX mode) → Free Space → Probe j (RX mode) → VNA Port 2
```

测量S21相位，消除共模误差。

### 4.3 相位数据模型

```typescript
interface PhaseCalibration {
  probe_id: number
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP'
  reference_probe_id: number  // 通常是 0

  // 频率-相位曲线 (单位: 度)
  frequency_points_mhz: number[]
  phase_offset_deg: number[]  // 相对于参考探头的相位偏差

  // 群时延 (单位: ns)
  group_delay_ns: number[]

  // 不确定度 (单位: 度)
  phase_uncertainty_deg: number[]

  // 参考
  vna_model: string
  vna_serial: string

  // 元数据
  calibrated_at: Date
  calibrated_by: string

  // 有效性
  valid_until: Date
  status: 'valid' | 'expired' | 'invalidated'
}
```

### 4.4 数据库模式

```sql
CREATE TABLE probe_phase_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  probe_id INTEGER NOT NULL,
  polarization VARCHAR(10) NOT NULL,
  reference_probe_id INTEGER NOT NULL DEFAULT 0,

  -- 频率-相位数据
  frequency_points_mhz JSONB NOT NULL,
  phase_offset_deg JSONB NOT NULL,
  group_delay_ns JSONB NOT NULL,
  phase_uncertainty_deg JSONB NOT NULL,

  -- 参考仪器
  vna_model VARCHAR(255),
  vna_serial VARCHAR(255),

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  -- 有效性
  valid_until TIMESTAMP,
  status VARCHAR(50) DEFAULT 'valid',

  -- 原始数据文件 (Touchstone .s2p file)
  raw_data_file_path TEXT,

  INDEX idx_probe_id (probe_id),
  INDEX idx_reference_probe_id (reference_probe_id)
);
```

## 5. 极化校准

### 5.1 校准原理

**目标**: 测量双极化探头的V/H极化隔离度和轴比（对于圆极化）。

**指标**:
- **极化隔离度** (Cross-Polarization Discrimination, XPD): > 20 dB (理想 > 30 dB)
- **轴比** (Axial Ratio, AR): < 3 dB (对于圆极化)

### 5.2 校准流程

#### 5.2.1 极化隔离度测量

**方法**: 旋转参考天线法

**步骤**:
1. 使用线极化参考天线（如偶极子）
2. 设置参考天线为V极化
3. 测量探头V极化端口接收功率 P_VV
4. 测量探头H极化端口接收功率 P_HV (交叉极化)
5. 计算隔离度: XPD_V = P_VV - P_HV (dB)
6. 旋转参考天线到H极化，重复步骤3-5

**合格标准**:
- XPD > 20 dB (最小要求)
- XPD > 30 dB (推荐)

#### 5.2.2 圆极化轴比测量

**方法**: 旋转线极化天线法

**步骤**:
1. 圆极化探头发射
2. 旋转线极化接收天线 0°-360°
3. 记录接收功率随角度变化
4. 拟合为 P(θ) = A + B·cos(2θ + φ)
5. 计算轴比: AR = 20·log10((P_max + P_min) / (P_max - P_min))

**合格标准**:
- AR < 3 dB (圆极化质量好)
- AR < 6 dB (可接受)

### 5.3 极化数据模型

```typescript
interface PolarizationCalibration {
  probe_id: number
  probe_type: 'dual_linear' | 'dual_slant' | 'circular'

  // 线极化探头
  linear_calibration?: {
    v_to_h_isolation_db: number  // V极化端口对H极化的隔离度
    h_to_v_isolation_db: number  // H极化端口对V极化的隔离度
    frequency_points_mhz: number[]
    isolation_vs_frequency_db: number[]
  }

  // 圆极化探头
  circular_calibration?: {
    polarization_hand: 'LHCP' | 'RHCP'
    axial_ratio_db: number
    frequency_points_mhz: number[]
    axial_ratio_vs_frequency_db: number[]
  }

  // 参考
  reference_antenna: string
  positioner: string  // e.g., "Orbit FR 5060 Turntable"

  // 元数据
  calibrated_at: Date
  calibrated_by: string

  // 有效性
  valid_until: Date
  status: 'valid' | 'expired' | 'invalidated'
}
```

### 5.4 数据库模式

```sql
CREATE TABLE probe_polarization_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  probe_id INTEGER NOT NULL,
  probe_type VARCHAR(50) NOT NULL,

  -- 线极化数据
  v_to_h_isolation_db FLOAT,
  h_to_v_isolation_db FLOAT,

  -- 圆极化数据
  polarization_hand VARCHAR(10),
  axial_ratio_db FLOAT,

  -- 频率相关数据
  frequency_points_mhz JSONB,
  isolation_vs_frequency_db JSONB,
  axial_ratio_vs_frequency_db JSONB,

  -- 参考
  reference_antenna VARCHAR(255),
  positioner VARCHAR(255),

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  -- 有效性
  valid_until TIMESTAMP,
  status VARCHAR(50) DEFAULT 'valid',

  INDEX idx_probe_id (probe_id)
);
```

## 6. 方向图校准

### 6.1 校准原理

**目标**: 测量探头的3D辐射方向图（增益随方向变化）。

**用途**:
- 场重构算法需要精确的探头方向图
- 验证探头对称性
- 检测探头损坏（方向图畸变）

### 6.2 测量设置

**方法**: 远场测量法

**设备**:
- 转台（Azimuth + Elevation）
- 参考天线（已校准）
- VNA 或 频谱分析仪 + 信号源

**测量距离**:
- R > 2D²/λ (远场条件)
- D = 探头最大尺寸
- λ = 波长

**例**:
- f = 3.5 GHz, λ = 8.6 cm
- D = 10 cm
- R > 2 × (0.1)² / 0.086 = 0.23 m

实际通常取 R = 1-3 m (留有余量)

### 6.3 测量流程

**步骤**:
1. 固定探头在转台上
2. 参考天线固定在远场位置
3. 扫描方位角 θ: 0°-360°, 步长 5°-10°
4. 扫描俯仰角 φ: 0°-180°, 步长 5°-10°
5. 对每个 (θ, φ) 点，测量接收功率或S21
6. 归一化到最大增益方向，得到方向图 G(θ, φ)

**数据量**:
- θ: 360° / 5° = 72 点
- φ: 180° / 5° = 36 点
- 总测量点: 72 × 36 = 2592 点
- 每个频点约 10-20 分钟

### 6.4 方向图数据模型

```typescript
interface ProbePattern {
  probe_id: number
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP'
  frequency_mhz: number

  // 角度网格
  azimuth_deg: number[]  // [0, 5, 10, ..., 355]
  elevation_deg: number[]  // [0, 5, 10, ..., 180]

  // 方向图数据 (单位: dBi)
  // gain_pattern[i][j] = gain at (azimuth[i], elevation[j])
  gain_pattern_dbi: number[][]  // 2D数组

  // 主要参数
  peak_gain_dbi: number
  peak_direction: {
    azimuth_deg: number
    elevation_deg: number
  }
  half_power_beamwidth_deg: {
    azimuth: number
    elevation: number
  }
  front_to_back_ratio_db: number

  // 参考
  reference_antenna: string
  turntable: string
  measurement_distance_m: number

  // 元数据
  measured_at: Date
  measured_by: string

  // 有效性
  valid_until: Date
  status: 'valid' | 'expired' | 'invalidated'
}
```

### 6.5 数据库模式

```sql
CREATE TABLE probe_patterns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  probe_id INTEGER NOT NULL,
  polarization VARCHAR(10) NOT NULL,
  frequency_mhz FLOAT NOT NULL,

  -- 角度网格
  azimuth_deg JSONB NOT NULL,
  elevation_deg JSONB NOT NULL,

  -- 方向图数据 (存储为扁平数组，前端重构为2D)
  gain_pattern_dbi JSONB NOT NULL,

  -- 主要参数
  peak_gain_dbi FLOAT,
  peak_azimuth_deg FLOAT,
  peak_elevation_deg FLOAT,
  hpbw_azimuth_deg FLOAT,
  hpbw_elevation_deg FLOAT,
  front_to_back_ratio_db FLOAT,

  -- 参考
  reference_antenna VARCHAR(255),
  turntable VARCHAR(255),
  measurement_distance_m FLOAT,

  -- 元数据
  measured_at TIMESTAMP DEFAULT NOW(),
  measured_by VARCHAR(100),

  -- 有效性
  valid_until TIMESTAMP,
  status VARCHAR(50) DEFAULT 'valid',

  -- 原始数据文件
  raw_data_file_path TEXT,

  INDEX idx_probe_id (probe_id),
  INDEX idx_frequency (frequency_mhz)
);
```

## 7. 链路校准

### 7.1 校准原理

**目标**: 快速校准RF链路（信号源 → RF矩阵 → 探头 → 暗室 → DUT）的端到端传输特性。

**频率**: 每周或每次测试前

**方法**: 使用已知DUT（如标准偶极子）进行快速验证。

### 7.2 校准流程

**步骤**:
1. 放置标准偶极子（已知增益）在静区中心
2. 执行简化的OTA测试（单频点，少量角度）
3. 对比测量结果与标准偶极子的已知参数
4. 计算链路校准系数
5. 如果偏差 > 阈值（如 ±1 dB），触发告警

### 7.3 链路校准数据模型

```typescript
interface LinkCalibration {
  id: string
  calibration_type: 'weekly_check' | 'pre_test' | 'post_maintenance'

  // 标准DUT
  standard_dut: {
    type: 'dipole' | 'horn' | 'patch'
    model: string
    serial: string
    known_gain_dbi: number
    frequency_mhz: number
  }

  // 测量结果
  measured_gain_dbi: number
  deviation_db: number

  // 探头级别的链路校准系数
  probe_link_calibrations: Array<{
    probe_id: number
    link_loss_db: number
    phase_offset_deg: number
  }>

  // 合格判定
  pass: boolean
  threshold_db: number

  // 元数据
  calibrated_at: Date
  calibrated_by: string
}
```

### 7.4 数据库模式

```sql
CREATE TABLE link_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  calibration_type VARCHAR(50) NOT NULL,

  -- 标准DUT
  standard_dut_type VARCHAR(50),
  standard_dut_model VARCHAR(255),
  standard_dut_serial VARCHAR(255),
  known_gain_dbi FLOAT,
  frequency_mhz FLOAT,

  -- 测量结果
  measured_gain_dbi FLOAT,
  deviation_db FLOAT,

  -- 探头链路校准 (JSONB数组)
  probe_link_calibrations JSONB,

  -- 合格判定
  pass BOOLEAN,
  threshold_db FLOAT DEFAULT 1.0,

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  INDEX idx_calibrated_at (calibrated_at),
  INDEX idx_pass (pass)
);
```

## 8. 校准有效性管理

### 8.1 有效期策略

| 校准类型 | 推荐有效期 | 触发条件 |
|---------|----------|---------|
| 幅度校准 | 3个月 | 定期或探头更换 |
| 相位校准 | 3个月 | 定期或RF链路变更 |
| 极化校准 | 6个月 | 定期或探头更换 |
| 方向图校准 | 12个月 | 定期或探头损坏 |
| 链路校准 | 7天 | 定期或系统维护后 |

### 8.2 自动过期检测

```typescript
interface CalibrationValidityChecker {
  // 检查所有校准有效性
  checkAllCalibrations(): Promise<CalibrationValidityReport>

  // 检查单个探头
  checkProbeCalibration(probeId: number): Promise<ProbeCalibrationStatus>

  // 自动触发重新校准
  scheduleRecalibration(probeId: number, calibrationType: string): Promise<void>
}

interface CalibrationValidityReport {
  total_probes: number
  valid_probes: number
  expired_probes: number
  expiring_soon_probes: number  // 7天内过期

  expired_calibrations: Array<{
    probe_id: number
    calibration_type: string
    expired_at: Date
    days_overdue: number
  }>

  expiring_soon_calibrations: Array<{
    probe_id: number
    calibration_type: string
    valid_until: Date
    days_remaining: number
  }>
}
```

### 8.3 数据库模式

```sql
CREATE TABLE calibration_validity_status (
  probe_id INTEGER PRIMARY KEY,

  -- 各类校准的有效性
  amplitude_valid BOOLEAN DEFAULT FALSE,
  amplitude_valid_until TIMESTAMP,

  phase_valid BOOLEAN DEFAULT FALSE,
  phase_valid_until TIMESTAMP,

  polarization_valid BOOLEAN DEFAULT FALSE,
  polarization_valid_until TIMESTAMP,

  pattern_valid BOOLEAN DEFAULT FALSE,
  pattern_valid_until TIMESTAMP,

  link_valid BOOLEAN DEFAULT FALSE,
  link_valid_until TIMESTAMP,

  -- 总体状态
  overall_status VARCHAR(50),  -- 'valid', 'expiring_soon', 'expired'

  -- 最后更新
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 视图：获取过期或即将过期的校准
CREATE VIEW calibrations_needing_attention AS
SELECT
  probe_id,
  'amplitude' AS calibration_type,
  amplitude_valid_until AS valid_until,
  CASE
    WHEN amplitude_valid_until < NOW() THEN 'expired'
    WHEN amplitude_valid_until < NOW() + INTERVAL '7 days' THEN 'expiring_soon'
    ELSE 'valid'
  END AS status
FROM calibration_validity_status
WHERE amplitude_valid_until < NOW() + INTERVAL '7 days'

UNION ALL

SELECT
  probe_id,
  'phase' AS calibration_type,
  phase_valid_until AS valid_until,
  CASE
    WHEN phase_valid_until < NOW() THEN 'expired'
    WHEN phase_valid_until < NOW() + INTERVAL '7 days' THEN 'expiring_soon'
    ELSE 'valid'
  END AS status
FROM calibration_validity_status
WHERE phase_valid_until < NOW() + INTERVAL '7 days'

-- ... 其他校准类型类似 ...
;
```

## 9. API设计

### 9.1 校准执行API

```typescript
// POST /api/v1/calibration/execute
interface ExecuteCalibrationRequest {
  calibration_type: 'amplitude' | 'phase' | 'polarization' | 'pattern' | 'link'
  probe_ids: number[]
  configuration: {
    frequency_range_mhz?: { start: number; stop: number; step: number }
    reference_instruments?: {
      antenna_id?: string
      vna_id?: string
      power_meter_id?: string
    }
    automation?: {
      auto_apply: boolean  // 自动应用校准系数
      notify_on_complete: boolean
    }
  }
}

interface ExecuteCalibrationResponse {
  calibration_job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  estimated_duration_minutes: number
  progress?: {
    current_probe: number
    total_probes: number
    current_frequency: number
    total_frequencies: number
  }
}

// GET /api/v1/calibration/status/{job_id}
interface CalibrationJobStatus {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress_percent: number
  current_step: string
  results?: CalibrationResult[]
  error_message?: string
}
```

### 9.2 校准数据查询API

```typescript
// GET /api/v1/calibration/probes/{probe_id}
interface ProbeCalibrationData {
  probe_id: number
  amplitude_calibration: AmplitudeCalibration | null
  phase_calibration: PhaseCalibration | null
  polarization_calibration: PolarizationCalibration | null
  pattern_calibration: ProbePattern[] | null  // 多个频点
  link_calibration: LinkCalibration | null

  validity_status: {
    overall: 'valid' | 'expiring_soon' | 'expired'
    amplitude: { status: string; valid_until: Date }
    phase: { status: string; valid_until: Date }
    polarization: { status: string; valid_until: Date }
    pattern: { status: string; valid_until: Date }
    link: { status: string; valid_until: Date }
  }
}

// GET /api/v1/calibration/validity/report
interface CalibrationValidityReportResponse {
  report: CalibrationValidityReport
  recommendations: Array<{
    probe_id: number
    calibration_type: string
    action: 'recalibrate_now' | 'schedule_soon' | 'monitor'
    priority: 'critical' | 'high' | 'medium' | 'low'
    reason: string
  }>
}
```

### 9.3 校准历史API

```typescript
// GET /api/v1/calibration/history/{probe_id}
interface CalibrationHistoryRequest {
  probe_id: number
  calibration_type?: string
  start_date?: Date
  end_date?: Date
  limit?: number
}

interface CalibrationHistoryResponse {
  probe_id: number
  history: Array<{
    calibration_id: string
    calibration_type: string
    calibrated_at: Date
    calibrated_by: string
    status: 'valid' | 'expired' | 'superseded'
    summary: {
      // 关键参数摘要
      [key: string]: any
    }
  }>

  // 趋势分析
  trends?: {
    amplitude_drift_db_per_month: number
    phase_drift_deg_per_month: number
    stability_rating: 'excellent' | 'good' | 'fair' | 'poor'
  }
}
```

## 10. UI设计

### 10.1 校准仪表盘

```typescript
// CalibrationDashboard.tsx

export function CalibrationDashboard() {
  const { data: validityReport } = useQuery('calibration-validity',
    () => api.getCalibrationValidityReport()
  )

  return (
    <Stack gap="lg">
      <Title order={2}>校准管理</Title>

      {/* 总体状态 */}
      <Group grow>
        <StatCard
          title="校准有效探头"
          value={validityReport.valid_probes}
          total={validityReport.total_probes}
          color="green"
          icon={<IconCheck />}
        />
        <StatCard
          title="即将过期"
          value={validityReport.expiring_soon_probes}
          total={validityReport.total_probes}
          color="yellow"
          icon={<IconAlertTriangle />}
        />
        <StatCard
          title="已过期"
          value={validityReport.expired_probes}
          total={validityReport.total_probes}
          color="red"
          icon={<IconX />}
        />
      </Group>

      {/* 过期告警 */}
      {validityReport.expired_calibrations.length > 0 && (
        <Alert
          icon={<IconAlertCircle />}
          title="校准过期告警"
          color="red"
        >
          <Stack gap="xs">
            {validityReport.expired_calibrations.map(cal => (
              <Text key={`${cal.probe_id}-${cal.calibration_type}`} size="sm">
                探头 #{cal.probe_id} - {cal.calibration_type} 已过期 {cal.days_overdue} 天
              </Text>
            ))}
          </Stack>
          <Button
            mt="md"
            color="red"
            onClick={() => handleBatchRecalibrate(validityReport.expired_calibrations)}
          >
            批量重新校准
          </Button>
        </Alert>
      )}

      {/* 探头校准状态表格 */}
      <Card withBorder>
        <Title order={4} mb="md">探头校准状态</Title>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>探头ID</Table.Th>
              <Table.Th>幅度校准</Table.Th>
              <Table.Th>相位校准</Table.Th>
              <Table.Th>极化校准</Table.Th>
              <Table.Th>方向图校准</Table.Th>
              <Table.Th>链路校准</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {probes.map(probe => (
              <Table.Tr key={probe.id}>
                <Table.Td>
                  <Badge>#{probe.id}</Badge>
                </Table.Td>
                <Table.Td>
                  <CalibrationStatusBadge
                    status={probe.amplitude_status}
                    validUntil={probe.amplitude_valid_until}
                  />
                </Table.Td>
                <Table.Td>
                  <CalibrationStatusBadge
                    status={probe.phase_status}
                    validUntil={probe.phase_valid_until}
                  />
                </Table.Td>
                <Table.Td>
                  <CalibrationStatusBadge
                    status={probe.polarization_status}
                    validUntil={probe.polarization_valid_until}
                  />
                </Table.Td>
                <Table.Td>
                  <CalibrationStatusBadge
                    status={probe.pattern_status}
                    validUntil={probe.pattern_valid_until}
                  />
                </Table.Td>
                <Table.Td>
                  <CalibrationStatusBadge
                    status={probe.link_status}
                    validUntil={probe.link_valid_until}
                  />
                </Table.Td>
                <Table.Td>
                  <Menu>
                    <Menu.Target>
                      <Button size="xs" variant="light">操作</Button>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item
                        icon={<IconRefresh />}
                        onClick={() => handleRecalibrate(probe.id, 'all')}
                      >
                        全部重新校准
                      </Menu.Item>
                      <Menu.Item
                        icon={<IconHistory />}
                        onClick={() => handleViewHistory(probe.id)}
                      >
                        查看校准历史
                      </Menu.Item>
                      <Menu.Item
                        icon={<IconDownload />}
                        onClick={() => handleDownloadCertificate(probe.id)}
                      >
                        下载校准证书
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  )
}

function CalibrationStatusBadge({
  status,
  validUntil
}: {
  status: string
  validUntil: Date
}) {
  const daysRemaining = Math.ceil((validUntil.getTime() - Date.now()) / (1000 * 60 * 60 * 24))

  let color = 'green'
  let label = '有效'

  if (daysRemaining < 0) {
    color = 'red'
    label = '已过期'
  } else if (daysRemaining <= 7) {
    color = 'yellow'
    label = `${daysRemaining}天后过期`
  } else {
    label = `${daysRemaining}天`
  }

  return (
    <Tooltip label={`有效期至: ${validUntil.toLocaleDateString()}`}>
      <Badge color={color} size="sm" variant="dot">
        {label}
      </Badge>
    </Tooltip>
  )
}
```

### 10.2 校准执行向导

```typescript
// CalibrationWizard.tsx

export function CalibrationWizard() {
  const [currentStep, setCurrentStep] = useState(0)
  const [config, setConfig] = useState<ExecuteCalibrationRequest>({
    calibration_type: 'amplitude',
    probe_ids: [],
    configuration: {}
  })

  return (
    <Modal opened size="xl" title="校准执行向导">
      <Stepper active={currentStep}>
        {/* Step 1: 选择校准类型 */}
        <Stepper.Step label="校准类型">
          <Radio.Group
            value={config.calibration_type}
            onChange={(val) => setConfig({ ...config, calibration_type: val })}
          >
            <Stack gap="sm">
              <Radio value="amplitude" label="幅度校准 (增益)" />
              <Radio value="phase" label="相位校准 (相位偏差)" />
              <Radio value="polarization" label="极化校准 (隔离度/轴比)" />
              <Radio value="pattern" label="方向图校准 (3D增益)" />
              <Radio value="link" label="链路校准 (端到端验证)" />
            </Stack>
          </Radio.Group>
        </Stepper.Step>

        {/* Step 2: 选择探头 */}
        <Stepper.Step label="选择探头">
          <MultiSelect
            label="要校准的探头"
            data={probes.map(p => ({
              value: String(p.id),
              label: `探头 #${p.id} (${p.polarization})`
            }))}
            value={config.probe_ids.map(String)}
            onChange={(val) => setConfig({
              ...config,
              probe_ids: val.map(Number)
            })}
          />
          <Button
            mt="md"
            variant="light"
            onClick={() => setConfig({
              ...config,
              probe_ids: probes.map(p => p.id)
            })}
          >
            全选
          </Button>
        </Stepper.Step>

        {/* Step 3: 配置参数 */}
        <Stepper.Step label="配置参数">
          {config.calibration_type === 'amplitude' && (
            <AmplitudeCalibrationConfig
              value={config.configuration}
              onChange={(val) => setConfig({ ...config, configuration: val })}
            />
          )}
          {/* ... 其他校准类型的配置组件 ... */}
        </Stepper.Step>

        {/* Step 4: 确认并执行 */}
        <Stepper.Step label="确认执行">
          <CalibrationSummary config={config} />
          <Button
            mt="lg"
            size="lg"
            fullWidth
            onClick={handleExecuteCalibration}
          >
            开始校准
          </Button>
        </Stepper.Step>
      </Stepper>

      <Group justify="space-between" mt="xl">
        <Button
          variant="default"
          onClick={() => setCurrentStep(currentStep - 1)}
          disabled={currentStep === 0}
        >
          上一步
        </Button>
        <Button
          onClick={() => setCurrentStep(currentStep + 1)}
          disabled={currentStep === 3}
        >
          下一步
        </Button>
      </Group>
    </Modal>
  )
}
```

## 11. 实现计划

### Phase 1: 基础框架 (2周)

**Week 1: 数据库和数据模型**
- [ ] 创建数据库表（amplitude, phase, polarization, pattern, link, validity）
- [ ] 实现数据模型（TypeScript interfaces, Pydantic models）
- [ ] 文件存储集成（S3/MinIO for raw data）

**Week 2: 幅度和相位校准**
- [ ] 幅度校准流程实现
- [ ] 相位校准流程实现
- [ ] 仪器HAL集成（VNA, Power Meter）
- [ ] 校准数据存储和查询API

### Phase 2: 高级校准 (2周)

**Week 3: 极化和方向图校准**
- [ ] 极化校准流程
- [ ] 方向图测量自动化（转台控制）
- [ ] 方向图数据处理和可视化

**Week 4: 链路校准和有效性管理**
- [ ] 链路校准快速验证
- [ ] 有效性跟踪系统
- [ ] 自动过期检测和告警

### Phase 3: UI和自动化 (1周)

**Week 5: UI组件**
- [ ] CalibrationDashboard
- [ ] CalibrationWizard
- [ ] ProbeCalibrationDetail视图
- [ ] 校准历史趋势图

### Phase 4: 生产就绪 (1周)

**Week 6: 测试和文档**
- [ ] 单元测试
- [ ] 集成测试
- [ ] 用户手册
- [ ] 校准SOP (Standard Operating Procedure)

## 12. 总结

探头校准是MIMO OTA测试系统的基石，确保测量准确性和可追溯性。本设计涵盖：

- **5种校准类型**: 幅度、相位、极化、方向图、链路
- **完整数据管理**: 校准系数、历史、有效性跟踪
- **自动化流程**: 从测量到数据处理全自动
- **可追溯性**: 符合ISO/IEC 17025要求

实现后，系统将提供：
- 准确性: ±0.5 dB 幅度, ±1° 相位
- 效率: 自动化校准，减少人工干预
- 可靠性: 有效性跟踪，防止使用过期校准
- 合规性: 符合3GPP/CTIA标准
