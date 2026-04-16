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
