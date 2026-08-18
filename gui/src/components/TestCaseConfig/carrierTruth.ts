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
