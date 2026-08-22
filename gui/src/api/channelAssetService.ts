/**
 * ChannelAsset (信道资产多态化) CRUD service (P2-16 S1)。
 *
 * 平行 customCdlProfileService.ts / dutProfileService.ts: 手写类型 mirror 后端 ChannelAsset
 * schema, 走 apiClient (运行时连真实后端)。后端 router prefix=/channel-assets。
 *
 * 四源统一: 判别键 source_type 决定 payload 形态 (判别联合体)。payload 多态 (Record), 各
 * source_type 的结构化子类型见下 (供 S4 GUI 构建/编辑)。allowed_targets 派生只读 (§3.1)。
 * 设计见 docs/design/channel-asset-polymorphism-design_V0.1.md。
 */
import apiClient from './client'

export type ChannelSourceType =
  | 'standard_3gpp'
  | 'custom_static'
  | 'rt_dynamic'
  | 'vendor_file'

/** 注入路径 (§3.1 allowed_targets 元素; 派生自 source_type)。 */
export type ChannelTarget = 'asc_baked' | 'b2_parametric' | 'gcm_native'

// —— 多态 payload 子类型 (mirror 后端 service 校验; 供 S4 构建 payload) ——

/** custom_static 的一个簇 (mirror CDLClusterInput)。 */
export interface CDLClusterPayload {
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

/** rt_dynamic 的一条原始 MPDB 射线 (mirror MPCInput; 非聚类后 CDL)。 */
export interface MPCRayPayload {
  delay_s: number
  power_linear: number
  aoa_deg: number
  aod_deg: number
  zoa_deg?: number
  zod_deg?: number
  phase_rad?: number | null
}

export interface StandardPayload {
  cdl_model_name: string
}
/** custom_static: 恰 1 个静态快照。 */
export interface CustomStaticPayload {
  snapshots: [{ clusters: CDLClusterPayload[] }]
}
/** rt_dynamic: 多快照, 每快照一组原始射线。 */
export interface RtDynamicPayload {
  snapshots: Array<{ rays: MPCRayPayload[] }>
  sampling_meta?: Record<string, unknown>
  scenario_meta?: Record<string, unknown>
}
export interface VendorFilePayload {
  scd_config: Record<string, unknown>
}

export type ChannelAssetPayload =
  | StandardPayload
  | CustomStaticPayload
  | RtDynamicPayload
  | VendorFilePayload
  | Record<string, unknown>

/** 后端 ChannelAssetResponse 的镜像。 */
export interface ChannelAsset {
  id: string
  name: string
  source_type: ChannelSourceType
  payload: Record<string, unknown>
  allowed_targets: ChannelTarget[]
  is_active: boolean
  description?: string | null
  canonical_name?: string | null
  derived_from?: string | null
  center_frequency_hz?: number | null
  bandwidth_mhz?: number | null
  is_los?: boolean | null
  k_factor_db?: number | null
  ue_velocity_mps?: number[] | null
  instrument_connection_id?: string | null
  associated_file_path?: string | null
}

export interface SMUProjectSyncItem {
  relative_path: string
  instrument_path: string
  size_bytes: number
  sha256: string
  center_frequencies_hz: Record<string, number>
  primary_center_frequency_hz?: number | null
  scan_status: string
  scan_detail?: string | null
  sync_status: string
  sync_detail: string
  connection_id: string
  asset_id?: string | null
  asset_name?: string | null
  target_arfcn?: number | null
}

export interface SMUProjectSyncPreview {
  connection_id: string
  items: SMUProjectSyncItem[]
  protected_paths: string[]
  total_files: number
  total_bytes: number
}

export interface SMUProjectSyncResult {
  updated_count: number
  already_synced_count: number
  preview: SMUProjectSyncPreview
}

/** POST /channel-assets 请求体 (mirror ChannelAssetCreate)。 */
export interface ChannelAssetCreatePayload {
  name: string
  source_type: ChannelSourceType
  payload: ChannelAssetPayload
  description?: string | null
  canonical_name?: string | null
  derived_from?: string | null
  center_frequency_hz?: number | null
  bandwidth_mhz?: number | null
  is_los?: boolean | null
  k_factor_db?: number | null
  ue_velocity_mps?: number[] | null
  instrument_connection_id?: string | null
  associated_file_path?: string | null
  created_by?: string | null
}

/** PUT /channel-assets/{id} (mirror Update; source_type 不可改, 不含)。 */
export type ChannelAssetUpdatePayload = Partial<
  Omit<ChannelAssetCreatePayload, 'source_type' | 'created_by'>
> & {
  is_active?: boolean
}

export async function fetchChannelAssets(
  opts: { sourceType?: ChannelSourceType; includeInactive?: boolean } = {},
): Promise<ChannelAsset[]> {
  const res = await apiClient.get<ChannelAsset[]>('/channel-assets', {
    params: { source_type: opts.sourceType, include_inactive: opts.includeInactive ?? false },
  })
  return res.data
}

export async function fetchChannelAsset(id: string): Promise<ChannelAsset> {
  const res = await apiClient.get<ChannelAsset>(`/channel-assets/${id}`)
  return res.data
}

export async function createChannelAsset(
  payload: ChannelAssetCreatePayload,
): Promise<ChannelAsset> {
  const res = await apiClient.post<ChannelAsset>('/channel-assets', payload)
  return res.data
}

export async function updateChannelAsset(
  id: string,
  payload: ChannelAssetUpdatePayload,
): Promise<ChannelAsset> {
  const res = await apiClient.put<ChannelAsset>(`/channel-assets/${id}`, payload)
  return res.data
}

/** 默认软删 (is_active=false); hard=true 物理删。 */
export async function deleteChannelAsset(id: string, hard = false): Promise<void> {
  await apiClient.delete(`/channel-assets/${id}`, { params: { hard } })
}

/** 只读扫描服务端配置的 SMB 挂载副本；客户端不能提交路径或频率。 */
export async function scanSMUProjects(): Promise<SMUProjectSyncPreview> {
  const res = await apiClient.post<SMUProjectSyncPreview>('/channel-assets/vendor-files/smu-scan')
  return res.data
}

/** 服务端强制重扫并原子同步；客户端预览不作为真值回传。 */
export async function syncSMUProjects(): Promise<SMUProjectSyncResult> {
  const res = await apiClient.post<SMUProjectSyncResult>('/channel-assets/vendor-files/smu-sync')
  return res.data
}

/** 新簇默认值 (对齐后端 CDLClusterInput 默认), 供 S4 簇编辑器。 */
export const DEFAULT_CDL_CLUSTER: CDLClusterPayload = {
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

/** 新射线默认值 (rt_dynamic), 供 S4。 */
export const DEFAULT_MPC_RAY: MPCRayPayload = {
  delay_s: 0,
  power_linear: 1,
  aoa_deg: 0,
  aod_deg: 0,
  zoa_deg: 90,
  zod_deg: 90,
  phase_rad: null,
}
