/**
 * 虚拟路测场景库 - Mock数据
 *
 * 包含10个预定义场景实例，覆盖不同的测试目的和环境类型
 */

import type {
  RoadTestScenario,
  RoadTestScenarioDetail,
} from '../types/roadTest'

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

// ========== 场景2: 上海高速公路 ==========

export const scenario_shanghai_highway: RoadTestScenarioDetail = {
  id: 'scenario-002',
  name: '上海高速公路',
  description: '沪宁高速上海段，高速行驶场景，测试高多普勒频移下的性能',
  category: ScenarioCategory.PERFORMANCE,
  taxonomy: {
    source: 'synthetic',
    geography: { region: '上海市沪宁高速', type: 'highway' },
    purpose: 'handover',
    network: '5G NR FR1',
    complexity: 'intermediate',
    tags: ['高速', '切换', '多普勒'],
  },
  origin: {
    type: 'real-world',
    realWorld: {
      location: '上海市沪宁高速',
      coordinates: { latitude: 31.2304, longitude: 121.4737 },
      captureDate: '2024-04-01',
      dataSources: ['GIS', 'OpenStreetMap'],
    },
  },
  metadata: {
    version: '1.0',
    createdAt: '2024-04-01T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
    organization: 'Meta-3D Lab',
  },
  networkConfig: {
    networkType: NetworkType.NR_FR1,
    duplexMode: DuplexMode.FDD,
    frequency: { dl: 2100, ul: 1900 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: [
      { id: 'bs-highway-001', name: '高速站点1', position: { x: 0, y: 0, z: 30 }, antennaConfig: { txAntennas: 32, rxAntennas: 16, gain: 18, beamforming: true }, power: { txPower: 46, maxEIRP: 64 } },
      { id: 'bs-highway-002', name: '高速站点2', position: { x: 2000, y: 0, z: 30 }, antennaConfig: { txAntennas: 32, rxAntennas: 16, gain: 18, beamforming: true }, power: { txPower: 46, maxEIRP: 64 } },
    ],
    handover: { enabled: true, algorithm: 'A3', hysteresis: 3, timeToTrigger: 160 },
  },
  trajectory: {
    type: PathType.HIGHWAY,
    duration: 300,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 0, heading: 0 } },
      { timestamp: 150, position: { x: 3000, y: 0, z: 1.5 }, velocity: { speed: 120, heading: 0 } },
      { timestamp: 300, position: { x: 6000, y: 0, z: 1.5 }, velocity: { speed: 120, heading: 0 } },
    ],
    stats: { totalDistance: 6000, avgSpeed: 120, maxSpeed: 120, minSpeed: 0 },
  },
  environment: {
    type: EnvironmentType.URBAN_MACRO,
    channelModel: ChannelModel.CDL_A,
    propagation: { pathLoss: { model: 'Highway (3GPP TR 38.901)', exponent: 2.8 }, shadowing: { enabled: true, stdDev: 4 }, fastFading: { enabled: true, dopplerSpread: 222 } },
    weather: { temperature: 25, humidity: 60 },
  },
  traffic: {
    type: TrafficType.FTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 150, min: 80, max: 300 },
    pattern: { mode: 'continuous' },
    qos: { priority: 7, latency: 30, packetLoss: 1 },
  },
  triggers: [],
  kpiTargets: [
    { metric: KPIMetric.THROUGHPUT_DL, target: { value: 120, unit: 'Mbps', operator: '>' }, sampling: { interval: 1000, aggregation: 'mean' }, passCriteria: { threshold: 120, percentile: 90 }, description: '下行吞吐量 > 120Mbps' },
  ],
  rayTracingOutput: undefined,
  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T08:00:00Z', validationNotes: '合成场景' },
    executability: { canExecuteOTA: true, canExecuteConducted: true, canExecuteDigitalTwin: true, blockers: [] },
  },
  references: [],
};

// ========== 场景3-10: 其他场景简化定义 ==========

const createSimpleScenario = (
  id: string,
  name: string,
  description: string,
  category: ScenarioCategory,
  region: string,
  geoType: 'urban' | 'suburban' | 'rural' | 'highway' | 'indoor',
  pathType: PathType,
  envType: EnvironmentType,
  networkType: NetworkType
): RoadTestScenarioDetail => ({
  id,
  name,
  description,
  category,
  taxonomy: {
    source: 'real-world',
    geography: { region, type: geoType },
    purpose: 'throughput',
    network: '5G NR FR1',
    complexity: 'basic',
    tags: [geoType],
  },
  origin: {
    type: 'real-world',
    realWorld: {
      location: region,
      coordinates: { latitude: 0, longitude: 0 },
      captureDate: '2024-04-01',
      dataSources: ['GIS'],
    },
  },
  metadata: {
    version: '1.0',
    createdAt: '2024-04-01T10:00:00Z',
    updatedAt: '2024-11-15T08:00:00Z',
    author: 'Meta-3D Team',
    organization: 'Meta-3D Lab',
  },
  networkConfig: {
    networkType,
    duplexMode: DuplexMode.TDD,
    frequency: { dl: 3500, ul: 3500 },
    bandwidth: { dl: 100, ul: 50 },
    baseStations: [
      { id: `bs-${id}-001`, name: '站点1', position: { x: 0, y: 0, z: 25 }, antennaConfig: { txAntennas: 32, rxAntennas: 16, gain: 18, beamforming: true }, power: { txPower: 43, maxEIRP: 61 } },
    ],
    handover: { enabled: true, algorithm: 'A3', hysteresis: 3, timeToTrigger: 160 },
  },
  trajectory: {
    type: pathType,
    duration: 300,
    waypoints: [
      { timestamp: 0, position: { x: 0, y: 0, z: 1.5 }, velocity: { speed: 0, heading: 0 } },
      { timestamp: 150, position: { x: 500, y: 500, z: 1.5 }, velocity: { speed: 30, heading: 45 } },
      { timestamp: 300, position: { x: 1000, y: 1000, z: 1.5 }, velocity: { speed: 30, heading: 45 } },
    ],
    stats: { totalDistance: 1414, avgSpeed: 30, maxSpeed: 30, minSpeed: 0 },
  },
  environment: {
    type: envType,
    channelModel: ChannelModel.CDL_C,
    propagation: { pathLoss: { model: '3GPP TR 38.901', exponent: 3.5 }, shadowing: { enabled: true, stdDev: 6 }, fastFading: { enabled: true, dopplerSpread: 50 } },
    weather: { temperature: 20, humidity: 50 },
  },
  traffic: {
    type: TrafficType.FTP,
    direction: TrafficDirection.DOWNLINK,
    dataRate: { target: 100, min: 50, max: 200 },
    pattern: { mode: 'continuous' },
    qos: { priority: 7, latency: 50, packetLoss: 1 },
  },
  triggers: [],
  kpiTargets: [
    { metric: KPIMetric.THROUGHPUT_DL, target: { value: 80, unit: 'Mbps', operator: '>' }, sampling: { interval: 1000, aggregation: 'mean' }, passCriteria: { threshold: 80 }, description: '下行吞吐量 > 80Mbps' },
  ],
  rayTracingOutput: undefined,
  integrity: {
    dataCompleteness: { hasNetwork: true, hasTrajectory: true, hasEnvironment: true, hasTraffic: true, hasKPI: true },
    validation: { isValidated: true, validatedBy: 'Meta-3D Team', validatedAt: '2024-11-15T08:00:00Z', validationNotes: '合成场景' },
    executability: { canExecuteOTA: true, canExecuteConducted: true, canExecuteDigitalTwin: true, blockers: [] },
  },
  references: [],
});

export const scenario_shenzhen_metro = createSimpleScenario('scenario-003', '深圳地铁隧道', '地铁1号线隧道内移动场景', ScenarioCategory.PERFORMANCE, '深圳地铁1号线', 'indoor', PathType.URBAN_GRID, EnvironmentType.INDOOR, NetworkType.NR_FR1);
export const scenario_guangzhou_rural = createSimpleScenario('scenario-004', '广州郊区乡村道路', '郊区低密度覆盖场景', ScenarioCategory.PERFORMANCE, '广州市增城区', 'rural', PathType.CUSTOM, EnvironmentType.RURAL, NetworkType.LTE);
export const scenario_chengdu_mall = createSimpleScenario('scenario-005', '成都室内购物中心', 'IFS国际金融中心室内覆盖', ScenarioCategory.PERFORMANCE, '成都IFS', 'indoor', PathType.CUSTOM, EnvironmentType.INDOOR, NetworkType.NR_FR1);
export const scenario_hangzhou_scenic = createSimpleScenario('scenario-006', '杭州西湖风景区', '西湖景区游客密集场景', ScenarioCategory.PERFORMANCE, '杭州西湖景区', 'suburban', PathType.URBAN_GRID, EnvironmentType.URBAN_MICRO, NetworkType.NR_FR1);
export const scenario_nanjing_airport = createSimpleScenario('scenario-007', '南京机场', '禄口国际机场航站楼', ScenarioCategory.PERFORMANCE, '南京禄口机场', 'indoor', PathType.CUSTOM, EnvironmentType.INDOOR, NetworkType.NR_FR1);
export const scenario_wuhan_industrial = createSimpleScenario('scenario-008', '武汉工业园区', '光谷工业园区场景', ScenarioCategory.PERFORMANCE, '武汉光谷', 'suburban', PathType.URBAN_GRID, EnvironmentType.URBAN_MACRO, NetworkType.NR_FR1);
export const scenario_xian_ancient = createSimpleScenario('scenario-009', '西安古城墙环线', '古城墙环线旅游路线', ScenarioCategory.PERFORMANCE, '西安古城墙', 'urban', PathType.URBAN_GRID, EnvironmentType.URBAN_MACRO, NetworkType.LTE);
export const scenario_chongqing_mountain = createSimpleScenario('scenario-010', '重庆山地城市', '山地城市复杂地形场景', ScenarioCategory.PERFORMANCE, '重庆市中心', 'urban', PathType.URBAN_GRID, EnvironmentType.URBAN_MACRO, NetworkType.NR_FR1);

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
  {
    id: 'scenario-002',
    name: '上海高速公路',
    description: '沪宁高速上海段，高速行驶场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'highway',
      region: '上海市沪宁高速',
      purpose: 'handover',
      network: '5G NR FR1',
      complexity: 'intermediate',
      tags: ['高速', '切换', '多普勒'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MACRO,
      duration: 300,
      avgSpeed: 120,
      numBaseStations: 2,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-003',
    name: '深圳地铁隧道',
    description: '地铁1号线隧道内移动场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'indoor',
      region: '深圳地铁1号线',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['indoor'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.INDOOR,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-004',
    name: '广州郊区乡村道路',
    description: '郊区低密度覆盖场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'rural',
      region: '广州市增城区',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['rural'],
    },
    summary: {
      networkType: NetworkType.LTE,
      environmentType: EnvironmentType.RURAL,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-005',
    name: '成都室内购物中心',
    description: 'IFS国际金融中心室内覆盖',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'indoor',
      region: '成都IFS',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['indoor'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.INDOOR,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-006',
    name: '杭州西湖风景区',
    description: '西湖景区游客密集场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'suburban',
      region: '杭州西湖景区',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['suburban'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MICRO,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-007',
    name: '南京机场',
    description: '禄口国际机场航站楼',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'indoor',
      region: '南京禄口机场',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['indoor'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.INDOOR,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-008',
    name: '武汉工业园区',
    description: '光谷工业园区场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'suburban',
      region: '武汉光谷',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['suburban'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MACRO,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-009',
    name: '西安古城墙环线',
    description: '古城墙环线旅游路线',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'urban',
      region: '西安古城墙',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['urban'],
    },
    summary: {
      networkType: NetworkType.LTE,
      environmentType: EnvironmentType.URBAN_MACRO,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
  {
    id: 'scenario-010',
    name: '重庆山地城市',
    description: '山地城市复杂地形场景',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'urban',
      region: '重庆市中心',
      purpose: 'throughput',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['urban'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MACRO,
      duration: 300,
      avgSpeed: 30,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-01T10:00:00Z',
  },
]

// 导出场景详情映射（用于根据ID获取完整场景）
export const scenarioDetailsMap: Record<string, RoadTestScenarioDetail> = {
  'scenario-001': scenario_beijing_cbd,
  'scenario-002': scenario_shanghai_highway,
  'scenario-003': scenario_shenzhen_metro,
  'scenario-004': scenario_guangzhou_rural,
  'scenario-005': scenario_chengdu_mall,
  'scenario-006': scenario_hangzhou_scenic,
  'scenario-007': scenario_nanjing_airport,
  'scenario-008': scenario_wuhan_industrial,
  'scenario-009': scenario_xian_ancient,
  'scenario-010': scenario_chongqing_mountain,
}
