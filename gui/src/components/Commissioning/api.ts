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
    precheck_strict_frequency?: boolean
    precheck_strict_emulation_file?: boolean
    precheck_strict_switch_mode?: boolean
    precheck_strict_cell_config?: boolean
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
    // P2-11: "强制跳过严格门" = 统一的暗室首测 (路径 A) bypass —— 一次降级**全部**
    // 6 道 strict 门 (cal/dut/频率/.smu/switch mode/cell_config), 否则真仪表 bring-up 会
    // 撞上它们 (只对真硬件生效, mock 空跑本就 N/A)。Phase 6 cell_config 门 (#114/#124/#126)
    // 此前漏接 (feedback_strict_gate_extend_bypass_toggle 母题)。镜像 test_commissioning_strict_gate_overrides。
    body.precheck_strict_dut = false
    body.precheck_strict_cal = false
    body.precheck_strict_frequency = false
    body.precheck_strict_emulation_file = false
    body.precheck_strict_switch_mode = false
    body.precheck_strict_cell_config = false
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

// U-5 借鉴: 暗室首测前逐设备快速自检 (连接 + 响应主动探测), 先单独验各仪表通再跑首测
export interface DeviceSelfcheckItem {
  category: string
  connected: boolean
  responsive: boolean
  detail?: string | null
}
export interface DeviceSelfcheckResult {
  all_ready: boolean
  devices: DeviceSelfcheckItem[]
  message: string
}
export const deviceSelfcheck = async () => {
  return client.post<DeviceSelfcheckResult>('/commissioning/device-selfcheck')
}
