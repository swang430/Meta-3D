// 库选择只影响编辑器；不修改执行资格或历史默认标记。
export const preferenceKey = (lab: string, category: string) =>
  `meta3d.topology-editor.default.v1:${lab}:${category}`;
export const requestMatches = (a: {scope: string; generation: number}, b: {scope: string; generation: number}) =>
  a.scope === b.scope && a.generation === b.generation;
export const canLeaveTopology = (dirty: boolean, busy: boolean) => !dirty && !busy;

type LibraryItem = {id?: string; created_at?: string; is_default: boolean};
export function chooseTopology(items: LibraryItem[], preferredId: string | null): string | null {
  const available = items.filter((item): item is LibraryItem & {id: string} => !!item.id);
  if (preferredId && available.some(item => item.id === preferredId)) return preferredId;
  const defaults = available.filter(item => item.is_default);
  if (defaults.length === 1) return defaults[0].id;
  return [...available].sort((a,b) => (b.created_at ?? '').localeCompare(a.created_at ?? '') || a.id.localeCompare(b.id))[0]?.id ?? null;
}

export async function loadTopologyLibrary<T extends {id?: string}>(
  page: (skip: number, limit: number) => Promise<{items: T[]; total: number}>,
): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  while (true) {
    const result = await page(items.length,100);
    if (!Array.isArray(result.items) || !Number.isInteger(result.total) || result.total < 0)
      throw new Error('拓扑库分页响应无效');
    for (const item of result.items) {
      if (!item.id || seen.has(item.id)) throw new Error('拓扑库分页重复或缺少ID，请刷新重试');
      seen.add(item.id);
      items.push(item);
    }
    if (items.length >= result.total) return items;
    if (!result.items.length) throw new Error('拓扑库分页没有进展，请刷新重试');
  }
}
