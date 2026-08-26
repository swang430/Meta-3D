export type PrimaryCarrierField =
  | 'frequency_hz'
  | 'bandwidth_mhz'
  | 'subcarrier_spacing_khz'

export interface CarrierTruthConfiguration {
  frequency_hz?: number
  bandwidth_mhz?: number
  subcarrier_spacing_khz?: number
  component_carriers?: Array<{
    frequency_hz?: number
    bandwidth_mhz?: number
    subcarrier_spacing_khz?: number
    [key: string]: unknown
  }>
  [key: string]: unknown
}

export type RadioTechnology = 'nr5g' | 'lte'
export type CarrierChannelKind = 'nr_arfcn' | 'lte_dl_earfcn'

export interface PrimaryCarrierIdentity {
  radio_technology: RadioTechnology
  channel_kind: CarrierChannelKind
  frequency_hz: number
  bandwidth_mhz: number
  subcarrier_spacing_khz?: number
  band?: string
  duplex?: 'fdd' | 'tdd'
  nr_arfcn?: number
  lte_dl_earfcn?: number
  role: 'pcell'
}

const finiteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

/** Strict read-side parser. A missing RAT is accepted only for a complete legacy NR PCell. */
export function primaryCarrierIdentity(
  config: CarrierTruthConfiguration,
): PrimaryCarrierIdentity | null {
  const raw = Array.isArray(config.component_carriers)
    ? config.component_carriers[0]
    : undefined
  if (!raw || !finiteNumber(raw.frequency_hz) || !finiteNumber(raw.bandwidth_mhz)) {
    return null
  }
  const rat = raw.radio_technology
  if (rat === 'lte') {
    if (
      raw.channel_kind !== 'lte_dl_earfcn'
      || typeof raw.band !== 'string'
      || (raw.duplex !== 'fdd' && raw.duplex !== 'tdd')
      || !finiteNumber(raw.lte_dl_earfcn)
      || raw.nr_arfcn != null
      || raw.subcarrier_spacing_khz != null
    ) return null
    return {
      radio_technology: 'lte', channel_kind: 'lte_dl_earfcn',
      frequency_hz: raw.frequency_hz, bandwidth_mhz: raw.bandwidth_mhz,
      band: raw.band, duplex: raw.duplex,
      lte_dl_earfcn: raw.lte_dl_earfcn, role: 'pcell',
    }
  }
  const isLegacy = rat == null && raw.channel_kind == null
  if (
    (rat !== 'nr5g' && !isLegacy)
    || (raw.channel_kind !== 'nr_arfcn' && !isLegacy)
    || !finiteNumber(raw.subcarrier_spacing_khz)
    || (raw.nr_arfcn != null && !finiteNumber(raw.nr_arfcn))
    || raw.lte_dl_earfcn != null
  ) return null
  return {
    radio_technology: 'nr5g', channel_kind: 'nr_arfcn',
    frequency_hz: raw.frequency_hz, bandwidth_mhz: raw.bandwidth_mhz,
    subcarrier_spacing_khz: raw.subcarrier_spacing_khz,
    ...(typeof raw.band === 'string' ? { band: raw.band } : {}),
    ...(finiteNumber(raw.nr_arfcn) ? { nr_arfcn: raw.nr_arfcn } : {}),
    role: 'pcell',
  }
}

/** Replace the single PCell atomically and clear an NR-only peak when switching to LTE. */
export function updatePrimaryCarrierIdentity<T extends CarrierTruthConfiguration>(
  config: T,
  carrier: PrimaryCarrierIdentity,
): T {
  const next: CarrierTruthConfiguration = {
    ...config,
    frequency_hz: carrier.frequency_hz,
    bandwidth_mhz: carrier.bandwidth_mhz,
    component_carriers: [{ ...carrier }],
  }
  if (carrier.radio_technology === 'lte') {
    delete next.subcarrier_spacing_khz
    delete next.theoretical_peak_throughput_mbps
  } else if (carrier.subcarrier_spacing_khz != null) {
    next.subcarrier_spacing_khz = carrier.subcarrier_spacing_khz
  }
  return next as T
}

/** PCell is the display/execution truth; top-level fields are legacy mirrors. */
export function primaryCarrierValue(
  config: CarrierTruthConfiguration,
  key: PrimaryCarrierField,
): number | undefined {
  const pcell = Array.isArray(config.component_carriers)
    ? config.component_carriers[0]
    : undefined
  const value = pcell ? pcell[key] : config[key]
  return typeof value === 'number' && Number.isFinite(value)
    ? value
    : undefined
}

/** Update the legacy mirror and PCell together without touching any SCell. */
export function updatePrimaryCarrierValue<T extends CarrierTruthConfiguration>(
  config: T,
  key: PrimaryCarrierField,
  next: number,
): T {
  const carriers = config.component_carriers
  if (!Array.isArray(carriers) || carriers.length === 0) {
    return { ...config, [key]: next }
  }
  const [pcell, ...scells] = carriers
  return {
    ...config,
    [key]: next,
    component_carriers: [{ ...pcell, [key]: next }, ...scells],
  }
}
