/**
 * Unified Report API Service
 */

import client from './client'
import type { Report, ReportListResponse, CreateReportRequest } from '../types/report'

const BASE_URL = '/reports'

/**
 * Create a new report
 */
export async function createReport(data: CreateReportRequest): Promise<Report> {
  const response = await client.post<Report>(BASE_URL, data)
  return response.data
}

/**
 * Get a report by ID
 */
export async function fetchReport(reportId: string): Promise<Report> {
  const response = await client.get<Report>(`${BASE_URL}/${reportId}`)
  return response.data
}

/**
 * List reports with optional filters
 */
export async function fetchReports(params?: {
  skip?: number
  limit?: number
  status?: string
  report_type?: string
  generated_by?: string
}): Promise<ReportListResponse> {
  const response = await client.get<ReportListResponse>(BASE_URL, { params })
  return response.data
}

/**
 * Get report by road test execution ID
 */
export async function fetchReportByRoadTestExecution(executionId: string): Promise<Report | null> {
  try {
    const response = await client.get<ReportListResponse>(BASE_URL, {
      params: { road_test_execution_id: executionId, limit: 1 }
    })
    if (response.data.reports.length > 0) {
      // Fetch full report with content_data
      return fetchReport(response.data.reports[0].id)
    }
    return null
  } catch {
    return null
  }
}

/**
 * Delete a report
 */
export async function deleteReport(reportId: string): Promise<void> {
  await client.delete(`${BASE_URL}/${reportId}`)
}


/** 独立审计资料，不是可正式交付的报告。 */
export async function fetchCalibrationAudit(reportId: string): Promise<string> {
  const response = await client.get<string>(`${BASE_URL}/${reportId}/calibration-audit`, {
    responseType: 'text', transformResponse: [(raw: string) => raw],
  })
  const data: import('../types/api').ReportCalibrationAudit = JSON.parse(response.data)
  if (data?.report_id !== reportId || data?.audit_kind !== 'calibration_audit' || data?.formal_eligible !== false) {
    throw new Error('审计包身份或用途声明不一致，未下载')
  }
  // 只解析副本核对身份；下载保留原文，避免浮点文本改写使原始证据hash失配。
  return response.data
}
