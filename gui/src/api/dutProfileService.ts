/**
 * DUTProfile (被测设备自声明能力) CRUD service。
 *
 * 平行 labProfileService.ts: 手写类型 mirror 后端 DUTProfileResponse/Create/Update,
 * 走 apiClient (运行时连真实后端)。后端 router prefix=/dut-profiles。
 *
 * 用途: ① 规划期 operator 建/管 DUT 能力档案 (本 service 的 CRUD);
 *      ② TestCase 配置 (MIMOOTAConfigForm) 选 dut_profile_id → precheck section 2.3
 *         拿 TestCase 请求 (层数/调制) 跟 DUT **声明**比, 请求 > 声明提前 fail。
 *
 * 合法值跟后端 dut_profile_service._validate 对齐 (改一处同步两处):
 *   调制 {QPSK,16QAM,64QAM,256QAM,1024QAM}; 双工 {TDD,FDD,BOTH}; 层数 > 0。
 */
import apiClient from './client'

/** 调制声明合法集 — 跟后端 _MODULATIONS 对齐。 */
export const DUT_MODULATION_OPTIONS = ['QPSK', '16QAM', '64QAM', '256QAM', '1024QAM']
/** 双工声明合法集 — 跟后端 _DUPLEX 对齐。 */
export const DUT_DUPLEX_OPTIONS = ['TDD', 'FDD', 'BOTH']

/** 后端 DUTProfileResponse 的镜像。 */
export interface DUTProfile {
  id: string
  name: string
  is_active: boolean
  description?: string | null
  manufacturer?: string | null
  model_name?: string | null
  max_dl_layers?: number | null
  max_ul_layers?: number | null
  max_modulation_dl?: string | null
  max_modulation_ul?: string | null
  ue_category?: string | null
  duplex_mode?: string | null
  supported_bands?: string[] | null
  extra_metadata?: Record<string, unknown> | null
}

/** POST /dut-profiles 请求体 (mirror DUTProfileCreate)。name 必填。 */
export interface DUTProfileCreatePayload {
  name: string
  description?: string | null
  manufacturer?: string | null
  model_name?: string | null
  max_dl_layers?: number | null
  max_ul_layers?: number | null
  max_modulation_dl?: string | null
  max_modulation_ul?: string | null
  ue_category?: string | null
  duplex_mode?: string | null
  supported_bands?: string[] | null
  extra_metadata?: Record<string, unknown> | null
  created_by?: string | null
}

/**
 * PUT /dut-profiles/{id} 请求体 (mirror DUTProfileUpdate)。
 * 后端 exclude_unset PATCH 语义: 只改显式带的字段; 显式 null = 清空该声明。
 */
export type DUTProfileUpdatePayload = Partial<DUTProfileCreatePayload> & {
  is_active?: boolean
}

export async function fetchDUTProfiles(includeInactive = false): Promise<DUTProfile[]> {
  const res = await apiClient.get<DUTProfile[]>('/dut-profiles', {
    params: { include_inactive: includeInactive },
  })
  return res.data
}

export async function fetchDUTProfile(id: string): Promise<DUTProfile> {
  const res = await apiClient.get<DUTProfile>(`/dut-profiles/${id}`)
  return res.data
}

export async function createDUTProfile(
  payload: DUTProfileCreatePayload,
): Promise<DUTProfile> {
  const res = await apiClient.post<DUTProfile>('/dut-profiles', payload)
  return res.data
}

export async function updateDUTProfile(
  id: string,
  payload: DUTProfileUpdatePayload,
): Promise<DUTProfile> {
  const res = await apiClient.put<DUTProfile>(`/dut-profiles/${id}`, payload)
  return res.data
}

/** 默认软删 (is_active=false); hard=true 物理删。 */
export async function deleteDUTProfile(id: string, hard = false): Promise<void> {
  await apiClient.delete(`/dut-profiles/${id}`, { params: { hard } })
}
