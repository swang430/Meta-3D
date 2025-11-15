/**
 * 虚拟路测场景库 - 场景6-10
 */

import type {
  RoadTestScenarioDetail,
} from '../../types/roadTest'

import {
  ScenarioCategory,
  NetworkType,
  DuplexMode,
  PathType,
  EnvironmentType,
  ChannelModel,
  TrafficType,
  TrafficDirection,
  KPIMetric,
} from '../../types/roadTest'

// ========== 场景6: 室内停车场 ==========

export const scenario_indoor_parking: RoadTestScenarioDetail = {
  id: 'scenario-006',
  name: '室内停车场穿透测试',
  description: '地下停车场环境，测试室内穿透损耗和弱信号场景下的连接保持能力',
  category: ScenarioCategory.ENVIRONMENT,

  taxonomy: {
    source: 'synthetic',
    geography: {
      region: '典型商业综合体地下停车场',
      type: 'indoor',
    },
    purpose: 'coverage',
    network: 'LTE',
    complexity: 'intermediate',
    tags: ['室内', '穿透', '弱信号', '停车场'],
  },

  origin: {
    type: 'synthetic',
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-07-10T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.LTE,
    duplexMode: DuplexMode.FDD,
    frequency: { dl: 2100, ul: 1900 },
    bandwidth: { dl: 20, ul: 20 },
    baseStations: [
      {
        id: 'bs-outdoor',
        name: '室外宏站',
        position: { x: 0, y: -100, z: 30 },
        antennaConfig: { txAntennas: 4, rxAntennas: 2, gain: 14, beamforming: false },
        power: { txPower: 43, maxEIRP: 57 },
      },
    ],
  },

  trajectory: {
    type: PathType.CUSTOM,
    duration: 300,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: -10 }, velocity: { speed: 10, heading: 90 } },
      { timestamp: 100, position: { x: 50, y: 0, z: -10 }, velocity: { speed: 10, heading: 90 } },
      { timestamp: 200, position: { x: 50, y: 50, z: -10 }, velocity: { speed: 10, heading: 180 } },
      { timestamp: 300, position: { x: 100, y: 50, z: -10 }, velocity: { speed: 10, heading: 90 } },
    ],
    stats: {
      totalDistance: 150,
      avgSpeed: 10,
      maxSpeed: 10,
      minSpeed: 10,
    },
  },

  environment: {
    type: EnvironmentType.INDOOR,
    channelModel: ChannelModel.TDL_C,
    propagation: {
      pathLoss: { model: 'Indoor Hotspot (3GPP TR 38.901)', exponent: 4.2 },
      shadowing: { enabled: true, stdDev: 10 },
      fastFading: { enabled: true, dopplerSpread: 5.5 },
    },
    obstacles: [
      {
        type: 'building',
        position: { x: 0, y: 0, z: -5 },
        dimensions: { width: 200, height: 3, depth: 200 },
        material: 'concrete',
        attenuation: 18,
      },
    ],
  },

  traffic: {
    type: TrafficType.HTTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 5, min: 1, max: 10 },
    pattern: { mode: 'burst', burstSize: 100, period: 5000 },
  },

  kpiTargets: [
    {
      metric: KPIMetric.RSRP,
      target: { value: -115, unit: 'dBm', operator: '>' },
      sampling: { interval: 500, aggregation: 'mean' },
      passCriteria: { threshold: -115, percentile: 80 },
      description: '室内信号强度',
    },
  ],

  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T13:00:00Z' },
    executability: { canExecuteOTA: true, canExecuteConducted: true, canExecuteDigitalTwin: true },
  },
}

// ========== 场景7: 高速极限测试 ==========

export const scenario_extreme_highspeed: RoadTestScenarioDetail = {
  id: 'scenario-007',
  name: '高速极限移动测试',
  description: '200km/h极限高速场景，测试极端多普勒和快速切换处理能力',
  category: ScenarioCategory.EXTREME,

  taxonomy: {
    source: 'synthetic',
    geography: {
      region: '高速测试跑道',
      type: 'highway',
    },
    purpose: 'mobility',
    network: '5G NR FR1',
    complexity: 'extreme',
    tags: ['极限高速', '200km/h', '极端多普勒', '压力测试'],
  },

  origin: {
    type: 'synthetic',
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-08-01T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 3500, ul: 3500 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: [
      {
        id: 'bs-track-001',
        name: '跑道基站1',
        position: { x: 0, y: 0, z: 40 },
        antennaConfig: { txAntennas: 64, rxAntennas: 32, gain: 18, beamforming: true },
        power: { txPower: 49, maxEIRP: 67 },
      },
      {
        id: 'bs-track-002',
        name: '跑道基站2',
        position: { x: 8000, y: 0, z: 40 },
        antennaConfig: { txAntennas: 64, rxAntennas: 32, gain: 18, beamforming: true },
        power: { txPower: 49, maxEIRP: 67 },
      },
    ],
    handover: { enabled: true, algorithm: 'A3', hysteresis: 1, timeToTrigger: 40 },
  },

  trajectory: {
    type: PathType.LINEAR,
    duration: 240,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 150, heading: 90 } },
      { timestamp: 60, position: { x: 2778, y: 0, z: 1.5 }, velocity: { speed: 200, heading: 90 } },
      { timestamp: 180, position: { x: 9444, y: 0, z: 1.5 }, velocity: { speed: 200, heading: 90 } },
      { timestamp: 240, position: { x: 12778, y: 0, z: 1.5 }, velocity: { speed: 180, heading: 90 } },
    ],
    stats: {
      totalDistance: 12778,
      avgSpeed: 191,
      maxSpeed: 200,
      minSpeed: 150,
    },
  },

  environment: {
    type: EnvironmentType.HIGHWAY,
    channelModel: ChannelModel.TDL_A,
    propagation: {
      pathLoss: { model: 'Free Space', exponent: 2.2 },
      shadowing: { enabled: true, stdDev: 3 },
      fastFading: { enabled: true, dopplerSpread: 648 },
    },
  },

  traffic: {
    type: TrafficType.VIDEO,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 30, min: 10, max: 60 },
    pattern: { mode: 'continuous' },
  },

  kpiTargets: [
    {
      metric: KPIMetric.THROUGHPUT_DL,
      target: { value: 20, unit: 'Mbps', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 20, percentile: 70 },
      description: '极限高速下维持基本吞吐量',
    },
    {
      metric: KPIMetric.HANDOVER_SUCCESS_RATE,
      target: { value: 90, unit: '%', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 90 },
    },
  ],

  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T14:00:00Z' },
    executability: { canExecuteOTA: true, canExecuteConducted: false, canExecuteDigitalTwin: true, blockers: ['传导模式难以模拟极限多普勒'] },
  },

  notes: '极限场景，用于压力测试，多普勒频移高达648Hz',
}

// ========== 场景8: 密集干扰场景 ==========

export const scenario_dense_interference: RoadTestScenarioDetail = {
  id: 'scenario-008',
  name: '密集干扰城区场景',
  description: '高密度基站部署区域，测试同频干扰抑制和邻区干扰协调能力',
  category: ScenarioCategory.EXTREME,

  taxonomy: {
    source: 'synthetic',
    geography: {
      region: '密集城区',
      type: 'urban',
    },
    purpose: 'interference',
    network: '5G NR FR1',
    complexity: 'advanced',
    tags: ['同频干扰', '密集基站', 'ICIC', '干扰协调'],
  },

  origin: {
    type: 'synthetic',
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-08-10T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 3500, ul: 3500 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: [
      {
        id: 'bs-dense-001',
        name: '密集区基站1',
        position: { x: 0, y: 0, z: 25 },
        antennaConfig: { txAntennas: 64, rxAntennas: 32, gain: 18, beamforming: true },
        power: { txPower: 43, maxEIRP: 61 },
      },
      {
        id: 'bs-dense-002',
        name: '密集区基站2',
        position: { x: 300, y: 0, z: 25 },
        antennaConfig: { txAntennas: 64, rxAntennas: 32, gain: 18, beamforming: true },
        power: { txPower: 43, maxEIRP: 61 },
      },
      {
        id: 'bs-dense-003',
        name: '密集区基站3',
        position: { x: 150, y: 260, z: 25 },
        antennaConfig: { txAntennas: 64, rxAntennas: 32, gain: 18, beamforming: true },
        power: { txPower: 43, maxEIRP: 61 },
      },
      {
        id: 'bs-dense-004',
        name: '密集区基站4',
        position: { x: 450, y: 260, z: 25 },
        antennaConfig: { txAntennas: 64, rxAntennas: 32, gain: 18, beamforming: true },
        power: { txPower: 43, maxEIRP: 61 },
      },
    ],
  },

  trajectory: {
    type: PathType.URBAN_GRID,
    duration: 360,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 25, heading: 90 } },
      { timestamp: 90, position: { x: 200, y: 0, z: 1.5 }, velocity: { speed: 25, heading: 45 } },
      { timestamp: 180, position: { x: 300, y: 200, z: 1.5 }, velocity: { speed: 25, heading: 90 } },
      { timestamp: 270, position: { x: 500, y: 200, z: 1.5 }, velocity: { speed: 25, heading: 180 } },
      { timestamp: 360, position: { x: 300, y: 400, z: 1.5 }, velocity: { speed: 25, heading: 270 } },
    ],
    stats: {
      totalDistance: 1000,
      avgSpeed: 25,
      maxSpeed: 25,
      minSpeed: 25,
    },
  },

  environment: {
    type: EnvironmentType.URBAN_MACRO,
    channelModel: ChannelModel.CDL_C,
    propagation: {
      pathLoss: { model: 'Urban Macro (3GPP TR 38.901)', exponent: 3.5 },
      shadowing: { enabled: true, stdDev: 8 },
      fastFading: { enabled: true, dopplerSpread: 23 },
    },
  },

  traffic: {
    type: TrafficType.FTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 60, min: 30, max: 120 },
    pattern: { mode: 'continuous' },
  },

  kpiTargets: [
    {
      metric: KPIMetric.SINR,
      target: { value: 5, unit: 'dB', operator: '>' },
      sampling: { interval: 1000, aggregation: 'p50' },
      passCriteria: { threshold: 5, percentile: 80 },
      description: '干扰环境下SINR维持',
    },
    {
      metric: KPIMetric.THROUGHPUT_DL,
      target: { value: 40, unit: 'Mbps', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 40, percentile: 75 },
    },
  ],

  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T15:00:00Z' },
    executability: { canExecuteOTA: true, canExecuteConducted: true, canExecuteDigitalTwin: true },
  },

  notes: '密集基站部署，基站间距仅300米，测试干扰抑制和波束管理',
}

// ========== 场景9: V2X十字路口 ==========

export const scenario_v2x_intersection: RoadTestScenarioDetail = {
  id: 'scenario-009',
  name: 'V2X十字路口碰撞预警',
  description: '城市十字路口，测试V2X低延迟通信和可靠性',
  category: ScenarioCategory.FUNCTIONAL,

  taxonomy: {
    source: 'real-world',
    geography: {
      region: '典型城市十字路口',
      type: 'urban',
    },
    purpose: 'latency',
    network: 'C-V2X',
    complexity: 'intermediate',
    tags: ['V2X', '低延迟', '十字路口', '碰撞预警'],
  },

  origin: {
    type: 'real-world',
    realWorld: {
      location: '典型城市交叉路口场景',
      captureDate: '2024-09-01',
    },
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-09-05T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.C_V2X,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 5900, ul: 5900 },
    bandwidth: { dl: 20, ul: 20 },
    baseStations: [
      {
        id: 'rsu-001',
        name: '路侧单元RSU',
        position: { x: 0, y: 0, z: 6 },
        antennaConfig: { txAntennas: 2, rxAntennas: 2, gain: 8, beamforming: false },
        power: { txPower: 23, maxEIRP: 31 },
      },
    ],
  },

  trajectory: {
    type: PathType.CUSTOM,
    duration: 30,
    waypoints: [
      { timestamp: 0, position: { x: -100, y: 0, z: 1.5 }, velocity: { speed: 50, heading: 90 } },
      { timestamp: 10, position: { x: -50, y: 0, z: 1.5 }, velocity: { speed: 40, heading: 90 } },
      { timestamp: 20, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 30, heading: 90 } },
      { timestamp: 30, position: { x: 50, y: 0, z: 1.5 }, velocity: { speed: 40, heading: 90 } },
    ],
    stats: {
      totalDistance: 150,
      avgSpeed: 40,
      maxSpeed: 50,
      minSpeed: 30,
    },
  },

  environment: {
    type: EnvironmentType.URBAN_MICRO,
    channelModel: ChannelModel.WINNER_B1,
    propagation: {
      pathLoss: { model: 'Urban Micro LOS', exponent: 2.1 },
      shadowing: { enabled: true, stdDev: 4 },
      fastFading: { enabled: true, dopplerSpread: 92 },
    },
  },

  traffic: {
    type: TrafficType.CUSTOM,
    direction: TrafficDirection.BIDIRECTIONAL,
    dataRate: { target: 1, min: 0.5, max: 2 },
    pattern: { mode: 'periodic', period: 100, dutyCycle: 10 },
    qos: { priority: 1, latency: 10, packetLoss: 0.1 },
  },

  kpiTargets: [
    {
      metric: KPIMetric.LATENCY,
      target: { value: 10, unit: 'ms', operator: '<' },
      sampling: { interval: 10, aggregation: 'p99' },
      passCriteria: { threshold: 10, percentile: 99 },
      description: 'V2X超低延迟要求',
    },
    {
      metric: KPIMetric.PACKET_LOSS,
      target: { value: 0.1, unit: '%', operator: '<' },
      sampling: { interval: 100, aggregation: 'mean' },
      passCriteria: { threshold: 0.1 },
    },
  ],

  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T16:00:00Z' },
    executability: { canExecuteOTA: true, canExecuteConducted: true, canExecuteDigitalTwin: true },
  },

  notes: 'V2X场景，延迟要求<10ms，丢包率<0.1%',
}

// ========== 场景10: 连续切换压力测试 ==========

export const scenario_continuous_handover: RoadTestScenarioDetail = {
  id: 'scenario-010',
  name: '连续切换压力测试',
  description: '密集基站部署高速公路，频繁切换场景，测试切换稳定性和累积误差',
  category: ScenarioCategory.EXTREME,

  taxonomy: {
    source: 'synthetic',
    geography: {
      region: '密集基站高速公路',
      type: 'highway',
    },
    purpose: 'handover',
    network: '5G NR FR1',
    complexity: 'advanced',
    tags: ['频繁切换', '压力测试', '累积误差', '稳定性'],
  },

  origin: {
    type: 'synthetic',
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-09-10T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 2600, ul: 2600 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: Array.from({ length: 10 }, (_, i) => ({
      id: `bs-ho-${String(i + 1).padStart(3, '0')}`,
      name: `切换测试基站${i + 1}`,
      position: { x: i * 2000, y: 0, z: 35 },
      antennaConfig: { txAntennas: 32, rxAntennas: 16, gain: 17, beamforming: true },
      power: { txPower: 46, maxEIRP: 63 },
    })),
    handover: { enabled: true, algorithm: 'A3', hysteresis: 2, timeToTrigger: 80 },
  },

  trajectory: {
    type: PathType.LINEAR,
    duration: 600,
    waypoints: Array.from({ length: 7 }, (_, i) => ({
      timestamp: i * 100,
      position: { x: i * 3000, y: 0, z: 1.5 },
      velocity: { speed: 108, heading: 90 },
    })),
    stats: {
      totalDistance: 18000,
      avgSpeed: 108,
      maxSpeed: 108,
      minSpeed: 108,
    },
  },

  environment: {
    type: EnvironmentType.HIGHWAY,
    channelModel: ChannelModel.TDL_A,
    propagation: {
      pathLoss: { model: 'Free Space + Two-Ray', exponent: 2.4 },
      shadowing: { enabled: true, stdDev: 5 },
      fastFading: { enabled: true, dopplerSpread: 166 },
    },
  },

  traffic: {
    type: TrafficType.FTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 80, min: 40, max: 150 },
    pattern: { mode: 'continuous' },
  },

  kpiTargets: [
    {
      metric: KPIMetric.HANDOVER_SUCCESS_RATE,
      target: { value: 99, unit: '%', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 99 },
      description: '连续切换成功率',
    },
    {
      metric: KPIMetric.HANDOVER_LATENCY,
      target: { value: 80, unit: 'ms', operator: '<' },
      sampling: { interval: 100, aggregation: 'p95' },
      passCriteria: { threshold: 80, percentile: 95 },
    },
    {
      metric: KPIMetric.THROUGHPUT_DL,
      target: { value: 60, unit: 'Mbps', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 60, percentile: 85 },
      description: '频繁切换下吞吐量维持',
    },
  ],

  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T17:00:00Z' },
    executability: { canExecuteOTA: true, canExecuteConducted: true, canExecuteDigitalTwin: true },
  },

  notes: '压力测试场景，10个基站间距2km，预期产生8-9次切换，测试切换累积效应',
}
