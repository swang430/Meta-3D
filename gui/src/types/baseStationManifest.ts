export type BaseStationProfileFieldManifest = {
  path: string
  label: string
  required: boolean
  placeholder: string
  description: string
}

export type BaseStationCapabilityEvidence =
  | 'authoritative'
  | 'diagnostic_only'
  | 'unavailable'
  | 'not_applicable'

export type BaseStationRatCapability = {
  rat: 'lte' | 'nr5g'
  source_reference: string
}

export type BaseStationConfigFieldCapability = {
  field: string
  support: 'authoritative' | 'diagnostic_only' | 'not_applicable'
  readback: 'authoritative' | 'unavailable' | 'not_applicable'
  reason: string
  source_reference: string | null
}

export type BaseStationAttachStageCapability = {
  stage: 'cell_ready' | 'ue_registered' | 'rrc_connected' | 'data_bearer_established'
  evidence: BaseStationCapabilityEvidence
  reason: string
  source_reference: string | null
}

export type BaseStationMetricCapability = {
  key: string
  direction: 'downlink' | 'uplink' | 'link' | 'not_applicable'
  unit: 'mbps' | 'percent' | 'ratio' | 'index' | 'raw' | 'not_applicable'
  scopes: Array<'pcell' | 'all_cells'>
  evidence: Exclude<BaseStationCapabilityEvidence, 'not_applicable'>
  source_reference: string | null
}

export type BaseStationMeasurementCapability = {
  cardinality: 'requested' | 'single'
  scopes: Array<'pcell' | 'all_cells'>
  lifecycle: 'authoritative_closed' | 'clear_read_only' | 'unavailable'
  metrics: BaseStationMetricCapability[]
  source_reference: string | null
}

export type BaseStationAdapterManifest = {
  schema_version: 2
  adapter_id: string
  model_name: string
  vendor: string
  rats: string[]
  capabilities: string[]
  rat_capabilities: BaseStationRatCapability[]
  operations: string[]
  config_fields: BaseStationConfigFieldCapability[]
  attach_stages: BaseStationAttachStageCapability[]
  measurement: BaseStationMeasurementCapability | null
  profile_requirement: 'required' | 'not_applicable'
  profile_schema_version: number | null
  profile_fields: BaseStationProfileFieldManifest[]
  manual_sources: string[]
  diagnostic_supported: boolean
  formal_gate: 'site_certification'
}

export type BaseStationProfileDraft = Record<string, string>

export type BaseStationCapabilityTone = 'green' | 'yellow' | 'gray'

export type BaseStationCapabilityProjectionItem = {
  key: string
  label: string
  detail: string
  source: BaseStationCapabilityEvidence
  tone: BaseStationCapabilityTone
}

export type BaseStationCapabilityProjection = {
  rats: BaseStationCapabilityProjectionItem[]
  attach: BaseStationCapabilityProjectionItem[]
  measurementWindow: BaseStationCapabilityProjectionItem
  metrics: BaseStationCapabilityProjectionItem[]
}

const attachLabels: Record<BaseStationAttachStageCapability['stage'], string> = {
  cell_ready: '小区就绪',
  ue_registered: 'UE 注册',
  rrc_connected: 'RRC 连接',
  data_bearer_established: '数据承载',
}

const evidencePresentation = (
  evidence: BaseStationCapabilityEvidence,
): Pick<BaseStationCapabilityProjectionItem, 'source' | 'tone'> => {
  if (evidence === 'authoritative') return { source: evidence, tone: 'green' }
  if (evidence === 'diagnostic_only') return { source: evidence, tone: 'yellow' }
  return { source: evidence, tone: 'gray' }
}

export const projectBaseStationCapabilities = (
  manifest: BaseStationAdapterManifest,
): BaseStationCapabilityProjection => {
  const lifecycle = manifest.measurement?.lifecycle ?? 'unavailable'
  const lifecycleEvidence: BaseStationCapabilityEvidence = lifecycle === 'authoritative_closed'
    ? 'authoritative'
    : lifecycle === 'clear_read_only'
      ? 'diagnostic_only'
      : 'unavailable'

  return {
    rats: manifest.rat_capabilities.map((item) => ({
      key: item.rat,
      label: item.rat.toUpperCase(),
      detail: item.source_reference,
      source: 'authoritative',
      tone: 'green',
    })),
    attach: manifest.attach_stages.map((item) => ({
      key: item.stage,
      label: attachLabels[item.stage],
      detail: item.reason,
      ...evidencePresentation(item.evidence),
    })),
    measurementWindow: {
      key: lifecycle,
      label: lifecycle === 'authoritative_closed'
        ? '完整闭环窗口'
        : lifecycle === 'clear_read_only'
          ? '清零/读取窗口'
          : '测量窗口不可用',
      detail: manifest.measurement
        ? `${manifest.measurement.cardinality} · ${manifest.measurement.scopes.join(' / ')}`
        : '未声明测量窗口',
      ...evidencePresentation(lifecycleEvidence),
    },
    metrics: (manifest.measurement?.metrics ?? []).map((item) => ({
      key: item.key,
      label: item.key,
      detail: `${item.direction} · ${item.unit} · ${item.scopes.join(' / ')}`,
      ...evidencePresentation(item.evidence),
    })),
  }
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null

const readPath = (root: Record<string, unknown>, path: string): unknown => {
  let current: unknown = root
  for (const segment of path.split('.')) {
    const record = asRecord(current)
    if (!record) return undefined
    current = record[segment]
  }
  return current
}

const writePath = (root: Record<string, unknown>, path: string, value: string) => {
  const segments = path.split('.')
  let current = root
  segments.forEach((segment, index) => {
    if (index === segments.length - 1) {
      current[segment] = value
      return
    }
    const existing = asRecord(current[segment])
    const next = existing ?? {}
    current[segment] = next
    current = next
  })
}

export const emptyBaseStationProfileDraft = (
  manifest: BaseStationAdapterManifest,
): BaseStationProfileDraft => Object.fromEntries(
  manifest.profile_fields.map((field) => [field.path, '']),
)

export const readBaseStationProfileDraft = (
  manifest: BaseStationAdapterManifest,
  value: unknown,
): BaseStationProfileDraft => {
  const draft = emptyBaseStationProfileDraft(manifest)
  const envelope = asRecord(value)
  if (
    !envelope
    || manifest.profile_schema_version === null
    || envelope.schema_version !== manifest.profile_schema_version
    || envelope.adapter !== manifest.adapter_id
  ) return draft

  manifest.profile_fields.forEach((field) => {
    const fieldValue = readPath(envelope, field.path)
    if (typeof fieldValue === 'string') draft[field.path] = fieldValue
  })
  return draft
}

export const validateBaseStationProfileDraft = (
  manifest: BaseStationAdapterManifest,
  draft: BaseStationProfileDraft,
): string | null => {
  for (const field of manifest.profile_fields) {
    if (field.required && !(draft[field.path] ?? '').trim()) {
      return `${field.label} 为必填项`
    }
  }
  return null
}

export const buildBaseStationAdapterProfile = (
  manifest: BaseStationAdapterManifest,
  draft: BaseStationProfileDraft,
): Record<string, unknown> | null => {
  if (manifest.profile_requirement === 'not_applicable') return null
  const validationError = validateBaseStationProfileDraft(manifest, draft)
  if (validationError) throw new Error(validationError)

  const envelope: Record<string, unknown> = {
    schema_version: manifest.profile_schema_version,
    adapter: manifest.adapter_id,
  }
  manifest.profile_fields.forEach((field) => {
    writePath(envelope, field.path, (draft[field.path] ?? '').trim())
  })
  return envelope
}
