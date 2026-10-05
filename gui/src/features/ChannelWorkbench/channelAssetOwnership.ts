/** 服务器目录中的已保存归属；不接受仪器抽屉的未保存草稿。 */
export type SavedChannelAssetOwner = {
  instrument_connection_id: string
  instrument_model_id: string
  label: string
  endpoint: string
}

export function savedChannelAssetOwner(category: {
  key: string
  selectedModelId: string | null
  connection: { id?: string | null; endpoint?: string | null }
  models: { id: string; vendor?: string; model: string }[]
} | undefined): SavedChannelAssetOwner | null {
  if (category?.key !== 'channelEmulator' || !category.selectedModelId || !category.connection.id) return null
  const model = category.models.find((item) => item.id === category.selectedModelId)
  if (!model) return null
  return {
    instrument_connection_id: category.connection.id,
    instrument_model_id: model.id,
    label: `${model.vendor ?? ''} ${model.model}`.trim(),
    endpoint: category.connection.endpoint ?? '',
  }
}

export function ownershipConfirmationPayload(assetIds: string[], owner: SavedChannelAssetOwner) {
  if (!assetIds.length || new Set(assetIds).size !== assetIds.length) throw new Error('请选择不重复的文件资产')
  return { asset_ids: assetIds, instrument_connection_id: owner.instrument_connection_id,
    instrument_model_id: owner.instrument_model_id }
}
