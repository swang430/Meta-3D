/**
 * SIMProfile (SIM/eSIM 身份+鉴权声明) CRUD service (P2-13 Phase 3)。
 *
 * 平行 dutProfileService。⚠️ 凭据 ki/opc 是 write-only: 响应**不返回原始值**, 只给
 * ki_masked (后4位) + ki_set (是否已设); 编辑时不传 ki = 保持原值, 传新值才改 (见后端 #140)。
 *
 * 合法值跟后端 sim_profile_service 对齐: 调制算法 {MILENAGE,TUAK,XOR}; card_kind
 * {test_sim,operator_test,commercial}; sim_form {usim,esim}。commercial 卡不存 ki。
 */
import apiClient from './client'

export const SIM_AUTH_ALGORITHMS = ['MILENAGE', 'TUAK', 'XOR']
export const SIM_CARD_KINDS = ['test_sim', 'operator_test', 'commercial']
export const SIM_FORMS = ['usim', 'esim']

/** 后端 SIMProfileResponse 镜像 (ki/opc 已脱敏, 无原始值)。 */
export interface SIMProfile {
  id: string
  name: string
  is_active: boolean
  description?: string | null
  imsi?: string | null
  iccid?: string | null
  mcc?: string | null
  mnc?: string | null
  auth_algorithm?: string | null
  card_kind?: string | null
  sim_form?: string | null
  eid?: string | null
  esim_profile_id?: string | null
  extra_metadata?: Record<string, unknown> | null
  // 脱敏凭据指示 (无原始 ki/opc)
  ki_masked?: string | null
  opc_masked?: string | null
  ki_set?: boolean
  opc_set?: boolean
}

/** POST /sim-profiles 请求体。name 必填; ki/opc 明文写入 (commercial 不可带 ki)。 */
export interface SIMProfileCreatePayload {
  name: string
  description?: string | null
  imsi?: string | null
  iccid?: string | null
  mcc?: string | null
  mnc?: string | null
  ki?: string | null
  opc?: string | null
  auth_algorithm?: string | null
  card_kind?: string | null
  sim_form?: string | null
  eid?: string | null
  esim_profile_id?: string | null
  extra_metadata?: Record<string, unknown> | null
  created_by?: string | null
}

/**
 * PUT /sim-profiles/{id}。exclude_unset PATCH 语义: 只改带的字段。
 * ⚠️ ki/opc 不传 = 保持原值 (凭据不必回传); 传新值才改; 显式 null 才清空。
 */
export type SIMProfileUpdatePayload = Partial<SIMProfileCreatePayload> & {
  is_active?: boolean
}

export async function fetchSIMProfiles(includeInactive = false): Promise<SIMProfile[]> {
  const res = await apiClient.get<SIMProfile[]>('/sim-profiles', {
    params: { include_inactive: includeInactive },
  })
  return res.data
}

export async function fetchSIMProfile(id: string): Promise<SIMProfile> {
  const res = await apiClient.get<SIMProfile>(`/sim-profiles/${id}`)
  return res.data
}

export async function createSIMProfile(
  payload: SIMProfileCreatePayload,
): Promise<SIMProfile> {
  const res = await apiClient.post<SIMProfile>('/sim-profiles', payload)
  return res.data
}

export async function updateSIMProfile(
  id: string,
  payload: SIMProfileUpdatePayload,
): Promise<SIMProfile> {
  const res = await apiClient.put<SIMProfile>(`/sim-profiles/${id}`, payload)
  return res.data
}

/** 默认软删 (is_active=false); hard=true 物理删。 */
export async function deleteSIMProfile(id: string, hard = false): Promise<void> {
  await apiClient.delete(`/sim-profiles/${id}`, { params: { hard } })
}
