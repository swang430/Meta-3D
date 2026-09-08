export type MetricTrend = '↑' | '↓' | '→' | string

import type { BaseStationAdapterManifest } from './baseStationManifest'
export type { BaseStationAdapterManifest }
import type { FrozenMacTestProfile } from './macTestProfile'
export type {
  FrozenMacTestProfile,
  LteRmcMacTestProfileV1,
  MacMetricRequirement,
  MacStatisticalWindow,
  NrMacTestProfileV1,
} from './macTestProfile'

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
  base_station_manifest: BaseStationAdapterManifest | null
}

export type InstrumentConnection = {
  /** DB InstrumentConnection UUID, 供 SCD 等按 connection 关联的 API 用 */
  id?: string | null
  endpoint?: string | null
  controller?: string | null
  notes?: string | null
  connection_params?: Record<string, any> | null
  base_station_model_presets?: Record<string, BaseStationModelPreset>
  channel_emulator_model_presets?: Record<string, ChannelEmulatorModelPreset>
  cmw500_lte_2x2_formal_enabled: boolean
  cmw500_lte_2x2_formal_updated_at: string | null
  base_station_site_certification: BaseStationSiteCertification | null
  channel_emulator_site_certification: ChannelEmulatorSiteCertification | null
}

export type BaseStationModelPreset = {
  schema_version: 1
  model_id: string
  endpoint: string
  controller: string
  notes: string
  connection_params: Record<string, unknown>
  base_station_adapter_profile: Record<string, unknown> | null
}

/** P2-58 ②：信道仿真器分型号 saved preset —— 与 BaseStationModelPreset 同形，**无** adapter_profile 槽
 *  （CE 无 profile 层；alignment_name / available_channel_models 都住在 connection_params 里，原样带着）。 */
export type ChannelEmulatorModelPreset = {
  schema_version: 1
  model_id: string
  endpoint: string
  controller: string
  notes: string
  connection_params: Record<string, unknown>
}

export type TestCaseExecutionPolicy = {
  schema_version: 1
  mode: 'formal' | 'diagnostic'
  reason: string
  updated_by: string
  updated_at: string
}

export type BaseStationSiteCertification = {
  schema_version: 1
  status: 'active' | 'revoked'
  lab_profile_id: string
  instrument_connection_id: string
  binding_digest: string
  adapter_id: string
  model: string
  firmware_version: string
  options: string[]
  source_execution_id: string
  evidence_digest: string
  required_proofs: {
    config_readback: boolean
    route_readback: boolean
    route_not_applicable: boolean
    cleanup: boolean
    transport_release: boolean
  }
  certified_by: string
  certified_at: string
  reason: string
  revoked_by?: string | null
  revoked_at?: string | null
  revocation_reason?: string | null
}

export type ChannelEmulatorSiteCertification = {
  schema_version: 1
  status: 'active' | 'revoked'
  lab_profile_id: string
  instrument_connection_id: string
  instrument_model_id: string
  binding_digest: string
  adapter_id: string
  plan_digest: string
  asset_digest: string
  load_mode: 'native_model' | 'external_waveform' | 'parametric_tdl'
  model: string
  firmware_version: string
  serial_number: string
  options: string[]
  identity_digest: string
  source_execution_id: string
  terminal_evidence_digest: string
  operation_receipts_digest: string
  measurement_evidence_digest: string
  required_proofs: {
    binding_plan_asset: boolean
    hardware_identity_options: boolean
    operation_receipts: boolean
    frequency: boolean
    level: boolean
    path_loss: boolean
    safe_idle: boolean
    transport_release: boolean
  }
  certified_by: string
  certified_at: string
  reason: string
  revoked_by?: string | null
  revoked_at?: string | null
  revocation_reason?: string | null
}

export type ChannelEmulatorCertificationPreview = {
  status: 'formal_ready' | 'diagnostic' | 'invalid' | 'not_applicable'
  binding_digest: string | null
  adapter_id: string | null
  instrument_model_id: string | null
  instrument_connection_id: string | null
  lab_profile_id: string | null
  site_certification: ChannelEmulatorSiteCertification | null
  site_certification_digest: string | null
  reasons: string[]
  detail: string
}

export type FrozenExecutionQualification = {
  schema_version: 1
  classification: 'formal' | 'diagnostic'
  reasons: string[]
  binding_digest: string
  site_certification_digest: string | null
  qualification_digest: string
}

export type ChannelOperationFieldEvidenceProjection = {
  field: string
  status: 'requested' | 'applied' | 'confirmed' | 'unknown' | 'not_applicable' | 'unavailable'
  provenance:
    | 'authoritative_readback'
    | 'command_error_queue'
    | 'runtime_state'
    | 'transport_release'
    | 'simulated'
    | 'unavailable'
  exchange_ids?: string[]
  source_reference: string | null
}

export type ChannelOperationReceiptEvidenceProjection = {
  sequence: number
  phase: 'load' | 'configure' | 'start' | 'adjust' | 'stop' | 'cleanup' | 'release'
  operation: string
  terminal_state: 'completed' | 'rejected' | 'failed' | 'cancelled'
  operation_succeeded: boolean | null
  simulated: boolean
  status: 'verified' | 'diagnostic' | 'rejected' | 'failed' | 'cancelled'
  fields: ChannelOperationFieldEvidenceProjection[]
  exchange_ids?: string[]
  error_queue_exchange_ids?: string[]
}

export type ChannelOperationSessionEvidenceProjection = {
  session_id: string
  operation_scope: string | null
  status: 'legacy' | 'verified' | 'diagnostic'
  receipt_count: number | null
  receipt_chain_digest: string | null
  receipts?: ChannelOperationReceiptEvidenceProjection[]
}

export type ChannelEmulatorOperationEvidenceProjection = {
  schema_version: 1
  status: 'not_available' | 'pending' | 'legacy' | 'verified' | 'diagnostic' | 'invalid'
  reasons: string[]
  sessions: ChannelOperationSessionEvidenceProjection[]
}

export type ExecutionEvidenceOutcome = {
  schema_version: 1
  compatibility_classification: 'compatible' | 'diagnostic' | 'legacy' | 'invalid'
  completion_semantic:
    | 'valid_test_completed'
    | 'diagnostic_completed'
    | 'pipeline_completed'
    | 'not_completed'
  formal_eligible: boolean
  compatibility_digest: string | null
  qualification_classification: 'formal' | 'diagnostic' | 'legacy'
  reasons: string[]
  pipeline_status: string
  channel_emulator_operation_evidence: ChannelEmulatorOperationEvidenceProjection
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
  base_station_adapter_profile?: Record<string, unknown> | null
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

export type HALCategoryActivationResult = {
  category_key: string
  status: 'activated' | 'unchanged' | 'inactive'
  driver_class: string | null
  instrument_id: string | null
  simulated: boolean | null
  message: string
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
  binding_digest: string | null
}

export type BaseStationBindingPreviewResponse = {
  status: 'configured' | 'not_applicable' | 'diagnostic_unbound' | 'invalid'
  binding_digest: string | null
  execution_mode: 'real' | 'simulated' | null
  adapter_id: string | null
  model_name: string | null
  category_id: string | null
  instrument_model_id: string | null
  instrument_connection_id: string | null
  lab_profile_id: string
  resolved_binding: Record<string, unknown> | null
  runtime_driver: Record<string, unknown> | null
  detail: string
  testcase_compatibility: BaseStationCompatibilityPreviewResponse | null
}

/** P2-58 ①：channelEmulator binding 只读预览（GET …/instrument-bindings/channelEmulator/preview，
 *  readiness 的 channel_emulator_binding 同形）。CE 没有 compatibility 槽，取而代之是 selected_asset_id。 */
export type ChannelEmulatorBindingPreviewResponse = {
  status: 'configured' | 'not_applicable' | 'diagnostic_unbound' | 'invalid'
  binding_digest: string | null
  execution_mode: 'real' | 'simulated' | null
  adapter_id: string | null
  model_name: string | null
  category_id: string | null
  instrument_model_id: string | null
  instrument_connection_id: string | null
  lab_profile_id: string
  resolved_binding: Record<string, unknown> | null
  runtime_driver: Record<string, unknown> | null
  detail: string
  /** 预览带 test_case_id 时附带的信道资产 id；不进 binding_digest。 */
  selected_asset_id: string | null
}

export type BaseStationCompatibilityPreviewResponse = {
  schema_version: 1
  status: 'compatible' | 'incompatible' | 'no_adapter' | 'not_evaluated' | 'invalid'
  compatible: boolean | null
  test_case_id: string | null
  lab_profile_id: string | null
  binding_digest: string | null
  execution_mode: 'real' | 'simulated' | null
  requirements: {
    schema_version: 1
    requested_rat: 'nr5g' | 'lte'
    required_operations: string[]
    mac_profile?: FrozenMacTestProfile | null
  } | null
  verdict: {
    schema_version: 1
    status: 'compatible' | 'incompatible' | 'no_adapter'
    compatible: boolean
    reasons: string[]
    requirements_digest: string
    manifest_digest: string | null
  } | null
  reasons: string[]
  detail: string
}

export type InstrumentBindingSyncResponse = {
  binding: {
    category_id: string
    instrument_model_id?: string | null
    connection_endpoint: string
    driver_mode?: 'auto' | 'mock' | 'real'
    role?: string | null
  }
  resolved?: BaseStationBindingPreviewResponse | null
  testcase_compatibility?: BaseStationCompatibilityPreviewResponse | null
}

export type HALReadinessResponse = {
  available: boolean
  drivers: ReadinessDriverRow[]
  lab_profile: ReadinessLabProfile
  calibration: ReadinessCalibration
  dut_attach: ReadinessDutAttach
  base_station_binding: BaseStationBindingPreviewResponse | null
  /** P2-58 ①：当前 LabProfile 的 channelEmulator binding 预览；HAL 未就绪或无活动 LabProfile 时为 null（required，非 ?:）。 */
  channel_emulator_binding: ChannelEmulatorBindingPreviewResponse | null
  base_station_testcase_compatibility: BaseStationCompatibilityPreviewResponse
  base_station_site_certification: BaseStationSiteCertification | null
  channel_emulator_site_certification_preview: ChannelEmulatorCertificationPreview | null
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
  execution_classification: 'formal' | 'diagnostic' | 'legacy'
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
