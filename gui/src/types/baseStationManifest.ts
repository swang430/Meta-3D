export type BaseStationProfileFieldManifest = {
  path: string
  label: string
  required: boolean
  placeholder: string
  description: string
}

export type BaseStationAdapterManifest = {
  schema_version: 1
  adapter_id: string
  model_name: string
  vendor: string
  rats: string[]
  capabilities: string[]
  profile_requirement: 'required' | 'not_applicable'
  profile_fields: BaseStationProfileFieldManifest[]
  manual_sources: string[]
  diagnostic_supported: boolean
  formal_gate: 'legacy_provenance' | 'connection_approval'
}

export type BaseStationProfileDraft = Record<string, string>

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
    || envelope.schema_version !== manifest.schema_version
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
    schema_version: manifest.schema_version,
    adapter: manifest.adapter_id,
  }
  manifest.profile_fields.forEach((field) => {
    writePath(envelope, field.path, (draft[field.path] ?? '').trim())
  })
  return envelope
}
