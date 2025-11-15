/**
 * 虚拟路测 - 场景数据模型
 *
 * 定义路测场景的完整业务语义
 * 场景层是业务抽象层，独立于具体测试模式
 */

import { ScenarioCategory } from './index'

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
  source: 'standard' | 'custom'
  tags: string[]

  // 元数据
  metadata: {
    version: string
    createdAt: string
    updatedAt: string
    author?: string
    organization?: string
    standard?: string         // 例如: '3GPP TS 38.101-1 Section 7.3.2'
  }

  // 业务语义定义
  networkConfig: NetworkConfig
  trajectory: PathTrajectory
  environment: EnvironmentConditions
  traffic: TrafficModel
  triggers?: TriggerEvent[]
  kpiTargets: KPIDefinition[]

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
  source: 'standard' | 'custom'
  tags: string[]

  // 关键参数摘要（用于快速预览）
  summary: {
    networkType: NetworkType
    environmentType: EnvironmentType
    duration: number          // 秒
    avgSpeed: number          // km/h
    numBaseStations: number
    kpiCount: number
  }

  createdAt: string
}
