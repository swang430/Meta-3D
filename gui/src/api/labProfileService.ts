/**
 * P2: LabProfile + RFChain resolution (read-only, calibration UI preview).
 *
 * Backed by GET /lab-profiles and GET /lab-profiles/{id}/rf-chains. The
 * resolved chain list is what the path-loss calibrator iterates over —
 * exposing the same shape here means the operator's "preview before Start"
 * matches what the backend will actually do.
 */
import apiClient from './client'
import type {
  BaseStationBindingPreviewResponse,
  ChannelEmulatorBindingPreviewResponse,
  InstrumentBindingSyncResponse,
  CalibrationScopeSnapshot,
  CalibrationScopeComparison,
  FixedRouteCalibrationDeclaration,
  FixedRouteCalibrationPreview,
  F64StateRequest,
  F64StateRecord,
  FixedRouteRequest,
  FixedRouteRecord,
  RouteSelection, RouteApplicationPreview, ConfirmRouteApplication, RouteApplicationRecord,
} from '../types/api'

export async function fetchRouteCalibrationPaths(labId:string,topologyId:string,mode:string):Promise<RouteSelection[]> {
  const rows=(await apiClient.get<RouteSelection[]>(`/lab-profiles/${labId}/route-calibration-paths`,
    {params:{topology_id:topologyId,operating_mode:mode}})).data
  if(rows.some(row=>row.lab_profile_id!==labId || row.topology_id!==topologyId || row.operating_mode!==mode)) throw new Error('路径响应与当前实验室、拓扑或模式不一致')
  return rows
}
export async function fetchRouteApplicationPreview(labId:string,runId:string):Promise<RouteApplicationPreview> {
  const value=(await apiClient.get<RouteApplicationPreview>(`/lab-profiles/${labId}/fixed-route-acquisitions/${runId}/application-preview`)).data
  if(value.acquisition_run_id!==runId || value.selection && value.selection.lab_profile_id!==labId) throw new Error('采用预览与所查看记录不一致')
  return value
}
export async function confirmRouteApplication(labId:string,body:ConfirmRouteApplication):Promise<RouteApplicationRecord> {
  const value=(await apiClient.post<RouteApplicationRecord>(`/lab-profiles/${labId}/route-calibration-applications`,body)).data
  if(value.selection_snapshot.lab_profile_id!==labId || value.acquisition_run_id!==body.acquisition_run_id ||
    value.selection_snapshot.route_digest!==body.route_digest) throw new Error('确认响应与本次记录不一致')
  return value
}
export async function fetchRouteApplicationHistory(labId:string,topologyId:string,chainId:string):Promise<RouteApplicationRecord[]> {
  const rows=(await apiClient.get<RouteApplicationRecord[]>(`/lab-profiles/${labId}/route-calibration-applications`,
    {params:{topology_id:topologyId,chain_id:chainId}})).data
  if(rows.some(row=>row.selection_snapshot.lab_profile_id!==labId || row.selection_snapshot.topology_id!==topologyId ||
    row.selection_snapshot.chain_id!==chainId)) throw new Error('采用历史与所选通路不一致')
  return rows
}

function checkedAcquisition(labId: string, value: FixedRouteRecord, runId?: string): FixedRouteRecord {
  if (value.lab_profile_id !== labId || (runId && value.run_id !== runId)) throw new Error('采集响应与所选实验室或记录不一致')
  return value
}

export async function startFixedRouteAcquisition(labId: string, request: FixedRouteRequest): Promise<FixedRouteRecord> {
  return checkedAcquisition(labId, (await apiClient.post<FixedRouteRecord>(`/lab-profiles/${labId}/fixed-route-acquisitions`, request)).data)
}

export async function fetchFixedRouteAcquisition(labId: string, runId: string): Promise<FixedRouteRecord> {
  return checkedAcquisition(labId, (await apiClient.get<FixedRouteRecord>(`/lab-profiles/${labId}/fixed-route-acquisitions/${runId}`)).data, runId)
}

export async function cancelFixedRouteAcquisition(labId: string, runId: string): Promise<FixedRouteRecord> {
  return checkedAcquisition(labId, (await apiClient.post<FixedRouteRecord>(`/lab-profiles/${labId}/fixed-route-acquisitions/${runId}/cancel`)).data, runId)
}

export async function fetchFixedRouteAcquisitions(labId: string): Promise<FixedRouteRecord[]> {
  return (await apiClient.get<FixedRouteRecord[]>(`/lab-profiles/${labId}/fixed-route-acquisitions`)).data.map(value => checkedAcquisition(labId, value))
}

export async function readF64CalibrationState(labId: string, request: F64StateRequest): Promise<F64StateRecord> {
  return (await apiClient.post<F64StateRecord>(`/lab-profiles/${labId}/f64-calibration-state`, request)).data
}

export async function fetchF64CalibrationHistory(labId: string): Promise<F64StateRecord[]> {
  return (await apiClient.get<F64StateRecord[]>(`/lab-profiles/${labId}/f64-calibration-state`)).data
}

export async function previewFixedRouteCalibration(request: FixedRouteCalibrationDeclaration): Promise<FixedRouteCalibrationPreview> {
  return (await apiClient.post<FixedRouteCalibrationPreview>('/calibration/path-loss/fixed-route/preview', request)).data
}

export async function fetchCalibrationScope(labId: string): Promise<CalibrationScopeSnapshot> {
  return (await apiClient.get<CalibrationScopeSnapshot>(`/lab-profiles/${labId}/calibration-scope`)).data
}

/** POST 只读比较，不保存、不加载、不授予校准复用资格。 */
export async function compareCalibrationScope(labId: string, baseline: CalibrationScopeSnapshot): Promise<CalibrationScopeComparison> {
  return (await apiClient.post<CalibrationScopeComparison>(`/lab-profiles/${labId}/calibration-scope/compare`, { baseline })).data
}

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

/** 编辑器既要列可选的 active 行，也要展示历史已绑定但停用的行。 */
export async function fetchAllLabProfiles(): Promise<LabProfileSummary[]> {
  const [active, inactive] = await Promise.all([
    fetchLabProfiles(true),
    fetchLabProfiles(false),
  ])
  return [...active, ...inactive].sort((a, b) => a.name.localeCompare(b.name))
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

export async function syncCurrentInstrumentBinding(
  labProfileId: string,
  categoryKey: string,
  expectedSavedConfigurationDigest: string,
  testCaseId?: string,
): Promise<InstrumentBindingSyncResponse> {
  const res = await apiClient.put<InstrumentBindingSyncResponse>(
    `/lab-profiles/${labProfileId}/instrument-bindings/${categoryKey}/sync-current`,
    { expected_saved_configuration_digest: expectedSavedConfigurationDigest },
    { params: testCaseId ? { test_case_id: testCaseId } : undefined },
  )
  return res.data
}

export async function fetchBaseStationBindingPreview(
  labProfileId: string,
  testCaseId?: string,
): Promise<BaseStationBindingPreviewResponse> {
  const res = await apiClient.get<BaseStationBindingPreviewResponse>(
    `/lab-profiles/${labProfileId}/instrument-bindings/baseStation/preview`,
    { params: testCaseId ? { test_case_id: testCaseId } : undefined },
  )
  return res.data
}

/** P2-58 ①：channelEmulator binding 只读预览（零仪器 I/O），与 BaseStation 版同形；契约第 3 步。 */
export async function fetchChannelEmulatorBindingPreview(
  labProfileId: string,
  testCaseId?: string,
): Promise<ChannelEmulatorBindingPreviewResponse> {
  const res = await apiClient.get<ChannelEmulatorBindingPreviewResponse>(
    `/lab-profiles/${labProfileId}/instrument-bindings/channelEmulator/preview`,
    { params: testCaseId ? { test_case_id: testCaseId } : undefined },
  )
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
  /** 校准 warnings (含 acquire 清理失败, 如 tone 停不掉 / CE 留直通) */
  warnings?: string[]
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
