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
