/**
 * P2: LabProfile + RFChain resolution (read-only, calibration UI preview).
 *
 * Backed by GET /lab-profiles and GET /lab-profiles/{id}/rf-chains. The
 * resolved chain list is what the path-loss calibrator iterates over —
 * exposing the same shape here means the operator's "preview before Start"
 * matches what the backend will actually do.
 */
import apiClient from './client'

export interface LabProfileSummary {
  id: string
  name: string
  description?: string | null
  organization?: string | null
  location?: string | null
  chamber_config_id?: string | null
  chamber_name?: string | null
  is_active: boolean
}

export interface RFChainEntry {
  /** SwitchTopology connection id — stable lookup key. */
  chain_id: string
  /** Source-side label, e.g. "B1.1" for the channel emulator port. */
  ce_port: string
  probe_id: number
  polarization: string
  cable_loss_db: number
}

export interface RFChainResolutionResponse {
  lab_profile_id: string
  lab_name: string
  chamber_id?: string | null
  chamber_name?: string | null
  topology_id?: string | null
  topology_name?: string | null
  operating_mode: string
  chains: RFChainEntry[]
  warnings: string[]
  success: boolean
}

export async function fetchLabProfiles(activeOnly = true): Promise<LabProfileSummary[]> {
  const res = await apiClient.get<LabProfileSummary[]>('/lab-profiles', {
    params: { is_active: activeOnly },
  })
  return res.data
}

/**
 * P0-2: payload the first-run wizard sends to create a LabProfile.
 * Mirrors `LabProfileCreateRequest` on the backend; keep both sides in
 * lock-step when adding fields.
 */
export interface InstrumentBindingPayload {
  category_id: string
  /** Optional — wizard may save IP without a model selection. */
  instrument_model_id?: string | null
  connection_endpoint: string
  driver_mode?: 'auto' | 'mock' | 'real'
  role?: string | null
}

export interface CreateLabProfileRequest {
  name: string
  chamber_config_id: string
  instrument_bindings: InstrumentBindingPayload[]
  description?: string | null
  organization?: string | null
  location?: string | null
  is_active?: boolean
  created_by?: string | null
}

export async function createLabProfile(
  payload: CreateLabProfileRequest,
): Promise<LabProfileSummary> {
  const res = await apiClient.post<LabProfileSummary>('/lab-profiles', payload)
  return res.data
}

export async function fetchRFChains(
  labProfileId: string,
  operatingMode = 'mimo_ota',
): Promise<RFChainResolutionResponse> {
  const res = await apiClient.get<RFChainResolutionResponse>(
    `/lab-profiles/${labProfileId}/rf-chains`,
    { params: { operating_mode: operatingMode } },
  )
  return res.data
}

/** P0: kicks off path-loss calibration for the resolved chain list. */
export interface StartPathLossForLabRequest {
  lab_profile_id: string
  operating_mode: string
  frequency_mhz: number
  sgh_model: string
  sgh_gain_dbi: number
  sgh_serial?: string
  vna_id?: string
  calibrated_by: string
  use_mock?: boolean
}

export interface CalibrationJobResponse {
  calibration_job_id: string
  status: string
  message?: string
  estimated_duration_minutes?: number
}

export async function startPathLossCalibrationForLab(
  payload: StartPathLossForLabRequest,
): Promise<CalibrationJobResponse> {
  const res = await apiClient.post<CalibrationJobResponse>(
    '/calibration/path-loss/start-for-lab',
    payload,
  )
  return res.data
}
