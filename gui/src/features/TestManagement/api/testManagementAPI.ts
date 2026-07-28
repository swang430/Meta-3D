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
  TestExecutionRecord,
  HistoryFilters,
} from '../types'

// ==================== Test Plans Management ====================

// ==================== Steps Management ====================

// ==================== Queue Management ====================

// ==================== Execution Control ====================

// ==================== Execution History ====================

/**
 * 执行历史 (ARCH-1 S2: 行 = test_executions 本表, 行 id 可直接作
 * 报告的 test_execution_ids)。单条查询与删除随换源退场:
 * 删除会毁掉报告引用并留下孤儿快照 (待决① 拍板去掉), 清理走脚本。
 */
export interface ExecutionHistoryPage {
  total: number
  items: TestExecutionRecord[]
}

export const getExecutionHistory = async (
  filters?: HistoryFilters,
): Promise<ExecutionHistoryPage> => {
  // 内审 F2: 不再丢弃后端 total — 换源后行基数放大 (每次执行一行),
  // "拿到的行数"≠"总执行数"; limit 顶到后端上限, 完整分页后端化留 backlog
  const response = await client.get<ExecutionHistoryPage>(
    '/test-executions',
    { params: { limit: 1000, ...filters } },
  )
  return response.data
}

// ==================== Sequence Library ====================

// ==================== Statistics & Analytics ====================

// ==================== Batch Operations ====================
