/**
 * TanStack Query hooks for Test Execution History
 *
 * ARCH-1 S2: 数据源换到 test_executions 本表。queryKey 根加 'v2' —
 * 返回形状变了必须换 key, 否则旧缓存 (计划摘要形状) 会喂给新组件当场崩
 * (memory feedback_react_query_shape_change_needs_new_key)。
 * 单条查询 / 删除 hook 随换源退场 (删除会毁报告引用, 待决① 拍板)。
 */

import { useQuery } from '@tanstack/react-query'
import type { HistoryFilters } from '../types'
import * as api from '../api/testManagementAPI'

// Query Keys
export const testHistoryKeys = {
  all: ['test-management', 'history', 'v2'] as const,
  lists: () => [...testHistoryKeys.all, 'list'] as const,
  list: (filters?: HistoryFilters) => [...testHistoryKeys.lists(), filters] as const,
}

// ==================== Queries ====================

/**
 * Hook to fetch execution history with filters
 */
export function useTestHistory(filters?: HistoryFilters) {
  return useQuery({
    queryKey: testHistoryKeys.list(filters),
    queryFn: () => api.getExecutionHistory(filters),
    staleTime: 30000, // 30 seconds
  })
}
