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

// Test Plan Execution Record interface
export interface TestPlanExecutionRecord {
  id: string
  test_plan_id: string
  test_plan_name: string
  test_plan_version: string
  status: string
  success_rate: number
  total_steps: number
  completed_steps: number
  failed_steps: number
  duration_minutes: number
  started_by: string
  completed_at: string
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
  const invalidateCaches = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['reports'] })
    queryClient.invalidateQueries({ queryKey: ['archived-execution-ids'] })
    queryClient.invalidateQueries({ queryKey: ['pending-test-plan-executions'] })
    queryClient.invalidateQueries({ queryKey: ['pending-road-test-executions'] })
    queryClient.invalidateQueries({ queryKey: ['test-management', 'history'] })
  }, [queryClient])

  // Mutation for test plan report generation
  const testPlanMutation = useMutation({
    mutationFn: async ({
      record,
      options = {},
    }: {
      record: TestPlanExecutionRecord
      options?: ReportGenerationOptions
    }) => {
      const opts = { ...defaultOptions, ...options }

      const reportRequest: CreateReportRequest = {
        title: `${record.test_plan_name} - 执行报告`,
        report_type: 'single_execution',
        format: opts.format,
        generated_by: 'user',
        description: `测试计划 "${record.test_plan_name}" (版本 ${record.test_plan_version}) 的执行报告`,
        test_plan_id: record.test_plan_id,
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
    onError: (error: Error) => {
      notifications.show({
        title: '生成失败',
        message: `无法生成报告: ${error.message}`,
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
      const opts = { ...defaultOptions, ...options }

      // First, fetch the complete execution report data
      // This is critical - VRT reports need content_data to be passed
      let contentData: Record<string, any> | undefined
      try {
        const executionReport = await RoadTestAPI.fetchExecutionReport(record.execution_id)
        contentData = executionReport as unknown as Record<string, any>
      } catch (error) {
        console.warn('Failed to fetch VRT execution report data:', error)
        // Continue without content_data - backend will try to reconstruct
      }

      const reportRequest: CreateReportRequest = {
        title: `${record.scenario_name} - 路测报告`,
        report_type: 'single_execution',
        format: opts.format,
        generated_by: 'user',
        description: `虚拟路测场景 "${record.scenario_name}" 的执行报告`,
        road_test_execution_id: record.execution_id,
        include_raw_data: opts.includeRawData,
        include_charts: opts.includeCharts,
        include_statistics: opts.includeStatistics,
        include_recommendations: opts.includeRecommendations,
        // Pass content_data directly - backend stores it in DB and uses during generation
        // This ensures VRT report data is available even if the in-memory execution is gone
        ...(contentData && { content_data: contentData }),
      }

      // Create report (content_data is stored in the report record)
      const report = await ReportsAPI.createReport(reportRequest)

      // Trigger generation - backend will use content_data from the report record
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
    onError: (error: Error) => {
      notifications.show({
        title: '生成失败',
        message: `无法生成报告: ${error.message}`,
        color: 'red',
      })
    },
  })

  // Generate report for test plan execution
  const generateTestPlanReport = useCallback(
    async (record: TestPlanExecutionRecord, options?: ReportGenerationOptions) => {
      setGeneratingIds((prev) => new Set(prev).add(record.id))
      try {
        await testPlanMutation.mutateAsync({ record, options })
      } finally {
        setGeneratingIds((prev) => {
          const next = new Set(prev)
          next.delete(record.id)
          return next
        })
      }
    },
    [testPlanMutation]
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
    generateTestPlanReport,
    generateVRTReport,
    isGenerating,
    isTestPlanGenerating: testPlanMutation.isPending,
    isVRTGenerating: vrtMutation.isPending,
  }
}

export default useReportGeneration
