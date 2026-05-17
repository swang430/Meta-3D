import client from './client'
import type {
  AppendSequencePayload,
  InstrumentCategory,
  CreateProbePayload,
  CreatePlanPayload,
  DashboardResponse,
  DemoRunPlanResponse,
  CreateTestCaseFromPlanPayload,
  CreateTestCasePayload,
  CreateTestCaseResponse,
  DeleteTestCaseResponse,
  MonitoringFeedsResponse,
  ProbesResponse,
  RecentTestsResponse,
  ReportTemplatesResponse,
  ReorderSequencePayload,
  ReorderPlanQueuePayload,
  ReorderPlanQueueResponse,
  SequenceLibraryResponse,
  TestCasesResponse,
  TestCaseResponse,
  TestPlanListResponse,
  TestPlanResponse,
  TestTemplatesResponse,
  UpdatePlanPayload,
  UpdateProbePayload,
  UpdateInstrumentPayload,
  InstrumentsResponse,
  DeletePlanResponse,
  ChamberConfiguration,
  ChamberListResponse,
  ChamberPresetsResponse,
  ChamberFromPresetPayload,
  CreateChamberPayload,
  UpdateChamberPayload,
  RequiredCalibrationsResponse,
  LinkBudgetResponse,
} from '../types/api'

export const fetchDashboard = async (): Promise<DashboardResponse> => {
  const response = await client.get<DashboardResponse>('/dashboard')
  return response.data
}

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

export const replaceProbes = async (probes: CreateProbePayload[]): Promise<ProbesResponse> => {
  const response = await client.put<ProbesResponse>('/probes/bulk', { probes })
  return response.data
}

export const fetchSequenceLibrary = async (): Promise<SequenceLibraryResponse> => {
  const response = await client.get<SequenceLibraryResponse>('/test-sequences')
  return response.data
}

export const fetchTestTemplates = async (): Promise<TestTemplatesResponse> => {
  const response = await client.get<TestTemplatesResponse>('/test-plans/cases?is_template=true')
  return response.data
}

export const fetchTestCases = async (): Promise<TestCasesResponse> => {
  const response = await client.get<TestCasesResponse>('/test-plans/cases')
  return response.data
}

export const fetchTestPlans = async (): Promise<TestPlanListResponse> => {
  const response = await client.get<TestPlanListResponse>('/test-plans')
  return response.data
}

export const fetchTestPlan = async (planId: string): Promise<TestPlanResponse> => {
  const response = await client.get<TestPlanResponse>(`/test-plans/${planId}`)
  return response.data
}

export const createTestPlan = async (payload: CreatePlanPayload): Promise<TestPlanResponse> => {
  const response = await client.post<TestPlanResponse>('/test-plans', payload)
  return response.data
}

export const reorderTestPlans = async (
  payload: ReorderPlanQueuePayload,
): Promise<ReorderPlanQueueResponse> => {
  const response = await client.post<ReorderPlanQueueResponse>('/test-plans/queue/reorder', payload)
  return response.data
}

export const updateTestPlan = async (
  planId: string,
  payload: UpdatePlanPayload,
): Promise<TestPlanResponse> => {
  const response = await client.patch<TestPlanResponse>(`/test-plans/${planId}`, payload)
  return response.data
}

export const appendPlanStep = async (
  planId: string,
  payload: AppendSequencePayload,
): Promise<TestPlanResponse> => {
  const response = await client.post<TestPlanResponse>(`/test-plans/${planId}/steps`, payload)
  return response.data
}

export const reorderPlanStep = async (
  planId: string,
  payload: ReorderSequencePayload,
): Promise<TestPlanResponse> => {
  const response = await client.post<TestPlanResponse>(`/test-plans/${planId}/steps/reorder`, payload)
  return response.data
}

export const removePlanStep = async (planId: string, stepId: string): Promise<TestPlanResponse> => {
  const response = await client.delete<TestPlanResponse>(`/test-plans/${planId}/steps/${stepId}`)
  return response.data
}

export const deleteTestPlan = async (planId: string): Promise<DeletePlanResponse> => {
  const response = await client.delete<DeletePlanResponse>(`/test-plans/${planId}`)
  return response.data
}

export const fetchRecentTests = async (): Promise<RecentTestsResponse> => {
  // TODO: 后端需要实现 /test-executions/recent 端点
  const response = await client.get<RecentTestsResponse>('/test-executions/recent')
  return response.data
}

export const fetchReportTemplates = async (): Promise<ReportTemplatesResponse> => {
  const response = await client.get<ReportTemplatesResponse>('/reports/templates')
  return response.data
}

export const fetchDemoRunPlan = async (): Promise<DemoRunPlanResponse> => {
  const response = await client.get<DemoRunPlanResponse>('/tests/demo-run')
  return response.data
}

export const fetchMonitoringFeeds = async (): Promise<MonitoringFeedsResponse> => {
  const response = await client.get<MonitoringFeedsResponse>('/monitoring/feeds')
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

export interface ChannelModelEntry {
  filename: string
  label: string
  description: string | null
  type: string // smu / rtc / asc / unknown
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
  label?: string
  description?: string
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

export const setPlanTopologyProfile = async (
  planId: string,
  profileId: string | null,
): Promise<SetPlanTopologyProfileResult> => {
  const response = await client.put<SetPlanTopologyProfileResult>(
    `/test-plans/${planId}/topology-profile`,
    { profile_id: profileId },
  )
  return response.data
}

export const createTestCaseFromPlan = async (
  payload: CreateTestCaseFromPlanPayload,
): Promise<CreateTestCaseResponse> => {
  const response = await client.post<CreateTestCaseResponse>('/test-plans/cases', payload)
  return response.data
}

export const createTestCase = async (
  payload: CreateTestCasePayload,
): Promise<CreateTestCaseResponse> => {
  const response = await client.post<CreateTestCaseResponse>('/test-plans/cases', payload)
  return response.data
}

export const fetchTestCaseDetail = async (caseId: string): Promise<TestCaseResponse> => {
  const response = await client.get<TestCaseResponse>(`/test-plans/cases/${caseId}`)
  return response.data
}

export const deleteTestCase = async (caseId: string): Promise<DeleteTestCaseResponse> => {
  const response = await client.delete<DeleteTestCaseResponse>(`/test-plans/cases/${caseId}`)
  return response.data
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
}): Promise<ChamberListResponse> => {
  const response = await client.get<ChamberListResponse>('/chambers', { params })
  return response.data
}

/**
 * 获取当前激活的暗室配置
 */
export const fetchActiveChamber = async (): Promise<ChamberConfiguration> => {
  const response = await client.get<ChamberConfiguration>('/chambers/active')
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
 * 激活指定暗室配置
 */
export const activateChamber = async (chamberId: string): Promise<ChamberConfiguration> => {
  const response = await client.post<ChamberConfiguration>(`/chambers/${chamberId}/activate`)
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
