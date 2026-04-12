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
  chamber_config_id: string | null
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

// ============================================================
// Chamber Configuration Types (暗室配置类型)
// ============================================================

export type ChamberType = 'type_a' | 'type_b' | 'type_c' | 'type_d' | 'custom'

export type ChamberPresetInfo = {
  type: string
  name: string
  description: string
  chamber_radius_m: number
  num_probes: number
  has_lna: boolean
  has_pa: boolean
  has_duplexer: boolean
  supports_trp: boolean
  supports_tis: boolean
  supports_mimo_ota: boolean
}

export type ChamberConfiguration = {
  id: string
  name: string
  description: string | null
  chamber_type: string
  is_active: boolean

  // 物理参数
  chamber_radius_m: number
  quiet_zone_diameter_m: number | null
  num_probes: number
  num_polarizations: number
  num_rings: number

  // LNA 配置
  has_lna: boolean
  lna_gain_db: number | null
  lna_noise_figure_db: number | null

  // PA 配置
  has_pa: boolean
  pa_gain_db: number | null
  pa_p1db_dbm: number | null

  // 双工器配置
  has_duplexer: boolean
  duplexer_isolation_db: number | null
  duplexer_insertion_loss_db: number | null

  // 转台配置
  has_turntable: boolean
  turntable_max_load_kg: number | null

  // 信道仿真器配置
  has_channel_emulator: boolean
  ce_bidirectional: boolean
  ce_num_ota_ports: number | null
  ce_min_input_dbm: number

  // 频率范围
  freq_min_mhz: number
  freq_max_mhz: number

  // 支持的测试类型
  supports_trp: boolean
  supports_tis: boolean
  supports_mimo_ota: boolean

  // 链路预算参数
  typical_cable_loss_db: number
  probe_gain_dbi: number

  // 元数据
  created_at: string
  updated_at: string | null
  created_by: string | null

  // 计算属性
  supported_tests: string[]
  max_ul_radius_m: number | null
}

export type CreateChamberPayload = Omit<
  ChamberConfiguration,
  'id' | 'is_active' | 'created_at' | 'updated_at' | 'created_by' | 'supported_tests' | 'max_ul_radius_m'
>

export type UpdateChamberPayload = Partial<CreateChamberPayload> & {
  is_active?: boolean
}

export type ChamberFromPresetPayload = {
  preset_type: ChamberType
  name?: string
  chamber_radius_m?: number
  quiet_zone_diameter_m?: number
  num_probes?: number
  lna_gain_db?: number
  lna_noise_figure_db?: number
  pa_gain_db?: number
  pa_p1db_dbm?: number
}

export type ChamberPresetsResponse = {
  presets: ChamberPresetInfo[]
}

export type ChamberListResponse = {
  items: ChamberConfiguration[]
  total: number
}

export type RequiredCalibrationsResponse = {
  chamber_id: string
  chamber_name: string
  required_calibrations: string[]
  optional_calibrations: string[]
}

export type LinkBudgetResponse = {
  chamber_id: string

  // 上行链路
  ul_dut_tx_power_dbm: number
  ul_system_gain_db: number
  ul_max_fspl_db: number
  ul_max_radius_m: number
  ul_margin_db: number

  // 下行链路
  dl_ce_output_dbm: number
  dl_system_gain_db: number
  dl_eirp_dbm: number
  dl_dut_sensitivity_dbm: number
  dl_margin_db: number

  // 评估
  ul_feasible: boolean
  dl_feasible: boolean
  recommendations: string[]
}
