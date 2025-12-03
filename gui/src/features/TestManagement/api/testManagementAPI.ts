/**
 * Unified Test Management API Client
 *
 * This module provides API functions for the unified test management system,
 * integrating concepts from both TestConfig and TestPlanManagement modules.
 *
 * @version 2.0.0
 * @date 2025-11-18
 */

import client from '../../../api/client'
import type {
  UnifiedTestPlan,
  TestPlanSummary,
  TestStep,
  TestQueueItem,
  TestQueueSummary,
  TestExecutionRecord,
  SequenceLibraryItem,
  PlansListParams,
  PlansListResponse,
  CreateTestPlanRequest,
  UpdateTestPlanRequest,
  AddStepRequest,
  UpdateStepRequest,
  ReorderStepsRequest,
  QueueTestPlanRequest,
  StartExecutionRequest,
  PauseExecutionRequest,
  ResumeExecutionRequest,
  CancelExecutionRequest,
  HistoryFilters,
  SequenceLibraryFilters,
} from '../types'

// ==================== Test Plans Management ====================

/**
 * List test plans with filters and pagination
 */
export const listTestPlans = async (params?: PlansListParams): Promise<PlansListResponse> => {
  const response = await client.get<PlansListResponse>('/test-plans', { params })
  return response.data
}

/**
 * Get a single test plan by ID
 */
export const getTestPlan = async (planId: string): Promise<UnifiedTestPlan> => {
  const response = await client.get<UnifiedTestPlan>(`/test-plans/${planId}`)
  return response.data
}

/**
 * Create a new test plan
 */
export const createTestPlan = async (
  payload: CreateTestPlanRequest,
): Promise<UnifiedTestPlan> => {
  const response = await client.post<UnifiedTestPlan>('/test-plans', payload)
  return response.data
}

/**
 * Update an existing test plan
 */
export const updateTestPlan = async (
  planId: string,
  payload: UpdateTestPlanRequest,
): Promise<UnifiedTestPlan> => {
  const response = await client.patch<UnifiedTestPlan>(
    `/test-plans/${planId}`,
    payload,
  )
  return response.data
}

/**
 * Delete a test plan
 */
export const deleteTestPlan = async (planId: string): Promise<void> => {
  await client.delete(`/test-plans/${planId}`)
}

/**
 * Duplicate a test plan
 */
export const duplicateTestPlan = async (planId: string): Promise<UnifiedTestPlan> => {
  const response = await client.post<UnifiedTestPlan>(
    `/test-plans/${planId}/duplicate`,
  )
  return response.data
}

// ==================== Steps Management ====================

/**
 * Get all steps for a test plan
 */
export const getTestSteps = async (planId: string): Promise<TestStep[]> => {
  const response = await client.get<TestStep[]>(
    `/test-plans/${planId}/steps`,
  )
  return response.data
}

/**
 * Add a new step to a test plan
 */
export const addTestStep = async (
  planId: string,
  payload: AddStepRequest,
): Promise<TestStep> => {
  const response = await client.post<TestStep>(
    `/test-plans/${planId}/steps`,
    payload,
  )
  return response.data
}

/**
 * Update an existing step
 */
export const updateTestStep = async (
  planId: string,
  stepId: string,
  payload: UpdateStepRequest,
): Promise<TestStep> => {
  const response = await client.patch<TestStep>(
    `/test-plans/${planId}/steps/${stepId}`,
    payload,
  )
  return response.data
}

/**
 * Delete a step from a test plan
 */
export const deleteTestStep = async (planId: string, stepId: string): Promise<void> => {
  await client.delete(`/test-plans/${planId}/steps/${stepId}`)
}

/**
 * Reorder steps in a test plan
 */
export const reorderTestSteps = async (
  planId: string,
  payload: ReorderStepsRequest,
): Promise<TestStep[]> => {
  const response = await client.post<{ steps: TestStep[] }>(
    `/test-plans/${planId}/steps/reorder`,
    payload,
  )
  return response.data.steps
}

/**
 * Duplicate a step within a test plan
 */
export const duplicateTestStep = async (
  planId: string,
  stepId: string,
): Promise<TestStep> => {
  const response = await client.post<TestStep>(
    `/test-plans/${planId}/steps/${stepId}/duplicate`,
  )
  return response.data
}

// ==================== Queue Management ====================

/**
 * Get the test execution queue
 */
export const getTestQueue = async (): Promise<TestQueueSummary[]> => {
  const response = await client.get<{ items: TestQueueSummary[] }>(
    '/test-plans/queue',
  )
  return response.data.items
}

/**
 * Add a test plan to the execution queue
 */
export const queueTestPlan = async (
  payload: QueueTestPlanRequest,
): Promise<TestQueueItem> => {
  const response = await client.post<TestQueueItem>('/test-plans/queue', payload)
  return response.data
}

/**
 * Remove a test plan from the execution queue
 */
export const removeFromQueue = async (queueItemId: string): Promise<void> => {
  await client.delete(`/test-plans/queue/${queueItemId}`)
}

/**
 * Reorder items in the execution queue
 */
export const reorderQueue = async (
  queueItemIds: string[],
): Promise<TestQueueSummary[]> => {
  const response = await client.post<{ items: TestQueueSummary[] }>(
    '/test-plans/queue/reorder',
    { queue_item_ids: queueItemIds },
  )
  return response.data.items
}

/**
 * Update queue item priority
 */
export const updateQueuePriority = async (
  queueItemId: string,
  priority: number,
): Promise<TestQueueItem> => {
  const response = await client.patch<TestQueueItem>(
    `/test-plans/queue/${queueItemId}/priority`,
    { priority },
  )
  return response.data
}

// ==================== Execution Control ====================

/**
 * Start execution of a queued test plan
 */
export const startExecution = async (
  planId: string,
  payload: StartExecutionRequest,
): Promise<UnifiedTestPlan> => {
  const response = await client.post<UnifiedTestPlan>(
    `/test-plans/${planId}/start`,
    payload,
  )
  return response.data
}

/**
 * Pause an executing test plan
 */
export const pauseExecution = async (
  planId: string,
  payload: PauseExecutionRequest,
): Promise<UnifiedTestPlan> => {
  const response = await client.post<UnifiedTestPlan>(
    `/test-plans/${planId}/pause`,
    payload,
  )
  return response.data
}

/**
 * Resume a paused test plan
 */
export const resumeExecution = async (
  planId: string,
  payload: ResumeExecutionRequest,
): Promise<UnifiedTestPlan> => {
  const response = await client.post<UnifiedTestPlan>(
    `/test-plans/${planId}/resume`,
    payload,
  )
  return response.data
}

/**
 * Cancel an executing test plan
 */
export const cancelExecution = async (
  planId: string,
  payload: CancelExecutionRequest,
): Promise<UnifiedTestPlan> => {
  const response = await client.post<UnifiedTestPlan>(
    `/test-plans/${planId}/cancel`,
    payload,
  )
  return response.data
}

// ==================== Execution History ====================

/**
 * Get execution history with filters
 */
export const getExecutionHistory = async (
  filters?: HistoryFilters,
): Promise<TestExecutionRecord[]> => {
  const response = await client.get<{ items: TestExecutionRecord[] }>(
    '/test-executions',
    { params: filters },
  )
  return response.data.items
}

/**
 * Get a single execution record by ID
 */
export const getExecutionRecord = async (
  recordId: string,
): Promise<TestExecutionRecord> => {
  const response = await client.get<TestExecutionRecord>(
    `/test-executions/${recordId}`,
  )
  return response.data
}

/**
 * Delete an execution record
 */
export const deleteExecutionRecord = async (recordId: string): Promise<void> => {
  await client.delete(`/test-executions/${recordId}`)
}

// ==================== Sequence Library ====================

/**
 * Get sequence library items with filters
 */
export const getSequenceLibrary = async (
  filters?: SequenceLibraryFilters,
): Promise<SequenceLibraryItem[]> => {
  const response = await client.get<{ items: SequenceLibraryItem[] }>(
    '/test-sequences',
    { params: filters },
  )
  return response.data.items
}

/**
 * Get a single sequence library item by ID
 */
export const getSequenceLibraryItem = async (
  itemId: string,
): Promise<SequenceLibraryItem> => {
  const response = await client.get<SequenceLibraryItem>(
    `/test-sequences/${itemId}`,
  )
  return response.data
}

/**
 * Get sequence library categories
 */
export const getSequenceCategories = async (): Promise<string[]> => {
  const response = await client.get<{ categories: string[] }>(
    '/test-sequences/categories',
  )
  return response.data.categories
}

/**
 * Get popular sequence library items
 */
export const getPopularSequences = async (limit: number = 10): Promise<SequenceLibraryItem[]> => {
  const response = await client.get<{ items: SequenceLibraryItem[] }>(
    '/test-sequences/popular',
    { params: { limit } },
  )
  return response.data.items
}

// ==================== Statistics & Analytics ====================

/**
 * Get test plan statistics
 */
export const getTestPlanStatistics = async () => {
  const response = await client.get<{
    total: number
    by_status: Record<string, number>
    avg_duration_minutes: number
    success_rate: number
  }>('/test-plans/statistics/plans')
  return response.data
}

/**
 * Get execution statistics
 */
export const getExecutionStatistics = async (startDate?: string, endDate?: string) => {
  const response = await client.get<{
    total_executions: number
    total_duration_minutes: number
    avg_duration_minutes: number
    success_rate: number
    executions_by_day: Array<{ date: string; count: number }>
  }>('/test-plans/statistics/executions', {
    params: { start_date: startDate, end_date: endDate },
  })
  return response.data
}

// ==================== Batch Operations ====================

/**
 * Batch delete test plans
 */
export const batchDeleteTestPlans = async (planIds: string[]): Promise<void> => {
  await client.post('/test-plans/batch-delete', { plan_ids: planIds })
}

/**
 * Batch update test plan status
 */
export const batchUpdatePlanStatus = async (
  planIds: string[],
  status: string,
): Promise<void> => {
  await client.post('/test-plans/batch-update-status', {
    plan_ids: planIds,
    status,
  })
}

/**
 * Export test plans to JSON
 */
export const exportTestPlans = async (planIds: string[]): Promise<Blob> => {
  const response = await client.post(
    '/test-plans/export',
    { plan_ids: planIds },
    { responseType: 'blob' },
  )
  return response.data
}

/**
 * Import test plans from JSON
 */
export const importTestPlans = async (file: File): Promise<UnifiedTestPlan[]> => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await client.post<{ plans: UnifiedTestPlan[] }>(
    '/test-plans/import',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  )
  return response.data.plans
}
