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

export interface LabResolutionDetail {
  /** "none" → no active labs in DB; "ambiguous" → ≥2 active labs */
  kind: 'none' | 'ambiguous'
  /** Human-readable, safe to display unchanged */
  message: string
  /** Picker data when kind === "ambiguous". Empty for kind="none". */
  active_labs: Array<{ id: string; name: string }>
}

/**
 * Create a commissioning session. ``labProfileId`` is optional —
 * when omitted, the backend picks the unique active LabProfile if
 * there's exactly one (back-compat). With 0 or ≥2 active labs the
 * call returns **422** with a structured detail (see
 * ``LabResolutionDetail``) that the GUI uses to render a picker.
 *
 * Pre-fix (before factory.py refactor) the 0 / ≥2 paths returned
 * 500 with an unactionable message — operator saw "初始化失败 错误
 * 代码500" with no recovery path.
 */
export const createSession = async (
  engineMode: string = 'mimo_first_asc',
  labProfileId?: string,
  ascSourcePath?: string,
  // Lab-smoke mode: relax the strict precheck gates (P1-8 cal / P1-9 DUT) so a
  // local rehearsal without a real DUT / calibration can get past 系统预检.
  // Omitted (undefined) → backend keeps its strict default (True) → on-site
  // real first-call stays protected. Only sent when the operator opts in.
  labSmoke?: boolean,
) => {
  // 2026-05-18 P0-7: engine_mode='external_asc' requires asc_source_path
  // (operator-supplied .asc directory). For the other two engine modes the
  // field is ignored server-side; we drop it from the payload anyway to keep
  // the request body minimal.
  const body: {
    engine_mode: string
    lab_profile_id?: string
    asc_source_path?: string
    precheck_strict_dut?: boolean
    precheck_strict_cal?: boolean
  } = {
    engine_mode: engineMode,
  }
  if (labProfileId) {
    body.lab_profile_id = labProfileId
  }
  if (engineMode === 'external_asc' && ascSourcePath) {
    body.asc_source_path = ascSourcePath
  }
  if (labSmoke) {
    // Both gates relaxed together — the documented local-rehearsal path
    // (mirrors test_commissioning_{smoke,e2e_p06} setting strict flags False).
    body.precheck_strict_dut = false
    body.precheck_strict_cal = false
  }
  return client.post<SessionResponse>('/commissioning/sessions', body)
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
