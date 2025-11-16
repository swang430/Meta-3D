# Hybrid Test Framework Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Virtual Test Subsystem (虚拟测试子系统)
- **优先级**: P1
- **状态**: Draft

## 1. 概述

### 1.1 目标

混合测试框架（Hybrid Test Framework）旨在无缝整合虚拟测试（基于ChannelEngine的3GPP信道仿真）与标准OTA测试（基于实际硬件的暗室测试），为用户提供灵活、高效、成本优化的测试解决方案。

### 1.2 核心价值

**成本优化**:
- 虚拟测试：零硬件成本，适合早期开发、参数扫描、快速迭代
- 标准测试：硬件成本高，适合最终验证、认证测试
- 混合测试：虚拟筛选 + 标准验证，降低总体测试成本

**时间优化**:
- 虚拟测试：秒级执行，适合大规模参数探索
- 标准测试：分钟级执行，适合关键场景验证
- 混合测试：并行执行虚拟和标准测试，缩短项目周期

**覆盖度优化**:
- 虚拟测试：覆盖3GPP标准全部场景（UMa/UMi/RMa/InH/CDL/TDL）
- 标准测试：覆盖实际暗室配置支持的场景
- 混合测试：虚拟测试广度 + 标准测试深度

### 1.3 适用场景

| 测试阶段 | 推荐模式 | 原因 |
|---------|---------|------|
| 天线设计初期 | 纯虚拟 | 快速迭代，零硬件成本 |
| 算法开发 | 纯虚拟 | 大规模参数扫描，秒级反馈 |
| 系统集成测试 | 混合模式 | 虚拟筛选 + 标准验证 |
| 预认证测试 | 混合模式 | 虚拟预测试 + 标准确认 |
| 正式认证测试 | 纯标准 | 监管要求，可追溯性 |
| 日常回归测试 | 混合模式 | 虚拟覆盖广度 + 标准抽检 |
| 生产线测试 | 纯标准 | 实际硬件验证 |

## 2. 架构设计

### 2.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Test Config  │  │ Test Monitor │  │ Result View  │           │
│  │  - 模式选择   │  │  - 实时状态   │  │  - 对比分析   │           │
│  │  - 参数设置   │  │  - 进度跟踪   │  │  - 报告生成   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Hybrid Test Orchestration Layer                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Test Mode Controller                         │   │
│  │  - 模式路由 (Virtual/Standard/Hybrid)                     │   │
│  │  - 参数映射 (Virtual ↔ Standard)                         │   │
│  │  - 结果聚合 (Merge results)                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Workflow Engine                              │   │
│  │  - 测试序列编排                                            │   │
│  │  - 依赖管理 (Virtual → Standard)                         │   │
│  │  - 并行执行控制                                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
           ▼                                    ▼
┌──────────────────────────┐      ┌──────────────────────────┐
│   Virtual Test Engine    │      │  Standard Test Engine    │
│  ┌────────────────────┐  │      │  ┌────────────────────┐  │
│  │ ChannelEngine API  │  │      │  │  Instrument HAL    │  │
│  │  - 3GPP TR 38.901  │  │      │  │  - Channel Emul.   │  │
│  │  - Probe weights   │  │      │  │  - Base Station    │  │
│  │  - Channel stats   │  │      │  │  - Signal Analyzer │  │
│  └────────────────────┘  │      │  └────────────────────┘  │
│  ┌────────────────────┐  │      │  ┌────────────────────┐  │
│  │  Fast Simulation   │  │      │  │  Hardware Control  │  │
│  │  - Seconds/test    │  │      │  │  - Minutes/test    │  │
│  │  - No HW cost      │  │      │  │  - Real chamber    │  │
│  └────────────────────┘  │      │  └────────────────────┘  │
└──────────────────────────┘      └──────────────────────────┘
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data Management Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Result Store │  │ Calibration  │  │ Test History │           │
│  │  - Virtual    │  │  - Shared    │  │  - Tracing   │           │
│  │  - Standard   │  │  - Versioned │  │  - Analytics │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 Test Mode Controller

测试模式控制器，负责根据用户配置路由到不同的测试引擎。

**职责**:
- 解析测试配置，确定测试模式（Pure Virtual / Pure Standard / Hybrid）
- 参数映射和转换（虚拟测试参数 ↔ 标准测试参数）
- 结果聚合和对比分析
- 校准数据共享

**接口设计**:
```typescript
interface TestModeController {
  // 确定测试模式
  determineTestMode(config: TestConfiguration): TestMode

  // 参数映射：虚拟 → 标准
  mapVirtualToStandard(
    virtualConfig: VirtualTestConfig
  ): StandardTestConfig

  // 参数映射：标准 → 虚拟
  mapStandardToVirtual(
    standardConfig: StandardTestConfig
  ): VirtualTestConfig

  // 结果聚合
  aggregateResults(
    virtualResult?: VirtualTestResult,
    standardResult?: StandardTestResult
  ): HybridTestResult

  // 相关性分析
  analyzeCorrelation(
    virtualResult: VirtualTestResult,
    standardResult: StandardTestResult
  ): CorrelationAnalysis
}
```

#### 2.2.2 Workflow Engine

工作流引擎，编排测试序列，管理依赖关系，控制并行执行。

**典型工作流**:

**工作流1: 虚拟筛选 → 标准验证**
```yaml
workflow:
  name: "Virtual Screening + Standard Validation"
  stages:
    - stage: "virtual_screening"
      type: "virtual"
      parallel: true
      scenarios:
        - UMa_LOS
        - UMa_NLOS
        - UMi_StreetCanyon
        - InH_OfficeOpen
      action: "generate_probe_weights"

    - stage: "filter_candidates"
      type: "analysis"
      criteria:
        - metric: "avg_probe_magnitude"
          threshold: "> 0.1"
        - metric: "num_active_probes"
          threshold: ">= 8"

    - stage: "standard_validation"
      type: "standard"
      parallel: false
      scenarios: "${filtered_scenarios}"
      action: "full_ota_test"

    - stage: "correlation_analysis"
      type: "analysis"
      action: "compare_virtual_vs_standard"
```

**工作流2: 并行对比测试**
```yaml
workflow:
  name: "Parallel Comparison"
  stages:
    - stage: "parallel_test"
      parallel_branches:
        - branch: "virtual"
          type: "virtual"
          scenarios: "${all_scenarios}"

        - branch: "standard"
          type: "standard"
          scenarios: "${sampled_scenarios}"

    - stage: "correlation_update"
      type: "analysis"
      action: "update_correlation_model"
```

**接口设计**:
```typescript
interface WorkflowEngine {
  // 加载工作流定义
  loadWorkflow(workflowId: string): Workflow

  // 执行工作流
  executeWorkflow(
    workflow: Workflow,
    context: ExecutionContext
  ): Promise<WorkflowResult>

  // 暂停/恢复/取消
  pauseWorkflow(workflowId: string): void
  resumeWorkflow(workflowId: string): void
  cancelWorkflow(workflowId: string): void

  // 监控
  getWorkflowStatus(workflowId: string): WorkflowStatus
}
```

#### 2.2.3 Virtual Test Engine

虚拟测试引擎，封装ChannelEngine集成。

**职责**:
- 调用ChannelEngine API生成探头权重
- 快速参数扫描（并行执行数百个配置）
- 统计分析和可视化

**性能指标**:
- 单次测试时间: < 5秒
- 并行能力: 10+ concurrent requests
- 场景覆盖: 3GPP TR 38.901 全部场景

#### 2.2.4 Standard Test Engine

标准测试引擎，控制实际硬件执行OTA测试。

**职责**:
- 调用仪器HAL控制硬件
- 执行暗室测试流程
- 数据采集和处理

**性能指标**:
- 单次测试时间: 5-30分钟（取决于测试复杂度）
- 精度: 符合3GPP/CTIA标准
- 可追溯性: 完整的校准链路

## 3. 测试模式

### 3.1 Pure Virtual Mode（纯虚拟模式）

**使用场景**:
- 天线设计初期
- 算法开发
- 大规模参数扫描
- 教学和培训

**配置示例**:
```typescript
const config: TestConfiguration = {
  mode: 'pure_virtual',
  virtual: {
    scenarios: [
      { type: 'UMa', condition: 'LOS', fc_ghz: 3.5 },
      { type: 'UMa', condition: 'NLOS', fc_ghz: 3.5 },
      { type: 'UMi_StreetCanyon', condition: 'LOS', fc_ghz: 28 }
    ],
    probe_array: {
      template: '32-probe-dual-ring',
      radius: 3.0
    },
    mimo_config: {
      tx_antennas: 4,
      rx_antennas: 2
    }
  }
}
```

**输出**:
- 探头权重 (幅度、相位)
- 信道统计 (路径损耗、RMS时延扩展、角度扩展)
- 可视化（探头功率分布、角度功率谱）

### 3.2 Pure Standard Mode（纯标准模式）

**使用场景**:
- 正式认证测试
- 生产线测试
- 监管审核

**配置示例**:
```typescript
const config: TestConfiguration = {
  mode: 'pure_standard',
  standard: {
    test_plan: 'CTIA_Ver4.0_Full',
    instruments: {
      channel_emulator: 'Keysight_PROPSIM_F64',
      base_station: 'Keysight_UXM_5G',
      signal_analyzer: 'Rohde_Schwarz_FSW'
    },
    dut: {
      type: 'vehicle',
      model: 'Tesla_Model3'
    },
    chamber: {
      size: '6m x 4m x 3m',
      probe_count: 32
    }
  }
}
```

**输出**:
- MIMO OTA测试报告（符合3GPP/CTIA标准）
- 吞吐量、误码率、RSRP/SINR等指标
- 校准证书和可追溯性记录

### 3.3 Hybrid Mode（混合模式）

#### 3.3.1 Sequential Hybrid（顺序混合）

**工作流**: 虚拟筛选 → 标准验证

**使用场景**:
- 系统集成测试
- 预认证测试

**配置示例**:
```typescript
const config: TestConfiguration = {
  mode: 'hybrid_sequential',

  // Step 1: 虚拟筛选
  virtual_screening: {
    scenarios: generateParameterSweep({
      scenario_types: ['UMa', 'UMi', 'InH'],
      frequencies: [3.5, 28, 39],
      conditions: ['LOS', 'NLOS']
    }),
    filter_criteria: {
      min_avg_magnitude: 0.1,
      min_active_probes: 8,
      max_pathloss_db: 120
    }
  },

  // Step 2: 标准验证
  standard_validation: {
    scenarios: '${filtered_scenarios}',  // 从虚拟筛选结果中选择
    test_depth: 'full',
    reuse_probe_weights: true  // 复用虚拟测试的探头权重作为初始值
  }
}
```

**优势**:
- 大幅减少标准测试次数（100+ scenarios → 10-20 scenarios）
- 虚拟测试提供初始探头权重，加速标准测试收敛
- 成本节省: ~60-80%

#### 3.3.2 Parallel Hybrid（并行混合）

**工作流**: 虚拟测试 ∥ 标准测试 → 相关性分析

**使用场景**:
- 建立虚拟-标准相关性模型
- 日常回归测试

**配置示例**:
```typescript
const config: TestConfiguration = {
  mode: 'hybrid_parallel',

  parallel_branches: [
    {
      name: 'virtual_full',
      type: 'virtual',
      scenarios: '${all_scenarios}'  // 全部场景
    },
    {
      name: 'standard_sample',
      type: 'standard',
      scenarios: sampleScenarios('${all_scenarios}', {
        strategy: 'stratified',  // 分层采样
        sample_rate: 0.1  // 10%采样率
      })
    }
  ],

  correlation_analysis: {
    metrics: ['avg_magnitude', 'pathloss_db', 'rms_delay_spread'],
    update_model: true  // 更新相关性模型
  }
}
```

**优势**:
- 持续改进虚拟-标准相关性
- 虚拟测试作为标准测试的"预言机"，提前发现异常
- 时间节省: 并行执行，无额外时间成本

## 4. 参数映射

### 4.1 虚拟 → 标准 映射

虚拟测试（ChannelEngine）的输出需要映射到标准测试的输入。

#### 4.1.1 探头权重映射

**虚拟测试输出**:
```typescript
interface VirtualProbeWeight {
  probe_id: number
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP'
  weight: {
    magnitude: number  // 线性幅度
    phase_deg: number  // 相位（度）
  }
  enabled: boolean
}
```

**标准测试输入** (Keysight PROPSIM):
```typescript
interface StandardProbeConfig {
  probe_id: number
  rf_path: number  // RF矩阵路径
  amplitude_db: number  // dB幅度
  phase_deg: number
  power_dbm: number  // 输出功率
  enable: boolean
}
```

**映射函数**:
```typescript
function mapProbeWeights(
  virtualWeights: VirtualProbeWeight[],
  referenceProbe: number = 0
): StandardProbeConfig[] {
  // 找到参考探头
  const refWeight = virtualWeights[referenceProbe]
  const refMagnitude = refWeight.weight.magnitude

  return virtualWeights.map((vw, idx) => ({
    probe_id: vw.probe_id,
    rf_path: vw.probe_id,  // 1:1映射

    // 相对幅度（dB）
    amplitude_db: 20 * Math.log10(vw.weight.magnitude / refMagnitude),

    // 相对相位
    phase_deg: vw.weight.phase_deg - refWeight.weight.phase_deg,

    // 功率（根据校准数据计算）
    power_dbm: calculateRequiredPower(vw, calibrationData),

    enable: vw.enabled
  }))
}
```

#### 4.1.2 场景参数映射

**虚拟场景**:
```typescript
interface VirtualScenario {
  type: 'UMa' | 'UMi' | 'InH' | 'RMa'
  condition: 'LOS' | 'NLOS'
  fc_ghz: number
  distance_2d: number
  bs_height: number
  ut_height: number
}
```

**标准场景** (信道仿真器配置):
```typescript
interface StandardChannelConfig {
  model: string  // '3GPP_38.901_UMa_LOS'
  carrier_frequency_hz: number
  tx_rx_distance_m: number
  tx_antenna_height_m: number
  rx_antenna_height_m: number
  doppler_spread_hz: number
  delay_spread_type: 'low' | 'medium' | 'high'
}
```

**映射函数**:
```typescript
function mapScenarioConfig(
  virtual: VirtualScenario
): StandardChannelConfig {
  return {
    model: `3GPP_38.901_${virtual.type}_${virtual.condition}`,
    carrier_frequency_hz: virtual.fc_ghz * 1e9,
    tx_rx_distance_m: virtual.distance_2d,
    tx_antenna_height_m: virtual.bs_height,
    rx_antenna_height_m: virtual.ut_height,
    doppler_spread_hz: calculateDopplerSpread(virtual),
    delay_spread_type: inferDelaySpreadType(virtual)
  }
}
```

### 4.2 标准 → 虚拟 映射

标准测试的配置也可以反向映射到虚拟测试，用于虚拟重现标准测试。

**逆向映射用途**:
- Debug标准测试异常（在虚拟环境中快速复现）
- 参数优化（虚拟环境中探索参数空间）
- 培训（虚拟环境中练习标准测试流程）

## 5. 数据模型

### 5.1 核心实体

#### 5.1.1 HybridTestConfiguration

```typescript
interface HybridTestConfiguration {
  id: string
  name: string
  description: string
  mode: TestMode

  // 虚拟测试配置
  virtual_config?: VirtualTestConfig

  // 标准测试配置
  standard_config?: StandardTestConfig

  // 混合模式配置
  hybrid_config?: {
    workflow_type: 'sequential' | 'parallel'
    virtual_to_standard_mapping: ParameterMapping
    correlation_analysis: CorrelationConfig
  }

  created_at: Date
  created_by: string
}

type TestMode =
  | 'pure_virtual'
  | 'pure_standard'
  | 'hybrid_sequential'
  | 'hybrid_parallel'
```

#### 5.1.2 HybridTestResult

```typescript
interface HybridTestResult {
  id: string
  configuration_id: string
  execution_id: string

  // 虚拟测试结果
  virtual_results?: VirtualTestResult[]

  // 标准测试结果
  standard_results?: StandardTestResult[]

  // 聚合结果
  aggregated_metrics: {
    total_scenarios: number
    virtual_only: number
    standard_only: number
    both: number
    correlation_coefficient?: number
  }

  // 相关性分析
  correlation_analysis?: {
    metric_correlations: Map<string, number>  // metric name → correlation
    prediction_error: Map<string, number>  // metric name → RMSE
    confidence_intervals: Map<string, [number, number]>
  }

  executed_at: Date
  duration_seconds: number
  status: 'success' | 'partial_success' | 'failed'
}
```

### 5.2 数据库模式

```sql
-- 混合测试配置表
CREATE TABLE hybrid_test_configurations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  description TEXT,
  mode VARCHAR(50) NOT NULL,  -- pure_virtual, pure_standard, hybrid_*

  virtual_config JSONB,  -- VirtualTestConfig
  standard_config JSONB,  -- StandardTestConfig
  hybrid_config JSONB,  -- HybridConfig

  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  created_by VARCHAR(100),

  -- 索引
  INDEX idx_mode (mode),
  INDEX idx_created_at (created_at)
);

-- 混合测试结果表
CREATE TABLE hybrid_test_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  configuration_id UUID REFERENCES hybrid_test_configurations(id),
  execution_id UUID NOT NULL,

  virtual_results JSONB,
  standard_results JSONB,
  aggregated_metrics JSONB,
  correlation_analysis JSONB,

  executed_at TIMESTAMP DEFAULT NOW(),
  duration_seconds INTEGER,
  status VARCHAR(50),

  -- 索引
  INDEX idx_config_id (configuration_id),
  INDEX idx_execution_id (execution_id),
  INDEX idx_executed_at (executed_at)
);

-- 相关性模型表（存储虚拟-标准相关性）
CREATE TABLE correlation_models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  metric_name VARCHAR(100) NOT NULL,
  scenario_type VARCHAR(50),  -- UMa, UMi, etc.

  -- 线性回归模型: standard = a * virtual + b
  coefficient_a FLOAT NOT NULL,
  coefficient_b FLOAT NOT NULL,
  r_squared FLOAT NOT NULL,
  rmse FLOAT NOT NULL,

  -- 训练数据统计
  sample_count INTEGER NOT NULL,
  last_updated TIMESTAMP DEFAULT NOW(),

  -- 唯一约束
  UNIQUE(metric_name, scenario_type)
);
```

## 6. API设计

### 6.1 REST API

#### 6.1.1 创建混合测试配置

```
POST /api/v1/hybrid-tests/configurations

Request Body:
{
  "name": "Virtual Screening + Standard Validation",
  "description": "Hybrid workflow for antenna testing",
  "mode": "hybrid_sequential",
  "virtual_config": { ... },
  "standard_config": { ... },
  "hybrid_config": {
    "workflow_type": "sequential",
    "filter_criteria": { ... }
  }
}

Response: 201 Created
{
  "id": "uuid",
  "name": "...",
  ...
}
```

#### 6.1.2 执行混合测试

```
POST /api/v1/hybrid-tests/execute

Request Body:
{
  "configuration_id": "uuid",
  "execution_context": {
    "priority": "high",
    "async": true
  }
}

Response: 202 Accepted
{
  "execution_id": "uuid",
  "status": "queued",
  "estimated_duration_seconds": 1800
}
```

#### 6.1.3 获取测试结果

```
GET /api/v1/hybrid-tests/results/{execution_id}

Response: 200 OK
{
  "id": "uuid",
  "configuration_id": "uuid",
  "virtual_results": [ ... ],
  "standard_results": [ ... ],
  "aggregated_metrics": { ... },
  "correlation_analysis": { ... },
  "status": "success"
}
```

#### 6.1.4 查询相关性模型

```
GET /api/v1/hybrid-tests/correlation-models
  ?metric=avg_magnitude
  &scenario_type=UMa

Response: 200 OK
{
  "metric_name": "avg_magnitude",
  "scenario_type": "UMa",
  "model": {
    "type": "linear_regression",
    "equation": "standard = 0.95 * virtual + 0.02",
    "r_squared": 0.89,
    "rmse": 0.015
  },
  "sample_count": 150,
  "last_updated": "2025-11-15T10:30:00Z"
}
```

## 7. UI设计

### 7.1 测试模式选择器

```typescript
// HybridTestModeSelector.tsx

interface TestModeOption {
  mode: TestMode
  label: string
  description: string
  icon: React.ReactNode
  pros: string[]
  cons: string[]
}

const TEST_MODE_OPTIONS: TestModeOption[] = [
  {
    mode: 'pure_virtual',
    label: '纯虚拟测试',
    description: '使用ChannelEngine仿真，无需硬件',
    icon: <IconCpu />,
    pros: [
      '秒级执行速度',
      '零硬件成本',
      '支持大规模参数扫描',
      '覆盖全部3GPP场景'
    ],
    cons: [
      '无法替代认证测试',
      '不包含实际硬件效应'
    ]
  },
  {
    mode: 'pure_standard',
    label: '纯标准测试',
    description: '使用实际暗室和仪器',
    icon: <IconTestPipe />,
    pros: [
      '符合认证要求',
      '真实硬件验证',
      '可追溯性完整'
    ],
    cons: [
      '测试时间长（分钟级）',
      '硬件成本高',
      '场景覆盖受限于暗室配置'
    ]
  },
  {
    mode: 'hybrid_sequential',
    label: '混合测试（顺序）',
    description: '虚拟筛选 → 标准验证',
    icon: <IconArrowsSplit />,
    pros: [
      '成本优化（60-80%节省）',
      '虚拟测试加速标准测试',
      '保持认证有效性'
    ],
    cons: [
      '需要两阶段执行',
      '总时间长于纯虚拟'
    ]
  },
  {
    mode: 'hybrid_parallel',
    label: '混合测试（并行）',
    description: '虚拟测试 ∥ 标准测试',
    icon: <IconGitBranch />,
    pros: [
      '建立相关性模型',
      '无额外时间成本',
      '持续改进虚拟测试准确度'
    ],
    cons: [
      '需要并行资源',
      '相关性模型需持续维护'
    ]
  }
]

export function HybridTestModeSelector({
  value,
  onChange
}: {
  value: TestMode
  onChange: (mode: TestMode) => void
}) {
  return (
    <Stack gap="md">
      <Title order={4}>选择测试模式</Title>
      <Radio.Group value={value} onChange={onChange}>
        <Stack gap="lg">
          {TEST_MODE_OPTIONS.map(option => (
            <Card
              key={option.mode}
              withBorder
              shadow="sm"
              style={{
                cursor: 'pointer',
                borderColor: value === option.mode ? 'var(--mantine-color-blue-6)' : undefined,
                borderWidth: value === option.mode ? 2 : 1
              }}
              onClick={() => onChange(option.mode)}
            >
              <Group align="flex-start">
                <Radio value={option.mode} />
                <Stack gap="xs" style={{ flex: 1 }}>
                  <Group>
                    {option.icon}
                    <Text fw={600}>{option.label}</Text>
                  </Group>
                  <Text size="sm" c="dimmed">{option.description}</Text>

                  <Group gap="xl">
                    <div>
                      <Text size="xs" fw={500} c="green">优势:</Text>
                      <List size="xs" spacing={2}>
                        {option.pros.map((pro, i) => (
                          <List.Item key={i}>{pro}</List.Item>
                        ))}
                      </List>
                    </div>

                    <div>
                      <Text size="xs" fw={500} c="orange">限制:</Text>
                      <List size="xs" spacing={2}>
                        {option.cons.map((con, i) => (
                          <List.Item key={i}>{con}</List.Item>
                        ))}
                      </List>
                    </div>
                  </Group>
                </Stack>
              </Group>
            </Card>
          ))}
        </Stack>
      </Radio.Group>
    </Stack>
  )
}
```

### 7.2 混合工作流配置器

```typescript
// HybridWorkflowConfigurator.tsx

export function HybridWorkflowConfigurator({
  mode,
  value,
  onChange
}: {
  mode: TestMode
  value: HybridConfig
  onChange: (config: HybridConfig) => void
}) {
  if (mode === 'hybrid_sequential') {
    return (
      <Stack gap="md">
        <Title order={5}>顺序混合工作流配置</Title>

        {/* Step 1: 虚拟筛选 */}
        <Card withBorder>
          <Stack gap="sm">
            <Group>
              <Badge>步骤1</Badge>
              <Text fw={500}>虚拟筛选</Text>
            </Group>

            <NumberInput
              label="场景总数"
              description="虚拟测试将扫描的场景总数"
              value={value.virtual_scenario_count}
              onChange={(val) => onChange({
                ...value,
                virtual_scenario_count: Number(val)
              })}
              min={1}
              max={1000}
            />

            <Title order={6}>筛选条件</Title>
            <Group>
              <NumberInput
                label="最小平均幅度"
                value={value.filter_criteria.min_avg_magnitude}
                onChange={(val) => onChange({
                  ...value,
                  filter_criteria: {
                    ...value.filter_criteria,
                    min_avg_magnitude: Number(val)
                  }
                })}
                min={0}
                max={1}
                step={0.01}
                decimalScale={3}
              />

              <NumberInput
                label="最小激活探头数"
                value={value.filter_criteria.min_active_probes}
                onChange={(val) => onChange({
                  ...value,
                  filter_criteria: {
                    ...value.filter_criteria,
                    min_active_probes: Number(val)
                  }
                })}
                min={1}
                max={64}
              />
            </Group>
          </Stack>
        </Card>

        {/* Step 2: 标准验证 */}
        <Card withBorder>
          <Stack gap="sm">
            <Group>
              <Badge>步骤2</Badge>
              <Text fw={500}>标准验证</Text>
            </Group>

            <Switch
              label="复用虚拟测试的探头权重"
              description="将虚拟测试的探头权重作为标准测试的初始值"
              checked={value.reuse_probe_weights}
              onChange={(e) => onChange({
                ...value,
                reuse_probe_weights: e.currentTarget.checked
              })}
            />

            <Select
              label="验证深度"
              data={[
                { value: 'quick', label: '快速验证（仅关键指标）' },
                { value: 'standard', label: '标准验证（常规指标）' },
                { value: 'full', label: '完整验证（全部指标）' }
              ]}
              value={value.validation_depth}
              onChange={(val) => onChange({
                ...value,
                validation_depth: val as 'quick' | 'standard' | 'full'
              })}
            />
          </Stack>
        </Card>

        {/* 预估 */}
        <Alert icon={<IconInfoCircle />} title="成本预估" color="blue">
          <Stack gap="xs">
            <Text size="sm">
              虚拟筛选: {value.virtual_scenario_count} 场景 × 5秒 ≈ {Math.ceil(value.virtual_scenario_count * 5 / 60)} 分钟
            </Text>
            <Text size="sm">
              预估筛选后场景数: ~{Math.ceil(value.virtual_scenario_count * 0.15)}
            </Text>
            <Text size="sm">
              标准验证: ~{Math.ceil(value.virtual_scenario_count * 0.15)} 场景 × {
                value.validation_depth === 'quick' ? '5' :
                value.validation_depth === 'standard' ? '15' : '30'
              } 分钟 ≈ {Math.ceil(value.virtual_scenario_count * 0.15 * (
                value.validation_depth === 'quick' ? 5 :
                value.validation_depth === 'standard' ? 15 : 30
              ) / 60)} 小时
            </Text>
            <Divider />
            <Text size="sm" fw={600}>
              总耗时预估: ~{
                Math.ceil(value.virtual_scenario_count * 5 / 60) / 60 +
                Math.ceil(value.virtual_scenario_count * 0.15 * (
                  value.validation_depth === 'quick' ? 5 :
                  value.validation_depth === 'standard' ? 15 : 30
                ) / 60)
              } 小时
            </Text>
            <Text size="sm" c="green" fw={600}>
              vs. 纯标准测试: ~{
                Math.ceil(value.virtual_scenario_count * (
                  value.validation_depth === 'quick' ? 5 :
                  value.validation_depth === 'standard' ? 15 : 30
                ) / 60)
              } 小时 (节省 {
                Math.round((1 - (
                  (Math.ceil(value.virtual_scenario_count * 5 / 60) / 60 +
                  Math.ceil(value.virtual_scenario_count * 0.15 * (
                    value.validation_depth === 'quick' ? 5 :
                    value.validation_depth === 'standard' : 15 : 30
                  ) / 60)) /
                  (Math.ceil(value.virtual_scenario_count * (
                    value.validation_depth === 'quick' ? 5 :
                    value.validation_depth === 'standard' ? 15 : 30
                  ) / 60))
                )) * 100)
              }%)
            </Text>
          </Stack>
        </Alert>
      </Stack>
    )
  }

  if (mode === 'hybrid_parallel') {
    return (
      <Stack gap="md">
        <Title order={5}>并行混合工作流配置</Title>

        <Card withBorder>
          <Stack gap="sm">
            <Text fw={500}>虚拟测试分支</Text>
            <Text size="sm" c="dimmed">将执行全部场景的虚拟测试</Text>
            <NumberInput
              label="场景总数"
              value={value.virtual_scenario_count}
              onChange={(val) => onChange({
                ...value,
                virtual_scenario_count: Number(val)
              })}
            />
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="sm">
            <Text fw={500}>标准测试分支</Text>
            <Text size="sm" c="dimmed">将对场景进行采样并执行标准测试</Text>

            <Select
              label="采样策略"
              data={[
                { value: 'random', label: '随机采样' },
                { value: 'stratified', label: '分层采样（按场景类型）' },
                { value: 'representative', label: '代表性采样（覆盖参数空间）' }
              ]}
              value={value.sampling_strategy}
              onChange={(val) => onChange({
                ...value,
                sampling_strategy: val as any
              })}
            />

            <NumberInput
              label="采样率 (%)"
              value={value.sampling_rate * 100}
              onChange={(val) => onChange({
                ...value,
                sampling_rate: Number(val) / 100
              })}
              min={1}
              max={50}
              suffix="%"
            />

            <Text size="sm">
              预估标准测试场景数: {Math.ceil(value.virtual_scenario_count * value.sampling_rate)}
            </Text>
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="sm">
            <Text fw={500}>相关性分析</Text>

            <Switch
              label="自动更新相关性模型"
              description="使用本次测试结果更新虚拟-标准相关性模型"
              checked={value.update_correlation_model}
              onChange={(e) => onChange({
                ...value,
                update_correlation_model: e.currentTarget.checked
              })}
            />

            <MultiSelect
              label="分析指标"
              data={[
                { value: 'avg_magnitude', label: '平均幅度' },
                { value: 'pathloss_db', label: '路径损耗' },
                { value: 'rms_delay_spread', label: 'RMS时延扩展' },
                { value: 'angular_spread', label: '角度扩展' },
                { value: 'num_active_probes', label: '激活探头数' }
              ]}
              value={value.correlation_metrics}
              onChange={(val) => onChange({
                ...value,
                correlation_metrics: val
              })}
            />
          </Stack>
        </Card>
      </Stack>
    )
  }

  return null
}
```

### 7.3 结果对比视图

```typescript
// HybridResultComparison.tsx

export function HybridResultComparison({
  result
}: {
  result: HybridTestResult
}) {
  const virtualData = result.virtual_results || []
  const standardData = result.standard_results || []

  // 找到两者都有的场景
  const commonScenarios = virtualData.filter(vr =>
    standardData.some(sr => sr.scenario_id === vr.scenario_id)
  )

  return (
    <Stack gap="md">
      <Title order={4}>混合测试结果对比</Title>

      {/* 聚合统计 */}
      <Group grow>
        <Card withBorder>
          <Stack gap="xs">
            <Text size="sm" c="dimmed">虚拟测试场景数</Text>
            <Text size="xl" fw={700}>{result.aggregated_metrics.virtual_only}</Text>
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="xs">
            <Text size="sm" c="dimmed">标准测试场景数</Text>
            <Text size="xl" fw={700}>{result.aggregated_metrics.standard_only}</Text>
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="xs">
            <Text size="sm" c="dimmed">对比场景数</Text>
            <Text size="xl" fw={700}>{result.aggregated_metrics.both}</Text>
          </Stack>
        </Card>

        {result.aggregated_metrics.correlation_coefficient !== undefined && (
          <Card withBorder>
            <Stack gap="xs">
              <Text size="sm" c="dimmed">相关系数</Text>
              <Text size="xl" fw={700}>
                {result.aggregated_metrics.correlation_coefficient.toFixed(3)}
              </Text>
              <Badge
                color={
                  result.aggregated_metrics.correlation_coefficient > 0.9 ? 'green' :
                  result.aggregated_metrics.correlation_coefficient > 0.7 ? 'yellow' : 'red'
                }
              >
                {
                  result.aggregated_metrics.correlation_coefficient > 0.9 ? '优秀' :
                  result.aggregated_metrics.correlation_coefficient > 0.7 ? '良好' : '需改进'
                }
              </Badge>
            </Stack>
          </Card>
        )}
      </Group>

      {/* 散点图对比 */}
      {commonScenarios.length > 0 && (
        <Card withBorder>
          <Title order={5} mb="md">虚拟 vs. 标准 - 平均幅度对比</Title>
          <ScatterPlot
            data={commonScenarios.map(vr => {
              const sr = standardData.find(s => s.scenario_id === vr.scenario_id)!
              return {
                x: vr.avg_magnitude,
                y: sr.avg_magnitude,
                label: vr.scenario_name
              }
            })}
            xLabel="虚拟测试"
            yLabel="标准测试"
            showRegressionLine
          />
        </Card>
      )}

      {/* 详细对比表格 */}
      <Card withBorder>
        <Title order={5} mb="md">场景详细对比</Title>
        <Table striped highlightOnHover withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>场景</Table.Th>
              <Table.Th>虚拟: 平均幅度</Table.Th>
              <Table.Th>标准: 平均幅度</Table.Th>
              <Table.Th>误差 (%)</Table.Th>
              <Table.Th>虚拟: 路径损耗</Table.Th>
              <Table.Th>标准: 路径损耗</Table.Th>
              <Table.Th>误差 (dB)</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {commonScenarios.map(vr => {
              const sr = standardData.find(s => s.scenario_id === vr.scenario_id)!
              const magError = Math.abs(vr.avg_magnitude - sr.avg_magnitude) / sr.avg_magnitude * 100
              const plError = Math.abs(vr.pathloss_db - sr.pathloss_db)

              return (
                <Table.Tr key={vr.scenario_id}>
                  <Table.Td>{vr.scenario_name}</Table.Td>
                  <Table.Td>{vr.avg_magnitude.toFixed(4)}</Table.Td>
                  <Table.Td>{sr.avg_magnitude.toFixed(4)}</Table.Td>
                  <Table.Td>
                    <Badge color={magError < 5 ? 'green' : magError < 10 ? 'yellow' : 'red'}>
                      {magError.toFixed(1)}%
                    </Badge>
                  </Table.Td>
                  <Table.Td>{vr.pathloss_db.toFixed(2)} dB</Table.Td>
                  <Table.Td>{sr.pathloss_db.toFixed(2)} dB</Table.Td>
                  <Table.Td>
                    <Badge color={plError < 1 ? 'green' : plError < 3 ? 'yellow' : 'red'}>
                      {plError.toFixed(2)} dB
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Card>

      {/* 相关性分析 */}
      {result.correlation_analysis && (
        <Card withBorder>
          <Title order={5} mb="md">相关性分析</Title>
          <Stack gap="sm">
            {Array.from(result.correlation_analysis.metric_correlations.entries()).map(([metric, corr]) => (
              <Group key={metric} justify="space-between">
                <Text size="sm">{metric}</Text>
                <Group>
                  <Progress
                    value={corr * 100}
                    size="lg"
                    style={{ width: 200 }}
                    color={corr > 0.9 ? 'green' : corr > 0.7 ? 'yellow' : 'red'}
                  />
                  <Text size="sm" fw={600} style={{ width: 60 }}>
                    {corr.toFixed(3)}
                  </Text>
                  <Badge
                    color={corr > 0.9 ? 'green' : corr > 0.7 ? 'yellow' : 'red'}
                    size="sm"
                  >
                    RMSE: {result.correlation_analysis.prediction_error.get(metric)?.toFixed(4)}
                  </Badge>
                </Group>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
    </Stack>
  )
}
```

## 8. 实现计划

### Phase 1: 核心框架 (2周)

**Week 1: 后端基础架构**
- [ ] Test Mode Controller实现
  - [ ] 模式路由逻辑
  - [ ] 参数映射函数（Virtual ↔ Standard）
  - [ ] 结果聚合
- [ ] Workflow Engine基础
  - [ ] 工作流定义解析
  - [ ] 顺序执行引擎
  - [ ] 状态管理
- [ ] 数据库模式创建
  - [ ] hybrid_test_configurations表
  - [ ] hybrid_test_results表
  - [ ] correlation_models表

**Week 2: API + UI基础**
- [ ] REST API实现
  - [ ] POST /configurations
  - [ ] POST /execute
  - [ ] GET /results/:id
- [ ] UI组件
  - [ ] HybridTestModeSelector
  - [ ] 基础配置表单
  - [ ] 结果显示

### Phase 2: 顺序混合模式 (2周)

**Week 3: 虚拟筛选 → 标准验证**
- [ ] Sequential workflow实现
  - [ ] 虚拟测试批量执行
  - [ ] 筛选逻辑（filter criteria）
  - [ ] 标准测试自动触发
- [ ] 探头权重复用
  - [ ] Virtual → Standard权重映射
  - [ ] 校准数据集成
- [ ] HybridWorkflowConfigurator (sequential mode)

**Week 4: 测试与优化**
- [ ] 端到端测试
- [ ] 性能优化（并行虚拟测试）
- [ ] 成本预估算法验证

### Phase 3: 并行混合模式 (2周)

**Week 5: 并行执行框架**
- [ ] Parallel workflow实现
  - [ ] 虚拟和标准测试并行调度
  - [ ] 采样策略（random, stratified, representative）
  - [ ] 结果同步
- [ ] 相关性分析
  - [ ] 线性回归模型
  - [ ] RMSE, R²计算
  - [ ] 模型持久化

**Week 6: 相关性模型管理**
- [ ] Correlation model CRUD
  - [ ] 模型训练
  - [ ] 模型更新
  - [ ] 模型版本管理
- [ ] HybridWorkflowConfigurator (parallel mode)
- [ ] HybridResultComparison组件

### Phase 4: 高级功能 (1周)

**Week 7: 生产就绪**
- [ ] 错误处理和恢复
  - [ ] Workflow中断恢复
  - [ ] 部分失败处理
- [ ] 监控和日志
  - [ ] 执行时间跟踪
  - [ ] 资源使用监控
- [ ] 文档和示例
  - [ ] 用户指南
  - [ ] API文档
  - [ ] Workflow示例库

## 9. 测试策略

### 9.1 单元测试

```typescript
// test/services/TestModeController.test.ts

describe('TestModeController', () => {
  describe('mapProbeWeights', () => {
    it('should convert virtual weights to standard config', () => {
      const virtualWeights: VirtualProbeWeight[] = [
        {
          probe_id: 0,
          polarization: 'V',
          weight: { magnitude: 1.0, phase_deg: 0 },
          enabled: true
        },
        {
          probe_id: 1,
          polarization: 'V',
          weight: { magnitude: 0.5, phase_deg: 45 },
          enabled: true
        }
      ]

      const standardConfig = mapProbeWeights(virtualWeights)

      expect(standardConfig[0].amplitude_db).toBeCloseTo(0, 2)
      expect(standardConfig[1].amplitude_db).toBeCloseTo(-6.02, 2)
      expect(standardConfig[1].phase_deg).toBeCloseTo(45, 2)
    })
  })

  describe('aggregateResults', () => {
    it('should merge virtual and standard results', () => {
      const virtualResult = {
        scenario_id: 'UMa_LOS_1',
        avg_magnitude: 0.25,
        pathloss_db: 85.5
      }

      const standardResult = {
        scenario_id: 'UMa_LOS_1',
        avg_magnitude: 0.24,
        pathloss_db: 86.2
      }

      const aggregated = aggregateResults(virtualResult, standardResult)

      expect(aggregated.both_tested).toBe(true)
      expect(aggregated.correlation).toBeDefined()
    })
  })
})
```

### 9.2 集成测试

```typescript
// test/integration/HybridWorkflow.test.ts

describe('Hybrid Workflow Integration', () => {
  it('should execute sequential hybrid workflow', async () => {
    // 创建配置
    const config: HybridTestConfiguration = {
      mode: 'hybrid_sequential',
      virtual_config: {
        scenarios: generateTestScenarios(100),
        probe_array: { template: '32-probe-dual-ring' }
      },
      hybrid_config: {
        workflow_type: 'sequential',
        filter_criteria: {
          min_avg_magnitude: 0.1,
          min_active_probes: 8
        }
      }
    }

    // 执行工作流
    const result = await hybridTestService.execute(config)

    // 验证
    expect(result.virtual_results).toHaveLength(100)
    expect(result.standard_results.length).toBeLessThan(20)  // ~15% 筛选率
    expect(result.status).toBe('success')
  })

  it('should execute parallel hybrid workflow with correlation', async () => {
    const config: HybridTestConfiguration = {
      mode: 'hybrid_parallel',
      virtual_config: {
        scenarios: generateTestScenarios(50)
      },
      standard_config: {
        sampling_rate: 0.2
      },
      hybrid_config: {
        workflow_type: 'parallel',
        correlation_analysis: { enabled: true }
      }
    }

    const result = await hybridTestService.execute(config)

    expect(result.virtual_results).toHaveLength(50)
    expect(result.standard_results).toHaveLength(10)  // 20% 采样
    expect(result.correlation_analysis).toBeDefined()
    expect(result.correlation_analysis.metric_correlations.size).toBeGreaterThan(0)
  })
})
```

### 9.3 E2E测试

```typescript
// test/e2e/HybridTest.e2e.test.ts

describe('Hybrid Test E2E', () => {
  it('should complete full hybrid test from UI to results', async () => {
    // 1. 用户选择混合模式
    await page.click('[data-testid="hybrid-sequential-mode"]')

    // 2. 配置虚拟筛选
    await page.fill('[data-testid="virtual-scenario-count"]', '50')
    await page.fill('[data-testid="filter-min-magnitude"]', '0.1')

    // 3. 配置标准验证
    await page.check('[data-testid="reuse-probe-weights"]')
    await page.selectOption('[data-testid="validation-depth"]', 'standard')

    // 4. 启动测试
    await page.click('[data-testid="start-test"]')

    // 5. 等待完成
    await page.waitForSelector('[data-testid="test-complete"]', { timeout: 300000 })

    // 6. 验证结果
    const virtualCount = await page.textContent('[data-testid="virtual-result-count"]')
    const standardCount = await page.textContent('[data-testid="standard-result-count"]')

    expect(Number(virtualCount)).toBe(50)
    expect(Number(standardCount)).toBeLessThanOrEqual(10)

    // 7. 检查对比视图
    await page.click('[data-testid="comparison-view"]')
    const correlation = await page.textContent('[data-testid="correlation-coefficient"]')
    expect(Number(correlation)).toBeGreaterThan(0.7)
  })
})
```

## 10. 未来扩展

### 10.1 自适应采样

基于相关性模型自动调整标准测试采样率：
- 相关性高（R² > 0.9）→ 降低采样率（节省成本）
- 相关性低（R² < 0.7）→ 提高采样率（保证准确性）

### 10.2 预测式测试

使用训练好的相关性模型直接预测标准测试结果：
- 仅虚拟测试 → 预测标准结果
- 置信区间和不确定性量化
- 仅在预测不确定性高时触发标准测试

### 10.3 机器学习增强

- 使用神经网络替代线性回归
- 多任务学习（同时预测多个指标）
- 迁移学习（不同暗室配置间的知识迁移）

### 10.4 成本优化自动化

- 自动生成最优混合测试策略
- 多目标优化（成本 vs. 覆盖度 vs. 准确性）
- 预算约束下的测试计划生成

## 11. 总结

混合测试框架是Meta-3D系统的核心竞争力之一，通过智能整合虚拟测试和标准测试，实现：

**成本优化**: 60-80%成本节省
**时间优化**: 并行执行，缩短项目周期
**覆盖度优化**: 虚拟测试广度 + 标准测试深度
**持续改进**: 相关性模型不断学习，虚拟测试准确度持续提升

该框架为用户提供灵活的测试策略选择，从早期开发的纯虚拟测试，到系统集成的混合测试，再到正式认证的纯标准测试，全生命周期支持汽车无线通信测试需求。
