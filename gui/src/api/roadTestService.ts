/**
 * Virtual Road Test API Service
 *
 * API client for road test scenarios, topologies, and executions
 */

import apiClient from './client'
import type {
  ConductedSelection,
  ConductedCalibrationRecord,
  ConductedPreparation,
  RunnerObservation,
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
  action: 'start' | 'pause' | 'resume' | 'stop' | 'complete',
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

// ===== Report APIs =====

import type { ExecutionReport, PhaseResult, KPISummary } from '../types/roadTest'

export async function fetchExecutionReport(executionId: string): Promise<ExecutionReport> {
  const response = await apiClient.get<ExecutionReport>(`${BASE_URL}/executions/${executionId}/report`)
  return response.data
}

export async function archiveExecutionReport(
  executionId: string
): Promise<{ id: string; title: string; status: string }> {
  const response = await apiClient.post<{ id: string; title: string; status: string }>(
    `${BASE_URL}/executions/${executionId}/archive-report`
  )
  return response.data
}

// ===== Metrics APIs =====

export interface TimeSeriesPoint {
  time_s: number
  position?: { lat: number; lon: number; alt?: number }
  rsrp_dbm?: number
  rsrq_db?: number
  sinr_db?: number
  dl_throughput_mbps?: number
  ul_throughput_mbps?: number
  latency_ms?: number
  event?: string
}

export interface ExecutionMetricsSubmit {
  execution_id: string
  time_series: TimeSeriesPoint[]
  phases: PhaseResult[]
  events: Array<{ time: string; type: string; description: string }>
  kpi_summary: KPISummary[]
}

export async function submitExecutionMetrics(
  executionId: string,
  metrics: Omit<ExecutionMetricsSubmit, 'execution_id'>
): Promise<{ status: string; points_received: number; phases_received: number }> {
  const response = await apiClient.post(`${BASE_URL}/executions/${executionId}/metrics`, {
    execution_id: executionId,
    ...metrics,
  })
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
    simulated_available: boolean
    real_available: boolean
    requires_preparation: boolean
    max_bandwidth_mhz: number | null
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

type ResourceOption = { id: string; name: string; mock_only?: boolean }

export async function fetchConductedOptions() {
  return (await apiClient.get<Record<'labs' | 'topologies' | 'assets', ResourceOption[]>>(
    `${BASE_URL}/conducted/options`)).data
}

export async function fetchConductedCalibrations() {
  return (await apiClient.get<ConductedCalibrationRecord[]>(`${BASE_URL}/conducted/calibrations`)).data
}

export async function fetchConductedCalibration(id: string) {
  return (await apiClient.get<ConductedCalibrationRecord & { evidence_b64: string; readings_b64: string }>(
    `${BASE_URL}/conducted/calibrations/${encodeURIComponent(id)}`)).data
}

export async function registerConductedCalibration(evidence: { report_file: string }) {
  return (await apiClient.post<ConductedCalibrationRecord>(`${BASE_URL}/conducted/calibrations`, evidence)).data
}

export async function prepareConducted(selection: ConductedSelection) {
  return (await apiClient.post<ConductedPreparation>(`${BASE_URL}/conducted/prepare`, selection)).data
}

export async function saveConducted(selection: ConductedSelection) {
  return (await apiClient.post<TestExecution>(`${BASE_URL}/conducted/executions`, selection)).data
}

export async function fetchExecutionObservations(id: string) {
  const response = await apiClient.get<{ observations?: RunnerObservation[] }>(
    `${BASE_URL}/executions/${id}/metrics`)
  return response.data.observations || []
}
