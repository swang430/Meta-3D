export type ChannelRadioTechnology = 'nr5g' | 'lte'
export type ChannelKind = 'nr_arfcn' | 'lte_dl_earfcn'

export interface ChannelFrequencyIdentity {
  radioTechnology: ChannelRadioTechnology
  channelKind: ChannelKind
  band: string
  channelNumber: number
}

export interface VendorSCDInput {
  radioTechnology: ChannelRadioTechnology
  band: string
  channelNumber: number
  bandwidthMhz: number
  model: string
  scenario: string
  mimo: string
  polarization: string
  version: number
}

const finiteInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0
const nonEmpty = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0

/** Read explicit identity or the exact complete pre-P1-73 NR SCD shape. */
export function parseChannelFrequencyIdentity(raw: unknown): ChannelFrequencyIdentity | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const value = raw as Record<string, unknown>
  if (value.radio_technology === 'lte' && value.channel_kind === 'lte_dl_earfcn') {
    if (!nonEmpty(value.band) || !finiteInteger(value.lte_dl_earfcn) || value.arfcn != null) return null
    return { radioTechnology: 'lte', channelKind: 'lte_dl_earfcn', band: value.band, channelNumber: value.lte_dl_earfcn }
  }
  if (value.radio_technology === 'nr5g' && value.channel_kind === 'nr_arfcn') {
    if (!nonEmpty(value.band) || !finiteInteger(value.arfcn) || value.lte_dl_earfcn != null) return null
    return { radioTechnology: 'nr5g', channelKind: 'nr_arfcn', band: value.band, channelNumber: value.arfcn }
  }
  const legacyKeys = ['band', 'arfcn', 'bandwidth_mhz', 'model', 'scenario', 'mimo', 'polarization', 'version']
  if (
    value.radio_technology == null && value.channel_kind == null
    && legacyKeys.every((key) => value[key] != null)
    && nonEmpty(value.band) && /^N\d+$/i.test(value.band)
    && finiteInteger(value.arfcn) && finiteInteger(value.version)
    && typeof value.bandwidth_mhz === 'number' && value.bandwidth_mhz > 0
    && ['model', 'scenario', 'mimo', 'polarization'].every((key) => nonEmpty(value[key]))
  ) {
    return { radioTechnology: 'nr5g', channelKind: 'nr_arfcn', band: value.band.toUpperCase(), channelNumber: value.arfcn }
  }
  return null
}

export function buildVendorSCDConfig(input: VendorSCDInput): Record<string, unknown> {
  const base = {
    radio_technology: input.radioTechnology,
    channel_kind: input.radioTechnology === 'lte' ? 'lte_dl_earfcn' : 'nr_arfcn',
    band: input.band.trim().toUpperCase(),
    bandwidth_mhz: input.bandwidthMhz,
    model: input.model.trim(), scenario: input.scenario.trim(), mimo: input.mimo.trim(),
    polarization: input.polarization.trim(), version: input.version,
  }
  return input.radioTechnology === 'lte'
    ? { ...base, lte_dl_earfcn: input.channelNumber }
    : { ...base, arfcn: input.channelNumber }
}
