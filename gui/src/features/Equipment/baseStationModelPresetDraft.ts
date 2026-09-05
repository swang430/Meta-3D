import type {
  InstrumentCategory,
  InstrumentConnectionUpdate,
} from '../../types/api.ts'
import {
  readBaseStationProfileDraft,
  type BaseStationProfileDraft,
} from '../../types/baseStationManifest.ts'

export type SavedBaseStationDraft = {
  modelId: string
  endpoint: string
  controller: string
  notes: string
  connection_params: string
  base_station_profile?: BaseStationProfileDraft
}

export type BaseStationSyncDraftLike = Pick<
  SavedBaseStationDraft,
  'modelId' | 'endpoint' | 'controller' | 'notes' | 'base_station_profile'
> & {
  connection_params?: string
}

const canonicalJson = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value) ?? 'undefined'
}

const canonicalParamsText = (text: string | undefined): string => {
  const raw = (text ?? '').trim()
  if (!raw) return canonicalJson({})
  try {
    return canonicalJson(JSON.parse(raw) as unknown)
  } catch {
    return raw
  }
}

/**
 * LabProfile sync consumes only the active saved category state. A model preset
 * restored into the drawer is still an unsaved draft until that model becomes
 * ``selectedModelId``; therefore this comparison intentionally does not use the
 * target model's preset as its baseline.
 */
export function hasUnsavedBaseStationSyncDraft(
  category: InstrumentCategory,
  draft: BaseStationSyncDraftLike,
): boolean {
  if (draft.modelId !== (category.selectedModelId ?? '')) return true

  const selectedModel = category.models.find((model) => model.id === category.selectedModelId)
  const manifest = selectedModel?.base_station_manifest
  const savedParams = category.connection.connection_params ?? {}
  const savedProfile = manifest
    ? readBaseStationProfileDraft(
        manifest,
        savedParams.base_station_adapter_profile as Record<string, unknown> | undefined,
      )
    : undefined

  return (
    draft.endpoint !== (category.connection.endpoint ?? '')
    || draft.controller !== (category.connection.controller ?? '')
    || draft.notes !== (category.connection.notes ?? '')
    || canonicalParamsText(draft.connection_params) !== canonicalJson(savedParams)
    || canonicalJson(draft.base_station_profile ?? {}) !== canonicalJson(savedProfile ?? {})
  )
}

/**
 * Every LabProfile sync endpoint consumes the category's active saved
 * connection, never the open drawer draft. Keep the BaseStation-specific
 * profile comparison, while applying the common saved-vs-draft comparison to
 * every other syncable instrument category.
 */
export function hasUnsavedInstrumentSyncDraft(
  category: InstrumentCategory,
  draft: BaseStationSyncDraftLike,
): boolean {
  if (category.key === 'baseStation') {
    return hasUnsavedBaseStationSyncDraft(category, draft)
  }

  return (
    draft.modelId !== (category.selectedModelId ?? '')
    || draft.endpoint !== (category.connection.endpoint ?? '')
    || draft.controller !== (category.connection.controller ?? '')
    || draft.notes !== (category.connection.notes ?? '')
    || canonicalParamsText(draft.connection_params)
      !== canonicalJson(category.connection.connection_params ?? {})
  )
}

export function explicitBaseStationConnectionDraft(
  draft: Pick<SavedBaseStationDraft, 'endpoint' | 'controller' | 'notes'>,
  connectionParams: Record<string, unknown>,
  baseStationAdapterProfile: Record<string, unknown> | null,
): InstrumentConnectionUpdate {
  return {
    endpoint: draft.endpoint,
    controller: draft.controller,
    notes: draft.notes,
    connection_params: connectionParams,
    base_station_adapter_profile: baseStationAdapterProfile,
  }
}

export function draftForBaseStationModel(
  category: InstrumentCategory,
  modelId: string,
): SavedBaseStationDraft {
  const preset = category.connection.base_station_model_presets?.[modelId]
  const manifest = category.models.find(
    (model) => model.id === modelId,
  )?.base_station_manifest

  if (!preset) {
    return {
      modelId,
      endpoint: '',
      controller: '',
      notes: '',
      connection_params: '',
      base_station_profile: manifest
        ? readBaseStationProfileDraft(manifest, undefined)
        : undefined,
    }
  }

  return {
    modelId,
    endpoint: preset.endpoint,
    controller: preset.controller,
    notes: preset.notes,
    connection_params: Object.keys(preset.connection_params).length > 0
      ? JSON.stringify(preset.connection_params, null, 2)
      : '',
    base_station_profile: manifest
      ? readBaseStationProfileDraft(
          manifest,
          preset.base_station_adapter_profile ?? undefined,
        )
      : undefined,
  }
}
