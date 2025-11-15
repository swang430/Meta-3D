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
  const response = await client.post<{ probe: CreateProbePayload }>('/probes', payload)
  return response.data.probe
}

export const updateProbe = async (id: string, payload: UpdateProbePayload) => {
  const response = await client.put<{ probe: CreateProbePayload }>(`/probes/${id}`, payload)
  return response.data.probe
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
  const response = await client.get<SequenceLibraryResponse>('/sequence/library')
  return response.data
}

export const fetchTestTemplates = async (): Promise<TestTemplatesResponse> => {
  const response = await client.get<TestTemplatesResponse>('/tests/templates')
  return response.data
}

export const fetchTestCases = async (): Promise<TestCasesResponse> => {
  const response = await client.get<TestCasesResponse>('/tests/cases')
  return response.data
}

export const fetchTestPlans = async (): Promise<TestPlanListResponse> => {
  const response = await client.get<TestPlanListResponse>('/tests/plans')
  return response.data
}

export const fetchTestPlan = async (planId: string): Promise<TestPlanResponse> => {
  const response = await client.get<TestPlanResponse>(`/tests/plans/${planId}`)
  return response.data
}

export const createTestPlan = async (payload: CreatePlanPayload): Promise<TestPlanResponse> => {
  const response = await client.post<TestPlanResponse>('/tests/plans', payload)
  return response.data
}

export const reorderTestPlans = async (
  payload: ReorderPlanQueuePayload,
): Promise<ReorderPlanQueueResponse> => {
  const response = await client.post<ReorderPlanQueueResponse>('/tests/plans/reorder', payload)
  return response.data
}

export const updateTestPlan = async (
  planId: string,
  payload: UpdatePlanPayload,
): Promise<TestPlanResponse> => {
  const response = await client.put<TestPlanResponse>(`/tests/plans/${planId}`, payload)
  return response.data
}

export const appendPlanStep = async (
  planId: string,
  payload: AppendSequencePayload,
): Promise<TestPlanResponse> => {
  const response = await client.post<TestPlanResponse>(`/tests/plans/${planId}/steps/append`, payload)
  return response.data
}

export const reorderPlanStep = async (
  planId: string,
  payload: ReorderSequencePayload,
): Promise<TestPlanResponse> => {
  const response = await client.post<TestPlanResponse>(`/tests/plans/${planId}/steps/reorder`, payload)
  return response.data
}

export const removePlanStep = async (planId: string, stepId: string): Promise<TestPlanResponse> => {
  const response = await client.delete<TestPlanResponse>(`/tests/plans/${planId}/steps/${stepId}`)
  return response.data
}

export const deleteTestPlan = async (planId: string): Promise<DeletePlanResponse> => {
  const response = await client.delete<DeletePlanResponse>(`/tests/plans/${planId}`)
  return response.data
}

export const fetchRecentTests = async (): Promise<RecentTestsResponse> => {
  const response = await client.get<RecentTestsResponse>('/tests/recent')
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
  const response = await client.put<{ category: InstrumentCategory }>(
    `/instruments/${categoryKey}`,
    payload,
  )
  return response.data.category
}

export const createTestCaseFromPlan = async (
  payload: CreateTestCaseFromPlanPayload,
): Promise<CreateTestCaseResponse> => {
  const response = await client.post<CreateTestCaseResponse>('/tests/cases', payload)
  return response.data
}

export const createTestCase = async (
  payload: CreateTestCasePayload,
): Promise<CreateTestCaseResponse> => {
  const response = await client.post<CreateTestCaseResponse>('/tests/cases/new', payload)
  return response.data
}

export const fetchTestCaseDetail = async (caseId: string): Promise<TestCaseResponse> => {
  const response = await client.get<TestCaseResponse>(`/tests/cases/${caseId}`)
  return response.data
}

export const deleteTestCase = async (caseId: string): Promise<DeleteTestCaseResponse> => {
  const response = await client.delete<DeleteTestCaseResponse>(`/tests/cases/${caseId}`)
  return response.data
}
