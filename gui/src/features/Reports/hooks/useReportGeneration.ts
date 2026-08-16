/**
 * Report Generation Hook
 *
 * Unified hook for generating reports from test plan executions and VRT executions.
 * Ensures consistent behavior across different entry points.
 */

import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import * as ReportsAPI from '../api/reportsAPI'
import * as RoadTestAPI from '../../../api/roadTestService'
import type { CreateReportRequest } from '../types'

// 执行记录 (ARCH-1 S2: 行来自 test_executions 本表, id 就是
// TestExecution.id — 报告的 test_execution_ids 直接引用它,
// 收集器真查得到行。旧计划摘要形状的 TestPlanExecutionRecord 已退场。)
export interface ExecutionRecord {
  id: string
  case_name: string | null
  status: string
}

// Virtual Road Test Execution Record interface
export interface RoadTestExecutionRecord {
  execution_id: string
  scenario_id: string
  scenario_name: string
  mode: string
  status: string
  progress_percent: number
  start_time?: string
  end_time?: string
  duration_s?: number
}

// Report generation options
export interface ReportGenerationOptions {
  format?: 'pdf' | 'html' | 'excel'
  includeRawData?: boolean
  includeCharts?: boolean
  includeStatistics?: boolean
  includeRecommendations?: boolean
}

const defaultOptions: Required<ReportGenerationOptions> = {
  format: 'pdf',
  includeRawData: false,
  includeCharts: true,
  includeStatistics: true,
  includeRecommendations: true,
}

/**
 * Hook for unified report generation
 *
 * Provides consistent report generation for both test plans and VRT executions.
 * Handles data fetching, report creation, and cache invalidation.
 */
export function useReportGeneration() {
  const queryClient = useQueryClient()
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set())

  // Invalidate all relevant caches after report generation
  // (ARCH-1 S2: pending / history 两个 key 随换源换代 — 返回形状变了
  // 必须换 key, 前缀 invalidate 对新 key 仍命中)
  const invalidateCaches = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['reports'] })
    queryClient.invalidateQueries({ queryKey: ['archived-execution-ids'] })
    queryClient.invalidateQueries({ queryKey: ['pending-executions', 'v2'] })
    queryClient.invalidateQueries({ queryKey: ['pending-road-test-executions'] })
    queryClient.invalidateQueries({ queryKey: ['test-management', 'history', 'v2'] })
  }, [queryClient])

  // 执行报告 (ARCH-1 S2: record.id = TestExecution.id, 收集器按它查执行行;
  // 不再传 test_plan_id — 用例执行不挂计划, 收集器无 plan 路径已体面化)
  const executionMutation = useMutation({
    mutationFn: async ({
      record,
      options = {},
    }: {
      record: ExecutionRecord
      options?: ReportGenerationOptions
    }) => {
      const opts = { ...defaultOptions, ...options }
      const displayName = record.case_name ?? '未命名用例'

      const reportRequest: CreateReportRequest = {
        title: `${displayName} - 执行报告`,
        report_type: 'single_execution',
        format: opts.format,
        generated_by: 'user',
        description: `测试用例 "${displayName}" 的执行报告`,
        test_execution_ids: [record.id],
        include_raw_data: opts.includeRawData,
        include_charts: opts.includeCharts,
        include_statistics: opts.includeStatistics,
        include_recommendations: opts.includeRecommendations,
      }

      // Create report
      const report = await ReportsAPI.createReport(reportRequest)

      // Trigger generation
      await ReportsAPI.generateReport(report.id)

      return report
    },
    onSuccess: (report) => {
      invalidateCaches()
      notifications.show({
        title: '报告生成中',
        message: `报告 "${report.title}" 正在生成，请在报告管理页面查看`,
        color: 'blue',
      })
    },
    onError: async (error: Error) => {
      notifications.show({
        title: '生成失败',
        message: `无法生成报告: ${await ReportsAPI.reportApiErrorMessage(error)}`,
        color: 'red',
      })
    },
  })

  // Mutation for VRT report generation
  const vrtMutation = useMutation({
    mutationFn: async ({
      record,
      options = {},
    }: {
      record: RoadTestExecutionRecord
      options?: ReportGenerationOptions
    }) => {
      void options
      // VRT archive content must be rebuilt by the server from the terminal
      // execution.  The generic report endpoint intentionally cannot accept
      // client-supplied VRT content or claim the execution's unique slot.
      return RoadTestAPI.archiveExecutionReport(record.execution_id)
    },
    onSuccess: (report) => {
      invalidateCaches()
      const completed = report.status === 'completed'
      notifications.show({
        title: completed ? '报告已归档' : '报告生成中',
        message: completed
          ? `报告 "${report.title}" 已从权威执行数据生成`
          : `报告 "${report.title}" 正在生成，请在报告管理页面查看`,
        color: completed ? 'green' : 'blue',
      })
    },
    onError: async (error: Error) => {
      notifications.show({
        title: '生成失败',
        message: `无法生成报告: ${await ReportsAPI.reportApiErrorMessage(error)}`,
        color: 'red',
      })
    },
  })

  // Generate report for a test execution (ARCH-1 S2)
  const generateExecutionReport = useCallback(
    async (record: ExecutionRecord, options?: ReportGenerationOptions) => {
      setGeneratingIds((prev) => new Set(prev).add(record.id))
      try {
        await executionMutation.mutateAsync({ record, options })
      } finally {
        setGeneratingIds((prev) => {
          const next = new Set(prev)
          next.delete(record.id)
          return next
        })
      }
    },
    [executionMutation]
  )

  // Generate report for VRT execution
  const generateVRTReport = useCallback(
    async (record: RoadTestExecutionRecord, options?: ReportGenerationOptions) => {
      setGeneratingIds((prev) => new Set(prev).add(record.execution_id))
      try {
        await vrtMutation.mutateAsync({ record, options })
      } finally {
        setGeneratingIds((prev) => {
          const next = new Set(prev)
          next.delete(record.execution_id)
          return next
        })
      }
    },
    [vrtMutation]
  )

  // Check if a specific execution is generating
  const isGenerating = useCallback(
    (id: string) => generatingIds.has(id),
    [generatingIds]
  )

  return {
    generateExecutionReport,
    generateVRTReport,
    isGenerating,
    isExecutionGenerating: executionMutation.isPending,
    isVRTGenerating: vrtMutation.isPending,
  }
}

export default useReportGeneration
