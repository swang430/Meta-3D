import client from './client'
import type {
  InstrumentCategory,
  CreateProbePayload,
  DemoRunPlanResponse,
  ProbesResponse,
  UpdateProbePayload,
  UpdateInstrumentPayload,
  InstrumentsResponse,
  ChamberConfiguration,
  ChamberListResponse,
  ChamberPresetsResponse,
  ChamberFromPresetPayload,
  CreateChamberPayload,
  UpdateChamberPayload,
  RequiredCalibrationsResponse,
  LinkBudgetResponse,
  HALReadinessResponse,
  TestExecutionListResponse,
  SystemLogTailResponse,
  DashboardAlertSummary,
} from '../types/api'
import type { components as ApiComponents } from '../types/api.generated'

type ContractTestCaseCreate = ApiComponents['schemas']['TestCaseCreate']
type ContractTestCaseResponse = ApiComponents['schemas']['TestCaseResponse']
type ContractHALReadinessResponse = ApiComponents['schemas']['HALReadinessResponse']

export const fetchProbes = async (): Promise<ProbesResponse> => {
  const response = await client.get<ProbesResponse>('/probes')
  return response.data
}

export const createProbe = async (payload: CreateProbePayload) => {
  const response = await client.post<any>('/probes', payload)
  return response.data
}

export const updateProbe = async (id: string, payload: UpdateProbePayload) => {
  const response = await client.put<any>(`/probes/${id}`, payload)
  return response.data
}

export const deleteProbe = async (id: string) => {
  await client.delete(`/probes/${id}`)
  return true
}

export const replaceProbes = async (
  probes: CreateProbePayload[],
  chamberId: string,
): Promise<ProbesResponse> => {
  // chamber_config_id 必传: 批量替换按**单个暗室**作用域 (后端拒绝全局替换, 防止一次
  // 清空所有暗室的探头)。chamberId 由调用方传入当前激活暗室。
  const response = await client.put<ProbesResponse>('/probes/bulk', {
    probes,
    chamber_config_id: chamberId,
  })
  return response.data
}

// ARCH-1 S4b: fetchSequenceLibrary 删除 —— 后端 /test-sequences 四条路由随
// 计划链拆除。它此前只被 App.tsx import 未调用 (noUnusedLocals:false 不报),
// 谁把它接回组件就是运行时 404。⚠️ G5 门只守 /test-plans 前缀, 覆盖不到
// /test-sequences —— 这一处靠人删, 不靠门。

// ============================================================
// P2-8: Operational Cockpit data sources
// ============================================================

/**
 * ① 系统就绪带 — composite HAL readiness snapshot.
 * `available=false` means HAL-owned driver/subnet data is unavailable;
 * request-time LabProfile and calibration sections remain live.
 */
export const fetchReadiness = async (labProfileId?: string, testCaseId?: string): Promise<HALReadinessResponse> => {
  const response = await client.get<ContractHALReadinessResponse>('/instruments/hal/readiness', {
    params: labProfileId || testCaseId
      ? {
          ...(labProfileId ? { lab_profile_id: labProfileId } : {}),
          ...(testCaseId ? { test_case_id: testCaseId } : {}),
        }
      : undefined,
  })
  return response.data
}

/**
 * ② 运行态 — terminal-state execution history (completed/failed/cancelled).
 * NOT a live-running stream; the cockpit surfaces it as "最近执行".
 */
export const fetchTestExecutions = async (
  params?: { limit?: number; skip?: number; status?: string },
): Promise<TestExecutionListResponse> => {
  const response = await client.get<TestExecutionListResponse>('/test-executions', { params })
  return response.data
}

/**
 * ④ 实时日志 — tail a structured log file with optional level / keyword filter.
 */
export const fetchSystemLogsTail = async (params?: {
  filename?: string
  lines?: number
  level?: string
  keyword?: string
  session_id?: string
  /** P1-36：按一次测试执行过滤（跨多请求 / 后台任务）。 */
  execution_id?: string
}): Promise<SystemLogTailResponse> => {
  const response = await client.get<SystemLogTailResponse>('/system-logs/tail', { params })
  return response.data
}

/**
 * P1-43：显式读取一页更早日志。与 `/tail` 分离，严禁放入自动轮询。
 */
export const fetchSystemLogsHistory = async (params: {
  cursor: string
  filename?: string
  lines?: number
  level?: string
  keyword?: string
  session_id?: string
  execution_id?: string
}): Promise<SystemLogTailResponse> => {
  const response = await client.get<SystemLogTailResponse>('/system-logs/history', { params })
  return response.data
}

/**
 * ④ 实时告警 — active alerts ordered by severity.
 */
/**
 * ④ 实时告警 — counts of active alerts by severity (top-of-zone tally).
 */
export const fetchAlertSummary = async (): Promise<DashboardAlertSummary> => {
  const response = await client.get<DashboardAlertSummary>('/dashboard/alerts/summary')
  return response.data
}

export const fetchDemoRunPlan = async (): Promise<DemoRunPlanResponse> => {
  const response = await client.get<DemoRunPlanResponse>('/tests/demo-run')
  return response.data
}

export const fetchInstrumentCatalog = async (): Promise<InstrumentsResponse> => {
  const response = await client.get<InstrumentsResponse>('/instruments/catalog')
  return response.data
}

export const updateInstrumentCategory = async (
  categoryKey: string,
  payload: UpdateInstrumentPayload,
): Promise<InstrumentCategory> => {
  const response = await client.put<InstrumentCategory>(
    `/instruments/${categoryKey}`,
    payload,
  )
  return response.data
}

export const certifyBaseStationSite = async (
  connectionId: string,
  payload: { source_execution_id: string; certified_by: string; reason: string },
): Promise<import('../types/api').BaseStationSiteCertification> => {
  const response = await client.put(
    `/instruments/connections/${connectionId}/base-station-site-certification`,
    payload,
  )
  return response.data
}

export const revokeBaseStationSiteCertification = async (
  connectionId: string,
  payload: { revoked_by: string; reason: string },
): Promise<import('../types/api').BaseStationSiteCertification> => {
  const response = await client.put(
    `/instruments/connections/${connectionId}/base-station-site-certification/revoke`,
    payload,
  )
  return response.data
}

export interface ChannelModelEntry {
  filename: string
  label: string
  description: string | null
  type: string // smu / rtc / asc / unknown
  scd_id?: string | null // P2-12 slice 4: SCD 派生 entry 的 SCD UUID (手敲条目为 null)
  channel_asset_id?: string | null
  radio_technology: 'nr5g' | 'lte' | 'legacy_unknown'
  channel_kind: 'nr_arfcn' | 'lte_dl_earfcn' | 'legacy_unknown'
  band?: string | null
  nr_arfcn?: number | null
  lte_dl_earfcn?: number | null
}

export interface ChannelModelsListResult {
  items: ChannelModelEntry[]
  reason: string | null // "driver_not_loaded" | "not_a_channel_emulator" | null
}

export const fetchChannelModels = async (
  categoryKey: string,
): Promise<ChannelModelsListResult> => {
  // Operator-curated list of selectable .smu/.rtc files. F64's ATE Server
  // doesn't expose MMEM SCPI and its FTP is closed (verified at CAICT
  // 2026-05-13), so we don't probe the instrument — we surface the
  // operator's list from connection_params['available_channel_models'].
  const response = await client.get<ChannelModelsListResult>(
    `/instruments/${categoryKey}/channel-models`,
  )
  return response.data
}

export interface AddChannelModelPayload {
  filename: string
  label: string
  description: string
  radio_technology: 'nr5g' | 'lte'
  channel_kind: 'nr_arfcn' | 'lte_dl_earfcn'
  band: string
  nr_arfcn?: number
  lte_dl_earfcn?: number
}

export const addChannelModel = async (
  categoryKey: string,
  payload: AddChannelModelPayload,
): Promise<ChannelModelsListResult> => {
  const response = await client.post<ChannelModelsListResult>(
    `/instruments/${categoryKey}/channel-models`,
    payload,
  )
  return response.data
}

export const removeChannelModel = async (
  categoryKey: string,
  filename: string,
): Promise<ChannelModelsListResult> => {
  // encodeURIComponent for filenames with spaces / special chars
  // (operator-supplied — F64 .smu filenames can contain hyphens, dots,
  // sometimes spaces in lab-internal naming conventions).
  const response = await client.delete<ChannelModelsListResult>(
    `/instruments/${categoryKey}/channel-models/${encodeURIComponent(filename)}`,
  )
  return response.data
}

// ============================================================
// P2-1: Topology profile (operator-selectable UXM cell/MIMO config
// templates within a detected Test App)
// ============================================================

export interface TopologyProfileEntry {
  profile_id: string
  name: string
  description: string
  category: string                // "siso" / "mimo" / "calibration"
  compatible_test_apps: string[]  // empty = any
  compatible_with_current_test_app?: boolean | null
  is_system_preset?: boolean      // P2-1 Phase 2.1
}

export interface TopologyProfilesListResult {
  items: TopologyProfileEntry[]
  current_test_app?: string | null
  selected_topology_profile_id?: string | null
  reason?: string | null // "not_a_uxm" | null
}

export interface SelectTopologyProfileResult {
  persisted: boolean
  profile_id?: string | null
  applied_now: boolean
  apply_skipped_reason?: string | null
  test_app?: string | null
}

// P2-1 Phase 2.1: full topology profile row — returned by CRUD endpoints.
export interface TopologyProfileDetail {
  profile_id: string
  name: string
  description?: string | null
  category: string
  band: string
  frequency_mhz: number
  bandwidth_mhz: number
  scs_khz: number
  duplex: string
  arfcn?: number | null
  mimo_layers: number
  mimo_port_preset: string
  dl_power_dbm: number
  ssb_power_dbm: number
  modulation: string
  target_mcs: number
  sched_algo: string
  enable_amc: boolean
  tdd_pattern: string
  tdd_period: string
  harq_max_trans: number
  harq_processes: number
  csi_rs_ports?: number | null
  stat_count: number
  cell_id: string
  state_file?: string | null
  compatible_test_apps: string[]
  notes?: string | null
  is_system_preset: boolean
  created_by?: string | null
}

// All fields optional except `name` on create. Allowlisted on the
// backend; unknown keys silently dropped by Pydantic at the request
// schema layer.
export type CreateTopologyProfilePayload = Partial<Omit<TopologyProfileDetail,
  'profile_id' | 'is_system_preset'>> & { name: string }
export type UpdateTopologyProfilePayload = Partial<Omit<TopologyProfileDetail,
  'profile_id' | 'is_system_preset' | 'created_by'>>

export const fetchTopologyProfiles = async (
  categoryKey: string,
): Promise<TopologyProfilesListResult> => {
  const response = await client.get<TopologyProfilesListResult>(
    `/instruments/${categoryKey}/topology-profiles`,
  )
  return response.data
}

export const selectTopologyProfile = async (
  categoryKey: string,
  profileId: string | null,
): Promise<SelectTopologyProfileResult> => {
  const response = await client.put<SelectTopologyProfileResult>(
    `/instruments/${categoryKey}/topology-profile`,
    { profile_id: profileId },
  )
  return response.data
}

// P2-1 Phase 2.1: CRUD on topology profile entities themselves.
// The four endpoints map 1:1 to the backend operations; the GUI
// editor surface (TopologyEditor component, deferred to Phase 2.2)
// consumes these.

// P2-1 Phase 2.2: full single-profile detail for the editor modal.
// List endpoint returns truncated TopologyProfileEntry; this returns
// the full 25+ field TopologyProfileDetail needed to populate the form.
export const fetchTopologyProfile = async (
  categoryKey: string,
  profileId: string,
): Promise<TopologyProfileDetail> => {
  const response = await client.get<TopologyProfileDetail>(
    `/instruments/${categoryKey}/topology-profiles/${encodeURIComponent(profileId)}`,
  )
  return response.data
}

export const createTopologyProfile = async (
  categoryKey: string,
  payload: CreateTopologyProfilePayload,
): Promise<TopologyProfileDetail> => {
  const response = await client.post<TopologyProfileDetail>(
    `/instruments/${categoryKey}/topology-profiles`,
    payload,
  )
  return response.data
}

export const updateTopologyProfile = async (
  categoryKey: string,
  profileId: string,
  payload: UpdateTopologyProfilePayload,
): Promise<TopologyProfileDetail> => {
  const response = await client.put<TopologyProfileDetail>(
    `/instruments/${categoryKey}/topology-profiles/${encodeURIComponent(profileId)}`,
    payload,
  )
  return response.data
}

export const deleteTopologyProfile = async (
  categoryKey: string,
  profileId: string,
): Promise<void> => {
  await client.delete(
    `/instruments/${categoryKey}/topology-profiles/${encodeURIComponent(profileId)}`,
  )
}

export const duplicateTopologyProfile = async (
  categoryKey: string,
  profileId: string,
): Promise<TopologyProfileDetail> => {
  const response = await client.post<TopologyProfileDetail>(
    `/instruments/${categoryKey}/topology-profiles/${encodeURIComponent(profileId)}/duplicate`,
  )
  return response.data
}

// P2-1 Phase 2.3: dedicated set/clear endpoint for plan-level topology
// override. Mirrors the binding-level `selectTopologyProfile` shape.
// Use this rather than the generic plan update PATCH for clear (the
// PATCH endpoint's `value is not None` filter blocks explicit-null
// clearing).

export interface SetPlanTopologyProfileResult {
  persisted: boolean
  profile_id: string | null
}

export const createTestCase = async (
  payload: ContractTestCaseCreate,
): Promise<ContractTestCaseResponse> => {
  const response = await client.post<ContractTestCaseResponse>('/test-plans/cases', payload)
  return response.data
}

export const fetchTestCaseDetail = async (caseId: string): Promise<ContractTestCaseResponse> => {
  const response = await client.get<ContractTestCaseResponse>(`/test-plans/cases/${caseId}`)
  return response.data
}

export const deleteTestCase = async (caseId: string): Promise<void> => {
  await client.delete(`/test-plans/cases/${caseId}`)
}

// ============================================================
// Chamber Configuration API (暗室配置 API)
// ============================================================

/**
 * 获取所有暗室预设模板
 */
export const fetchChamberPresets = async (): Promise<ChamberPresetsResponse> => {
  const response = await client.get<ChamberPresetsResponse>('/chambers/presets')
  return response.data
}

/**
 * 获取暗室配置列表
 */
export const fetchChamberConfigurations = async (params?: {
  skip?: number
  limit?: number
  activeOnly?: boolean
  lab_profile_id?: string
}): Promise<ChamberListResponse> => {
  const response = await client.get<ChamberListResponse>('/chambers', { params })
  return response.data
}

/**
 * 取**全部**暗室配置 (分页聚合)。
 * 后端 /chambers 的 limit 上限为 100, 默认仅 20; 暗室总数可能 > 100 (现场已 124 个),
 * 单次请求会漏掉靠后的暗室 (如 CAICT-FS 在第 84 位 → 默认 limit 20 根本选不到),
 * 导致下拉框里"暗室凭空消失"。这里按 limit=100 翻页直到取满 total。
 */
export const fetchAllChamberConfigurations = async (
  labProfileId?: string,
): Promise<ChamberConfiguration[]> => {
  const pageSize = 100
  let skip = 0
  const all: ChamberConfiguration[] = []
  for (;;) {
    const page = await fetchChamberConfigurations({
      skip,
      limit: pageSize,
      lab_profile_id: labProfileId,
    })
    const items = page.items ?? []
    all.push(...items)
    if (items.length < pageSize || all.length >= (page.total ?? all.length)) break
    skip += pageSize
  }
  return all
}

/**
 * 获取所选 LabProfile 绑定的当前暗室配置
 */
export const fetchActiveChamber = async (
  labProfileId?: string,
): Promise<ChamberConfiguration> => {
  const response = await client.get<ChamberConfiguration>('/chambers/active', {
    params: { lab_profile_id: labProfileId },
  })
  return response.data
}

/**
 * 获取指定暗室配置
 */
export const fetchChamber = async (chamberId: string): Promise<ChamberConfiguration> => {
  const response = await client.get<ChamberConfiguration>(`/chambers/${chamberId}`)
  return response.data
}

/**
 * 从预设模板创建暗室配置
 */
export const createChamberFromTemplate = async (
  payload: ChamberFromPresetPayload
): Promise<ChamberConfiguration> => {
  const response = await client.post<ChamberConfiguration>('/chambers/from-preset', payload)
  return response.data
}

/**
 * 创建自定义暗室配置
 */
export const createCustomChamber = async (
  payload: CreateChamberPayload
): Promise<ChamberConfiguration> => {
  const response = await client.post<ChamberConfiguration>('/chambers', payload)
  return response.data
}

/**
 * 更新暗室配置
 */
export const updateChamber = async (
  chamberId: string,
  payload: UpdateChamberPayload
): Promise<ChamberConfiguration> => {
  const response = await client.put<ChamberConfiguration>(`/chambers/${chamberId}`, payload)
  return response.data
}

/**
 * 将指定暗室绑定为所选 LabProfile 的当前暗室
 */
export const activateChamber = async (
  chamberId: string,
  labProfileId?: string,
): Promise<ChamberConfiguration> => {
  const response = await client.post<ChamberConfiguration>(
    `/chambers/${chamberId}/activate`,
    undefined,
    { params: { lab_profile_id: labProfileId } },
  )
  return response.data
}

/**
 * 复制暗室配置 — 系统预设是只读的，要修改先复制成可编辑副本
 */
export const duplicateChamber = async (chamberId: string): Promise<ChamberConfiguration> => {
  const response = await client.post<ChamberConfiguration>(`/chambers/${chamberId}/duplicate`)
  return response.data
}

/**
 * 删除暗室配置
 */
export const deleteChamber = async (chamberId: string): Promise<{ message: string }> => {
  const response = await client.delete<{ message: string }>(`/chambers/${chamberId}`)
  return response.data
}

/**
 * 获取暗室配置所需的校准项目
 */
export const fetchChamberCalibration = async (
  chamberId: string
): Promise<RequiredCalibrationsResponse> => {
  const response = await client.get<RequiredCalibrationsResponse>(
    `/chambers/${chamberId}/required-calibrations`
  )
  return response.data
}

/**
 * 计算链路预算
 */
export const calculateLinkBudget = async (
  chamberId: string,
  params?: {
    frequency_mhz?: number
    dut_tx_power_dbm?: number
    dut_sensitivity_dbm?: number
    ce_output_dbm?: number
  }
): Promise<LinkBudgetResponse> => {
  const response = await client.get<LinkBudgetResponse>(
    `/chambers/${chamberId}/link-budget`,
    { params }
  )
  return response.data
}

// ============================================================
// U-5: Positioner (转台) standalone 控制 (调试维护 / 现场转台验证)
// 后端 app/api/instrument.py positioner 段; 遵循 HAL 操作端点不进 openapi.yaml 先例,
// 手写 type (类比 MIMOOTAConfigForm)。
// ============================================================

export interface PositionerResult {
  ok: boolean
  azimuth: number | null
  elevation: number | null
  reason?: string | null
  message?: string | null
}

export interface PositionerSweepPoint {
  target: number
  actual_azimuth: number | null
  actual_elevation: number | null
  within_tolerance: boolean | null
}

export interface PositionerSweepResult {
  ok: boolean
  points: PositionerSweepPoint[]
  reason?: string | null
  message?: string | null
}

export async function positionerHome(): Promise<PositionerResult> {
  const response = await client.post<PositionerResult>('/instruments/positioner/home')
  return response.data
}

export async function positionerMove(azimuth: number, elevation = 0): Promise<PositionerResult> {
  const response = await client.post<PositionerResult>('/instruments/positioner/move', {
    azimuth,
    elevation,
  })
  return response.data
}

export async function positionerPosition(): Promise<PositionerResult> {
  const response = await client.get<PositionerResult>('/instruments/positioner/position')
  return response.data
}

export async function positionerStop(): Promise<PositionerResult> {
  const response = await client.post<PositionerResult>('/instruments/positioner/stop')
  return response.data
}

export async function positionerSweep(
  angles?: number[],
  homeFirst = true,
  toleranceDeg = 0.5,
): Promise<PositionerSweepResult> {
  const payload: Record<string, unknown> = { home_first: homeFirst, tolerance_deg: toleranceDeg }
  if (angles) payload.angles = angles
  const response = await client.post<PositionerSweepResult>(
    '/instruments/positioner/sweep',
    payload,
  )
  return response.data
}
