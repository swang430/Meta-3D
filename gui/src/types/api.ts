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

// 'pending_dev' = backend has the catalog row but no real HAL driver
// registered yet (instrument.py:_convert_model assigns this when
// has_real_driver(category, model) is false). Operators must see this
// distinctly from 'available' so they don't pick it expecting real signaling.
export type InstrumentStatus = 'available' | 'offline' | 'reserved' | 'maintenance' | 'pending_dev'

export type InstrumentModel = {
  id: string
  vendor: string
  model: string
  summary: string
  interfaces: string[]
  /** Freeform datasheet-derived badges built from the InstrumentModel
   * row's `capabilities` JSON column (channels, bandwidth, MIMO config,
   * etc). Distinct from `model_capabilities` below. */
  capabilities: string[]
  /** P2-3: canonical capability tokens this model CAN expose, read off
   * `DriverClass.model_capabilities` server-side. Empty list means
   * either no real driver class is registered, or the driver
   * intentionally declared empty (e.g. FS16). Used by binding-edit UI
   * + PreflightModal to surface mismatches before HAL Reload. Optional
   * because older backends don't include the field. */
  model_capabilities?: string[]
  bandwidth?: string | null
  channels?: string | null
  status: InstrumentStatus
}

export type InstrumentConnection = {
  /** DB InstrumentConnection UUID, 供 SCD 等按 connection 关联的 API 用 */
  id?: string | null
  endpoint?: string | null
  controller?: string | null
  notes?: string | null
  connection_params?: Record<string, any> | null
  cmw500_lte_2x2_formal_enabled: boolean
  cmw500_lte_2x2_formal_updated_at: string | null
}

export type Cmw500FormalCapabilityResponse = {
  connection_id: string
  enabled: boolean
  updated_at: string
}

export type Cmw500Lte2x2InternalRoute = {
  pcc_bb_board: string
  rx_connector: string
  rx_converter: string
  tx1_connector: string
  tx1_converter: string
  tx2_connector: string
  tx2_converter: string
}

export type BaseStationAdapterProfile = {
  schema_version: 1
  adapter: 'cmw500'
  lte_2x2_internal_route: Cmw500Lte2x2InternalRoute
}

export type InstrumentConnectionUpdate = {
  endpoint?: string | null
  controller?: string | null
  notes?: string | null
  connection_params?: Record<string, unknown> | null
  base_station_adapter_profile?: BaseStationAdapterProfile | null
}

export type InstrumentCategory = {
  /** DB UUID for this category. Stable identifier used by LabProfile
   *  instrument_bindings, topology editor links, etc. Distinct from
   *  `key` (which is the human-stable string slug like "channelEmulator"). */
  categoryId?: string | null
  key: string
  label: string
  description: string
  tags?: string[]
  isActive?: boolean
  selectedModelId: string | null
  connection: InstrumentConnection
  models: InstrumentModel[]
  usagePhase: string[]
  driverMode: string
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

// MockServer/localStorage 的演示用例，不是 live TestCaseResponse 契约。
export type MockTestCase = {
  id: string
  name: string
  dut: string
  createdAt: string
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

export type MockTestCaseDetail = MockTestCase & {
  steps: SequenceStep[]
}

export type ProbesResponse = {
  total: number
  probes: Probe[]
}

export type SequenceStepsResponse = {
  steps: SequenceStep[]
}

export type SequenceLibraryResponse = {
  library: SequenceLibraryItem[]
}


// ============================================================
// P2-8: Operational Cockpit data sources
// ============================================================

// ── ① 系统就绪带 — GET /instruments/hal/readiness ──
// Shape mirrors api-service HALReadinessResponse (already in openapi.yaml +
// api.generated.ts). Re-declared here as hand-written types to match the
// service.ts convention (service consumes ../types/api, not generated).

// P0-2 D5: 'warn' = 驱动可用但默认配置没落上 (apply 失败 / binding 选择已失效)
// — 仪表当前配置未知, 正式测试前必须走一次下发。不挡路但必须可见 (黄灯)。
export type ReadinessDriverStatus = 'ok' | 'warn' | 'fail' | 'skipped'

// P1-11: when status === 'fail', why. 'network' = TCP preflight couldn't
// reach the host (most likely wrong /24 subnet); 'scpi' = TCP reached but
// the session / *IDN? failed. null/undefined whenever status !== 'fail'.
export type ReadinessFailKind = 'network' | 'scpi'

export type ReadinessDriverRow = {
  category: string
  model: string
  endpoint: string
  status: ReadinessDriverStatus
  detail: string
  extras?: Record<string, unknown>
  fail_kind?: ReadinessFailKind | null
}

// P1-11/P1-13: per-/24-subnet reachability rollup, tri-state via
// (probed, reachable): probed=false → no instrument was network-probed
// (mock-HAL mode, or binding without host:port) → 未探测/unknown, reachable
// is meaningless (do NOT render reachable); probed && reachable → 可达;
// probed && !reachable → 不可达. hint is a runbook string for unreachable
// subnets, null otherwise. cidr 'unknown' buckets unparseable-IP rows.
export type SubnetReachability = {
  cidr: string
  reachable: boolean
  instrument_count: number
  unreachable_count: number
  hint?: string | null
  probed: boolean
}

export type ReadinessLabProfileStatus = 'ok' | 'inactive' | 'missing' | 'ambiguous'

export type ReadinessLabProfile = {
  profile_id?: string | null
  profile_name?: string | null
  is_active: boolean
  status: ReadinessLabProfileStatus
  detail: string
}

export type ReadinessCalibrationStatus = 'valid' | 'expired' | 'missing' | 'no_lab'

export type ReadinessCalibration = {
  certificate_number?: string | null
  valid_until_iso?: string | null
  status: ReadinessCalibrationStatus
  days_remaining?: number | null
  detail: string
}

// DUT-attach is deliberately a backend placeholder — status is always
// "not_implemented" in this build (no probe-sensing / RFID / session table).
export type ReadinessDutAttach = {
  status: string // "not_implemented" in this build
  detail: string
}

export type Cmw500Lte2x2Readiness = {
  status: 'ready' | 'warning' | 'diagnostic' | 'not_applicable'
  adapter_registered: boolean
  connection_id: string | null
  model: string | null
  identity_verified: boolean | null
  firmware_version: string | null
  options: string[]
  formal_enabled: boolean
  formal_updated_at: string | null
  fdd_ready: boolean
  tdd_ready: boolean
  detail: string
}

export type HALReadinessResponse = {
  available: boolean
  drivers: ReadinessDriverRow[]
  lab_profile: ReadinessLabProfile
  calibration: ReadinessCalibration
  dut_attach: ReadinessDutAttach
  cmw500_lte_2x2: Cmw500Lte2x2Readiness | null
  generated_at_iso: string
  subnets: SubnetReachability[]
}

// ── ② 运行态 — GET /test-executions?limit=N ──
// ARCH-1 S2: 数据源是 test_executions 本表 — 每次执行一行 (用例执行 /
// 暗室首测 / 诊断), 含 running 行。名字终于说真话: 行真的是执行行了。
// 三态: phases_* 为 null = 该执行链不记相位进度 (显示 "—");
// validation_pass 为 null = 未判定。

export type TestExecutionStatus =
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | string

export type TestExecutionItem = {
  id: string
  case_name: string | null
  source_test_case_id: string | null
  status: TestExecutionStatus
  phases_total: number | null
  phases_done: number | null
  phases_failed: number | null
  duration_sec: number | null
  started_at: string | null
  completed_at: string | null
  executed_by: string | null
  error_message: string | null
  validation_pass: boolean | null
  // P2-34: 告警发布结果 published | duplicate | failed; null = 未记录 (≠ 已发布)
  failure_alert_outcome: string | null
}

export type TestExecutionListResponse = {
  total: number
  items: TestExecutionItem[]
}

// ── ④ 实时日志 — GET /system-logs/tail ──
export type SystemLogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'RAW' | string

export type SystemLogEntry = {
  ts: string
  level: SystemLogLevel
  logger: string
  hal_mode: string
  session_id: string
  /** P1-36：一次**测试执行**的关联 id。与 session_id（每请求）是两个生命周期。 */
  execution_id: string
  instrument_id: string
  msg: string
  raw?: string | null
}

export type SystemLogTailResponse = {
  filename: string
  total_lines_read: number
  filtered_count: number
  entries: SystemLogEntry[]
  older_cursor: string | null
  has_older: boolean
}

// ── ④ 实时告警 — GET /dashboard/alerts + /dashboard/alerts/summary ──
export type DashboardAlertSeverity = 'info' | 'warning' | 'error' | 'critical' | string

export type DashboardAlert = {
  id: string
  title: string
  message?: string | null
  severity: DashboardAlertSeverity
  alert_type?: string | null
  source?: string | null
  status: string
  is_read: boolean
  related_entity_type?: string | null
  related_entity_id?: string | null
  created_at: string
  updated_at: string
  acknowledged_at?: string | null
  resolved_at?: string | null
  created_by?: string | null
  acknowledged_by?: string | null
}

export type DashboardAlertListResponse = {
  total: number
  alerts: DashboardAlert[]
}

export type DashboardAlertSummary = {
  total_active: number
  info_count: number
  warning_count: number
  error_count: number
  critical_count: number
}

// MockServer 的演示监控帧；不是 live `/monitoring/feeds` 契约。live 元素是
// `{name, value:number, unit, timestamp}`，不得再复用本类型的展示型 MetricItem。
export type MockMonitoringFeedsResponse = {
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
  // P2-1 Phase 2.3: plan-level UXM topology override (null = use binding-level)
  topology_profile_id?: string | null
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
  // P2-1 Phase 2.3: optional plan-level UXM topology override
  topology_profile_id?: string | null
}

export type UpdatePlanPayload = {
  name?: string
  status?: string
  notes?: string
  steps?: SequenceStep[]
  // P2-1 Phase 2.3: plan-level UXM topology override. Set via this
  // payload only sets (the legacy update endpoint filters explicit
  // nulls). Use setPlanTopologyProfile() to clear.
  topology_profile_id?: string
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

export type InstrumentsResponse = {
  categories: InstrumentCategory[]
}

export type UpdateInstrumentPayload = {
  modelId?: string
  connection?: InstrumentConnectionUpdate
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
  is_system_preset: boolean

  // 物理参数
  chamber_radius_m: number
  quiet_zone_diameter_m: number | null
  num_probes: number
  num_polarizations: number
  num_rings: number
  probe_distribution: 'ring' | 'multi-ring' | 'custom'

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

export type ChamberWritableFields = Omit<
  ChamberConfiguration,
  | 'id'
  | 'is_active'
  | 'is_system_preset'
  | 'created_at'
  | 'updated_at'
  | 'created_by'
  | 'supported_tests'
  | 'max_ul_radius_m'
>

export type CreateChamberPayload =
  Pick<ChamberWritableFields, 'name' | 'chamber_radius_m'> &
  Partial<Omit<ChamberWritableFields, 'name' | 'chamber_radius_m'>>

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
