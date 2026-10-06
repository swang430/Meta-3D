/** Display server-authored adapter constraints; never infer ranges from model names. */
export function projectMacStatisticalWindow(manifest: unknown, kind: string) {
  const unknown = {
    status: 'unknown' as const,
    minimum: 1, // Common profile schema requires a positive integer, not an instrument range.
    maximum: undefined as number | undefined,
    description: '单位：subframes；仪表允许范围 unknown（未确认）；仍需服务器兼容性及执行证据核验',
  }
  if (!manifest || typeof manifest !== 'object' || !('mac_profiles' in manifest)
    || !Array.isArray(manifest.mac_profiles)) return unknown
  const matches = manifest.mac_profiles.filter((item) => item?.kind === kind
    && item.profile_version === 1 && item.rat === (kind === 'lte_rmc' ? 'lte' : 'nr5g'))
  if (matches.length !== 1) return unknown
  const range = matches[0].statistical_window
  if (!range || range.unit !== 'subframes' || !Number.isInteger(range.minimum)
    || !Number.isInteger(range.maximum) || range.minimum < 1 || range.maximum < range.minimum
    || typeof range.source_reference !== 'string' || !range.source_reference.trim()) return unknown
  return {
    status: 'known' as const,
    minimum: range.minimum as number,
    maximum: range.maximum as number,
    description: `单位：subframes；服务器约束 ${range.minimum}～${range.maximum}；${range.source_reference}`,
  }
}
