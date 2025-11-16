# System Calibration Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Calibration Subsystem (校准子系统)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

系统级校准（System-Level Calibration）是MPAC测试系统校准体系的最高层，验证整个系统（探头、信道仿真器、基站仿真器、RF链路、控制软件）作为一个整体能否准确、可靠地执行OTA测试。

与探头校准（Level 0）和信道校准（Level 1-2）关注单个组件不同，系统级校准关注：

1. **端到端准确性**: 从输入信号到最终测量结果的全链路准确性
2. **系统可重复性**: 同一测试重复执行的结果一致性
3. **系统可比性**: 与参考实验室/标准的对比
4. **合规性**: 符合3GPP/CTIA/FCC等标准要求

### 1.2 校准层次关系

```
┌────────────────────────────────────────────────────────────┐
│          Level 3: System-Level Calibration                 │
│  - 端到端TRP/TIS/EIS验证                                    │
│  - 标准DUT对比测试                                          │
│  - 实验室间比对                                             │
└────────────────────────────────────────────────────────────┘
                         ▲
          ┌──────────────┴──────────────┐
          │                             │
┌─────────┴──────────┐      ┌───────────┴──────────┐
│ Level 2: Spatial   │      │ Level 1: Temporal    │
│ Channel Calib      │      │ Channel Calib        │
│ (Channel-Calib.md) │      │ (Channel-Calib.md)   │
└─────────┬──────────┘      └───────────┬──────────┘
          │                             │
          └──────────────┬──────────────┘
                         ▼
        ┌────────────────────────────────┐
        │  Level 0: Probe Calibration    │
        │  (Probe-Calibration-Design.md) │
        └────────────────────────────────┘
```

### 1.3 标准依据

- **3GPP TS 34.114**: 5G NR UE/BS OTA performance requirements
- **CTIA OTA Test Plan Ver. 4.0**: Certification test requirements
- **FCC KDB 971168**: Guidance on OTA measurements
- **CISPR 16**: Specification for radio disturbance and immunity measuring apparatus
- **ISO/IEC 17025**: General requirements for the competence of testing and calibration laboratories

## 2. 系统校准类型

### 2.1 TRP校准 (Total Radiated Power)

**定义**: 总辐射功率，DUT在所有方向上辐射的总功率。

**数学定义**:
```
TRP = ∫∫ ERP(θ, φ) · sin(θ) dθ dφ / (4π)

其中:
ERP(θ, φ) = 有效辐射功率（方向性增益）
积分覆盖整个球面
```

**物理意义**: 验证MPAC系统能否准确测量DUT的发射功率。

**校准方法**:
1. 使用已知TRP的标准DUT（如标准偶极子，TRP已由参考实验室测量）
2. 在MPAC系统中测量TRP
3. 对比测量值与参考值
4. 误差应在 ±0.5 dB 以内

### 2.2 TIS校准 (Total Isotropic Sensitivity)

**定义**: 总全向灵敏度，DUT在所有方向上的平均接收灵敏度。

**数学定义**:
```
TIS = -10 · log10( ∫∫ 10^(-EIS(θ,φ)/10) · sin(θ) dθ dφ / (4π) )

其中:
EIS(θ, φ) = 等效全向灵敏度（方向性）
```

**物理意义**: 验证MPAC系统能否准确测量DUT的接收性能。

**校准方法**:
1. 使用已知TIS的标准DUT
2. 在MPAC系统中测量TIS
3. 对比测量值与参考值
4. 误差应在 ±1 dB 以内

### 2.3 EIS校准 (Equivalent Isotropic Sensitivity)

**定义**: 在MIMO OTA测试中，EIS是最重要的性能指标。

**校准方法**: 见 Channel-Calibration-Design.md Section 5

### 2.4 可重复性验证 (Repeatability)

**定义**: 同一DUT，同一测试配置，重复测量N次，结果的一致性。

**指标**:
```
Repeatability = σ / μ

其中:
σ = 标准差
μ = 平均值
```

**要求**:
- TRP可重复性: σ < 0.3 dB
- TIS可重复性: σ < 0.5 dB
- EIS可重复性: σ < 0.5 dB

### 2.5 可比性验证 (Comparability)

**定义**: 与参考实验室（如国家计量院、CTIA认证实验室）的测量结果对比。

**方法**: 循环比对（Round Robin Test）
1. 选择稳定的标准DUT
2. 分别在本实验室和参考实验室测量
3. 对比结果
4. 差异应在 ±1 dB 以内

## 3. 系统架构

### 3.1 校准系统组件

```
┌─────────────────────────────────────────────────────────────────┐
│               System Calibration Orchestrator                    │
│  - 端到端测试流程编排                                             │
│  - 标准DUT管理                                                    │
│  - 实验室间比对协调                                               │
│  - 校准证书生成                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Calibration Test Suites                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │     TRP      │  │     TIS      │  │     EIS      │           │
│  │  Validation  │  │  Validation  │  │  Validation  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Repeatability│  │Comparability │  │  Compliance  │           │
│  │     Test     │  │     Test     │  │     Check    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Standard DUT Library                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Dipole     │  │  Patch Array │  │  Reference   │           │
│  │   (Known TRP)│  │  (Known TIS) │  │  Smartphone  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Complete MPAC System                          │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Probes + Channel Emulator + Base Station + Control   │     │
│  └────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Calibration Data & Certificates                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            PostgreSQL Database                           │   │
│  │  - system_trp_calibrations                               │   │
│  │  - system_tis_calibrations                               │   │
│  │  - repeatability_tests                                   │   │
│  │  - comparability_tests                                   │   │
│  │  - calibration_certificates                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 校准工作流

```
┌─────────────┐
│   Start     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Pre-Check   │ - 验证所有组件校准有效性
│             │ - 预热仪器（30分钟）
│             │ - 环境检查（温度、湿度）
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ TRP Test    │ - 标准DUT TRP测量
│             │ - 与参考值对比
│             │ - 误差 < ±0.5 dB?
└──────┬──────┘
       │
       ├──Yes──┐
       │       ▼
       │  ┌─────────────┐
       │  │ TIS Test    │
       │  │             │
       │  │ 误差 < ±1dB?│
       │  └──────┬──────┘
       │         │
       │    Yes──┤
       │         ▼
       │  ┌─────────────┐
       │  │ EIS Test    │
       │  │             │
       │  │ 误差 < ±1dB?│
       │  └──────┬──────┘
       │         │
       │    Yes──┤
       │         ▼
       │  ┌─────────────┐
       │  │Repeatability│
       │  │   Test      │
       │  │ σ < 0.5dB?  │
       │  └──────┬──────┘
       │         │
       │    Yes──┤
       │         ▼
       │  ┌─────────────┐
       │  │ Certificate │
       │  │ Generation  │
       │  └──────┬──────┘
       │         │
       │         ▼
       │  ┌─────────────┐
       │  │  Completed  │
       │  └─────────────┘
       │
       └──No───┐
               ▼
        ┌─────────────┐
        │   Failed    │
        │ - Root Cause│
        │ - Corrective│
        │   Action    │
        └─────────────┘
```

## 4. TRP校准详细设计

### 4.1 标准DUT选择

**推荐标准DUT**:

| DUT类型 | 频段 | 参考TRP | 用途 |
|--------|------|---------|------|
| λ/2偶极子 | Sub-6 GHz | 理论值: 0 dBi | 基础验证 |
| λ/4单极子 | Sub-6 GHz | 理论值: -2.1 dBi | 基础验证 |
| 2x2贴片阵列 | Sub-6 GHz | 实测值: XX dBm | MIMO验证 |
| 标准手机模型 | Sub-6 GHz | 实测值: YY dBm | 实际应用验证 |

**参考TRP获取**:
1. 理论计算（偶极子、单极子）
2. 参考实验室测量（CTIA认证实验室）
3. 制造商提供（带校准证书）

### 4.2 TRP测量流程

#### 4.2.1 测量配置

**发射参数**:
- 频率: 3.5 GHz (示例)
- 带宽: 20 MHz
- 调制: CW (连续波) 或 QPSK
- 发射功率: 23 dBm (典型值)

**测量网格**:
- 方位角 θ: 0° - 360°, 步长 15°
- 俯仰角 φ: 0° - 180°, 步长 15°
- 总测量点: 24 × 13 = 312 点

#### 4.2.2 数据采集

对每个 (θ, φ) 点:
1. 转台旋转到指定角度
2. DUT发射信号
3. 探头阵列接收（多个探头同时采样，选择信号最强的）
4. 功率计测量接收功率 P_rx(θ, φ)
5. 计算有效辐射功率:
   ```
   ERP(θ, φ) = P_rx(θ, φ) + L_path - G_probe
   ```

#### 4.2.3 TRP计算

```typescript
function calculateTRP(
  erpMap: number[][]  // ERP(θ, φ) in dBm
): number {
  let sumLinear = 0
  const thetaStep = 15 * Math.PI / 180
  const phiStep = 15 * Math.PI / 180

  for (let i = 0; i < erpMap.length; i++) {
    const theta = i * thetaStep
    for (let j = 0; j < erpMap[i].length; j++) {
      const erpDbm = erpMap[i][j]
      const erpLinear = Math.pow(10, erpDbm / 10)  // dBm to mW

      // 球面积分权重
      const weight = Math.sin(theta) * thetaStep * phiStep

      sumLinear += erpLinear * weight
    }
  }

  // 归一化到4π球面
  const trpLinear = sumLinear / (4 * Math.PI)

  // 转换回dBm
  const trpDbm = 10 * Math.log10(trpLinear)

  return trpDbm
}
```

### 4.3 数据模型

```typescript
interface TRPCalibration {
  id: string

  // 标准DUT
  standard_dut: {
    type: 'dipole' | 'monopole' | 'patch_array' | 'reference_phone'
    model: string
    serial: string
    reference_trp_dbm: number
    reference_lab: string  // 参考实验室
    reference_certificate_id: string
  }

  // 测试配置
  test_config: {
    fc_ghz: number
    bandwidth_mhz: number
    modulation: string
    tx_power_dbm: number
    measurement_grid: {
      theta_step_deg: number
      phi_step_deg: number
      total_points: number
    }
  }

  // 测量数据
  measured_data: {
    erp_map_dbm: number[][]  // ERP(θ, φ)
    theta_deg: number[]
    phi_deg: number[]
  }

  // 计算结果
  results: {
    measured_trp_dbm: number
    reference_trp_dbm: number
    error_db: number
  }

  // 验证
  validation: {
    pass: boolean
    threshold_db: number  // 0.5 dB
    notes?: string
  }

  // 元数据
  calibrated_at: Date
  calibrated_by: string
  temperature_celsius: number
  humidity_percent: number
}
```

### 4.4 数据库模式

```sql
CREATE TABLE system_trp_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 标准DUT
  dut_type VARCHAR(50) NOT NULL,
  dut_model VARCHAR(255) NOT NULL,
  dut_serial VARCHAR(255) NOT NULL,
  reference_trp_dbm FLOAT NOT NULL,
  reference_lab VARCHAR(255),
  reference_certificate_id VARCHAR(255),

  -- 测试配置
  fc_ghz FLOAT NOT NULL,
  bandwidth_mhz FLOAT,
  modulation VARCHAR(50),
  tx_power_dbm FLOAT,

  -- 测量网格
  theta_step_deg FLOAT,
  phi_step_deg FLOAT,
  total_points INTEGER,

  -- 测量数据
  erp_map_dbm JSONB NOT NULL,  -- 2D array
  theta_deg JSONB,
  phi_deg JSONB,

  -- 结果
  measured_trp_dbm FLOAT NOT NULL,
  error_db FLOAT NOT NULL,

  -- 验证
  validation_pass BOOLEAN NOT NULL,
  threshold_db FLOAT DEFAULT 0.5,
  notes TEXT,

  -- 环境
  temperature_celsius FLOAT,
  humidity_percent FLOAT,

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  INDEX idx_validation_pass (validation_pass),
  INDEX idx_calibrated_at (calibrated_at)
);
```

## 5. TIS校准详细设计

### 5.1 TIS测量流程

TIS测量与TRP测量类似，但DUT处于接收模式。

#### 5.1.1 测量配置

**接收参数**:
- 频率: 3.5 GHz
- 带宽: 20 MHz
- 调制: QPSK
- 目标吞吐量: 95% 最大吞吐量

**测量流程**:
1. 配置基站仿真器发射信号
2. 信号通过信道仿真器和探头阵列
3. 对每个 (θ, φ) 方向:
   - 旋转DUT到指定角度
   - 调整输入功率，找到DUT达到目标吞吐量的最小功率
   - 记录该功率为 EIS(θ, φ)
4. 计算TIS:
   ```
   TIS = -10 · log10( Σ 10^(-EIS(θ,φ)/10) · Δ(θ,φ) / (4π) )
   ```

### 5.2 数据模型

```typescript
interface TISCalibration {
  id: string

  standard_dut: {
    type: string
    model: string
    serial: string
    reference_tis_dbm: number
    reference_lab: string
  }

  test_config: {
    fc_ghz: number
    bandwidth_mhz: number
    modulation: string
    target_throughput_mbps: number
  }

  measured_data: {
    eis_map_dbm: number[][]  // EIS(θ, φ)
    theta_deg: number[]
    phi_deg: number[]
  }

  results: {
    measured_tis_dbm: number
    reference_tis_dbm: number
    error_db: number
  }

  validation: {
    pass: boolean
    threshold_db: number  // 1.0 dB
  }

  calibrated_at: Date
  calibrated_by: string
}
```

### 5.3 数据库模式

```sql
CREATE TABLE system_tis_calibrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 标准DUT
  dut_type VARCHAR(50),
  dut_model VARCHAR(255),
  dut_serial VARCHAR(255),
  reference_tis_dbm FLOAT NOT NULL,
  reference_lab VARCHAR(255),

  -- 测试配置
  fc_ghz FLOAT NOT NULL,
  bandwidth_mhz FLOAT,
  modulation VARCHAR(50),
  target_throughput_mbps FLOAT,

  -- 测量数据
  eis_map_dbm JSONB NOT NULL,
  theta_deg JSONB,
  phi_deg JSONB,

  -- 结果
  measured_tis_dbm FLOAT NOT NULL,
  error_db FLOAT NOT NULL,

  -- 验证
  validation_pass BOOLEAN NOT NULL,
  threshold_db FLOAT DEFAULT 1.0,

  -- 元数据
  calibrated_at TIMESTAMP DEFAULT NOW(),
  calibrated_by VARCHAR(100),

  INDEX idx_validation_pass (validation_pass)
);
```

## 6. 可重复性测试

### 6.1 测试流程

**目标**: 验证系统测量的稳定性。

**方法**:
1. 选择稳定的标准DUT
2. 重复测量N次（N ≥ 10）
3. 计算统计参数：
   - 平均值 μ
   - 标准差 σ
   - 变异系数 CV = σ / μ

**合格标准**:
- TRP: σ < 0.3 dB
- TIS: σ < 0.5 dB
- EIS: σ < 0.5 dB

### 6.2 数据模型

```typescript
interface RepeatabilityTest {
  id: string

  test_type: 'TRP' | 'TIS' | 'EIS'

  standard_dut: {
    model: string
    serial: string
  }

  // 重复测量
  measurements: Array<{
    run_number: number
    value_dbm: number
    timestamp: Date
  }>

  // 统计分析
  statistics: {
    num_runs: number
    mean_dbm: number
    std_dev_db: number
    coefficient_of_variation: number
    min_dbm: number
    max_dbm: number
    range_db: number
  }

  // 验证
  validation: {
    pass: boolean
    threshold_db: number  // 0.3 for TRP, 0.5 for TIS/EIS
  }

  tested_at: Date
  tested_by: string
}
```

### 6.3 数据库模式

```sql
CREATE TABLE repeatability_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  test_type VARCHAR(50) NOT NULL,

  -- 标准DUT
  dut_model VARCHAR(255),
  dut_serial VARCHAR(255),

  -- 测量数据
  measurements JSONB NOT NULL,  -- [{run_number, value_dbm, timestamp}, ...]

  -- 统计
  num_runs INTEGER NOT NULL,
  mean_dbm FLOAT NOT NULL,
  std_dev_db FLOAT NOT NULL,
  coefficient_of_variation FLOAT,
  min_dbm FLOAT,
  max_dbm FLOAT,
  range_db FLOAT,

  -- 验证
  validation_pass BOOLEAN NOT NULL,
  threshold_db FLOAT NOT NULL,

  tested_at TIMESTAMP DEFAULT NOW(),
  tested_by VARCHAR(100),

  INDEX idx_test_type (test_type),
  INDEX idx_validation_pass (validation_pass)
);
```

## 7. 可比性测试（实验室间比对）

### 7.1 循环比对流程

**参与方**:
- 本实验室 (Lab A)
- 参考实验室 (Lab B, C, ...)

**流程**:
1. 选择稳定的标准DUT（如标准手机）
2. Lab A测量TRP/TIS/EIS
3. DUT运输到Lab B
4. Lab B测量TRP/TIS/EIS
5. 对比结果
6. 如有多个实验室，继续循环

**评估指标**:
```
Bias = Measurement_A - Measurement_B
Acceptable if |Bias| < 1 dB
```

### 7.2 数据模型

```typescript
interface ComparabilityTest {
  id: string
  round_robin_id: string  // 多个实验室共享

  // 本实验室信息
  lab_info: {
    lab_name: string
    lab_id: string
    accreditation: string  // e.g., "ISO/IEC 17025:2017"
  }

  // 标准DUT
  standard_dut: {
    model: string
    serial: string
    stable: boolean  // 稳定性检查
  }

  // 本实验室测量
  local_measurements: {
    trp_dbm: number
    tis_dbm: number
    eis_dbm: number
    measured_at: Date
  }

  // 参考实验室测量
  reference_measurements: Array<{
    lab_name: string
    lab_id: string
    trp_dbm: number
    tis_dbm: number
    eis_dbm: number
    measured_at: Date
  }>

  // 对比分析
  comparison: {
    trp_bias_db: number[]  // vs. each reference lab
    tis_bias_db: number[]
    eis_bias_db: number[]

    trp_mean_bias_db: number
    tis_mean_bias_db: number
    eis_mean_bias_db: number
  }

  // 验证
  validation: {
    pass: boolean
    threshold_db: number  // 1.0 dB
    notes?: string
  }

  tested_at: Date
  tested_by: string
}
```

### 7.3 数据库模式

```sql
CREATE TABLE comparability_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  round_robin_id UUID,  -- 共享ID

  -- 实验室信息
  lab_name VARCHAR(255) NOT NULL,
  lab_id VARCHAR(100),
  lab_accreditation VARCHAR(255),

  -- 标准DUT
  dut_model VARCHAR(255),
  dut_serial VARCHAR(255),
  dut_stable BOOLEAN,

  -- 本地测量
  local_trp_dbm FLOAT,
  local_tis_dbm FLOAT,
  local_eis_dbm FLOAT,
  local_measured_at TIMESTAMP,

  -- 参考测量
  reference_measurements JSONB,  -- [{lab_name, trp_dbm, tis_dbm, ...}, ...]

  -- 对比
  trp_bias_db JSONB,
  tis_bias_db JSONB,
  eis_bias_db JSONB,

  trp_mean_bias_db FLOAT,
  tis_mean_bias_db FLOAT,
  eis_mean_bias_db FLOAT,

  -- 验证
  validation_pass BOOLEAN,
  threshold_db FLOAT DEFAULT 1.0,
  notes TEXT,

  tested_at TIMESTAMP DEFAULT NOW(),
  tested_by VARCHAR(100),

  INDEX idx_round_robin_id (round_robin_id),
  INDEX idx_validation_pass (validation_pass)
);
```

## 8. 校准证书生成

### 8.1 证书内容

**必需信息**:
- 证书编号
- 校准日期
- 有效期（通常6-12个月）
- 校准实验室信息（名称、地址、认证）
- 被校准系统信息（型号、序列号、配置）
- 校准标准（3GPP TS 34.114, CTIA Ver. 4.0）
- 校准结果：
  - TRP误差: ±X dB
  - TIS误差: ±Y dB
  - 可重复性: σ = Z dB
  - 可比性: Bias = W dB
- 校准工程师签名
- 技术负责人审核签名
- 数字签名（防伪）

### 8.2 数据模型

```typescript
interface CalibrationCertificate {
  id: string
  certificate_number: string  // e.g., "MPAC-SYS-CAL-2025-001"

  // 系统信息
  system_info: {
    system_name: string  // "Meta-3D MPAC System"
    serial_number: string
    configuration: {
      num_probes: number
      chamber_size: string
      channel_emulator_model: string
      base_station_emulator_model: string
    }
  }

  // 实验室信息
  lab_info: {
    name: string
    address: string
    accreditation: string  // "ISO/IEC 17025:2017"
    accreditation_body: string  // e.g., "CNAS"
  }

  // 校准日期
  calibration_date: Date
  valid_until: Date  // calibration_date + 12 months

  // 校准标准
  standards: string[]  // ["3GPP TS 34.114", "CTIA OTA Ver. 4.0"]

  // 校准结果
  results: {
    trp_error_db: number
    trp_pass: boolean

    tis_error_db: number
    tis_pass: boolean

    repeatability_std_dev_db: number
    repeatability_pass: boolean

    comparability_bias_db: number
    comparability_pass: boolean
  }

  // 签名
  calibrated_by: string
  calibrated_by_signature: string  // Base64 encoded signature image

  reviewed_by: string
  reviewed_by_signature: string

  digital_signature: string  // SHA-256 hash for integrity

  // 附件
  attachments: Array<{
    type: 'raw_data' | 'analysis_report' | 'traceability_chain'
    file_path: string
  }>

  issued_at: Date
}
```

### 8.3 数据库模式

```sql
CREATE TABLE calibration_certificates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  certificate_number VARCHAR(100) UNIQUE NOT NULL,

  -- 系统信息
  system_name VARCHAR(255),
  system_serial_number VARCHAR(255),
  system_configuration JSONB,

  -- 实验室信息
  lab_name VARCHAR(255),
  lab_address TEXT,
  lab_accreditation VARCHAR(255),
  lab_accreditation_body VARCHAR(100),

  -- 日期
  calibration_date DATE NOT NULL,
  valid_until DATE NOT NULL,

  -- 标准
  standards JSONB,  -- ["3GPP TS 34.114", ...]

  -- 结果
  trp_error_db FLOAT,
  trp_pass BOOLEAN,
  tis_error_db FLOAT,
  tis_pass BOOLEAN,
  repeatability_std_dev_db FLOAT,
  repeatability_pass BOOLEAN,
  comparability_bias_db FLOAT,
  comparability_pass BOOLEAN,

  -- 签名
  calibrated_by VARCHAR(100),
  calibrated_by_signature TEXT,  -- Base64
  reviewed_by VARCHAR(100),
  reviewed_by_signature TEXT,
  digital_signature VARCHAR(64),  -- SHA-256 hash

  -- 附件
  attachments JSONB,

  issued_at TIMESTAMP DEFAULT NOW(),

  INDEX idx_certificate_number (certificate_number),
  INDEX idx_valid_until (valid_until)
);
```

## 9. API设计

### 9.1 校准执行API

```typescript
// POST /api/v1/system-calibration/execute
interface ExecuteSystemCalibrationRequest {
  calibration_suite: 'complete' | 'trp_only' | 'tis_only' | 'repeatability_only'

  standard_dut_id: string  // 从DUT库中选择

  configuration?: {
    fc_ghz: number
    bandwidth_mhz: number
    num_runs?: number  // for repeatability (default 10)
  }

  auto_generate_certificate: boolean
}

interface ExecuteSystemCalibrationResponse {
  calibration_job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  estimated_duration_hours: number
}

// GET /api/v1/system-calibration/status/{job_id}
interface SystemCalibrationJobStatus {
  job_id: string
  status: string
  progress_percent: number
  current_test: string

  results?: {
    trp_calibration_id?: string
    tis_calibration_id?: string
    repeatability_test_id?: string

    overall_pass: boolean
  }
}
```

### 9.2 证书API

```typescript
// POST /api/v1/calibration-certificates/generate
interface GenerateCertificateRequest {
  calibration_ids: {
    trp_calibration_id: string
    tis_calibration_id: string
    repeatability_test_id: string
    comparability_test_id?: string
  }

  certificate_info: {
    lab_name: string
    lab_accreditation: string
    calibrated_by: string
    reviewed_by: string
  }

  validity_months: number  // default 12
}

interface GenerateCertificateResponse {
  certificate_id: string
  certificate_number: string
  pdf_url: string  // URL to download PDF
  digital_signature: string
}

// GET /api/v1/calibration-certificates/{certificate_id}/pdf
// Returns PDF file

// POST /api/v1/calibration-certificates/{certificate_id}/verify
interface VerifyCertificateRequest {
  digital_signature: string
}

interface VerifyCertificateResponse {
  valid: boolean
  message: string
}
```

## 10. UI设计

### 10.1 系统校准仪表盘

```typescript
// SystemCalibrationDashboard.tsx

export function SystemCalibrationDashboard() {
  const { data: status } = useQuery('system-calibration-status',
    () => api.getSystemCalibrationStatus()
  )

  return (
    <Stack gap="lg">
      <Title order={2}>系统级校准</Title>

      {/* 当前证书状态 */}
      <Card withBorder>
        <Group justify="space-between">
          <Stack gap="xs">
            <Title order={4}>当前校准证书</Title>
            {status.current_certificate ? (
              <>
                <Text>证书编号: {status.current_certificate.certificate_number}</Text>
                <Text>校准日期: {formatDate(status.current_certificate.calibration_date)}</Text>
                <Text>有效期至: {formatDate(status.current_certificate.valid_until)}</Text>

                <Group>
                  <Badge color={status.current_certificate.trp_pass ? 'green' : 'red'}>
                    TRP: {status.current_certificate.trp_pass ? 'PASS' : 'FAIL'}
                  </Badge>
                  <Badge color={status.current_certificate.tis_pass ? 'green' : 'red'}>
                    TIS: {status.current_certificate.tis_pass ? 'PASS' : 'FAIL'}
                  </Badge>
                  <Badge color={status.current_certificate.repeatability_pass ? 'green' : 'red'}>
                    可重复性: {status.current_certificate.repeatability_pass ? 'PASS' : 'FAIL'}
                  </Badge>
                </Group>
              </>
            ) : (
              <Text c="red">无有效校准证书</Text>
            )}
          </Stack>

          <Group>
            <Button
              leftSection={<IconDownload />}
              variant="light"
              onClick={() => handleDownloadCertificate(status.current_certificate.id)}
            >
              下载证书
            </Button>
            <Button
              leftSection={<IconRefresh />}
              onClick={() => handleStartCalibration()}
            >
              重新校准
            </Button>
          </Group>
        </Group>
      </Card>

      {/* 校准历史 */}
      <Card withBorder>
        <Title order={4} mb="md">校准历史</Title>
        <Timeline active={0} bulletSize={24} lineWidth={2}>
          {status.calibration_history.map((cal, idx) => (
            <Timeline.Item
              key={cal.id}
              bullet={cal.overall_pass ? <IconCheck size={12} /> : <IconX size={12} />}
              title={`${formatDate(cal.calibration_date)} - ${cal.certificate_number}`}
            >
              <Text size="xs" mt={4}>
                TRP: {cal.trp_error_db.toFixed(2)} dB |
                TIS: {cal.tis_error_db.toFixed(2)} dB |
                σ: {cal.repeatability_std_dev_db.toFixed(2)} dB
              </Text>
              <Button
                size="xs"
                variant="subtle"
                mt="xs"
                onClick={() => handleViewDetails(cal.id)}
              >
                详情
              </Button>
            </Timeline.Item>
          ))}
        </Timeline>
      </Card>
    </Stack>
  )
}
```

### 10.2 校准执行向导

```typescript
// SystemCalibrationWizard.tsx

export function SystemCalibrationWizard() {
  const [currentStep, setCurrentStep] = useState(0)

  return (
    <Modal opened size="xl" title="系统校准向导">
      <Stepper active={currentStep}>
        <Stepper.Step label="选择校准套件">
          <Radio.Group label="校准类型">
            <Stack gap="sm">
              <Radio
                value="complete"
                label="完整校准（TRP + TIS + 可重复性 + 证书）"
                description="推荐：首次校准或年度校准"
              />
              <Radio
                value="trp_only"
                label="仅TRP校准"
                description="快速验证发射性能"
              />
              <Radio
                value="tis_only"
                label="仅TIS校准"
                description="快速验证接收性能"
              />
              <Radio
                value="repeatability_only"
                label="仅可重复性测试"
                description="验证系统稳定性"
              />
            </Stack>
          </Radio.Group>
        </Stepper.Step>

        <Stepper.Step label="选择标准DUT">
          <Select
            label="标准DUT"
            placeholder="从DUT库中选择"
            data={standardDUTs.map(dut => ({
              value: dut.id,
              label: `${dut.model} (SN: ${dut.serial}) - TRP: ${dut.reference_trp_dbm} dBm`
            }))}
          />

          <Alert icon={<IconInfoCircle />} mt="md" color="blue">
            <Text size="sm">
              请确保选择的标准DUT已在参考实验室校准，并带有有效的校准证书。
            </Text>
          </Alert>
        </Stepper.Step>

        <Stepper.Step label="配置参数">
          <Stack gap="sm">
            <NumberInput
              label="频率 (GHz)"
              value={3.5}
              step={0.1}
              min={0.5}
              max={100}
            />

            <NumberInput
              label="带宽 (MHz)"
              value={20}
              step={10}
            />

            <NumberInput
              label="重复测量次数"
              value={10}
              min={5}
              max={50}
              description="用于可重复性测试"
            />

            <Switch
              label="自动生成校准证书"
              defaultChecked
            />
          </Stack>
        </Stepper.Step>

        <Stepper.Step label="确认执行">
          <Stack gap="md">
            <Text size="sm">
              <strong>校准套件:</strong> 完整校准
            </Text>
            <Text size="sm">
              <strong>标准DUT:</strong> Standard Dipole Array (SN: 12345)
            </Text>
            <Text size="sm">
              <strong>预计时间:</strong> 约 4-6 小时
            </Text>

            <Alert icon={<IconAlertCircle />} color="yellow">
              <Text size="sm">
                系统校准期间，MPAC系统将无法执行其他测试任务。请确保有足够的时间窗口。
              </Text>
            </Alert>

            <Button
              size="lg"
              fullWidth
              leftSection={<IconPlayerPlay />}
              onClick={handleStartCalibration}
            >
              开始校准
            </Button>
          </Stack>
        </Stepper.Step>
      </Stepper>

      <Group justify="space-between" mt="xl">
        <Button variant="default" onClick={() => setCurrentStep(currentStep - 1)} disabled={currentStep === 0}>
          上一步
        </Button>
        <Button onClick={() => setCurrentStep(currentStep + 1)} disabled={currentStep === 3}>
          下一步
        </Button>
      </Group>
    </Modal>
  )
}
```

## 11. 实现计划

### Phase 1: TRP/TIS校准 (2周)

**Week 1: TRP校准**
- [ ] 标准DUT管理模块
- [ ] TRP测量自动化
- [ ] TRP计算算法
- [ ] 数据库和API

**Week 2: TIS校准**
- [ ] TIS测量自动化（含吞吐量测试）
- [ ] TIS计算算法
- [ ] 数据库和API

### Phase 2: 可重复性和可比性 (1周)

**Week 3: 验证测试**
- [ ] 可重复性测试自动化
- [ ] 可比性测试数据管理
- [ ] 统计分析模块

### Phase 3: 证书系统 (1周)

**Week 4: 证书生成**
- [ ] 证书数据模型
- [ ] PDF证书模板设计
- [ ] 数字签名实现
- [ ] 证书验证API

### Phase 4: UI和集成 (1周)

**Week 5: UI和测试**
- [ ] SystemCalibrationDashboard
- [ ] SystemCalibrationWizard
- [ ] 证书下载和验证UI
- [ ] 端到端测试

## 12. 总结

系统级校准是MPAC测试系统最终的质量保证，确保：

- **端到端准确性**: TRP误差 < ±0.5 dB, TIS误差 < ±1 dB
- **可重复性**: 标准差 < 0.5 dB
- **可比性**: 与参考实验室偏差 < 1 dB
- **可追溯性**: 校准证书链路完整，符合ISO/IEC 17025
- **合规性**: 满足3GPP/CTIA/FCC等标准要求

实现后，系统将具备认证实验室级别的测量能力，可用于正式的OTA认证测试。
