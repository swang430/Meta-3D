export type BaseStationConfigMode = 'dispatch' | 'inherit'

type ConfigModeFields = {
  base_station_config_mode?: unknown
  uxm_config_mode?: unknown
}

export type BaseStationConfigModeResolution = {
  mode: BaseStationConfigMode
  conflict: boolean
}

const parseMode = (value: unknown): BaseStationConfigMode | undefined =>
  value === 'dispatch' || value === 'inherit' ? value : undefined

export const resolveBaseStationConfigMode = (
  config: ConfigModeFields,
): BaseStationConfigModeResolution => {
  const current = parseMode(config.base_station_config_mode)
  const legacy = parseMode(config.uxm_config_mode)
  return {
    mode: current ?? legacy ?? 'dispatch',
    conflict: current !== undefined && legacy !== undefined && current !== legacy,
  }
}

export const updateBaseStationConfigMode = <T extends Record<string, unknown>>(
  config: T,
  mode: BaseStationConfigMode,
): Omit<T, 'base_station_config_mode' | 'uxm_config_mode'> & {
  base_station_config_mode: BaseStationConfigMode
} => {
  const next: Record<string, unknown> = { ...config }
  delete next.uxm_config_mode
  next.base_station_config_mode = mode
  return next as Omit<T, 'base_station_config_mode' | 'uxm_config_mode'> & {
    base_station_config_mode: BaseStationConfigMode
  }
}
