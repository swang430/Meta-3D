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
}

export interface DiagnosticRunDetail extends DiagnosticRunSummary {
  params?: Record<string, unknown> | null
  output_excerpt?: string | null
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
