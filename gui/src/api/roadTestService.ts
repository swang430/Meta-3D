/**
 * Virtual Road Test API Service
 *
 * API client for road test scenarios, topologies, and executions
 */

import apiClient from './client'
import type {
  RoadTestScenario,
  ScenarioSummary,
  TestExecution,
  ExecutionSummary,
  TestStatus,
  ScenarioCategory,
  TestMode,
  ExecutionStatus,
} from '../types/roadTest'

const BASE_URL = '/road-test'

// ===== Scenario APIs =====

export interface ListScenariosParams {
  category?: ScenarioCategory
  tags?: string
  source?: 'standard' | 'custom'
}

export async function fetchScenarios(params?: ListScenariosParams): Promise<ScenarioSummary[]> {
  const response = await apiClient.get<ScenarioSummary[]>(`${BASE_URL}/scenarios`, { params })
  return response.data
}

export async function fetchScenarioDetail(scenarioId: string): Promise<RoadTestScenario> {
  const response = await apiClient.get<RoadTestScenario>(`${BASE_URL}/scenarios/${scenarioId}`)
  return response.data
}

export async function createScenario(scenario: Partial<RoadTestScenario>): Promise<RoadTestScenario> {
  const response = await apiClient.post<RoadTestScenario>(`${BASE_URL}/scenarios`, scenario)
  return response.data
}

export async function updateScenario(
  scenarioId: string,
  updates: Partial<RoadTestScenario>
): Promise<RoadTestScenario> {
  const response = await apiClient.put<RoadTestScenario>(`${BASE_URL}/scenarios/${scenarioId}`, updates)
  return response.data
}

export async function deleteScenario(scenarioId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/scenarios/${scenarioId}`)
}

// ===== Execution APIs =====

export interface ListExecutionsParams {
  mode?: TestMode
  status?: ExecutionStatus
}

export async function fetchExecutions(params?: ListExecutionsParams): Promise<ExecutionSummary[]> {
  const response = await apiClient.get<ExecutionSummary[]>(`${BASE_URL}/executions`, { params })
  return response.data
}

export async function fetchExecutionDetail(executionId: string): Promise<TestExecution> {
  const response = await apiClient.get<TestExecution>(`${BASE_URL}/executions/${executionId}`)
  return response.data
}

export async function createExecution(data: {
  mode: TestMode
  scenario_id: string
  topology_id?: string
  config?: Record<string, any>
  notes?: string
}): Promise<TestExecution> {
  const response = await apiClient.post<TestExecution>(`${BASE_URL}/executions`, data)
  return response.data
}

export async function controlExecution(
  executionId: string,
  action: 'start' | 'pause' | 'resume' | 'stop',
  parameters?: Record<string, any>
): Promise<{ status: string }> {
  const response = await apiClient.post(`${BASE_URL}/executions/${executionId}/control`, {
    action,
    parameters,
  })
  return response.data
}

export async function fetchExecutionStatus(executionId: string): Promise<TestStatus> {
  const response = await apiClient.get<TestStatus>(`${BASE_URL}/executions/${executionId}/status`)
  return response.data
}

// ===== System APIs =====

export interface SystemCapabilities {
  digital_twin: {
    available: boolean
    max_bandwidth_mhz: number
    max_mimo_order: string
    acceleration_factor: number
  }
  conducted: {
    available: boolean
    max_bandwidth_mhz: number
    max_mimo_order: string
    requires_topology: boolean
  }
  ota: {
    available: boolean
    max_bandwidth_mhz: number
    max_mimo_order: string
    requires_mpac: boolean
  }
}

export async function fetchCapabilities(): Promise<SystemCapabilities> {
  const response = await apiClient.get<SystemCapabilities>(`${BASE_URL}/capabilities`)
  return response.data
}
