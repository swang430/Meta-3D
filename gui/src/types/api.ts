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

export type ProbePosition = {
  azimuth: number  // 方位角（度）0-360
  elevation: number  // 仰角（度）-90-90
  radius: number  // 半径（米）
}

export type Probe = {
  id: string
  probe_number: number
  name: string | null
  ring: number  // 1-4
  polarization: string  // "V" | "H"
  position: ProbePosition
  is_active: boolean
  is_connected: boolean
  status: string  // "idle" | "active" | "error" | "calibrating"
  hardware_id: string | null
  channel_port: number | null
  last_calibration_date: string | null
  calibration_status: string  // "valid" | "expired" | "invalid" | "unknown"
  calibration_data: Record<string, any> | null
  frequency_range_mhz: Record<string, number> | null
  max_power_dbm: number | null
  gain_db: number | null
  notes: string | null
  created_at: string
  updated_at: string | null
  created_by: string | null
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
  name: string
  description?: string
  version?: string
  dut_info?: Record<string, any>
  test_environment?: Record<string, any>
  scenario_id?: string
  test_case_ids?: string[]
  priority?: number
  created_by: string
  notes?: string
  tags?: string[]
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
