/**
 * 虚拟路测场景库 - 统一导出
 *
 * 整合所有场景数据，提供统一的访问接口
 */

import {
  RoadTestScenario,
  RoadTestScenarioDetail,
  NetworkType,
  EnvironmentType,
  ScenarioCategory,
} from '../../types/roadTest'

// 导入场景1
import { scenario_beijing_cbd } from './scenario_001_beijing_cbd'
// 导入场景2-10（待创建单独文件）
import { scenario_highway_g2 } from './scenario_002_highway_g2'
import { scenario_shanghai_tunnel } from './scenario_003_shanghai_tunnel'
import { scenario_shenzhen_tech_park } from './scenario_004_shenzhen_techpark'
import { scenario_suburban_lowspeed } from './scenario_005_suburban'
import { scenario_indoor_parking } from './scenario_006_indoor_parking'
import { scenario_extreme_highspeed } from './scenario_007_extreme_highspeed'
import { scenario_dense_interference } from './scenario_008_dense_interference'
import { scenario_v2x_intersection } from './scenario_009_v2x_intersection'
import { scenario_continuous_handover } from './scenario_010_continuous_handover'

// ========== 场景简化视图列表 ==========

export const scenarioList: RoadTestScenario[] = [
  // 场景1: 北京CBD早高峰通勤
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
      tags: ['早高峰', '密集建筑', '低速', '频繁切换', '真实场景'],
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
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-03-20T10:00:00Z',
  },

  // 场景2: 京沪高速G2巡航
  {
    id: 'scenario-002',
    name: '京沪高速G2巡航',
    description: '京沪高速G2苏州段，车辆以100-120km/h高速巡航',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'highway',
      region: '京沪高速G2苏州段',
      purpose: 'handover',
      network: '5G NR FR1',
      complexity: 'intermediate',
      tags: ['高速', '切换', '多普勒', '稀疏基站'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.HIGHWAY,
      duration: 600,
      avgSpeed: 115,
      numBaseStations: 3,
      kpiCount: 3,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-04-15T14:00:00Z',
  },

  // 场景3: 上海南京路隧道
  {
    id: 'scenario-003',
    name: '上海南京路隧道穿越',
    description: '上海延安路隧道穿越场景，测试信号遮挡和弱覆盖',
    category: ScenarioCategory.ENVIRONMENT,
    taxonomy: {
      source: 'real-world',
      geographyType: 'tunnel',
      region: '上海延安路隧道',
      purpose: 'reliability',
      network: 'LTE',
      complexity: 'advanced',
      tags: ['隧道', '遮挡', '弱覆盖', '信号恢复'],
    },
    summary: {
      networkType: NetworkType.LTE,
      environmentType: EnvironmentType.TUNNEL,
      duration: 240,
      avgSpeed: 52,
      numBaseStations: 3,
      kpiCount: 2,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: false, digitalTwin: true },
    createdAt: '2024-05-25T10:00:00Z',
  },

  // 场景4: 深圳科技园区覆盖
  {
    id: 'scenario-004',
    name: '深圳科技园区覆盖验证',
    description: '深圳南山科技园区，中密度建筑，测试覆盖完整性',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'real-world',
      geographyType: 'urban',
      region: '深圳市南山区科技园',
      purpose: 'coverage',
      network: '5G NR FR1',
      complexity: 'intermediate',
      tags: ['科技园', '覆盖', '中密度建筑'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MICRO,
      duration: 480,
      avgSpeed: 30,
      numBaseStations: 2,
      kpiCount: 2,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-06-15T10:00:00Z',
  },

  // 场景5: 郊区低速移动
  {
    id: 'scenario-005',
    name: '郊区低速移动场景',
    description: '典型郊区环境，低密度建筑，测试大范围覆盖',
    category: ScenarioCategory.PERFORMANCE,
    taxonomy: {
      source: 'synthetic',
      geographyType: 'suburban',
      region: '通用郊区环境',
      purpose: 'coverage',
      network: '5G NR FR1',
      complexity: 'basic',
      tags: ['郊区', '低密度', '大范围覆盖'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.SUBURBAN,
      duration: 600,
      avgSpeed: 40,
      numBaseStations: 2,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-07-01T10:00:00Z',
  },

  // 场景6: 室内停车场
  {
    id: 'scenario-006',
    name: '室内停车场穿透测试',
    description: '地下停车场环境，测试室内穿透损耗',
    category: ScenarioCategory.ENVIRONMENT,
    taxonomy: {
      source: 'synthetic',
      geographyType: 'indoor',
      region: '典型商业综合体地下停车场',
      purpose: 'coverage',
      network: 'LTE',
      complexity: 'intermediate',
      tags: ['室内', '穿透', '弱信号', '停车场'],
    },
    summary: {
      networkType: NetworkType.LTE,
      environmentType: EnvironmentType.INDOOR,
      duration: 300,
      avgSpeed: 10,
      numBaseStations: 1,
      kpiCount: 1,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-07-10T10:00:00Z',
  },

  // 场景7: 高速极限测试
  {
    id: 'scenario-007',
    name: '高速极限移动测试',
    description: '200km/h极限高速场景，测试极端多普勒',
    category: ScenarioCategory.EXTREME,
    taxonomy: {
      source: 'synthetic',
      geographyType: 'highway',
      region: '高速测试跑道',
      purpose: 'mobility',
      network: '5G NR FR1',
      complexity: 'extreme',
      tags: ['极限高速', '200km/h', '极端多普勒', '压力测试'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.HIGHWAY,
      duration: 240,
      avgSpeed: 191,
      numBaseStations: 2,
      kpiCount: 2,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: false, digitalTwin: true },
    createdAt: '2024-08-01T10:00:00Z',
  },

  // 场景8: 密集干扰场景
  {
    id: 'scenario-008',
    name: '密集干扰城区场景',
    description: '高密度基站部署区域，测试同频干扰抑制',
    category: ScenarioCategory.EXTREME,
    taxonomy: {
      source: 'synthetic',
      geographyType: 'urban',
      region: '密集城区',
      purpose: 'interference',
      network: '5G NR FR1',
      complexity: 'advanced',
      tags: ['同频干扰', '密集基站', 'ICIC', '干扰协调'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.URBAN_MACRO,
      duration: 360,
      avgSpeed: 25,
      numBaseStations: 4,
      kpiCount: 2,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-08-10T10:00:00Z',
  },

  // 场景9: V2X十字路口
  {
    id: 'scenario-009',
    name: 'V2X十字路口碰撞预警',
    description: '城市十字路口，测试V2X低延迟通信',
    category: ScenarioCategory.FUNCTIONAL,
    taxonomy: {
      source: 'real-world',
      geographyType: 'urban',
      region: '典型城市十字路口',
      purpose: 'latency',
      network: 'C-V2X',
      complexity: 'intermediate',
      tags: ['V2X', '低延迟', '十字路口', '碰撞预警'],
    },
    summary: {
      networkType: NetworkType.C_V2X,
      environmentType: EnvironmentType.URBAN_MICRO,
      duration: 30,
      avgSpeed: 40,
      numBaseStations: 1,
      kpiCount: 2,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-09-05T10:00:00Z',
  },

  // 场景10: 连续切换压力测试
  {
    id: 'scenario-010',
    name: '连续切换压力测试',
    description: '密集基站部署高速公路，频繁切换场景',
    category: ScenarioCategory.EXTREME,
    taxonomy: {
      source: 'synthetic',
      geographyType: 'highway',
      region: '密集基站高速公路',
      purpose: 'handover',
      network: '5G NR FR1',
      complexity: 'advanced',
      tags: ['频繁切换', '压力测试', '累积误差', '稳定性'],
    },
    summary: {
      networkType: NetworkType.NR_FR1,
      environmentType: EnvironmentType.HIGHWAY,
      duration: 600,
      avgSpeed: 108,
      numBaseStations: 10,
      kpiCount: 3,
    },
    isComplete: true,
    isValidated: true,
    canExecute: { ota: true, conducted: true, digitalTwin: true },
    createdAt: '2024-09-10T10:00:00Z',
  },
]

// ========== 场景详情映射 ==========

export const scenarioDetailsMap: Record<string, RoadTestScenarioDetail> = {
  'scenario-001': scenario_beijing_cbd,
  'scenario-002': scenario_highway_g2,
  'scenario-003': scenario_shanghai_tunnel,
  'scenario-004': scenario_shenzhen_tech_park,
  'scenario-005': scenario_suburban_lowspeed,
  'scenario-006': scenario_indoor_parking,
  'scenario-007': scenario_extreme_highspeed,
  'scenario-008': scenario_dense_interference,
  'scenario-009': scenario_v2x_intersection,
  'scenario-010': scenario_continuous_handover,
}

// ========== 辅助函数 ==========

/**
 * 根据ID获取场景详情
 */
export function getScenarioById(id: string): RoadTestScenarioDetail | undefined {
  return scenarioDetailsMap[id]
}

/**
 * 根据筛选条件获取场景列表
 */
export function filterScenarios(filters: {
  source?: 'real-world' | 'synthetic' | 'standard-derived'
  geographyType?: 'urban' | 'suburban' | 'highway' | 'tunnel' | 'indoor' | 'rural'
  purpose?: string
  network?: string
  complexity?: 'basic' | 'intermediate' | 'advanced' | 'extreme'
  tags?: string[]
}): RoadTestScenario[] {
  return scenarioList.filter((scenario) => {
    if (filters.source && scenario.taxonomy.source !== filters.source) return false
    if (filters.geographyType && scenario.taxonomy.geographyType !== filters.geographyType) return false
    if (filters.purpose && scenario.taxonomy.purpose !== filters.purpose) return false
    if (filters.network && scenario.taxonomy.network !== filters.network) return false
    if (filters.complexity && scenario.taxonomy.complexity !== filters.complexity) return false
    if (filters.tags && !filters.tags.some((tag) => scenario.taxonomy.tags.includes(tag))) return false
    return true
  })
}

/**
 * 获取所有场景的统计信息
 */
export function getScenarioStatistics() {
  return {
    total: scenarioList.length,
    bySource: {
      realWorld: scenarioList.filter((s) => s.taxonomy.source === 'real-world').length,
      synthetic: scenarioList.filter((s) => s.taxonomy.source === 'synthetic').length,
    },
    byGeography: {
      urban: scenarioList.filter((s) => s.taxonomy.geographyType === 'urban').length,
      highway: scenarioList.filter((s) => s.taxonomy.geographyType === 'highway').length,
      tunnel: scenarioList.filter((s) => s.taxonomy.geographyType === 'tunnel').length,
      suburban: scenarioList.filter((s) => s.taxonomy.geographyType === 'suburban').length,
      indoor: scenarioList.filter((s) => s.taxonomy.geographyType === 'indoor').length,
    },
    byComplexity: {
      basic: scenarioList.filter((s) => s.taxonomy.complexity === 'basic').length,
      intermediate: scenarioList.filter((s) => s.taxonomy.complexity === 'intermediate').length,
      advanced: scenarioList.filter((s) => s.taxonomy.complexity === 'advanced').length,
      extreme: scenarioList.filter((s) => s.taxonomy.complexity === 'extreme').length,
    },
  }
}
