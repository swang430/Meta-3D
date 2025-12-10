/**
 * TanStack Query hooks for Test Execution control
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import type {
  StartExecutionRequest,
  PauseExecutionRequest,
  ResumeExecutionRequest,
  CancelExecutionRequest,
} from '../types'
import * as api from '../api/testManagementAPI'
import { testPlansKeys } from './useTestPlans'
import { testQueueKeys } from './useTestQueue'

// ==================== Mutations ====================

/**
 * Hook to start execution of a queued test plan
 */
export function useStartExecution() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: StartExecutionRequest }) =>
      api.startExecution(planId, payload),
    onSuccess: (updatedPlan) => {
      // Update plan cache
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })

      notifications.show({
        title: '执行已开始',
        message: `测试计划 "${updatedPlan.name}" 开始执行`,
        color: 'blue',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '启动失败',
        message: error.message || '无法启动测试计划执行',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to pause an executing test plan
 */
export function usePauseExecution() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: PauseExecutionRequest }) =>
      api.pauseExecution(planId, payload),
    onSuccess: (updatedPlan) => {
      // Update plan cache
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })

      notifications.show({
        title: '执行已暂停',
        message: `测试计划 "${updatedPlan.name}" 已暂停`,
        color: 'yellow',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '暂停失败',
        message: error.message || '无法暂停测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to resume a paused test plan
 */
export function useResumeExecution() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: ResumeExecutionRequest }) =>
      api.resumeExecution(planId, payload),
    onSuccess: (updatedPlan) => {
      // Update plan cache
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })

      notifications.show({
        title: '执行已恢复',
        message: `测试计划 "${updatedPlan.name}" 继续执行`,
        color: 'blue',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '恢复失败',
        message: error.message || '无法恢复测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to cancel an executing test plan
 */
export function useCancelExecution() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: CancelExecutionRequest }) =>
      api.cancelExecution(planId, payload),
    onSuccess: (updatedPlan) => {
      // Update plan cache
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })

      notifications.show({
        title: '执行已取消',
        message: `测试计划 "${updatedPlan.name}" 已取消`,
        color: 'orange',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '取消失败',
        message: error.message || '无法取消测试计划',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to complete an executing test plan
 */
export function useCompleteExecution() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (planId: string) => api.completeExecution(planId),
    onSuccess: (updatedPlan) => {
      // Update plan cache
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })

      notifications.show({
        title: '执行已完成',
        message: `测试计划 "${updatedPlan.name}" 已完成`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '完成失败',
        message: error.message || '无法完成测试计划',
        color: 'red',
      })
    },
  })
}
