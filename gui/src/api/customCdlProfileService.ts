/**
 * CustomCDLProfile (自定义 CDL 簇编辑) CRUD service (P2-15)。
 *
 * 平行 dutProfileService.ts: 手写类型 mirror 后端 CustomCDLProfile schema, 走 apiClient
 * (运行时连真实后端)。后端 router prefix=/custom-cdl-profiles。簇字段映射 ChannelEgine
 * CDLClusterSpec。
 *
 * 用途: ① 规划期 operator 建/管自定义 CDL (簇级参数); ② TestCase 配置 (MIMOOTAConfigForm)
 *      选 cdl_profile_id → 后端 input_mode=custom → ChannelEgine 合成反映自定义簇。
 */
import apiClient from './client'

/** 一个 CDL 簇 (mirror 后端 CDLClusterInput / ChannelEgine CDLClusterSpec)。 */
export interface CDLClusterInput {
  delay_s: number
  power_linear: number
  aoa_deg: number
  aod_deg: number
  zoa_deg?: number
  zod_deg?: number
  as_aoa_deg?: number
  as_aod_deg?: number
  as_zoa_deg?: number
  as_zod_deg?: number
  xpr_db?: number | null
  initial_phases_rad?: number[] | null
  num_rays?: number
}

/** 后端 CustomCDLProfileResponse 的镜像。 */
export interface CustomCDLProfile {
  id: string
  name: string
  is_active: boolean
  description?: string | null
  center_frequency_hz?: number | null
  pathloss_db?: number | null
  is_los?: boolean | null
  k_factor_db?: number | null
  ue_velocity_mps?: number[] | null
  clusters: CDLClusterInput[]
}

/** POST /custom-cdl-profiles 请求体 (mirror CustomCDLProfileCreate)。name + clusters 必填。 */
export interface CustomCDLProfileCreatePayload {
  name: string
  clusters: CDLClusterInput[]
  description?: string | null
  center_frequency_hz?: number | null
  pathloss_db?: number | null
  is_los?: boolean | null
  k_factor_db?: number | null
  ue_velocity_mps?: number[] | null
  created_by?: string | null
}

/** PUT /custom-cdl-profiles/{id} (mirror Update, exclude_unset PATCH 语义)。 */
export type CustomCDLProfileUpdatePayload = Partial<CustomCDLProfileCreatePayload> & {
  is_active?: boolean
}

export async function fetchCustomCDLProfiles(
  includeInactive = false,
): Promise<CustomCDLProfile[]> {
  const res = await apiClient.get<CustomCDLProfile[]>('/custom-cdl-profiles', {
    params: { include_inactive: includeInactive },
  })
  return res.data
}

export async function fetchCustomCDLProfile(id: string): Promise<CustomCDLProfile> {
  const res = await apiClient.get<CustomCDLProfile>(`/custom-cdl-profiles/${id}`)
  return res.data
}

export async function createCustomCDLProfile(
  payload: CustomCDLProfileCreatePayload,
): Promise<CustomCDLProfile> {
  const res = await apiClient.post<CustomCDLProfile>('/custom-cdl-profiles', payload)
  return res.data
}

export async function updateCustomCDLProfile(
  id: string,
  payload: CustomCDLProfileUpdatePayload,
): Promise<CustomCDLProfile> {
  const res = await apiClient.put<CustomCDLProfile>(`/custom-cdl-profiles/${id}`, payload)
  return res.data
}

/** 默认软删 (is_active=false); hard=true 物理删。 */
export async function deleteCustomCDLProfile(id: string, hard = false): Promise<void> {
  await apiClient.delete(`/custom-cdl-profiles/${id}`, { params: { hard } })
}

/** 一个新簇的默认值 (对齐后端 Pydantic CDLClusterInput 默认)。 */
export const DEFAULT_CLUSTER: CDLClusterInput = {
  delay_s: 0,
  power_linear: 1,
  aoa_deg: 0,
  aod_deg: 0,
  zoa_deg: 90,
  zod_deg: 90,
  as_aoa_deg: 0,
  as_aod_deg: 0,
  as_zoa_deg: 0,
  as_zod_deg: 0,
  xpr_db: null,
  num_rays: 20,
}
