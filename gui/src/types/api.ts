export type SystemStatusItem = {
  label: string
  value: string
  detail: string
}

export type AlertSeverity = 'info' | 'warning' | 'critical'

export type AlertItem = {
  id: string
  title: string
  severity: AlertSeverity
  timestamp: string
}

export type MetricTrend = '↑' | '↓' | '→' | string

export type MetricItem = {
  label: string
  value: string
  trend?: MetricTrend
  id?: string
}

export type Probe = {
  id: string
  ring: string
  polarization: string
  position: string
}

export type InstrumentStatus = 'available' | 'offline' | 'reserved' | 'maintenance'

export type InstrumentModel = {
  id: string
  vendor: string
  model: string
  summary: string
  interfaces: string[]
  capabilities: string[]
  bandwidth?: string
  channels?: string
  status: InstrumentStatus
}

export type InstrumentConnection = {
  endpoint?: string
  controller?: string
  notes?: string
}

export type InstrumentCategory = {
  key: string
  label: string
  description: string
  tags?: string[]
  selectedModelId: string | null
  connection: InstrumentConnection
  models: InstrumentModel[]
}

export type SequenceStep = {
  id: string
  title: string
  meta: string
  description?: string
  templateId?: string
  parameters?: Record<string, string>
}

export type SequenceLibraryItem = SequenceStep

export type TestTemplate = {
  id: string
  name: string
  dut: string
  createdAt: string
}

export type TestCase = TestTemplate & {
  category?: string
  tags?: string[]
  description?: string

  // 场景关联信息（可选）- 标记是否由虚拟路测场景生成
  linkedScenario?: {
    scenarioId: string
    mode: 'ota' | 'conducted' | 'digital_twin'
    generatedAt: string
  }
}

export type TestCaseDetail = TestCase & {
  steps: SequenceStep[]
}

export type RecentTest = {
  id: string
  name: string
  dut: string
  result: string
  date: string
}

export type ReportTemplate = {
  id: string
  name: string
  format: string
  lastUpdated: string
}

export type DashboardResponse = {
  systemStatus: SystemStatusItem[]
  activeAlerts: AlertItem[]
  liveMetrics: MetricItem[]
}

export type ProbesResponse = {
  probes: Probe[]
}

export type SequenceStepsResponse = {
  steps: SequenceStep[]
}

export type SequenceLibraryResponse = {
  library: SequenceLibraryItem[]
}

export type TestTemplatesResponse = {
  templates: TestTemplate[]
}

export type TestCasesResponse = {
  cases: TestCase[]
}

export type RecentTestsResponse = {
  recentTests: RecentTest[]
}

export type ReportTemplatesResponse = {
  reportTemplates: ReportTemplate[]
}

export type MonitoringFeedsResponse = {
  feeds: MetricItem[]
}

export type DemoRunStep = {
  id: string
  title: string
  goal: string
  duration: string
  deliverables: string[]
  kpis: string[]
}

export type DemoRunEvent = {
  id: string
  offsetMs: number
  stepIndex: number
  level: 'INFO' | 'WARN' | 'DEBUG'
  message: string
  metrics?: MetricItem[]
  checkpoint?: {
    summary: string
    progress: string
  }
  result?: DemoRunResult
}

export type DemoRunResult = {
  verdict: '通过' | '失败' | '告警'
  summary: string
  metrics: Array<{
    label: string
    baseline: string
    measured: string
    status: 'ok' | 'warn' | 'alert'
  }>
  attachments: Array<{
    name: string
    type: string
    size: string
  }>
  recommendations: string[]
}

export type DemoRunPlan = {
  id: string
  templateId: string
  templateName: string
  description: string
  totalDuration: string
  steps: DemoRunStep[]
  timeline: DemoRunEvent[]
  result: DemoRunResult
}

export type DemoRunPlanResponse = {
  plan: DemoRunPlan
}

export type TestPlanSummary = {
  id: string
  name: string
  caseId: string
  caseName: string
  status: string
  updatedAt: string
  owner?: string
}

export type TestPlanDetail = {
  id: string
  name: string
  caseId: string
  caseName: string
  status: string
  updatedAt: string
  notes?: string
  steps: SequenceStep[]
}

export type TestPlanListResponse = {
  plans: TestPlanSummary[]
}

export type TestPlanResponse = {
  plan: TestPlanDetail
}

export type CreateProbePayload = Probe

export type UpdateProbePayload = Omit<Probe, 'id'>

export type ReorderSequencePayload = {
  fromId: string
  toId: string | '__end__'
}

export type AppendSequencePayload = {
  libraryId: string
}

export type CreatePlanPayload = {
  caseId: string
  name?: string
}

export type UpdatePlanPayload = {
  name?: string
  status?: string
  notes?: string
  steps?: SequenceStep[]
}

export type ReorderPlanQueuePayload = {
  planId: string
  direction: 'up' | 'down' | 'top' | 'bottom'
}

export type ReorderPlanQueueResponse = TestPlanListResponse

export type DeletePlanResponse = {
  success: boolean
}

export type CreateTestCaseFromPlanPayload = {
  sourcePlanId: string
  name: string
  category: string
  dut: string
  tags?: string[]
  description?: string
  caseId?: string
  steps?: SequenceStep[]
}

export type CreateTestCasePayload = {
  name: string
  category: string
  dut: string
  tags?: string[]
  description?: string
  blueprint?: string[]
}

export type TestCaseResponse = {
  testCase: TestCaseDetail
}

export type CreateTestCaseResponse = {
  testCase: TestCaseDetail
}

export type DeleteTestCaseResponse = {
  success: boolean
}

export type InstrumentsResponse = {
  categories: InstrumentCategory[]
}

export type UpdateInstrumentPayload = {
  modelId?: string
  connection?: InstrumentConnection
}

export type InstrumentCategoryResponse = {
  category: InstrumentCategory
}
