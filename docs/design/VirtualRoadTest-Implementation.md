# 虚拟路测产品 - 开发者实施指南

## 目录

- [1. 开发环境准备](#1-开发环境准备)
- [2. 目录结构设计](#2-目录结构设计)
- [3. Phase 1 实施步骤](#3-phase-1-实施步骤)
- [4. 核心代码示例](#4-核心代码示例)
- [5. Mock数据设计](#5-mock数据设计)
- [6. 前端组件开发](#6-前端组件开发)
- [7. API实现](#7-api实现)
- [8. 测试策略](#8-测试策略)
- [9. 部署指南](#9-部署指南)

---

## 1. 开发环境准备

### 1.1 前置条件

确保已安装以下工具：

```bash
# Node.js (v18+)
node --version  # v18.0.0+

# npm (v9+)
npm --version   # v9.0.0+

# Git
git --version

# IDE推荐: VS Code
code --version
```

### 1.2 安装依赖

```bash
cd gui

# 安装现有依赖
npm install

# 安装新增依赖
npm install --save \
  recharts \
  three @react-three/fiber @react-three/drei \
  leaflet react-leaflet \
  @types/leaflet

# 开发依赖
npm install --save-dev \
  @types/three
```

### 1.3 VS Code推荐插件

```json
{
  "recommendations": [
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "ms-vscode.vscode-typescript-next",
    "bradlc.vscode-tailwindcss",
    "mermaid-js.mermaid-editor"
  ]
}
```

---

## 2. 目录结构设计

### 2.1 完整目录树

```
Meta-3D/
├── gui/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts                    # 已有
│   │   │   ├── service.ts                   # 已有，需扩展
│   │   │   ├── mockServer.ts                # 已有，需扩展
│   │   │   └── mockDatabase.ts              # 已有，需扩展
│   │   │
│   │   ├── services/                        # 已有
│   │   │   ├── channels/                    # 已有
│   │   │   │   ├── ChannelEmulatorHAL.ts
│   │   │   │   ├── mockDriver.ts
│   │   │   │   └── transport.ts
│   │   │   │
│   │   │   ├── testExecution/               # 🆕 新增
│   │   │   │   ├── ITestExecutor.ts         # 统一接口
│   │   │   │   ├── DigitalTwinExecutor.ts   # 数字孪生执行器
│   │   │   │   ├── ConductedExecutor.ts     # 传导测试执行器
│   │   │   │   └── OTAExecutor.ts           # OTA执行器
│   │   │   │
│   │   │   ├── digitalTwin/                 # 🆕 新增
│   │   │   │   ├── NetworkSimulator.ts      # 网络仿真器
│   │   │   │   ├── ChannelSimulator.ts      # 信道仿真器
│   │   │   │   ├── DUTSimulator.ts          # DUT仿真器
│   │   │   │   └── ScenarioEngine.ts        # 场景引擎
│   │   │   │
│   │   │   ├── conducted/                   # 🆕 新增
│   │   │   │   ├── TopologyManager.ts       # 拓扑管理器
│   │   │   │   ├── BaseStationDriver.ts     # 基站驱动
│   │   │   │   └── DUTDriver.ts             # DUT驱动
│   │   │   │
│   │   │   └── ota/                         # 🆕 新增
│   │   │       ├── OTAScenarioMapper.ts     # 场景映射器
│   │   │       └── MPACController.ts        # MPAC控制器
│   │   │
│   │   ├── components/                      # 已有
│   │   │   ├── ProbeLayoutView.tsx          # 已有
│   │   │   │
│   │   │   └── VirtualRoadTest/             # 🆕 新增
│   │   │       ├── ModeSelector.tsx         # 模式选择器
│   │   │       ├── ScenarioLibrary.tsx      # 场景库
│   │   │       ├── ScenarioEditor/          # 场景编辑器
│   │   │       │   ├── index.tsx
│   │   │       │   ├── MapEditor.tsx
│   │   │       │   ├── NetworkEditor.tsx
│   │   │       │   └── EventTimeline.tsx
│   │   │       ├── TopologyConfigurator/    # 拓扑配置器
│   │   │       │   ├── index.tsx
│   │   │       │   ├── WizardMode.tsx
│   │   │       │   ├── VisualMode.tsx
│   │   │       │   └── ConnectionMapper.tsx
│   │   │       ├── ExecutionMonitor/        # 执行监控
│   │   │       │   ├── DigitalTwinDashboard.tsx
│   │   │       │   ├── ConductedDashboard.tsx
│   │   │       │   ├── OTADashboard.tsx
│   │   │       │   └── KPICharts.tsx
│   │   │       └── ResultsAnalyzer/         # 结果分析
│   │   │           ├── index.tsx
│   │   │           ├── CompareView.tsx
│   │   │           └── ReportGenerator.tsx
│   │   │
│   │   ├── types/                           # 已有
│   │   │   ├── api.ts                       # 已有，需扩展
│   │   │   ├── api.generated.ts             # 已有
│   │   │   ├── channel.ts                   # 已有
│   │   │   │
│   │   │   └── roadTest/                    # 🆕 新增
│   │   │       ├── scenario.ts              # 场景类型
│   │   │       ├── topology.ts              # 拓扑类型
│   │   │       ├── execution.ts             # 执行类型
│   │   │       └── metrics.ts               # 指标类型
│   │   │
│   │   ├── hooks/                           # 🆕 新增
│   │   │   ├── useScenarios.ts              # TanStack Query hooks
│   │   │   ├── useTopologies.ts
│   │   │   ├── useExecution.ts
│   │   │   └── useWebSocket.ts
│   │   │
│   │   ├── data/                            # 🆕 新增
│   │   │   ├── scenarioLibrary.ts           # 预定义场景库
│   │   │   └── standardScenarios/           # 标准场景数据
│   │   │       ├── 3gpp/
│   │   │       ├── ctia/
│   │   │       └── 5gaa/
│   │   │
│   │   ├── App.tsx                          # 已有，需扩展菜单
│   │   └── main.tsx                         # 已有
│   │
│   ├── public/
│   │   └── config/
│   │       ├── probes/                      # 已有
│   │       └── scenarios/                   # 🆕 新增：场景配置文件
│   │
│   └── package.json                         # 需更新依赖
│
├── api/
│   └── openapi.yaml                         # 需扩展
│
├── VirtualRoadTest.md                       # 主设计文档
├── VirtualRoadTest-Architecture.md          # 架构设计文档
└── VirtualRoadTest-Implementation.md        # 本文档
```

---

## 3. Phase 1 实施步骤

### 3.1 第1周：类型定义与接口

#### Step 1: 创建核心类型文件

```bash
# 创建新目录
mkdir -p gui/src/types/roadTest
mkdir -p gui/src/services/testExecution
mkdir -p gui/src/components/VirtualRoadTest
mkdir -p gui/src/hooks
mkdir -p gui/src/data
```

#### Step 2: 实现类型定义

创建 `gui/src/types/roadTest/scenario.ts`:

```typescript
// gui/src/types/roadTest/scenario.ts

/**
 * 场景分类枚举
 */
export enum ScenarioCategory {
  STANDARD_3GPP = '3GPP',
  STANDARD_CTIA = 'CTIA',
  STANDARD_5GAA = '5GAA',
  FUNCTIONAL_HANDOVER = 'handover',
  FUNCTIONAL_BEAM_SWITCHING = 'beam_switching',
  PERFORMANCE_THROUGHPUT = 'max_throughput',
  ENV_URBAN_CANYON = 'urban_canyon',
  ENV_HIGHWAY_SPEED = 'high_speed',
  ENV_TUNNEL = 'tunnel',
  EXTREME_EDGE_COVERAGE = 'cell_edge',
  CUSTOM = 'custom'
}

/**
 * 路测场景定义
 */
export interface RoadTestScenario {
  // 元数据
  id: string;
  name: string;
  description?: string;
  category: ScenarioCategory;
  source: 'standard' | 'custom';
  tags: string[];

  // 网络配置
  network: NetworkConfig;

  // 路径轨迹
  route: Route;

  // 环境条件
  environment: Environment;

  // 业务流量
  traffic: TrafficConfig;

  // 触发事件
  events: ScenarioEvent[];

  // KPI定义
  kpi: KPIDefinition[];
}

/**
 * 网络配置
 */
export interface NetworkConfig {
  type: '5G_NR' | 'LTE' | 'C-V2X';
  band: string;              // 'n78', 'n79'
  bandwidth: string;         // '100MHz'
  baseStations: BaseStationConfig[];
}

export interface BaseStationConfig {
  id: string;
  position: {
    lat: number;
    lon: number;
    alt: number;             // 海拔 (米)
  };
  power: string;             // '46dBm'
  azimuth?: number;          // 方位角 (度)
  tilt?: number;             // 下倾角 (度)
}

/**
 * 路径轨迹
 */
export interface Route {
  type: 'predefined' | 'recorded' | 'generated';
  waypoints: Waypoint[];
  duration: number;          // 秒
  totalDistance: number;     // 米
  speed: SpeedProfile;
}

export interface Waypoint {
  time: number;              // 秒
  position: {
    lat: number;
    lon: number;
    alt: number;
  };
  velocity: {
    speed: number;           // m/s
    heading: number;         // 度 (0-360)
  };
  nearestBS?: string;        // 最近基站ID
}

export type SpeedProfile =
  | { type: 'constant'; value: number }           // km/h
  | { type: 'variable'; values: number[] }        // 时间序列
  | { type: 'acceleration'; initial: number; final: number; duration: number };

/**
 * 环境条件
 */
export interface Environment {
  type: 'urban' | 'suburban' | 'highway' | 'rural' | 'tunnel';
  weather: 'clear' | 'rain' | 'fog' | 'snow';
  trafficDensity: 'light' | 'medium' | 'heavy';
  obstructions: Obstruction[];
}

export interface Obstruction {
  type: 'building' | 'tree' | 'vehicle' | 'other';
  position: {
    lat: number;
    lon: number;
  };
  dimensions?: {
    width: number;           // 米
    height: number;          // 米
  };
  material?: string;         // 'concrete', 'glass', etc.
}

/**
 * 业务流量配置
 */
export interface TrafficConfig {
  type: 'ftp' | 'video' | 'voip' | 'mixed';
  direction: 'DL' | 'UL' | 'bidirectional';
  dataRate: string;          // '50Mbps'
  packetSize?: number;       // 字节
  iat?: number;              // Inter-Arrival Time (ms)
}

/**
 * 场景事件
 */
export interface ScenarioEvent {
  time: number;              // 秒
  type: 'handover' | 'beam_switch' | 'rf_impairment' | 'traffic_burst';
  parameters: Record<string, any>;
}

/**
 * KPI定义
 */
export interface KPIDefinition {
  name: string;              // 'throughput', 'latency', 'bler'
  target: string;            // '>50Mbps', '<20ms', '<1%'
  percentile?: number;       // 95 (第95百分位)
  weight?: number;           // 权重 (0-1)
}
```

创建 `gui/src/types/roadTest/topology.ts`:

```typescript
// gui/src/types/roadTest/topology.ts

/**
 * 网络拓扑定义（传导测试专用）
 */
export interface NetworkTopology {
  id: string;
  name: string;
  type: 'SISO' | 'MIMO_2x2' | 'MIMO_4x4' | 'MIMO_8x8' | 'custom';

  // 基站仿真器
  baseStation: BaseStationDevice;

  // 信道仿真器
  channelEmulator: ChannelEmulatorDevice;

  // DUT
  dut: DUTDevice;

  // RF连接
  connections: RFConnection[];
}

export interface BaseStationDevice {
  model: 'CMX500' | '8820C' | 'other';
  address: string;           // IP地址
  txPorts: number[];         // [1, 2, 3, 4]
  frequency: string;         // 'n78@3.5GHz'
  power: string;             // '-50dBm'
}

export interface ChannelEmulatorDevice {
  model: 'PropsIM_F64' | 'Vertex' | 'KSW-WNS02B' | 'other';
  address: string;
  inputMapping: PortMapping[];
  outputMapping: PortMapping[];
  channelModel: string;      // '3GPP CDL-C'
}

export interface PortMapping {
  logicalPort: number;
  physicalPort: number;
}

export interface DUTDevice {
  model: string;             // 车辆型号
  rxPorts: number[];         // [1, 2, 3, 4]
  controlInterface: DUTInterface;
}

export interface DUTInterface {
  type: 'adb' | 'usb' | 'ethernet';
  address: string;
  credentials?: {
    username: string;
    password: string;
  };
}

/**
 * RF连接定义
 */
export interface RFConnection {
  from: {
    device: 'baseStation' | 'channelEmulator' | 'dut';
    port: number;
  };
  to: {
    device: 'baseStation' | 'channelEmulator' | 'dut';
    port: number;
  };
  cable: CableSpec;
}

export interface CableSpec {
  type: string;              // 'RG-58', 'LMR-400'
  length: number;            // 单位：米
  loss: number;              // 单位：dB
}
```

创建 `gui/src/types/roadTest/execution.ts`:

```typescript
// gui/src/types/roadTest/execution.ts

import { RoadTestScenario } from './scenario';
import { NetworkTopology } from './topology';

/**
 * 测试模式
 */
export enum TestMode {
  DIGITAL_TWIN = 'digital_twin',
  CONDUCTED = 'conducted',
  OTA = 'ota'
}

/**
 * 测试配置
 */
export interface TestConfig {
  mode: TestMode;
  scenario: RoadTestScenario;
  topology?: NetworkTopology;        // 传导模式需要
  dut: DUTConfig;
  kpi: KPIDefinition[];
  duration?: number;

  // 模式特定配置
  digitalTwinConfig?: DigitalTwinConfig;
  conductedConfig?: ConductedConfig;
  otaConfig?: OTAConfig;
}

/**
 * DUT配置
 */
export interface DUTConfig {
  model: string;
  antennas: number;
  capabilities: string[];
}

/**
 * 数字孪生配置
 */
export interface DigitalTwinConfig {
  resources: {
    gpuCount: number;
    cpuCores: number;
    memory: string;          // '32GB'
  };
  fidelity: {
    timeStep: number;        // 秒
    spatialResolution: number; // 米
    channelTaps: number;
  };
  acceleration: {
    realTimeFactor: number;  // 1.0 = 实时
    parallelization: boolean;
    gpuAcceleration: boolean;
  };
}

/**
 * 传导测试配置
 */
export interface ConductedConfig {
  chamber: {
    location: string;
    isolation: number;       // dB
  };
  powerCalibration: {
    enabled: boolean;
    referenceLevel: string;
    tolerance: number;
  };
  cableLossCompensation: {
    enabled: boolean;
    autoDetect: boolean;
  };
}

/**
 * OTA测试配置
 */
export interface OTAConfig {
  mpac: {
    probeCount: number;
    radius: number;          // 米
  };
  positioner: {
    azimuthRange: [number, number];
    elevationRange: [number, number];
  };
}

/**
 * 测试结果
 */
export interface TestResult {
  success: boolean;
  mode?: TestMode;
  message?: string;
  data?: any;
}

/**
 * 执行句柄
 */
export interface ExecutionHandle {
  executionId: string;
  mode: TestMode;
  status: TestStatus;
  startTime: string;
}

/**
 * 测试状态
 */
export enum TestStatus {
  INITIALIZING = 'initializing',
  RUNNING = 'running',
  PAUSED = 'paused',
  STOPPED = 'stopped',
  COMPLETED = 'completed',
  FAILED = 'failed'
}
```

创建 `gui/src/types/roadTest/metrics.ts`:

```typescript
// gui/src/types/roadTest/metrics.ts

/**
 * 测试指标
 */
export interface TestMetrics {
  timestamp: string;
  throughput: ThroughputMetrics;
  latency: LatencyMetrics;
  signalQuality: SignalQualityMetrics;
  linkQuality: LinkQualityMetrics;
}

export interface ThroughputMetrics {
  downlink: number;          // Mbps
  uplink: number;            // Mbps
}

export interface LatencyMetrics {
  average: number;           // ms
  p50: number;
  p95: number;
  p99: number;
}

export interface SignalQualityMetrics {
  rsrp: number[];            // dBm (per antenna)
  rsrq: number[];            // dB
  sinr: number[];            // dB
}

export interface LinkQualityMetrics {
  bler: number;              // %
  mcs: number;               // Modulation and Coding Scheme
  cqi: number;               // Channel Quality Indicator
}
```

#### Step 3: 实现统一执行器接口

创建 `gui/src/services/testExecution/ITestExecutor.ts`:

```typescript
// gui/src/services/testExecution/ITestExecutor.ts

import {
  TestConfig,
  TestResult,
  ExecutionHandle,
  TestStatus,
  TestMode
} from '../../types/roadTest/execution';
import { TestMetrics } from '../../types/roadTest/metrics';
import { RoadTestScenario } from '../../types/roadTest/scenario';
import { NetworkTopology } from '../../types/roadTest/topology';
import { DUTConfig } from '../../types/roadTest/execution';

/**
 * 验证结果
 */
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/**
 * 测试能力
 */
export interface TestCapabilities {
  supportedScenarios: string[];
  maxDuration: number;
  maxAntennas: number;
  features: string[];
}

/**
 * 事件回调
 */
export type EventCallback = (event: TestEvent) => void;

export interface TestEvent {
  type: 'status' | 'metric' | 'alert' | 'log';
  timestamp: string;
  data: any;
}

/**
 * 订阅对象
 */
export interface Subscription {
  unsubscribe: () => void;
}

/**
 * 统一测试执行器接口
 */
export interface ITestExecutor {
  // ========== 生命周期管理 ==========

  /**
   * 初始化测试执行器
   */
  initialize(config: TestConfig): Promise<TestResult>;

  /**
   * 验证配置
   */
  validate(): Promise<ValidationResult>;

  /**
   * 执行测试
   */
  execute(): Promise<ExecutionHandle>;

  /**
   * 暂停测试
   */
  pause(): Promise<void>;

  /**
   * 继续测试
   */
  resume(): Promise<void>;

  /**
   * 停止测试
   */
  stop(): Promise<void>;

  /**
   * 清理资源
   */
  cleanup(): Promise<void>;

  // ========== 配置管理 ==========

  /**
   * 加载场景
   */
  loadScenario(scenario: RoadTestScenario): Promise<TestResult>;

  /**
   * 配置拓扑（传导模式）
   */
  configureTopology(topology: NetworkTopology): Promise<TestResult>;

  /**
   * 配置DUT
   */
  configureDUT(dut: DUTConfig): Promise<TestResult>;

  // ========== 实时监控 ==========

  /**
   * 查询状态
   */
  queryStatus(): Promise<TestStatus>;

  /**
   * 获取指标
   */
  getMetrics(): Promise<TestMetrics>;

  /**
   * 订阅事件
   */
  subscribeEvents(callback: EventCallback): Subscription;

  // ========== 能力查询 ==========

  /**
   * 获取能力
   */
  getCapabilities(): TestCapabilities;

  /**
   * 获取支持的场景
   */
  getSupportedScenarios(): RoadTestScenario[];
}
```

### 3.2 第2周：Mock数据与API

#### Step 1: 扩展Mock数据库

编辑 `gui/src/api/mockDatabase.ts`，添加场景库数据：

```typescript
// gui/src/api/mockDatabase.ts (扩展部分)

import { RoadTestScenario, ScenarioCategory } from '../types/roadTest/scenario';
import { NetworkTopology } from '../types/roadTest/topology';

// ========== 场景库 ==========

export const mockScenarios: RoadTestScenario[] = [
  {
    id: 'std-3gpp-uma-nlos',
    name: '3GPP UMa NLOS 城市密集区',
    description: '3GPP TR 38.901 UMa场景，非视距传播',
    category: ScenarioCategory.STANDARD_3GPP,
    source: 'standard',
    tags: ['3GPP', 'UMa', 'NLOS', 'urban'],

    network: {
      type: '5G_NR',
      band: 'n78',
      bandwidth: '100MHz',
      baseStations: [
        {
          id: 'BS1',
          position: { lat: 31.2304, lon: 121.4737, alt: 25 },
          power: '46dBm',
          azimuth: 0,
          tilt: 10
        }
      ]
    },

    route: {
      type: 'predefined',
      waypoints: [
        {
          time: 0,
          position: { lat: 31.2300, lon: 121.4730, alt: 0 },
          velocity: { speed: 8.33, heading: 45 },  // 30 km/h
          nearestBS: 'BS1'
        },
        {
          time: 30,
          position: { lat: 31.2310, lon: 121.4740, alt: 0 },
          velocity: { speed: 8.33, heading: 45 },
          nearestBS: 'BS1'
        },
        {
          time: 60,
          position: { lat: 31.2320, lon: 121.4750, alt: 0 },
          velocity: { speed: 8.33, heading: 45 },
          nearestBS: 'BS1'
        }
      ],
      duration: 60,
      totalDistance: 500,
      speed: { type: 'constant', value: 30 }
    },

    environment: {
      type: 'urban',
      weather: 'clear',
      trafficDensity: 'heavy',
      obstructions: [
        {
          type: 'building',
          position: { lat: 31.2305, lon: 121.4735 },
          dimensions: { width: 50, height: 30 },
          material: 'concrete'
        }
      ]
    },

    traffic: {
      type: 'ftp',
      direction: 'DL',
      dataRate: '100Mbps'
    },

    events: [],

    kpi: [
      {
        name: 'throughput',
        target: '>50Mbps',
        percentile: 95,
        weight: 0.5
      },
      {
        name: 'latency',
        target: '<20ms',
        percentile: 95,
        weight: 0.3
      },
      {
        name: 'bler',
        target: '<1%',
        percentile: 95,
        weight: 0.2
      }
    ]
  },

  {
    id: 'func-handover-highway',
    name: '高速公路切换场景',
    description: '车辆高速移动触发小区切换',
    category: ScenarioCategory.FUNCTIONAL_HANDOVER,
    source: 'standard',
    tags: ['handover', 'highway', 'mobility'],

    network: {
      type: '5G_NR',
      band: 'n78',
      bandwidth: '100MHz',
      baseStations: [
        {
          id: 'BS1',
          position: { lat: 31.2300, lon: 121.4700, alt: 30 },
          power: '46dBm'
        },
        {
          id: 'BS2',
          position: { lat: 31.2300, lon: 121.4800, alt: 30 },
          power: '46dBm'
        }
      ]
    },

    route: {
      type: 'predefined',
      waypoints: [
        {
          time: 0,
          position: { lat: 31.2300, lon: 121.4720, alt: 0 },
          velocity: { speed: 33.33, heading: 90 },  // 120 km/h
          nearestBS: 'BS1'
        },
        {
          time: 60,
          position: { lat: 31.2300, lon: 121.4760, alt: 0 },
          velocity: { speed: 33.33, heading: 90 },
          nearestBS: 'BS1'
        },
        {
          time: 120,
          position: { lat: 31.2300, lon: 121.4800, alt: 0 },
          velocity: { speed: 33.33, heading: 90 },
          nearestBS: 'BS2'
        }
      ],
      duration: 120,
      totalDistance: 3000,
      speed: { type: 'constant', value: 120 }
    },

    environment: {
      type: 'highway',
      weather: 'clear',
      trafficDensity: 'medium',
      obstructions: []
    },

    traffic: {
      type: 'video',
      direction: 'DL',
      dataRate: '20Mbps'
    },

    events: [
      {
        time: 60,
        type: 'handover',
        parameters: {
          from: 'BS1',
          to: 'BS2',
          type: 'intra-freq'
        }
      }
    ],

    kpi: [
      {
        name: 'handover_success_rate',
        target: '>99%',
        weight: 0.6
      },
      {
        name: 'handover_interruption_time',
        target: '<50ms',
        percentile: 95,
        weight: 0.4
      }
    ]
  }
];

// ========== 拓扑库 ==========

export const mockTopologies: NetworkTopology[] = [
  {
    id: 'topo-mimo-4x4',
    name: 'MIMO 4×4 标准拓扑',
    type: 'MIMO_4x4',

    baseStation: {
      model: 'CMX500',
      address: '192.168.1.100',
      txPorts: [1, 2, 3, 4],
      frequency: 'n78@3.5GHz',
      power: '-50dBm'
    },

    channelEmulator: {
      model: 'PropsIM_F64',
      address: '192.168.1.101',
      inputMapping: [
        { logicalPort: 1, physicalPort: 1 },
        { logicalPort: 2, physicalPort: 2 },
        { logicalPort: 3, physicalPort: 3 },
        { logicalPort: 4, physicalPort: 4 }
      ],
      outputMapping: [
        { logicalPort: 1, physicalPort: 1 },
        { logicalPort: 2, physicalPort: 2 },
        { logicalPort: 3, physicalPort: 3 },
        { logicalPort: 4, physicalPort: 4 }
      ],
      channelModel: '3GPP CDL-C'
    },

    dut: {
      model: 'Tesla Model 3',
      rxPorts: [1, 2, 3, 4],
      controlInterface: {
        type: 'adb',
        address: '192.168.1.102'
      }
    },

    connections: [
      {
        from: { device: 'baseStation', port: 1 },
        to: { device: 'channelEmulator', port: 1 },
        cable: { type: 'LMR-400', length: 5, loss: 1.2 }
      },
      {
        from: { device: 'baseStation', port: 2 },
        to: { device: 'channelEmulator', port: 2 },
        cable: { type: 'LMR-400', length: 5, loss: 1.2 }
      },
      {
        from: { device: 'baseStation', port: 3 },
        to: { device: 'channelEmulator', port: 3 },
        cable: { type: 'LMR-400', length: 5, loss: 1.2 }
      },
      {
        from: { device: 'baseStation', port: 4 },
        to: { device: 'channelEmulator', port: 4 },
        cable: { type: 'LMR-400', length: 5, loss: 1.2 }
      },
      {
        from: { device: 'channelEmulator', port: 1 },
        to: { device: 'dut', port: 1 },
        cable: { type: 'RG-58', length: 2, loss: 0.5 }
      },
      {
        from: { device: 'channelEmulator', port: 2 },
        to: { device: 'dut', port: 2 },
        cable: { type: 'RG-58', length: 2, loss: 0.5 }
      },
      {
        from: { device: 'channelEmulator', port: 3 },
        to: { device: 'dut', port: 3 },
        cable: { type: 'RG-58', length: 2, loss: 0.5 }
      },
      {
        from: { device: 'channelEmulator', port: 4 },
        to: { device: 'dut', port: 4 },
        cable: { type: 'RG-58', length: 2, loss: 0.5 }
      }
    ]
  }
];

// 导出用于localStorage的key
export const STORAGE_KEYS = {
  SCENARIOS: 'mock-db-scenarios-v1',
  TOPOLOGIES: 'mock-db-topologies-v1',
  EXECUTIONS: 'mock-db-executions-v1'
};
```

#### Step 2: 扩展API服务

编辑 `gui/src/api/service.ts`，添加新的API函数：

```typescript
// gui/src/api/service.ts (新增部分)

import { RoadTestScenario } from '../types/roadTest/scenario';
import { NetworkTopology } from '../types/roadTest/topology';
import { TestConfig, ExecutionHandle, TestStatus } from '../types/roadTest/execution';
import { TestMetrics } from '../types/roadTest/metrics';

// ========== 场景API ==========

export async function fetchScenarios(params?: {
  category?: string;
  source?: 'standard' | 'custom';
  tags?: string[];
}): Promise<RoadTestScenario[]> {
  const response = await client.get('/api/v1/road-test/scenarios', { params });
  return response.data;
}

export async function fetchScenarioDetail(id: string): Promise<RoadTestScenario> {
  const response = await client.get(`/api/v1/road-test/scenarios/${id}`);
  return response.data;
}

export async function createScenario(
  payload: Omit<RoadTestScenario, 'id'>
): Promise<RoadTestScenario> {
  const response = await client.post('/api/v1/road-test/scenarios', payload);
  return response.data;
}

export async function updateScenario(
  id: string,
  payload: Partial<RoadTestScenario>
): Promise<RoadTestScenario> {
  const response = await client.put(`/api/v1/road-test/scenarios/${id}`, payload);
  return response.data;
}

export async function deleteScenario(id: string): Promise<void> {
  await client.delete(`/api/v1/road-test/scenarios/${id}`);
}

// ========== 拓扑API ==========

export async function fetchTopologies(): Promise<NetworkTopology[]> {
  const response = await client.get('/api/v1/road-test/topologies');
  return response.data;
}

export async function fetchTopologyDetail(id: string): Promise<NetworkTopology> {
  const response = await client.get(`/api/v1/road-test/topologies/${id}`);
  return response.data;
}

export async function createTopology(
  payload: Omit<NetworkTopology, 'id'>
): Promise<NetworkTopology> {
  const response = await client.post('/api/v1/road-test/topologies', payload);
  return response.data;
}

export async function validateTopology(topology: NetworkTopology): Promise<{
  valid: boolean;
  errors: string[];
  warnings: string[];
}> {
  const response = await client.post(
    `/api/v1/road-test/topologies/${topology.id}/validate`,
    topology
  );
  return response.data;
}

// ========== 执行API ==========

export async function createExecution(config: TestConfig): Promise<ExecutionHandle> {
  const response = await client.post('/api/v1/road-test/executions', config);
  return response.data;
}

export async function fetchExecutionStatus(id: string): Promise<{
  executionId: string;
  status: TestStatus;
  progress: number;
  message?: string;
}> {
  const response = await client.get(`/api/v1/road-test/executions/${id}`);
  return response.data;
}

export async function controlExecution(
  id: string,
  action: 'pause' | 'resume' | 'stop'
): Promise<void> {
  await client.post(`/api/v1/road-test/executions/${id}/control`, { action });
}

export async function fetchExecutionMetrics(id: string): Promise<TestMetrics> {
  const response = await client.get(`/api/v1/road-test/executions/${id}/metrics`);
  return response.data;
}

export async function stopExecution(id: string): Promise<void> {
  await client.delete(`/api/v1/road-test/executions/${id}`);
}
```

#### Step 3: 扩展Mock服务器

编辑 `gui/src/api/mockServer.ts`，添加Mock端点处理：

```typescript
// gui/src/api/mockServer.ts (新增部分)

import MockAdapter from 'axios-mock-adapter';
import { mockScenarios, mockTopologies, STORAGE_KEYS } from './mockDatabase';
import { v4 as uuidv4 } from 'uuid';

// ... 现有代码 ...

// ========== 场景API Mock ==========

mock.onGet('/api/v1/road-test/scenarios').reply((config) => {
  const { category, source } = config.params || {};

  let filtered = [...mockScenarios];

  if (category) {
    filtered = filtered.filter(s => s.category === category);
  }

  if (source) {
    filtered = filtered.filter(s => s.source === source);
  }

  return [200, filtered];
});

mock.onGet(/\/api\/v1\/road-test\/scenarios\/(.+)/).reply((config) => {
  const id = config.url!.match(/\/api\/v1\/road-test\/scenarios\/(.+)/)![1];
  const scenario = mockScenarios.find(s => s.id === id);

  if (!scenario) {
    return [404, { error: 'Scenario not found' }];
  }

  return [200, scenario];
});

mock.onPost('/api/v1/road-test/scenarios').reply((config) => {
  const payload = JSON.parse(config.data);
  const newScenario = {
    ...payload,
    id: `custom-${uuidv4()}`,
    source: 'custom'
  };

  mockScenarios.push(newScenario);

  return [201, newScenario];
});

// ========== 拓扑API Mock ==========

mock.onGet('/api/v1/road-test/topologies').reply(() => {
  return [200, mockTopologies];
});

mock.onPost('/api/v1/road-test/topologies').reply((config) => {
  const payload = JSON.parse(config.data);
  const newTopology = {
    ...payload,
    id: `topo-${uuidv4()}`
  };

  mockTopologies.push(newTopology);

  return [201, newTopology];
});

mock.onPost(/\/api\/v1\/road-test\/topologies\/(.+)\/validate/).reply((config) => {
  // 简单验证逻辑
  const topology = JSON.parse(config.data);
  const errors: string[] = [];
  const warnings: string[] = [];

  // 检查端口数量匹配
  if (topology.baseStation.txPorts.length !== topology.channelEmulator.inputMapping.length) {
    errors.push('基站TX端口数量与信道仿真器输入端口不匹配');
  }

  // 检查连接完整性
  const expectedConnections = topology.baseStation.txPorts.length * 2; // BSE->CE + CE->DUT
  if (topology.connections.length !== expectedConnections) {
    warnings.push(`预期${expectedConnections}个连接，实际${topology.connections.length}个`);
  }

  return [200, {
    valid: errors.length === 0,
    errors,
    warnings
  }];
});

// ========== 执行API Mock ==========

const mockExecutions = new Map<string, any>();

mock.onPost('/api/v1/road-test/executions').reply((config) => {
  const testConfig = JSON.parse(config.data);
  const executionId = `exec-${uuidv4()}`;

  const execution = {
    executionId,
    mode: testConfig.mode,
    status: 'running',
    startTime: new Date().toISOString(),
    config: testConfig,
    metrics: {
      throughput: { downlink: 0, uplink: 0 },
      latency: { average: 0, p50: 0, p95: 0, p99: 0 },
      signalQuality: { rsrp: [], rsrq: [], sinr: [] },
      linkQuality: { bler: 0, mcs: 0, cqi: 0 }
    }
  };

  mockExecutions.set(executionId, execution);

  // 模拟测试运行：定期更新指标
  const interval = setInterval(() => {
    const exec = mockExecutions.get(executionId);
    if (!exec || exec.status !== 'running') {
      clearInterval(interval);
      return;
    }

    // 生成随机指标
    exec.metrics = {
      throughput: {
        downlink: 50 + Math.random() * 50,
        uplink: 10 + Math.random() * 20
      },
      latency: {
        average: 10 + Math.random() * 10,
        p50: 8 + Math.random() * 5,
        p95: 15 + Math.random() * 10,
        p99: 20 + Math.random() * 15
      },
      signalQuality: {
        rsrp: [-80 + Math.random() * 10, -80 + Math.random() * 10],
        rsrq: [-10 + Math.random() * 5, -10 + Math.random() * 5],
        sinr: [15 + Math.random() * 10, 15 + Math.random() * 10]
      },
      linkQuality: {
        bler: Math.random() * 2,
        mcs: Math.floor(Math.random() * 28),
        cqi: Math.floor(Math.random() * 15)
      }
    };
  }, 1000);

  return [201, {
    executionId,
    mode: testConfig.mode,
    status: 'running',
    startTime: execution.startTime
  }];
});

mock.onGet(/\/api\/v1\/road-test\/executions\/(.+)\/metrics/).reply((config) => {
  const id = config.url!.match(/\/api\/v1\/road-test\/executions\/(.+)\/metrics/)![1];
  const execution = mockExecutions.get(id);

  if (!execution) {
    return [404, { error: 'Execution not found' }];
  }

  return [200, {
    timestamp: new Date().toISOString(),
    ...execution.metrics
  }];
});

mock.onPost(/\/api\/v1\/road-test\/executions\/(.+)\/control/).reply((config) => {
  const id = config.url!.match(/\/api\/v1\/road-test\/executions\/(.+)\/control/)![1];
  const { action } = JSON.parse(config.data);
  const execution = mockExecutions.get(id);

  if (!execution) {
    return [404, { error: 'Execution not found' }];
  }

  switch (action) {
    case 'pause':
      execution.status = 'paused';
      break;
    case 'resume':
      execution.status = 'running';
      break;
    case 'stop':
      execution.status = 'stopped';
      break;
  }

  return [200, { status: execution.status }];
});
```

### 3.3 第3-4周：前端组件开发

#### 组件1: ModeSelector

创建 `gui/src/components/VirtualRoadTest/ModeSelector.tsx`:

```typescript
// gui/src/components/VirtualRoadTest/ModeSelector.tsx

import React, { useState } from 'react';
import {
  Stack,
  Title,
  Grid,
  Card,
  Text,
  ThemeIcon,
  List,
  Badge,
  Button,
  Table
} from '@mantine/core';
import {
  IconCpu,
  IconPlugConnected,
  IconRadar2,
  IconCheck
} from '@tabler/icons-react';
import { TestMode } from '../../types/roadTest/execution';

interface ModeSelectorProps {
  onModeSelected: (mode: TestMode) => void;
}

export const ModeSelector: React.FC<ModeSelectorProps> = ({ onModeSelected }) => {
  const [selectedMode, setSelectedMode] = useState<TestMode>();

  const handleSelectMode = (mode: TestMode) => {
    setSelectedMode(mode);
  };

  const handleNext = () => {
    if (selectedMode) {
      onModeSelected(selectedMode);
    }
  };

  return (
    <Stack spacing="xl">
      <Title order={2}>选择测试模式</Title>

      <Grid>
        {/* 模式1: 数字孪生 */}
        <Grid.Col span={4}>
          <Card
            shadow="sm"
            padding="lg"
            withBorder
            onClick={() => handleSelectMode(TestMode.DIGITAL_TWIN)}
            style={{
              cursor: 'pointer',
              border: selectedMode === TestMode.DIGITAL_TWIN
                ? '2px solid var(--mantine-color-blue-6)'
                : undefined
            }}
          >
            <ThemeIcon size="xl" variant="light" color="blue" mb="md">
              <IconCpu size={32} />
            </ThemeIcon>

            <Text weight={600} size="lg">全数字仿真</Text>
            <Text size="sm" color="dimmed" mt="xs">
              数字孪生，纯软件仿真<br />
              成本最低，速度最快<br />
              适合早期研发验证
            </Text>

            <List mt="md" size="sm" spacing="xs" icon={<IconCheck size={16} color="green" />}>
              <List.Item>无需硬件设备</List.Item>
              <List.Item>支持极端场景</List.Item>
              <List.Item>快速迭代 (10x)</List.Item>
            </List>

            <Badge mt="md" color="blue">仿真精度: 中</Badge>
          </Card>
        </Grid.Col>

        {/* 模式2: 传导测试 */}
        <Grid.Col span={4}>
          <Card
            shadow="sm"
            padding="lg"
            withBorder
            onClick={() => handleSelectMode(TestMode.CONDUCTED)}
            style={{
              cursor: 'pointer',
              border: selectedMode === TestMode.CONDUCTED
                ? '2px solid var(--mantine-color-green-6)'
                : undefined
            }}
          >
            <ThemeIcon size="xl" variant="light" color="green" mb="md">
              <IconPlugConnected size={32} />
            </ThemeIcon>

            <Text weight={600} size="lg">传导测试</Text>
            <Text size="sm" color="dimmed" mt="xs">
              仪表-DUT射频直连<br />
              成本中等，精度较高<br />
              适合功能验证和调试
            </Text>

            <List mt="md" size="sm" spacing="xs" icon={<IconCheck size={16} color="green" />}>
              <List.Item>真实RF链路</List.Item>
              <List.Item>隔离干扰</List.Item>
              <List.Item>快速定位问题</List.Item>
            </List>

            <Badge mt="md" color="green">测试精度: 高</Badge>
          </Card>
        </Grid.Col>

        {/* 模式3: OTA测试 */}
        <Grid.Col span={4}>
          <Card
            shadow="sm"
            padding="lg"
            withBorder
            onClick={() => handleSelectMode(TestMode.OTA)}
            style={{
              cursor: 'pointer',
              border: selectedMode === TestMode.OTA
                ? '2px solid var(--mantine-color-orange-6)'
                : undefined
            }}
          >
            <ThemeIcon size="xl" variant="light" color="orange" mb="md">
              <IconRadar2 size={32} />
            </ThemeIcon>

            <Text weight={600} size="lg">OTA辐射测试</Text>
            <Text size="sm" color="dimmed" mt="xs">
              MPAC暗室空中辐射<br />
              成本最高，精度最高<br />
              适合最终认证测试
            </Text>

            <List mt="md" size="sm" spacing="xs" icon={<IconCheck size={16} color="green" />}>
              <List.Item>完整RF链路</List.Item>
              <List.Item>天线真实辐射</List.Item>
              <List.Item>认证级别</List.Item>
            </List>

            <Badge mt="md" color="orange">测试精度: 最高</Badge>
          </Card>
        </Grid.Col>
      </Grid>

      {/* 对比表 */}
      <Table mt="xl">
        <thead>
          <tr>
            <th>对比维度</th>
            <th>全数字仿真</th>
            <th>传导测试</th>
            <th>OTA测试</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>成本</td>
            <td><Badge color="green">低</Badge></td>
            <td><Badge color="yellow">中</Badge></td>
            <td><Badge color="red">高</Badge></td>
          </tr>
          <tr>
            <td>测试周期</td>
            <td><Badge color="green">分钟</Badge></td>
            <td><Badge color="yellow">小时</Badge></td>
            <td><Badge color="red">天</Badge></td>
          </tr>
          <tr>
            <td>场景覆盖</td>
            <td><Badge color="green">无限</Badge></td>
            <td><Badge color="yellow">有限</Badge></td>
            <td><Badge color="yellow">有限</Badge></td>
          </tr>
          <tr>
            <td>测试精度</td>
            <td><Badge color="yellow">中</Badge></td>
            <td><Badge color="green">高</Badge></td>
            <td><Badge color="green">最高</Badge></td>
          </tr>
        </tbody>
      </Table>

      <Button
        mt="xl"
        size="lg"
        disabled={!selectedMode}
        onClick={handleNext}
      >
        下一步：选择测试场景
      </Button>
    </Stack>
  );
};
```

#### 组件2: ScenarioLibrary

创建 `gui/src/components/VirtualRoadTest/ScenarioLibrary.tsx`:

```typescript
// gui/src/components/VirtualRoadTest/ScenarioLibrary.tsx

import React, { useState } from 'react';
import {
  Stack,
  Title,
  Group,
  Button,
  Tabs,
  TextInput,
  Grid,
  Card,
  Text,
  Badge,
  SimpleGrid
} from '@mantine/core';
import { IconPlus, IconSearch } from '@tabler/icons-react';
import { RoadTestScenario, ScenarioCategory } from '../../types/roadTest/scenario';
import { useScenarios } from '../../hooks/useScenarios';

interface ScenarioLibraryProps {
  onScenarioSelected: (scenario: RoadTestScenario) => void;
  onCreateScenario: () => void;
}

export const ScenarioLibrary: React.FC<ScenarioLibraryProps> = ({
  onScenarioSelected,
  onCreateScenario
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const { data: scenarios, isLoading } = useScenarios({
    category: selectedCategory !== 'all' ? selectedCategory : undefined
  });

  const filteredScenarios = scenarios?.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <Stack spacing="md">
      <Group position="apart">
        <Title order={2}>路测场景库</Title>
        <Button leftIcon={<IconPlus />} onClick={onCreateScenario}>
          创建自定义场景
        </Button>
      </Group>

      {/* 分类筛选 */}
      <Tabs value={selectedCategory} onChange={setSelectedCategory}>
        <Tabs.List>
          <Tabs.Tab value="all">全部场景</Tabs.Tab>
          <Tabs.Tab value="standard">标准场景</Tabs.Tab>
          <Tabs.Tab value="functional">功能场景</Tabs.Tab>
          <Tabs.Tab value="performance">性能场景</Tabs.Tab>
          <Tabs.Tab value="environment">环境场景</Tabs.Tab>
          <Tabs.Tab value="extreme">极端场景</Tabs.Tab>
          <Tabs.Tab value="custom">自定义场景</Tabs.Tab>
        </Tabs.List>
      </Tabs>

      {/* 搜索框 */}
      <TextInput
        placeholder="搜索场景名称、标签..."
        icon={<IconSearch size={16} />}
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
      />

      {/* 场景网格 */}
      {isLoading ? (
        <Text>加载中...</Text>
      ) : (
        <Grid>
          {filteredScenarios?.map(scenario => (
            <Grid.Col key={scenario.id} span={4}>
              <ScenarioCard
                scenario={scenario}
                onSelect={() => onScenarioSelected(scenario)}
              />
            </Grid.Col>
          ))}
        </Grid>
      )}
    </Stack>
  );
};

// 场景卡片组件
interface ScenarioCardProps {
  scenario: RoadTestScenario;
  onSelect: () => void;
}

const ScenarioCard: React.FC<ScenarioCardProps> = ({ scenario, onSelect }) => {
  const getCategoryColor = (category: ScenarioCategory): string => {
    const colorMap: Record<string, string> = {
      [ScenarioCategory.STANDARD_3GPP]: 'blue',
      [ScenarioCategory.FUNCTIONAL_HANDOVER]: 'green',
      [ScenarioCategory.PERFORMANCE_THROUGHPUT]: 'orange',
      [ScenarioCategory.ENV_URBAN_CANYON]: 'purple',
      [ScenarioCategory.CUSTOM]: 'gray'
    };
    return colorMap[category] || 'gray';
  };

  return (
    <Card shadow="sm" padding="lg" withBorder>
      <Group position="apart" mb="xs">
        <Text weight={600}>{scenario.name}</Text>
        <Badge color={getCategoryColor(scenario.category)}>
          {scenario.category}
        </Badge>
      </Group>

      <Text size="sm" color="dimmed" lineClamp={2}>
        {scenario.description}
      </Text>

      <SimpleGrid cols={2} mt="md" spacing="xs">
        <div>
          <Text size="xs" color="dimmed">网络</Text>
          <Text size="sm" weight={500}>{scenario.network.type}</Text>
        </div>
        <div>
          <Text size="xs" color="dimmed">环境</Text>
          <Text size="sm" weight={500}>{scenario.environment.type}</Text>
        </div>
        <div>
          <Text size="xs" color="dimmed">时长</Text>
          <Text size="sm" weight={500}>{scenario.route.duration}s</Text>
        </div>
        <div>
          <Text size="xs" color="dimmed">距离</Text>
          <Text size="sm" weight={500}>{scenario.route.totalDistance}m</Text>
        </div>
      </SimpleGrid>

      <Group mt="md" spacing="xs">
        {scenario.tags.map(tag => (
          <Badge key={tag} size="xs" variant="outline">{tag}</Badge>
        ))}
      </Group>

      <Button fullWidth mt="md" onClick={onSelect}>
        选择场景
      </Button>
    </Card>
  );
};
```

#### 组件3: React Hooks

创建 `gui/src/hooks/useScenarios.ts`:

```typescript
// gui/src/hooks/useScenarios.ts

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchScenarios,
  fetchScenarioDetail,
  createScenario,
  updateScenario,
  deleteScenario
} from '../api/service';
import { RoadTestScenario } from '../types/roadTest/scenario';

export function useScenarios(params?: {
  category?: string;
  source?: 'standard' | 'custom';
}) {
  return useQuery({
    queryKey: ['scenarios', params],
    queryFn: () => fetchScenarios(params)
  });
}

export function useScenarioDetail(id: string) {
  return useQuery({
    queryKey: ['scenario', id],
    queryFn: () => fetchScenarioDetail(id),
    enabled: !!id
  });
}

export function useCreateScenario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: Omit<RoadTestScenario, 'id'>) => createScenario(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] });
    }
  });
}

export function useUpdateScenario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<RoadTestScenario> }) =>
      updateScenario(id, payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] });
      queryClient.invalidateQueries({ queryKey: ['scenario', variables.id] });
    }
  });
}

export function useDeleteScenario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteScenario(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] });
    }
  });
}
```

---

## 4. 测试策略

### 4.1 单元测试

```typescript
// gui/test/roadTest/ITestExecutor.test.ts

import { describe, it, expect, beforeEach } from 'vitest';
import { MockDigitalTwinExecutor } from '../mocks/MockDigitalTwinExecutor';
import { TestMode, TestStatus } from '../../src/types/roadTest/execution';

describe('ITestExecutor Interface', () => {
  let executor: MockDigitalTwinExecutor;

  beforeEach(() => {
    executor = new MockDigitalTwinExecutor();
  });

  it('should initialize successfully', async () => {
    const config = {
      mode: TestMode.DIGITAL_TWIN,
      scenario: mockScenario,
      dut: mockDUT,
      kpi: []
    };

    const result = await executor.initialize(config);

    expect(result.success).toBe(true);
    expect(result.mode).toBe(TestMode.DIGITAL_TWIN);
  });

  it('should execute and return handle', async () => {
    await executor.initialize(mockConfig);
    const handle = await executor.execute();

    expect(handle.executionId).toBeDefined();
    expect(handle.status).toBe(TestStatus.RUNNING);
  });

  it('should pause and resume', async () => {
    await executor.initialize(mockConfig);
    await executor.execute();

    await executor.pause();
    const status1 = await executor.queryStatus();
    expect(status1).toBe(TestStatus.PAUSED);

    await executor.resume();
    const status2 = await executor.queryStatus();
    expect(status2).toBe(TestStatus.RUNNING);
  });
});
```

### 4.2 集成测试

```typescript
// gui/test/roadTest/integration/endToEnd.test.ts

import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useScenarios, useCreateExecution } from '../../src/hooks';

describe('End-to-End Flow', () => {
  it('should complete full test workflow', async () => {
    // 1. 获取场景列表
    const { result: scenariosResult } = renderHook(() => useScenarios());
    await waitFor(() => expect(scenariosResult.current.data).toBeDefined());

    const scenario = scenariosResult.current.data![0];

    // 2. 创建执行
    const { result: executionResult } = renderHook(() => useCreateExecution());
    const config = {
      mode: TestMode.DIGITAL_TWIN,
      scenario,
      dut: mockDUT,
      kpi: []
    };

    executionResult.current.mutate(config);
    await waitFor(() => expect(executionResult.current.data).toBeDefined());

    expect(executionResult.current.data!.executionId).toBeDefined();
  });
});
```

---

## 5. 部署指南

### 5.1 开发环境

```bash
# 启动开发服务器
cd gui
npm run dev

# 在浏览器中访问
# http://localhost:5173
```

### 5.2 生产构建

```bash
# 构建前端
cd gui
npm run build

# 输出目录: gui/dist/
```

### 5.3 Docker部署（可选）

```dockerfile
# Dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY gui/package*.json ./
RUN npm ci

COPY gui/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

```bash
# 构建镜像
docker build -t meta-3d-frontend .

# 运行容器
docker run -p 80:80 meta-3d-frontend
```

---

## 6. 下一步

### Phase 2: OTA模式增强 (3-4周)

1. 实现 `OTAScenarioMapper`
2. 集成现有 `ChannelEmulatorHAL`
3. 开发场景编辑器基础版
4. 添加5个标准场景

### Phase 3: 传导测试模式 (6-8周)

1. 实现 `ConductedExecutor`
2. 开发拓扑配置器
3. 实现基站驱动和DUT驱动
4. 集成测试

### Phase 4: 数字孪生模式 (8-12周)

1. 选择仿真引擎（推荐ns-3）
2. 实现 `DigitalTwinExecutor`
3. 开发3D可视化
4. 性能优化

---

## 7. 常见问题

### Q1: 如何添加新的场景？

A: 在 `gui/src/data/scenarioLibrary.ts` 中添加新的场景定义，或使用场景编辑器UI创建。

### Q2: 如何扩展新的测试模式？

A: 实现 `ITestExecutor` 接口，并在 `TestExecutionEngine` 中注册新模式。

### Q3: 如何集成真实仪表驱动？

A: 实现对应的Driver接口（如 `IBaseStationDriver`），替换Mock实现。

---

**文档结束**

相关文档:
- [VirtualRoadTest.md](./VirtualRoadTest.md)
- [VirtualRoadTest-Architecture.md](./VirtualRoadTest-Architecture.md)
