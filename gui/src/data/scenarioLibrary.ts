/**
 * 虚拟路测场景库 - Mock数据
 *
 * 包含10个预定义场景实例，覆盖不同的测试目的和环境类型
 */

import {
  RoadTestScenario,
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

// ========== 场景1: 北京CBD早高峰通勤 ==========

export const scenario_beijing_cbd: RoadTestScenarioDetail = {
  id: 'scenario-001',
  name: '北京CBD早高峰通勤',
  description: '模拟北京朝阳区CBD核心区域早高峰时段的通勤场景，车辆低速行驶，密集建筑环境，多基站频繁切换',
  category: ScenarioCategory.PERFORMANCE,

  taxonomy: {
    source: 'real-world',
    geography: {
      region: '北京市朝阳区CBD',
      type: 'urban',
    },
    purpose: 'throughput',
    network: '5G NR FR1',
    complexity: 'advanced',
    tags: ['早高峰', '密集建筑', '低速', '频繁切换', '真实场景'],
  },

  origin: {
    type: 'real-world',
    realWorld: {
      location: '北京市朝阳区CBD核心区 - 国贸到望京SOHO',
      coordinates: {
        latitude: 39.9075,
        longitude: 116.4465,
      },
      captureDate: '2024-03-15',
      dataSources: ['GIS', 'Street View', 'OpenStreetMap'],
    },
    rayTracing: {
      tool: 'WirelessInSite',
      version: '3.5.1',
      environmentModel: 'beijing-cbd-3d-model-v2.wxi',
      generatedBy: 'Meta-3D Team',
      generatedAt: '2024-03-20T10:00:00Z',
    },
  },

  metadata: {
    version: '1.0',
    createdAt: '2024-03-20T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
    organization: 'Meta-3D Lab',
  },

  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.TDD,
    frequency: {
      dl: 3500,
      ul: 3500,
    },
    bandwidth: {
      dl: 100,
      ul: 50,
    },
    baseStations: [
      {
        id: 'bs-cbd-001',
        name: 'CBD国贸站',
        position: { x: 0, y: 0, z: 30 },
        antennaConfig: {
          txAntennas: 64,
          rxAntennas: 32,
          gain: 18,
          beamforming: true,
        },
        power: {
          txPower: 46,
          maxEIRP: 64,
        },
      },
      {
        id: 'bs-cbd-002',
        name: 'CBD建外SOHO站',
        position: { x: 800, y: 600, z: 35 },
        antennaConfig: {
          txAntennas: 64,
          rxAntennas: 32,
          gain: 18,
          beamforming: true,
        },
        power: {
          txPower: 46,
          maxEIRP: 64,
        },
      },
      {
        id: 'bs-cbd-003',
        name: 'CBD大望路站',
        position: { x: 1500, y: 300, z: 28 },
        antennaConfig: {
          txAntennas: 64,
          rxAntennas: 32,
          gain: 18,
          beamforming: true,
        },
        power: {
          txPower: 46,
          maxEIRP: 64,
        },
      },
    ],
    handover: {
      enabled: true,
      algorithm: 'A3',
      hysteresis: 3,
      timeToTrigger: 160,
    },
  },

  trajectory: {
    type: PathType.URBAN_GRID,
    duration: 600,
    waypoints: [
      {
        timestamp: 0,
        position: { x: 0, y: 0, z: 1.5 },
        velocity: { speed: 0, heading: 45 },
      },
      {
        timestamp: 60,
        position: { x: 200, y: 200, z: 1.5 },
        velocity: { speed: 30, heading: 45 },
      },
      {
        timestamp: 180,
        position: { x: 600, y: 600, z: 1.5 },
        velocity: { speed: 20, heading: 60 },
      },
      {
        timestamp: 300,
        position: { x: 1000, y: 400, z: 1.5 },
        velocity: { speed: 40, heading: 90 },
      },
      {
        timestamp: 450,
        position: { x: 1500, y: 300, z: 1.5 },
        velocity: { speed: 25, heading: 120 },
      },
      {
        timestamp: 600,
        position: { x: 1800, y: 600, z: 1.5 },
        velocity: { speed: 0, heading: 120 },
      },
    ],
    stats: {
      totalDistance: 2500,
      avgSpeed: 28,
      maxSpeed: 40,
      minSpeed: 0,
    },
  },

  environment: {
    type: EnvironmentType.URBAN_MACRO,
    channelModel: ChannelModel.CDL_C,
    propagation: {
      pathLoss: {
        model: 'Urban Macro (3GPP TR 38.901)',
        exponent: 3.8,
      },
      shadowing: {
        enabled: true,
        stdDev: 7,
      },
      fastFading: {
        enabled: true,
        dopplerSpread: 55.6,
      },
    },
    weather: {
      temperature: 18,
      humidity: 45,
    },
  },

  traffic: {
    type: TrafficType.FTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: {
      target: 100,
      min: 50,
      max: 200,
    },
    pattern: {
      mode: 'continuous',
    },
    qos: {
      priority: 7,
      latency: 50,
      packetLoss: 1,
    },
  },

  triggers: [
    {
      id: 'trigger-001',
      type: TriggerType.HANDOVER,
      timestamp: 180,
      condition: {
        parameter: 'RSRP',
        operator: '<',
        threshold: -110,
        unit: 'dBm',
      },
      action: {
        type: 'start_handover',
        parameters: {
          targetCell: 'bs-cbd-002',
        },
      },
      description: '从国贸站切换到建外SOHO站',
    },
    {
      id: 'trigger-002',
      type: TriggerType.HANDOVER,
      timestamp: 450,
      condition: {
        parameter: 'RSRP',
        operator: '<',
        threshold: -110,
        unit: 'dBm',
      },
      action: {
        type: 'start_handover',
        parameters: {
          targetCell: 'bs-cbd-003',
        },
      },
      description: '从建外SOHO站切换到大望路站',
    },
  ],

  kpiTargets: [
    {
      metric: KPIMetric.THROUGHPUT_DL,
      target: {
        value: 80,
        unit: 'Mbps',
        operator: '>',
      },
      sampling: {
        interval: 1000,
        aggregation: 'mean',
      },
      passCriteria: {
        threshold: 80,
        percentile: 90,
      },
      description: '平均下行吞吐量应大于80Mbps',
    },
    {
      metric: KPIMetric.HANDOVER_SUCCESS_RATE,
      target: {
        value: 98,
        unit: '%',
        operator: '>',
      },
      sampling: {
        interval: 1000,
        aggregation: 'mean',
      },
      passCriteria: {
        threshold: 98,
      },
      description: '切换成功率应大于98%',
    },
    {
      metric: KPIMetric.LATENCY,
      target: {
        value: 50,
        unit: 'ms',
        operator: '<',
      },
      sampling: {
        interval: 100,
        aggregation: 'p95',
      },
      passCriteria: {
        threshold: 50,
        percentile: 95,
      },
      description: 'P95延迟应小于50ms',
    },
  ],

  rayTracingOutput: {
    tool: 'WirelessInSite',
    version: '3.5.1',
    resultFiles: {
      pathLossMatrix: '/data/scenarios/beijing-cbd/path-loss-matrix.dat',
      channelCoefficients: '/data/scenarios/beijing-cbd/channel-coef.dat',
      dopplerProfile: '/data/scenarios/beijing-cbd/doppler-profile.dat',
    },
    statistics: {
      averagePathLoss: 118,
      shadowingStdDev: 7.2,
      rmsDelaySpread: 186,
      dominantPathDelay: 45,
    },
    execution: {
      computeTime: 3600,
      rayCount: 150000000,
      reflectionOrder: 6,
      diffractionOrder: 2,
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
      validatedBy: 'Zhang Wei',
      validatedAt: '2024-11-15T08:00:00Z',
      validationNotes: '射线跟踪结果与实测数据对比误差<5dB',
    },
    executability: {
      canExecuteOTA: true,
      canExecuteConducted: true,
      canExecuteDigitalTwin: true,
    },
  },

  notes: '该场景基于北京CBD实际道路网络和建筑数据，使用射线跟踪工具生成传播特性，适用于验证密集城区的吞吐量和切换性能。',
  references: [
    {
      title: '3GPP TR 38.901 Study on channel model for frequencies from 0.5 to 100 GHz',
      document: '3GPP TR 38.901 V17.0.0',
    },
    {
      title: 'Remcom Wireless InSite User Manual',
      url: 'https://www.remcom.com/wireless-insite',
    },
  ],
}

// ========== 场景简化视图（用于列表展示）==========

export const scenarioList: RoadTestScenario[] = [
  {
    id: 'scenario-001',
    name: '北京CBD早高峰通勤',
    description: '模拟北京朝阳区CBD核心区域早高峰时段的通勤场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'urban',
      region: '北京市朝阳区CBD',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'advanced',
      tags: ['早高峰', '密集建筑', '低速', '频繁切换'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MACRO,
      duration: 600,
      avgSpeed: 28,
      numBaseStations: 3,
      kpiCount: 3,
    },
    isComplete: true,
    isValidated: true,
    canExecute: {
      ota: true,
      conducted: true,
      digitalTwin: true,
    },
    createdAt: '2024-03-20T10:00:00Z',
  },
  // TODO: 其余9个场景的简化视图将在下一步添加
]

// 导出场景详情映射（用于根据ID获取完整场景）
export const scenarioDetailsMap: Record<string, RoadTestScenarioDetail> = {
  'scenario-001': scenario_beijing_cbd,
  // TODO: 其余9个场景的完整定义将在下一步添加
}
