/** 仅决定工作台展示位置，不改变来源、仪器归属或执行资格。 */
export function isRtScene(a: { source_type: string; payload: Record<string, unknown>; associated_file_path?: string | null }) {
  return a.source_type === 'rt_dynamic' || (a.source_type === 'vendor_file' &&
    a.payload.rt_scene === true && /\.smu$/i.test(a.associated_file_path ?? ''))
}
