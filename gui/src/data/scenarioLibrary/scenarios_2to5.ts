/**
 * 虚拟路测场景库 - 场景2-5
 */

import {
  RoadTestScenarioDetail,
  ScenarioCategory,
  NetworkType,
  DuplexMode,
  PathType,
  EnvironmentType,
  ChannelModel,
  TrafficType,
  TrafficDirection,
  KPIMetric,
  TriggerType,
} from '../types/roadTest'

// ========== 场景2: 京沪高速G2巡航 ==========

export const scenario_highway_g2: RoadTestScenarioDetail = {
  id: 'scenario-002',
  name: '京沪高速G2巡航',
  description: '京沪高速G2苏州段，车辆以100-120km/h高速巡航，基站间距大，测试高速切换性能',
  category: ScenarioCategory.PERFORMANCE,

  taxonomy: {
    source: 'real-world',
    geography: {
      region: '京沪高速G2苏州段',
      type: 'highway',
    },
    purpose: 'handover',
    network: '5G NR FR1',
    complexity: 'intermediate',
    tags: ['高速', '切换', '多普勒', '稀疏基站'],
  },

  origin: {
    type: 'real-world',
    realWorld: {
      location: '京沪高速G2苏州段 K1200-K1220',
      coordinates: {
        latitude: 31.2989,
        longitude: 120.5853,
      },
      captureDate: '2024-04-10',
      dataSources: ['GIS', 'Satellite Imagery'],
    },
    rayTracing: {
      tool: 'WinProp',
      version: '2023.1',
      environmentModel: 'g2-highway-suzhou-20km.wpi',
      generatedBy: 'Meta-3D Team',
      generatedAt: '2024-04-15T14:00:00Z',
    },
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-04-15T14:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
    organization: 'Meta-3D Lab',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: {
      dl: 2600,
      ul: 2600,
    },
    bandwidth: {
      dl: 100,
      ul: 50,
    },
    baseStations: [
      {
        id: 'bs-g2-001',
        name: 'G2-K1200基站',
        position: { x: 0, y: 0, z: 40 },
        antennaConfig: {
          txAntennas: 32,
          rxAntennas: 16,
          gain: 17,
          beamforming: true,
        },
        power: {
          txPower: 49,
          maxEIRP: 66,
        },
      },
      {
        id: 'bs-g2-002',
        name: 'G2-K1210基站',
        position: { x: 10000, y: 0, z: 40 },
        antennaConfig: {
          txAntennas: 32,
          rxAntennas: 16,
          gain: 17,
          beamforming: true,
        },
        power: {
          txPower: 49,
          maxEIRP: 66,
        },
      },
      {
        id: 'bs-g2-003',
        name: 'G2-K1220基站',
        position: { x: 20000, y: 0, z: 40 },
        antennaConfig: {
          txAntennas: 32,
          rxAntennas: 16,
          gain: 17,
          beamforming: true,
        },
        power: {
          txPower: 49,
          maxEIRP: 66,
        },
      },
    ],
    handover: {
      enabled: true,
      algorithm: 'A3',
      hysteresis: 2,
      timeToTrigger: 100,
    },
  },

  trajectory: {
    type: PathType.LINEAR,
    duration: 600,
    waypoints: [
      {
        timestamp: 0,
        position: { x: 0, y: 0, z: 1.5 },
        velocity: { speed: 100, heading: 90 },
      },
      {
        timestamp: 150,
        position: { x: 4167, y: 0, z: 1.5 },
        velocity: { speed: 120, heading: 90 },
      },
      {
        timestamp: 300,
        position: { x: 9167, y: 0, z: 1.5 },
        velocity: { speed: 120, heading: 90 },
      },
      {
        timestamp: 450,
        position: { x: 14167, y: 0, z: 1.5 },
        velocity: { speed: 120, heading: 90 },
      },
      {
        timestamp: 600,
        position: { x: 19167, y: 0, z: 1.5 },
        velocity: { speed: 110, heading: 90 },
      },
    ],
    stats: {
      totalDistance: 19167,
      avgSpeed: 115,
      maxSpeed: 120,
      minSpeed: 100,
    },
  },

  environment: {
    type: EnvironmentType.HIGHWAY,
    channelModel: ChannelModel.TDL_A,
    propagation: {
      pathLoss: {
        model: 'Free Space + Two-Ray Ground',
        exponent: 2.5,
      },
      shadowing: {
        enabled: true,
        stdDev: 4,
      },
      fastFading: {
        enabled: true,
        dopplerSpread: 222.2,
      },
    },
    weather: {
      temperature: 22,
      humidity: 60,
    },
  },

  traffic: {
    type: TrafficType.VIDEO,
    direction: TrafficDirection.DOWNLINK,
    dataRate: {
      target: 50,
      min: 30,
      max: 100,
    },
    pattern: {
      mode: 'continuous',
    },
    qos: {
      priority: 5,
      latency: 100,
      packetLoss: 2,
      jitter: 30,
    },
  },

  triggers: [
    {
      id: 'trigger-ho-001',
      type: TriggerType.HANDOVER,
      timestamp: 250,
      condition: {
        parameter: 'RSRP',
        operator: '<',
        threshold: -105,
        unit: 'dBm',
      },
      action: {
        type: 'start_handover',
        parameters: { targetCell: 'bs-g2-002' },
      },
      description: 'K1200 → K1210切换',
    },
    {
      id: 'trigger-ho-002',
      type: TriggerType.HANDOVER,
      timestamp: 500,
      condition: {
        parameter: 'RSRP',
        operator: '<',
        threshold: -105,
        unit: 'dBm',
      },
      action: {
        type: 'start_handover',
        parameters: { targetCell: 'bs-g2-003' },
      },
      description: 'K1210 → K1220切换',
    },
  ],

  kpiTargets: [
    {
      metric: KPIMetric.THROUGHPUT_DL,
      target: { value: 40, unit: 'Mbps', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 40, percentile: 85 },
    },
    {
      metric: KPIMetric.HANDOVER_SUCCESS_RATE,
      target: { value: 95, unit: '%', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 95 },
    },
    {
      metric: KPIMetric.HANDOVER_LATENCY,
      target: { value: 100, unit: 'ms', operator: '<' },
      sampling: { interval: 100, aggregation: 'p95' },
      passCriteria: { threshold: 100, percentile: 95 },
    },
  ],

  rayTracingOutput: {
    tool: 'WinProp',
    version: '2023.1',
    resultFiles: {
      pathLossMatrix: '/data/scenarios/highway-g2/path-loss-matrix.dat',
      dopplerProfile: '/data/scenarios/highway-g2/doppler-profile.dat',
    },
    statistics: {
      averagePathLoss: 110,
      shadowingStdDev: 4.1,
      rmsDelaySpread: 45,
      dominantPathDelay: 8,
    },
    execution: {
      computeTime: 1800,
      rayCount: 50000000,
      reflectionOrder: 2,
      diffractionOrder: 1,
    },
  },

  integrity: {
    dataCompleteness: {
      hasNetwork: true,
      hasTrajectory: true,
      hasEnvironment: true,
      hasTraffic: true,
      hasKPI: true,
    },
    validation: {
      isValidated: true,
      validatedBy: 'Li Ming',
      validatedAt: '2024-11-15T09:00:00Z',
    },
    executability: {
      canExecuteOTA: true,
      canExecuteConducted: true,
      canExecuteDigitalTwin: true,
    },
  },

  notes: '高速公路场景，基站间距10km，测试高速移动下的切换性能和多普勒效应处理能力',
}

// ========== 场景3: 上海南京路隧道 ==========

export const scenario_shanghai_tunnel: RoadTestScenarioDetail = {
  id: 'scenario-003',
  name: '上海南京路隧道穿越',
  description: '上海延安路隧道穿越场景，测试信号遮挡、弱覆盖和信号恢复能力',
  category: ScenarioCategory.ENVIRONMENT,

  taxonomy: {
    source: 'real-world',
    geography: {
      region: '上海延安路隧道',
      type: 'tunnel',
    },
    purpose: 'reliability',
    network: 'LTE',
    complexity: 'advanced',
    tags: ['隧道', '遮挡', '弱覆盖', '信号恢复'],
  },

  origin: {
    type: 'real-world',
    realWorld: {
      location: '上海市延安路隧道（黄浦江穿越段）',
      coordinates: {
        latitude: 31.2304,
        longitude: 121.4737,
      },
      captureDate: '2024-05-20',
      dataSources: ['GIS', '隧道内部勘测数据'],
    },
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-05-25T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.LTE,
    duplexMode: DuplexMode.FDD,
    frequency: {
      dl: 1800,
      ul: 1700,
    },
    bandwidth: {
      dl: 20,
      ul: 20,
    },
    baseStations: [
      {
        id: 'bs-tunnel-entry',
        name: '隧道入口基站',
        position: { x: -500, y: 0, z: 10 },
        antennaConfig: {
          txAntennas: 4,
          rxAntennas: 2,
          gain: 14,
          beamforming: false,
        },
        power: { txPower: 43, maxEIRP: 57 },
      },
      {
        id: 'bs-tunnel-inside',
        name: '隧道内中继',
        position: { x: 1500, y: 0, z: 3 },
        antennaConfig: {
          txAntennas: 2,
          rxAntennas: 2,
          gain: 10,
          beamforming: false,
        },
        power: { txPower: 30, maxEIRP: 40 },
      },
      {
        id: 'bs-tunnel-exit',
        name: '隧道出口基站',
        position: { x: 3500, y: 0, z: 10 },
        antennaConfig: {
          txAntennas: 4,
          rxAntennas: 2,
          gain: 14,
          beamforming: false,
        },
        power: { txPower: 43, maxEIRP: 57 },
      },
    ],
  },

  trajectory: {
    type: PathType.LINEAR,
    duration: 240,
    waypoints: [
      {
        timestamp: 0,
        position: { x: -500, y: 0, z: 1.5 },
        velocity: { speed: 60, heading: 90 },
      },
      {
        timestamp: 60,
        position: { x: 500, y: 0, z: -5 },
        velocity: { speed: 50, heading: 90 },
      },
      {
        timestamp: 120,
        position: { x: 1500, y: 0, z: -8 },
        velocity: { speed: 50, heading: 90 },
      },
      {
        timestamp: 180,
        position: { x: 2500, y: 0, z: -5 },
        velocity: { speed: 50, heading: 90 },
      },
      {
        timestamp: 240,
        position: { x: 3500, y: 0, z: 1.5 },
        velocity: { speed: 60, heading: 90 },
      },
    ],
    stats: {
      totalDistance: 4000,
      avgSpeed: 52,
      maxSpeed: 60,
      minSpeed: 50,
    },
  },

  environment: {
    type: EnvironmentType.TUNNEL,
    channelModel: ChannelModel.CUSTOM,
    propagation: {
      pathLoss: {
        model: 'Tunnel Waveguide Model',
        exponent: 1.8,
      },
      shadowing: {
        enabled: true,
        stdDev: 12,
      },
      fastFading: {
        enabled: true,
        dopplerSpread: 33.3,
      },
    },
    obstacles: [
      {
        type: 'building',
        position: { x: 0, y: 0, z: 0 },
        dimensions: { width: 3000, height: 10, depth: 12 },
        material: 'concrete',
        attenuation: 25,
      },
    ],
  },

  traffic: {
    type: TrafficType.HTTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: {
      target: 10,
      min: 2,
      max: 20,
    },
    pattern: {
      mode: 'burst',
      burstSize: 500,
      period: 2000,
    },
  },

  kpiTargets: [
    {
      metric: KPIMetric.RSRP,
      target: { value: -110, unit: 'dBm', operator: '>' },
      sampling: { interval: 500, aggregation: 'mean' },
      passCriteria: { threshold: -110, percentile: 80 },
      description: '隧道内信号强度维持',
    },
    {
      metric: KPIMetric.COVERAGE,
      target: { value: 95, unit: '%', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 95 },
      description: '隧道覆盖率',
    },
  ],

  integrity: {
    dataCompleteness: {
      hasNetwork: true,
      hasTrajectory: true,
      hasEnvironment: true,
      hasTraffic: true,
      hasKPI: true,
    },
    validation: {
      isValidated: true,
      validatedBy: 'Wang Fang',
      validatedAt: '2024-11-15T10:00:00Z',
    },
    executability: {
      canExecuteOTA: true,
      canExecuteConducted: false,
      canExecuteDigitalTwin: true,
      blockers: ['传导模式不支持隧道环境模拟'],
    },
  },

  notes: '隧道场景，信号穿透损耗大，依赖隧道内中继设备',
}

// ========== 场景4: 深圳科技园区覆盖 ==========

export const scenario_shenzhen_tech_park: RoadTestScenarioDetail = {
  id: 'scenario-004',
  name: '深圳科技园区覆盖验证',
  description: '深圳南山科技园区，中密度建筑，测试覆盖完整性和边缘性能',
  category: ScenarioCategory.PERFORMANCE,

  taxonomy: {
    source: 'real-world',
    geography: {
      region: '深圳市南山区科技园',
      type: 'urban',
    },
    purpose: 'coverage',
    network: '5G NR FR1',
    complexity: 'intermediate',
    tags: ['科技园', '覆盖', '中密度建筑'],
  },

  origin: {
    type: 'real-world',
    realWorld: {
      location: '深圳市南山区深圳湾科技生态园',
      coordinates: {
        latitude: 22.5329,
        longitude: 113.9344,
      },
      captureDate: '2024-06-10',
    },
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-06-15T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 2600, ul: 2600 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: [
      {
        id: 'bs-park-001',
        name: '园区1号站',
        position: { x: 0, y: 0, z: 25 },
        antennaConfig: {
          txAntennas: 64,
          rxAntennas: 32,
          gain: 18,
          beamforming: true,
        },
        power: { txPower: 46, maxEIRP: 64 },
      },
      {
        id: 'bs-park-002',
        name: '园区2号站',
        position: { x: 1200, y: 800, z: 25 },
        antennaConfig: {
          txAntennas: 64,
          rxAntennas: 32,
          gain: 18,
          beamforming: true,
        },
        power: { txPower: 46, maxEIRP: 64 },
      },
    ],
  },

  trajectory: {
    type: PathType.CIRCULAR,
    duration: 480,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 0, heading: 0 } },
      { timestamp: 120, position: { x: 600, y: 0, z: 1.5 }, velocity: { speed: 30, heading: 90 } },
      { timestamp: 240, position: { x: 600, y: 600, z: 1.5 }, velocity: { speed: 30, heading: 180 } },
      { timestamp: 360, position: { x: 0, y: 600, z: 1.5 }, velocity: { speed: 30, heading: 270 } },
      { timestamp: 480, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 30, heading: 0 } },
    ],
    stats: {
      totalDistance: 2400,
      avgSpeed: 30,
      maxSpeed: 30,
      minSpeed: 0,
    },
  },

  environment: {
    type: EnvironmentType.URBAN_MICRO,
    channelModel: ChannelModel.CDL_B,
    propagation: {
      pathLoss: { model: 'Urban Micro (3GPP TR 38.901)', exponent: 3.2 },
      shadowing: { enabled: true, stdDev: 6 },
      fastFading: { enabled: true, dopplerSpread: 25 },
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
      metric: KPIMetric.COVERAGE,
      target: { value: 98, unit: '%', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 98 },
    },
    {
      metric: KPIMetric.THROUGHPUT_DL,
      target: { value: 60, unit: 'Mbps', operator: '>' },
      sampling: { interval: 1000, aggregation: 'p50' },
      passCriteria: { threshold: 60, percentile: 80 },
    },
  ],

  integrity: {
    dataCompleteness: {
      hasNetwork: true,
      hasTrajectory: true,
      hasEnvironment: true,
      hasTraffic: true,
      hasKPI: true,
    },
    validation: {
      isValidated: true,
      validatedBy: 'Chen Jie',
      validatedAt: '2024-11-15T11:00:00Z',
    },
    executability: {
      canExecuteOTA: true,
      canExecuteConducted: true,
      canExecuteDigitalTwin: true,
    },
  },
}

// ========== 场景5: 郊区低速移动 ==========

export const scenario_suburban_lowspeed: RoadTestScenarioDetail = {
  id: 'scenario-005',
  name: '郊区低速移动场景',
  description: '典型郊区环境，低密度建筑，测试大范围覆盖和边缘性能',
  category: ScenarioCategory.PERFORMANCE,

  taxonomy: {
    source: 'synthetic',
    geography: {
      region: '通用郊区环境',
      type: 'suburban',
    },
    purpose: 'coverage',
    network: '5G NR FR1',
    complexity: 'basic',
    tags: ['郊区', '低密度', '大范围覆盖'],
  },

  origin: {
    type: 'synthetic',
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-07-01T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 2600, ul: 2600 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: [
      {
        id: 'bs-sub-001',
        name: '郊区基站1',
        position: { x: 0, y: 0, z: 30 },
        antennaConfig: { txAntennas: 32, rxAntennas: 16, gain: 17, beamforming: false },
        power: { txPower: 46, maxEIRP: 63 },
      },
      {
        id: 'bs-sub-002',
        name: '郊区基站2',
        position: { x: 5000, y: 0, z: 30 },
        antennaConfig: { txAntennas: 32, rxAntennas: 16, gain: 17, beamforming: false },
        power: { txPower: 46, maxEIRP: 63 },
      },
    ],
  },

  trajectory: {
    type: PathType.LINEAR,
    duration: 600,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 40, heading: 90 } },
      { timestamp: 300, position: { x: 3333, y: 0, z: 1.5 }, velocity: { speed: 40, heading: 90 } },
      { timestamp: 600, position: { x: 6667, y: 0, z: 1.5 }, velocity: { speed: 40, heading: 90 } },
    ],
    stats: {
      totalDistance: 6667,
      avgSpeed: 40,
      maxSpeed: 40,
      minSpeed: 40,
    },
  },

  environment: {
    type: EnvironmentType.SUBURBAN,
    channelModel: ChannelModel.TDL_B,
    propagation: {
      pathLoss: { model: 'Suburban (COST231-Hata)', exponent: 3.0 },
      shadowing: { enabled: true, stdDev: 8 },
      fastFading: { enabled: true, dopplerSpread: 37 },
    },
  },

  traffic: {
    type: TrafficType.HTTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 30, min: 10, max: 60 },
    pattern: { mode: 'continuous' },
  },

  kpiTargets: [
    {
      metric: KPIMetric.COVERAGE,
      target: { value: 95, unit: '%', operator: '>' },
      sampling: { interval: 1000, aggregation: 'mean' },
      passCriteria: { threshold: 95 },
    },
  ],

  integrity: {
    dataCompleteness: {
      hasNetwork: true,
      hasTrajectory: true,
      hasEnvironment: true,
      hasTraffic: true,
      hasKPI: true,
    },
    validation: {
      isValidated: true,
      validatedBy: 'Meta-3D Team',
      validatedAt: '2024-11-15T12:00:00Z',
    },
    executability: {
      canExecuteOTA: true,
      canExecuteConducted: true,
      canExecuteDigitalTwin: true,
    },
  },
}
