/**
 * TanStack Query hooks for Test Steps management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import type {
  TestStep,
  AddStepRequest,
  UpdateStepRequest,
  ReorderStepsRequest,
} from '../types'
import * as api from '../api/testManagementAPI'
import { testPlansKeys } from './useTestPlans'

// Query Keys
export const testStepsKeys = {
  all: ['test-management', 'steps'] as const,
  byPlan: (planId: string) => [...testStepsKeys.all, 'plan', planId] as const,
}

// ==================== Queries ====================

/**
 * Hook to fetch all steps for a test plan
 */
export function useTestSteps(planId: string | undefined) {
  return useQuery({
    queryKey: testStepsKeys.byPlan(planId!),
    queryFn: () => api.getTestSteps(planId!),
    enabled: !!planId,
    staleTime: 10000, // 10 seconds
  })
}

// ==================== Mutations ====================

/**
 * Hook to add a new step to a test plan
 */
export function useAddTestStep() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: AddStepRequest }) =>
      api.addTestStep(planId, payload),
    onSuccess: (newStep, { planId }) => {
      // Invalidate steps list
      queryClient.invalidateQueries({ queryKey: testStepsKeys.byPlan(planId) })

      // Invalidate parent plan (to update step count)
      queryClient.invalidateQueries({ queryKey: testPlansKeys.detail(planId) })

      notifications.show({
        title: '步骤已添加',
        message: `步骤 "${newStep.title}" 已添加`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '添加失败',
        message: error.message || '无法添加步骤',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to update a test step
 */
export function useUpdateTestStep() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      planId,
      stepId,
      payload,
    }: {
      planId: string
      stepId: string
      payload: UpdateStepRequest
    }) => api.updateTestStep(planId, stepId, payload),
    onMutate: async ({ planId, stepId, payload }) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: testStepsKeys.byPlan(planId) })

      // Snapshot previous value
      const previousSteps = queryClient.getQueryData<TestStep[]>(testStepsKeys.byPlan(planId))

      // Optimistically update
      if (previousSteps) {
        queryClient.setQueryData<TestStep[]>(
          testStepsKeys.byPlan(planId),
          previousSteps.map((step) =>
            step.id === stepId ? { ...step, ...payload } : step,
          ),
        )
      }

      return { previousSteps }
    },
    onSuccess: (updatedStep, { planId }) => {
      // Update steps list
      queryClient.invalidateQueries({ queryKey: testStepsKeys.byPlan(planId) })

      notifications.show({
        title: '步骤已更新',
        message: `步骤 "${updatedStep.title}" 已更新`,
        color: 'green',
      })
    },
    onError: (error: Error, { planId }, context) => {
      // Rollback on error
      if (context?.previousSteps) {
        queryClient.setQueryData(testStepsKeys.byPlan(planId), context.previousSteps)
      }

      notifications.show({
        title: '更新失败',
        message: error.message || '无法更新步骤',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to delete a test step
 */
export function useDeleteTestStep() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, stepId }: { planId: string; stepId: string }) =>
      api.deleteTestStep(planId, stepId),
    onMutate: async ({ planId, stepId }) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: testStepsKeys.byPlan(planId) })

      // Snapshot previous value
      const previousSteps = queryClient.getQueryData<TestStep[]>(testStepsKeys.byPlan(planId))

      // Optimistically remove step
      if (previousSteps) {
        queryClient.setQueryData<TestStep[]>(
          testStepsKeys.byPlan(planId),
          previousSteps.filter((step) => step.id !== stepId),
        )
      }

      return { previousSteps }
    },
    onSuccess: (_, { planId }) => {
      // Invalidate steps list
      queryClient.invalidateQueries({ queryKey: testStepsKeys.byPlan(planId) })

      // Invalidate parent plan (to update step count)
      queryClient.invalidateQueries({ queryKey: testPlansKeys.detail(planId) })

      notifications.show({
        title: '步骤已删除',
        message: '步骤已从测试计划中删除',
        color: 'green',
      })
    },
    onError: (error: Error, { planId }, context) => {
      // Rollback on error
      if (context?.previousSteps) {
        queryClient.setQueryData(testStepsKeys.byPlan(planId), context.previousSteps)
      }

      notifications.show({
        title: '删除失败',
        message: error.message || '无法删除步骤',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to reorder steps in a test plan
 */
export function useReorderTestSteps() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: ReorderStepsRequest }) =>
      api.reorderTestSteps(planId, payload),
    onMutate: async ({ planId, payload }) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: testStepsKeys.byPlan(planId) })

      // Snapshot previous value
      const previousSteps = queryClient.getQueryData<TestStep[]>(testStepsKeys.byPlan(planId))

      // Optimistically reorder
      if (previousSteps) {
        const orderMap = new Map(payload.step_orders.map((item) => [item.step_id, item.order]))
        const reorderedSteps = [...previousSteps].sort((a, b) => {
          const orderA = orderMap.get(a.id) ?? a.order
          const orderB = orderMap.get(b.id) ?? b.order
          return orderA - orderB
        })
        queryClient.setQueryData<TestStep[]>(testStepsKeys.byPlan(planId), reorderedSteps)
      }

      return { previousSteps }
    },
    onSuccess: (reorderedSteps, { planId }) => {
      // Update with server response
      queryClient.setQueryData(testStepsKeys.byPlan(planId), reorderedSteps)

      notifications.show({
        title: '步骤已重排',
        message: '步骤顺序已更新',
        color: 'green',
      })
    },
    onError: (error: Error, { planId }, context) => {
      // Rollback on error
      if (context?.previousSteps) {
        queryClient.setQueryData(testStepsKeys.byPlan(planId), context.previousSteps)
      }

      notifications.show({
        title: '重排失败',
        message: error.message || '无法重排步骤',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to duplicate a test step
 */
export function useDuplicateTestStep() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, stepId }: { planId: string; stepId: string }) =>
      api.duplicateTestStep(planId, stepId),
    onSuccess: (newStep, { planId }) => {
      // Invalidate steps list
      queryClient.invalidateQueries({ queryKey: testStepsKeys.byPlan(planId) })

      // Invalidate parent plan
      queryClient.invalidateQueries({ queryKey: testPlansKeys.detail(planId) })

      notifications.show({
        title: '步骤已复制',
        message: `步骤 "${newStep.title}" 已创建`,
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '复制失败',
        message: error.message || '无法复制步骤',
        color: 'red',
      })
    },
  })
}
