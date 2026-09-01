export type MacStatisticalWindow = {
  unit: 'subframes'
  count: number
}

export type MacMetricRequirement = {
  key: string
  scope: 'pcell' | 'all_cells'
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
  enable_amc: boolean
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
  duplex: 'fdd'
  transmission_mode: 'TM3'
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
  enable_amc: boolean
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
  duplex: 'fdd'
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
  return {
    kind: 'nr_throughput',
    rat: 'nr5g',
    statistical_window: { unit: 'subframes', count },
    mcs: finiteNumber(configuration.mcs, 28),
    enable_amc: configuration.enable_amc === true,
    tdd_pattern: typeof configuration.tdd_pattern === 'string'
      ? configuration.tdd_pattern
      : 'DDDDDDDSUU',
    tdd_period: typeof configuration.tdd_period === 'string'
      ? configuration.tdd_period
      : '5MS',
    harq_max_trans: positiveInteger(configuration.harq_max_trans, 4),
    harq_processes: positiveInteger(configuration.harq_processes, 16),
    scheduler_algorithm: 'full_throughput',
    csi_rs_ports: positiveInteger(configuration.csi_rs_ports, 4),
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
  if (rat === 'lte') return next

  const nr = current.kind === 'nr_throughput'
    ? current
    : profileDraftForConfiguration({}, 'nr5g') as NrMacProfileDraft
  next.mcs = finiteNumber(patch.mcs, nr.mcs)
  next.enable_amc = typeof patch.enable_amc === 'boolean'
    ? patch.enable_amc
    : nr.enable_amc
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

export function describeFrozenMacProfile(value: unknown): string {
  const profile = frozenProfile(value)
  const outer = record(value)
  if (!profile || typeof outer?.profile_digest !== 'string') return '未冻结（旧数据或尚未保存）'
  const metrics = profile.metric_requirements.map((item) => item.key).join(', ')
  return `${profile.rat.toUpperCase()} · ${profile.kind}@${profile.profile_version} · ${metrics} · ${outer.profile_digest.slice(0, 12)}…`
}
