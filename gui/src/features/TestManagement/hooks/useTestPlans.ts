/**
 * TanStack Query hooks for Test Plans management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import type {
  UnifiedTestPlan,
  PlansListParams,
  CreateTestPlanRequest,
  UpdateTestPlanRequest,
} from '../types'
import * as api from '../api/testManagementAPI'

// Query Keys
export const testPlansKeys = {
  all: ['test-management', 'plans'] as const,
  lists: () => [...testPlansKeys.all, 'list'] as const,
  list: (params?: PlansListParams) => [...testPlansKeys.lists(), params] as const,
  details: () => [...testPlansKeys.all, 'detail'] as const,
  detail: (id: string) => [...testPlansKeys.details(), id] as const,
  statistics: () => [...testPlansKeys.all, 'statistics'] as const,
}

// ==================== Queries ====================

/**
 * Hook to fetch list of test plans with filters
 */
export function useTestPlans(params?: PlansListParams) {
  return useQuery({
    queryKey: testPlansKeys.list(params),
    queryFn: () => api.listTestPlans(params),
    staleTime: 30000, // 30 seconds
  })
}

/**
 * Hook to fetch a single test plan
 */
export function useTestPlan(planId: string | undefined) {
  return useQuery({
    queryKey: testPlansKeys.detail(planId!),
    queryFn: () => api.getTestPlan(planId!),
    enabled: !!planId,
    staleTime: 10000, // 10 seconds
  })
}

/**
 * Hook to fetch test plan statistics
 */
export function useTestPlanStatistics() {
  return useQuery({
    queryKey: testPlansKeys.statistics(),
    queryFn: api.getTestPlanStatistics,
    staleTime: 60000, // 1 minute
  })
}

// ==================== Mutations ====================

/**
 * Hook to create a new test plan
 */
export function useCreateTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateTestPlanRequest) => api.createTestPlan(payload),
    onSuccess: (newPlan) => {
      // Invalidate list queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.statistics() })

      // Optimistically set the new plan in cache
      queryClient.setQueryData(testPlansKeys.detail(newPlan.id), newPlan)

      notifications.show({
        title: '创建成功',
        message: `测试计划 "${newPlan.name}" 已创建`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '创建失败',
        message: error.message || '无法创建测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to update a test plan
 */
export function useUpdateTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: UpdateTestPlanRequest }) =>
      api.updateTestPlan(planId, payload),
    onMutate: async ({ planId, payload }) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: testPlansKeys.detail(planId) })

      // Snapshot previous value
      const previousPlan = queryClient.getQueryData<UnifiedTestPlan>(
        testPlansKeys.detail(planId),
      )

      // Optimistically update
      if (previousPlan) {
        queryClient.setQueryData<UnifiedTestPlan>(testPlansKeys.detail(planId), {
          ...previousPlan,
          ...payload,
          updated_at: new Date().toISOString(),
        })
      }

      return { previousPlan }
    },
    onSuccess: (updatedPlan) => {
      // Update detail cache
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)

      // Invalidate list queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })

      notifications.show({
        title: '更新成功',
        message: `测试计划 "${updatedPlan.name}" 已更新`,
        color: 'green',
      })
    },
    onError: (error: Error, { planId }, context) => {
      // Rollback on error
      if (context?.previousPlan) {
        queryClient.setQueryData(testPlansKeys.detail(planId), context.previousPlan)
      }

      notifications.show({
        title: '更新失败',
        message: error.message || '无法更新测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to delete a test plan
 */
export function useDeleteTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (planId: string) => api.deleteTestPlan(planId),
    onSuccess: (_, planId) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: testPlansKeys.detail(planId) })

      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.statistics() })

      notifications.show({
        title: '删除成功',
        message: '测试计划已删除',
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '删除失败',
        message: error.message || '无法删除测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to duplicate a test plan
 */
export function useDuplicateTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (planId: string) => api.duplicateTestPlan(planId),
    onSuccess: (newPlan) => {
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.statistics() })

      // Set new plan in cache
      queryClient.setQueryData(testPlansKeys.detail(newPlan.id), newPlan)

      notifications.show({
        title: '复制成功',
        message: `测试计划 "${newPlan.name}" 已创建`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '复制失败',
        message: error.message || '无法复制测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to batch delete test plans
 */
export function useBatchDeleteTestPlans() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (planIds: string[]) => api.batchDeleteTestPlans(planIds),
    onSuccess: (_, planIds) => {
      // Remove from cache
      planIds.forEach((planId) => {
        queryClient.removeQueries({ queryKey: testPlansKeys.detail(planId) })
      })

      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.statistics() })

      notifications.show({
        title: '批量删除成功',
        message: `已删除 ${planIds.length} 个测试计划`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '批量删除失败',
        message: error.message || '无法删除测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to export test plans
 */
export function useExportTestPlans() {
  return useMutation({
    mutationFn: (planIds: string[]) => api.exportTestPlans(planIds),
    onSuccess: (blob, planIds) => {
      // Create download link
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `test-plans-${new Date().toISOString()}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      notifications.show({
        title: '导出成功',
        message: `已导出 ${planIds.length} 个测试计划`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '导出失败',
        message: error.message || '无法导出测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to import test plans
 */
export function useImportTestPlans() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (file: File) => api.importTestPlans(file),
    onSuccess: (plans) => {
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.statistics() })

      // Set new plans in cache
      plans.forEach((plan) => {
        queryClient.setQueryData(testPlansKeys.detail(plan.id), plan)
      })

      notifications.show({
        title: '导入成功',
        message: `已导入 ${plans.length} 个测试计划`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '导入失败',
        message: error.message || '无法导入测试计划',
        color: 'red',
      })
    },
  })
}
