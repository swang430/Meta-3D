/**
 * P3: workshop-tier diagnostics — sequence list/run + audit log read.
 *
 * Sequences themselves live as Python files in api-service/app/diagnostics;
 * the GUI just enumerates them and lets the operator launch one. Results
 * persist to the diagnostic_runs table; this service also exposes the
 * read-only history endpoint.
 */
import apiClient from './client'

export interface SequenceParamSpec {
  name: string
  label: string
  type: 'number' | 'string' | 'boolean'
  default?: number | string | boolean | null
  options?: string[]
}

export interface DiagnosticSequenceMetadata {
  key: string
  name: string
  description: string
  required_categories: string[]
  params_schema: SequenceParamSpec[]
  safe_during_test: boolean
}

export interface SequenceStepResult {
  label: string
  success: boolean
  detail: string
  duration_ms?: number | null
}

export interface SequenceRunResponse {
  diagnostic_run_id: string
  success: boolean
  summary: string
  duration_ms: number
  log: string[]
  steps: SequenceStepResult[]
  extra: Record<string, unknown>
}

export interface DiagnosticRunSummary {
  id: string
  kind: string
  lab_profile_id?: string | null
  target_name: string
  success: boolean
  duration_ms?: number | null
  run_at: string
  run_by?: string | null
  error_message?: string | null
  output_excerpt?: string | null
}

export interface DiagnosticRunDetail extends DiagnosticRunSummary {
  params?: Record<string, unknown> | null
  hal_trace_log_path?: string | null
}

export interface DiagnosticRunListResponse {
  items: DiagnosticRunSummary[]
  total: number
}

export async function listDiagnosticSequences(): Promise<DiagnosticSequenceMetadata[]> {
  const res = await apiClient.get<DiagnosticSequenceMetadata[]>('/diagnostic-sequences')
  return res.data
}

export interface RunSequencePayload {
  lab_profile_id?: string
  operating_mode?: string
  params?: Record<string, unknown>
  run_by?: string
}

export async function runDiagnosticSequence(
  key: string,
  payload: RunSequencePayload,
): Promise<SequenceRunResponse> {
  const res = await apiClient.post<SequenceRunResponse>(
    `/diagnostic-sequences/${encodeURIComponent(key)}/run`,
    payload,
  )
  return res.data
}

export interface ListRunsParams {
  kind?: string
  lab_profile_id?: string
  success?: boolean
  /** Substring filter on target_name. EquipmentManager uses this with
   *  category_key to pull per-instrument SCPI history. */
  target_contains?: string
  limit?: number
  offset?: number
}

export async function listDiagnosticRuns(
  params: ListRunsParams = {},
): Promise<DiagnosticRunListResponse> {
  const res = await apiClient.get<DiagnosticRunListResponse>('/diagnostic-runs', { params })
  return res.data
}

export async function getDiagnosticRun(id: string): Promise<DiagnosticRunDetail> {
  const res = await apiClient.get<DiagnosticRunDetail>(`/diagnostic-runs/${id}`)
  return res.data
}

// ── P3 Phase 3: ad-hoc commissioning + HAL trace ────────────────────────

export type CommissioningPhaseName =
  | 'precheck'
  | 'reference'
  | 'mimo_test'
  | 'analysis'
  | 'report'

export interface AdhocPhaseRequest {
  lab_profile_id?: string
  phase_name: CommissioningPhaseName
  config_overrides?: Record<string, unknown>
  phase_overrides?: Record<string, unknown>
  run_by?: string
}

export interface AdhocPhaseResponse {
  diagnostic_run_id: string
  test_execution_id: string
  phase: string
  status: string
  duration_ms: number
  result: Record<string, unknown>
  error_message?: string | null
}

export async function runAdhocPhase(
  payload: AdhocPhaseRequest,
): Promise<AdhocPhaseResponse> {
  const res = await apiClient.post<AdhocPhaseResponse>(
    '/commissioning/diagnostic/run-phase',
    payload,
  )
  return res.data
}

export interface HALTraceTailResponse {
  log_path: string
  lines: string[]
  total_lines_returned: number
}

export async function fetchHALTraceTail(lines = 200): Promise<HALTraceTailResponse> {
  const res = await apiClient.get<HALTraceTailResponse>(
    '/commissioning/diagnostic/hal-trace-tail',
    { params: { lines } },
  )
  return res.data
}
