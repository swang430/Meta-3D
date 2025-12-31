# 虚拟路测架构设计 v2.0

## 文档信息
- **版本**: 2.0
- **日期**: 2025-12-29
- **状态**: 设计草案

---

## 1. 架构概述

### 1.1 核心设计原则

```
┌─────────────────────────────────────────────────────────────────┐
│                    虚拟路测三层架构                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Layer 1: Network (核心网络)                              │   │
│   │  - 不涉及无线接入                                          │   │
│   │  - IP/路由/核心网配置                                      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              ↕                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Layer 2: Base Station (基站控制)                         │   │
│   │  - 覆盖范围内的发射/接收控制                                │   │
│   │  - 基站-终端之间的无线接口                                  │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              ↕                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Layer 3: Environment (数字孪生环境)                       │   │
│   │  - 射线跟踪信道                                            │   │
│   │  - 干扰源/噪声/移动散射体                                   │   │
│   │  - 天线配置（影响信道计算）                                  │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 层次职责边界

| 层次 | 职责 | 不包含 |
|------|------|--------|
| **Network** | 核心网、传输网、IP路由、QoS策略 | 无线频段、天线配置 |
| **Base Station** | gNB/eNB配置、调度、发射功率、MIMO模式 | 信道传播模型 |
| **Environment** | 传播环境、信道模型、干扰、天线影响 | 网络拓扑、核心网配置 |

---

## 2. Layer 1: Network (核心网络)

### 2.1 设计定位

Network层负责**不涉及无线接入**的网络配置，即从核心网到基站回传的所有非RF部分。

### 2.2 数据模型

```typescript
interface NetworkConfiguration {
  // === 核心网配置 ===
  coreNetwork: {
    type: '5GC' | 'EPC' | 'Hybrid'

    // 5G核心网组件 (可选，用于高级仿真)
    amf?: { endpoint: string }  // Access and Mobility Management Function
    smf?: { endpoint: string }  // Session Management Function
    upf?: { endpoint: string }  // User Plane Function

    // LTE核心网组件 (可选)
    mme?: { endpoint: string }  // Mobility Management Entity
    sgw?: { endpoint: string }  // Serving Gateway
    pgw?: { endpoint: string }  // PDN Gateway
  }

  // === 传输网配置 ===
  transport: {
    backhaul_type: 'fiber' | 'microwave' | 'satellite'
    bandwidth_gbps: number
    latency_ms: number
    jitter_ms?: number
  }

  // === IP/路由配置 ===
  ipConfig: {
    ue_ip_pool: string          // e.g., "10.0.0.0/24"
    dns_servers: string[]
    default_gateway?: string
  }

  // === QoS配置 ===
  qos: {
    default_qfi?: number        // QoS Flow Identifier
    profiles: QoSProfile[]
  }

  // === 流量模型 ===
  traffic?: {
    type: 'FTP' | 'HTTP' | 'VIDEO' | 'VOIP' | 'MIXED'
    direction: 'DL' | 'UL' | 'BIDIRECTIONAL'
    bandwidth_mbps?: number
  }
}

interface QoSProfile {
  name: string
  qfi: number
  priority: number
  guaranteed_bitrate_kbps?: number
  max_bitrate_kbps?: number
  latency_budget_ms?: number
}
```

### 2.3 与测试模式的关系

| 测试模式 | Network层处理方式 |
|---------|------------------|
| 数字孪生 | 完全软件仿真 |
| 传导测试 | 连接真实仪表 |
| OTA测试 | 连接真实仪表 |

---

## 3. Layer 2: Base Station (基站控制)

### 3.1 设计定位

Base Station层负责**覆盖范围内的发射和接收控制**，包括基站与终端之间的无线接口配置。

**注意**: 信道传播模型不在此层，而是在Environment层定义。Base Station层只负责"发射什么信号"和"如何接收"。

### 3.2 数据模型

```typescript
interface BaseStationConfiguration {
  // === 基站列表 ===
  stations: BaseStation[]

  // === 全局无线参数 ===
  radioConfig: {
    technology: 'NR' | 'LTE' | 'NR-LTE-DSS'
    band: string                // e.g., "n78", "B42"
    frequency_mhz: number       // 中心频率
    bandwidth_mhz: number       // 系统带宽
    duplex_mode: 'TDD' | 'FDD'
    scs_khz?: number            // Subcarrier Spacing (NR)
  }

  // === MIMO配置 (影响信道，但在此层配置) ===
  mimoConfig: {
    tx_layers: number
    rx_layers: number
    precoding_mode: 'open-loop' | 'closed-loop' | 'beamforming'
  }

  // === 调度配置 ===
  scheduler: {
    type: 'round-robin' | 'proportional-fair' | 'max-throughput'
    max_users_per_tti?: number
  }
}

interface BaseStation {
  bs_id: string
  name: string

  // === 位置信息 ===
  position: {
    lat: number
    lon: number
    alt: number
  }

  // === 发射配置 ===
  tx: {
    power_dbm: number           // 总发射功率
    antenna_height_m: number
    azimuth_deg: number         // 方位角
    tilt_deg: number            // 下倾角
  }

  // === 天线配置 (独立模块，可被Environment引用) ===
  antenna: AntennaConfiguration  // 内嵌天线配置

  // === 小区配置 ===
  cells: Cell[]
}

// 天线配置作为独立模块，既可内嵌在BaseStation，也可被Environment引用
interface AntennaConfiguration {
  id: string
  name: string
  type: 'omnidirectional' | 'directional' | 'panel' | 'horn' | 'custom'

  // 天线阵列配置
  array: {
    rows: number
    columns: number
    element_spacing_lambda: number  // 以波长为单位
    polarization: 'single' | 'dual' | 'cross'
  }

  // 辐射方向图
  pattern: {
    type: 'isotropic' | '3gpp-38901' | 'measured'
    gain_dbi: number
    beamwidth_h_deg?: number
    beamwidth_v_deg?: number
    pattern_file?: string         // 实测方向图文件
  }

  // 波束赋形能力
  beamforming?: {
    capable: boolean
    max_beams: number
    beam_switching_time_us?: number
  }
}

interface Cell {
  cell_id: string
  pci: number                   // Physical Cell ID
  sector: number                // 扇区编号 (0, 1, 2)
  earfcn?: number               // LTE frequency channel
  nrarfcn?: number              // NR frequency channel
}
```

### 3.3 与Environment层的接口

```typescript
// Base Station 请求 Environment 计算信道
interface ChannelRequest {
  bs_id: string
  ue_position: Position3D
  timestamp_s: number
  antenna_config_ref: string     // 天线配置引用
}

// Environment 返回信道响应
interface ChannelResponse {
  path_loss_db: number
  delay_spread_ns: number
  doppler_shift_hz: number
  channel_matrix: Complex[][]    // MIMO信道矩阵
  multipath_components: MultipathComponent[]
}
```

---

## 4. Layer 3: Environment (数字孪生环境)

### 4.1 设计定位

Environment层是整个虚拟路测的**数字孪生背景**，包含所有影响无线传播的因素。

**核心职责**:
1. 物理环境定义（地形、建筑、天气）
2. 信道模型配置（射线跟踪/统计模型）
3. 干扰源定义
4. 噪声模型
5. 移动散射体
6. 终端配置

**注意**: 天线配置保留在BaseStation层，Environment层可以通过引用获取天线参数用于信道计算。

### 4.2 数据模型

```typescript
interface EnvironmentConfiguration {
  // === 物理环境 ===
  physicalEnvironment: {
    type: 'urban' | 'suburban' | 'highway' | 'tunnel' | 'indoor' | 'rural'

    // 地理区域（用于射线跟踪）
    region?: {
      name: string              // e.g., "北京CBD"
      bounds: GeoBounds
      gis_file?: string         // GIS数据文件
      building_model?: string   // 3D建筑模型
    }

    // 天气条件
    weather: {
      condition: 'clear' | 'rain' | 'fog' | 'snow'
      rain_rate_mm_h?: number   // 影响FR2衰减
      humidity_percent?: number
      temperature_c?: number
    }
  }

  // === 信道模型配置 ===
  channelModel: {
    type: 'ray-tracing' | '3gpp-statistical' | 'measured'

    // 射线跟踪配置
    rayTracing?: RayTracingConfig

    // 3GPP统计模型配置
    statisticalModel?: {
      scenario: 'UMa' | 'UMi' | 'RMa' | 'InH'
      los_condition: 'LOS' | 'NLOS' | 'auto'
      cluster_model?: 'CDL-A' | 'CDL-B' | 'CDL-C' | 'CDL-D' | 'CDL-E' |
                      'TDL-A' | 'TDL-B' | 'TDL-C'
    }

    // 实测信道数据
    measured?: {
      data_file: string
      format: 'matlab' | 'csv' | 'hdf5'
    }
  }

  // === 干扰源 ===
  interference: InterferenceSource[]

  // === 噪声模型 ===
  noise: {
    thermal_noise_figure_db: number
    additional_noise_db?: number
    noise_floor_dbm?: number
  }

  // === 移动散射体 ===
  scatterers: MovingScatterer[]

  // === 终端配置 ===
  ueConfig: {
    antenna: AntennaConfiguration  // 终端天线配置
    height_m: number
    body_loss_db?: number
  }
}
```

### 4.3 射线跟踪配置

```typescript
interface RayTracingConfig {
  tool: 'WirelessInSite' | 'WinProp' | 'CloudRT' | 'Custom'
  version?: string

  // 仿真参数
  simulation: {
    max_reflections: number       // 最大反射次数
    max_diffractions: number      // 最大绕射次数
    ray_spacing_deg: number       // 射线间隔
    frequency_mhz: number
  }

  // 输出文件引用
  output: {
    path_loss_file?: string
    channel_coefficients_file?: string
    power_delay_profile_file?: string
    angle_data_file?: string
  }

  // 预计算的路径点数据
  precomputed?: {
    route_file: string            // 路径文件
    sample_rate_hz: number        // 采样率
    total_points: number
  }
}
```

### 4.4 干扰源模型

```typescript
interface InterferenceSource {
  id: string
  type: 'co-channel' | 'adjacent-channel' | 'out-of-band' | 'wideband'

  // 干扰源位置
  position: Position3D

  // 干扰特性
  characteristics: {
    power_dbm: number
    frequency_mhz: number
    bandwidth_mhz: number
    modulation?: string
    duty_cycle?: number          // 0-1, 用于间歇性干扰
  }

  // 时变性
  temporal?: {
    start_time_s: number
    duration_s: number
    pattern: 'continuous' | 'pulsed' | 'random'
  }
}
```

### 4.5 移动散射体模型

```typescript
interface MovingScatterer {
  id: string
  type: 'vehicle' | 'pedestrian' | 'train' | 'aircraft'

  // 散射体轨迹
  trajectory: Waypoint[]

  // 雷达截面积 (影响反射强度)
  rcs_dbsm: number               // Radar Cross Section in dB-m²

  // 遮挡特性
  blockage: {
    attenuation_db: number       // 完全遮挡时的衰减
    shadow_region_m: number      // 阴影区域尺寸
  }
}
```

---

## 5. 测试步骤定义 (8步)

基于三层架构，定义8个测试步骤：

### 5.1 步骤列表

| 步骤编号 | 步骤名称 | 所属层 | 职责 |
|---------|---------|-------|------|
| 1 | `chamber_init` | 硬件 | OTA暗室初始化 |
| 2 | `network_config` | Network | 配置核心网/传输网 |
| 3 | `base_station_setup` | Base Station | 配置基站参数 |
| 4 | `ota_mapper` | 映射 | 信道→探头权重映射 |
| 5 | `route_execution` | 执行 | 执行路径测试 |
| 6 | `kpi_validation` | 验证 | 验证KPI指标 |
| 7 | `report_generation` | 报告 | 生成测试报告 |
| 8 | `environment_setup` | Environment | 加载数字孪生环境 (**新增**) |

### 5.2 步骤 8: environment_setup

```typescript
interface EnvironmentSetupStep {
  // === 环境加载 ===
  environment_file?: string       // 预定义环境文件
  environment_config?: EnvironmentConfiguration  // 或内联配置

  // === 信道模型配置 ===
  channel_model?: {
    type: 'ray-tracing' | '3gpp-statistical' | 'measured'
    scenario?: 'UMa' | 'UMi' | 'RMa' | 'InH'
    los_condition?: 'LOS' | 'NLOS' | 'auto'
  }

  // === 干扰配置 ===
  interference?: {
    enabled: boolean
    sources?: InterferenceSource[]
  }

  // === 移动散射体配置 ===
  scatterers?: {
    enabled: boolean
    sources?: MovingScatterer[]
  }

  // === 预计算选项 ===
  precompute_channel?: {
    enabled: boolean
    route_file?: string
    sample_rate_hz?: number
  }

  // === 验证选项 ===
  validate_environment?: boolean
  timeout_seconds?: number
}
```

### 5.3 步骤与测试模式的对应关系

每个步骤根据测试模式有不同的执行行为：

```
步骤                   数字孪生           传导测试           OTA测试
────────────────────  ────────────────  ────────────────  ────────────────
1. chamber_init       跳过              跳过              执行(真实暗室)
2. network_config     软件模拟核心网     配置仪表网络       配置仪表网络
3. base_station_setup 软件模拟基站       配置真实仪表基站    配置真实仪表基站
4. ota_mapper         跳过              跳过              执行(信道→探头)
5. route_execution    纯软件仿真         信号发生器回放      信道仿真器+探头
6. kpi_validation     执行              执行              执行
7. report_generation  执行              执行              执行
8. environment_setup  执行(加载环境)     执行(加载环境)     执行(加载环境)
```

### 5.4 步骤执行顺序

虽然步骤编号是1-8，但**实际执行顺序**根据测试模式调整：

**OTA测试执行顺序:**
```
environment_setup → chamber_init → network_config → base_station_setup
    → ota_mapper → route_execution → kpi_validation → report_generation
```

**传导测试执行顺序:**
```
environment_setup → network_config → base_station_setup
    → route_execution → kpi_validation → report_generation
```

**数字孪生执行顺序:**
```
environment_setup → network_config(模拟) → base_station_setup(模拟)
    → route_execution(仿真) → kpi_validation → report_generation
```

### 5.5 步骤内容根据模式变化

```typescript
// 示例：base_station_setup 步骤在不同模式下的行为
interface BaseStationSetupStep {
  // 通用配置
  channel_model?: string
  num_base_stations?: number
  bs_positions?: Position3D[]
  timeout_seconds?: number

  // 模式特定行为 (运行时由执行引擎处理)
  // digital_twin: 初始化软件模拟器
  // conducted: 配置信号发生器
  // ota: 配置仪表 + 准备信道仿真
}
```

---

## 6. 数据流架构

### 6.1 场景到测试执行的数据流

```
┌─────────────────────┐
│   Scenario Library   │
│  (场景定义)          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Environment Layer   │  ← 加载数字孪生环境
│  - 信道模型          │
│  - 天线配置          │
│  - 干扰/噪声         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Channel Calculation │  ← 计算信道矩阵
│  (ChannelEngine)     │
└──────────┬──────────┘
           │
           ▼
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌────────┐   ┌────────────┐
│数字孪生 │   │ OTA Mapper  │  ← 信道→探头权重
│(软件)   │   │ (探头映射)   │
└────────┘   └─────┬──────┘
                   │
                   ▼
             ┌────────────┐
             │ Probe Array │  ← 探头权重下发
             │ Controller  │
             └────────────┘
```

### 6.2 环境与基站的交互

```typescript
// 场景执行时的数据流
async function executeScenario(scenario: RoadTestScenario, mode: TestMode) {
  // 1. 加载环境配置
  const env = await loadEnvironment(scenario.environment)

  // 2. 初始化信道计算器 (使用环境中的天线配置)
  const channelEngine = new ChannelEngine({
    model: env.channelModel,
    antennas: {
      bs: env.antennaConfigs[scenario.baseStations[0].antenna_config_ref],
      ue: env.antennaConfigs[env.ueConfig.antenna_config_ref]
    }
  })

  // 3. 遍历路径点
  for (const waypoint of scenario.route.waypoints) {
    // 计算该位置的信道
    const channel = await channelEngine.calculate({
      bs_position: scenario.baseStations[0].position,
      ue_position: waypoint.position,
      timestamp: waypoint.time_s
    })

    if (mode === 'ota') {
      // 4. 转换为探头权重
      const probeWeights = await otaMapper.mapToProbes(channel)

      // 5. 下发到探头控制器
      await probeController.setWeights(probeWeights)
    }
  }
}
```

---

## 7. 实现优先级

### Phase 1: 数据模型重构
- [ ] 更新 `roadTest.ts` 类型定义
- [ ] 拆分 NetworkConfiguration
- [ ] 拆分 BaseStationConfiguration
- [ ] 新增 EnvironmentConfiguration
- [ ] 更新 StepConfiguration 增加 environment_setup

### Phase 2: 后端适配
- [ ] 更新场景 API 模型
- [ ] ChannelEngine 接入 Environment 配置
- [ ] OTA Mapper 接入天线配置

### Phase 3: 前端组件
- [ ] 创建 EnvironmentEditor 组件
- [ ] 更新场景详情视图
- [ ] 更新测试执行流程

---

## 8. 向后兼容性

现有场景数据迁移策略：

```typescript
function migrateScenarioV1toV2(oldScenario: ScenarioV1): ScenarioV2 {
  return {
    ...oldScenario,

    // 从旧的扁平结构提取 Environment
    environment: {
      physicalEnvironment: {
        type: oldScenario.environment?.type || 'urban',
        weather: { condition: oldScenario.environment?.weather || 'clear' }
      },
      channelModel: {
        type: '3gpp-statistical',
        statisticalModel: {
          scenario: oldScenario.environment?.channel_model || 'UMa',
          los_condition: 'auto'
        }
      },
      antennaConfigs: {
        'bs-default': { /* 默认基站天线 */ },
        'ue-default': { /* 默认终端天线 */ }
      },
      ueConfig: {
        antenna_config_ref: 'ue-default',
        height_m: 1.5
      }
    },

    // 更新基站配置引用
    baseStations: oldScenario.base_stations?.map(bs => ({
      ...bs,
      antenna_config_ref: 'bs-default'
    }))
  }
}
```

---

## 9. 总结

本设计通过三层架构（Network / Base Station / Environment）实现了：

1. **职责清晰**: 每层有明确的边界和职责
2. **信道建模统一**: Environment层统一管理所有影响信道的因素
3. **天线配置集中**: 天线配置在Environment层，基站和终端通过引用使用
4. **测试模式适配**: 各层根据测试模式灵活执行或跳过
5. **向后兼容**: 提供迁移策略保证现有数据可用

**下一步**: 讨论确认后，开始Phase 1实现。
