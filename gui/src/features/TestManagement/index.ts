/**
 * Unified Test Management Feature
 *
 * This module exports the main TestManagement component and related utilities.
 *
 * @example
 * import { TestManagement } from '@/features/TestManagement'
 */

export { TestManagement, default } from './TestManagement'

// Re-export types for convenience
export type * from './types'

// Re-export hooks for convenience
export * from './hooks'

// Re-export API client for advanced usage
export * as testManagementAPI from './api/testManagementAPI'
