/**
 * 虚拟路测 - 场景数据模型
 *
 * 定义路测场景的完整业务语义
 * 场景层是业务抽象层，独立于具体测试模式
 *
 * 设计原则：
 * 1. 虚拟路测关注真实道路场景，不是标准符合性测试
 * 2. 场景为原子单元（All-in-One），所有参数形成整体
 * 3. 支持射线跟踪工具生成的场景导入
 * 4. 多维度标签分类体系
 */

import { ScenarioCategory } from './index'

// ========== 场景分类（多维度标签体系）==========

export interface ScenarioTaxonomy {
  // 维度1: 来源类型
  source: 'real-world' | 'synthetic' | 'standard-derived'

  // 维度2: 地理特征
  geography: {
    region: string        // 例如: "北京CBD", "京沪高速G2"
    type: 'urban' | 'suburban' | 'highway' | 'tunnel' | 'indoor' | 'rural'
  }

  // 维度3: 测试目的
  purpose: 'coverage' | 'handover' | 'throughput' | 'latency' | 'mobility' | 'reliability' | 'interference'

  // 维度4: 网络类型 (在NetworkConfig中也有定义，这里用于快速筛选)
  network: 'LTE' | '5G NR FR1' | '5G NR FR2' | 'C-V2X' | 'Hybrid'

  // 维度5: 复杂度
  complexity: 'basic' | 'intermediate' | 'advanced' | 'extreme'

  // 自由标签
  tags: string[]  // 例如: ["早高峰", "密集建筑", "高速移动", "干扰"]
}

// ========== 场景来源与射线跟踪 ==========

export interface ScenarioOrigin {
  type: 'real-world' | 'synthetic' | 'customer-requested'

  // 真实场景信息
  realWorld?: {
    location: string              // 例如: "北京市朝阳区CBD"
    coordinates?: {
      latitude: number
      longitude: number
    }
    captureDate?: string          // 场景数据采集日期
    dataSources?: string[]        // 例如: ["GIS", "Street View", "LiDAR"]
  }

  // 射线跟踪生成信息
  rayTracing?: {
    tool: 'WirelessInSite' | 'WinProp' | 'CloudRT' | 'Custom'
    version: string
    environmentModel: string      // 环境模型文件引用
    configFile?: string           // 射线跟踪配置文件
    generatedBy?: string          // 创建人员
    generatedAt: string
  }

  // 客户定制场景
  customerRequest?: {
    customer: string
    project: string
    requirements: string
    deliveryDate?: string
  }
}

export interface RayTracingOutput {
  tool: 'WirelessInSite' | 'WinProp' | 'CloudRT' | 'Custom'
  version: string

  // 结果文件路径或URL
  resultFiles: {
    pathLossMatrix?: string       // 路径损耗矩阵文件
    channelCoefficients?: string  // 信道系数文件
    dopplerProfile?: string       // 多普勒谱文件
    powerDelayProfile?: string    // 功率时延谱文件
    angleOfArrival?: string       // 到达角数据
    angleOfDeparture?: string     // 离开角数据
  }

  // 统计信息（从射线跟踪结果提取）
  statistics?: {
    averagePathLoss: number       // 平均路径损耗 (dB)
    shadowingStdDev: number       // 阴影衰落标准差 (dB)
    rmsDelaySpread: number        // RMS时延扩展 (ns)
    dominantPathDelay: number     // 主径时延 (ns)
  }

  // 执行信息
  execution: {
    computeTime: number           // 计算时间 (秒)
    rayCount: number              // 跟踪的射线数量
    reflectionOrder: number       // 反射阶数
    diffractionOrder: number      // 绕射阶数
  }
}

// ========== 场景完整性与验证 ==========

export interface ScenarioIntegrity {
  // 数据完整性
  dataCompleteness: {
    hasNetwork: boolean           // 网络配置完整
    hasTrajectory: boolean        // 轨迹定义完整
    hasEnvironment: boolean       // 环境条件完整
    hasTraffic: boolean          // 流量模型完整
    hasKPI: boolean              // KPI定义完整
  }

  // 验证状态
  validation: {
    isValidated: boolean          // 已通过验证
    validatedBy?: string          // 验证人员
    validatedAt?: string          // 验证时间
    validationNotes?: string      // 验证备注
  }

  // 可执行性
  executability: {
    canExecuteOTA: boolean        // 可在OTA模式执行
    canExecuteConducted: boolean  // 可在传导模式执行
    canExecuteDigitalTwin: boolean // 可在数字孪生模式执行

    blockers?: string[]           // 阻塞问题列表
  }
}

// ========== 网络配置 ==========

export enum NetworkType {
  LTE = 'LTE',
  NR_FR1 = '5G NR FR1',
  NR_FR2 = '5G NR FR2',
  C_V2X = 'C-V2X',
  HYBRID = 'Hybrid'
}

export enum DuplexMode {
  FDD = 'FDD',
  TDD = 'TDD'
}

export interface BaseStationConfig {
  id: string
  name: string
  position: {
    x: number  // 米
    y: number  // 米
    z: number  // 米（高度）
  }
  antennaConfig: {
    txAntennas: number  // 发射天线数
    rxAntennas: number  // 接收天线数
    gain: number        // dBi
    beamforming: boolean
  }
  power: {
    txPower: number     // dBm
    maxEIRP: number     // dBm
  }
}

export interface NetworkConfig {
  networkType: NetworkType
  duplexMode: DuplexMode

  // 频率配置
  frequency: {
    dl: number          // 下行中心频率 (MHz)
    ul: number          // 上行中心频率 (MHz)
  }

  // 带宽配置
  bandwidth: {
    dl: number          // 下行带宽 (MHz)
    ul: number          // 上行带宽 (MHz)
  }

  // 基站配置
  baseStations: BaseStationConfig[]

  // 切换配置
  handover?: {
    enabled: boolean
    algorithm: 'A3' | 'A5' | 'custom'
    hysteresis: number  // dB
    timeToTrigger: number  // ms
  }
}

// ========== 路径轨迹 ==========

export interface Waypoint {
  timestamp: number   // 秒
  position: {
    x: number         // 米
    y: number         // 米
    z: number         // 米（高度）
  }
  velocity: {
    speed: number     // km/h
    heading: number   // 度 (0-360)
  }
  orientation?: {
    roll: number      // 度
    pitch: number     // 度
    yaw: number       // 度
  }
}

export enum PathType {
  LINEAR = 'linear',           // 直线
  CIRCULAR = 'circular',       // 环形
  FIGURE_8 = 'figure-8',      // 8字形
  URBAN_GRID = 'urban-grid',  // 城市网格
  HIGHWAY = 'highway',         // 高速公路
  CUSTOM = 'custom'            // 自定义
}

export interface PathTrajectory {
  type: PathType
  duration: number              // 总时长 (秒)
  waypoints: Waypoint[]

  // 轨迹统计信息
  stats: {
    totalDistance: number       // 总距离 (米)
    avgSpeed: number            // 平均速度 (km/h)
    maxSpeed: number            // 最大速度 (km/h)
    minSpeed: number            // 最小速度 (km/h)
  }
}

// ========== 环境条件 ==========

export enum EnvironmentType {
  URBAN_MACRO = 'Urban Macro',
  URBAN_MICRO = 'Urban Micro',
  SUBURBAN = 'Suburban',
  RURAL = 'Rural',
  HIGHWAY = 'Highway',
  INDOOR = 'Indoor',
  TUNNEL = 'Tunnel',
  CANYON = 'Urban Canyon'
}

export enum ChannelModel {
  // 3GPP标准模型
  CDL_A = '3GPP CDL-A',  // NLOS
  CDL_B = '3GPP CDL-B',  // NLOS
  CDL_C = '3GPP CDL-C',  // NLOS
  CDL_D = '3GPP CDL-D',  // LOS
  CDL_E = '3GPP CDL-E',  // LOS
  TDL_A = '3GPP TDL-A',
  TDL_B = '3GPP TDL-B',
  TDL_C = '3GPP TDL-C',

  // WINNER模型
  WINNER_B1 = 'WINNER B1',
  WINNER_C2 = 'WINNER C2',

  // 自定义
  CUSTOM = 'Custom'
}

export interface EnvironmentConditions {
  type: EnvironmentType
  channelModel: ChannelModel

  // 传播特性
  propagation: {
    pathLoss: {
      model: string         // 例如: 'Free Space', 'Urban Macro (COST231)'
      exponent?: number     // 路径损耗指数
    }
    shadowing: {
      enabled: boolean
      stdDev: number        // 标准差 (dB)
    }
    fastFading: {
      enabled: boolean
      dopplerSpread: number // Hz
    }
  }

  // 环境参数
  weather?: {
    temperature: number     // 摄氏度
    humidity: number        // 百分比
    rainfall?: number       // mm/h
  }

  // 障碍物（可选）
  obstacles?: Array<{
    type: 'building' | 'vehicle' | 'tree' | 'other'
    position: { x: number; y: number; z: number }
    dimensions: { width: number; height: number; depth: number }
    material: string        // 例如: 'concrete', 'metal', 'glass'
    attenuation: number     // dB
  }>
}

// ========== 业务流量 ==========

export enum TrafficType {
  FTP = 'FTP',
  HTTP = 'HTTP',
  VIDEO = 'Video Streaming',
  VOIP = 'VoIP',
  GAMING = 'Gaming',
  IPERF = 'iPerf',
  CUSTOM = 'Custom'
}

export enum TrafficDirection {
  DOWNLINK = 'DL',
  UPLINK = 'UL',
  BIDIRECTIONAL = 'Bi-directional'
}

export interface TrafficModel {
  type: TrafficType
  direction: TrafficDirection

  // 速率配置
  dataRate: {
    target: number          // Mbps
    min?: number            // Mbps
    max?: number            // Mbps
  }

  // 流量模式
  pattern: {
    mode: 'continuous' | 'burst' | 'periodic'
    burstSize?: number      // KB
    period?: number         // ms
    dutyCycle?: number      // 百分比
  }

  // QoS参数
  qos?: {
    priority: number        // 1-9
    latency: number         // ms
    packetLoss: number      // 百分比
    jitter?: number         // ms
  }
}

// ========== 触发事件 ==========

export enum TriggerType {
  HANDOVER = 'Handover',
  BEAM_SWITCH = 'Beam Switch',
  CARRIER_AGGREGATION = 'Carrier Aggregation',
  INTERFERENCE = 'Interference',
  POWER_CHANGE = 'Power Change',
  LOCATION = 'Location',
  TIME = 'Time'
}

export interface TriggerEvent {
  id: string
  type: TriggerType
  timestamp: number           // 触发时间点 (秒)

  // 触发条件
  condition: {
    parameter: string         // 例如: 'RSRP', 'SINR', 'position'
    operator: '>' | '<' | '=' | '>=' | '<='
    threshold: number
    unit: string              // 例如: 'dBm', 'dB', 'meters'
  }

  // 触发动作
  action: {
    type: string              // 例如: 'start_handover', 'switch_beam'
    parameters: Record<string, any>
  }

  description?: string
}

// ========== KPI定义 ==========

export enum KPIMetric {
  THROUGHPUT_DL = 'Throughput (DL)',
  THROUGHPUT_UL = 'Throughput (UL)',
  LATENCY = 'Latency',
  BLER = 'BLER',
  RSRP = 'RSRP',
  RSRQ = 'RSRQ',
  SINR = 'SINR',
  HANDOVER_SUCCESS_RATE = 'Handover Success Rate',
  HANDOVER_LATENCY = 'Handover Latency',
  COVERAGE = 'Coverage',
  PACKET_LOSS = 'Packet Loss',
  CUSTOM = 'Custom'
}

export interface KPIDefinition {
  metric: KPIMetric

  // 目标值
  target: {
    value: number
    unit: string              // 例如: 'Mbps', 'ms', '%', 'dBm'
    operator: '>' | '<' | '>=' | '<=' | '='
  }

  // 采样配置
  sampling: {
    interval: number          // 采样间隔 (ms)
    aggregation: 'mean' | 'min' | 'max' | 'p50' | 'p90' | 'p95' | 'p99'
  }

  // 通过标准
  passCriteria: {
    threshold: number
    percentile?: number       // 百分比 (例如: 95% 的样本需要满足)
  }

  description?: string
}

// ========== 完整场景定义 ==========

export interface RoadTestScenarioDetail {
  // 基础信息
  id: string
  name: string
  description: string
  category: ScenarioCategory

  // 场景分类（多维度标签）
  taxonomy: ScenarioTaxonomy

  // 场景来源
  origin: ScenarioOrigin

  // 元数据
  metadata: {
    version: string
    createdAt: string
    updatedAt: string
    author?: string
    organization?: string
  }

  // 业务语义定义（原子场景 - 所有参数形成整体）
  networkConfig: NetworkConfig
  trajectory: PathTrajectory
  environment: EnvironmentConditions
  traffic: TrafficModel
  triggers?: TriggerEvent[]
  kpiTargets: KPIDefinition[]

  // 射线跟踪输出（如果场景由射线跟踪生成）
  rayTracingOutput?: RayTracingOutput

  // 场景完整性与验证
  integrity: ScenarioIntegrity

  // 附加信息
  notes?: string
  references?: Array<{
    title: string
    url?: string
    document?: string
  }>
}

// ========== 场景简化视图（用于列表展示）==========

export interface RoadTestScenario {
  id: string
  name: string
  description: string
  category: ScenarioCategory

  // 分类摘要（用于筛选和排序）
  taxonomy: {
    source: 'real-world' | 'synthetic' | 'standard-derived'
    geographyType: 'urban' | 'suburban' | 'highway' | 'tunnel' | 'indoor' | 'rural'
    region: string            // 例如: "北京CBD"
    purpose: string           // 例如: "throughput"
    network: string           // 例如: "5G NR FR1"
    complexity: 'basic' | 'intermediate' | 'advanced' | 'extreme'
    tags: string[]
  }

  // 关键参数摘要（用于快速预览）
  summary: {
    networkType: NetworkType
    environmentType: EnvironmentType
    duration: number          // 秒
    avgSpeed: number          // km/h
    numBaseStations: number
    kpiCount: number
  }

  // 完整性标记
  isComplete: boolean         // 数据完整
  isValidated: boolean        // 已验证
  canExecute: {
    ota: boolean
    conducted: boolean
    digitalTwin: boolean
  }

  createdAt: string
}
