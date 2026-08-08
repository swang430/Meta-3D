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
  // 2026-08-07 现场: 只放过**校准证书**那一道门, 其余 7 道照常守着。
  // 为什么要单独一个: `labSmoke` 是一次降级全部 8 道 —— 操作员为了绕开
  // "lab has no active calibration certificate" 打开它, 会**连 DUT 门一起废掉**,
  // 于是刚补的「登记 DUT」按钮形同虚设, P1-9 防对错车保护也没了。
  // 现场实况 (CAICT 2026-08-07): 校准证书未绑 (P0-3 未做完) 但 DUT 可以真 attach,
  // 这两件事本来就该分开决定。
  calBypass?: boolean,
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
    precheck_strict_dut_capability?: boolean
    precheck_strict_sim_identity?: boolean
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
    // P2-11/P2-13: "强制跳过严格门" = 统一的暗室首测 (路径 A) bypass —— 一次降级**全部**
    // 8 道 strict 门 (cal/dut/频率/.smu/switch mode/cell_config/dut_capability/sim_identity),
    // 否则真仪表 bring-up 会撞上它们。dut_capability = DUTProfile 声明门, sim_identity = SIMProfile
    // 防插错卡门 (都规划期/attach 校验), 跟其它门一起 bypass (feedback_strict_gate_extend_bypass_toggle:
    // 加门同步 4 处, 这次提前补)。镜像 test_commissioning_strict_gate_overrides。
    body.precheck_strict_dut = false
    body.precheck_strict_cal = false
    body.precheck_strict_frequency = false
    body.precheck_strict_emulation_file = false
    body.precheck_strict_switch_mode = false
    body.precheck_strict_cell_config = false
    body.precheck_strict_dut_capability = false
    body.precheck_strict_sim_identity = false
  }
  // 只跳校准门 —— 独立于 labSmoke, 两个都开时结果一致 (都是 false), 不冲突。
  // ⚠ 这里**只准写 precheck_strict_cal 一个 flag**。想再放过别的门就各自加一个
  // 独立开关, 别往这个分支里塞 —— 一塞就又变回"一开全废"的 labSmoke, 那正是
  // 本分支要治的东西。
  if (calBypass) {
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

/**
 * DUT attach 登记 —— 补 GUI 侧唯一的入口。
 *
 * 背景：precheck 的严格 DUT 门（`precheck.py` §5b）要求
 * `measurements['dut_attach']` 存在，否则真仪表下必 FAIL；但在此之前
 * **全仓只有 Phases.tsx 里一段提示文字**告诉操作员"自己去 POST"，
 * 没有任何可点的入口 —— 现场只能手敲 curl（2026-08-07 现场实证：
 * execution 1d4a642a 就死在 "DUT attach record missing"）。
 *
 * ⚠ **`session_id` 就是 `execution_id`** —— 后端
 * `commissioning.py` 的 `_execution_to_session_response()` 写的是
 * `session_id=str(execution.id)`。这里直接拿它当路径参数，**别再去
 * 找一个叫 execution_id 的字段**，SessionResponse 里没有那个名字。
 *
 * ⚠ 本接口**总是成功写记录**：查不到 UE 只会让 `rrc_connected=false`
 * 并往 `warnings` 里塞原因。所以"调用成功"≠"门会过"——
 * 严格门还要 `rrc_connected===true` **且** precheck 当下再查一次
 * UE 仍然在线。调用方必须把 `rrc_connected` 如实显示出来，
 * 不能拿 `success` 冒充"DUT 已就位"。
 */
export interface AttachDutRequest {
  imsi: string
  phone_number?: string | null
  dut_model?: string | null
  dut_serial?: string | null
  notes?: string | null
}

export interface AttachDutResponse {
  success: boolean
  execution_id: string
  dut_imsi: string
  rrc_connected: boolean
  ue_info?: Record<string, unknown> | null
  warnings: string[]
  error?: string | null
}

export const attachDut = async (executionId: string, body: AttachDutRequest) => {
  return client.post<AttachDutResponse>(
    `/test-executions/${executionId}/attach-dut`,
    body,
  )
}
