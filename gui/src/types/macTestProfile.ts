export type MacStatisticalWindow = {
  unit: 'subframes'
  count: number
}

export type MacMetricRequirement = {
  key: string
  scope: 'pcell' | 'all_cells'
}

export const UXM_NR_TDD_PERIOD_VALUES = [
  '0.5MS', '0.625MS', '1MS', '1.25MS', '2MS',
  '2.5MS', '3MS', '4MS', '5MS', '10MS',
] as const

export const UXM_NR_HARQ_MAX_TRANS_VALUES = [
  1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 28,
] as const

export const UXM_NR_HARQ_PROCESSES_VALUES = [
  1, 2, 4, 6, 8, 10, 12, 13, 14, 16, 32,
] as const

export const UXM_NR_MIMO_LAYERS_VALUES = [1, 2, 4] as const

export const UXM_NR_CSI_RS_PORTS_VALUES = [
  1, 2, 4, 8, 12, 16, 24, 32,
] as const

export const LTE_TDD_ULDL_CONFIGURATION_VALUES = [0, 1, 2, 3, 4, 5, 6] as const
export const LTE_TDD_SPECIAL_SUBFRAME_VALUES = [0, 1, 2, 3, 4, 5, 6, 7] as const
export const LTE_TDD_RMC_VERSION_VALUES = [0, 1] as const

const UXM_NR_SLOT_DURATION_MS: Record<number, number> = {
  15: 1,
  30: 0.5,
  60: 0.25,
  120: 0.125,
}

const UXM_NR_TDD_PERIOD_MS: Record<string, number> = {
  '0.5MS': 0.5,
  '0.625MS': 0.625,
  '1MS': 1,
  '1.25MS': 1.25,
  '2MS': 2,
  '2.5MS': 2.5,
  '3MS': 3,
  '4MS': 4,
  '5MS': 5,
  '10MS': 10,
}

/**
 * 手册 `Tx Periodicity (P)` 的 Default（Section「NR Scheduling > TDD UL-DL Config >
 * Pattern 1」，Default `MS5`）。只在无法从时隙模式唯一推出周期时兜底，
 * 且此时 validateMacProfileDraftForSave() 会把不一致显式报给用户。
 */
const UXM_NR_TDD_PERIOD_MANUAL_DEFAULT = '5MS'

/**
 * 与后端 `uxm_nr_tdd_period_for_pattern()` 用**同一条推导公式**：
 * 周期 = 时隙数 × 单时隙时长，且只在唯一匹配时采纳。
 *
 * 此前界面对缺失周期一律填 5MS，而后端按模式与 SCS 推导，于是 15 / 60 / 120 kHz 的
 * 稀疏旧配置一打开就报「模式、SCS 与周期不一致」，改个载波频率还会把这个错值写实、
 * 导致存不进去。
 *
 * ⚠️ 公式同源，**失败分支两端策略不同**：算不出唯一匹配时后端直接 raise，这里退回
 *    手册 Default 交给 validateMacProfileDraftForSave() 拦。方向一致（都不放行），
 *    但别把这里当成后端行为的等价物。
 */
function uxmNrTddPeriodForPattern(pattern: string, scsKhz: number): string {
  const slotMs = UXM_NR_SLOT_DURATION_MS[scsKhz]
  if (slotMs === undefined) return UXM_NR_TDD_PERIOD_MANUAL_DEFAULT
  const durationMs = pattern.trim().length * slotMs
  const matches = Object.entries(UXM_NR_TDD_PERIOD_MS).filter(
    ([, periodMs]) => Math.abs(durationMs - periodMs) <= 1e-9,
  )
  return matches.length === 1 ? matches[0][0] : UXM_NR_TDD_PERIOD_MANUAL_DEFAULT
}

type MacTestProfileBase = {
  schema_version: 1
  profile_version: 1
  test_intent: 'downlink_throughput'
  mimo_layers: number
  statistical_window: MacStatisticalWindow
  metric_requirements: MacMetricRequirement[]
  source_reference: string
}

export type NrMacTestProfileV1 = MacTestProfileBase & {
  kind: 'nr_throughput'
  rat: 'nr5g'
  rb_allocation: 'all'
  scheduler_algorithm: 'full_throughput'
  mcs: number
  mimo_layers: 1 | 2 | 4
  enable_amc: false
  tdd_pattern: string
  tdd_period: string
  harq_max_trans: number
  harq_processes: number
  subcarrier_spacing_khz: number
  csi_rs_ports: number
  source_reference: 'Instrument_API_Doc/Keysight UXM NR SCPI/5G_NR_Test_Application_SCPI_Reference.zip'
}

export type LteRmcMacTestProfileV1 = MacTestProfileBase & {
  kind: 'lte_rmc'
  rat: 'lte'
  scheduling_mode: 'rmc'
  resource_allocation: 'full'
  enable_amc: false
  duplex: 'fdd' | 'tdd'
  transmission_mode: 'TM3'
  mimo_layers: 2
  // P2-56 ②：LTE TDD 专属维度。后端序列化不带 exclude_none，所以这三个键
  // **恒出现在线上形态里**；FDD 下恒为 null。与 api.generated.ts 保持一致。
  // special_subframe 只到 7：值 8/9 要求 normal cyclic prefix，本驱动无该维度。
  uldl_configuration: 0 | 1 | 2 | 3 | 4 | 5 | 6 | null
  special_subframe: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | null
  rmc_version: 0 | 1 | null
  source_reference: 'Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf'
}

export type MacTestProfile = NrMacTestProfileV1 | LteRmcMacTestProfileV1

export type FrozenMacTestProfile = {
  profile: MacTestProfile
  profile_digest: string
}

export type NrMacProfileDraft = {
  kind: 'nr_throughput'
  rat: 'nr5g'
  statistical_window: MacStatisticalWindow
  mcs: number
  enable_amc: false
  tdd_pattern: string
  tdd_period: string
  harq_max_trans: number
  harq_processes: number
  scheduler_algorithm: 'full_throughput'
  csi_rs_ports: number
}

export type LteMacProfileDraft = {
  kind: 'lte_rmc'
  rat: 'lte'
  statistical_window: MacStatisticalWindow
  scheduling_mode: 'rmc'
  resource_allocation: 'full'
  enable_amc: false
  duplex: 'fdd' | 'tdd'
  transmission_mode: 'TM3'
  uldl_configuration: 0 | 1 | 2 | 3 | 4 | 5 | 6 | null
  special_subframe: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | null
  rmc_version: 0 | 1 | null
}

export type MacProfileDraft = NrMacProfileDraft | LteMacProfileDraft

type MacProfileDraftPatch = {
  duplex?: 'fdd' | 'tdd'
  mcs?: number
  enable_amc?: boolean
  tdd_pattern?: string
  tdd_period?: string
  harq_max_trans?: number
  harq_processes?: number
  csi_rs_ports?: number
  statistical_window_count?: number
  uldl_configuration?: number | null
  special_subframe?: number | null
  rmc_version?: number | null
}

const LEGACY_MAC_KEYS = [
  'mac_profile',
  'mcs',
  'enable_amc',
  'tdd_pattern',
  'tdd_period',
  'harq_max_trans',
  'harq_processes',
  'stat_count',
  'sched_algo',
  'csi_rs_ports',
  'scheduling_mode',
  'resource_allocation',
  'transmission_mode',
  'lte_tdd_frame_structure',
] as const

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function positiveInteger(value: unknown, fallback: number): number {
  const candidate = finiteNumber(value, fallback)
  return Number.isInteger(candidate) && candidate > 0 ? candidate : fallback
}

function enumIntegerOrNull<const T extends readonly number[]>(
  value: unknown,
  allowed: T,
): T[number] | null {
  if (
    typeof value === 'number'
    && Number.isInteger(value)
    && allowed.includes(value as T[number])
  ) {
    return value as T[number]
  }
  return null
}

function primaryBandwidthMhz(configuration: Record<string, unknown>): number | null {
  const carriers = Array.isArray(configuration.component_carriers)
    ? configuration.component_carriers
    : []
  const pcell = record(carriers[0])
  const value = pcell?.bandwidth_mhz ?? configuration.bandwidth_mhz
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * 与后端 `_migrate_legacy_mac_profile()` 同一取法：优先主载波，其次顶层，缺省 30 kHz。
 */
function subcarrierSpacingKhz(configuration: Record<string, unknown>): number {
  const carriers = Array.isArray(configuration.component_carriers)
    ? configuration.component_carriers
    : []
  const pcell = record(carriers[0])
  return finiteNumber(
    pcell?.subcarrier_spacing_khz ?? configuration.subcarrier_spacing_khz,
    30,
  )
}

function frozenProfile(value: unknown): MacTestProfile | null {
  const outer = record(value)
  const profile = record(outer?.profile)
  if (!outer || !profile || typeof outer.profile_digest !== 'string') return null
  if (profile.kind === 'nr_throughput' && profile.rat === 'nr5g') {
    return profile as NrMacTestProfileV1
  }
  if (profile.kind === 'lte_rmc' && profile.rat === 'lte') {
    return profile as LteRmcMacTestProfileV1
  }
  return null
}

/**
 * Project the server-frozen profile when available; otherwise migrate the
 * legacy TestCase inputs into an edit-only draft.  The browser never creates
 * a profile digest or decides adapter compatibility.
 */
export function profileDraftForConfiguration(
  configuration: Record<string, unknown>,
  rat: 'nr5g' | 'lte',
): MacProfileDraft {
  const frozen = frozenProfile(configuration.mac_profile)
  if (rat === 'nr5g' && frozen?.kind === 'nr_throughput') {
    return {
      kind: frozen.kind,
      rat: frozen.rat,
      statistical_window: frozen.statistical_window,
      mcs: frozen.mcs,
      enable_amc: frozen.enable_amc,
      tdd_pattern: frozen.tdd_pattern,
      tdd_period: frozen.tdd_period,
      harq_max_trans: frozen.harq_max_trans,
      harq_processes: frozen.harq_processes,
      scheduler_algorithm: frozen.scheduler_algorithm,
      csi_rs_ports: frozen.csi_rs_ports,
    }
  }
  if (rat === 'lte' && frozen?.kind === 'lte_rmc') {
    return {
      kind: frozen.kind,
      rat: frozen.rat,
      statistical_window: frozen.statistical_window,
      scheduling_mode: frozen.scheduling_mode,
      resource_allocation: frozen.resource_allocation,
      enable_amc: frozen.enable_amc,
      duplex: frozen.duplex,
      transmission_mode: frozen.transmission_mode,
      uldl_configuration: frozen.uldl_configuration,
      special_subframe: frozen.special_subframe,
      rmc_version: frozen.rmc_version,
    }
  }
  const count = positiveInteger(configuration.stat_count, 5000)
  if (rat === 'lte') {
    const carriers = Array.isArray(configuration.component_carriers)
      ? configuration.component_carriers
      : []
    const pcell = record(carriers[0])
    const authoring = record(configuration.lte_tdd_frame_structure)
    return {
      kind: 'lte_rmc',
      rat: 'lte',
      statistical_window: { unit: 'subframes', count },
      scheduling_mode: 'rmc',
      resource_allocation: 'full',
      enable_amc: false,
      duplex: pcell?.duplex === 'tdd' ? 'tdd' : 'fdd',
      transmission_mode: 'TM3',
      uldl_configuration: enumIntegerOrNull(
        authoring?.uldl_configuration,
        LTE_TDD_ULDL_CONFIGURATION_VALUES,
      ),
      special_subframe: enumIntegerOrNull(
        authoring?.special_subframe,
        LTE_TDD_SPECIAL_SUBFRAME_VALUES,
      ),
      rmc_version: enumIntegerOrNull(
        authoring?.rmc_version,
        LTE_TDD_RMC_VERSION_VALUES,
      ),
    }
  }
  const nrTddPattern = typeof configuration.tdd_pattern === 'string'
    ? configuration.tdd_pattern
    : 'DDDDDDDSUU'
  return {
    kind: 'nr_throughput',
    rat: 'nr5g',
    statistical_window: { unit: 'subframes', count },
    mcs: finiteNumber(configuration.mcs, 28),
    enable_amc: false,
    tdd_pattern: nrTddPattern,
    tdd_period: typeof configuration.tdd_period === 'string'
      ? configuration.tdd_period
      : uxmNrTddPeriodForPattern(
        nrTddPattern,
        subcarrierSpacingKhz(configuration),
      ),
    harq_max_trans: positiveInteger(configuration.harq_max_trans, 4),
    harq_processes: positiveInteger(configuration.harq_processes, 16),
    scheduler_algorithm: 'full_throughput',
    csi_rs_ports: positiveInteger(
      configuration.csi_rs_ports,
      Math.max(2, positiveInteger(configuration.mimo_layers, 2) * 2),
    ),
  }
}

/**
 * Emit only the existing legacy authoring inputs.  The backend is the sole
 * canonical writer: it validates the RAT-specific shape and freezes/digests
 * the resulting profile at the schema boundary.
 */
export function updateMacProfileDraft(
  configuration: Record<string, unknown>,
  rat: 'nr5g' | 'lte',
  patch: MacProfileDraftPatch,
): Record<string, unknown> {
  const current = profileDraftForConfiguration(configuration, rat)
  const next = { ...configuration }
  for (const key of LEGACY_MAC_KEYS) delete next[key]

  const count = positiveInteger(
    patch.statistical_window_count,
    current.statistical_window.count,
  )
  next.stat_count = count
  if (rat === 'lte') {
    next.mimo_layers = 2
    const lte = current.kind === 'lte_rmc'
      ? current
      : profileDraftForConfiguration({}, 'lte') as LteMacProfileDraft
    const duplex = patch.duplex ?? lte.duplex
    if (duplex === 'tdd') {
      const uldl = enumIntegerOrNull(
        patch.uldl_configuration !== undefined
          ? patch.uldl_configuration
          : lte.uldl_configuration,
        LTE_TDD_ULDL_CONFIGURATION_VALUES,
      )
      const special = enumIntegerOrNull(
        patch.special_subframe !== undefined
          ? patch.special_subframe
          : lte.special_subframe,
        LTE_TDD_SPECIAL_SUBFRAME_VALUES,
      )
      const rmc = enumIntegerOrNull(
        patch.rmc_version !== undefined
          ? patch.rmc_version
          : lte.rmc_version,
        LTE_TDD_RMC_VERSION_VALUES,
      )
      next.lte_tdd_frame_structure = {
        uldl_configuration: uldl,
        special_subframe: special,
        ...(primaryBandwidthMhz(configuration) === 20
          ? { rmc_version: rmc }
          : {}),
      }
    }
    return next
  }

  const nr = current.kind === 'nr_throughput'
    ? current
    : profileDraftForConfiguration({}, 'nr5g') as NrMacProfileDraft
  next.mcs = finiteNumber(patch.mcs, nr.mcs)
  next.enable_amc = false
  next.tdd_pattern = typeof patch.tdd_pattern === 'string'
    ? patch.tdd_pattern
    : nr.tdd_pattern
  next.tdd_period = typeof patch.tdd_period === 'string'
    ? patch.tdd_period
    : nr.tdd_period
  next.harq_max_trans = positiveInteger(patch.harq_max_trans, nr.harq_max_trans)
  next.harq_processes = positiveInteger(patch.harq_processes, nr.harq_processes)
  next.sched_algo = 'FULLBUFFER'
  next.csi_rs_ports = positiveInteger(patch.csi_rs_ports, nr.csi_rs_ports)
  return next
}

export function validateMacProfileDraftForSave(
  configuration: Record<string, unknown>,
): string | null {
  const carriers = Array.isArray(configuration.component_carriers)
    ? configuration.component_carriers
    : []
  const pcell = record(carriers[0])
  if (pcell?.radio_technology === 'lte') {
    const draft = profileDraftForConfiguration(configuration, 'lte')
    if (draft.kind !== 'lte_rmc') return 'LTE MAC profile 类型无效'
    if (draft.duplex === 'fdd') return null
    if (!LTE_TDD_ULDL_CONFIGURATION_VALUES.includes(
      draft.uldl_configuration as 0,
    )) {
      return 'LTE TDD ULDL 配置必须选择 0 至 6'
    }
    if (!LTE_TDD_SPECIAL_SUBFRAME_VALUES.includes(
      draft.special_subframe as 0,
    )) {
      return 'LTE TDD 特殊子帧必须选择 0 至 7'
    }
    const bandwidth = primaryBandwidthMhz(configuration)
    if (![1.4, 3, 5, 10, 15, 20].includes(bandwidth ?? -1)) {
      return 'LTE TDD 带宽不在 CMW500 已审计 RMC 范围内'
    }
    if (bandwidth === 20 && !LTE_TDD_RMC_VERSION_VALUES.includes(
      draft.rmc_version as 0,
    )) {
      return 'LTE TDD 20 MHz 必须选择 RMC 版本 0 或 1'
    }
    if (bandwidth !== 20 && draft.rmc_version !== null) {
      return '当前 LTE TDD 带宽不需要 RMC 版本，必须清空'
    }
    return null
  }

  const draft = profileDraftForConfiguration(configuration, 'nr5g')
  if (draft.kind !== 'nr_throughput') return 'NR MAC profile 类型无效'
  const layers = positiveInteger(configuration.mimo_layers, 2)
  if (!UXM_NR_MIMO_LAYERS_VALUES.includes(layers as 1 | 2 | 4)) {
    return 'NR MIMO 层数必须为 1、2 或 4'
  }
  if (!UXM_NR_CSI_RS_PORTS_VALUES.includes(draft.csi_rs_ports as 1)) {
    return 'NR CSI-RS 端口数不在 UXM 已审计范围内'
  }
  const pattern = draft.tdd_pattern.trim().toUpperCase()
  if (!/^D*S?U*$/.test(pattern) || pattern.length === 0) {
    return 'NR TDD 时隙模式必须为非空的 D…D、可选 S、U…U 排列'
  }
  const slotMs = UXM_NR_SLOT_DURATION_MS[subcarrierSpacingKhz(configuration)]
  const periodMs = UXM_NR_TDD_PERIOD_MS[draft.tdd_period.toUpperCase()]
  if (
    slotMs === undefined
    || periodMs === undefined
    || Math.abs(pattern.length * slotMs - periodMs) > 1e-9
  ) {
    return 'NR TDD 时隙模式、SCS 与周期不一致'
  }
  return null
}

export function describeFrozenMacProfile(value: unknown): string {
  const profile = frozenProfile(value)
  const outer = record(value)
  if (!profile || typeof outer?.profile_digest !== 'string') return '未冻结（旧数据或尚未保存）'
  const metrics = profile.metric_requirements.map((item) => item.key).join(', ')
  return `${profile.rat.toUpperCase()} · ${profile.kind}@${profile.profile_version} · ${metrics} · ${outer.profile_digest.slice(0, 12)}…`
}
