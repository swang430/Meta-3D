export interface CreateSessionParams {
  radioTechnology?: 'nr5g' | 'lte'
  engineMode?: string
  labProfileId?: string
  ascSourcePath?: string
  channelAssetId?: string
  frequencyHz?: number
  bandwidthMhz?: number
  band?: string
  duplex?: 'fdd' | 'tdd'
  subcarrierSpacingKhz?: number
  nrArfcn?: number
  lteDlEarfcn?: number
  theoreticalPeakThroughputMbps?: number
  uxmDlPowerDbmPerBw?: number
  f64InputRefDbm?: number
  f64CrestDb?: number
  f64OutputLevelDbm?: number
  emulationFile?: string
  f64BypassMode?: number
  baseStationConfigMode?: 'dispatch' | 'inherit'
  labSmoke?: boolean
  calBypass?: boolean
}

export interface CreateSessionBody {
  radio_technology: 'nr5g' | 'lte'
  engine_mode: string
  lab_profile_id?: string
  asc_source_path?: string
  channel_asset_id?: string
  frequency_hz?: number
  bandwidth_mhz?: number
  band?: string
  duplex?: 'fdd' | 'tdd'
  subcarrier_spacing_khz?: number
  nr_arfcn?: number
  lte_dl_earfcn?: number
  theoretical_peak_throughput_mbps?: number
  uxm_dl_power_dbm_per_bw?: number
  f64_input_ref_dbm?: number
  f64_crest_db?: number
  f64_output_level_dbm?: number
  emulation_file?: string
  f64_bypass_mode?: number
  base_station_config_mode?: 'dispatch' | 'inherit'
  precheck_strict_dut?: boolean
  precheck_strict_cal?: boolean
  precheck_strict_frequency?: boolean
  precheck_strict_emulation_file?: boolean
  precheck_strict_switch_mode?: boolean
  precheck_strict_cell_config?: boolean
  precheck_strict_dut_capability?: boolean
  precheck_strict_sim_identity?: boolean
}

/** 纯请求构造器：现场工作点必须作为本次 session 数据显式保存。 */
export const buildCreateSessionBody = (
  params: CreateSessionParams = {},
): CreateSessionBody => {
  const {
    radioTechnology = 'nr5g',
    engineMode = 'mimo_first_asc',
    labProfileId,
    ascSourcePath,
    channelAssetId,
    frequencyHz,
    bandwidthMhz,
    band,
    duplex,
    subcarrierSpacingKhz,
    nrArfcn,
    lteDlEarfcn,
    theoreticalPeakThroughputMbps,
    uxmDlPowerDbmPerBw,
    f64InputRefDbm,
    f64CrestDb,
    f64OutputLevelDbm,
    emulationFile,
    f64BypassMode,
    baseStationConfigMode,
    labSmoke,
    calBypass,
  } = params
  const body: CreateSessionBody = {
    radio_technology: radioTechnology,
    engine_mode: engineMode,
  }
  if (labProfileId) body.lab_profile_id = labProfileId
  if (engineMode === 'external_asc' && ascSourcePath) {
    body.asc_source_path = ascSourcePath
  }
  if (engineMode !== 'external_asc' && channelAssetId) {
    body.channel_asset_id = channelAssetId
  }
  if (frequencyHz !== undefined) body.frequency_hz = frequencyHz
  if (bandwidthMhz !== undefined) body.bandwidth_mhz = bandwidthMhz
  if (band) body.band = band
  if (radioTechnology === 'lte') {
    if (duplex) body.duplex = duplex
    if (lteDlEarfcn !== undefined) body.lte_dl_earfcn = lteDlEarfcn
    if (theoreticalPeakThroughputMbps !== undefined) {
      body.theoretical_peak_throughput_mbps = theoreticalPeakThroughputMbps
    }
  } else {
    if (subcarrierSpacingKhz !== undefined) {
      body.subcarrier_spacing_khz = subcarrierSpacingKhz
    }
    if (nrArfcn !== undefined) body.nr_arfcn = nrArfcn
  }
  if (uxmDlPowerDbmPerBw !== undefined) {
    body.uxm_dl_power_dbm_per_bw = uxmDlPowerDbmPerBw
  }
  if (f64InputRefDbm !== undefined) body.f64_input_ref_dbm = f64InputRefDbm
  if (f64CrestDb !== undefined) body.f64_crest_db = f64CrestDb
  if (f64OutputLevelDbm !== undefined) {
    body.f64_output_level_dbm = f64OutputLevelDbm
  }
  if (!channelAssetId && engineMode === 'keysight_gcm' && emulationFile) {
    body.emulation_file = emulationFile
  }
  if (f64BypassMode !== undefined) body.f64_bypass_mode = f64BypassMode
  if (baseStationConfigMode !== undefined) {
    body.base_station_config_mode = baseStationConfigMode
  }
  if (labSmoke) {
    body.precheck_strict_dut = false
    body.precheck_strict_cal = false
    body.precheck_strict_frequency = false
    body.precheck_strict_emulation_file = false
    body.precheck_strict_switch_mode = false
    body.precheck_strict_cell_config = false
    body.precheck_strict_dut_capability = false
    body.precheck_strict_sim_identity = false
  }
  if (calBypass) body.precheck_strict_cal = false
  return body
}
