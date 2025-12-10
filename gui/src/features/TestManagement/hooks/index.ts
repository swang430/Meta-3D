/**
 * Unified Test Management Hooks
 *
 * This module exports all TanStack Query hooks for the unified test management system.
 * Import hooks from this index file for convenience.
 *
 * @example
 * import { useTestPlans, useCreateTestPlan } from '@/features/TestManagement/hooks'
 */

// Test Plans
export {
  useTestPlans,
  useTestPlan,
  useTestPlanStatistics as useTestPlanStats,
  useCreateTestPlan,
  useUpdateTestPlan,
  useDeleteTestPlan,
  useDuplicateTestPlan,
  useBatchDeleteTestPlans,
  useExportTestPlans,
  useImportTestPlans,
  testPlansKeys,
} from './useTestPlans'

// Test Steps
export {
  useTestSteps,
  useAddTestStep,
  useUpdateTestStep,
  useDeleteTestStep,
  useReorderTestSteps,
  useDuplicateTestStep,
  testStepsKeys,
} from './useTestSteps'

// Test Queue
export {
  useTestQueue,
  useQueueTestPlan,
  useRemoveFromQueue,
  useReorderQueue,
  useUpdateQueuePriority,
  testQueueKeys,
} from './useTestQueue'

// Test Execution
export {
  useStartExecution,
  usePauseExecution,
  useResumeExecution,
  useCancelExecution,
  useCompleteExecution,
} from './useTestExecution'

// Test History
export {
  useTestHistory,
  useExecutionRecord,
  useDeleteExecutionRecord,
  testHistoryKeys,
} from './useTestHistory'

// Sequence Library
export {
  useSequenceLibrary,
  useSequenceLibraryItem,
  useSequenceCategories,
  usePopularSequences,
  sequenceLibraryKeys,
} from './useSequenceLibrary'

// Statistics
export {
  useTestPlanStatistics,
  useExecutionStatistics,
  statisticsKeys,
} from './useStatistics'
