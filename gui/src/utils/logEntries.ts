import type { SystemLogEntry } from '../types/api'

export type GroupedSystemLogEntry = SystemLogEntry & {
  continuation_lines: string[]
  grouped_raw: string | null
}

/**
 * Python traceback 等非 JSON 续行在 API 中表现为 RAW 条目。显示排序前先把它们
 * 并回上一条结构化父记录，否则直接 reverse 会把一个 traceback 自己也倒过来。
 * 输入数组与条目均不修改；页首没有父记录的 RAW 保留为独立条目，加载更早页后
 * 会在整份合并快照上重新归组。
 */
export function groupLogContinuations(entries: SystemLogEntry[]): GroupedSystemLogEntry[] {
  const grouped: GroupedSystemLogEntry[] = []

  for (const entry of entries) {
    if (entry.level.toUpperCase() === 'RAW' && grouped.length > 0) {
      const previous = grouped[grouped.length - 1]
      const continuation = entry.raw ?? entry.msg
      previous.continuation_lines.push(continuation)
      previous.grouped_raw = [previous.grouped_raw, continuation].filter(Boolean).join('\n')
      continue
    }

    grouped.push({
      ...entry,
      continuation_lines: [],
      grouped_raw: entry.raw ?? null,
    })
  }

  return grouped
}

/** Group first so a hidden parent cannot leave its RAW traceback on a neighbor. */
export function filterGroupedLogEntries(
  entries: SystemLogEntry[],
  predicate: (entry: GroupedSystemLogEntry) => boolean,
): GroupedSystemLogEntry[] {
  return groupLogContinuations(entries).filter(predicate)
}
