/**
 * TanStack Query hooks for Test Execution History
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import type { TestExecutionRecord, HistoryFilters } from '../types'
import * as api from '../api/testManagementAPI'

// Query Keys
export const testHistoryKeys = {
  all: ['test-management', 'history'] as const,
  lists: () => [...testHistoryKeys.all, 'list'] as const,
  list: (filters?: HistoryFilters) => [...testHistoryKeys.lists(), filters] as const,
  details: () => [...testHistoryKeys.all, 'detail'] as const,
  detail: (id: string) => [...testHistoryKeys.details(), id] as const,
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

/**
 * Hook to fetch a single execution record
 */
export function useExecutionRecord(recordId: string | undefined) {
  return useQuery({
    queryKey: testHistoryKeys.detail(recordId!),
    queryFn: () => api.getExecutionRecord(recordId!),
    enabled: !!recordId,
    staleTime: 60000, // 1 minute
  })
}

// ==================== Mutations ====================

/**
 * Hook to delete an execution record
 */
export function useDeleteExecutionRecord() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (recordId: string) => api.deleteExecutionRecord(recordId),
    onSuccess: (_, recordId) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: testHistoryKeys.detail(recordId) })

      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: testHistoryKeys.lists() })

      notifications.show({
        title: '记录已删除',
        message: '执行记录已删除',
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '删除失败',
        message: error.message || '无法删除执行记录',
        color: 'red',
      })
    },
  })
}
