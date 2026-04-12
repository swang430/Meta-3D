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
