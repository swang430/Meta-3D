/**
 * Mock Data Generator for Test Management
 *
 * Generates realistic mock data for development and testing.
 *
 * @version 2.0.0
 */

import type {
  UnifiedTestPlan,
  TestStep,
  TestQueueSummary,
  TestExecutionRecord,
  SequenceLibraryItem,
  TestPlanStatus,
  StepParameter,
} from '../types'

// Helper to generate random ID
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

// Helper to generate random date in past
const randomPastDate = (daysAgo: number = 30) => {
  const now = Date.now()
  const past = now - daysAgo * 24 * 60 * 60 * 1000
  return new Date(past + Math.random() * (now - past)).toISOString()
}

/**
 * Generate mock test plans
 */
export function generateMockTestPlans(count: number = 10): UnifiedTestPlan[] {
  const statuses: TestPlanStatus[] = [
    'draft',
    'ready',
    'queued',
    'running',
    'paused',
    'completed',
    'failed',
    'cancelled',
  ]

  const plans: UnifiedTestPlan[] = []

  for (let i = 0; i < count; i++) {
    const status = statuses[Math.floor(Math.random() * statuses.length)]
    const totalCases = Math.floor(Math.random() * 20) + 5
    const completedCases =
      status === 'completed'
        ? totalCases
        : status === 'running'
        ? Math.floor(totalCases * 0.6)
        : 0
    const failedCases = status === 'failed' ? Math.floor(Math.random() * 3) : 0

    plans.push({
      id: generateId(),
      name: `MIMO OTA 测试计划 ${i + 1}`,
      description: `这是第 ${i + 1} 个测试计划的描述信息`,
      version: '1.0.0',
      status,
      dut_info: {
        model: `Device Model ${i + 1}`,
        serial: `SN${1000 + i}`,
        imei: `${860000000000000 + i}`,
        manufacturer: 'TestManufacturer',
        firmware_version: `v${1 + Math.floor(i / 3)}.0.${i % 10}`,
      },
      test_environment: {
        chamber_id: 'MPAC-001',
        temperature: 25 + Math.random() * 5,
        humidity: 50 + Math.random() * 10,
        atmospheric_pressure: 101.325,
      },
      steps: [],
      test_case_ids: [],
      total_test_cases: totalCases,
      completed_test_cases: completedCases,
      failed_test_cases: failedCases,
      queue_position: status === 'queued' ? i + 1 : undefined,
      priority: Math.floor(Math.random() * 10) + 1,
      estimated_duration_minutes: 60 + Math.random() * 120,
      actual_duration_minutes:
        status === 'completed' ? 60 + Math.random() * 120 : undefined,
      started_at: ['running', 'paused', 'completed', 'failed'].includes(status)
        ? randomPastDate(7)
        : undefined,
      completed_at: ['completed', 'failed', 'cancelled'].includes(status)
        ? randomPastDate(3)
        : undefined,
      created_by: 'TestUser',
      created_at: randomPastDate(30),
      updated_at: randomPastDate(7),
      notes: i % 3 === 0 ? '这是一个测试备注' : undefined,
      tags: i % 2 === 0 ? ['5G', 'MIMO'] : ['LTE', 'Performance'],
    })
  }

  return plans
}

/**
 * Generate mock test steps
 */
export function generateMockTestSteps(planId: string, count: number = 5): TestStep[] {
  const steps: TestStep[] = []
  const categories = ['校准', '测量', '验证', '分析']

  for (let i = 0; i < count; i++) {
    const parameters: Record<string, StepParameter> = {
      frequency: {
        type: 'number',
        label: '频率',
        value: 2400 + i * 100,
        defaultValue: 2400,
        required: true,
        unit: 'MHz',
        validation: {
          min: 2000,
          max: 6000,
        },
      },
      power: {
        type: 'number',
        label: '功率',
        value: -10 + i,
        defaultValue: -10,
        required: true,
        unit: 'dBm',
        validation: {
          min: -30,
          max: 30,
        },
      },
      duration: {
        type: 'number',
        label: '持续时间',
        value: 10,
        defaultValue: 10,
        required: true,
        unit: 's',
        validation: {
          min: 1,
          max: 3600,
        },
      },
      mode: {
        type: 'select',
        label: '模式',
        value: 'auto',
        defaultValue: 'auto',
        required: true,
        validation: {
          options: ['auto', 'manual', 'custom'],
        },
      },
    }

    steps.push({
      id: generateId(),
      order: i,
      sequence_library_id: `seq-${i + 1}`,
      title: `测试步骤 ${i + 1}`,
      description: `这是第 ${i + 1} 个测试步骤的描述`,
      category: categories[i % categories.length],
      parameters,
      timeout_seconds: 300,
      retry_count: 0,
      continue_on_failure: false,
      status: 'pending',
    })
  }

  return steps
}

/**
 * Generate mock queue items
 */
export function generateMockQueue(plans: UnifiedTestPlan[]): TestQueueSummary[] {
  const queuedPlans = plans.filter((p) => p.status === 'queued' || p.status === 'running')

  return queuedPlans.map((plan, index) => ({
    queue_item: {
      id: generateId(),
      test_plan_id: plan.id,
      position: index + 1,
      priority: plan.priority,
      status: plan.status === 'running' ? 'ready' : 'waiting',
      queued_by: 'TestUser',
      queued_at: randomPastDate(1),
    },
    test_plan: {
      id: plan.id,
      name: plan.name,
      status: plan.status,
      priority: plan.priority,
      total_test_cases: plan.total_test_cases,
      completed_test_cases: plan.completed_test_cases,
      failed_test_cases: plan.failed_test_cases,
      created_by: plan.created_by,
      created_at: plan.created_at,
      updated_at: plan.updated_at,
      tags: plan.tags,
    },
  }))
}

/**
 * Generate mock execution history
 */
export function generateMockHistory(count: number = 20): TestExecutionRecord[] {
  const records: TestExecutionRecord[] = []
  const statuses: ('completed' | 'failed' | 'cancelled')[] = [
    'completed',
    'completed',
    'completed',
    'failed',
    'cancelled',
  ]

  for (let i = 0; i < count; i++) {
    const status = statuses[Math.floor(Math.random() * statuses.length)]
    const totalSteps = Math.floor(Math.random() * 10) + 5
    const completedSteps =
      status === 'completed' ? totalSteps : Math.floor(totalSteps * 0.7)
    const failedSteps = status === 'failed' ? Math.floor(Math.random() * 3) + 1 : 0
    const skippedSteps = totalSteps - completedSteps - failedSteps

    records.push({
      id: generateId(),
      test_plan_id: generateId(),
      test_plan_name: `MIMO OTA 测试计划 ${i + 1}`,
      test_plan_version: '1.0.0',
      status,
      total_steps: totalSteps,
      completed_steps: completedSteps,
      failed_steps: failedSteps,
      skipped_steps: skippedSteps,
      started_at: randomPastDate(30),
      completed_at: randomPastDate(25),
      duration_minutes: 60 + Math.random() * 120,
      started_by: 'TestUser',
      success_rate: completedSteps / totalSteps,
      error_summary:
        status === 'failed' ? '部分测试步骤执行失败，详见错误日志' : undefined,
      notes: i % 3 === 0 ? '执行备注信息' : undefined,
    })
  }

  return records.sort(
    (a, b) => new Date(b.completed_at).getTime() - new Date(a.completed_at).getTime(),
  )
}

/**
 * Generate mock sequence library
 */
export function generateMockSequenceLibrary(count: number = 30): SequenceLibraryItem[] {
  const categories = [
    '系统校准',
    '信道测量',
    '性能验证',
    '天线测试',
    '数据采集',
  ]
  const items: SequenceLibraryItem[] = []

  for (let i = 0; i < count; i++) {
    items.push({
      id: `seq-${i + 1}`,
      title: `测试序列 ${i + 1}`,
      description: `这是第 ${i + 1} 个测试序列的描述信息`,
      category: categories[i % categories.length],
      tags: ['MIMO', 'OTA', '5G'],
      defaultParameters: {
        frequency: {
          type: 'number',
          label: '频率',
          value: 2400,
          defaultValue: 2400,
          required: true,
          unit: 'MHz',
        },
      },
      version: '1.0.0',
      author: 'TestAuthor',
      created_at: randomPastDate(180),
      updated_at: randomPastDate(30),
      usage_count: Math.floor(Math.random() * 100),
      popularity_score: Math.floor(Math.random() * 100),
    })
  }

  return items
}

/**
 * Mock data store (in-memory)
 */
export class MockDataStore {
  private plans: UnifiedTestPlan[]
  private steps: Map<string, TestStep[]>
  private history: TestExecutionRecord[]
  private sequenceLibrary: SequenceLibraryItem[]

  constructor() {
    // Initialize with mock data
    this.plans = generateMockTestPlans(15)
    this.steps = new Map()
    this.history = generateMockHistory(25)
    this.sequenceLibrary = generateMockSequenceLibrary(30)

    // Generate steps for each plan
    this.plans.forEach((plan) => {
      this.steps.set(plan.id, generateMockTestSteps(plan.id, 5))
    })
  }

  // Plans
  getPlans() {
    return this.plans
  }

  getPlan(id: string) {
    return this.plans.find((p) => p.id === id)
  }

  createPlan(plan: UnifiedTestPlan) {
    this.plans.push(plan)
    this.steps.set(plan.id, [])
    return plan
  }

  updatePlan(id: string, updates: Partial<UnifiedTestPlan>) {
    const index = this.plans.findIndex((p) => p.id === id)
    if (index !== -1) {
      this.plans[index] = { ...this.plans[index], ...updates }
      return this.plans[index]
    }
    return null
  }

  deletePlan(id: string) {
    const index = this.plans.findIndex((p) => p.id === id)
    if (index !== -1) {
      this.plans.splice(index, 1)
      this.steps.delete(id)
      return true
    }
    return false
  }

  // Steps
  getSteps(planId: string) {
    return this.steps.get(planId) || []
  }

  addStep(planId: string, step: TestStep) {
    const steps = this.steps.get(planId) || []
    steps.push(step)
    this.steps.set(planId, steps)
    return step
  }

  updateStep(planId: string, stepId: string, updates: Partial<TestStep>) {
    const steps = this.steps.get(planId)
    if (steps) {
      const index = steps.findIndex((s) => s.id === stepId)
      if (index !== -1) {
        steps[index] = { ...steps[index], ...updates }
        return steps[index]
      }
    }
    return null
  }

  deleteStep(planId: string, stepId: string) {
    const steps = this.steps.get(planId)
    if (steps) {
      const index = steps.findIndex((s) => s.id === stepId)
      if (index !== -1) {
        steps.splice(index, 1)
        return true
      }
    }
    return false
  }

  // Queue
  getQueue() {
    return generateMockQueue(this.plans)
  }

  // History
  getHistory() {
    return this.history
  }

  // Sequence Library
  getSequenceLibrary() {
    return this.sequenceLibrary
  }

  getSequenceCategories() {
    return Array.from(new Set(this.sequenceLibrary.map((item) => item.category)))
  }
}

// Singleton instance
export const mockDataStore = new MockDataStore()
