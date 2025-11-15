/**
 * 虚拟路测 - 核心类型定义
 * 导出所有虚拟路测相关的类型
 */

// ========== 基础枚举 ==========

// 测试模式
export const TestMode = {
  DIGITAL_TWIN: 'digital_twin',
  CONDUCTED: 'conducted',
  OTA: 'ota'
} as const

export type TestMode = typeof TestMode[keyof typeof TestMode]

// 场景分类
export const ScenarioCategory = {
  STANDARD_3GPP: '3GPP',
  STANDARD_CTIA: 'CTIA',
  STANDARD_5GAA: '5GAA',
  FUNCTIONAL: 'functional',
  PERFORMANCE: 'performance',
  ENVIRONMENT: 'environment',
  EXTREME: 'extreme',
  CUSTOM: 'custom'
} as const

export type ScenarioCategory = typeof ScenarioCategory[keyof typeof ScenarioCategory]

// ========== 场景类型（从scenario.ts导出）==========

// 导出场景相关的所有类型
export * from './scenario'

// ========== 测试配置 ==========

// 网络拓扑定义（传导测试用）
export interface NetworkTopology {
  id: string
  name: string
  type: 'SISO' | 'MIMO_2x2' | 'MIMO_4x4' | 'MIMO_8x8' | 'custom'
}

// 测试配置
export interface TestConfig {
  mode: TestMode
  scenarioId: string  // 引用场景ID
  topology?: NetworkTopology
}

// ========== 测试执行 ==========

// 测试执行句柄
export interface ExecutionHandle {
  executionId: string
  mode: TestMode
  scenarioId: string
  status: 'initializing' | 'running' | 'paused' | 'stopped' | 'completed' | 'failed'
  startTime: string
  progress?: {
    currentStep: number
    totalSteps: number
    elapsedTime: number  // 秒
  }
}
