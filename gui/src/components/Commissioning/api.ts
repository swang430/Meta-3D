/**
 * Commissioning API
 */
import client from '../../api/client'

export interface SessionResponse {
  session_id: string
  phase: string
  phase_statuses: Record<string, 'pending' | 'running' | 'waiting' | 'completed' | 'failed' | 'skipped'>
  overall_progress: number
  config: any
  started_at: string | null
  completed_at: string | null
  precheck: any | null
  reference: any | null
  mimo_test: any | null
  analysis: any | null
  report_id: string | null
}

export const createSession = async (engineMode: string = 'mimo_first_asc') => {
  return client.post<SessionResponse>('/commissioning/sessions', { engine_mode: engineMode })
}

export const getSession = async (sessionId: string) => {
  return client.get<SessionResponse>(`/commissioning/sessions/${sessionId}`)
}

export const runPhase = async (sessionId: string, phaseName: string) => {
  return client.post<{ phase: string; status: string; result: any }>(`/commissioning/sessions/${sessionId}/phase/${phaseName}`)
}

export const runAll = async (sessionId: string) => {
  return client.post<SessionResponse>(`/commissioning/sessions/${sessionId}/run-all`)
}
