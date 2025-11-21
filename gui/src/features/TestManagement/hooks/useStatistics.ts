/**
 * TanStack Query hooks for Statistics & Analytics
 */

import { useQuery } from '@tanstack/react-query'
import * as api from '../api/testManagementAPI'

// Query Keys
export const statisticsKeys = {
  all: ['test-management', 'statistics'] as const,
  plans: () => [...statisticsKeys.all, 'plans'] as const,
  executions: (startDate?: string, endDate?: string) =>
    [...statisticsKeys.all, 'executions', { startDate, endDate }] as const,
}

// ==================== Queries ====================

/**
 * Hook to fetch test plan statistics
 */
export function useTestPlanStatistics() {
  return useQuery({
    queryKey: statisticsKeys.plans(),
    queryFn: api.getTestPlanStatistics,
    staleTime: 60000, // 1 minute
  })
}

/**
 * Hook to fetch execution statistics
 */
export function useExecutionStatistics(startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: statisticsKeys.executions(startDate, endDate),
    queryFn: () => api.getExecutionStatistics(startDate, endDate),
    staleTime: 60000, // 1 minute
  })
}
