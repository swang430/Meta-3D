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
  // P2-56 ②：跟随后端放开。draft 是**服务端冻结 profile 的投影**，锁死 'fdd'
  // 会让 TDD 用例在表单里显示成 FDD —— 显示层撒谎比缺字段更糟。
  // ⚠️ 三个 TDD 帧结构字段（uldl_configuration / special_subframe /
  // rmc_version）**不在 draft 里**：GUI 今天没有创建/编辑 TDD profile 的入口。
  // 保存时 `updateMacProfileDraft` 对 TDD **保留** mac_profile 原样回传
  // （见该函数的 LTE 分支），让服务端沿用已冻结的那一份 —— 否则后端会走
  // legacy 派生并因缺帧结构而拒绝，TDD 用例就成了「可创建、不可编辑」。
  // ⚠️ 初版注释写「那是既有的 GUI 能力缺口，不是本片新增」是**不准确的**：
  // 本片之前 duplex 是 Literal["fdd"]，TDD 用例根本不可能存在，缺口不可达。
  duplex: 'fdd' | 'tdd'
  transmission_mode: 'TM3'
}

export type MacProfileDraft = NrMacProfileDraft | LteMacProfileDraft

type MacProfileDraftPatch = {
  mcs?: number
  enable_amc?: boolean
  tdd_pattern?: string
  tdd_period?: string
  harq_max_trans?: number
  harq_processes?: number
  csi_rs_ports?: number
  statistical_window_count?: number
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
    }
  }
  const count = positiveInteger(configuration.stat_count, 5000)
  if (rat === 'lte') {
    return {
      kind: 'lte_rmc',
      rat: 'lte',
      statistical_window: { unit: 'subframes', count },
      scheduling_mode: 'rmc',
      resource_allocation: 'full',
      enable_amc: false,
      duplex: 'fdd',
      transmission_mode: 'TM3',
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
    // P2-56 ②（内审 F5）：TDD 用例必须**原样保留** mac_profile。
    // 上面那句 `delete next[key]` 会把它剥掉，让后端走 legacy 派生；而
    // legacy 的扁平字段里没有帧结构（uldl_configuration / special_subframe），
    // 后端会显式拒绝 —— 结果是 TDD 用例「可创建、不可编辑」。
    // GUI 今天没有编辑 TDD 帧结构的入口，所以这里的正确行为是**不动它**，
    // 让服务端沿用已冻结的那一份。
    // 走本文件既有的 `record()` 守卫，不新增裸类型断言（外审 R2 high 的建议）。
    // ⚠️ 这里**不改变** null 形态的行为：`configuration` 为 `null` / `undefined`
    // 时，本函数第一句 `profileDraftForConfiguration(...)` 里的
    // `frozenProfile(configuration.mac_profile)` 就已经抛 TypeError —— 那是
    // main 上就有的既有行为，本片不动它（⑦：不改它，本片那个可观察故障还在）。
    // 换 `record()` 只是不让新增代码再多一处裸 `as`，行为逐格实测等价。
    const frozen = record(configuration)?.mac_profile
    const frozenDuplex = record(record(frozen)?.profile)?.duplex
    if (frozenDuplex === 'tdd') {
      next.mac_profile = frozen
      // ⚠️ 同时**撤掉 stat_count**（内审 F1）：后端在 `mac_profile` 存在时
      // 按**值**对账 —— `stat_count` 与 `mac_profile.statistical_window.count`
      // **不相等**才拒（"mac_profile conflicts with deprecated stat_count"，
      // 见 config.py 的 expected_legacy 分支；相等是放行的）。
      // 而 TDD 分支保留的是**旧的**冻结 profile，用户新改的 stat_count 必然
      // 与它不等 —— 索性不带出去，让冻结的统计窗口当唯一真值。
      // 表单已把 TDD 的统计窗口置灰，但本函数是纯函数、可被别处调用 ——
      // 让它自己不产生冲突形态，比只靠 UI 挡更可靠。
      delete next.stat_count
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
  if (pcell?.radio_technology === 'lte') return null

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
