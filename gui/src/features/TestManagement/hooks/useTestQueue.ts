/**
 * TanStack Query hooks for Test Queue management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import type { TestQueueSummary, QueueTestPlanRequest } from '../types'
import * as api from '../api/testManagementAPI'
import { testPlansKeys } from './useTestPlans'

// Query Keys
export const testQueueKeys = {
  all: ['test-management', 'queue'] as const,
  list: () => [...testQueueKeys.all, 'list'] as const,
}

// ==================== Queries ====================

/**
 * Hook to fetch test execution queue
 */
export function useTestQueue() {
  return useQuery({
    queryKey: testQueueKeys.list(),
    queryFn: api.getTestQueue,
    refetchInterval: 5000, // Refresh every 5 seconds
    staleTime: 2000, // Consider stale after 2 seconds
  })
}

// ==================== Mutations ====================

/**
 * Hook to add a test plan to the execution queue
 */
export function useQueueTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: QueueTestPlanRequest) => api.queueTestPlan(payload),
    onSuccess: (queueItem, payload) => {
      // Invalidate queue list
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })

      // Update the plan's status to 'queued'
      queryClient.invalidateQueries({
        queryKey: testPlansKeys.detail(payload.test_plan_id),
      })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })

      notifications.show({
        title: '已加入队列',
        message: '测试计划已加入执行队列',
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '加入队列失败',
        message: error.message || '无法将测试计划加入队列',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to remove a test plan from the execution queue
 */
export function useRemoveFromQueue() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (queueItemId: string) => api.removeFromQueue(queueItemId),
    onMutate: async (queueItemId) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: testQueueKeys.list() })

      // Snapshot previous value
      const previousQueue = queryClient.getQueryData<TestQueueSummary[]>(
        testQueueKeys.list(),
      )

      // Optimistically remove from queue
      if (previousQueue) {
        queryClient.setQueryData<TestQueueSummary[]>(
          testQueueKeys.list(),
          previousQueue.filter((item) => item.queue_item.id !== queueItemId),
        )
      }

      return { previousQueue }
    },
    onSuccess: () => {
      // Invalidate queue and plans lists
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })

      notifications.show({
        title: '已移出队列',
        message: '测试计划已从执行队列中移除',
        color: 'green',
      })
    },
    onError: (error: Error, _, context) => {
      // Rollback on error
      if (context?.previousQueue) {
        queryClient.setQueryData(testQueueKeys.list(), context.previousQueue)
      }

      notifications.show({
        title: '移出队列失败',
        message: error.message || '无法移出队列',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to reorder items in the execution queue
 */
export function useReorderQueue() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (queueItemIds: string[]) => api.reorderQueue(queueItemIds),
    onMutate: async (queueItemIds) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: testQueueKeys.list() })

      // Snapshot previous value
      const previousQueue = queryClient.getQueryData<TestQueueSummary[]>(
        testQueueKeys.list(),
      )

      // Optimistically reorder
      if (previousQueue) {
        const orderMap = new Map(queueItemIds.map((id, index) => [id, index]))
        const reordered = [...previousQueue].sort((a, b) => {
          const orderA = orderMap.get(a.queue_item.id) ?? Infinity
          const orderB = orderMap.get(b.queue_item.id) ?? Infinity
          return orderA - orderB
        })
        queryClient.setQueryData<TestQueueSummary[]>(testQueueKeys.list(), reordered)
      }

      return { previousQueue }
    },
    onSuccess: (reorderedQueue) => {
      // Update with server response
      queryClient.setQueryData(testQueueKeys.list(), reorderedQueue)

      notifications.show({
        title: '队列已重排',
        message: '执行队列顺序已更新',
        color: 'green',
      })
    },
    onError: (error: Error, _, context) => {
      // Rollback on error
      if (context?.previousQueue) {
        queryClient.setQueryData(testQueueKeys.list(), context.previousQueue)
      }

      notifications.show({
        title: '重排失败',
        message: error.message || '无法重排队列',
        color: 'red',
      })
    },
  })
}

/**
 * Hook to update queue item priority
 */
export function useUpdateQueuePriority() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ queueItemId, priority }: { queueItemId: string; priority: number }) =>
      api.updateQueuePriority(queueItemId, priority),
    onSuccess: () => {
      // Invalidate queue list
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })

      notifications.show({
        title: '优先级已更新',
        message: '队列项优先级已更新',
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '更新失败',
        message: error.message || '无法更新优先级',
        color: 'red',
      })
    },
  })
}
