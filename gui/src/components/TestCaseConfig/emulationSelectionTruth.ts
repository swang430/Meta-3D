/** 保留服务器派生资产身份；只有无来源 ID 的手工项才保存裸路径。 */
interface Selection {
  channel_asset_id?: string
  scd_id?: string
  emulation_file?: string
}
interface Item {
  filename: string
  channel_asset_id?: string | null
  scd_id?: string | null
}

export function selectEmulationFile<T extends Selection>(value: T, items: readonly Item[], filename: string | null): T {
  const item = items.find((entry) => entry.filename === filename)
  return {
    ...value,
    channel_asset_id: item?.channel_asset_id || undefined,
    scd_id: item?.channel_asset_id ? undefined : item?.scd_id || undefined,
    emulation_file: item?.channel_asset_id || item?.scd_id ? undefined : filename ?? undefined,
  }
}

export function selectedEmulationFilename(value: Selection, items: readonly Item[]): string | null {
  if (value.channel_asset_id) return items.find((entry) => entry.channel_asset_id === value.channel_asset_id)?.filename ?? null
  if (value.scd_id) return items.find((entry) => entry.scd_id === value.scd_id)?.filename ?? null
  return value.emulation_file ?? null
}
