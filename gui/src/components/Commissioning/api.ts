/**
 * Commissioning API
 */
import client from '../../api/client'
import {
  buildCreateSessionBody,
  type CreateSessionParams,
} from './sessionBody'
import type { FrozenExecutionQualification } from '../../types/api'

export {
  buildCreateSessionBody,
  DEFAULT_COMMISSIONING_ENGINE_MODE,
  type CreateSessionBody,
  type CreateSessionParams,
} from './sessionBody'
export {
  LTE_TRANSMISSION_MODES,
  type LteTransmissionMode,
} from '../TestCaseConfig/carrierTruth'

export interface CommissioningExecutionConfig extends Record<string, unknown> {
  base_station_adapter_profile_freeze?: {
    resolution?: { adapter?: string }
    cmw500_lte_2x2_formal_capability?: {
      instrument_connection_id: string
      enabled: boolean
      updated_at: string | null
    }
  }
}

export interface SessionResponse {
  session_id: string
  phase: string
  phase_statuses: Record<string, 'pending' | 'running' | 'waiting' | 'completed' | 'failed' | 'skipped'>
  overall_progress: number
  config: CommissioningExecutionConfig
  started_at: string | null
  completed_at: string | null
  precheck: Record<string, unknown> | null
  reference: Record<string, unknown> | null
  mimo_test: Record<string, unknown> | null
  analysis: Record<string, unknown> | null
  report_id: string | null
  execution_qualification: FrozenExecutionQualification | null
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
export const createSession = async (params: CreateSessionParams = {}) => {
  return client.post<SessionResponse>(
    '/commissioning/sessions',
    buildCreateSessionBody(params),
  )
}

export const getSession = async (sessionId: string) => {
  return client.get<SessionResponse>(`/commissioning/sessions/${sessionId}`)
}

export const runPhase = async (sessionId: string, phaseName: string) => {
  return client.post<{ phase: string; status: string; result: unknown }>(`/commissioning/sessions/${sessionId}/phase/${phaseName}`)
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
 * DUT 身份元数据登记（可选）。
 *
 * 标准 MIMO OTA 吞吐量执行不再靠运行前登记满足连接门：MEASURE 会按
 * TestCase 初始化 UXM/F64/开关矩阵并在最终测量态读取 CONN。这个接口
 * 保留给 IMSI/车型追溯和 SIM 身份核对；调用时读取的 UE 状态只是即时参考。
 *
 * ⚠ **`session_id` 就是 `execution_id`** —— 后端
 * `commissioning.py` 的 `_execution_to_session_response()` 写的是
 * `session_id=str(execution.id)`。这里直接拿它当路径参数，**别再去
 * 找一个叫 execution_id 的字段**，SessionResponse 里没有那个名字。
 *
 * ⚠ 本接口**总是成功写记录**：查不到 UE 只会让 `rrc_connected=false`
 * 并往 `warnings` 里塞原因。所以"调用成功"不代表正式 attach 已完成；
 * 调用方仍须把即时状态如实显示，不能拿 `success` 冒充"DUT 已就位"。
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
